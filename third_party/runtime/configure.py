"""Validate the complete user JSON and produce build/runtime parameters."""
import json
import math
import re
from pathlib import Path
from paths import ROOT,RUNTIME,relative
DEVICE='vortex'

def keys(obj, expected, label):
    if not isinstance(obj,dict) or set(obj)!=set(expected.split()):raise ValueError(label+': expected fields '+expected)
def integer(value,low,high,label):
    if type(value) is not int or not low<=value<=high:raise ValueError(f'{label} must be an integer in [{low}, {high}]')
def clock(value,label):
    integer(value,1,10000,label)
    if 10**9%value:raise ValueError(label+' must yield an integer fs period')
def validate(c):
    keys(c,'program gpu host axi ucie memsim simulation','project')
    keys(c['gpu'],'clock_mhz cores warps threads l1i_bytes l1d_bytes l2_enabled l2_bytes','gpu')
    clock(c['gpu']['clock_mhz'],'gpu.clock_mhz')
    for k in ('cores','warps','threads'):
        v=c['gpu'][k];integer(v,1,32,'gpu.'+k)
        if v&(v-1):raise ValueError('gpu.'+k+' must be a power of two')
    for k in ('l1i_bytes','l1d_bytes','l2_bytes'):
        v=c['gpu'][k];integer(v,4096,16*1024*1024,'gpu.'+k)
        if v&(v-1):raise ValueError('cache size must be a power of two')
    if type(c['gpu']['l2_enabled']) is not bool:raise ValueError('l2_enabled must be boolean')
    h=c['host'];keys(h,'clock_mhz num_cpus l1i l1d l2 tlb_entries','host')
    clock(h['clock_mhz'],'host.clock_mhz');integer(h['num_cpus'],2,64,'host.num_cpus');integer(h['tlb_entries'],1,4096,'host.tlb_entries')
    for k in ('l1i','l1d','l2'):
        s=h[k]
        if not isinstance(s,str) or not re.fullmatch(r'[1-9][0-9]*(KiB|MiB)',s):raise ValueError('invalid host cache size')
        amount=int(s[:-3])*(1024 if s.endswith('KiB') else 1024**2)
        sets,rem=divmod(amount,(16 if k=='l2' else 8)*64)
        if rem or not sets or sets&(sets-1):raise ValueError('cache must have a power-of-two set count')
    keys(c['axi'],'period_ns outstanding planes stalls replay','axi')
    for k,hi in (('period_ns',1000),('outstanding',128),('planes',4)):integer(c['axi'][k],1,hi,'axi.'+k)
    for k in ('stalls','replay'):
        if type(c['axi'][k]) is not bool:raise ValueError('axi.'+k+' must be boolean')
    u=c['ucie'];keys(u,'lanes rate_gtps bits_per_symbol tat_ns','ucie')
    integer(u['lanes'],1,256,'ucie.lanes');integer(u['bits_per_symbol'],1,2,'ucie.bits_per_symbol')
    for k,lo,hi in (('rate_gtps',0,1000),('tat_ns',0,1000000)):
        v=u[k]
        if type(v) not in (int,float) or not math.isfinite(v) or not lo<=v<=hi or (k=='rate_gtps' and not v):raise ValueError('invalid ucie.'+k)
    m=c['memsim'];keys(m,'standard channels scale queue slots response_hold','memsim')
    if m['standard'] not in ('hbm3','hbm4','lpddr5','lpddr6'):raise ValueError('unsupported memory standard')
    for k in ('channels','scale','queue','slots'):integer(m[k],1,1023 if k=='slots' else 1024,'memsim.'+k)
    integer(m['response_hold'],0,1000000,'memsim.response_hold')
    keys(c['simulation'],'max_ticks','simulation');integer(c['simulation']['max_ticks'],1,10**17,'max_ticks')
    b=c['program'];kind=b.get('type')
    if kind=='smoke':
        keys(b,'type input workers','program');integer(b['input'],0,0xffffffff,'input');integer(b['workers'],1,256,'workers')
    elif kind=='tiny_llm':
        keys(b,'type prompt generated_tokens kv_cache','program');integer(b['generated_tokens'],1,8,'generated_tokens')
        if type(b['kv_cache']) is not bool:raise ValueError('kv_cache must be boolean')
        if not isinstance(b['prompt'],str) or not b['prompt'] or len(b['prompt'])+b['generated_tokens']-1>16:raise ValueError('prompt exceeds model context')
    elif kind=='custom':
        keys(b,'type defines expect workers','program');integer(b['workers'],1,256,'workers')
        if not isinstance(b['defines'],dict):raise ValueError('defines must be an object')
        for name,v in b['defines'].items():
            if not re.fullmatch('[A-Z][A-Z0-9_]*',name):raise ValueError('invalid define name')
            integer(v,0,0xffffffff,'define '+name)
        if not isinstance(b['expect'],list) or not b['expect']:raise ValueError('expected outputs required')
        for e in b['expect']:
            keys(e,'address value','expected word');a=int(e['address'],0)
            if a%4 or not 0x90000000<=a<0x90060000:raise ValueError('expected address outside user buffer')
            integer(e['value'],0,0xffffffff,'expected value')
    else:raise ValueError('program.type must be smoke, tiny_llm or custom')
    return c

def load_config(path):return validate(json.loads(Path(path).read_text()))
def resolved_parts(c):
    a={'device_clock_mhz':c['gpu']['clock_mhz'],'simx':{k:c['gpu'][k] for k in ('cores','warps','threads')},'gpu':c['gpu'],'host':c['host'],'axi':c['axi'],'memory':c['memsim'],'ucie':c['ucie'],'max_ticks':c['simulation']['max_ticks']}
    return a,{'name':c['program']['type'],**{k:v for k,v in c['program'].items() if k!='type'}}
def address_map(a=None):
    m=json.loads((RUNTIME/'defaults/addrmap.json').read_text())
    if a:
        for s in m['sources']:s['clock_mhz']=a['host']['clock_mhz'] if s['name']=='host' else a['device_clock_mhz']
    return m

def simx_flags(c):
    g=c['gpu'];values={**{'NUM_'+k.upper():g[k] for k in ('cores','warps','threads')},'ICACHE_SIZE':g['l1i_bytes'],'DCACHE_SIZE':g['l1d_bytes'],'L2_SIZE':g['l2_bytes']}
    return ' '.join('-DVX_CFG_'+k+'='+str(v) for k,v in values.items())+' -DVX_CFG_L2_'+('ENABLE' if g['l2_enabled'] else 'DISABLE')
def build_inputs(c):return {'gpu':{k:v for k,v in c['gpu'].items() if k!='clock_mhz'},'defaults':(RUNTIME/'defaults/simx.toml').read_text()}
