"""Execute only exact configuration parsing; no service, network or signing."""
import ast,json,secrets,sys,tempfile
from dataclasses import dataclass
from pathlib import Path
root=Path(sys.argv[1]).resolve()
sys.path.insert(0,str(root))
path=root/'custody-service/src/pulpo_custody_service/runtime.py'
tree=ast.parse(path.read_text())
names={'PILOT_MAX_CENTS','RuntimeConfigError','_required','_hex_secret','_positive_int','RuntimeConfig'}
nodes=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0)]
for node in tree.body:
    if getattr(node,'name',None) in names or (isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id in names for t in node.targets)):
        nodes.append(node)
namespace={'dataclass':dataclass,'Path':Path}
exec(compile(ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[])),str(path),'exec'),namespace)
Config=namespace['RuntimeConfig']
with tempfile.TemporaryDirectory(prefix='pulpo-config-test-') as folder:
    env={'PULPO_CUSTODY_STATE_PATH':str(Path(folder)/'unused.sqlite3'),
        'PULPO_KERNEL_SECRET_HEX':secrets.token_hex(32),'PULPO_CUSTODY_SECRET_HEX':secrets.token_hex(32),
        'PULPO_AUTHORITY_PUBLIC_KEY_HEX':'d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a',
        'PULPO_AUTHORITY_ID':'test','PULPO_AUTHORITY_VERIFIER_ID':'test','PULPO_AUTHORITY_KEY_ID':'test',
        'PULPO_AUTHORITY_DEPLOYMENT_ID':'test','PULPO_AUTHORITY_MAX_TTL_SECONDS':'300',
        'PULPO_PILOT_BUDGET_CENTS':'3000','PULPO_OWNER_REF':'owner://test',
        'NAMECOM_SANDBOX_USERNAME':'fixture-test','NAMECOM_SANDBOX_EXECUTOR_TOKEN':'fake-executor',
        'NAMECOM_SANDBOX_OBSERVER_TOKEN':'fake-observer'}
    results=[]
    for name in ['PULPO_KERNEL_SECRET_HEX','PULPO_CUSTODY_SECRET_HEX']:
        fixture=('11' if name=='PULPO_KERNEL_SECRET_HEX' else '22')*32
        for label,value in [('missing',None),('short','aa'*16),('all-zero','00'*32),('published-fixture',fixture)]:
            config=dict(env)
            if value is None:config.pop(name)
            else:config[name]=value
            try:Config.from_environ(config)
            except namespace['RuntimeConfigError'] as exc:
                assert name in str(exc), 'Another field masked the tested configuration'
                results.append({'field':name,'case':label,'accepted':False,'reason':str(exc)})
            else:results.append({'field':name,'case':label,'accepted':True})
from pulpo.kernel import GovernanceKernel,Policy
a=GovernanceKernel(Policy(frozenset({'read'}),0))
b=GovernanceKernel(Policy(frozenset({'read'}),0))
report={'scope':'Exact runtime configuration AST only; no service construction or real credentials',
        'config_tests':results,'default_kernel_secret_bytes':len(a._secret),
        'independent_default_kernel_secrets_differ':a._secret!=b._secret}
Path(sys.argv[2]).write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
