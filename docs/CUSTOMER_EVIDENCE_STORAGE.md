# Customer evidence storage and data handling

Status: Recorded implementation boundaries; Proposed appliance sizing and future integrations.

## Responsibilities

Scope decision, 2026-10-29: external storage, external copies' integrity
verification, backup/restore operations, retention and legal holds belong to the
end user. They are excluded from Preview E1 acceptance. Pulpo does not provision
or certify an external archive or require an external-storage integration to
complete this bounded Linux slice. See `E1_SCOPE_CLOSURE_20261029.md`.

Pulpo retains responsibility for its documented canonical evidence validation
and rejection of supported corrupt/unverifiable state. Delegating external
storage operations does not disable these checks or authorize canonical deletion.

Pulpo is responsible for its documented evidence generation, bounded local
observation history, integrity checks and supported export behavior. It is not
an indefinite archive or NAS. Customers are responsible for provisioning and
operating long-term evidence storage, retention obligations, access controls,
backups, tested recovery and legal holds. The customer must decide what records
their obligations require; a dashboard export alone may not satisfy them.

Local retention has two distinct meanings. Control Center keeps bounded session
observations and reads bounded public projections. The canonical audit currently
has **no automatic size/time retention, archival acknowledgment or safe pruning
API**. It grows until operator capacity management intervenes. This policy does
not add one, or promise indefinite local capacity. Monitor capacity and stop
admitting workload before exhaustion through the existing governed owner path.
No automatic capacity admission controller is added by this change.

## Match the customer's infrastructure

| Choice | Available behavior | Boundary |
| --- | --- | --- |
| Local filesystem | Existing explicit owner publication of sanitized JSON projections to a private absolute file path | Manual handoff; not a complete historical archive |
| Mounted NAS: SMB/NFS | Same file publication contract, conditional on an already mounted filesystem satisfying private ownership, non-symlink path, atomic replacement and directory synchronization requirements | Customer mounts, secures and validates it; mount failure or incompatible semantics is failure/unknown, not success |
| SAN-backed filesystem | Same conditional file publication contract on an already provisioned filesystem | Pulpo does not manage SAN block devices, mounts or redundancy |
| SIEM/syslog | Not implemented; outside E1 | No selectable forwarding integration or delivery guarantee |
| S3-compatible object storage | Not implemented; outside E1 | No selectable S3 integration, credentials or Object Lock configuration |
| Hybrid local buffer plus remote archive | Customer can manually handle existing public exports; automated delivery is outside E1 | No durable transfer queue, retry/receipt protocol, full-audit archive or pruning |

These filesystem choices describe a deployment of the same implemented file
exporter, not separately certified NAS/SAN integrations. A storage plan in
**System → Session setup** records a choice, planned public-export destination
and explicit acknowledgment in the existing private preferences file. It never
opens the destination, verifies its connection, installs a timer or transfers a
file. Changing the choice/path clears acknowledgment. Unacknowledged, unsupported
or malformed plans cannot be saved. Old setups without a plan still load. The
acknowledgment is revision-bound local metadata, not human authorization or a
compliance attestation. Remember/forget affects preferences only. Paths may reveal
personal information; do not include credentials or share preferences as evidence.

## Existing evidence architecture and export contract

Pulpo-Preview's existing `GovernanceKernel` / `SQLiteKernelState` owns the canonical
audit, hash chain/head and enforcement-critical state. Custody convergence projects
pending custody obligations into that same audit; its outbox is not another ledger.
Control Center remains an observer with no canonical writer, router or exporter.

Only the existing owner may call `pulpo.mcp_boundary.export_mcp_snapshot` or
`pulpo.evidence_export.export_evidence_observation` at the existing safe boundary.
Their public schemas remain `pulpo.mcp-read-snapshot.v0` and
`pulpo.evidence-observation.v1`. The latter includes counters and **at most 24
recent sanitized events**, not all audit payloads. Repeated publication replaces
the previous snapshot. Customers needing historical observations must preserve
separate copies themselves, with provenance and access controls. These copies
remain projections, not a second canonical ledger or a full forensic archive.

Do not copy/export a live state database, raw audit payloads, permits, signing
material or credentials through this handoff. The separate authority-service
reference has a Google Cloud locked-bucket sink; that service-specific adapter
does not implement generic kernel archival, S3 or a Control Center integration.

Integrity verification detects supported tampering; it does not prove external
durability, complete-database rollback resistance, customer backup quality or
legal compliance. Preserve original classifications, timestamps and hashes.
Do not promote Recorded/Unknown observations into Verified enforcement.

## Export failure and capacity

Publication failure must surface through the existing error path. A directory
sync failure after replacement means commit unknown, not a proven remote receipt.
Never delete evidence on failed/unknown export. A successful projection write
also grants no permission to delete canonical audit or state. Preserve replay
guards, consumed approvals/permits, directives, unresolved consequences, custody
obligations and tamper evidence regardless of archive preference or retention age.
This change adds no deletion, database rotation, truncation, vacuum, relocation,
new ledger, background uploader or enforcement bypass. A customer legal hold
must be maintained in their archival process; automated legal-hold enforcement
and full-audit archive verification remain unimplemented.

## Planned appliance capacity (Proposed; not an implemented quota)

The following are historical, nonbinding sizing examples, not E1 requirements,
committed product settings or obligations to implement archival/pruning.

Initial design target: a 256 GB SSD, a 32 GiB operational evidence budget and a
64 GiB configurable local evidence ceiling per appliance. Reserve separate room
for OS, upgrades/recovery, database growth and protected enforcement state. These
are engineering starting points, not measured workload guarantees or existing
settings. Do not apply a filesystem quota that prevents required canonical writes.

Size from measured total persisted bytes per day (including SQLite/WAL/index
overhead) × maximum archive outage days × safety factor, plus protected state
and recovery headroom. At 1 GiB/day, 32 GiB gives 16 days with a 2× allowance;
at 10 GiB/day it gives 1.6 days. Benchmark normal and burst workloads before
admitting an appliance specification. Existing volume warnings at 85%/95% are
shared-volume observations, not evidence-quota enforcement. Safe bounded
canonical retention needs a separately reviewed archive/receipt/pruning design.
