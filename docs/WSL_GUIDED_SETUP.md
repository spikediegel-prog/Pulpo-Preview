# Guided WSL setup

Overview now offers Start guided setup. The walkthrough lives inside the existing
System → Setup readiness tab alongside its checklist, not in a new dashboard or
System tab. It is WSL-only, optional, non-modal and never opens itself on launch.
The user's existing remembered startup page/System-tab choice remains intact.

## Five steps, without a readiness verdict

1. **Understand observations:** distinguish WSL resource readings, source-reported
   facts, local file reads, missing evidence and enforcement. A connected service
   or passing benchmark does not establish governance.
2. **Select Governance and Evidence exports:** navigate to their existing source
   pages. The user uses the existing Select/Re-read controls for trusted-owner
   sanitized exports; databases, raw audit logs and credentials are excluded.
   Return to the guide to see cached local read status, completion time and source
   freshness. Missing sources remain gaps and do not block browsing the guide.
3. **Optional connectors:** open Connections or skip UniFi UDM/NinjaOne/CrowdStrike
   setup. Skipping records only a session-local navigation choice; no provider is
   disconnected, source selection cleared or credential supplied.
4. **Checks and gaps:** open the existing Troubleshooting view, explicitly check
   an available selected source and inspect cause, impact, timestamps and manual
   next step. The guide projects cached check states; it runs no bulk check,
   service probe or repair. Missing service-health evidence stays Unknown.
5. **Optional persistence:** review Session setup and explicitly press Remember
   there if desired. The guide never saves preferences or a completion record.
   Returning to Overview with gaps is supported and confers no Ready/governed
   verdict.

Previous/Next are navigation only. Step numbers show position, not completion or
coverage. Actions are fixed navigation to existing pages; unknown action targets
and out-of-range/noninteger steps are rejected. The user can continue without
sources, checks or a saved setup. No checkmarks or aggregate readiness score are
created.

## Keeping your place

A Return to guide banner appears while the active guide is outside its own pane,
including while inspecting the checklist. Returning preserves the current step.
Overview offers Resume guided setup while the guide is active. Close guide hides
the banner and shows the checklist if needed, preserving observations, selectors,
preferences and provider state. Reopening a closed guide starts at step one.
Position and the optional-skip choice are memory-only and disappear on close.

The existing Setup Readiness visible-only timer renders cached observations.
The guide adds no polling loop, source reader, network client, provider login,
credential field, canonical writer, configuration service or persistence format.
Actions navigate to existing source pages; their normal behavior stays intact.
In particular, Evidence's existing visible polling may run after an explicit
initial source read, while a remembered pending-re-read location remains gated.
The guide does not bypass that gate or renew source timestamps.

The layout uses the existing charcoal/purple/soft-white theme and scrollable
content. Fixed navigation buttons remain keyboard-focusable; step actions rebuild
only when the step changes, retaining focus during cache/age updates. The narrow
layout retains the same System-tab count and supports vertical scrolling. Banner
and guide references are released during normal root teardown.

## Required change record

1. **Invariant:** navigation through setup cannot become execution, configuration
   approval, implicit source validation or governance assurance. Missing/stale/
   failed evidence remains visible rather than being converted to completion.
2. **Authority:** unchanged. No kernel, canonical writer, state backend, signer,
   credential or provider client is introduced or retained by the guide.
3. **Canonical mutations:** none. New state is bounded ephemeral guide position,
   active/closed state and optional-skip choice. Existing source readers, checks
   and explicit preferences save remain exclusively on their original pages.
   No policy, permit, grant, authority, service or performance setting changes.
4. **Exact evidence:** [WSL test logs, source hashes and native captures](control-center-evidence/wsl-guide/README.md).
   UI tests traverse all five steps with source readers and preference saves
   blocked, verify navigation/return position and optional skip, display an actual
   failed private temporary export read without raw error/path disclosure, retain
   source selections, test first-run non-interruption, checklist switching,
   keyboard focus, narrow layout, fixed navigation bounds and teardown.
5. **Not proved:** source authenticity/availability, deployed enforcement,
   production readiness, service liveness, complete accessibility, recovery or
   independently authenticated timestamps. Browsing every step is not evidence
   that any owner export was selected, any check passed or any setup was saved.
6. **Classification:** implementation, tests and captures Recorded; selected
   source states are existing bounded observations; missing data/enforcement
   Unknown. No Verified/governed claim or completion attestation is created.
7. **Legacy reuse:** Setup Readiness container/cache timer, Source Health and
   Troubleshooting projections, existing source pages, Session setup, navigation,
   theme and lifecycle. No canonical control path copied or writer duplicated.
8. **Temporal transfer:** no reusable authority lesson admitted. No historical
   authority replay or temporal-transfer proof claimed.

## Eight-pass analytical review

| Pass | Finding and boundary |
| --- | --- |
| Flip | A malicious source or confused user cannot inject a guide action or earn a verified state. Fixed step/action definitions; only existing cached status fields enter guide summaries, not raw errors or paths. |
| Reverse | An unintended check/save would need an execution call. Guide actions hold only fixed page navigation; actual reads/checks/saves remain explicit on the original pages. Tests block all readers/save functions during guide traversal. |
| Invert | Reaching step five is not setup success or authority compliance. No completion score, all-clear, checkmark, permission or attestation is issued. |
| Inside-Out | The guide cannot authenticate its UI, source identity or local clock. It labels local receipt and source freshness separately and preserves Unknown service health. |
| Darken | Failed reads, absent exports and skipped connectors remain gaps. No fallback discovery, credential scan, permission repair, retry or automatic connection attempt is introduced. |
| Lighten | A first-time user can explore with no exports and close the guide without an incident or denied-use inference. Existing remembered navigation is respected. |
| Amplify | One bounded five-step position and one skip flag, no new timer/history/file. Repeated return/navigation does not duplicate source readers or preference writes; existing Evidence polling rules remain explicit. |
| Negate | Extend the existing checklist and link to existing tools. A new dashboard, setup executor, credential workflow or persistent completion store is unnecessary. |

Decision: WSL validation and draft review only. No merge or production deployment.
