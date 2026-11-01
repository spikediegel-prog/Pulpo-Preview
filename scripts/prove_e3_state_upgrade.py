"""Synthetic native-Linux historical state upgrade; never opens live state."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile

CHILD = r'''
import hashlib,json,sqlite3,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from pulpo import GovernanceKernel,Intent,Policy,SQLiteKernelState,StateIntegrityError
folder=Path(sys.argv[2]); mode=sys.argv[3]; path=folder/'synthetic.sqlite3'
intent=Intent('agent:e3','read','synthetic:e3',0)
with SQLiteKernelState(path) as state:
    kernel=GovernanceKernel(Policy(frozenset({'read'}),0),secret=b'E3-public-synthetic-fixture-only',clock=lambda:1000000,state=state)
    if mode=='legacy':
        decision=kernel.evaluate(intent)
        assert decision.outcome=='allow' and kernel.consume(decision.permit,intent)
        (folder/'fixture.json').write_text(json.dumps({'permit':decision.permit,'prefix':list(state.audit)}))
        assert kernel.verify_audit()
    else:
        fixture=json.loads((folder/'fixture.json').read_text())
        assert list(state.audit)[:len(fixture['prefix'])]==fixture['prefix']
        assert kernel.verify_audit() and not kernel.consume(fixture['permit'],intent)
        assert kernel.verify_audit()
    print(json.dumps({'mode':mode,'audit_count':len(state.audit),'audit_digest':hashlib.sha256(json.dumps(state.audit,sort_keys=True).encode()).hexdigest(),'audit_verified':True}))
if mode=='future':
    with sqlite3.connect(path) as db:
        # A newer producer would replace the current version=1 CHECK too.
        db.execute('DROP TABLE audit_integrity_schema')
        db.execute('CREATE TABLE audit_integrity_schema (id INTEGER PRIMARY KEY, version INTEGER NOT NULL)')
        db.execute('INSERT INTO audit_integrity_schema VALUES (1,2)')
    with sqlite3.connect(path) as db: before=tuple(db.iterdump())
    try: SQLiteKernelState(path)
    except (StateIntegrityError,ValueError): pass
    else: raise AssertionError('future schema accepted')
    with sqlite3.connect(path) as db: assert before==tuple(db.iterdump())
    print(json.dumps({'future_schema_rejected_without_rewrite':True}))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--legacy-root', type=Path, required=True)
    parser.add_argument('--owner-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if platform.system() != 'Linux' or os.geteuid() == 0:
        raise RuntimeError('Run on native Linux as the normal VM user')
    if args.output.exists() or not args.output.is_absolute():
        raise ValueError('New absolute output required')
    report = {'passed': False, 'cases': [], 'limits': [
        'Synthetic database only; no customer recovery or external storage.',
        'One historical legacy schema to current migration, not every historical version.',
        'Kernel/database downgrade is unsupported; app rollback must not downgrade canonical state.',
        'Historical adoption cannot prove a prefix lost before the upgrade.']}
    for label, root in [('legacy', args.legacy_root), ('current', args.owner_root)]:
        report[label + '_sha'] = subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()
        if subprocess.check_output(['git','-C',str(root),'status','--porcelain'],text=True).strip():
            raise RuntimeError(label + ' source must be clean')
    if report['legacy_sha'] != '12d07e37a34c979fc054872299191bb26c8ad387':
        raise RuntimeError('Unexpected historical checkpoint')
    args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        tests = subprocess.run([sys.executable,'-B','-m','unittest','-v',
            'tests.test_audit_integrity_migration','tests.test_persistence'],
            cwd=args.owner_root,capture_output=True,text=True,timeout=180)
        args.output.with_suffix('.tests.log').write_text(tests.stdout+tests.stderr)
        if tests.returncode or 'skipped=' in tests.stderr:
            raise RuntimeError('Selected state tests did not all pass')
        report['selected_unittest_summary'] = tests.stderr.strip().splitlines()[-3:]
        with tempfile.TemporaryDirectory(prefix='e3-state-',dir=args.output.parent) as temporary:
            for mode, root in [('legacy',args.legacy_root),('upgrade',args.owner_root),
                               ('restart',args.owner_root),('future',args.owner_root)]:
                child = subprocess.run([sys.executable,'-I','-B','-c',CHILD,str(root),temporary,mode],
                    capture_output=True,text=True,timeout=40)
                if child.returncode:
                    raise RuntimeError(mode+': '+child.stderr)
                report['cases'].extend(json.loads(line) for line in child.stdout.splitlines())
        report['passed'] = True
    except Exception as exc:
        report['error'] = str(exc)
        raise
    finally:
        with args.output.open('x') as stream:
            json.dump(report,stream,indent=2);stream.write('\n')
    print(json.dumps({'passed':True,'evidence':str(args.output)}))


if __name__ == '__main__':
    main()
