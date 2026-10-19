# Native Evidence monitor

Base: `ee33ece` (merged Governance, bounded Ollama proposals and cleanup fix).
The existing Tk application and palette are retained. Evidence collection
tuning remains available behind **Evidence collection settings**; its APIs,
validation, comparison, save and undo behavior are unchanged.

## Display and scope

The top chart separates reads, writes and commits with a charcoal background
and purple, cyan and amber series. Colors identify series; they are not health
scores. The vertical scale is automatic and labeled in calls/second. One-minute,
15-minute and one-hour choices use only collected session observations.

SQLite's canonical owner uses a connection subclass with **ephemeral** counters:

- Reads: completed `Connection.execute(SELECT...)` calls.
- Writes: completed INSERT/UPDATE/DELETE/REPLACE/DDL calls; one completed
  `executemany` batch is one call. A later rollback does not erase that call.
- Commits: successful explicit or connection-context transaction completion,
  including read transactions. A failed commit is not counted as a success.
- Rollbacks and SQL errors: connection-scoped operation counters.

These are not rows, file I/O, fsyncs, committed row changes or fleet totals.
Owner-side audit projection reads are included. Cursor APIs, arbitrary external
connections, savepoint RELEASE, executescript and other processes are outside
these counters; canonical state uses the measured connection methods. SQL text
and parameters are never retained. Counter state is never used by policy,
permits, budgets, audit hashing, execution or reconciliation.

Two different source timestamps are required for a rate. Duplicate observations
add no point. Same-identity substitution or backward time fails the read; a
source-id change starts a fresh history. Missing/decreasing counters and gaps
over 15 seconds produce gaps. History holds at most 1,801 observations. Stale
sources produce Unknown current rates; no flat line is manufactured.

Below the chart:

| Section | Meaning |
|---|---|
| Storage | Main DB and WAL file sizes, free/total capacity on the DB's actual volume. Shared volume use is not all Pulpo evidence. Amber at 85% used; red at 95%. |
| Database health | Owner-reported optional SQLite `quick_check(1)`, scoped to that physical check. Unchecked/unavailable is Unknown. Stale/paused passing checks lose green. |
| Audit integrity | Existing canonical audit verification, source-reported. Separate from physical health; the UI cannot independently verify the redacted projection. |
| Permissions | Source-audit totals for allowed/denied decisions, approval requests, consumed/rejected permits, rejected/expired/replayed approvals. These are not current outstanding permits, pending approvals, active alerts or unique incidents. |
| AI usage | Provider-reported input/output tokens and optional USD micro-cost for the latest completed request. No inferred price, lifetime total or permission budget. |
| Warnings | Staleness, capacity thresholds, failed/unavailable DB check, reported audit failure, historical rejections/errors, large WAL and incomplete AI usage. No automatic cleanup or authority action. |
| Event index | Latest 24 existing canonical record references, timestamp, fixed event/outcome enums and record hash. Filters for decisions, permit events and rejections. No payloads, prompts or bearer permits. |

Policy denials and approval requests are workflow outcomes, not incidents by
themselves. Expired/replayed **approval** counters use explicit canonical reasons.
Permit rejection events do not distinguish expiry/replay, so that breakdown is
Unknown. AI quota/limit alerts remain Unknown without a configured limit source.
A large-WAL hint requires WAL > max(64 MiB, main DB size); it is not a request
to checkpoint or delete files. No warning summary proves deployment all-clear.

**Pause for review** freezes polling while users filter/select/copy event hashes.
Values are marked historical, current rates become Unknown and positive health
loses green. Resume re-reads; missing time stays a gap. Page hiding/minimization
pauses polling, and root destruction cancels the owned timer.
Tk variables have explicit window owners. Destruction releases those variables
and tuning traces on the UI thread and breaks monitor callback cycles, preventing
later worker-thread garbage collection from finalizing Tcl objects.

## Existing trusted owner integration

The UI never opens the database, initializes a backend, obtains an orchestrator,
receives credentials, mints/consumes permits, or checks authority services.
`pulpo.evidence-observation.v1` is a bounded, credential-free projection of the
existing owner and audit, not another ledger or source of authority.

In the **already trusted owning process/thread**, use its existing orchestrator:

```python
from pulpo.evidence_export import export_evidence_observation

# Parent already exists. Integrate into the owner's existing authorized loop.
# No new kernel, backend, signer or authority service is created for monitoring.
export_evidence_observation(
    orchestrator, absolute_snapshot_path,
    check_database=False,  # Optional explicit operator check; potentially costly.
    ai=latest_usage,       # AIUsage or None; never a client, prompt or credential.
)
```

The owning connection must have no active transaction. The exporter reads
existing evidence, optionally checks the DB, and publishes public metadata using
the existing atomic frozen-export primitive. It does not migrate, vacuum,
checkpoint, repair or change canonical DB bytes. Regular exports must be
arranged in the owner's existing execution lifecycle; this change installs no
daemon, listener, background canonical writer or production scheduler.

Select that file in Evidence. The UI re-reads every two seconds while visible.
Owner timestamp >15 seconds old is stale; >5 seconds in the future is rejected.
Re-reading a file does not refresh the deployment. File selection is session-only.
The protected shared loader enforces the existing 16 KiB/private-file/schema
boundary. Unknown/extra fields, malformed data and failed refreshes clear old
values. POSIX nonblocking open prevents a substituted FIFO blocking before
type validation. Existing MCP v0 parsing and export contracts remain unchanged.

Optional Ollama integration preserves `request_local_proposal(prompt, model)`'s
string return. `request_local_proposal_with_usage(prompt, model)` returns the
same validated content plus frozen `AIUsage`. Counts use provider fields
`prompt_eval_count` / `eval_count`; absent or malformed values stay Unknown.
Cost stays Unknown. No extra request, model access, auto retry or authority path
was added. [Official Ollama usage fields](https://github.com/ollama/ollama/blob/main/docs/api/usage.mdx).
Other providers can supply the same primitive report through the trusted owner;
no new provider connector is claimed. No inference was run during visual testing.

Full record investigation remains on the existing trusted canonical audit path:
use the copied record hash to locate the corresponding record there. The UI
neither fetches raw evidence nor provides a second audit database or export.

## Authority and adversarial review

Invariant: `NO_WRITE_ROUTE != NO_WRITE_CAPABILITY`. The transport/UI retains only
immutable public metadata, bounded history and a selected path. The connection
subclass and exporter remain inside the existing canonical owner. Authority is
unchanged. **No new canonical state mutation is introduced or exposed.** The
same existing kernel transitions still control all durable mutations. Export
publication writes only the selected non-authoritative observation artifact.

| Pass | Boundary/result |
|---|---|
| Flip | A hostile valid snapshot can lie about metrics; all reports remain Recorded with unauthenticated provenance and Unknown enforcement. No control action consumes these fields. |
| Reverse | UI-side canonical mutation would need a DB/writer/credential; none crosses the projection. The UI has no DB path auto-discovery. |
| Invert | Failed commits remain failures; a healthy DB cannot turn a failed audit or unverified enforcement green. |
| Inside-Out | Source validity flags, IDs and timestamps cannot authenticate themselves. Quick-check and audit verification are independent reported scopes. |
| Darken | Injected/raw payloads are rejected, errors do not echo contents, private tokens/prompts are excluded at trusted export, large/deep files fail closed. Hostile OS/ACL containment is not claimed. |
| Lighten | Ordinary denial, waiting for approval, rollback and historical rejection are not automatically current incidents. Missing AI usage is not zero. |
| Amplify | Polling is read-only, bounded and pausable; repeated exports preserve canonical bytes/audit. Replays, counter resets, source changes and time gaps cannot fabricate rates. Owner audit projection/quick-check cost still scales with DB size. |
| Negate | Reuse the existing owner, audit, atomic publication, protected reader and StatusRow UI. No extra database opener, signer, router, executor, ledger or authority client. |

Legacy sources: native resource graph styling/StatusRow, existing MCP frozen
publication/reader, SQLite canonical connection operations and Ollama validated
proposal path. No authority control path copied. This change admits no reusable
organizational lesson or temporal-transfer proof; no such historical proof is
claimed. Schema acceptance is not deployment provenance, audit completeness,
backup/recovery evidence, provider billing validation or enforced quota evidence.

Bounded tests/rendering are **Verified**; owner/provider reports are **Recorded**;
production source authenticity and enforcement are **Unknown**. Native captures,
test commands and raw logs are in `control-center-evidence/evidence-monitor/`.
No merge or deployment is part of this change.
