"""Ubuntu-only isolated probes: synthetic TLS credentials and fake effects."""
from dataclasses import replace
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
import hashlib, json, multiprocessing as mp, os, signal, ssl, subprocess, sys, tempfile, threading

ROOT=Path(sys.argv[1]).resolve()
OUT=Path(sys.argv[2]).resolve()
sys.path.insert(0,str(ROOT))
CTX=mp.get_context('spawn')

def transport_probe(folder):
    import pulpo.github_execution_context as module
    key,cert=folder/'tls-key.pem',folder/'tls-cert.pem'
    subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-keyout',str(key),'-out',str(cert),'-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost,IP:127.0.0.1','-addext','basicConstraints=critical,CA:TRUE'],check=True,capture_output=True)
    import secrets
    token=secrets.token_hex(32)
    received=[]
    class Sink(BaseHTTPRequestHandler):
        def do_GET(self):
            received.append(self.headers.get('Authorization') == 'Bearer '+token)
            payload=b'{"login":"synthetic","id":1}'
            self.send_response(200); self.send_header('Content-Length',str(len(payload))); self.end_headers(); self.wfile.write(payload)
        def log_message(self,*args): pass
    class Redirect(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(302); self.send_header('Location',f'https://localhost:{sink.server_port}/capture'); self.send_header('Content-Length','0'); self.end_headers()
        def log_message(self,*args): pass
    servers=[]
    try:
        for handler in (Sink,Redirect):
            server=ThreadingHTTPServer(('127.0.0.1',0),handler)
            context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); context.load_cert_chain(cert,key)
            server.socket=context.wrap_socket(server.socket,server_side=True)
            thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
            servers.append((server,thread))
            if handler is Sink: sink=server
            else: origin=server
        env={k:v for k,v in os.environ.items() if k.lower() not in ('http_proxy','https_proxy','all_proxy','ssl_cert_file','ssl_cert_dir','requests_ca_bundle','curl_ca_bundle')}
        env.update(SSL_CERT_FILE=str(cert),PULPO_CA_BUNDLE=str(cert))
        with patch.dict(os.environ,env,clear=True),patch.object(module,'_GITHUB_API_ORIGIN',f'https://127.0.0.1:{sink.server_port}'):
            assert module.GitHubRESTMetadataReader(token).fetch_authenticated_user()['login']=='synthetic'
        assert received==[True]
        received.clear()
        with patch.dict(os.environ,env,clear=True),patch.object(module,'_GITHUB_API_ORIGIN',f'https://127.0.0.1:{origin.server_port}'):
            error=None
            try: module.GitHubRESTMetadataReader(token).fetch_authenticated_user()
            except module.GitHubContextAttestationError as exc: error=type(exc).__name__
        class Response:
            status=200
            requested=None
            closed=False
            def read(self,size=-1):
                self.requested=size
                data=b'{"padding":"'+b'x'*(2*1024*1024)+b'"}'
                return data if size<0 else data[:size]
            def close(self): self.closed=True
        response=Response()
        accepted=True
        try: module.GitHubRESTMetadataReader('synthetic-token',opener=lambda *a,**k:response).fetch_authenticated_user()
        except module.GitHubContextAttestationError: accepted=False
        return {'tls_fixture_only':True,'positive_tls_authenticated_read':True,'cross_origin_destination_calls':len(received),'synthetic_bearer_received':any(received),'reader_error':error,'oversized_metadata_accepted':accepted,'response_read_limit':response.requested,'response_closed':response.closed}
    finally:
        for server,thread in reversed(servers): server.shutdown(); server.server_close(); thread.join(3)
        key.unlink(missing_ok=True); cert.unlink(missing_ok=True)

def consume_worker(path,permit,intent,barrier,queue):
    from pulpo import GovernanceKernel,Policy
    from pulpo.state import SQLiteKernelState
    state=SQLiteKernelState(path)
    try:
        kernel=GovernanceKernel(Policy(frozenset({'read'}),0),secret=b'round2-synthetic',clock=lambda:1000,state=state)
        barrier.wait(15)
        queue.put({'consumed':kernel.consume(permit,intent)})
    except Exception as exc: queue.put({'error':type(exc).__name__})
    finally: state.close()

def budget_worker(path,order,barrier,queue):
    from pulpo.commerce import SQLiteBudgetAccount,CommerceViolation
    account=SQLiteBudgetAccount(path)
    barrier.wait(15)
    try:
        account.reserve(order,now_ns=11_000_000)
        queue.put('reserved')
    except CommerceViolation as exc: queue.put(str(exc))

def group(target,arguments):
    count=len(arguments); barrier=CTX.Barrier(count); queue=CTX.Queue()
    processes=[CTX.Process(target=target,args=(*args,barrier,queue)) for args in arguments]
    try:
        for p in processes:p.start()
        results=[queue.get(timeout=25) for _ in processes]
        for p in processes:p.join(10); assert p.exitcode==0,p.exitcode
        return results
    finally:
        for p in processes:
            if p.is_alive():p.kill();p.join(5)
        queue.close();queue.join_thread()

def concurrency_probe(folder):
    from pulpo import GovernanceKernel,Policy,Intent
    from pulpo.state import SQLiteKernelState
    from pulpo.commerce import SQLiteBudgetAccount
    from tests.test_custody_executor import CustodyExecutorTests
    path=folder/'permits.sqlite3'
    state=SQLiteKernelState(path)
    kernel=GovernanceKernel(Policy(frozenset({'read'}),0),secret=b'round2-synthetic',clock=lambda:1000,state=state)
    intent=Intent('agent:synthetic','read','synthetic:resource')
    permit=kernel.evaluate(intent).permit; state.close()
    consumed=group(consume_worker,[(path,permit,intent)]*8)
    assert sum(item.get('consumed',False) for item in consumed)==1,consumed
    assert not any('error' in item for item in consumed),consumed
    state=SQLiteKernelState(path)
    try:
        kernel=GovernanceKernel(Policy(frozenset({'read'}),0),secret=b'round2-synthetic',clock=lambda:1000,state=state)
        assert kernel.verify_audit()
        count=sum(row['event']=='permit_consumed' for row in kernel.audit)
        assert count==1,count
    finally:state.close()
    account=SQLiteBudgetAccount(folder/'budget.sqlite3')
    fixture=CustodyExecutorTests()
    orders=[fixture.order(f'round2-{i}.example') for i in range(8)]
    reservations=group(budget_worker,[(folder/'budget.sqlite3',order) for order in orders])
    assert reservations.count('reserved')==1,reservations
    assert account.reserved_cents==2000 and account.available_cents==1000
    return {'independent_processes':8,'permit_results':consumed,'verified_consumption_events':count,'budget_results':reservations,'reserved_cents':account.reserved_cents,'available_cents':account.available_cents}

def execution_race_worker(path,governed,order,log,barrier,queue):
    from pulpo.custody import SQLiteGovernanceCustody,CustodyViolation
    from pulpo.custody_executor import TrustedDomainExecutor
    custody=SQLiteGovernanceCustody(path,signing_secret=b'trusted-executor-custody',clock=lambda:11_000_000)
    barrier.wait(15)
    try:
        TrustedDomainExecutor(custody,executor_id='executor:round2').execute(governed,order,EffectAdapter(log))
        queue.put('executed')
    except CustodyViolation as exc:queue.put('rejected:'+str(exc))

def revocation_worker(path,permit,intent,ready,release,queue):
    from pulpo.state import SQLiteKernelState
    from tests.test_directives import DirectiveProofTests
    state=SQLiteKernelState(path)
    try:
        kernel,_=DirectiveProofTests().governed(state)
        ready.set();assert release.wait(15)
        queue.put(kernel.consume(permit,intent))
    finally:state.close()

def additional_state_probe(folder):
    from tests.test_custody_executor import CustodyExecutorTests
    from tests.test_directives import DirectiveProofTests,directive,OPERATOR
    from pulpo.state import SQLiteKernelState
    from pulpo.directives import GovernedDirectiveProjection
    from pulpo import Intent
    fixture=CustodyExecutorTests();fixture.path=folder/'execution-race.sqlite3'
    try:_,_,governed,order=fixture.governed_attempt()
    finally:fixture.doCleanups()
    log=folder/'execution-race-effects.log'
    execution=group(execution_race_worker,[(fixture.path,governed,order,log)]*6)
    assert execution.count('executed')==1,execution
    assert len(log.read_text().splitlines())==1
    path=folder/'revocation.sqlite3';state=SQLiteKernelState(path)
    fixture=DirectiveProofTests();d=directive()
    kernel,verifier,controller=fixture.activate(state,d)
    intent=Intent('agent:builder','write','repo:file',1)
    decision=GovernedDirectiveProjection(kernel).evaluate(intent,d)
    assert decision.outcome=='allow'
    ready,release,queue=CTX.Event(),CTX.Event(),CTX.Queue()
    child=CTX.Process(target=revocation_worker,args=(path,decision.permit,intent,ready,release,queue))
    try:
        child.start();assert ready.wait(15)
        envelope=fixture.approve(kernel,verifier,controller.REVOKE,d,'round2-revoke','round2-revoke-nonce')
        assert controller.revoke(d,envelope,operator_principal=OPERATOR).outcome=='allow'
        release.set();consumed=queue.get(timeout=15);child.join(10)
        assert child.exitcode==0 and consumed is False
        assert kernel.verify_audit()
    finally:
        if child.is_alive():child.kill();child.join(5)
        state.close();queue.close();queue.join_thread()
    return {'execution_processes':6,'execution_results':execution,'durable_fake_provider_effects':1,'preopened_other_process_consumed_after_revocation':consumed,'audit_valid':True}

class EffectAdapter:
    def __init__(self,log,phase=None,connection=None):self.log=Path(log);self.phase=phase;self.connection=connection
    def stop(self,phase):
        if self.phase==phase:
            self.connection.send(phase)
            self.connection.recv()  # parent kills only this disposable child
    def preflight(self,order):self.stop('preflight');return 'b'*64
    def purchase(self,order,*,max_charge_cents,idempotency_key):
        from pulpo.commerce import RegistrarResult
        self.stop('before_effect')
        fd=os.open(self.log,os.O_CREAT|os.O_WRONLY|os.O_APPEND,0o600)
        try:os.write(fd,(idempotency_key+'\n').encode());os.fsync(fd)
        finally:os.close(fd)
        self.stop('after_effect')
        return RegistrarResult(payment_id='synthetic',charged_cents=order.purchase_price_cents,receipt_hash='a'*64,registration_id='synthetic',domain=order.domain,registrar=order.registrar)

def execute_worker(path,governed,order,log,phase,connection):
    from pulpo.custody import SQLiteGovernanceCustody
    from pulpo.custody_executor import TrustedDomainExecutor
    custody=SQLiteGovernanceCustody(path,signing_secret=b'trusted-executor-custody',clock=lambda:11_000_000)
    try:TrustedDomainExecutor(custody,executor_id='executor:round2').execute(governed,order,EffectAdapter(log,phase,connection))
    except Exception as exc:connection.send({'error':type(exc).__name__})
    finally:connection.close()

def crash_probe(folder):
    from tests.test_custody_executor import CustodyExecutorTests
    from pulpo.custody import SQLiteGovernanceCustody,CustodyViolation
    from pulpo.custody_executor import TrustedDomainExecutor
    results=[]
    for phase in ('preflight','before_effect','after_effect'):
        fixture=CustodyExecutorTests();fixture.path=folder/(phase+'.sqlite3')
        try:custody,budget,governed,order=fixture.governed_attempt()
        finally:fixture.doCleanups()
        log=folder/(phase+'-provider-effects.log')
        parent,child=CTX.Pipe()
        process=CTX.Process(target=execute_worker,args=(fixture.path,governed,order,log,phase,child))
        try:
            process.start();child.close()
            assert parent.poll(15),'worker did not reach kill boundary'
            assert parent.recv()==phase,'unexpected worker failure'
            process.kill();process.join(10);assert process.exitcode==-signal.SIGKILL
        finally:
            if process.is_alive():process.kill();process.join(5)
            parent.close();child.close()
        custody=SQLiteGovernanceCustody(fixture.path,signing_secret=b'trusted-executor-custody',clock=lambda:11_000_000)
        before=custody.attempt(governed.attempt_id).state
        rejected=False
        try:TrustedDomainExecutor(custody,executor_id='executor:round2').execute(governed,order,EffectAdapter(log))
        except CustodyViolation:rejected=True
        effects=log.read_text().splitlines() if log.exists() else []
        assert len(effects)==(0 if phase=='before_effect' else 1),(phase,effects)
        assert rejected==(phase!='preflight'),(phase,rejected)
        results.append({'kill_boundary':phase,'exit_signal':'SIGKILL','durable_state_after_kill':before,'retry_rejected':rejected,'durable_fake_provider_effects':len(effects),'budget_remains_reserved_cents':budget.reserved_cents})
    return results

def main():
    report={'source':str(ROOT),'python':sys.version,'probe_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'source_sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ('pulpo/github_execution_context.py','pulpo/state.py','pulpo/kernel.py','pulpo/custody_executor.py','pulpo/custody.py','pulpo/commerce.py')},'scope':'Loopback TLS, independent spawned Linux processes, disposable SQLite, durable fake-provider effect log; no live credentials, no external network.'}
    with tempfile.TemporaryDirectory(prefix='pulpo-round2-') as folder:
        directory=Path(folder)
        probes=[('additional_state',additional_state_probe)] if '--state-only' in sys.argv else [('transport',transport_probe),('concurrency',concurrency_probe),('crash_recovery',crash_probe),('additional_state',additional_state_probe)]
        for name,probe in probes:
            try:report[name]=probe(directory)
            except Exception as exc:report[name]={'probe_error':type(exc).__name__,'detail':str(exc)}
            OUT.write_text(json.dumps(report,indent=2))
            print(name+': '+json.dumps(report[name]),flush=True)
    assert not any(isinstance(v,dict) and 'probe_error' in v for v in report.values()),'probe execution failed'

if __name__=='__main__':main()
