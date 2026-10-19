# Activity: bounded observation and investigation

**Recorded implementation; enforcement remains Unknown.** Activity extends the
existing native Control Center in place. Its two views answer different questions:

- **Local session:** what this window observed about its own operations.
- **Evidence references:** which redacted canonical references the currently
  selected Evidence observation supplies (maximum 24), not a complete history.

## Operator display

The session monitor plots retained local event counts per wall-clock minute for
the last ten minutes. It does not estimate traffic, fleet totals, throughput or
canonical event rates. Minutes before the session began remain gaps. Counts can
be incomplete after the retention bound; the number of dropped entries is shown.
Purple/amber/red distinguish Info/Warning/Error with corresponding text labels.

The newest-first feed filters time, category, outcome, severity and search.
System, Evidence, Governance, Connections and AI are category choices; unavailable
connection/AI event sources produce no invented entries. Local messages, System
benchmark start/completion/failure/cancellation, performance setting save/restore,
legacy Evidence fixture operations, exports and Evidence read-state transitions
have structured metadata. Progress ticks do not flood the event feed.

Selection expands a readonly detail pane and a related-page action. A navigation
badge counts new local events while Activity is hidden or paused; visiting the
live page clears that badge, independent of local review status. The attention
summary counts unreviewed retained local warnings/errors and separately explains
an invalid/stale Evidence observation. It is not an active incident count.
Historical denials, policy blocks and permit rejections remain outcomes in the
reference view; they are not automatically classified as operational errors.

Mark reviewed locally changes only ephemeral UI bookkeeping. It does not change
the recorded outcome, acknowledge a canonical incident, authorize retry, grant
approval or resolve unknown consequences. Cancelled benchmarks are informational.

Pause display freezes rows, chart and source snapshot. New local events still
enter the bounded session buffer and update the new-event badge. Filters/refresh
are disabled until resume. Copy/export uses the frozen rows, not later arrivals.
Source references use only the existing immutable snapshot already held by
Evidence. Activity does not independently read files, open a database, poll a
service or refresh a hidden Evidence page. Return to Evidence to re-read its
selected source. Repeated display refreshes replace this index, rather than
appending duplicate references. Source freshness is reported; provenance and
deployment enforcement are not established by a recent timestamp.

## Privacy, limits and lifecycle

The session buffer retains at most 500 events with at most 8192 characters of
free-form local detail per event. Display controls are removed from that text.
The existing `append(message)` entry point remains a generic local diagnostic
message; it cannot promote text into trusted categories or a Verified claim.

Local diagnostic text can contain paths or sensitive details. Copy safe reference
exports only allowlisted metadata for a local event, or a record hash for a source
reference. Preview safe export opens a readonly, scrollable view of the exact JSON
to be saved. A later Save as writes that frozen document to the operator-selected
destination; closing/cancelling the preview does not write anything. Every
free-form message, path, command, prompt and error body is omitted, rather than
depending on a secret-detection regex. Structured exports may include public
source/record hashes; the preview states the coverage limits. No reporting or
upload occurs automatically.

The views are cleared on exit. No new durable activity database or audit journal
is created. Active-page refresh uses a one-second UI timer, skips hidden/minimized
rendering, and performs no new source I/O. Page changes and destruction cancel
timers. Tk variables are owned and released by the UI thread; workers emit only
primitive queue messages through the existing operation paths.

## Required change record

1. **Invariant/failure:** free-form session output was difficult to investigate;
   local activity must not become a second audit authority or fabricate complete
   event coverage. Unreviewed warnings must not be mistaken for active incidents.
2. **Authority delta:** unchanged. No kernel, canonical writer/state backend,
   orchestrator, executor, signer, credential, service client or permission API is
   retained by the Activity model/page. `NO_WRITE_ROUTE != NO_WRITE_CAPABILITY`.
3. **Canonical mutations:** none introduced or exposed. Local review/filter/pause
   affects UI memory only. Explicit export writes a selected non-authoritative
   report. Existing checked performance-setting APIs and canonical boundaries
   remain unchanged.
4. **Evidence:** [native review and regression artifacts](control-center-evidence/activity/README.md).
   Tests cover retention, malformed metadata, filtering, cancel/failure outcomes,
   frozen export/cancel, text omission, review semantics, stale/invalid source,
   duplicate-free references, absence of Activity source reads and existing
   System/Evidence operations. Artifacts bind the implementation by source hashes.
5. **Limits:** no complete audit history, correlated per-action authority proof,
   service/AI request stream, production volume, incident resolution or governance
   enforcement is established. Native screen-reader qualification and frozen
   application packaging are outside this increment's evidence.
6. **Classification:** session actions/tests are Recorded, timing/health
   interpretations retain their original scope, source references are
   source-reported Recorded values, enforcement/provenance remain Unknown.
7. **Legacy source:** reuse `ControlCenter.append`, existing operation queues,
   Evidence's immutable parsed observation, native navigation and existing
   performance APIs. No copied kernel control path, new provider route, router,
   executor, ledger or authority plane.
8. **Temporal transfer:** no reusable organizational lesson is admitted; no
   temporal-transfer claim. The native before screenshot observes base
   `2f09d6e1e112ea011202e0c63f3185efe5250b83` before editing. It is presentation
   evidence, not replay of historical authority, approvals or credentials.

## Eight-pass review

| Pass | Result |
| --- | --- |
| Flip | Malformed local metadata is rejected; free-form text cannot choose an action/category/severity. Source events still pass the existing strict Evidence contract. No canonical writer is held. |
| Reverse | False history/incident assurance is stopped at coverage labels, separate source views, retention counts and preserved original outcomes. Local review cannot resolve canonical state. |
| Invert | Successful fixture work remains a local result. An allowed decision, consumed permit or copied reference does not establish execution or enforcement. |
| Inside-Out | Session display, local review and exported JSON are not independent canonical audit sources or self-issued authority. |
| Darken | Threat case: verbose/sensitive errors or repeated events fill the UI. Bound count/text, omit all free-form export text, disclose dropped entries and preserve source validation failures. |
| Lighten | A policy block may be expected enforcement behavior; rejection is not automatically an incident. An empty bounded index is not absence of events. |
| Amplify | Bound session memory and the 24-reference index; repeated refresh replaces references. Paused retention loss is visible after resume, with no retry or remote polling loop. |
| Negate | Reuse existing primitive queues and parsed observations. No daemon, database connection, canonical mutation interface or UI rewrite is necessary. |

Continue within these presentation boundaries. Unknown consequential outcomes
never authorize retry. Adding a future event source requires its own strict
observation contract and review; category/filter presence does not create it.
