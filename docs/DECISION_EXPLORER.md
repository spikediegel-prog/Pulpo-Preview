# Decision Explorer: bounded record inspection

Governance now has Summary and Decision Explorer tabs. The explorer inspects one
reference from the existing selected Evidence observation; it does not reconstruct
an action history. The charcoal, purple and soft-white application theme is reused.

## Canonical inspection and chosen increment

The canonical kernel/state decision records retain `outcome`, `reason` and
`intent_hash`; permit consumption is a separate state transition. Custody has
distinct attempt, claim, transmission and reconciliation transitions. In particular,
`REQUEST_TRANSMITTED` conservatively means a request **may** have reached a provider;
it does not establish completion. Decision-boundary declarations in
`decision_evidence.py` are evidence-only and never grant authority.

The existing trusted-owner `evidence_export.py` deliberately projects only fixed
event/outcome enums, record times and hashes into at most 24 `EvidenceEvent` values.
It exports no intent hash, reason, principal, resource, correlation ID, approval
binding, bearer permit, execution receipt or reconciliation state. Governance's
separate `pulpo.mcp-read-snapshot.v0` export contains aggregate metadata only.

This increment reuses `pulpo.evidence-observation.v1` unchanged. No raw audit file,
state database, orchestrator, kernel, provider client or canonical writer enters
the explorer. It is a view of the current cache, not an additional audit source,
ledger, incident store or decision API. There is no new export or polling timer.
Full request-to-consequence inspection requires a separately designed, correlated,
redacted owner projection before this UI can claim that coverage. Timestamp proximity,
matching outcomes and shared source identity cannot supply that correlation.

## What an operator sees

- Reference type filters: all, decisions, approvals or permits. Latest exported
  order appears first; records are not reordered into a supposed action chain.
- Source fingerprint, reported freshness and reported audit result. Failed audit
  checks stay explicit. A recent timestamp or passing report does not authenticate
  the source or independently verify its chain.
- A selected record's full hash, nanosecond UTC record time and separate export
  observation time. Missing coverage is not interpreted as zero activity.
- Request/target, policy decision, approval, permit, execution/consequence stages.
  Only the selected event's own stage receives **Recorded** information. All
  uncorrelated stages remain **Unknown**, even if neighboring references appear
  to contain an approval or permit. Decision reason and policy binding remain
  unavailable. `approval_verified` is a source event name, not a UI verification
  claim. Consumption does not prove an external effect; rejection does not prove
  that no other governed effect occurred.
- Copy safe record reference includes only the existing strict enums, hashes,
  numeric times and explicit Unknown provenance/enforcement. It excludes paths,
  raw payloads, reasons, prompts, credentials and bearer permits.

Select/re-read/clear the file in Evidence. While Governance is visible, Evidence's
existing hidden-page polling pauses. Update display reads only that cache; its
freshness is recalculated on display update or a visit to Governance. This is not
a live decision stream. No reference means no selection, not a claim of no actions.
Source changes, errors, clearing and filter changes clear selection and disable
copying. Returning records require explicit selection again. Copy also checks the
current cache before touching the clipboard, covering source replacement between
render and action. There are no approvals, retries, revocations or resolution
markers. Unknown consequences never authorize retry.

The existing scrollable Governance page and a separate Decision Explorer tab keep
the summary usable. Tables and detail text support keyboard navigation and scrolling;
the two-column table fits the existing minimum window size. Full accessibility
qualification remains unproven.

## Required change record

1. **Invariant:** authorization, attempted execution and established consequence
   must remain separate. Unlinked records cannot be promoted into a complete chain.
2. **Authority:** unchanged; cached frozen public values and UI navigation only.
3. **Canonical mutations:** none introduced or exposed. No new authority, audit,
   state, credential, provider, approval or reconciliation capability.
4. **Evidence:** [native before/after captures, logs and source hashes](control-center-evidence/decision-explorer/README.md).
   Tests exercise separate stages, all decision outcomes, permit/approval events,
   unrelated neighbors, exact UTC times, source replacement before copying,
   failed/cleared/returning sources, filters, cached-only repeated navigation,
   minimum-width keyboard selection, no file creation and owner-thread teardown.
5. **Not proved:** source authenticity, complete history, stage correlation,
   exact policy/approval binding, deployed enforcement, external consequence,
   production readiness or complete accessibility.
6. **Classification:** implementation, captures and test results **Recorded**.
   Displayed events are source-reported **Recorded**; unsupported stages remain
   **Unknown**. Eight-pass threat cases are analytical, not observed incidents.
7. **Legacy reuse:** existing frozen observation contract, Evidence cache, shared
   theme and navigation. Canonical record shapes were inspected without copying
   their control paths or retaining canonical objects.
8. **Temporal transfer:** no reusable authority lesson is admitted. Historical
   authority replay was not performed; no temporal-transfer proof is claimed.

## Eight-pass analytical review

Purpose: inspect source-supported decision references without inventing a chain.
Authority boundary: cached public DTOs, display and explicit safe clipboard copy.

| Pass | Finding / boundary |
| --- | --- |
| Flip | A hostile schema-valid export can lie. Events remain source-reported; fixed enums/hashes cannot introduce routes or executable controls. |
| Reverse | An unintended effect requires a writer/executor. Neither is imported or retained. The explorer only navigates to the existing Evidence page or copies a bounded reference. |
| Invert | An allowed decision, reported approval or consumed permit is not execution success. Every unrelated stage remains Unknown. |
| Inside-Out | The UI cannot ratify source truth, bind approval, reconcile a consequence or independently verify a hash chain from these redacted references. |
| Darken | Bounded threat: forged, stale or substituted exports could mislead an operator or copy an old reference. Source/error precedence and selection invalidation prevent stale actions; provenance remains unverified. |
| Lighten | Missing records may reflect redaction, the latest-24 bound or no configured export. None proves denial, absence of governance effects or provider failure. |
| Amplify | Repeated navigation and update reuse the bounded current cache; no history grows, files are not written and no new polling workload or audit source is created. |
| Negate | Keep the safe existing DTO and explicit Unknown stages. Opening a canonical database or introducing a second authority/evidence service is unnecessary for this increment. |

Decision: continue to tests, native inspection and draft PR review only. Smallest
next proof for a future complete explorer: specify exact owner-side correlation
and redaction against existing canonical evidence, including unresolved effects,
without granting the UI any canonical capability.
