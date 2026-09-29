"""Build the reusable platform for one validated project configuration."""
import argparse,json,os,shutil,subprocess
from pathlib import Path
from paths import ROOT,CACHE,BUILD,RUNTIME,GEM5,MEMSIM_BUILD,STORAGE_ROOT,SETTINGS,dump
from configure import load_config,build_inputs
from storage_dependency import record_build

def run(args,cwd=ROOT):subprocess.run(list(map(str,args)),cwd=cwd,check=True)
def build(config,force=False,ready=False):
    config=Path(config).resolve();c=load_config(config)
    selected={'device':build_inputs(c),'ucie':c['ucie']}
    marker=BUILD/'platform.json';previous=json.loads(marker.read_text()) if marker.exists() else {}
    outputs=[GEM5,BUILD/'vortex/sw/runtime/libvortex-gem5-x86_64.so',BUILD/'vortex/sim/simx/libvortex-gem5.so']
    valid=previous==selected and all(p.exists() for p in outputs)
    if ready:return valid
    if not force and valid:return
    BUILD.mkdir(parents=True,exist_ok=True)
    dump(CACHE/'link.json',c['ucie']);os.environ['STORAGE_LINK_CONFIG']=str(CACHE/'link.json')
    run(['cmake','-S',STORAGE_ROOT/'mem_sim','-B',MEMSIM_BUILD,'-G','Ninja','-DCMAKE_BUILD_TYPE=Release','-DCMAKE_CXX_COMPILER='+os.environ['AXI_CXX']])
    run(['cmake','--build',MEMSIM_BUILD,'-j',SETTINGS['jobs']])
    home=ROOT/'third_party/gem5';scons=os.environ['GEM5_SCONS']
    args=['CXX='+os.environ['AXI_CXX'],'CC='+os.environ['AXI_CC'],'PYTHON_CONFIG='+os.environ['PYTHON_CONFIG'],'EXTRAS='+str(ROOT/'integration')+':'+str(STORAGE_ROOT/'storage_axi')]
    if not (home/'build/AXI/gem5.build/config').exists():run([scons,'defconfig','build/AXI','build_opts/X86',*args],home)
    run([scons,'setconfig','build/AXI','RUBY=n','USE_KVM=y','USE_SYSTEMC=y',*args],home)
    run([scons,'build/AXI/gem5.opt',*args,'-j',SETTINGS['jobs']],home)
    if force or previous.get('device')!=selected['device'] or not all(p.exists() for p in outputs[1:]):
        ram=ROOT/'third_party/vortex/third_party/ramulator/build'
        if (ram/'CMakeCache.txt').exists() and str(ROOT/'third_party/.cache/tools') not in (ram/'CMakeCache.txt').read_text():shutil.rmtree(ram)
        run(['bash',RUNTIME/'build_device.sh',config])
    record_build();dump(marker,selected)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--force',action='store_true');p.add_argument('--ready',action='store_true');o=p.parse_args()
    if o.ready:raise SystemExit(0 if build(o.config,ready=True) else 1)
    build(o.config,o.force)
