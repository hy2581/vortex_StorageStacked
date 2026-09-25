"""Official host/runtime + SimX, with one online path for GPU external memory."""
import argparse
import json
import os
from pathlib import Path

import m5
from m5.objects import (
    AddrRange, AxiDemo, Cache, Gem5ToTlmBridge64, HetAxiMonitor, L2XBar,
    Process, Root, SEWorkload, SimpleMemory, SrcClockDomain, System,
    SystemC_Kernel, SystemXBar, TimingSimpleCPU, VoltageDomain, VortexGPGPU,
)


class L1(Cache):
    assoc = 8
    tag_latency = 1
    data_latency = 1
    response_latency = 1
    mshrs = 16
    tgts_per_mshr = 20


class L2(Cache):
    assoc = 16
    tag_latency = 10
    data_latency = 10
    response_latency = 10
    mshrs = 32
    tgts_per_mshr = 12
    write_buffers = 16


def connect_memory(system, architecture, bar, output):
    """BAR requests: gem5 packets -> TLM -> AXI256 -> UCIe -> mem_sim."""
    axi = architecture['axi']
    memory = architecture['memory']
    base, size = bar
    system.axi = AxiDemo(
        backend='aou', memory_backend='memsim', base=base, size=size,
        period=f"{axi['period_ns']}ns", outstanding=axi['outstanding'],
        planes=axi['planes'], stalls=axi['stalls'], replay=axi['replay'],
        memsim_standard=memory['standard'], memsim_channels=memory['channels'],
        memsim_scale=memory['scale'], memsim_queue=memory['queue'],
        memsim_slots=memory['slots'], memsim_response_hold=memory['response_hold'],
        trace_dir=str(output),
    )
    system.bridge = Gem5ToTlmBridge64(addr_ranges=[AddrRange(base, size=size)])
    system.bridge.tlm = system.axi.tlm
    # Observe accepted packets; the monitor does not execute or replay traffic.
    system.monitor = HetAxiMonitor(
        trace_host=True, trace_device=True,
        host_clock_period=10**9 // architecture['host']['clock_mhz'],
        device_clock_period=10**9 // architecture['device_clock_mhz'],
    )
    system.monitor.mem_side_port = system.bridge.gem5
    system.monitor.cpu_side_port = system.membus.mem_side_ports


def connect_host(system, config, host_region):
    """Run the official benchmark and runtime, including result verification."""
    host = config['architecture']['host']
    base, size = host_region
    host_range = AddrRange(base, size=size)
    system.mem_ranges = [host_range]
    # Only host code/stack/heap use local memory; the GPU BAR has its own path.
    system.host_mem = SimpleMemory(range=host_range, latency='10ns', conf_table_reported=True)
    system.host_mem.port = system.membus.mem_side_ports
    system.workload = SEWorkload.init_compatible(config['host_binary'])
    command = [config['host_binary'], '-n', str(config['benchmark']['elements']), '-k', config['kernel']]
    if config['benchmark']['name'] == 'sgemv':
        command += ['-m', str(config['benchmark']['elements'])]
    process = Process(
        pid=100, executable=config['host_binary'],
        cmd=command,
        env=['VORTEX_DRIVER=gem5-x86_64',
             'LD_LIBRARY_PATH=' + config['runtime_dir'] + ':' + os.environ['SS_PREFIX'] + '/lib'],
    )
    system.cpu = [TimingSimpleCPU(cpu_id=i) for i in range(host['num_cpus'])]
    system.multi_thread = True
    system.l2bus = L2XBar()
    for cpu in system.cpu:
        cpu.icache = L1(size=host['l1i'], is_read_only=True, writeback_clean=True)
        cpu.dcache = L1(size=host['l1d'])
        cpu.icache.cpu_side = cpu.icache_port
        cpu.dcache.cpu_side = cpu.dcache_port
        cpu.icache.mem_side = system.l2bus.cpu_side_ports
        cpu.dcache.mem_side = system.l2bus.cpu_side_ports
        cpu.createInterruptController()
        cpu.interrupts[0].pio = system.membus.mem_side_ports
        cpu.interrupts[0].int_requestor = system.membus.cpu_side_ports
        cpu.interrupts[0].int_responder = system.membus.mem_side_ports
        cpu.workload = process
        cpu.createThreads()
    system.l2cache = L2(size=host['l2'])
    system.l2cache.cpu_side = system.l2bus.mem_side_ports
    system.l2cache.mem_side = system.membus.cpu_side_ports
    return process


def connect_gpu(system, config, cp, bar):
    """gem5 ticks SimX; core and CP DMA complete only after timing responses."""
    system.vortex = VortexGPGPU(
        library=config['library'], kernel='',
        pio_addr=cp[0], pio_size=cp[1], pin_addr=bar[0], pin_size=bar[1],
        timing_memory=True, trace_enable=False, trace_addr_offset=bar[0],
        clk_domain=SrcClockDomain(
            clock=f"{config['architecture']['device_clock_mhz']}MHz",
            voltage_domain=system.clk_domain.voltage_domain,
        ),
    )
    system.vortex.pio = system.membus.mem_side_ports
    system.vortex.dma = system.membus.cpu_side_ports


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, help='Resolved run snapshot')
    options = parser.parse_args()
    config = json.loads(Path(options.config).read_text())
    architecture = config['architecture']
    output = Path(m5.options.outdir).resolve()
    m5.ticks.setGlobalFrequency('1fs')
    (output / 'hettrace').mkdir(exist_ok=True)
    os.environ.update(HETTRACE_DIR=str(output / 'hettrace'), HETTRACE_FILTER='all', HETTRACE_FORMAT='binary')
    regions = {r['name']: (int(r['base'], 16), int(r['size'], 16))
               for r in config['address_map']['regions']}

    system = System()
    system.clk_domain = SrcClockDomain(
        clock=f"{architecture['host']['clock_mhz']}MHz", voltage_domain=VoltageDomain(),
    )
    system.mem_mode = 'timing'
    system.membus = SystemXBar()
    system.system_port = system.membus.cpu_side_ports
    connect_memory(system, architecture, regions['vortex_bar'], output)
    process = connect_host(system, config, regions['host_heap'])
    connect_gpu(system, config, regions['vortex_cp'], regions['vortex_bar'])
    kernel = SystemC_Kernel(system=system)
    root = Root(full_system=False, systemc_kernel=kernel)
    m5.instantiate()
    cp_base, cp_size = regions['vortex_cp']
    process.map(cp_base, cp_base, (cp_size + 4095) // 4096 * 4096, cacheable=False)
    bar_base, bar_size = regions['vortex_bar']
    process.map(bar_base, bar_base, bar_size, cacheable=False)

    event = m5.simulate(architecture['max_ticks'])
    completion = {'cause': event.getCause(), 'code': event.getCode(), 'tick_fs': m5.curTick()}
    # This is computation completion only; run.py still requires data/link checks.
    passed = event.getCode() == 0 and 'exiting with last active thread context' in event.getCause()
    completion['passed'] = passed
    if passed:
        system.axi.finish()
    (output / 'completion.json').write_text(json.dumps(completion, indent=2) + '\n')
    print('EXIT:', event.getCause(), 'code', event.getCode(), 'tick', m5.curTick())
    if not passed:
        raise RuntimeError('Accelerator computation did not complete successfully: ' + str(completion))


if __name__ == '__m5_main__':
    main()
