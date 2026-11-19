"""Synthetic test harness. The bundled, unchanged Pulpo kernel owns all authority.

Fixture signer is the upstream public test double, never a human signing key.
This program is test tooling, not a WSUS executor or a deployment service.
"""
from __future__ import annotations
import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import secrets
import socket
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parent

def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', choices=['canonical', 'preview'], default='canonical')
    parser.add_argument('--config', default=str(ROOT / 'config/clinical.example.json'))
    parser.add_argument('--out', required=True, help='New evidence directory; existing output is refused')
    args = parser.parse_args()
    from clinical_config import load
    config = load(args.config)
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(ROOT / 'vendor' / args.engine))
    from pulpo import AgentGrant, GovernanceKernel, Intent, Policy, SQLiteKernelState
    from pulpo.directives import Directive, DirectiveAuthorityController, GovernedDirectiveProjection
    from fixture_authority import HmacTestVerifier, signed_envelope, trust_for
    # Any accidental socket use fails in this process. OS isolation is still required
    # for a hostile guest; this guard is not a network security boundary.
    def no_network(*a, **kw):
        raise RuntimeError('Network disabled in synthetic evaluation')
    socket.socket = no_network
    socket.create_connection = no_network
    rows = []
    def check(name, condition, detail=''):
        rows.append({'name': name, 'passed': bool(condition), 'detail': detail,
                     'classification': 'Verified' if condition else 'Recorded'})
    actions = frozenset({'simulate_patch', 'simulate_fhir', 'simulate_dicom'})
    control = frozenset({'activate_directive', 'revoke_directive'})
    sites = config['sites']
    a, b = sites[1:3]
    grants = [AgentGrant('operator:central', control, ('directive:site-',), 0)]
    for site in sites:
        grants += [AgentGrant('agent:' + site, actions, (f'sim:site:{site}:',), 1),
                   AgentGrant('operator:' + site + '-local', control,
                              (f'directive:site-{site}:',), 0)]
    verifier = HmacTestVerifier()  # Known public fixture material only.
    trust = trust_for(verifier, deployment_id=config['deployment'], max_approval_ttl_ns=10**12)
    policy = Policy(actions | control, 1, control, tuple(grants), trust)
    now = [1_000_000_000_000]
    clock = lambda: now[0]
    secret = secrets.token_bytes(32)  # Ephemeral synthetic kernel MAC; never exported.
    serial = [0]
    def envelope(kernel, intent, **kw):
        serial[0] += 1
        return signed_envelope(kernel, intent, verifier, now_ns=now[0], ttl_ns=10**9,
                               approval_id=f'fixture-{serial[0]}', nonce=f'nonce-{serial[0]}', **kw)
    def directive(site, suffix='', *, start=None, end=None):
        # Delimiters prevent clinic-a from matching clinic-ab.
        return Directive(f'site-{site}' + suffix, 1, trust.authority_id, 'agent:' + site,
                         actions, (f'sim:site:{site}:ring:{config["patch_ring"]}:update:KB-SYNTH-001:',), 1,
                         start or now[0], end or now[0] + config['window_seconds'] * 10**9)
    def intent(site, action='simulate_patch', suffix='device-001', principal=None):
        resource = f'sim:site:{site}:ring:{config["patch_ring"]}:update:KB-SYNTH-001:{suffix}'
        return Intent(principal or 'agent:' + site, action, resource, 1, 'clinical-fixture')
    inventory = {s: {'device': 'device-001', 'update': 'KB-SYNTH-001',
                     'patch_state': 'pending', 'source': 'synthetic'} for s in sites}
    observations = []
    def transition(kernel, d, operation='activate_directive', operator='operator:central', env=None):
        controller = DirectiveAuthorityController(kernel)
        i = controller.authority_intent(operation, d, operator_principal=operator)
        env = env or envelope(kernel, i)
        method = controller.activate if operation == 'activate_directive' else controller.revoke
        return method(d, env, operator_principal=operator), env
    with tempfile.TemporaryDirectory(prefix='pulpo-clinical-') as tmp:
        db = Path(tmp) / 'synthetic.sqlite3'
        state = SQLiteKernelState(db)
        kernel = GovernanceKernel(policy, secret=secret, approval_verifier=verifier, clock=clock, state=state)
        projection = GovernedDirectiveProjection(kernel)
        d = directive(a)
        i = intent(a)
        check('unactivated directive denies', projection.evaluate(i, d).outcome == 'deny')
        activated, activation_envelope = transition(kernel, d)
        check('central activates site window', activated.outcome == 'allow', activated.reason)
        # Narrow site authority cannot activate a directive for another site.
        cross, _ = transition(kernel, directive(b), operator='operator:' + a + '-local')
        check('site operator cannot activate another site', cross.outcome == 'deny', cross.reason)
        check('cross-site worker denied', projection.evaluate(intent(b, principal='agent:' + a), d).outcome == 'deny')
        check('unknown worker denied', projection.evaluate(intent(a, principal='agent:unknown'), d).outcome == 'deny')
        check('prefix sibling denied', kernel.evaluate(intent(a + 'b', principal='agent:' + a)).outcome == 'deny')
        check('live action name denied', kernel.evaluate(replace(i, action='approve_wsus_update')).outcome == 'deny')
        check('live resource denied', kernel.evaluate(replace(i, resource='https://wsus.invalid')).outcome == 'deny')
        check('other ring denied by directive', projection.evaluate(replace(i,resource=i.resource.replace(':ring:'+config['patch_ring']+':',':ring:other:')),d).outcome == 'deny')
        check('different update denied by directive', projection.evaluate(replace(i,resource=i.resource.replace('KB-SYNTH-001','KB-SYNTH-999')),d).outcome == 'deny')
        check('cost expansion denied', projection.evaluate(replace(i,cost=2),d).outcome == 'deny')
        check('missing permit rejected', not kernel.consume(None,i))
        allowed = projection.evaluate(i, d)
        check('permit issued for exact synthetic patch', allowed.outcome == 'allow' and bool(allowed.permit))
        check('substituted update rejected', not kernel.consume(allowed.permit, replace(i, resource=i.resource.replace('001', '999'))))
        accepted = kernel.consume(allowed.permit, i)
        if accepted:
            # Test consequence only: no shell, service, adapter or host action.
            inventory[a]['patch_state'] = 'installed-simulated'
            observations.append({'site': a, 'intent_hash': kernel.intent_hash(i),
                                 'observation': 'installed-simulated', 'classification': 'Recorded'})
        check('simulated patch consequence observed', accepted and inventory[a]['patch_state'] == 'installed-simulated')
        check('one-use permit replay denied', not kernel.consume(allowed.permit, i))
        replay, _ = transition(kernel, d, env=activation_envelope)
        check('activation approval replay denied', replay.outcome == 'deny', replay.reason)
        reserved = projection.evaluate(intent(a, suffix='device-002'), d)
        revoked, _ = transition(kernel, d, 'revoke_directive')
        check('revocation accepted by canonical controller', revoked.outcome == 'allow', revoked.reason)
        check('already-issued permit rejected after revocation', not kernel.consume(reserved.permit, intent(a, suffix='device-002')))
        check('new request rejected after revocation', projection.evaluate(i, d).outcome == 'deny')
        expiry = directive(a, '-expiry')
        transition(kernel, expiry)
        exp_i = intent(a, suffix='expiry-device')
        exp_p = projection.evaluate(exp_i, expiry)
        now[0] = expiry.expires_at_ns
        check('directive-bound permit expires at exact boundary', not kernel.consume(exp_p.permit, exp_i))
        check('expired window denies new request', projection.evaluate(exp_i, expiry).outcome == 'deny')
        future = directive(a, '-future', start=now[0]+10**9, end=now[0]+20**9)
        transition(kernel, future)
        check('future window denies', projection.evaluate(i, future).outcome == 'deny')
        bad_d = directive(a, '-invalid')
        ctrl_i = DirectiveAuthorityController.authority_intent('activate_directive', bad_d, operator_principal='operator:central')
        bad = replace(envelope(kernel, ctrl_i), signature='00'*32)
        denied, _ = transition(kernel, bad_d, env=bad)
        check('forged approval rejected', denied.outcome == 'deny', denied.reason)
        for field, value in [('session_id','substituted-session'),('principal','operator:other'),
                             ('deployment_id','other-deployment'),('policy_hash','0'*64),
                             ('intent_hash','0'*64),('key_id','key:other')]:
            substituted = replace(envelope(kernel, ctrl_i), **{field:value})
            denied, _ = transition(kernel, bad_d, env=substituted)
            check('approval substitution denied: ' + field, denied.outcome == 'deny', denied.reason)
        expired_env = envelope(kernel, ctrl_i)
        now[0] += 10**9
        denied, _ = transition(kernel, bad_d, env=expired_env)
        check('expired approval rejected', denied.outcome == 'deny', denied.reason)
        check('unknown permit rejected', not kernel.consume('not-a-permit', i))
        # An unavailable verifier represents disconnected authority, no cached grants.
        offline = GovernanceKernel(policy, secret=secret, clock=clock, state=state)
        denied, _ = transition(offline, bad_d)
        check('offline authority cannot activate', denied.outcome == 'deny', denied.reason)
        check('offline authority absence does not erase revocation', GovernedDirectiveProjection(offline).evaluate(i, d).outcome == 'deny')
        local = directive(b, '-offline-window')
        transition(kernel, local)
        cached_i = intent(b, suffix='offline-device')
        cached = projection.evaluate(cached_i, local)
        # Deliberate boundary demonstration: disconnected verifier is NOT a global
        # offline stop. Preissued local capabilities remain valid within their window.
        check('offline local permit boundary demonstrated', offline.consume(cached.permit, cached_i),
              'Verified limitation: no distributed revocation freshness is established')
        after_restart = projection.evaluate(intent(b, suffix='restart'), local)
        state.close()
        state = SQLiteKernelState(db)
        kernel = GovernanceKernel(policy, secret=secret, approval_verifier=verifier, clock=clock, state=state)
        check('canonical audit survives SQLite restart', kernel.verify_audit())
        check('spent permit remains spent after restart', not kernel.consume(allowed.permit, i))
        check('unspent permit survives ordinary same-state restart', kernel.consume(after_restart.permit, intent(b, suffix='restart')))
        projection = GovernedDirectiveProjection(kernel)
        if config['optional_simulations']:
            for action, payload in [
                ('simulate_fhir', {'resourceType':'Bundle','type':'collection','entry':[{'resource':{'resourceType':'Patient','id':'SYNTHETIC-001','active':True}}]}),
                ('simulate_dicom', {'format':'DICOM-metadata-simulation','PatientID':'SYNTHETIC-001','Modality':'DX','StudyInstanceUID':'2.25.10001','pixels':None})]:
                test_i = intent(b, action=action, suffix='synthetic-record')
                decision = projection.evaluate(test_i, local)
                ok = decision.outcome == 'allow' and kernel.consume(decision.permit, test_i)
                check(action + ' governed fixture access', ok)
                dump(out / (action + '.json'), payload)
        # Consume before a hypothetical adapter crash; never infer completion or retry.
        crash_i = intent(b, suffix='lost-receipt')
        crash_p = projection.evaluate(crash_i, local)
        taken = kernel.consume(crash_p.permit, crash_i)
        check('lost consequence receipt blocks permit retry', taken and not kernel.consume(crash_p.permit, crash_i),
              'AUTHORIZED / ATTEMPTED / CONSEQUENCE UNKNOWN; no replacement permit issued by this scenario')
        # Inspect version-specific bare permit behavior rather than assuming parity.
        bare_i = intent(b, suffix='bare-kernel-boundary')
        bare = kernel.evaluate(bare_i)
        now[0] += 301 * 10**9
        bare_accepted = kernel.consume(bare.permit, bare_i)
        check('bare permit expiry behavior at source pin',
              bare_accepted == (args.engine == 'canonical'),
              'Canonical: no bare permit TTL; Preview: default 300 second TTL. Directive window binding is tested separately.')
        check('canonical evidence chain verifies at export', kernel.verify_audit())
        audit = kernel.audit
        dump(out / 'canonical-audit.json', audit)
        policy_hash = kernel.policy_hash
        state.close()
    provenance = json.loads((ROOT / 'SOURCE-PINS.json').read_text())
    report = {'schema':'pulpo.clinical-evaluation.v0.1','synthetic_only':True,
              'engine':args.engine,'source_pin':provenance[args.engine]['commit'],
              'recorded_at_ns':time.time_ns(),'config':config,'policy_hash':policy_hash,
              'result':'PASS' if all(x['passed'] for x in rows) else 'FAIL',
              'checks':rows,'inventory':inventory,'observations':observations,
              'enforcement':'Unknown for production; local synthetic assertions only',
              'consequence_unknown':1,'authority_model':'same-process public test double; no human authority proof',
              'audit_records':len(audit),'audit_tip':audit[-1]['hash'] if audit else None}
    dump(out / 'report.json', report)
    dump(out / 'config.json', config)
    from render_report import render
    render(report, out / 'Clinical-Control-Center.html')
    manifest = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file()}
    dump(out / 'SHA256.json', manifest)
    print(json.dumps({'result':report['result'],'passed':sum(x['passed'] for x in rows),'total':len(rows),'engine':args.engine}))
    return 0 if report['result'] == 'PASS' else 1

if __name__ == '__main__':
    raise SystemExit(main())
