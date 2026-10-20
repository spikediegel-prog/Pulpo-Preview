# Source Health & Coverage

System → Source health presents five existing export sources: Governance metadata,
Evidence, UniFi UDM, NinjaOne and CrowdStrike. It reuses the existing charcoal,
purple and soft-white theme. Validation and visual review for this increment focus
on Ubuntu in WSL, as requested; no new Windows qualification is claimed.

## Separate observations

**Selection** means a file was selected in this session. It does not establish
that a collector is installed, configured or running. No selection means Unknown,
not offline. No file paths or free-form errors appear in this projection.

**Local read result** is recorded after an existing reader finishes. It captures
the UI wall-clock time and whether that reader accepted the file. There is at most
one frozen result for each of the five fixed source keys, held only in memory.
Re-reading an unchanged file updates this local result; it never updates the
export's source timestamp. Clearing a selection removes the local read result.
This is not continuous monitoring of file existence, accessibility or permissions.
A past accepted file can become unreadable without this view knowing until the
existing reader is explicitly used again (or Evidence's existing visible-page
polling runs). A rejected source clears its prior observations as before.

**Source time** comes only from an accepted observation. Evidence is stale after
15 seconds and connection reports after 60 seconds, reusing the existing limits.
Source times more than five seconds ahead indicate clock mismatch. A future time
is never presented as zero age. Governance's current format has no export time;
its source time and freshness stay Unknown even after a successful local read.
Local wall clocks and reported timestamps do not prove synchronization.

**Reported checks** are distinct from local readability and timestamp age. A
readable connector file may report TLS/authentication/permission failure. A recent
Evidence export may report failed database or audit checks. A successful read or
passing source report never establishes healthy service, authenticated provenance
or deployed enforcement. Missing/unavailable database checks and unknown collection
results are gaps, not reported failed checks. Red indicates failed reads or
reported failures; amber indicates stale/future timestamps; missing checks stay
neutral. No health score, all-clear, incident count or synthetic metric is derived.

## Coverage and troubleshooting

Each source has a selected-source detail pane containing its local read result,
reported timestamp, source fingerprint where available, reported checks, exact
coverage limitations, remaining Unknowns and a next step. Fingerprints remain
reported metadata, not authenticated identities. Governance's policy fingerprint
is not reused as an exporter identity. Evidence covers nullable telemetry and at
most 24 redacted references, not correlated action chains or complete history.
Provider counts remain bounded returned pages, not fleet totals. The page explains
the existing 100-record device/host/client limits, NinjaOne's 200-alert limit and
CrowdStrike's 100 alert-ID limit without inventing coverage.

Troubleshooting links navigate to the existing source page. Private Ubuntu file
permission and format checks stay with its existing reader. The operator can ask
the trusted owner to republish an observation, then explicitly re-read it. Stale
reports explain why re-reading the same file cannot refresh its source time.
UDM TLS reports point to the existing Guided UDM setup, without bypassing trust,
installing certificates or accepting credentials in the UI.

While Source health is visible, a single one-second display timer updates ages
from the existing caches. No source files or providers are polled by this page.
It stops on tab/page changes and root destruction, and skips rendering when
minimized/unmapped. Evidence's existing two-second file polling pauses while its
page is hidden; opening Evidence can resume that existing behavior. Connection
and Governance file re-reads stay explicit. Update display is cache-only.
Fixed table rows retain source selection, and a changed detail keeps the current
logical paragraph in view. The narrow layout wraps System tabs into two columns,
keeps the table within the minimum window width and provides keyboard selection,
outer-page scrolling and a separate detail scrollbar.

## Authority and required change record

1. **Invariant:** file readability, source time, collection success, coverage and
   governance assurance must remain separate. Local refresh cannot manufacture
   source freshness or upgrade Recorded reports into Verified enforcement.
2. **Authority:** unchanged. New code holds fixed public values, local read-result
   metadata and presentation/navigation references only. No credential, kernel,
   provider client, executor, canonical state backend or signing capability.
3. **Canonical mutations:** none introduced or exposed. Existing source loaders,
   APIs and export schemas are unchanged. Local read metadata is session-only,
   bounded to five keys, with no file, second audit source, ledger or incident store.
4. **Evidence:** [WSL native before/after captures, test logs and source hashes](control-center-evidence/source-health/README.md).
   Tests cover source selection, stale reads, absent export times, reported failures
   versus gaps, invalid sources overriding cached success, clocks, boundaries,
   privacy, fixed bounds, re-reads/clears, cache-only navigation, keyboard/layout,
   timer cancellation, paragraph preservation and owner-thread teardown.
5. **Not proved:** authenticated source identity, continuous file readability,
   collector uptime/configuration, full fleet/history coverage, clock sync,
   independent audit verification, correlated actions, deployed enforcement,
   production readiness, full accessibility or new Windows qualification.
6. **Classification:** implementation, native captures and tests **Recorded**;
   accepted export content remains source-reported **Recorded**. Missing source,
   authority and consequence information remains **Unknown**. Any fixture capture
   is prominently labeled synthetic, never live operational proof.
7. **Legacy reuse:** existing Evidence/connection DTOs and file readers,
   Governance observation summaries, freshness limits, source navigation,
   shared theme and existing System views. No control path is copied or expanded.
8. **Temporal transfer:** no reusable authority lesson is admitted. Historical
   authority replay was not performed, and no temporal-transfer proof is claimed.
   The exact-base native screenshot is a visual baseline only.

## Eight-pass analytical review

Purpose: expose observation quality and coverage without implying governance.
Exact requested outcome: a WSL-focused, read-only source dashboard and next steps.
Authority boundary: existing cached DTOs, five session-local read results and fixed
navigation; no source reader or provider is added to the dashboard.

| Pass | Finding and boundary |
| --- | --- |
| Flip | A hostile but schema-valid export may lie. Fingerprints, recent timestamps and passing checks remain source-reported; nothing authenticates the exporter. |
| Reverse | A false all-clear could arise by substituting local read time for export time. Separate fields and tests keep Governance time Unknown and stale exports stale after re-read. |
| Invert | Read OK does not mean collection OK, database health, complete history or enforcement. Reported TLS/database/audit failures stay visible; missing checks remain gaps. |
| Inside-Out | The UI records only its local reader's result. It cannot self-attest a canonical chain, ratify source identity, configure credentials or resolve a consequence. |
| Darken | Bounded threat: an invalid source plus an old cache or injected free-form error could mislead or disclose data. Invalid/read-failed observations override cache values; no raw paths/errors are echoed. No continuous readability claim is made. |
| Lighten | No selected source or stale data may reflect ordinary setup/cadence. Neither is evidence of an outage, compromise or absent governance effect. |
| Amplify | Fixed five keys and one replaceable read result each prevent an accumulating event store. One visible-only display timer does no file/network I/O and is canceled on leaving or teardown. Repeated navigation creates no files. |
| Negate | Reuse existing caches and source pages. A watcher, network scanner, new collector, canonical reader, repair control or second evidence service is unnecessary. |

Decision: continue to WSL tests, native inspection and draft review only. Smallest
next proof: review the exact source-to-display mapping and retained test evidence.
Authenticated deployment coverage and correlated action inspection require their
own canonical evidence design; this dashboard does not infer them.
