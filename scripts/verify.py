#!/usr/bin/env python3
"""Independent transaction, source, byte, compute and waveform acceptance."""
import csv
import json
import math
from pathlib import Path
import re
import sys
from hettrace import addrmap
from hettrace.reader import CHAN_AR, CHAN_AW, CHAN_B, CHAN_R, CHAN_W, read_records, read_header
from hettrace.validate import validate_dir, format_report

def read(p):
    return json.loads(p.read_text())

def verify(root):
    c = read(root / 'resolved.json')
    dev = c['device']
    a = c['architecture']
    b = c['benchmark']
    completion = read(root / 'completion.json')
    assert completion['passed'] and completion['code'] == 0
    memory_config = read(root / 'memsim_config.json')
    assert memory_config['standard'] == a['memory']['standard']
    assert memory_config['channels'] == a['memory']['channels']
    assert memory_config['timing_scale'] == a['memory']['scale']
    assert memory_config['queue_depth'] == a['memory']['queue']
    actual_system = read(root / 'config.json')['systemc_kernel']['system']
    assert c['time_unit'] == '1 fs' and c['address_map']['ticks_per_second'] == 10 ** 15
    assert actual_system['mem_mode'] == 'timing'
    assert len(actual_system['cpu']) == a['host']['num_cpus']
    assert actual_system['clk_domain']['clock'] == [10 ** 9 // a['host']['clock_mhz']]
    gpu = actual_system['vortex']
    assert gpu['timing_memory'] is True and gpu['kernel'] == ''
    assert gpu['library'] == c['library']
    assert gpu['clk_domain']['clock'] == [10 ** 9 // a['device_clock_mhz']]
    regions = {r['name']: (int(r['base'], 16), int(r['size'], 16))
               for r in c['address_map']['regions']}
    base, size = regions['vortex_bar']
    assert (gpu['pin_addr'], gpu['pin_size']) == (base, size)
    assert (gpu['pio_addr'], gpu['pio_size']) == regions['vortex_cp']
    assert actual_system['bridge']['addr_ranges'] == [f'{base}:{base + size}']
    host_base, host_size = regions['host_heap']
    assert actual_system['host_mem']['range'] == f'{host_base}:{host_base + host_size}'
    actual_axi = actual_system['axi']
    assert (actual_axi['base'], actual_axi['size']) == (base, size)
    assert actual_axi['backend'] == 'aou' and actual_axi['memory_backend'] == 'memsim'
    assert actual_axi['period'] == a['axi']['period_ns'] * 1000000
    assert actual_axi['planes'] == a['axi']['planes']
    assert actual_axi['outstanding'] == a['axi']['outstanding']
    assert actual_axi['replay'] == a['axi']['replay']
    assert actual_axi['stalls'] == a['axi']['stalls']
    assert actual_axi['memsim_slots'] == a['memory']['slots']
    assert actual_axi['memsim_response_hold'] == a['memory']['response_hold']
    checks = {k: read(root / (k + '.json')) for k in ('check_summary', 'aou_check_summary', 'memsim_check', 'memsim_core')}
    assert all((v['passed'] for v in checks.values()))
    wave = read(root / 'wave_audit/summary.json')
    assert len(wave) == 1 and all((v['passed'] for v in wave.values()))
    expected = {dev, 'host'}
    for name in expected:
        mhz = a['device_clock_mhz'] if name == dev else a['host']['clock_mhz']
        header = read_header(str(root / 'hettrace' / (name + '.hettrace')))
        assert header.ticks_per_second == 10 ** 15
        assert header.clock_period_ticks == 10 ** 9 // mhz
        sid, level, _, _ = addrmap.SOURCES[name]
        addrmap.SOURCES[name] = (sid, level, mhz, addrmap.TICKS_PER_SECOND // (mhz * 10 ** 6))
    issues, summaries = validate_dir(str(root / 'hettrace'), require_heterogeneous=dev == 'vortex', ticks_per_second=10 ** 15)
    (root / 'hettrace/validation.txt').write_text(format_report(issues, summaries) + '\n')
    assert not [i for i in issues if i.level == 'ERROR']
    assert {s.name for s in summaries} == expected and all((s.transactions > 0 for s in summaries))
    with (root / 'transactions.csv').open() as f:
        tx = list(csv.DictReader(f))
    records = {s: list(read_records(str(root / 'hettrace' / (s + '.hettrace')))) for s in expected}
    # Both the monitor and AXI bridge split packets into legal bursts; e.g.
    # a 24-byte CP transfer becomes separate 16-byte and 8-byte bursts.
    assert sum(s.transactions for s in summaries) == sum(int(t['segments']) for t in tx), 'Trace burst count differs from AXI packet segments'
    for chan, cmd in ((CHAN_R, 'R'), (CHAN_W, 'W')):
        assert sum((r.size for rs in records.values() for r in rs if r.chan == chan)) == sum((int(t['bytes']) for t in tx if t['command'] == cmd))
    sources = {}
    for source, rs in records.items():
        starts = {r.txn: r.tick for r in rs if r.chan in (CHAN_AW, CHAN_AR)}
        ends = {}
        for r in rs:
            if r.chan in (CHAN_R, CHAN_B):
                ends[r.txn] = max(r.tick, ends.get(r.txn, 0))
        assert starts.keys() == ends.keys()
        latencies = [ends[k] - starts[k] for k in starts]
        assert min(latencies) > 0 and max((r.tick for r in rs)) <= completion['tick_fs']
        sources[source] = {'transactions': len(starts), 'bytes': sum((r.size for r in rs if r.chan in (CHAN_R, CHAN_W))), 'roundtrip_mean_ns': sum(latencies) / len(latencies) / 1000000.0}
    log = (root / 'run.log').read_text()
    devices = {}
    assert 'PASSED!' in log
    operator_check = None
    if b['name'] in ('sgemv', 'softmax', 'relu'):
        reports = re.findall(r'^LLM_CHECK (\{[^\n]+\})$', log, re.MULTILINE)
        assert len(reports) == 1, 'Expected one independent operator result check'
        operator_check = json.loads(reports[0])
        assert operator_check['passed'] is True
        assert operator_check['operator'] == b['name']
        assert operator_check['elements'] == b['elements']
        expected_outputs = b['elements'] ** 2 if b['name'] == 'softmax' else b['elements']
        assert operator_check['checked_outputs'] == expected_outputs
        assert all(math.isfinite(v) for v in operator_check.values() if type(v) in (int, float))
        if b['name'] == 'sgemv':
            assert operator_check['rows'] == operator_check['columns'] == b['elements']
        if b['name'] == 'softmax':
            assert operator_check['max_abs_error'] <= 2.2e-5
            assert operator_check['row_sum_max_error'] <= 2e-5
        if b['name'] == 'relu':
            counts = [operator_check[k] for k in ('negative_inputs', 'zero_inputs', 'positive_inputs')]
            assert sum(counts) == b['elements']
            if b['elements'] >= 8:
                assert min(counts) > 0
    build = re.search(r'vortex-gem5 \(XLEN=(\d+), threads=(\d+), warps=(\d+), cores=(\d+), clusters=(\d+)\)', log)
    assert build, 'No SimX library build configuration'
    xlen, threads, warps, cores, clusters = map(int, build.groups())
    assert xlen == 32 and clusters == 1
    assert {'cores': cores, 'warps': warps, 'threads': threads} == a['simx'], 'Loaded SimX differs from requested GPU configuration'
    m = re.search('VortexGPGPU timing summary: core_read=(\\d+) core_write=(\\d+) cp_read=(\\d+) cp_write=(\\d+) completed=(\\d+).* cp_cycles=(\\d+) vortex_cycles=(\\d+)', log)
    assert m, 'No SimX completion statistics'
    devices = dict(zip(('core_read', 'core_write', 'cp_read', 'cp_write', 'completed', 'cp_cycles', 'cycles'), map(int, m.groups())))
    assert all((devices[k] > 0 for k in ('core_read', 'core_write', 'cp_read', 'cp_write')))
    assert devices['completed'] == sum((devices[k] for k in ('core_read', 'core_write', 'cp_read', 'cp_write')))
    result = {'passed': True, 'device': dev, 'benchmark': b, 'axi_data_bits': read(root / 'protocol_summary.json')['axi_data_bits'], 'completion': completion, 'sources': sources, 'devices': devices, 'checks': checks, 'wave': wave, 'scope': 'accelerator -> native AXI256 -> AXI2Flit -> UCIe -> online mem_sim -> returned data'}
    assert result['axi_data_bits'] == 256
    if operator_check is not None:
        result['operator_check'] = operator_check
    (root / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'passed': True, 'device': dev, 'sources': sources, 'devices': devices}, indent=2))
if __name__ == '__main__':
    verify(Path(sys.argv[1]))
