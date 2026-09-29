"""Resolve configured paths relative to the checkout."""
import json
import os
import sys
if sys.flags.optimize: raise RuntimeError("Run without Python optimization; validation requires assertions")
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
RUNTIME = ROOT / 'third_party/gem5/runtime'
CACHE = ROOT / 'third_party/.cache'
BUILD = CACHE / 'build'
SETTINGS = json.loads((RUNTIME / 'paths.json').read_text())
if Path(SETTINGS['storage']).is_absolute(): raise ValueError('storage must be a relative path')
STORAGE_ROOT = (ROOT / SETTINGS['storage']).resolve()
MEMSIM_BUILD = BUILD / 'memsim'
VORTEX_BUILD = BUILD / 'vortex'
GEM5 = ROOT / 'third_party/gem5/build/AXI/gem5.opt'
def relative(path, base=ROOT): return os.path.relpath(path, base)
def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False)+'\n')
