# Setup Readiness · WSL only

System → Setup readiness is constructed only when the local runtime reports Linux
and its kernel release contains `microsoft` (case insensitive). Ordinary Linux,
Windows and macOS do not receive this tab or its UI. This is a display/platform
check, not a security attestation. A custom WSL kernel without that identifier will
not enable the view. No Windows implementation or visual qualification is added.

The existing charcoal/purple/soft-white theme, source observations, navigation and
non-secret UDM guide are reused. No API/export schema is changed.

## Checklist scope and meaning

The nine fixed checks cover the local WSL runtime; core Governance/Evidence
observation setup; optional UDM, NinjaOne and CrowdStrike exports; optional UDM
certificate trust and site UUID; and separately Unknown governance assurance and
consequences. Core here means the checklist's observation workflow, not a claim
that the canonical kernel requires UI exports to govern an action.

States are **Recorded**, **Needs setup**, **Needs attention**, **Optional** and
**Unknown**. No overall Ready verdict, percentage, completion score, health score
or enforcement-verified label is calculated. Missing optional connectors do not
block Control Center. Source selection, accepted file reads and recent timestamps
are separate facts from collection success, source identity and enforcement.

A core source without a selection needs setup. Failed reads/reported failures and
stale/future source timestamps need attention. Accepted observations with a known
local read result can be Recorded; Governance export freshness remains Unknown
because its format lacks a source timestamp. A readable connector export with no
collection result remains Unknown. Missing database checks are displayed as gaps,
not failed checks. All source semantics come from the existing Source Health
projection; its read-error precedence and 15/60-second freshness limits remain.

Each selected check explains the evidence, limits and next action. Runtime means
only this UI is running in a WSL-identified kernel, not that a canonical service
or collector runs. Governance assurance remains Unknown even when all observation
setup facts are Recorded. These exports do not establish current policy/grants,
approval/permit bindings, correlated execution or external consequences. Unknown
consequences never authorize retry.

## UDM boundaries

The certificate check is Unknown without an independent trust observation. A
selected report of TLS failure raises an explicitly source-reported indication
with its freshness classification. It does not run a live probe. A CA filename,
saved setup or successful source-reported collection cannot independently verify
trust here. Guided UDM setup remains the route to review trust requirements;
certificate verification is never bypassed or altered.

The site-UUID check can become Recorded only for an open guide whose non-secret
current form exactly matches its reviewed/saved `collect` handoff. A canonical
UUID alone, an unreviewed edit, a site-discovery handoff or an inventory export
cannot fill it. Static `UdmSetup` validation is reused without `guide.config()`,
filesystem probes, setup-file scans, certificate reads or credential access.
The view returns a boolean match only; it never displays/retains raw form values,
file paths, IPs or UUIDs. Editing or closing the guide withdraws this observation;
an existing setup file outside that available session state is not discovered.
A Recorded UUID is local configuration, not proof of site discovery/access,
collector execution, source provenance or current file availability.

All actions are fixed navigation: Diagnostics, the source pages, Decision
Explorer or Guided UDM setup. No command runs, setup saves, credentials load,
certificates install, governed actions occur or resolution markers are created.
Opening a source page may resume that page's existing behavior, such as Evidence
file polling; the checklist itself never polls files or providers.

The Source Health view's existing visible-only timer/keyboard/teardown behavior
is reused. Only the active System subview runs its age display timer. Repeated
updates replace nine stable rows; no history or persistent checklist is added.
Selections and the reviewed paragraph are preserved on changing observations.
WSL System tabs reflow into multiple columns; minimum-size windows use two columns,
with a source table scrollbar, page scrolling and a separate detail scrollbar.

## Required change record

1. **Invariant:** setup observation is not enforcement verification. Intelligence
   cannot grant authority, infer a complete chain or authorize retries from gaps.
2. **Authority:** unchanged. Frozen source projections, non-secret current guide
   fields and fixed UI navigation only. No kernel, executor, state backend,
   provider client, human credential or other canonical writer retained.
3. **Canonical mutation:** none introduced/exposed. No new API, reader, collector,
   ledger, incident store, memory system, approval path or authority plane. No
   source file/configuration is saved by the checklist.
4. **Evidence:** [WSL native review, exact logs and source hashes](control-center-evidence/wsl-readiness/README.md).
   Tests cover WSL-only gating, absent non-WSL tab, first-run/optional scopes,
   Recorded setup with Unknown assurance/trust, stale/future/error precedence,
   unknown collection results, no path probes, reviewed handoff substitution,
   malformed/edited/closed guide state, cache-only repeated navigation, keyboard,
   minimum width, timer cancellation, UDM navigation and teardown.
5. **Not proved:** independent trust/source identity, installed/running collectors,
   full setup deployment, clock synchronization, actual provider access, current
   policy/grants, exact approval bindings, complete action history, consequences,
   deployed enforcement, production readiness or complete accessibility.
6. **Classification:** implementation/captures/tests Recorded. Source reports and
   local configuration matches Recorded; unavailable assurance stays Unknown.
   Threat cases below are analytical. No metrics or verified trust are invented.
7. **Legacy reuse:** Source Health projection and view lifecycle, strict non-secret
   UdmSetup value validation, existing guide/navigation and shared theme. No
   canonical control path copied or expanded.
8. **Temporal transfer:** no reusable authority lesson admitted. Historical
   authority replay was not performed; no temporal-transfer proof is claimed.
   Prior captures are visual references only.

## Eight-pass analytical review

Purpose: make WSL observation setup understandable without implying authority.
Exact outcome: bounded WSL-only checklist and fixed navigation, no auto-setup.

| Pass | Finding / boundary |
| --- | --- |
| Flip | Forged exports can claim success; reports remain Recorded and authenticity Unknown. Arbitrary source strings/paths/errors never become actions or displayed setup values. |
| Reverse | False enforcement assurance would require promoting configuration or connectivity into proof. The separate assurance/trust rows remain Unknown; no overall Ready verdict exists. |
| Invert | A saved handoff, valid UUID or allowed record is not collector execution or legitimate consequence. Missing/failed/stale observations retain their own state. |
| Inside-Out | The checklist cannot certify its own trust, change canonical state, sign approvals or ratify a source chain. It never retains those capabilities. |
| Darken | Bounded threat: stale reports, substituted forms, unknown-result files or cached successful values could mislead. Source Health error precedence and exact reviewed-form matching reject those promotions. No live TLS, certificate or credential probe is added. |
| Lighten | Optional connectors may be unused and metadata may be absent or intentionally redacted. Gaps do not imply outage, denial, compromise or no governance effect. |
| Amplify | Nine stable rows and an existing visible-only timer avoid accumulating history or new polling load. Repeated visits create no files; timers stop on leaving/destroying. |
| Negate | Reuse cached observations and the existing non-secret guide rather than adding auto-configuration, network probing, credential custody, a second reader or authority path. |

Decision: continue to WSL tests, native inspection and draft review only. Smallest
next proof: inspect exact state mappings, runtime gating and retained test/capture
evidence. No PR merge or production deployment is authorized by this checklist.
