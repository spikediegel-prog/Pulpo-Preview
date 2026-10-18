# Security patch history: external authority boundaries, 2026-10-18

## Change and classification

**Verified:** two synthetic regression characterizations make external-control
limits executable. This change adds tests and evidence; production behavior and
canonical authority remain unchanged.

- A denied provider-write intent does not prevent an isolated Python child with
  a synthetic token and loopback route from reaching a fake provider.
- A preissued canonical permit is rejected after directive revocation and SQLite
  restart, while the separately held synthetic provider token remains usable.

Both fixtures reject missing credentials (HTTP 403), verify the positive control,
and verify that off-path provider I/O adds no canonical audit records even though
the existing chain remains valid. No shell, real token, remote provider or live
consequential effect is used. The child receives only synthetic input through
stdin and a small environment without ambient credential variables.

Passing these characterizations establishes the stated limits; it does not
establish external containment. Production network isolation, provider credential
custody and provider-side token revocation remain deployment responsibilities.
See [agent network boundaries](AGENT_NETWORK_AND_DISCLOSURE_BOUNDARIES.md).

## Exact source and validation

Base commit: `ef314e313f264281acbb7df3d44573a85598d726`.
The source fixture's full Git tree matched the GitHub base tree
`ffcb18259718cfd0b87285d15e3d2cdc359adf70` before the new test was added.
This verifies clean-main content rather than relying on the earlier dirty local
checkout's test results. The fixture was reconstructed from the exact local
ancestor plus GitHub's compare/file data because direct WSL cloning stalled.
Every changed blob and the complete resulting tree SHA were checked.

New test SHA-256: `972ad4ffca50031afdbe4209bd2ec0b8e99d88a789e65afe8455f1b6d7cd5475`.
Platform: `Linux-6.18.33.2-microsoft-standard-WSL2-x86_64-with-glibc2.43`. WSL Python 3.14.4, with the repository's
reviewed Ubuntu constraints and dependency inventory from the preceding audit.
Exact commands, environment overrides, counts and raw-log hashes are recorded in
[summary.json](2026-10-18/external-authority-boundaries/summary.json).
The [regression transcript](2026-10-18/external-authority-boundaries/regression-summary.log)
includes both new results and every skip.

Run from the repository root with its authority and custody dependencies installed:

```bash
export PYTHONPATH="$PWD:$PWD/custody-service/src:$PWD/authority-service/src"
export PYTHONDONTWRITEBYTECODE=1
python -B -X utf8 -W error -m unittest discover -s tests -v
python -B -X utf8 -W error -m unittest discover -s custody-service/tests -v
python -B -X utf8 -W error -m unittest discover -s authority-service/tests -v
```

Results: core 644 tests (2 Windows-only skips), custody 45 tests (no skips),
authority 67 tests (4 PostgreSQL skips because no test DSN is configured).
750 passed, 6 skipped, no failures. Windows remediation and live PostgreSQL
integration are outside this verification.

## Authority, reconciliation and evidence limits

Authority delta: none. Production canonical state mutations introduced or exposed:
none. Fixture transitions use only the existing kernel, directive controller and
disposable SQLite state. No second executor, ledger, observer authority or token
revocation mechanism is introduced. Existing test helpers are reused without
importing a legacy control path.

Earlier local inspection verified revocation/replay/tunnel and HTTPS-hardening
commit ancestry, and current GitHub main already includes the hardening through
PR #17. This PR does not republish unrelated local changes or claim new runtime
fixes. Historical checkpoints exist; cross-checkpoint temporal transfer was not
performed. These are bounded current-source fixtures, not generally admitted
organizational lessons.

**Unknown:** production containment, real provider token revocation, off-path
audit completeness, PostgreSQL integration, Windows behavior and all possible
execution interleavings. No production compromise or forged permit is asserted.

## Eight-pass review

| Pass | Finding and disposition |
| --- | --- |
| Flip | A hostile child can ignore wrappers; characterize that route explicitly. |
| Reverse | Prevent usable provider credentials and unauthorized network routes from reaching workers. |
| Invert | Fake-provider acceptance is ungoverned I/O, not authorized success. |
| Inside-Out | A valid canonical audit does not attest off-path effects. |
| Darken | Persistent external tokens could enable repeated effects; this is a synthetic threat case. |
| Lighten | Canonical permits remain denied after revocation/restart; no permit forgery is shown. |
| Amplify | Reusing a provider token spans revocation; one-use permits cannot revoke it. |
| Negate | Preserve the existing kernel and require external custody/containment, without adding another execution path. |

Continue decision: synthetic loopback tests and evidence only. No real credential
duplication, production provider route or production state mutation occurs.

## Governance security fixes — 2026-10-18

Added atomic in-memory replay handling, strict cost validation, custody execution
deadline checks, policy/configured-issuer/approval-lifetime permit bindings, and
persistent authenticated ownership of approval requests. See
[the fix and migration record](GOVERNANCE_FIXES_20261018.md) and
[PR validation evidence](2026-10-18/governance-fixes/summary.json).
## Upstream security repair follow-up — 2026-10-18

**Verified, bounded WSL evidence:** applied focused renewal binding/reconciliation from upstream #312; permit lifetime from #278; isolated audit calculation workers from draft #302; strict disposable PostgreSQL CI gate from draft #315. Preserved Preview's signed-handle, issuer, locking and audit integrity repairs. No second authority plane. See [UPSTREAM_FIXES_20261018.md](UPSTREAM_FIXES_20261018.md) for exact commands, upstream heads, compatibility effects and eight-pass review.

Final suites: 682 core (680 passed, 2 Windows-only skips), 47 custody passed, 70 authority passed against rootless PostgreSQL 18.6 with no skips. Total 797 passed / 2 skipped. PostgreSQL server stopped. Existing mutation checks: 19/19 killed; zero invalid/surviving. New expiry regression fails on the exact starting tree and passes after the change. Failed intermediate runs are retained and excluded. CI PostgreSQL 16 and deployed services remain unverified.

Exact log SHA-256 evidence:

- `acceptance-core.log`: `273cb31a8cf6598809973bcf168a1655daafaa8122b976a01e4c7a3978487bc4`
- `final-custody.log`: `9b489d965e5c2e91af23666d6655325ea8f77fa77c23075b2474ee788c01d785`
- `authority-postgres.log`: `d901cf22f0697f2106c41bd4a2ba7fbb6955971b2c7db9b35f5d50ed6dd1fab1`
- `constitutional.json`: `8dd82ddf268390d8f6e8dd43cc620efb6e15654ce5f9af4bb49ca8d9d64b24b3`
- `baseline-expiry-negative.log`: `7899d7110a3a6370dcf2ca60de23519d32f76875dc1dd87d33bcb7d61f4bea86`

## PR #20 bundled-runtime calibration repair — 2026-10-18

**Verified, bounded WSL:** frozen executables now retain strict coordinator audit verification without relaunching the application as a Python worker. Bundled calibration records one effective worker. Two new regressions reproduce the old failure and pass after repair; 684 core (two Windows-only skips), 47 custody and 70 live disposable PostgreSQL tests pass: 799 passed / 2 skipped. Source-worker failures still fail closed; no authority or canonical mutation path was added. The original hosted PostgreSQL 16.15 job passed; actual Windows executable acceptance of this follow-up awaits the hosted rerun. See [the follow-up record](UPSTREAM_FIXES_20261018.md#bundled-runtime-follow-up-for-pr-20) and [commands/hash evidence](2026-10-18/upstream-fixes/frozen-runtime-summary.json).
