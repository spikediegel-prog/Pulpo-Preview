# E1 storage-pressure diagnostics

Classification: Verified bounded diagnostic/test behavior; Recorded host capacity.
Parent checkpoint: b6408929426eba5ff106488c7626e57c4141582d. No production
admission, archival, retention or pruning capability is added.

## Invariant/failure addressed

The existing public evidence projection and Control Center show shared-volume
space warnings. They do not provide an explicit operator check for inode
exhaustion, filesystem read-only flags, minimum headroom, wrong storage device
or a missing/replaced directory. A missing target must not silently fall back
to a healthy parent filesystem, and unknown capacity must not become zero or
healthy evidence. Capacity observations must never authorize audit deletion.

Add scripts/check_storage_pressure.py as an explicit metadata-only CLI. It
opens existing directories through descriptor-relative walks, rejecting links
in every component. It reads fstat/statvfs metadata and re-walks the path after
collection to detect directory replacement or a new parent symlink. It never
enumerates files, opens a database, reads file contents, creates a target
directory, probes a write, checkpoints, vacuums or rotates canonical state.
All descriptors are closed. The observation is point-in-time, not a guarantee
that a path/mount remains unchanged after collection.

## Operator contract

From the Preview checkout:

    python -m scripts.check_storage_pressure --path /home/spikediegel/pulpo-e1-evidence-20261028

The target must be an existing absolute directory with no symlink component.
--expected-device MAJOR:MINOR optionally pins an independently selected device
expectation. A mismatch returns Unknown and no capacity numbers. It detects a
common wrong-device/fallback case; device equality does not authenticate a
mount, export, remote store or customer-approved storage identity. Without a
trusted expectation the report remains capacity-only. Missing/private targets
are Unknown; the tool neither creates them nor escalates to inspect them.

Byte observations distinguish allocated bytes, free reserved space and space
available to non-privileged processes. Pressure percentages use unavailable
space, including reserved free blocks, so they may differ from df's displayed
used percentage. Inodes have an independent available-count pressure check.
Missing, invalid, zero-total or unsupported/sentinel accounting is Unknown.
Known byte exhaustion remains Critical even if inode accounting is unknown.

Defaults are 85% warning and 95% critical unavailable capacity, matching the
existing review thresholds as an operational convention, not appliance sizing.
--min-free-bytes and --min-free-inodes optionally require explicit remaining
headroom. Both default to zero: this does not promise that remaining capacity is
sufficient for a workload. Zero available capacity is Critical regardless.
Read-only filesystem flags are Critical. Directory write access, per-user
quotas and actual write success remain unassessed; no write probe is performed.

The schema is pulpo.storage-pressure.v1. Status is ok, warning, critical or
unknown. Exit 0 means the current capacity observation met the selected limits;
exit 1 indicates warning/critical; exit 2 indicates unknown, invalid input or
report-publication failure. None is a permit or deployment/enforcement result.
The report always marks enforcement not_assessed, mount/export identity
not_verified, quota enforcement not_implemented and canonical pruning unavailable.

--evidence NEW_ABSOLUTE_FILE reuses the existing private create-only diagnostic
publisher. Prior reports and links are preserved. Disk-full/sync/publication
failure is visible and cannot emit successful publication stdout. Diagnostic
output can share the full filesystem, so persistence is not guaranteed; use
the explicit stderr/exit result and existing trusted operational channels. The
CLI itself installs no monitor, uploader, timer, repair or admission controller.

## Verified tests and actual observations

45 tests ran: 44 passed, one existing graphical Tk test skipped. There are 17
new storage-pressure tests. They cover threshold boundaries, reserved blocks,
byte/inode minimums, exhausted inodes with free bytes, read-only flags, invalid
accounting, unsupported inode data, missing/file/symlink paths, device mismatch,
permission/stat errors, directory replacement, same-target parent-symlink
substitution, unsafe arguments, private create-only publication and simulated
ENOSPC. The existing publication and storage-plan tests also pass.

Existing crash/recovery oracle and guarded-recovery tests pass, including real
SQLite FULL/BUSY/trigger failures in disposable fixture databases and supported
replay, stale/corrupt state and tamper cases. Those tests use bounded database
limits/fault fixtures; the personal VM's filesystem was never deliberately
filled and no real inode exhaustion, remount or quota change was attempted.

Recorded live sample on the VM's existing diagnostic directory: device 252:0,
about 33.7 GiB available to non-privileged processes, about 3.78 million free
inodes, 43.63% unavailable byte capacity including reserved blocks, 5.49%
unavailable inodes, no read-only flag, selected pressure state ok. This observes
the shared root filesystem; it is not a measurement of Pulpo evidence usage or
a running governance service's private data directory.

Two actual CLI negative cases also pass without allocating test data:
--min-free-bytes 1000000000000 reports Critical/exit 1 because the selected
counterfactual reserve exceeds actual free space; --expected-device 0:0 reports
Unknown/exit 2 with the actual observed 252:0 and no fallback byte values.
These are policy/identity fixture cases, not an actual shortage or missing NAS.
Reports, final tests, source hashes and exact commit patch are retained locally.

## Authority, canonical mutations and retention boundaries

Authority delta: none. Canonical state mutations introduced/exposed: none.
No kernel, writer, signer, executor or new canonical ledger is retained by this
CLI. Only explicitly requested publication writes an independent diagnostic
report. The schema is not added to a governance attestation or Control Center
authority path. Existing public export schemas, UI settings and storage-plan
acknowledgment behavior remain unchanged.

No audit, WAL, replay guard, consumed permit, pending consequence, custody
obligation or tamper record is deleted or altered. No real database contents
are read. No automatic quotas, workload stop, live-database export, logrotate,
truncate, archive receipt or canonical pruning route is introduced. The existing
CUSTOMER_EVIDENCE_STORAGE.md boundaries remain authoritative. Failed or Unknown
publication must never permit deletion. An operator responds through the
existing trusted owner path; this observation does not grant that authority.

## Eight-pass review and temporal boundary

- Flip: malformed/unreadable metadata or wrong devices cannot become healthy
  capacity observations; the report has no canonical write capability.
- Reverse: validate limits/path and reject a device mismatch before accepting
  capacity; re-walk before publishing the snapshot.
- Invert: free space is not evidence-quota compliance, write success, authority,
  archive durability or permission to delete canonical records.
- Inside-Out: test the diagnostic's accounting, path race handling and its own
  inability to publish under storage failure.
- Darken: zero headroom, inode exhaustion, read-only flags, malformed accounting,
  path substitution and ENOSPC remain explicit Critical/Unknown/error outcomes.
- Lighten: another application may consume shared capacity; an unimplemented
  inode counter or missing mount does not establish evidence corruption.
- Amplify: repeated checks remain metadata-only; prior reports are create-only.
  Report accumulation is not a safe canonical-retention mechanism.
- Negate: no disk filling, privileged mount/quota change, live-state inspection,
  second admission controller or automatic deletion is needed for this slice.

Legacy source: existing volume-warning thresholds and private diagnostic
publisher, plus existing failure-test harnesses; no legacy control path copied.
The exact parent has volume observations but no descriptor-bound pressure CLI.
There is no relevant historical implementation checkpoint for this new CLI;
no whole-system temporal replay or general organizational-learning proof is
claimed. Existing canonical authority/replay rules are unchanged by testing.

Remaining Unknown/Proposed: customer quota behavior, remote/NAS/SAN semantics,
archive acknowledgment, safe canonical retention/pruning, pressure-driven
admission through the canonical owner, sustained workload sizing, real whole
filesystem exhaustion and hardware durability. No production-readiness claim,
push, merge, publication, production change or OS storage reconfiguration is
part of this work. Original uncommitted changes remain preserved.
