# Incident-reporting + near-miss channel

WIC *Frontier AI Safety and Governance 2026*, indicator 3.2 (risk incident
reporting and near-miss sharing): only about a quarter of the 24 countries
assessed have stable arrangements here, and Pulpo had none — it recorded the
unknown an incident report would cite, but had no reporting channel and no
near-miss log. This module (`pulpo/incident_channel.py`) is that channel's
first half: the record, derived from outcomes Pulpo already records.
Slice (e) adds the second half: a person can file a report of their own
(see Human report path, below) -- a claim, in their words, about an
effect they say happened.

It reports to nobody by itself. There is no external reporting, no sharing,
no notification, no network call. A human — or a later, separately governed
step — reads the frozen report and decides what leaves the machine.

## Definitions

- **Incident**: a consequential effect that was executed, or may have been
  executed, whose outcome is unknown or wrong.
- **Near-miss**: a governed action refused or caught before any consequential
  effect, OR an unknown that later resolved cleanly. No effect happened, or
  the effect is verified fine.

Both are derived, read-only projections of the canonical audit chain and the
custody store. An incident record also carries a handling lifecycle -- open,
acknowledged, resolved, closed -- recorded as `incident_lifecycle` audit
events (see Lifecycle, below). Near-misses carry no lifecycle
(`not_applicable`).

## Feed table

| Source | Source detail | Kind | Resolution | Anchor | Integrity |
|---|---|---|---|---|---|
| canonical audit | `purchase_consequence_unknown` | incident | unresolved | audit record hash | hash chain (`verify_audit`) |
| canonical audit | `purchase_consequence_unknown` + custody attempt `reconciled_success` | near-miss | resolved_cleanly | audit record hash + custody authorization hash | hash chain + HMAC receipt |
| canonical audit | `purchase_consequence_unknown` + custody attempt `reconciled_failure` | incident | confirmed_wrong | audit record hash + custody authorization hash | hash chain + HMAC receipt |
| canonical audit | `purchase_consequence_unknown` + custody attempt in any other state | incident | unresolved | audit record hash + custody authorization hash | hash chain + HMAC receipt |
| canonical audit | `purchase_revalidation_failed` | near-miss | not_applicable | audit record hash | hash chain |
| canonical audit | `purchase_revalidation_failed` + custody attempt (by attempt id, else order hash) | near-miss | not_applicable | audit record hash + custody authorization hash | hash chain + HMAC receipt |
| canonical audit | `permit_rejected` | near-miss | not_applicable | audit record hash | hash chain |
| canonical audit | `decision` with outcome `deny` | near-miss | not_applicable | audit record hash | hash chain |
| canonical audit | `approval_rejected` | near-miss | not_applicable | audit record hash | hash chain |
| custody store | attempt `unresolved` | incident | unresolved | attempt authorization hash | HMAC-signed transition receipts |
| custody store | attempt `reconciliation_required` | incident | unresolved | attempt authorization hash | HMAC-signed transition receipts |
| custody store | attempt `attempt_authorized` / `attempt_claimed` / `request_transmitted` (latest state, no later state) | incident | unresolved | attempt authorization hash | HMAC-signed transition receipts |
| custody store | attempt `reconciled_failure` | incident | confirmed_wrong | attempt authorization hash | HMAC-signed transition receipts |
| custody store | attempt `reconciled_success` | — (no record) | — | — | resolver only |
| human report | `human_incident_report` | incident | unresolved | audit record hash | hash chain (claim, not evidence) |
| human report | `human_incident_report` | near-miss | not_applicable | audit record hash | hash chain (claim, not evidence) |

Rules:

- One record per source audit event (`incident:<audit-record-hash>` or
  `near-miss:<audit-record-hash>`); one record per custody attempt
  (`incident:custody:<attempt_id>`, the attempt id already being a hash);
  one record per `human_incident_report` event
  (`incident:<audit-record-hash>` or `near-miss:<audit-record-hash>`).
- Merge: when a custody attempt has a `purchase_consequence_unknown` audit
  event carrying its `custody_attempt_id`, exactly one record is emitted,
  anchored on the audit event, with resolution taken from the attempt's
  latest state. A `purchase_revalidation_failed` event consumes its attempt
  the same way -- by `custody_attempt_id` when the payload carries one,
  else by `order_hash` (the attempt object hash IS the order hash) -- so a
  refusal yields exactly one near-miss, anchored on the audit event and
  the custody authorization. An attempt with no such audit event gets its
  own custody-anchored record. A `reconciled_success` attempt with no audit
  event referencing it emits nothing.
- Records sort by (`first_seen_ns`, `record_id`). There is no cap on
  records: incidents are rare, and silently dropping one would be worse
  than a large report.
- Only hashes cross into a record as anchors — never authority material.
  The permit itself never appears; only its hash, exactly as the canonical
  audit already records it.
- `freeze_incident_report` is read-only: it appends nothing to the audit
  and writes nothing to the custody store. With `custody=None` the feed is
  audit-only; custody resolution of an unknown needs the store passed in.

## Integrity levels

A record's anchor is only as strong as its source, and every record carries
its `source` so a reader can tell which anchor backs it:

- **Audit-derived** records are anchored by the audit record hash and the
  hash chain. The report carries `audit_valid` from `kernel.verify_audit()`
  and derives regardless, flagging a broken chain rather than hiding it.
- **Custody-derived** records are anchored by the attempt authorization hash
  and the HMAC-signed transition receipts. They are **not** hash-chained to
  the canonical audit. Do not present custody-derived records as
  audit-backed.
- **Human-reported** records are anchored by the audit record hash of the
  `human_incident_report` event and the hash chain -- the anchor proves
  the claim was filed, when it was filed, and by whom as recorded. It
  proves nothing about whether what the claim says is true. A human
  report is a claim, not evidence: never present it as a verified outcome.

Custody transitions reach the canonical audit wherever an evidence
projector is wired: `DomainCommerceExecutor` takes an `evidence_projector`
and, when supplied, projects every transition
(`SQLiteCustodyEvidenceConvergence.project_all`) into `custody_transition`
audit events -- authorize, claim, transmit, require-reconciliation,
reconcile. The `TrustedDomainExecutor`'s projector is still only wired in
tests. The custody feed therefore still reads the custody store directly
(`SQLiteGovernanceCustody.attempts()`, a read-only SELECT-only enumeration),
and the channel says so on every record via its `source` field.

## Custody time is a bound, not a timestamp

The custody store records **no per-attempt timestamp**.
`created_epoch` / `updated_epoch` are head-epoch counters (1, 2, 3, ...),
not seconds, so there is no epoch-to-nanosecond conversion to apply;
converting one would fabricate a time. A custody-sourced record instead
carries the store head's `custody_time_ns` at freeze time as both
`first_seen_ns` and `last_seen_ns`: the time of the store's latest
transition, an upper bound on the attempt's last transition, not the
attempt's own time. A merged record keeps the audit timestamp as
`first_seen_ns` and takes `last_seen_ns` as the later of the audit
timestamp and the custody head time.

## Lifecycle

An incident record carries a handling lifecycle, derived from the canonical
audit -- never stored beside the record. Every transition is an
`incident_lifecycle` audit event, so the current state is replayable from
the chain: who did what, when.

| Transition | From | To | Rule |
|---|---|---|---|
| `acknowledge` | `open` | `acknowledged` | -- |
| `resolve` | `acknowledged` | `resolved` | -- |
| `close` | `resolved` | `closed` | If the record's resolution is still `unresolved`, a reason is required and the event is recorded as an explicit override (`override: true`). |
| `reopen` | `resolved`, `closed` | `open` | -- |

Rules:

- The transition API is library-level:
  `transition_incident(orchestrator, record_id, transition, *, actor,
  reason=None, custody=None)`. `actor` is an explicit attribution string,
  conventionally `operator:<name>` for a human or `process:<name>` for
  automation; it is recorded, not authenticated -- there is no credential
  check here.
- Lifecycle is handling status only. Acknowledging, resolving, or closing a
  record changes how it is reported, never what the kernel, the custody
  coordinator, or any permit will do.
- Near-misses carry lifecycle `not_applicable` and accept no transitions:
  refused before any effect, or an unknown that resolved cleanly, there is
  nothing to work.
- Closing an incident whose resolution is still `unresolved` is allowed
  only with a reason, recorded as an override. The alternative -- refusing
  the close -- would leave a permanently unknown outcome open forever; the
  override makes the decision visible instead of pretending the outcome was
  resolved. A failed append raises: unlike the purchase-outcome record,
  which is best-effort so a failed projection never masks the outcome the
  caller must reconcile, a lifecycle transition is an explicit operator
  action, and silent failure would leave the operator believing the
  incident is closed when it is not.
- Reopening a closed incident is always possible: a wrongly-closed incident
  is itself a governance failure, and the reopen is audit-visible.
- Derivation: `freeze_incident_report` folds `incident_lifecycle` events in
  audit order, applying only transitions valid from the record's current
  derived state. An event for an unknown record id, for a near-miss, or
  with a from_state that does not match is ignored -- it stays in the audit
  as history but cannot corrupt the derived state.
- A kind flip retires the incident record and its lifecycle: an unknown
  that later resolves cleanly becomes a near-miss (`not_applicable`) under
  a new record id, and the earlier lifecycle events remain in the audit as
  history. A custody-anchored record that reconciles to success vanishes
  the same way.
- Schema: records and reports are now v3 (`pulpo.incident-record.v3`,
  `pulpo.incident-report.v3`): each record carries `lifecycle`,
  `lifecycle_at_ns` (when the current state began; the record's
  `first_seen_ns` when never transitioned) and `lifecycle_actor` (who made
  the latest transition; empty when never transitioned), plus the human
  fields `claimed_at_ns` (the time the reporter says the incident
  happened; 0 on machine-derived records) and `reporter` (who filed the
  claim; empty on machine-derived records). v2 snapshots still load: the
  loader fills both fields with their defaults and normalises the schema
  to v3. v1 snapshots are not loadable -- the channel is days old and
  library-only, so no durable v1 reports exist.
- `list_incidents` accepts a `lifecycle=` filter alongside `kind=` and
  `resolution=`, and a `source=` filter (`canonical_audit`,
  `custody_store`, `human_report`).

## Human report path (slice (e))

A person files a report of their own -- the channel's second half. The
rules are the point of the slice, so they are stated plainly:

- **A human report is a claim, not evidence.** It records what a person
  says happened, in their words. It never alters, reclassifies, or
  overwrites a machine-derived record. It may reference machine record
  ids; it never rewrites them. Filing a report that references a machine
  incident leaves that incident exactly as it was -- same kind, same
  resolution, same lifecycle -- and transitioning the human record
  (acknowledge, resolve, close, reopen) touches only the human record.
- **The claim enters the same channel.** Filing appends a
  `human_incident_report` audit event carrying the envelope
  (`pulpo.incident-human-report.v1`: kind, reporter, description,
  claimed time, related record ids) and the derivation converts it into
  an IncidentRecord with source `human_report`, exactly like a machine
  feed. The record enters the same lifecycle (open for an incident,
  `not_applicable` for a near-miss) and the same audit trail: every
  transition is an `incident_lifecycle` audit event, and a failed append
  raises -- filing is an explicit operator action, and silent failure
  would leave the operator believing the report was filed when it was
  not.
- **The reporter is attribution, not authentication.** The reporter is
  recorded as given, conventionally `operator:<name>`; there is no
  credential check, and the record never claims the reporter was
  authenticated. The same holds for the actor on every lifecycle
  transition.
- **The claimed time is recorded as claimed.** `claimed_at_ns` is the
  time the reporter says the incident happened. It is a claim, not a
  trusted timestamp: it is recorded as given even if it is in the past,
  the distant past, or the future. The record's `first_seen_ns` is when
  the claim was filed, never the claimed time. A claimed time is never
  used to order, backdate, or re-time anything.
- **Related records are references, not links of authority.** Related
  record ids must name records in the current frozen report at filing
  time; they are carried as `related_record` anchors (hashes only, the
  hash embedded in each related record id) and in the audit payload. A
  related record that later vanishes (a kind flip, a custody resolution)
  does not invalidate the human record: the reference stays in the audit
  as history.
- **A malformed human event is not projected.** Derivation validates the
  envelope strictly (schema, kind, non-empty description and reporter,
  positive claimed time, related ids a list of strings). An event that
  fails validation produces no record -- the claim stays in the audit as
  history, but an untrustworthy payload must not become a record. The
  filing function is the only writer and it validates, so a malformed
  event means tampering or a bug.
- **Filing is a library call and a CLI command.**
  `file_human_incident_report(orchestrator, *, kind, reporter,
  description, claimed_at_ns, related_record_ids=(), custody=None)`
  returns the derived record. `pulpo incidents report --state PATH --kind
  ... --reporter ... --description ... --claimed-at ISO [--related ...]`
  is the CLI form (see Surfaces). There is no filing form on the
  Evidence page: the page is read-only over frozen reports and has no
  live orchestrator, so filing there would break the page's contract.
  There is no external reporting, no regulator notification, no sharing:
  the frozen report is read locally, and sending is still open.

## What the channel does not do

- No authorization, no permits, no keys. Freezing a report grants nothing.
- No external reporting or sharing, no network calls, no notification.
- No mismatch feed beyond custody `reconciled_failure`: `reconcile_effects`
  (`pulpo/effect_reconcile.py`) runs only from scripts/proofs/tests, never
  from the live path, and its results are never persisted. There is no
  durable mismatch feed to derive from. If effect-reconciliation results
  become durable, they belong here as a third feed.
- No external reporting or sharing (see Surfaces, below, for what reads
  the frozen report locally).
- No custody-transition projection into the audit on the
  `TrustedDomainExecutor` path: its projector is still only wired in tests,
  so worker-driven attempts are visible here only because the channel reads
  the store directly. The live commerce path does project (see above).
- No filing form on the Evidence page: the page is read-only over frozen
  reports and has no live orchestrator. Filing is a library call and a
  CLI command (see Human report path, above); putting a write form on a
  read-only page would break the page's contract.


## Surfaces (slice (d))

Two read-only surfaces read a frozen `pulpo.incident-report.v3` snapshot
(produced by `export_incident_report`); neither opens a database, appends
to the audit, or offers a lifecycle transition. Slice (e) adds one write
surface, `pulpo incidents report`, described under the CLI below.

### CLI: `pulpo incidents`

- `pulpo incidents list [--report PATH] [--kind incident|near_miss]
  [--resolution ...] [--lifecycle ...] [--source canonical_audit|custody_store|human_report]
  [--since ISO] [--until ISO]` --
  one line per matching record. `--report` defaults to
  `evidence/incident_report.json`; the time window applies to
  `first_seen_ns`, as in `list_incidents`.
- `pulpo incidents show [--report PATH] <record_id>` -- full record
  detail (source, reason, resolution, lifecycle with actor, anchors).
  For a human-reported record it also prints the reporter and the
  claimed time, labelled as reported, not verified.
- `pulpo incidents summary [--report PATH]` -- counts from the report
  header (incidents, near-misses, unresolved, resolved cleanly,
  confirmed wrong) plus audit validity.
- `pulpo incidents report --state PATH --kind incident|near_miss
  --reporter operator:<name> --description TEXT --claimed-at ISO
  [--related RECORD_ID ...]` -- files a human report into the canonical
  audit and prints the new record id. This is the channel's first write
  surface: it opens the state file the operator points at (`--state`
  has no default -- there is no canonical deployment layout to guess
  at -- and a missing file, or a file that is not a Pulpo kernel state,
  is refused, never created). The kernel is constructed with a
  throwaway read-only policy: filing appends through the direct state
  seam, as `transition_incident` does, not through a governed action,
  so the policy is not consulted; the audit chain hash is unkeyed
  SHA-256, so the constructed kernel appends validly. The reporter is
  recorded as given, not authenticated.
- Exit codes follow the existing CLI: 0 on success; a missing or invalid
  report, an unknown record id, or a bad `--since`/`--until` is a
  `ValueError` and exits through `parser.error`, as `pulpo verify` and
  `pulpo setup` already do. An empty report lists zero records, not an
  error. A failed filing (bad kind, reporter, description, claimed time,
  or an unknown related record id) is likewise a `ValueError` and exits
  the same way.

### Control Center Evidence page (Tkinter)

An "Incidents" section on the existing Evidence page, in the
`EvidenceEvents` pattern: the operator selects a frozen incident-report
file ("Select incident report…"), the page re-reads it on its 2-second
visible tick, and a Treeview lists records with kind / resolution /
lifecycle filters, a counts summary, row details, and a copy-record-id
button. Read-only: no transition, acknowledgement, or authority action
is offered, and the section keeps its own source state -- incident reads
are not registered in the center's source-health registry, whose keys
are (`Governance`, `Evidence`, providers).

The Qt Control Center lives in a separate repo (this repo's Control
Center is Tkinter); the Qt Evidence page is a follow-on there, not in
this slice. Neither page offers filing: both are read-only over frozen
reports, and filing is a CLI/library action (see Human report path,
above).

## The live path now reconciles (incident-reconciliation slice)

The live commerce path drives the custody lifecycle on the coordinator
path (`pulpo/commerce.py`, `DomainCommerceExecutor`):

- **Success**: claim + transmit around the executor's own provider call,
  require-reconciliation once it returns, then `reconciled_success` from
  the executor's own observation -- complete payment evidence with settled
  budget plus complete delivery evidence. The channel emits no record: a
  successful coordinator purchase is no longer an unresolved incident.
  The observation is first-party (`pulpo.commerce.live`), not independent:
  it records what the provider synchronously returned to the trusted
  in-process executor, under the schema
  `pulpo.live-purchase-observation.v0`. It must never be mistaken for the
  independent observation `IndependentDomainReconciler` requires.
- **Known failure**: the provider returns a charge outside the authorized
  amount (or a negative charge) -- `reconciled_failure` on the provider's
  own return, matching the independent reconciler's
  `observed_charge_exceeded_authorization` failure. The channel reports
  one incident, `confirmed_wrong`.
- **Unknown**: the provider call raises, or returns incomplete evidence --
  the attempt stays `reconciliation_required` (never `attempt_authorized`,
  which no reconciler accepts), and the channel reports one unresolved
  incident, open for later independent reconciliation.
- **Refusal**: a purchase refused at revalidation never claims or
  transmits. The refusal event carries the attempt id and the channel
  consumes the attempt into exactly one near-miss. The attempt itself
  stays `attempt_authorized` in the store: the custody vocabulary has no
  cancel/refuse transition, so the channel consumes it rather than the
  store resolving it. A cancel transition is still an open vocabulary
  decision (see below).

The claim/transmit steps are not fabrication: the transmission they record
IS this executor's own provider call, under its own id
(`domain:<attempt_id>:live`) -- not a worker handoff that never happened.
Driving claim/transmit for a purchase handed to a worker would be
fabrication, and the live path does not do that.

## Two consequences to know about

1. **A refused attempt still dangles in the store.** The channel consumes
   it, so the report is clean, but the custody store still holds an
   `attempt_authorized` attempt that can never execute (its permit is spent
   and its reservation attempted). Only a cancel/refuse transition in the
   custody vocabulary would resolve the store state; that is a decision for
   Mike/Austin, not taken here.
2. **Unknown custody states fail closed toward reporting.** An attempt in a
   state the channel does not recognise is reported as an unresolved
   incident, never silently dropped.

## Porting note

Slice 4's evidence modules (`evidence_observation`, `evidence_export`) do
not exist upstream, and neither does this channel. Porting it upstream
costs porting `evidence_observation` / `evidence_export` plus this module
(and the `attempts()` read-only enumeration on the custody store). The
channel itself depends only on the canonical audit columns, the custody
store, and the `_publish_snapshot` frozen-file boundary. Slice (e) moves
the record to v3 (`claimed_at_ns` and `reporter` on the record); a port
of the v2 channel needs those two fields carried over to stay in step,
and v2 snapshots load into v3 with both fields defaulted.

## Open questions

- Human report path: the CLI and the library file reports locally, and
  the frozen report is the local reading surface. What (if anything) is
  sent where is still open -- nothing in this module answers that.
- Evidence-projector wiring on the `TrustedDomainExecutor` path, so
  worker-driven custody transitions reach the canonical audit too (the live
  commerce path already projects when a projector is wired). Constructing
  `SQLiteCustodyEvidenceConvergence` against a production store also needs
  an owner: whoever constructs it must wire its `project_all` as the
  executor's projector, or the convergence trigger blocks the coordinator
  path by design.
- A cancel/refuse transition in the custody vocabulary, so a refused
  attempt reaches a terminal state in the store instead of lingering as
  `attempt_authorized` (the channel already consumes it; only the store
  state is open).
