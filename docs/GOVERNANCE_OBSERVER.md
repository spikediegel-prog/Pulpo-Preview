# Governance observation: first native increment

Based on resource overview commit `f3a982f0a5eccd65ad043894d34f3c65abe93ac3`.
PR #23 was merged externally as `07f4c4b0c1ef071b7dc5acf69bbb97cee5b7f16f`
while this change was prepared. This increment targets main and preserves the native Tk application.

## Behavior and source

The Governance page presents expandable Policy, Decisions and Audit integrity
rows in the existing charcoal, restrained purple and soft-white palette.
Select snapshot, Re-read and Clear operate only on session presentation.
No source is automatically discovered and selection is not persisted.

The only accepted source is the existing frozen
`pulpo.mcp-read-snapshot.v0` export. Its trusted producer remains
`export_mcp_snapshot(orchestrator, destination)` in `pulpo/mcp_boundary.py`.
The UI reuses `load_mcp_snapshot` with its size/schema/duplicate-key validation,
POSIX private-file checks and Windows read-only handle protections. It never
instantiates a kernel, orchestrator, state backend, executor or authority client.
No export API or canonical schema changes are introduced.

Policy fingerprint, audit count, audit tip and audit-check result are **Recorded**
source reports. Schema acceptance does not authenticate the source. A substituted
valid file cannot turn the view green. Local read time is labeled local read time;
it is not the export time. Deployment identity, export freshness, authenticity and
deployed enforcement remain **Unknown**, including after repeated re-reads.
The source path is displayed locally, without automatic reporting or telemetry.

A source-reported failed audit check is red Attention, not an independent finding.
Unavailable, malformed, oversized, inconsistent or injected snapshots clear prior
values and show Attention with actionable path/schema/permissions guidance.
Errors do not echo raw document contents or exception strings. Empty audits remain
Unknown. Audit records are explicitly not decision counts. Decisions never invent
approvals, denials, permits, execution results or reconciliation stages.

This export has no decision records, policy rules, grants or human-authority
configuration. Those richer displays require a separately reviewed, capability-free
projection of the existing canonical path. No second evidence format, ledger or
governance engine was created to fill that gap. Future decision displays must show
policy denial as Blocked by policy and pending approval as ordinary workflow;
unknown consequences cannot authorize retry.

## Authority and review

Invariant: `NO_WRITE_ROUTE != NO_WRITE_CAPABILITY`; the observer retains only
primitive presentation strings and the selected file path. Authority is unchanged.
Canonical mutations introduced or exposed: **none**. Existing tuning, comparison,
save, undo and export paths retain their APIs. The UI cannot approve, grant,
revoke, retry or execute. Frozen metadata is not a bearer permit or credential.

Eight-pass adversarial transformation review:

| Pass | Boundary and result |
|---|---|
| Flip | Hostile source may substitute valid metadata; never authenticate it or claim enforcement. |
| Reverse | A false governed claim would require promoting a file to authority; no green enforcement path exists. |
| Invert | Passing source audit report remains Recorded, even if selected deliberately by the operator. |
| Inside-Out | UI cannot verify its own source via a self-asserted flag or hash; provenance stays Unknown. |
| Darken | Malformed content clears prior values; arbitrary extra fields are rejected and not echoed. Compromised OS/filesystem availability is outside this check. |
| Lighten | No snapshot or unavailable decision evidence is Unknown, not a claim that governance failed. |
| Amplify | Repeated reads and replayed/substituted snapshots cannot append audit records, create permits or refresh source age. |
| Negate | Reuse the existing frozen public export; no kernel, database, credentials or new exporter needed in the UI. |

Legacy source: existing MCP frozen export/loader and native `StatusRow` presentation.
No authority control path was copied. No reusable organizational lesson or historical
transfer is admitted by this UI change; no temporal replay proof is claimed.

## Validation and limits

See `control-center-evidence/governance/README.md` for commands, platform results,
captures and logs. **Verified** claims are limited to those bounded tests and
rendered layouts. **Recorded** claims describe the selected snapshot. Runtime
deployment governance remains **Unknown**. Production signing, independent audit
root trust, complete history, containment, revocation, screen-reader qualification,
all DPI settings and hostile OS/filesystem races are not established here.

No merge or deployment is part of this change.
