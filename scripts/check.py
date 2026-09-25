#!/usr/bin/env python3
"""Availability and isolation check; computation is verified by run/test."""
from storage_dependency import STORAGE_ROOT, MEMSIM_BUILD, storage_version, require_build
import argparse,ctypes,json,os,re,subprocess
from pathlib import Path
from configure import ROOT,DEVICE,load,DEFAULT_CONFIG
require_build()
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--config',default=DEFAULT_CONFIG)
options=parser.parse_args()
load(config=options.config)
gem5=ROOT/"third_party/gem5/build/AXI/gem5.opt"
other='CoralNPU'
selected='VortexGPGPU'
subprocess.run([str(gem5),"--listener-mode=off","-d",str(ROOT/"build/check"),"-c",f"import m5.objects as o; assert hasattr(o, '{selected}'); assert not hasattr(o, '{other}'); assert not hasattr(o, 'AxiPacketTester'); assert not hasattr(o, 'UnifiedTimingMemory'); print('DEVICE_ISOLATION_PASS')"],check=True)
lib=ROOT/'build/vortex/sim/simx/libvortex-gem5.so'
ctypes.CDLL(str(MEMSIM_BUILD/"libstoragestacked_memsim.so"))
ctypes.CDLL(str(lib))
linked=subprocess.check_output(["ldd",str(lib)],text=True)
linked += subprocess.check_output(["ldd",str(gem5)],text=True)
assert "not found" not in linked
allowed = (ROOT, Path(os.environ['SS_DEPS_ROOT']).resolve(), Path('/lib'), Path('/lib64'), Path('/usr'))
for dependency in re.findall(r'(/[\w./+-]+)', linked):
    assert any(Path(dependency).is_relative_to(parent) for parent in allowed), dependency
assert "libsystemc" not in linked.lower()
print(json.dumps({"available":True,"device":DEVICE,"gem5_bytes":gem5.stat().st_size,"library_bytes":lib.stat().st_size,"scope":"availability and device isolation"},indent=2))
