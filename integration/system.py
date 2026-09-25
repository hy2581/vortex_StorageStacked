"""Connect a gem5/Vortex platform to the independent AXI storage service."""
import argparse
import json
from pathlib import Path
import m5
from m5.objects import (AddrRange, Gem5ToTlmBridge64, HetAxiMonitor, Root,
                        StorageBridge, SystemC_Kernel)
from soc import create


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',required=True)
    config=json.loads(Path(parser.parse_args().config).read_text())
    output=Path(m5.options.outdir).resolve()
    system,process,regions=create(config,output)
    a=config['architecture'];axi=a['axi'];memory=a['memory']
    base,size=regions['vortex_bar']
    system.axi=StorageBridge(
        base=base,size=size,period=f"{axi['period_ns']}ns",
        outstanding=axi['outstanding'],planes=axi['planes'],
        stalls=axi['stalls'],replay=axi['replay'],
        memsim_standard=memory['standard'],memsim_channels=memory['channels'],
        memsim_scale=memory['scale'],memsim_queue=memory['queue'],
        memsim_slots=memory['slots'],memsim_response_hold=memory['response_hold'],
        trace_dir=str(output))
    system.bridge=Gem5ToTlmBridge64(addr_ranges=[AddrRange(base,size=size)])
    system.bridge.tlm=system.axi.tlm
    system.monitor=HetAxiMonitor(
        trace_host=True,trace_device=True,
        host_clock_period=10**9//a['host']['clock_mhz'],
        device_clock_period=10**9//a['device_clock_mhz'])
    system.monitor.mem_side_port=system.bridge.gem5
    system.monitor.cpu_side_port=system.membus.mem_side_ports
    root=Root(full_system=False,systemc_kernel=SystemC_Kernel(system=system))
    m5.instantiate()
    for name in ('vortex_cp','vortex_bar'):
        address,length=regions[name]
        process.map(address,address,(length+4095)//4096*4096,cacheable=False)
    event=m5.simulate(a['max_ticks'])
    passed=event.getCode()==0 and 'exiting with last active thread context' in event.getCause()
    completion={'cause':event.getCause(),'code':event.getCode(),'tick_fs':m5.curTick(),'passed':passed}
    if passed:system.axi.finish()
    (output/'completion.json').write_text(json.dumps(completion,indent=2)+'\n')
    print('EXIT:',event.getCause(),'code',event.getCode(),'tick',m5.curTick())
    if not passed:raise RuntimeError('Device computation did not complete: '+str(completion))


if __name__=='__m5_main__':main()
