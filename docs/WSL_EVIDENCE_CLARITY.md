# WSL observation clarity

This increment refines the existing native Control Center and charcoal/purple
palette. New presentation is enabled for WSL; other platforms retain the previous
Evidence text log and controls. Source and export APIs are unchanged.

## Five refinements

1. **Test context.** A persistent header names selected files containing
   `TEST-ONLY` as an **unverified filename hint**. Evidence's Source details also
   offers an explicit operator test label, scoped to the current selection and
   this window. Neither classification authenticates an exporter. The header is
   compact at narrow widths and remains visible when the page scrolls or changes.
   Unmarked sources are unclassified, never automatically called production.
   Renaming a file can remove a filename hint; it cannot establish provenance or
   enforcement. No file content, profile or export schema is changed by a label.
2. **Graph states.** No source, restored/not read, failed read, paused review,
   stale data, unavailable counters, first sample, incomparable counters, partial
   readings and recent comparable samples have separate explanations. Stale data
   does not prove an owner stopped. Recent timestamps do not prove liveness. The
   empty graph is smaller; unknown readings stay Unknown, missing history stays
   gaps, and actual zero rates remain distinct. Sampling, thresholds and bounded
   history are unchanged. Legends and controls wrap using requested sizes.
3. **Snapshot summary.** Source name and last successful local read precede a
   snapshot summary, expandable storage/health/audit rows, and collapsible notes.
   Notes appear above detailed authorization/AI counters; their count is a count
   of displayed conditions, not active incidents. Definitions, full selected path
   and the test-label control are available under Source details. Source age is
   always separate from local read time. No metrics are fabricated or estimated.
4. **Events.** At most 24 existing redacted references appear in a keyboard
   accessible table with source record time, event and outcome. Show details
   exposes one selected reference; Copy record hash copies exactly that public
   hash. It is disabled without a selection. Identical cached re-renders preserve
   selection and scroll; removal, source replacement, failed read or filtering
   clears any reference no longer available. Adjacent rows are never correlated
   into an invented action lifecycle. Horizontal scrolling covers narrow columns.
5. **Sources.** System → Monitor → Sources adds the selected local path, the last
   successful local read, and Select / replace source. Replacement uses the same
   source page/file chooser and protected loader. This action is explicit; display
   updates and navigation do not discover files or contact providers. A restored
   Evidence selection keeps its existing explicit-first-read gate. No saved setup
   format, performance profile, collector or provider configuration is changed.

Last successful local reads are bounded in-memory presentation state, one per
supported source, and cleared for a new explicit selection or Clear. A later failed
read retains the historical timestamp but clears current metrics through the
existing loader. Paths are shown locally and are not added to clipboard summaries,
support exports, telemetry or saved preferences by this change. Existing optional
Remember setup still saves only its previously supported fields when requested.

## Required change record

1. **Invariant/failure:** test names, recent timestamps and passing source reports
   must not become authenticated deployment or enforcement claims. Blank graphs
   and dense logs obscured the actual observation state during the walkthrough.
2. **Authority:** unchanged. Test context and read history are local presentation;
   they cannot grant, approve, revoke, consume or execute any capability.
3. **Canonical mutations:** none introduced or exposed. No kernel, owner, executor,
   database handle, signer or new ledger is created or retained by these views.
4. **Evidence:** native before/after captures plus exact core test log and source
   hashes are in `control-center-evidence/evidence-clarity`. Tests cover cache-only
   context, malformed/failing source clearing, unknown/gapped counters, exact hash
   copying, source changes, restored read gates and larger-text controls.
5. **Limits:** screenshots and fixture tests do not prove full accessibility,
   every font/display scale, authenticated provenance, independent audit integrity,
   provider liveness, production governance, or live VM-to-WSL transfer. The new
   UI does not add an authenticated test/production field to existing exports.
6. **Classification:** Verified is limited to the recorded tests/layouts. Metrics
   and metadata remain Recorded source reports. File-name context is Inferred;
   operator labels are explicitly local declarations. Enforcement stays Unknown.
7. **Legacy source:** existing source readers, read-attempt cache, snapshot/rate
   history, event enums, filters, file choosers and source-health model are reused.
   No legacy authority control path is copied.
8. **Temporal transfer:** no reusable governance lesson is admitted and no
   temporal-transfer proof is claimed. Prior UI screenshots are comparisons, not
   reconstructed historical authority checkpoints.

## Eight-pass analytical review

| Pass | Result |
| --- | --- |
| Flip | A hostile filename or operator label can misdescribe context; the UI calls it unverified and never promotes it to authority. |
| Reverse | A false deployment success would require equating file acceptance, a local read or a recent timestamp with enforcement; the views explicitly separate them. |
| Invert | Passing database/audit reports remain source reports. Invalid refresh clears current values and event copy targets despite earlier success. |
| Inside-Out | The observer cannot certify its own source; a test label and record hash are not authentication mechanisms. |
| Darken | Replaced/failed/stale exports cannot preserve current positive readings. A compromised host, misleading timestamps or substituted schema-valid sources remain outside this UI's trust guarantee. |
| Lighten | Missing counters, no model usage and stale frozen copies remain information gaps, not fabricated zero activity or new incidents. |
| Amplify | Repeated cache renders add no audit records or authority; source caches remain bounded, event display stays at 24 and polling cadence is unchanged. |
| Negate | Use existing protected public exports and explicit selectors without a new owner, service, credential scan or automatic connector. |

Continue decision: proceed with this presentation-only increment after tests and
native review. Smallest next proof is the same live test-data walkthrough with
the updated WSL UI. Source authenticity, deployment enforcement and complete
accessibility qualification remain unverified.
