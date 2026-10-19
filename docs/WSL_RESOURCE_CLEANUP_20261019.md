# WSL resource cleanup repair — 2026-10-19

## Problem and resulting behavior

At exact parent commit `6e260e2551e4b7fc12ee30e8f2e88e4792ae43b0`,
the core suite exited zero while Python 3.14 reported three ignored finalizer
warnings: one rejected GitHub HTTP response and two SQLite test connections.

The GitHub metadata reader now closes a raised `HTTPError`, whose response is
not returned by urllib. Redirect rejection and sanitized error reporting stay
in force, including if closing the rejected response also raises. No response
body is read on this failure path and no retry is introduced.

The legacy proposal upgrade fixture now explicitly closes both raw SQLite
connections while retaining its transaction contexts. This is a test-fixture
repair; no production database migration or state semantics changed.

`scripts/run_unit_tests.py` now fails when a resource warning or other ignored
finalizer exception reaches `sys.unraisablehook` during discovery, execution,
or the final explicit collection. It retains only exception type names and
restores the caller's hook. Core CI invokes this gate. It does not guarantee
detection of resources kept reachable until interpreter shutdown or otherwise
prevented from finalizing.

## Authority and canonical state

Product authority is unchanged. No policy, permit, signing key, canonical writer,
ledger, execution route, or state mutation is introduced. The only product
change releases a failed metadata response. CI admission is stricter.

## Verified local evidence

- Ubuntu 26.04.1 LTS, WSL 2, Python 3.14.4, SQLite 3.46.1.
- Before repair: independent cleanup harness observes exactly three unraisable
  ResourceWarnings and exits 1 despite ordinary unittest reporting success.
- Two new HTTP cleanup regressions fail against the original reader and pass
  after repair. They cover no body read, prompt close, and sanitized close failure.
- Focused regressions: 21/21 pass.
- Disabling the new gate's unraisable exit check is caught by two regressions.
- Full core gate: 744 tests, 742 passed, 2 Windows-only skips, no failures,
  errors, or ResourceWarnings. WSLg covers the desktop tests.
- Custody service: 47/47 passed, no ResourceWarnings.
- Docker 29.1.3: existing hostile-worker route isolation proof passes on a new
  test image. Custody is nonroot with read-only root filesystem; the worker has
  no custody volume, Docker socket, or provider/governance secrets. Custody
  reaches the synthetic provider while worker DNS and raw-IP routes are denied.
- All three test containers, two internal networks, and one disposable volume
  are independently verified absent after cleanup. No user/group/socket
  permissions were changed; trusted-host Docker administration used WSL root.

## Eight-pass analytical review

- Flip: hostile error contents stay sanitized; the rejected body is not read.
- Reverse: release the rejected response at the reader's existing failure path.
- Invert: an otherwise green suite becomes failure on observed finalizer errors.
- Inside-Out: local tests and self-recorded logs are not independent certification.
- Darken: secondary close failure remains denial without exposing provider text.
- Lighten: the SQLite issue is confined to fixture ownership, not demonstrated
  production data loss or an audit-integrity bypass.
- Amplify: repeatable core/service suites and deliberate gate weakening verify
  detection without changing product authority or retrying provider effects.
- Negate: no broad Docker permission grant or real provider/model is needed.

## Boundaries and uncertainty

Claims above are Verified only for the recorded source and test environment.
Docker evidence covers the exact disposable topology, not a hostile host admin,
all deployment layouts, or production containment. No live model, registrar,
payment, production database, Cloud SQL/KMS, or independent certification was
tested. Windows validation is deferred. The CI workflow uses Python 3.11; the
SQLite finalizer-negative fixture naturally skips before Python 3.13. No claim
of historical transfer beyond the exact-parent before/after controls is made.

The external Docker wrapper's final metadata read initially hit Git ownership
protection after the proof and fixture cleanup succeeded. Independent read-only
verification recovered the metadata; the wrapper now scopes safe.directory to
that single Git invocation. No global Git trust changes were made.
