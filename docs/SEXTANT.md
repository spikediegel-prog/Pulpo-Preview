# Sextant

Status: **Recorded implementation; workload metrics Unknown**. The neutral
Control Center page is named **Sextant**. The name is presentation-only; the
page remains a read-only workload signal view.

## What is shown

The page provides a read-only, at-a-glance place for workload accuracy and
calibrated drift, an observation list/detail pane, source freshness, refresh
controls, and a 24-hour/week/month evidence-count navigator. With current
repository data, the accuracy and drift readings remain **Unknown**, the
workload observation list remains empty, and the histogram has no bars.

The existing `pulpo.evidence-observation.v1` snapshot is the only related
observation source currently integrated with this Control Center. It reports
database/authorization aggregates and up to 24 redacted, general Pulpo event
references. It does not carry workload identity or version, model version,
reviewed known-correct outcomes, an eligible accuracy denominator, a workload
distribution, a comparable baseline, a calibrated threshold, checkpoints, or
workload-linked evidence counts. General governance events are therefore not
relabelled as workload events, and aggregate database/audit counts are not used
to populate the workload histogram.

## Existing checkpoint and audit sources

The canonical audit source is `SQLiteKernelState.audit` in `pulpo/state.py`.
Records have a sequence, event, payload, timestamp, previous hash, and SHA-256
record hash. `GovernanceKernel.verify_audit()` verifies the canonical chain.
`pulpo.evidence_export.freeze_evidence_observation()` projects fixed event
names, outcomes, record hashes, aggregate counters, and at most the latest 24
references into `pulpo.evidence-observation.v1`; it does not export raw payloads
or a workload identity. `pulpo.verifier.audit_checks()` explicitly leaves event
completeness unverifiable because it has no independent event source.

Two other uses of “checkpoint” are not workload evaluations:

- `audit_verification_checkpoint` is local SQLite bootstrap cache metadata.
  `SQLiteKernelState.verify_audit_bootstrap()` checks its HMAC using the existing
  kernel secret, re-reads the raw audit prefix, and falls back to full chain
  verification when the cache is invalid. The cache optimizes verification; it
  is not an external evidence attestation or workload checkpoint.
- Historical checkpoints in repository experiments are exact Git commits used
  for replay/comparison. They do not identify a deployed workload evaluation,
  model version, correctness label, or baseline.

The current UI's trusted-owner snapshot reader still validates the
`pulpo.evidence-observation.v1` envelope and schema, but source IDs, timestamps,
audit-valid flags, event hashes, and reported counters are not an authenticated
deployment identity or independent completeness proof. The unkeyed audit
record hashes support chain checking at the canonical verifier; transported
hash strings alone do not prove source authenticity. No existing source joins
workload samples to reviewed outcomes, versioned calibration, a workload
checkpoint, or an independently complete workload event stream.

### Owner projection boundary

No owner-side workload projection is added in this increment. Inspection found
no existing governed workload-event producer, reviewed correctness record, or
calibration approval source to project. Reusing the existing audit exporter
would yield only generic governance events; creating new audit event types or
review labels here would introduce canonical state mutation and an unsupported
authority/evidence path. Sextant therefore has no source of truthful workload
records yet. This is a **Recorded blocker**, not evidence that no workload
events exist outside the inspected repository paths.

## Offline Sextant v1 observation and replay contract

`pulpo.sextant_observation` defines the pure data model
`pulpo.sextant-observation.v1`, a strict dictionary parser, and a deterministic
offline replay. Its top-level fields are exactly `schema`, `source_id`,
`observed_at_ns`, `first_sequence`, `event_count`, `calibration`, and `events`.
A calibration is versioned and scoped to a workload and numeric metric; it
records baseline workload/model versions, baseline sample count/mean/sample
standard deviation, an investigate-only standardized-delta threshold, and
opaque checkpoint/evidence references. Each event records its contiguous
sequence and timestamp, workload and model versions, metric value, optional
reviewed-correct Boolean, checkpoint reference, and evidence record-hash
reference. Batches are bounded to 16 events to fit the existing protected
snapshot reader's 16 KiB file limit, and the reader enforces that serialized
byte bound independently; one current workload/model cohort is allowed. The
explicit event count catches count mismatch; sequence continuity catches gaps
and reordering inside the declared batch. Unknown fields, malformed values,
timestamp reordering, and mixed scopes are rejected.

This parser validates shape and ordering, not provenance or truth. References
are locators only, and `source_id` is a producer-supplied label; the contract
does not verify the referenced checkpoint, evidence record, calibration
process, or human review. Sequence continuity detects gaps within a declared
batch, not omitted events before/after that window. A valid-field content
substitution is not detectable by this contract. There is no signature, MAC,
transport identity, or `p3_verified` field. Carrying the JSON over P³ (or any
other transport) does not authenticate it and cannot upgrade a `Recorded`
report to `Verified`. The model is not connected to the Control Center, a file
watcher, the owner exporter, a database, service, or transport; all current
workload UI values remain **Unknown**. `load_sextant_observation(path)` reuses
the existing protected frozen-file reader (regular file, size cap, duplicate
JSON-key rejection, and platform-specific path/permission protections) and
then applies this strict schema. File protection does not authenticate whoever
produced the content.

`SextantReplayGuard` detects duplicate, overlapping, and gapped batches for one
source during one in-memory viewing session. Its cursor is disposable UI
bookkeeping, not a durable replay ledger; it resets on process/session change
and cannot stop a producer from changing its self-reported source ID.
`freshness()` classifies the producer-supplied observation timestamp as recent,
stale, or clock-mismatched. It does not authenticate the clock. Incomplete
counts and in-window gaps are rejected, but omitted events outside the declared
batch remain undetectable without an independently trusted completeness source.
Tests deliberately demonstrate that a structurally valid substituted metric
value is accepted: the current contract has no authenticator capable of
detecting that substitution.

### Metric semantics

- **Accuracy:** only events with `reviewed_correct` explicitly set to a Boolean
  enter the denominator. The numerator is `True`; `False` is a reviewed
  incorrect outcome. `None` is unreviewed and excluded, never treated as
  incorrect or correct. Replay reports reviewed count, correct count, point
  estimate, and a Wilson 95% interval. The interval quantifies binomial sampling
  uncertainty only under the usual representative/independent-sample
  assumptions; it does not establish label quality, source authenticity, or
  population accuracy. The contract records the review assertion but cannot
  independently establish that an outcome is known-correct.
- **Drift:** replay compares one batch's numeric metric to the explicitly
  versioned calibration baseline for the same workload and metric. It reports
  observed and baseline counts/means, combined standard error
  `sqrt(baseline_sd^2 / baseline_n + observed_sample_variance / observed_n)`,
  and standardized mean delta. This uncertainty estimate assumes independent,
  comparable samples measured in the same units; those assumptions are not
  validated by the contract. A configured absolute standardized delta at or
  above the threshold is labeled **Investigate**; otherwise it is **Below
  investigate threshold**. Fewer than two current samples yield **Unknown**.
  If the combined standard error is zero, the standardized score and status
  remain **Unknown** rather than dividing by zero or inventing a threshold
  result. This descriptive threshold is not a p-value, correctness assessment,
  cryptographic check, causal explanation, or automatic action. Calibration is
  reported, not authorized or verified, by this contract.

The offline fixture tests exercise a controlled synthetic shift and ensure
missing/reordered/corrupted batches fail closed, stale/future timestamps are
distinguished, and the ephemeral cursor rejects replays/overlaps/gaps. These
tests validate parser and arithmetic behavior only; synthetic events are not
production evidence.

Accuracy is not computed without reviewed outcomes known to be correct and a
defined evaluated sample. Drift is not computed without workload/model versions,
a comparable baseline, and an explicitly calibrated threshold. The page shows
the missing detail categories as Unknown rather than zero. Correlation or
statistical change would be a signal to investigate, not proof of cause;
statistical measures do not establish correctness or cryptographic verification.

## Refresh, timeline, and source boundaries

Refresh cadence is configurable as Off, 30 seconds, 1 minute, or 5 minutes.
Pause stops automatic refresh; manual refresh remains available. When a
general Evidence observation is selected, refresh reuses `EvidencePage.refresh`
and its existing strict snapshot loader. It never opens a database or introduces
a workload source reader. The cadence therefore refreshes only that selected
general observation; it does not collect workload data.

“Display last refreshed locally” is a local UI refresh time, not the timestamp
of a workload measurement. Separately, the available general evidence
observation reports its own source timestamp and existing freshness
classification. A stale general evidence snapshot does not imply stale workload
metrics: workload metrics are unavailable, and workload-source freshness is
Unknown.

The bottom navigator changes the displayed period among 24 hours, Week, and
Month. In this increment, all periods show the empty state because no
workload-scoped event counts are available. If such a source is integrated in a
future governed change, bars are reserved for evidence counts, not accuracy or
drift values. The event/detail area is similarly empty instead of displaying
unrelated general audit references as workload activity.

## Required change record

1. **Invariant/failure addressed:** workload metrics and investigations must
   not be fabricated from unrelated evidence. Statistical changes, accuracy,
   cryptographic verification, and causal explanations remain distinct claims.
2. **Authority delta:** unchanged. The page owns no kernel, orchestrator,
   executor, canonical state backend, signer, credential, service client, or
   mutation method. It adds no route or capability.
3. **Canonical state:** no canonical state mutation was introduced or exposed.
   The page reads the immutable `EvidencePage` selection through its existing
   strict reader; manual and scheduled refresh reuse that existing read path.
   The existing evidence exporter remains in its trusted owner and is not
   invoked here.
4. **Success/adversarial evidence:** `python -W error -m unittest tests.test_sextant_observation tests.test_control_center tests.test_audit_checkpoint tests.test_evidence_observation -v`
   verifies Unknown accuracy/drift, no fabricated workload rows when a generic
   decision reference is present, explicit baseline limitations, period
   selection, disabled cadence, refresh through the existing reader, controlled
   synthetic drift and baseline-like behavior, uncertainty and sample counts,
   version and evidence-reference reporting, and rejection of missing,
   reordered, incomplete, malformed-reference, and non-finite metric events,
   plus stale timestamps and replay-guard behavior. It also confirms a valid
   shape-preserving content substitution is not authenticated. The UI test
   checks the empty state remains empty with a generic reference. Result:
   **75 tests run; all non-skipped tests passed, with 16 environment-specific
   skips** on this Windows host.
5. **Evidence boundary:** tests do not establish a production workload feed,
   reviewed correctness labels, a valid metric definition, calibrated
   thresholds, causality, source authenticity, cryptographic verification,
   deployment enforcement, accessibility qualification, or workload history.
   The offline replay contract is not wired into the visible metric cards, and
   no owner-side workload projection exists without an existing governed source.
6. **Claim classification:** the UI behavior and test assertions are
   **Verified** at the tested commit; the selected general source's values and
   timestamps are source-reported **Recorded** values; the absence of a
   workload-specific feed in the inspected repository contract is **Recorded**;
   production accuracy, drift, causes, and workload-source freshness are
   **Unknown**. No inference is presented as a verified outcome.
7. **Legacy behavior:** reuses the native Control Center navigation, theme,
   existing Evidence snapshot model, freshness classifier, and Evidence read
   path. No legacy control path is copied into a new source, router, executor,
   ledger, audit system, or authority plane.
8. **Temporal transfer:** no reusable lesson is admitted and no historical
   replay is claimed or used.

## Eight-pass adversarial transformation review

| Pass | Result |
|---|---|
| Flip | If the parser/UI or source is misleading, it cannot authenticate a workload identity, establish a correctness label, or change canonical state. Source-supplied calibration and evidence references remain Recorded assertions. |
| Reverse | A false accuracy/drift claim would require reviewed outcomes, identity, and baselines absent from the production source. The offline contract supplies a strict shape only; the UI still leaves both metrics Unknown. |
| Invert | A threshold crossing is only an investigation signal. Hash-shaped references, a valid parser result, and a useful-looking graph do not establish chain verification, event completeness, or metric correctness. |
| Inside-Out | The presentation cannot self-validate or create its own evidence. The offline parser has no writer/authority objects and is not connected to the canonical verifier or UI feed. |
| Darken | Threat case: a transported producer substitutes well-formed values, omits events, or replays plausible evidence references. Shape checks cannot detect a valid-field substitution or omission outside the declared sequence window; no authenticated production feed or Verified label is claimed. |
| Lighten | No workload feed may simply not have been connected; this is not evidence that workloads failed, drifted, or were correct. The page displays Unknown rather than a failure score. |
| Amplify | UI refresh remains bounded to the selected existing snapshot. Offline event batches are bounded to 1,024, require contiguous in-window sequences, and reject mixed cohorts; they do not prove completeness beyond that batch. |
| Negate | No live feed, database reader, scheduler, or authority capability is added. A pure strict contract plus synthetic replay tests establish the next safe semantic increment while production stays Unknown. |

This review is analytical only. Adding a workload source, metric semantics,
baseline approval, or evidence promotion requires its own authorized design,
strict source contract, tests, and adversarial review. This page grants none.
