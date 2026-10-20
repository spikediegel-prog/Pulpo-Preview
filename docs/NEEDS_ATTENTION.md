# Needs Attention on Overview

Status: **Recorded implementation, native inspection and regression evidence.**
Base: `104582caee19e36e0a904e3ac55bd273d07b389d`.

Overview now places a compact Needs Attention panel below the activity monitor
and above the existing operational status rows. Its three-row list scrolls through
derived conditions. Select a row to see the impact, source, observation age and
next step; the button opens an existing page or, for a UDM certificate/configuration
report, the existing UDM setup guide. These are navigation actions, not collection,
repair, approval, retry or incident-resolution commands.

## Conditions and meaning

| Kind | Included conditions | Meaning |
| --- | --- | --- |
| Problem | Selected-source read/validation failure; source-reported connector failure; reported audit or physical database check failure | A specific problem indication, scoped to its source/sample, not a fleet incident or proof of compromise. |
| Information gap | Unselected sources; stale/clock-inconsistent observations; unknown collection/database health/capacity; missing local readings; incomplete governance coverage | Information is unavailable or insufficient, not an offline or failed system by inference. |
| Resource hint | Existing local CPU/memory/storage thresholds; existing evidence-volume and WAL size conditions | A last-sample capacity/utilization hint, not enforcement or deployment health. |

Historical denial, approval, permit-rejection and SQL-error totals are not promoted
to current incidents. Normal workflow outcomes remain in their existing pages.
The current exports do not carry unresolved-consequence state or deployment
enforcement proof; the governance coverage item explicitly leaves these Unknown.

Freshness uses existing source contracts: connection reports over 60 seconds,
evidence observations over 15 seconds, and future clocks beyond five seconds
produce information gaps. A local resource sample over ten seconds old is marked
historical. Reported failures are retained as sample-scoped indications even when
their sample becomes historical. Source age is not time since an incident started,
nor proof that a source timestamp is authentic. Governance exports lack a source
timestamp; their age stays Unknown rather than using the local file-read time.

Resource thresholds remain 75% review / 90% attention; evidence volume remains
85% / 95%. WAL comparison retains the existing `> max(64 MiB, database size)`
hint. Shared-volume use is not all Pulpo evidence. Windows, Linux and WSL VM scope
is labeled where known. Unknown measurements never become zero.

## Refresh, selection and privacy

The model reads only cached, validated projections already held by the existing
pages. There is no new file reader, provider client, credential, service, timer,
background worker or network request. Overview's existing local-resource callback
updates the projection approximately every two seconds while visible. Entering
Overview and existing source-render callbacks also refresh it. Returning to
Overview recomputes age without polling a source. Existing source pages keep their
own refresh/collection behavior; this feature does not change it.

Fixed provider/rule sets bound item count. Stable keys update existing table rows
without accumulating a history or rebuilding the widget tree on every tick.
Selection survives age refresh. If a selected condition disappears, details say
that its removal does not confirm resolution and disable the old action. Clearing
an observation can remove its derived items; it never resolves a canonical
incident. No reviewed/dismissed/resolved marker or persistent acknowledgment is
introduced. Counts are condition items, not incident, device or fleet totals.
A removed condition returning with the same key cannot reactivate its old action;
the operator must select a current row again.

The panel uses fixed explanatory copy, enum-derived reasons and bounded source
fingerprints. It does not echo raw exception strings, selected file paths, provider
payloads, arbitrary source text or credentials. Public screenshot examples contain
only first-run gaps and actual local OS resource readings. Failure/adversarial
cases use labeled automated fixtures, not invented live metrics.

## Required change record

1. **Invariant addressed:** an actionable summary must distinguish observed
   indications, unknown coverage and resource hints; source selection or successful
   connectivity must not imply governed/enforcement-verified operation.
2. **Authority:** unchanged. The projection and panel hold frozen public metadata
   and navigation references only. No execution, signing, provider or canonical
   mutation capability is gained.
3. **Canonical mutations:** none introduced or exposed. No second audit/incident
   ledger, policy router, approval path or reconciliation system is created.
4. **Evidence:** [native review captures, exact test logs and source hashes](control-center-evidence/needs-attention/README.md).
   New cases cover first-run gaps, TLS versus stale success, existing thresholds,
   historical workflow counts, error precedence, sanitized copy, clock mismatch,
   bounded/repeated projection, cached-only navigation, age-refresh selection,
   disabled stale actions, source clearing, minimum-size layout and teardown.
5. **Unproven boundaries:** authenticated source identity, freshness beyond reported
   metadata, full fleet coverage, unresolved-consequence counts, independent audit
   verification, production readiness, full accessibility and enforcement.
6. **Classification:** implementation/tests/captures Recorded. Conditions are local
   observations or source-reported metadata; threat cases below are analysis.
   Unavailable authority/enforcement and consequence information remain Unknown.
7. **Legacy reuse:** existing observation contracts, page navigation, UDM setup,
   source loaders and local resource refresh callbacks; no kernel path copied or
   alternate executor introduced.
8. **Temporal transfer:** no reusable authority lesson is admitted. Historical
   authority replay was not performed and no temporal-transfer proof is claimed.

## Eight-pass review

Purpose: help operators understand source-supported conditions and navigate to
the relevant existing details. Exact outcome: a bounded Overview projection.
Authority boundary: cached observations and navigation only.

| Pass | Finding and boundary |
| --- | --- |
| Flip | A hostile but schema-valid export can lie. Its content remains source-reported and unverified; fingerprints and recent timestamps do not authenticate it. Export strings cannot provide new routes or executable actions. |
| Reverse | An unintended repair, approval or resolution would need a mutation/command capability. New callbacks only navigate; no new reader, client, writer or command runner exists. The UDM guide retains its existing separate collector boundary. |
| Invert | Zero problem indications is not an all-clear. Missing source/coverage remains visible; successful reads do not clear governance uncertainty. Invalid source reads override cached good values. |
| Inside-Out | The UI cannot ratify its own evidence or resolve canonical incidents. It exposes reported audit failure without claiming independent chain verification. No canonical state object is retained. |
| Darken | Bounded threat: stale/forged metadata or misleading historical totals could suggest a false current incident or pass. Tests cover clocks, historical workflow exclusion, error precedence, privacy and disabled removed-condition actions. Complete authenticity and accessibility remain unproven. |
| Lighten | Missing/stale data can reflect ordinary export setup or collection cadence. It is a gap, not proof of provider outage, compromise or incident resolution. |
| Amplify | Fixed providers and rules, one current cache projection, stable table keys and existing refresh callbacks avoid an accumulating alert ledger or new polling load. Repeated projection/navigation preserves source data and creates no files. |
| Negate | Reuse existing cached observations and page links. A network monitor, notification service, autonomous repair agent or second incident database is unnecessary. |

Decision: continue to local validation and draft review; no merge or deployment.
Smallest next proof: inspect the retained captures and test results, then review
the exact rule-to-source mappings. Future incident-resolution or governed actions
would need their own canonical design and authorization.
