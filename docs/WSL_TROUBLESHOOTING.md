# WSL troubleshooting center

System → Troubleshooting presents nine bounded checks: local UI runtime, Pulpo
service health, five existing owner-export sources, evidence storage capacity,
and benchmark cleanup. It is created only under the existing WSL runtime gate.
Other platforms retain their three System tabs. The six WSL tabs wrap into three
columns on wide windows and two on narrow windows; content scrolls vertically.

## Checks and interpretation

Selecting a row shows its local check completion time separately from the
source-reported timestamp, plus cause/observation, impact and a manual next step.
Navigation and visible-only age updates use existing caches. They never read a
source file, discover services, scan credentials or contact a provider.

Check selected source is explicit and unavailable until the corresponding owner
export has been selected on its existing source page. It calls the same Evidence,
Governance or Connections reader; storage reuses the Evidence reader. Existing
format, permissions, replay/clock rules and failure-clearing semantics remain in
place. A source re-read neither contacts its provider nor republishes an export.
Unchanged exports keep their original source timestamps. Existing readers are
bounded but this change does not add a hard filesystem-read deadline.

The local UI runtime check uses the existing diagnostic refresh. Its completion
time is recorded locally after that call returns, not inferred from app startup.
This confirms neither deployment availability nor service health. No live Pulpo
service-health contract identifies an intended service in this UI, so that row
remains Unknown and its check button unavailable. The trusted owner must inspect
the intended Ubuntu deployment; no service name, process liveness, restart,
repair, retry, OS configuration or credential is inferred or introduced.

Failed reads, source-reported failed checks, stale/future clocks and unchecked
sources stay distinct. An unselected source is Unknown, not offline. Evidence
capacity comes only from a usable selected Evidence export; absence is Unknown,
not zero. Below 10% free is a presentation attention hint. Stale exported capacity
remains historical and flagged, not a measurement of the local WSL volume or a
write/recovery test. A failed current read suppresses prior capacity. Existing
benchmark cleanup blocks are displayed without clearing or independently
certifying them. There is no overall health score or enforcement verdict.

## Preview and local export

Preview diagnostic report creates a frozen, bounded JSON projection of the fixed
finding fields and their times. It appears inline in a scrollable read-only view;
Export preview remains unavailable until a preview exists. Export writes exactly
that string to the user's chosen local file through the existing save dialog.
Later checks do not silently change the preview. Generate a new preview to include
new results. Cancellation/failure retain the preview and show a fixed status.

The report is built from fixed enums/text and numeric timestamps/capacity. It
never serializes raw source objects, arbitrary issue/error text, paths, host/device
identifiers, source fingerprints, raw logs, credentials or environment variables.
No support upload, archive, remote message, automatic export or persistent
diagnostic history is added. Preview and local check time clear on window close.
UI wall-clock times and source timestamps are not independently authenticated.

## Required change record

1. **Invariant:** information gaps, local read outcomes, source-reported failures,
   freshness and enforcement must remain separate. Troubleshooting must not
   acquire a canonical writer or promote successful reads into service health.
2. **Authority:** unchanged. This is a projection of existing non-authoritative
   caches plus explicit calls to their existing readers and diagnostic refresh.
   No kernel, state backend, signer, provider client or canonical writer is held.
3. **Canonical mutations:** none. Existing explicit export writes only the
   reviewed local support report; selected-reader calls update existing UI caches
   and session-local read/activity observations. No policy, permit, grant,
   approval, service configuration or performance profile is changed.
4. **Evidence:** [exact WSL test logs, hashes, native captures and report](control-center-evidence/wsl-troubleshooting/README.md).
   Tests cover missing/failed/unchecked/stale/future sources, capacity thresholds,
   failure suppression, privacy under injected raw text, explicit real selected
   reads, frozen exact preview/export, WSL gating, narrow layout, keyboard
   selection, cache-only navigation, lifecycle and teardown.
5. **Not proved:** live service health, collector liveness, production readiness,
   enforcement, independent provenance/time, full accessibility, safe recovery,
   complete diagnostics or hard read deadlines. Source authenticity remains
   Unknown; no remote probe or recovery exercise was performed.
6. **Claims:** implementation, tests, captures and report are Recorded. Missing
   source/service/capacity observations are Unknown. Attention is a UI hint,
   not an incident determination or authorization to repair.
7. **Legacy sources:** SourceHealth projection/lifecycle/keyboard handling,
   existing Evidence/Governance/Connections read functions, System diagnostics
   and explicit save dialog. No canonical control path copied.
8. **Temporal transfer:** no reusable authority lesson is admitted; no historical
   authority replay was performed or temporal-transfer proof claimed.

## Eight-pass analytical review

Purpose: guide WSL users from bounded observations to manual troubleshooting.
Boundary: local projection, existing explicit readers, reviewed local export.

| Pass | Finding and decision |
| --- | --- |
| Flip | A hostile export can fail existing validation, but cannot supply raw report text or a repair command. Fixed findings exclude raw strings and credentials. |
| Reverse | An unintended repair or canonical write would require a writer. This view holds none; its actions are existing readers, diagnostic refresh, fixed navigation and reviewed local export. |
| Invert | A successful file read or local runtime check is not healthy deployment or enforcement. Service health stays Unknown without an observation contract. |
| Inside-Out | UI times, cached values and capacity hints cannot authenticate the UI or exporter. No all-clear, freshness renewal, independent cleanup attestation or source identity claim is made. |
| Darken | Failed reads must suppress old capacity; stale or future reports remain attention/gaps. Injected raw errors/paths must not enter support output. Covered by tests. |
| Lighten | Missing exports are ordinary setup gaps, not outages. A low-space hint requires owner review, not deleting evidence or changing permissions. |
| Amplify | Nine stable rows, one visible-only cache timer and one frozen preview remain bounded. Repeated navigation performs no reads or writes; explicit readers retain existing limits and no network polling is added. |
| Negate | Reuse existing readers and manual source-owner guidance. A new service probe, repair executor, credential scanner, report uploader or diagnostic history store is unnecessary for this increment. |

Decision: WSL validation and draft review only. No merge or production deployment.
