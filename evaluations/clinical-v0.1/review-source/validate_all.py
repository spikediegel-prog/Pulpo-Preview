"""Run only the bounded offline evaluation and selected upstream regressions."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parent

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',required=True,help='New directory')
    args=p.parse_args();out=Path(args.out).resolve();out.mkdir(parents=True,exist_ok=False)
    results=[]
    def run(name,argv,cwd=ROOT):
        started=time.time()
        r=subprocess.run([sys.executable,*argv],cwd=cwd,capture_output=True,text=True,timeout=180)
        (out/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        results.append({'name':name,'exit_code':r.returncode,'passed':r.returncode==0,'seconds':round(time.time()-started,3),'argv':argv})
    for engine in ['canonical','preview']:
        run('clinical-'+engine,['evaluate.py','--engine',engine,'--out',str(out/engine)])
        modules=['tests.test_kernel','tests.test_directives','tests.test_authority']
        if engine=='preview':modules+=['tests.test_external_authority_boundaries','tests.test_permit_lifetime','tests.test_guarded_recovery']
        run('upstream-'+engine,['-m','unittest',*modules,'-v'],ROOT/'vendor'/engine)
    run('observer-and-config',['-m','unittest','test_clinical','-v'])
    summary={'schema':'pulpo.clinical-test-summary.v0.1','recorded_at_ns':time.time_ns(),
             'runtime':sys.version,'host_platform':sys.platform,
             'scope':'Selected local synthetic tests only. Host execution is not hypervisor or production qualification.',
             'results':results,'result':'PASS' if all(r['passed'] for r in results) else 'FAIL'}
    (out/'TEST-SUMMARY.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))
    return 0 if summary['result']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
