#!/usr/bin/env python3
"""Run one real accelerator benchmark and require end-to-end acceptance."""
from storage_dependency import STORAGE_ROOT, MEMSIM_BUILD, storage_version, require_build
import argparse
import datetime
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
from configure import ROOT, DEVICE, load, build_inputs, run_arguments, apply_overrides, address_map, config_path

def dump(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')

def main():
    require_build()
    p = argparse.ArgumentParser()
    run_arguments(p)
    p.add_argument('--output', type=Path)
    o = p.parse_args()
    a, b = load(o.benchmark, o.config)
    apply_overrides(a, o.scale, o.replay)
    output = o.output or ROOT / 'results' / datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    dump(output / 'summary.json', {'passed': False, 'stage': 'preflight', 'device': DEVICE})
    lock = (ROOT / 'build/build.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_SH)
    env = dict(os.environ)
    env['PYTHONPATH'] = str(ROOT / 'integration/tools') + ':' + str(STORAGE_ROOT / 'scripts')
    extra = [MEMSIM_BUILD, Path(env['SS_PREFIX']) / 'lib']
    extra += [ROOT / 'third_party/vortex/third_party/ramulator']
    env['LD_LIBRARY_PATH'] = ':'.join(map(str, extra))

    def run(command, log):
        with (output / log).open('a') as stream:
            subprocess.run(list(map(str, command)), cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT, check=True)
    stage = 'build benchmark'
    try:
        build_args = ['--config', o.config]
        if o.benchmark:
            build_args += ['--benchmark', o.benchmark]
        built = ROOT / 'build/device-config.json'
        if not built.exists() or json.loads(built.read_text()) != build_inputs(a):
            fcntl.flock(lock, fcntl.LOCK_UN)
            fcntl.flock(lock, fcntl.LOCK_EX)
            if not built.exists() or json.loads(built.read_text()) != build_inputs(a):
                run(['bash', ROOT / 'scripts/build_device.sh', *build_args], 'benchmark-build.log')
            fcntl.flock(lock, fcntl.LOCK_SH)
        gem5 = ROOT / 'third_party/gem5/build/AXI/gem5.opt'
        c = {'device': DEVICE, 'architecture': a, 'benchmark': b, 'address_map': address_map(a),
             'simx_defaults': build_inputs(a)['simx_defaults'],
             'config_file': str(config_path(o.config).resolve()), 'time_unit': '1 fs'}
        vx = ROOT / 'build/vortex'
        c.update(library=str(vx / 'sim/simx/libvortex-gem5.so'), host_binary=str(vx / 'tests/regression' / b['name'] / b['name']), kernel=str(vx / 'tests/regression' / b['name'] / 'kernel.vxbin'), runtime_dir=str(vx / 'sw/runtime'))
        files = [gem5, MEMSIM_BUILD / 'libstoragestacked_memsim.so', Path(c['library']), Path(c['kernel'])]
        if 'host_binary' in c:
            files.append(Path(c['host_binary']))
        for file in files:
            if not file.is_file():
                raise FileNotFoundError(str(file) + '; run ./run.sh build')
        dump(output / 'resolved.json', c)
        manifest = {'storage': storage_version(), 'sources': json.loads((ROOT / 'config/sources.json').read_text()), 'files': [{'name': str(x.relative_to(ROOT)), 'bytes': x.stat().st_size} for x in files], 'python': sys.version, 'compiler': subprocess.check_output([env['AXI_CXX'], '--version'], text=True).splitlines()[0]}
        dump(output / 'environment.json', manifest)
        stage = 'simulate'
        dump(output / 'summary.json', {'passed': False, 'stage': stage, 'device': DEVICE, 'benchmark': b})
        run([gem5, '--listener-mode=off', '-d', output, ROOT / 'scripts/simulate.py', '--config', output / 'resolved.json'], 'run.log')
        stage = 'verify data and link'
        dump(output / 'summary.json', {'passed': False, 'stage': stage, 'device': DEVICE, 'benchmark': b})
        run([sys.executable, ROOT / 'scripts/validate.py', output], 'validation-run.log')
        print('PASS: ' + str(output / 'summary.json'))
    except Exception as error:
        dump(output / 'summary.json', {'passed': False, 'stage': stage, 'device': DEVICE, 'error': str(error)})
        print(f'FAIL ({stage}): {output}', file=sys.stderr)
        raise
if __name__ == '__main__':
    main()
