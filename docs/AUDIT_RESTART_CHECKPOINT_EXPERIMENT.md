# Experimental restart audit verification cache

Base: `preview` at `a8ce8cadde299ea545b9547ac3a93134796774f0`.
Branch: `experiment/restart-audit-checkpoint`. Claim status: Proposed for preview admission.

## Invariant and implementation

A cached chain head alone cannot detect historical payload edits. This change
preserves the canonical `audit` table, chain format, append transactions, replay
guards, permit consumption, approval verification, and forced full
`GovernanceKernel.verify_audit()` behavior.

SQLite bootstrap stores one reconstructible cache row in
`audit_verification_checkpoint`. Its version, verified sequence, chain head,
and SHA-256 of the exact ordered raw SQLite prefix (including sequence and
payload JSON bytes) are bound by HMAC-SHA-256. The HMAC is domain-separated from
permits and uses the existing kernel secret. No key, signing credential, permit,
approval, policy, or authority decision is persisted in the cache.

Every restart reads all raw audit rows and hashes the recorded prefix. A valid
MAC, exact prefix digest, and matching boundary row allow skipping JSON decoding
and per-record chain hashing only for those previously verified bytes. Every
suffix row is decoded and chain-verified. Missing, corrupt, unknown-version,
unauthenticated, truncated, or mismatched cache data invokes the existing full
verifier. Invalid canonical audit data or unavailable cache publication fails
closed through `StateIntegrityError`. Deleting the cache restores full bootstrap
verification and reconstructs it after success.

Validation and publication occur under one `BEGIN IMMEDIATE` snapshot, preventing
concurrent append or historical edit from racing cache publication. An unchanged
validated cache is reused without a write. Ordinary append does not update the
cache or read the audit tip again. A default random kernel secret, or secret
rotation, invalidates the old MAC and safely incurs full verification.

## Authority and mutation boundary

Authority gained: none. Canonical audit/state mutations introduced: none.
The existing canonical SQLite backend creates and updates only disposable
verification metadata during kernel bootstrap. The metadata has no read path
into policy, approvals, directives, permits, or execution decisions. It does not
replace canonical evidence. There is no new router, executor, ledger, human
signing credential, or authority service.

Legacy source: current preview full verifier and `_append_many()` transaction
discipline. No historical control path was copied. Historical commits used by
the existing temporal-transfer regression harness were fetched by exact SHA;
that harness is not evidence that this optimization transfers to those systems.
No applicable historical optimization checkpoint has been identified, so no
general reusable temporal-transfer claim is made.

## Adversarial transformation review

Purpose/outcome: reduce restart verification CPU while detecting changed
historical canonical evidence and retaining the forced full proof path.

- Flip: a hostile cache writer can corrupt or delete metadata; it cannot
  authenticate a changed prefix without the existing secret. Full fallback
  verifies canonical evidence independently of cache assertions.
- Reverse: hidden historical corruption would require bypassing the prefix
  digest or forging the MAC. The prefix is reread, not inferred from its tip.
- Invert: faster startup is not success when an invalid chain is accepted;
  historical/suffix tamper and malformed JSON tests require rejection.
- Inside-Out: the kernel owns the existing permit secret and the canonical
  backend is already trusted code. Cache MAC material is not a human authority
  credential and grants no permit. Compromised kernel code/secret is outside
  the demonstrated integrity boundary.
- Darken: an attacker edits old payloads and recomputes the unkeyed prefix digest
  in the cache; the MAC mismatch forces full verification and rejects the edit.
- Lighten: deletion, key rotation, incompatible schema, or stale sequence may
  be benign; reconstruct through full verification rather than grant trust.
- Amplify: concurrent restart/write is serialized; failed publication rolls
  back; existing replay/rollback/order tests remain required. Scanning and
  serialization still scale linearly with history and payload volume.
- Negate: avoid a new signing key or trusted sidecar. Reuse the existing secret,
  scan exact bytes, and keep the full verifier as the fallback and manual proof.

Continue decision: bounded experimental implementation and adversarial checks
introduce no authority expansion. Smallest next proof: run local regression
suites, record the benchmark, and propose an unmerged PR to preview.

## Evidence and limits

Focused Windows verification: 64 tests passed with `-W error`, including 11 new
checkpoint tests plus persistence, kernel, and parallel-verification suites.
The persistence suites cover approval/nonce/permit replay, failed issuance and
consumption, commit rollback, tip reads, and concurrent append ordering. New
tests exercise cache corruption, schema and MAC mismatch, deletion/key rotation,
historical and boundary-row tampering, a forged unkeyed digest, malformed JSON,
suffix verification/refresh, truncation, forced full verification, failed cache
publication, and bootstrap snapshot overlap with a writer.

Final Linux verification with the repository's pinned service dependencies:
457 core tests passed, 65 authority-service tests completed successfully
(61 passed, 4 optional integrations skipped), and 26 custody-service tests
passed. All suites used `-W error`. Python 3.14.4 also emitted ignored-finalizer
ResourceWarnings for existing unclosed service/test SQLite connections; the
logs preserve these rather than claiming warning-free execution. Compilation
and whitespace checks passed.

Full Windows exploration was not green: candidate 451 tests, 9 failures,
55 errors, 5 skips; unchanged base 440 tests, 6 failures, 55 errors, 5 skips.
The logs include Windows file lifetime, POSIX permissions/path expectations,
Git clean-status checks, and initially unavailable historical fixture failures.
The differing Git clean-status results are not claimed to be identical baseline
failures. Linux final results supersede these for the repository's Linux CI
target; this experiment does not repair Windows portability elsewhere.
Exact historical fixture `0eb1266fecf586c79457e0fcaf412bc6345545a2` was fetched;
its local freeze manifest was restored from Git bytes to avoid Windows CRLF
conversion. No fixture content change is included in the PR.

Benchmark: Windows 11, Python 3.12.14, SQLite 3.53.1; five samples per case, each
in a fresh process and connection. Timed region is kernel bootstrap; imports,
SQLite schema initialization, fixture generation, and an independent forced
full verification after each measurement are excluded. OS disk caches are not
flushed. Complete samples and source digests are in
`perf-results/audit-checkpoint-restart.json`.

| Prefix records | Full bootstrap median | Cached unchanged median | Cached +20 suffix median | Unchanged speedup |
| --- | ---: | ---: | ---: | ---: |
| 1,000 | 7.849 ms | 2.823 ms | 7.734 ms | 2.78x |
| 10,000 | 78.532 ms | 27.112 ms | 43.499 ms | 2.90x |
| 50,000 | 397.923 ms | 125.477 ms | 181.628 ms | 3.17x |

Verified: the recorded local executable tests and benchmark observations.
Recorded: environment, exact base, source hashes, complete logs and timings.
Proposed: admission of this optimization to preview; production benefit is not
claimed from a synthetic benchmark.

Remaining risks/boundaries:

- This remains O(n) I/O and memory; large payload histories incur serialization
  and hashing costs. Prefix digest checks do not deliver O(1) restarts.
- First startup/fallback adds cache construction costs to full verification;
  refreshing after appends adds a metadata write. Small histories may see little
  benefit when a suffix is present.
- Bootstrap takes a SQLite reserved writer lock. Contention/unavailable storage
  can fail closed; no availability improvement is claimed.
- MAC security assumes the existing secret is protected and sufficiently strong.
  No secret storage hardening is added. Default random secrets do not reuse
  checkpoints across independently constructed kernels.
- Whole valid-chain replacement, whole-database rollback, and rollback of replay
  guards are not prevented by the current full verifier either. No external
  monotonic anchor or rollback-resistant storage is introduced.
- Linux CI/production services, cloud integrations, deployed authority, container
  isolation, and physical cold-disk latency require their own evidence.
