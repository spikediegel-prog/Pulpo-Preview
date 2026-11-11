# Incident-reporting + near-miss channel

WIC *Frontier AI Safety and Governance 2026*, indicator 3.2 (risk incident
reporting and near-miss sharing): only about a quarter of the 24 countries
assessed have stable arrangements here, and Pulpo had none — it recorded the
unknown an incident report would cite, but had no reporting channel and no
near-miss log. This module (`pulpo/incident_channel.py`) is that channel's
first half: the record, derived from outcomes Pulpo already records.

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

Rules:

- One record per source audit event (`incident:<audit-record-hash>` or
  `near-miss:<audit-record-hash>`); one record per custody attempt
  (`incident:custody:<attempt_id>`, the attempt id already being a hash).
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
- Schema: records and reports are now v2 (`pulpo.incident-record.v2`,
  `pulpo.incident-report.v2`): each record carries `lifecycle`,
  `lifecycle_at_ns` (when the current state began; the record's
  `first_seen_ns` when never transitioned) and `lifecycle_actor` (who made
  the latest transition; empty when never transitioned). v1 snapshots are
  not loadable -- the channel is days old and library-only, so no durable
  v1 reports exist.
- `list_incidents` accepts a `lifecycle=` filter alongside `kind=` and
  `resolution=`.

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


## Surfaces (slice (d))

Two read-only surfaces read a frozen `pulpo.incident-report.v2` snapshot
(produced by `export_incident_report`); neither opens a database, appends
to the audit, or offers a lifecycle transition.

### CLI: `pulpo incidents`

- `pulpo incidents list [--report PATH] [--kind incident|near_miss]
  [--resolution ...] [--lifecycle ...] [--since ISO] [--until ISO]` --
  one line per matching record. `--report` defaults to
  `evidence/incident_report.json`; the time window applies to
  `first_seen_ns`, as in `list_incidents`.
- `pulpo incidents show [--report PATH] <record_id>` -- full record
  detail (source, reason, resolution, lifecycle with actor, anchors).
- `pulpo incidents summary [--report PATH]` -- counts from the report
  header (incidents, near-misses, unresolved, resolved cleanly,
  confirmed wrong) plus audit validity.
- Exit codes follow the existing CLI: 0 on success; a missing or invalid
  report, an unknown record id, or a bad `--since`/`--until` is a
  `ValueError` and exits through `parser.error`, as `pulpo verify` and
  `pulpo setup` already do. An empty report lists zero records, not an
  error.

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
this slice.

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
store, and the `_publish_snapshot` frozen-file boundary — no schema change
on either side.

## Open questions

- Human report path: who reads the frozen report, and what (if anything)
  is sent where? Nothing in this module answers that.
- Human report path: who reads the frozen report, and what (if anything)
  is sent where? Nothing in this module answers that. (The CLI and the
  Evidence page are the local reading surfaces; sending is still open.)
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
