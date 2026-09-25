#!/usr/bin/env python3
"""Generate protocol address constants from config/addrmap.json."""
import argparse,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
LEVELS={'post_llc':0,'pre_cache':1,'axi_master':2,'interconnect':3}
def camel(name): return ''.join(p.capitalize() for p in name.split('_'))
def render():
    m=json.loads((ROOT/'config/addrmap.json').read_text())
    regions={r['name']:(int(r['base'],16),int(r['size'],16),r['kind'],tuple(r['accessors'])) for r in m['regions']}
    sources={s['name']:(s['id'],s['level'],s['clock_mhz'],m['ticks_per_second']//(s['clock_mhz']*10**6)) for s in m['sources']}
    assert len({s[0] for s in sources.values()})==len(sources)
    previous_end=0
    for name,(base,size,kind,accessors) in sorted(regions.items(),key=lambda kv:kv[1][0]):
        assert size>0 and previous_end<=base and base+size<=1<<m['map_addr_bits'],name
        assert set(accessors)<=set(sources),name
        previous_end=base+size
    for name,(_,level,mhz,_) in sources.items():
        assert level in LEVELS and mhz>0 and m['ticks_per_second']%(mhz*10**6)==0,name
    dram=(int(m['dram_window']['base'],16),int(m['dram_window']['size'],16))
    windows=[(n,*((dram) if n=='dram_window' else regions[n][:2])) for n in m['trace_windows']['regions']]
    h=['// Generated from config/addrmap.json; do not edit.','#pragma once','#include <cstdint>','#include <cstddef>','namespace hettrace {',
       f'constexpr int kMapAddrBits = {m["map_addr_bits"]};',f'constexpr uint64_t kTicksPerSecond = {m["ticks_per_second"]}ull;', 'enum SrcId : uint16_t {']
    h += [f'    kSrc{camel(n)} = {s[0]},' for n,s in sources.items()]
    h += [f'    kSrcCount = {max(s[0] for s in sources.values())+1}', '};','enum TapLevel : uint8_t {']
    h += [f'    kLevel{camel(n)} = {v},' for n,v in LEVELS.items()]
    h += ['};']+[f'constexpr uint64_t kClockPeriodTicks_{n} = {s[3]}ull;' for n,s in sources.items()]
    for n,(base,size,*_) in regions.items():h += [f'constexpr uint64_t k{camel(n)}Base = {base}ull;',f'constexpr uint64_t k{camel(n)}Size = {size}ull;']
    h += [f'constexpr uint64_t kDramWindowBase = {dram[0]}ull;',f'constexpr uint64_t kDramWindowSize = {dram[1]}ull;',
          'struct Region { const char* name; uint64_t base, size; bool is_dram; };','constexpr Region kRegions[] = {']
    h += [f'    {{"{n}", {b}ull, {s}ull, {str(k=="dram").lower()}}},' for n,(b,s,k,_) in regions.items()]
    h += ['};','constexpr size_t kNumRegions = sizeof(kRegions)/sizeof(kRegions[0]);','inline const char* RegionOf(uint64_t addr) { for (const auto& r:kRegions) if (addr>=r.base && addr<r.base+r.size) return r.name; return nullptr; }',
          'inline bool IsDram(uint64_t addr) { return addr>=kDramWindowBase && addr<kDramWindowBase+kDramWindowSize; }',
          'struct TraceWindow { const char* name; uint64_t base, size; };','constexpr TraceWindow kTraceWindows[] = {']
    h += [f'    {{"{n}", {b}ull, {s}ull}},' for n,b,s in windows]
    h += ['};','constexpr size_t kNumTraceWindows = sizeof(kTraceWindows)/sizeof(kTraceWindows[0]);','inline bool IsTraced(uint64_t addr) { for (const auto& w:kTraceWindows) if (addr>=w.base && addr<w.base+w.size) return true; return false; }','} // namespace hettrace']
    py=['"""Generated from config/addrmap.json; do not edit."""',f'MAP_ADDR_BITS = {m["map_addr_bits"]}',f'TICKS_PER_SECOND = {m["ticks_per_second"]}',f'LEVELS = {LEVELS!r}',
        'LEVEL_NAMES = {v:k for k,v in LEVELS.items()}',f'SOURCES = {sources!r}','SRC_NAME_BY_ID = {s[0]:n for n,s in SOURCES.items()}',f'REGIONS = {regions!r}',f'DRAM_WINDOW = {dram!r}',f'TRACE_WINDOWS = {tuple(windows)!r}',f'HANDOFF_REGIONS = {tuple(n for n,r in regions.items() if len(r[3])>=2)!r}',
        'def region_of(addr):\n    return next((n for n,(b,s,_,_) in REGIONS.items() if b<=addr<b+s), None)',
        'def is_dram(addr):\n    return DRAM_WINDOW[0]<=addr<sum(DRAM_WINDOW)',
        'def is_traced(addr):\n    return any(b<=addr<b+s for _,b,s in TRACE_WINDOWS)',
        'def may_access(src_name,addr):\n    name=region_of(addr)\n    return name is not None and src_name in REGIONS[name][3]']
    return {'integration/include/hettrace/addrmap.h':'\n'.join(h)+'\n','integration/tools/hettrace/addrmap.py':'\n'.join(py)+'\n'}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');args=p.parse_args()
    for name,text in render().items():
        path=ROOT/name
        if args.check:
            if path.read_text()!=text:raise RuntimeError('Stale generated address map: '+name)
        elif not path.exists() or path.read_text()!=text:path.write_text(text)
    print('Address map is up to date')
