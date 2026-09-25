#!/usr/bin/env python3
"""Resumable acceptance; runs independent cases concurrently under build locks."""
from storage_dependency import STORAGE_ROOT, MEMSIM_BUILD, storage_version
import argparse, datetime, json, os, re, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from configure import ROOT, DEVICE, load, DEFAULT_CONFIG, address_map
p = argparse.ArgumentParser()
p.add_argument('--config', default=DEFAULT_CONFIG)
p.add_argument('--output', type=Path)
p.add_argument('--resume', action='store_true', help='Reuse passed cases with matching configuration, source versions and binary sizes')
a = p.parse_args()
base_arch, _ = load(config=a.config)
slow_scale = 4 * base_arch['memory']['scale']
if slow_scale > 1024:
    p.error('test compares a 4x slower memory; use memory.scale <= 256 for acceptance')
out = (a.output or ROOT / 'results' / ('acceptance-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))).resolve()
out.mkdir(parents=True, exist_ok=a.resume)
(out / 'summary.json').write_text('{"passed":false,"stage":"running"}\n')

def read(path):
    return json.loads(path.read_text())

def invoke(cmd, filename):
    with (out / filename).open('w') as stream:
        subprocess.run(list(map(str, cmd)), cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, check=True)

def reusable(name, flags):
    directory = out / name
    if not a.resume or not (directory / 'summary.json').exists():
        return False
    if not read(directory / 'summary.json')['passed']:
        return False
    bench = flags[flags.index('--benchmark') + 1] if '--benchmark' in flags else None
    arch, b = load(bench, a.config)
    if '--scale' in flags:
        arch['memory']['scale'] = int(flags[flags.index('--scale') + 1])
    if '--replay' in flags:
        arch['axi']['replay'] = True
    saved = read(directory / 'resolved.json')
    env = read(directory / 'environment.json')
    return saved['architecture'] == arch and saved['benchmark'] == b and saved.get('address_map') == address_map(arch) and saved.get('simx_defaults') == (ROOT / 'config/simx.toml').read_text() and (env['sources'] == read(ROOT / 'config/sources.json')) and env.get('storage') == storage_version() and all(((ROOT / f['name']).is_file() and (ROOT / f['name']).stat().st_size == f['bytes'] for f in env['files']))

def run_case(case):
    name, flags = case
    if reusable(name, flags):
        print('Reuse verified ' + DEVICE + ' ' + name, flush=True)
        return (name, read(out / name / 'summary.json'), True)
    if (out / name).exists():
        raise RuntimeError('Existing case is incomplete or no longer matches; use a new --output directory: ' + str(out / name))
    print('Running ' + DEVICE + ' ' + name, flush=True)
    invoke([sys.executable, ROOT / 'scripts/run.py', '--config', a.config, '--output', out / name, *flags], name + '.log')
    result = read(out / name / 'summary.json')
    assert result['passed']
    return (name, result, False)
try:
    invoke([sys.executable, ROOT / 'scripts/check.py', '--config', a.config], 'environment-check.log')
    invoke([os.environ['AXI_CXX'], '-O3', '-std=c++17', ROOT / 'scripts/check_softmax_exp.cpp',
            '-o', out / 'check-softmax-exp'], 'softmax-exp-build.log')
    invoke([out / 'check-softmax-exp'], 'softmax-exp-check.json')
    assert read(out / 'softmax-exp-check.json')['passed']
    plan = json.loads(subprocess.check_output(['ctest', '--test-dir', str(MEMSIM_BUILD), '--show-only=json-v1'], text=True))
    count = len(plan['tests'])
    native = out / 'native-tests.log'
    if not (a.resume and native.exists() and re.search(f'100% tests passed, 0 tests failed out of {count}\\b', native.read_text())):
        invoke(['ctest', '--test-dir', MEMSIM_BUILD, '--output-on-failure'], 'native-tests.log')
    if not (a.resume and (out / 'api/api_check.json').exists() and read(out / 'api/api_check.json')['passed']):
        invoke([sys.executable, STORAGE_ROOT / 'mem_sim/integration/check_online.py', MEMSIM_BUILD / 'libstoragestacked_memsim.so', out / 'api'], 'api.log')
    variant = 'vecadd64'
    cases = {}
    reused = []
    group = [('default', []), ('slow', ['--scale', str(slow_scale)]), ('replay', ['--replay'])]
    group.append(('alternate', ['--benchmark', 'config/benchmarks/' + variant + '.json']))
    for name in ('sgemm', 'sgemv', 'softmax', 'relu'):
        group.append((name, ['--benchmark', 'config/benchmarks/' + name + '.json']))
    with ThreadPoolExecutor(max_workers=4) as pool:
        for name, result, was_reused in pool.map(run_case, group):
            cases[name] = result
            if was_reused:
                reused.append(name)
    fast, slow = (cases['default'], cases['slow'])
    assert read(out / 'slow/memsim_config.json')['period_fs'] == 4 * read(out / 'default/memsim_config.json')['period_fs']
    assert slow['devices']['cycles'] > fast['devices']['cycles']
    assert slow['completion']['tick_fs'] > fast['completion']['tick_fs']
    assert slow['sources'][DEVICE]['roundtrip_mean_ns'] > fast['sources'][DEVICE]['roundtrip_mean_ns']
    assert slow['sources'][DEVICE]['transactions'] == fast['sources'][DEVICE]['transactions']
    result = {'passed': True, 'device': DEVICE, 'native_tests_passed': count, 'api_check': read(out / 'api/api_check.json'), 'cases': {k: {'passed': v['passed'], 'sources': v['sources'], 'devices': v['devices']} for k, v in cases.items()}, 'reused_verified_cases': reused, 'memory_feedback': {'passed': True, 'scale': 4, 'cycles': [fast['devices']['cycles'], slow['devices']['cycles']]}}
    assert result['api_check']['passed']
    result['llm_operators'] = {name: cases[name]['operator_check'] for name in ('sgemv', 'softmax', 'relu')}
    result['softmax_exp_check'] = read(out / 'softmax-exp-check.json')
    (out / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
    print('PASS: ' + str(out / 'summary.json'))
except Exception as error:
    (out / 'summary.json').write_text(json.dumps({'passed': False, 'error': str(error)}, indent=2) + '\n')
    raise
