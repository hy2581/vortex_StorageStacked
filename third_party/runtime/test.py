"""Run user-visible projects and check computation, timing feedback and errors."""
import argparse,concurrent.futures,copy,datetime,json,subprocess
from pathlib import Path
from paths import ROOT,CACHE,MEMSIM_BUILD,STORAGE_ROOT,dump,relative
from report import write_report,write_status
from check_negative import check
p=argparse.ArgumentParser();p.add_argument('--project',choices=('smoke','llm'));o=p.parse_args()
stamp='test-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
output=CACHE/'validation'/stamp;output.mkdir(parents=True);write_status(output,'regression')
cases=[]
def add(name,project,updates):
    c=json.loads((ROOT/'user'/project/'config.json').read_text())
    for group,fields in updates.items():c[group].update(fields)
    path=ROOT/'user'/project/'result'/stamp/(name+'.json');dump(path,c)
    cases.append((name,project,path,c))
if o.project in (None,'smoke'):
    add('smoke','smoke',{})
    add('smoke_slow','smoke',{'memsim':{'scale':4}})
    add('smoke_wrap','smoke',{'program':{'input':0xffffffff}})
if o.project in (None,'llm'):
    add('llm','llm',{})
    add('llm_no_cache','llm',{'program':{'kv_cache':False}})
    add('llm_replay','llm',{'axi':{'replay':True}})
    add('llm_long','llm',{'program':{'prompt':'red blue ','generated_tokens':4}})

def run(case):
    name,project,path,c=case;result=path.parent/name
    with (output/(name+'.log')).open('w') as log:
        subprocess.run([str(ROOT/'user/run.sh'),project,'--config',relative(path,ROOT/'user'/project),'--output',relative(result,ROOT/'user'/project)],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
    s=json.loads((result/'summary.json').read_text());assert s['passed']
    return name,result,s
try:
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:finished=list(pool.map(run,cases))
    if o.project in (None,'smoke'):
        add('smoke_arch','smoke',{
            'program':{'workers':8},
            'gpu':{'cores':4,'warps':8,'threads':8,'l1i_bytes':32768,'l1d_bytes':32768,'l2_enabled':True,'l2_bytes':524288},
            'host':{'num_cpus':2,'clock_mhz':1000,'l1i':'16KiB','l1d':'16KiB','l2':'512KiB','tlb_entries':32},
            'axi':{'period_ns':3,'outstanding':2,'planes':1,'stalls':False},
            'ucie':{'lanes':8,'rate_gtps':16,'tat_ns':80},
            'memsim':{'scale':2,'queue':1,'slots':1,'response_hold':3}})
        finished.append(run(cases[-1]))
    by_name={name:(result,s) for name,result,s in finished}
    checks={}
    if 'smoke_slow' in by_name:
        fast=by_name['smoke'][1];slow=by_name['smoke_slow'][1]
        assert slow['devices']['cycles']>fast['devices']['cycles'],'Memory slowdown did not reach GPU execution'
        checks['memory_feedback']={'passed':True,'base_cycles':fast['devices']['cycles'],'slow_cycles':slow['devices']['cycles']}
    if 'llm_no_cache' in by_name:
        cached=by_name['llm'][1]['llm'];uncached=by_name['llm_no_cache'][1]['llm']
        assert cached['generated_token_ids']==uncached['generated_token_ids']
        assert cached['forward_calls']<uncached['forward_calls']
        checks['kv_cache']={'passed':True,'cached_calls':cached['forward_calls'],'uncached_calls':uncached['forward_calls']}
    negative=check(by_name['smoke'][0] if 'smoke' in by_name else None,by_name['llm'][0] if 'llm' in by_name else None)
    native_plan=json.loads(subprocess.check_output(['ctest','--test-dir',str(MEMSIM_BUILD),'--show-only=json-v1'],text=True))
    with (output/'native.log').open('w') as log:subprocess.run(['ctest','--test-dir',str(MEMSIM_BUILD),'--output-on-failure'],stdout=log,stderr=subprocess.STDOUT,check=True)
    with (output/'api.log').open('w') as log:subprocess.run(['python',str(STORAGE_ROOT/'mem_sim/integration/check_online.py'),str(MEMSIM_BUILD/'libstoragestacked_memsim.so'),str(output/'api')],stdout=log,stderr=subprocess.STDOUT,check=True)
    s={'passed':True,'native_tests_passed':len(native_plan['tests']),'api_check':json.loads((output/'api/api_check.json').read_text()),'negative':negative,'comparisons':checks,'cases':{}}
    for name,result,item in finished:
        value=item['smoke']['output'] if 'smoke' in item else item['llm']['generated_text']
        s['cases'][name]={'passed':True,'output':value,'cycles':item['devices']['cycles'],'report':relative(result/'report.md',output)}
    dump(output/'summary.json',s);write_report(output);print('PASS:',relative(output/'report.md'))
except Exception as error:
    write_status(output,'regression',str(error));raise

finally:
    from portable import sanitize
    sanitize(output)
