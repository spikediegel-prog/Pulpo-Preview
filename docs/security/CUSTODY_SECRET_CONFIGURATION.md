# Custody secret configuration

## Startup requirements

The sandbox custody service requires the operator to supply both:

- `PULPO_KERNEL_SECRET_HEX`: the kernel's persistent internal HMAC secret.
- `PULPO_CUSTODY_SECRET_HEX`: the custody receipt-signing HMAC secret.

Each must decode from hexadecimal to at least 32 bytes. Missing, empty,
malformed or short values stop startup. The service also rejects any value
formed by repeating a prefix of 1–16 bytes, including a final partial repeat.
This covers all-zero keys, any single repeated byte, the formerly published
`11`/`22` fixtures, and short repeated phrases such as `password` or `test`.
Detection uses decoded bytes, so uppercase or whitespace in valid hex cannot
hide a rejected pattern. Errors name the setting and reason without printing
its value.

There is no default password, secret fallback, automatic regeneration, or
environment switch to disable these checks. They run while parsing trusted
configuration, before the runtime constructs the service or opens its canonical
database. The public Ed25519 verification key retains its separate exact-length
validation; it is not a shared secret or a password.

This rejection rule catches known bad patterns. It cannot prove entropy,
identify every published key, or recognize a non-repeating secret somebody
copied or hashed from a public example. Use a cryptographically secure generator
and protect the resulting values; passing validation alone is not proof of safe
key provenance.

## New deployment setup

An authorized operator can generate each internal secret independently with
either of these commands, running it separately for each setting:

```sh
openssl rand -hex 32
```

```sh
python3 -c 'import secrets; print(secrets.token_hex(32))'
```

These commands print a new secret. Run them in the operator's trusted setup
environment, store the values in the deployment's protected configuration or
secret store, and supply them only to the trusted custody process. Do not put
their output in chat, the repository, examples, logs, worker environments or
human approval credentials. They generate internal service secrets, not human
signing credentials or permission to enroll an approver.

Keep each selected secret stable across restarts and preserve its association
with its database. Generate fresh secrets when creating a new deployment;
do not generate replacement values every time an existing service restarts.

## Existing installations

If an installation uses a newly rejected value, startup now fails explicitly.
The validator does not modify that installation's keys, permits, audit records,
custody receipts, database, policy or approvals.

Do not replace a key underneath an existing database to silence the error.
Those values authenticate existing state and evidence. Preserve the database
and existing protected configuration, stop consequential operations, and plan
an explicitly authorized migration or new deployment with the operator.
There is no automatic key rotation, state reset, or migration in this change.

Previously launched processes are not changed by this source patch. The check
applies when the updated runtime parses its configuration at startup.

## Tests and proof fixtures

Runtime tests use fresh ephemeral internal secrets. Both container-isolation
workflows and `scripts/prove_provider_route_isolation.sh` generate new internal
fixture keys per proof run instead of embedding known values. Those keys stay
on the trusted test-host/custody side and are not passed to the hostile worker.
Fixture generation is not an operator key-rotation mechanism.

The rejection tests cover every repeated single-byte 32-byte value, short
repeated ASCII/binary patterns, truncated repeats, normalized hex, missing and
malformed values, and longer rejected values. Positive tests cover independently
generated 32-, 48- and 64-byte secrets and stable parsing across restart
configuration. Rejection leaves the intended disposable state path absent and
does not expose the submitted value in the error.

The full custody suite is run by the existing CI and Ubuntu security workflow:

```sh
PYTHONPATH=custody-service/src:. python -B -W error -m unittest discover -s custody-service/tests -v
```

## Security change record

- **Invariant:** known repetitive fixture keys and the documented placeholder
  patterns must not become admitted custody runtime configuration.
- **Authority delta:** admission is narrowed. No new credential capability or
  human signing authority is introduced.
- **Canonical mutation introduced:** none. Configuration rejection precedes
  `build_service`; the patch does not access existing canonical state.
- **Recorded baseline:** at `1035d85010e1615461d24917b52476b094907a90`, parsing
  rejected missing/short secrets but accepted the all-zero and published fixture
  values. No remote authentication bypass was demonstrated.
- **Verified scope:** regression evidence applies to this configuration boundary
  and disposable test/proof fixtures. Existing deployments and the provenance
  of their configured secrets have not been inspected.
- **Legacy disposition:** the existing runtime parser is narrowed; no router,
  executor, ledger, evidence source, or alternate authority plane is imported.
- **Temporal boundary:** compare the same malformed and valid configuration
  cases against the exact recorded main and candidate. No claim of general
  historical transfer is made and no historical authority is changed.

## Adversarial transformation review

| Pass | Result |
| --- | --- |
| Flip | Treat copied examples and operator input as potentially predictable; reject published repetitive fixture patterns. |
| Reverse | Stop before building a kernel/custody service or opening state, rather than discovering an invalid key after effects. |
| Invert | Startup availability is not success if achieved by silently accepting a rejected key or regenerating one. |
| Inside-Out | Apply the same rule to CI and proof launchers; replace their known values without adding a bypass. |
| Darken | A deployment using a known internal secret loses the intended secrecy assumption; no remote bypass or live compromise is asserted. |
| Lighten | A repetitive key in an isolated fixture is not evidence that a real deployment uses it. |
| Amplify | Repeated startup attempts with equivalent decoded bytes stay rejected and leave state absent. |
| Negate | Require protected operator-supplied generated secrets; avoid automatic rotation, canonical state repair, or a second authority path. |

## Recorded validation

At tested source `c74738a1d4a5b8a1c28d9463eadf4eebf9027845` on WSL Ubuntu 26.04.1:

- Core suite: 632 tests PASS, with 2 Windows-only skips.
- Custody suite: 45 tests PASS, including both fields and all 256 repeated-byte values.
- Authority suite: 67 tests, 63 executed PASS, 4 PostgreSQL tests skipped.
- Container build and fake-provider route-isolation proof: PASS with per-run keys.
- Dependency, shell syntax and compilation checks: PASS.

The exact baseline/candidate probe and logs are preserved in
`custody-secret-hardening-evidence/`. The container test used disposable fake
provider resources and did not change any deployed configuration. Later
evidence-only commits leave the tested executable source unchanged.
