#!/usr/bin/env python3
"""Resolve the single run configuration and validate it before building/running."""
import argparse
import json
import re
import tomllib
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
DEVICE = 'vortex'
DEFAULT_CONFIG = 'config/run.toml'
TICKS_PER_SECOND = 10 ** 15
BENCHMARKS = ('vecadd', 'sgemm', 'sgemv', 'softmax', 'relu')

def config_path(path):
    p = Path(path)
    return p if p.is_absolute() else ROOT / p

def read(path):
    return json.loads(config_path(path).read_text())

def positive(value, name, upper=1000000):
    if type(value) is not int or not 0 < value <= upper:
        raise ValueError(f'{name} must be an integer in [1, {upper}]')

def keys(obj, expected, name):
    if not isinstance(obj, dict):
        raise ValueError(f'{name} must be a table/object')
    if set(obj) != set(expected.split()):
        raise ValueError(f"{name}: expected keys {expected}; got {', '.join(obj)}")

def address_map(architecture=None):
    mapping = read('config/addrmap.json')
    if mapping['ticks_per_second'] != TICKS_PER_SECOND:
        raise ValueError('addrmap must use 1 fs ticks (10^15 ticks per second)')
    required = {'vortex_cp': (536870912, 512), 'host_heap': (2147483648, 268435456), 'vortex_bar': (4294967296, 4294967296)}
    actual = {v['name']: (int(v['base'], 16), int(v['size'], 16)) for v in mapping['regions']}
    if actual != required:
        raise ValueError('addrmap differs from the compiled driver/kernel ABI; update source and rebuild together')
    if architecture is not None:
        clocks = {'host': architecture['host']['clock_mhz'], 'vortex': architecture['device_clock_mhz']}
        for source in mapping['sources']:
            source['clock_mhz'] = clocks[source['name']]
    return mapping

def load(benchmark=None, config=DEFAULT_CONFIG):
    with config_path(config).open('rb') as stream:
        settings = tomllib.load(stream)
    keys(settings, 'gpu benchmark memory axi host simulation', 'run config')
    keys(settings['gpu'], 'clock_mhz cores warps threads', 'gpu')
    keys(settings['simulation'], 'max_ticks', 'simulation')
    keys(settings['benchmark'], 'name elements', 'benchmark')
    a = {
        'device_clock_mhz': settings['gpu']['clock_mhz'],
        'simx': {k: settings['gpu'][k] for k in ('cores', 'warps', 'threads')},
        'axi': settings['axi'],
        'memory': settings['memory'],
        'host': settings['host'],
        'max_ticks': settings['simulation']['max_ticks'],
    }
    b = read(benchmark) if benchmark else settings['benchmark']
    positive(a['device_clock_mhz'], 'gpu.clock_mhz', 10000)
    if 10 ** 9 % a['device_clock_mhz']:
        raise ValueError('gpu.clock_mhz must produce an integral fs period')
    positive(a['max_ticks'], 'simulation.max_ticks', 10 ** 17)
    keys(a['axi'], 'period_ns outstanding planes stalls replay', 'axi')
    for k in ('period_ns', 'outstanding', 'planes'):
        positive(a['axi'][k], 'axi.' + k, {'period_ns': 1000, 'outstanding': 128, 'planes': 4}[k])
    for k in ('stalls', 'replay'):
        if type(a['axi'][k]) is not bool:
            raise ValueError(k + ' must be true/false')
    keys(a['memory'], 'standard channels scale queue slots response_hold', 'memory')
    if a['memory']['standard'] not in ('hbm3', 'hbm4', 'lpddr5', 'lpddr6'):
        raise ValueError('unsupported memory standard')
    for k in ('channels', 'scale', 'queue', 'slots'):
        positive(a['memory'][k], 'memory.' + k, 1024)
    if type(a['memory']['response_hold']) is not int or a['memory']['response_hold'] < 0:
        raise ValueError('response_hold must be a nonnegative integer')
    keys(a['host'], 'clock_mhz num_cpus l1i l1d l2', 'host')
    positive(a['host']['clock_mhz'], 'host.clock_mhz', 10000)
    if 10 ** 9 % a['host']['clock_mhz']:
        raise ValueError('host clock must have an integral fs period')
    positive(a['host']['num_cpus'], 'host.num_cpus', 64)
    if a['host']['num_cpus'] < 2:
        raise ValueError('Vortex runtime requires at least two host CPU contexts')
    for k in ('l1i', 'l1d', 'l2'):
        size = a['host'][k]
        if not isinstance(size, str) or not re.fullmatch(r'[1-9][0-9]*(KiB|MiB)', size):
            raise ValueError('host.' + k + ' must be a positive size such as 32KiB or 1MiB')
        amount = int(size[:-3]) * (1024 if size.endswith('KiB') else 1024 ** 2)
        associativity = 16 if k == 'l2' else 8
        sets, remainder = divmod(amount, associativity * 64)
        if remainder or sets == 0 or sets & (sets - 1):
            raise ValueError('host.' + k + ' must have a power-of-two number of cache sets')
    keys(a['simx'], 'cores warps threads', 'simx')
    for k, v in a['simx'].items():
        positive(v, 'gpu.' + k, 32)
        if v & v - 1:
            raise ValueError('gpu.' + k + ' must be a power of two')
    keys(b, 'name elements', 'benchmark')
    if b['name'] not in BENCHMARKS:
        raise ValueError('benchmark.name must be one of: ' + ', '.join(BENCHMARKS))
    positive(b['elements'], 'elements', 16384)
    if b['name'] == 'sgemv' and b['elements'] % 4:
        raise ValueError('sgemv elements must be a multiple of 4 (four-column vector loads)')
    address_map()
    return (a, b)

def build_inputs(a):
    return {'device': DEVICE, 'simx': a['simx'], 'benchmarks': list(BENCHMARKS),
            'simx_defaults': (ROOT / 'config/simx.toml').read_text()}

def apply_overrides(a, scale=None, replay=False):
    if scale is not None:
        positive(scale, 'scale', 1024)
        a['memory']['scale'] = scale
    if replay:
        a['axi']['replay'] = True

def run_arguments(parser):
    parser.add_argument('--config', default=DEFAULT_CONFIG, help='Run TOML, relative to the project root')
    parser.add_argument('--benchmark', help='Override only the benchmark with a JSON preset')
    parser.add_argument('--scale', type=int, help='Override the memory clock-period multiplier')
    parser.add_argument('--replay', action='store_true', help='Inject Flit CRC errors and exercise replay')

def main():
    p = argparse.ArgumentParser(description=__doc__)
    run_arguments(p)
    p.add_argument('--simx-flags', action='store_true')
    p.add_argument('--benchmark-name', action='store_true')
    p.add_argument('--benchmark-names', action='store_true')
    p.add_argument('--record-build', action='store_true')
    p.add_argument('--show', action='store_true')
    p.add_argument('--json', action='store_true', help='Print the full configuration as JSON with --show')
    o = p.parse_args()
    a, b = load(o.benchmark, o.config)
    apply_overrides(a, o.scale, o.replay)
    if o.simx_flags:
        print(' '.join((f'-DVX_CFG_NUM_{k.upper()}={v}' for k, v in a['simx'].items())))
    if o.benchmark_name:
        print(b['name'])
    if o.benchmark_names:
        print(' '.join(BENCHMARKS))
    if o.record_build:
        (ROOT / 'build/device-config.json').write_text(json.dumps(build_inputs(a), indent=2) + '\n')
    if o.show:
        built = ROOT / 'build/device-config.json'
        resolved = {
            'config': str(config_path(o.config).resolve()),
            'time_unit': '1 fs',
            'path': 'SimX -> gem5 timing -> TLM -> AXI256 -> AXI2Flit -> UCIe -> mem_sim',
            'architecture': a, 'benchmark': b,
            'device_rebuild_required': not built.exists() or read(built) != build_inputs(a),
            'address_map': address_map(a),
        }
        if o.json:
            print(json.dumps(resolved, indent=2))
        else:
            gpu, memory, axi, host = a['simx'], a['memory'], a['axi'], a['host']
            print(f"配置：{resolved['config']}")
            shape = '向量元素数' if b['name'] in ('vecadd', 'relu') else '方阵边长'
            print(f"算例：{b['name']}，{shape} {b['elements']}")
            print(f"GPU：{gpu['cores']} 核 × {gpu['warps']} warp/核 × {gpu['threads']} 线程/warp，{a['device_clock_mhz']} MHz")
            print(f"内存：{memory['standard']}，{memory['channels']} 通道，周期倍率 {memory['scale']}")
            print(f"内存队列：深度 {memory['queue']}，在途 burst {memory['slots']}，额外响应等待 {memory['response_hold']} tick")
            print(f"AXI：256 bit，周期 {axi['period_ns']} ns，在途 TLM 请求 {axi['outstanding']}，资源平面 {axi['planes']}")
            print(f"链路测试：反压 {'开启' if axi['stalls'] else '关闭'}，CRC 错误注入/重放 {'开启' if axi['replay'] else '关闭'}")
            print(f"主机：{host['num_cpus']} 个 CPU 上下文，{host['clock_mhz']} MHz，L1I/L1D/L2 = {host['l1i']}/{host['l1d']}/{host['l2']}")
            print(f"时间：1 tick = 1 fs，watchdog {a['max_ticks']} tick")
            print(f"访存：{resolved['path']}")
            print(f"GPU BAR：0x100000000 起，4 GiB；主机程序/栈使用独立本地主存")
            print(f"设备配置需要重编译：{'是（run 自动处理）' if resolved['device_rebuild_required'] else '否'}")
            print('完整 JSON：./run.sh config [相同参数] --json')
if __name__ == '__main__':
    main()
