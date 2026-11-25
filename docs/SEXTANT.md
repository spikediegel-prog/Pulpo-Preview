# Sextant

Status: **Recorded implementation; workload metrics Unknown**. The neutral
Control Center page is named **Sextant**. The name is presentation-only; the
page remains a read-only workload signal view.

## Synthetic proof of concept

Select **Run synthetic demo** to populate the page with ten deterministic,
in-memory samples and run them through the same bounded replay calculations as
the offline contract. The generated sequence includes a baseline-like period
and a later latency shift, so the drift card can show an investigation signal;
synthetic outcome labels populate the accuracy example. The shared metrics
panel centers each value over its matching deviation graph. The graphs use a
fixed center reference and symmetric outside rails whose distance from center
represents the absolute deviation. The latency center is its calibrated
synthetic baseline; the accuracy center is a synthetic 95% target. Annotations
give signed direction and amount: latency percentage from baseline or accuracy
percentage-point difference from target. The lower histogram separately counts
generated events over the selected period. Select a row for its generated metric
and label.
**Clear demo** restores the ordinary
Unknown/empty state and zero-position placeholders.

This is a presentation and calculation demo, not an executed workload:
no service, model, inference, or external provider is run, and the generated
latencies, correctness labels, hashes, and checkpoint references are not
observations or evidence. The demo is explicitly labeled **SIMULATION ONLY**,
exists only in memory until cleared or the window closes, does not call the
general evidence reader, and performs no file writes or canonical Pulpo state
mutations. Freshness is not measured for generated timestamps. It does not
change the production-source boundary described below.

## Synthetic scenarios loaded from JSON

The Select workload observation control also accepts the separately versioned
`pulpo.sextant-synthetic-scenario.v1` envelope for replayable demonstrations.
It contains a scenario name, an illustrative accuracy target from 0 to 100
percent, and one ordinary `pulpo.sextant-observation.v1` document. Sextant
validates both layers through its protected frozen-file reader, labels the
scenario **SIMULATION ONLY**, and shows the supplied target on the accuracy
deviation graph. The target is demonstration metadata; it does not change the
ordinary observation schema, represent a production target, or establish that
any workload ran. Ordinary observation JSON still has no accuracy-target
field, so its accuracy remains an absolute 0–100 percent reading.

## What is shown

The page provides a read-only, at-a-glance place for workload accuracy and
calibrated drift, an observation list/detail pane, source freshness, refresh
controls, and a 24-hour/week/month evidence-count navigator. With current
repository data and no synthetic scenario selected, the accuracy and drift
readings remain **Unknown**, the workload observation list remains empty, and
the histogram has no bars.

The existing `pulpo.evidence-observation.v1` snapshot is the only production
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
report to `Verified`. The model is not connected to a production Control Center
source, file watcher, owner exporter, database, service, or transport. The
separately labeled local synthetic scenario uses this model for demonstration
only. `load_sextant_observation(path)` reuses
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
production evidence. The UI's opt-in scenario shows those calculations with
generated values and remains visibly marked **SIMULATION ONLY**.

Production accuracy is not computed without reviewed outcomes known to be
correct and a defined evaluated sample. Production drift is not computed
without workload/model versions, a comparable baseline, and an explicitly
calibrated threshold. The demo's generated-label percentage and generated
baseline comparison are only scenario arithmetic, not production metrics. With
no demo selected, the page shows missing detail categories as Unknown rather
than zero. Correlation or statistical change would be a signal to investigate,
not proof of cause; statistical measures do not establish correctness or
cryptographic verification.

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
Month. With no synthetic scenario selected, all periods show the empty state
because no workload-scoped event counts are available. During the explicitly
synthetic demo, bars count generated scenario events only, not production
evidence. The event/detail area is similarly empty instead of displaying
unrelated general audit references as workload activity.

## Required change record

1. **Invariant/failure addressed:** workload metrics must not be fabricated
   from unrelated evidence. The UI demo labels all generated values and
   outcomes as simulation and preserves the production Unknown/empty state
   when it is cleared or unused.
2. **Authority delta:** unchanged. The page owns no kernel, orchestrator,
   executor, canonical state backend, signer, credential, service client, or
   mutation method. The demo introduces no route or governed capability.
3. **Canonical state:** no canonical mutation was introduced or exposed.
   Synthetic observations and replay results remain in memory; the demo does
   not call the general evidence reader or write files.
4. **Success/adversarial evidence:** `python -W error -m unittest tests.test_sextant_demo tests.test_sextant_observation tests.test_control_center tests.test_audit_checkpoint tests.test_evidence_observation -v`
   checks deterministic bounded sample generation, a controlled investigation
   signal, synthetic outcome arithmetic, explicit empty-state preservation,
   visible simulation labeling, both top-of-page calibrated-zero graphs,
   symmetric rails and signed deviation labels, row details, period counts, and
   clearing back to Unknown
   without source reads or file writes. Parser tests also cover missing,
   reordered, incomplete, malformed-reference, non-finite, stale, and replayed
   inputs, and demonstrate that valid-shape substitution is not authenticated.
   Result on Windows: **78 tests run, all passed, with 16 environment-specific
   skips**.
5. **Evidence boundary:** the scenario is a generated calculation fixture, not
   a measured workload or production source. Tests do not establish a live
   workload feed, correctness labels, valid metric definition, calibrated
   thresholds, causality, source authenticity, cryptographic verification,
   deployment enforcement, accessibility qualification, or workload history.
6. **Claim classification:** UI behavior and tests are **Verified** at the
   tested commit. Generated scenario inputs and their derived display values
   are **Proposed** simulation only. The selected general source's values and
   timestamps remain source-reported **Recorded** values. Production workload
   identity, accuracy, drift, causes, and freshness remain **Unknown**.
7. **Legacy behavior:** reuses the native Control Center navigation and theme,
   plus the existing pure bounded replay calculation. No legacy authority or
   control path is copied into a source, router, executor, ledger, audit system,
   or authority plane.
8. **Temporal transfer:** no reusable lesson is admitted. No relevant
   historical checkpoint is used for this local synthetic presentation demo;
   no historical replay or authority change is claimed.

## Eight-pass adversarial transformation review

| Pass | Result |
|---|---|
| Flip | If the demo renderer is misleading or compromised, both graph titles and the scenario banner state that values are synthetic; it has no source reader or canonical writer to exploit. |
| Reverse | A false production workload claim would require source identity and real reviewed observations, neither of which the fixture supplies. Clearing the demo returns the UI to Unknown. |
| Invert | A displayed investigation signal or deviation rail is not success evidence for a real workload; graph titles and the banner label them as simulation, and values are Proposed. |
| Inside-Out | The demo creates scenario inputs and calculates their outputs, but cannot independently attest its generated labels, calibration, references, or any production fact. |
| Darken | Threat case: a user screenshots or repeats a graph or statistic as a real workload measurement. UI labels reduce confusion but cannot control downstream copying; the values remain non-evidence. |
| Lighten | The user-invoked local scenario is a benign calculation and presentation demonstration; it performs no model inference, external request, or state mutation. |
| Amplify | Repeated demo runs replace one bounded ten-event in-memory fixture; no accumulation, persistent replay cursor, or external execution is introduced. |
| Negate | To demonstrate cards, calibrated-zero deviation graphs, event counts, row details, and replay behavior, fixed synthetic values are sufficient. A live workload, transport, file watcher, or evidence writer is unnecessary and excluded. |

**Purpose:** demonstrate Sextant cards, calibrated-zero deviation graphs, rows,
and replay behavior locally.
**Exact outcome:** display a bounded synthetic scenario and calculated outputs
without presenting them as real workload evidence.
**Authority boundary:** user-invoked local presentation only; no external
execution, source reader, file write, credential, or canonical state writer.
**Claim classifications:** implementation behavior **Verified** by tests;
scenario and derived display values **Proposed**; production workload facts
**Unknown**. **Decision:** continue with this bounded demo; stop before adding
any live workload, source, transport, or persistent evidence path.
**Smallest next proof:** separately validate a real workload observation source
and its authority boundary before any integration. **Remaining unknowns:** no
real workload execution, identity, reviewed labels, calibrated baseline, or
production source is established by this demo.

This review is analytical only. Adding a workload source, metric semantics,
baseline approval, or evidence promotion requires its own authorized design,
strict source contract, tests, and adversarial review. This page grants none.
