# Preview E1 Linux: bounded scope closure

Date: 2026-10-29. Decision: complete the bounded engineering scope below on the
existing development branch. This is not release, merge, deployment or production
admission. User direction assigns external storage and external-copy integrity
verification to the end user. No new storage integration is required for E1.

## Scope and disposition

| Area | Evidence and disposition |
| --- | --- |
| Linux service security | Recorded earlier hardened system-service proof at `da4913186bcb494cf3a9252bdc36294a9d46b4da`: root-owned staged code/config, dynamic non-root identity, no effective capabilities, no-new-privileges, isolated networking, private state, authority rejection and verified cleanup. Bounded fixture validation complete; no installed production service claimed. |
| Enterprise networking diagnostics/configuration validation | Verified listener parsing, explicit allowlists, private create-only reports, TLS/hostname/CA behavior, proxy/redirect/error handling and key-log denial in bounded fixtures. Recorded current inventory without external probes. No customer network reconfiguration or universal integration claim. |
| Local evidence handling | Verified metadata-only capacity/inode/read-only/path/device uncertainty diagnostics and report failure behavior. Existing bounded public projection remains distinct from the canonical audit. No automatic canonical rotation, deletion or pruning. Operators manage local headroom through the trusted owner path. |
| Restart recovery and canonical integrity | Verified fresh processes and fresh transient user services reopening saved ext4 fixture state, exact prior audit preservation and spent-permit rejection. Supported corrupt/unverifiable state is rejected through existing canonical mechanisms. No change to authority or writers. |

No new implementation blocker was found within this reviewed scope. Closure is
bounded by the tested environment and the exclusions below; it does not convert
unimplemented features or skipped cases into passes.

## Responsibility boundary

End users provision and operate external storage, check the integrity and
completeness of their external copies, maintain access controls/retention/holds,
and perform backups and recovery testing. An external device, cloud bucket,
independent durable receipt or full-audit exporter is not an E1 prerequisite.

Pulpo retains its documented canonical evidence checks, supported fail-closed
behavior, replay protections, local diagnostics and existing export contract.
Customer responsibility does not make a projection a complete archive, suppress
integrity errors or grant permission to remove canonical records. Consumed
permits, unresolved obligations/consequences and tamper evidence remain protected.

The optional archive prototype and VM-to-host synthetic transfer experiment are
retained as exploratory evidence only. They add no canonical acknowledgment or
retention capability and do not establish independent backup durability. The
proposed archival document is not an active implementation roadmap.

## Current verification and historical evidence

Tested checkpoint: `74378f5d90ca3e0ef894a19bd138f788b1118cd7`, clean working
tree before/after verification. Python 3.12.3 in the isolated acceptance runtime.
The closure changes documentation only, after this run.

**Verified:** 83 targeted tests passed, zero skips/failures/errors, with warnings
treated as errors. Modules: `tests.test_network_exposure`, `tests.test_network_e1`,
`tests.test_linux_network_readiness`, `tests.test_storage_pressure`,
`tests.test_service_sandbox_proof`, `tests.test_disk_service_recovery`,
`tests.test_guarded_recovery`, `tests.test_crash_recovery_harness`.
The explicit disposable live user-service proof was enabled; both phases fully
exited, the prior audit prefix matched, replay was denied, and fixtures were
removed. Subsequent system/user enumeration found no `pulpo-e1-*` transient unit.

**Recorded:** the earlier acceptance at
`da4913186bcb494cf3a9252bdc36294a9d46b4da` had 1,055 successes and 59 skips.
Its core/authority/custody log hashes and hardened disk-system-service report
hash were rechecked. Nine critical source hashes (kernel/state/transport,
custody runtime/core and E1 scripts) still match that acceptance. This supports
traceability, not a new execution of the hardened system-service proof or the
full suite. No sudo or production action was performed for closure.

Current VM evidence directory:
`/home/spikediegel/pulpo-e1-evidence-20261028/e1-closure-ede588992610be27`.
Contains `closure-observations.json`, `targeted-tests.log`, a fresh
`disk-user-service-*.json`, `network-inventory.json` and `storage-pressure.json`.
The collector used no external connectivity probe or live database copy.

## Remaining limits, not silently waived

- The earlier 59 skips remain: GUI/platform/Python-version coverage and four
  PostgreSQL cases without a disposable DSN. They are not successful executions.
- Real enterprise proxy rollout, customer CA/certificate lifecycle, routed IPv6,
  VLAN/VPN and external reachability require environment-specific validation.
- Power loss, OS reboot, hardware durability and rollback of an entire older
  valid database were not established. No broader recovery claim is made.
- Automatic quotas/capacity admission and canonical pruning remain absent. Local
  capacity still needs operator management; external ownership cannot eliminate
  this local limitation. Do not use logrotate on canonical SQLite/WAL/audit state.
- Current dependency vulnerability/container/release admission remains separate.
  The preserved original development runtime differs from the acceptance runtime.
- Production services, external archival integrations and end-user infrastructure
  are outside this closure. None was installed or configured.

## Doctrine record

Invariant: `CANONICAL_STATE_MUTATION == GOVERNED_CAPABILITY`. Authority delta:
none. Canonical mutations introduced/exposed: none. This record changes scope
and responsibility language, not code, execution permissions, checks or state.
No second ledger, controller, exporter or signer is added. Control Center stays
an observer; its checkout and the original Preview checkout remain unchanged.

| Pass | Result |
| --- | --- |
| Flip | End-user storage responsibility cannot waive Pulpo's canonical validation. |
| Reverse | Scope closure cannot authorize deletion, release or production mutation. |
| Invert | A closed slice does not mean every enterprise environment passed. |
| Inside-Out | Recheck source/log/report hashes; distinguish observations from admission. |
| Darken | Corrupt state, failed persistence, exhausted/unknown storage and replay remain tested failures, not success by policy. |
| Lighten | Absent external storage is an explicit exclusion, not a core defect or evidence of compromise. |
| Amplify | Repeat restart/replay checks without accumulating test services or widening authority. |
| Negate | Finish the intended Linux work without adding remote storage or another governance surface. |

Existing canonical verifier, owner export contract and E1 fixture/diagnostic
paths are reused unchanged; no legacy authority control path is copied. Exact
historical acceptance is cited above, not promoted to a generally transferable
lesson. No whole-system temporal replay or production-readiness claim is made.
