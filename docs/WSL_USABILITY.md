# WSL navigation and resource readability

This increment groups existing System views and replaces the long resource-graph
caption with a compact strip in Overview and System Diagnostics. It retains the
charcoal/purple/soft-white theme, existing readers, sampling cadence, APIs,
performance controls and authority boundaries. Non-WSL keeps the original three
System buttons and resource caption; no Windows qualification is added.

## System areas

| Area | Existing view names, retained for navigation and saved preferences |
| --- | --- |
| Monitor | Diagnostics, Source health, Troubleshooting |
| Set up | Setup readiness, Session setup |
| Tune | Configuration, Tuning & benchmarks |

The area buttons show only their related secondary views. Short button labels
(Sources, Troubleshoot, Guide & checklist, Remember setup, Compare settings,
Benchmarks) accompany the unchanged full view name in a visible location line.
Returning to an area recalls its most recently selected view in this window.
This recall is ephemeral, not an additional persisted setting.

Existing `select_mode` names, source-page handoffs, guide return, troubleshooting
links, `tabs` keys/buttons and saved `system_tab` values continue to work. Direct
navigation to a view selects the appropriate area automatically. The existing
session format does not change or migrate. Unsupported view/group names are
rejected. Group navigation does not read exports, save preferences or start a
benchmark; normal existing Diagnostics resource sampling remains governed by its
active-page rules.

Both button rows and the resource graph range controls reflow based on actual requested control widths, rather than
assuming short text or one font size. Inactive-area buttons are unmapped and
leave normal keyboard traversal. The location line makes current area/view
readable without relying solely on selected-button color. Existing focus borders
and keyboard-focusable buttons are retained.

## Compact resource strip

The collapsed strip shows WSL resources, relative sample age and the retained
sample-history span. A text-labeled legend shows Normal, Elevated, High and
Unknown using readable purple/amber/red/gray shades on the light content surface.
It is a legend, not an aggregate status or health score. Thresholds remain the
existing resource hints: below 75%, 75% to below 90%, and 90% or above. High is the
existing Attention category in status rows; no severity calculation changes.

Details expands inline through a standard keyboard-focusable button, whose text
changes to Hide details. It reveals the exact local sample timestamp and zone,
reported resource source and volume, Linux VM scope, thresholds, missing-reading
behavior and the limits of session history. Missing/invalid measurements stay
Unknown and graph gaps remain gaps. No host/fleet/service/enforcement health is
inferred. History is retained sample span, possibly containing gaps, not uptime
or continuous observation coverage.

Age and span use the existing sample's monotonic time. Missing, future or
non-finite time values are not displayed as a current/zero measurement. The
local wall-clock timestamp remains in Details, separately labeled. A bounded
one-second display timer updates age from the last cached sample only. It adds
no resource/source read, provider request, scan or persistence. The existing
sampler still runs on its existing cadence. Page deactivation, unmapping and
root teardown cancel the display timer; mapping/activation resumes it. Paused
samples remain labeled as paused. No hard resource-read deadline is added.

The strip wraps its summary and legend at narrow widths and places Details on
its own row when enlarged labels do not fit beside it. Graph scale captions wrap
rather than losing their units/range labels. Expanded details remain
in the existing vertical scroll surface. Existing graph metrics and ranges are
unchanged; no placeholder metrics, smoothed history or inferred values are added.

## Required change record

1. **Invariant:** readable status/navigation cannot manufacture current readings,
   erase gaps, change source freshness or promote resource hints to governance.
   Regrouping must preserve direct links, existing controls and saved choices.
2. **Authority:** unchanged. No kernel, signer, canonical writer, provider client,
   state backend, OS setting or credential capability added or retained.
3. **Canonical mutations:** none. New state is ephemeral area recall, Details
   expansion and cached age presentation. The sampler/readers/writers remain on
   existing paths; resource samples, thresholds and session schema are unchanged.
4. **Evidence:** [exact WSL logs, hashes and native before/after captures](control-center-evidence/wsl-usability/README.md).
   Tests cover missing/invalid/future timing, real cached duration, paused age,
   cache-only Details, timer lifecycle, direct links/group recall, source-read and
   save blocking during navigation, narrow/larger-button reflow, full Tk text
   scaling with all graph ranges and strip controls inside the window, and teardown.
   Existing tests retain source failure/freshness, guided setup and saved-session
   coverage under the new grouping.
5. **Not proved:** complete accessibility, every DPI/font/window combination,
   authenticated time/source provenance, production/service readiness, fleet
   health or governance enforcement. No canonical performance benchmark is run
   or new sampling/retention policy claimed.
6. **Classification:** implementation/tests/captures Recorded; resource values
   remain local observations, missing data and enforcement Unknown. Relative age
   is local presentation, not source authentication or an authority timestamp.
7. **Legacy reuse:** unchanged System views/keys, session format, navigation
   callbacks, ResourceSample/history/sampler/thresholds, theme/focus patterns and
   guide/source/troubleshooting handoffs. No canonical control path copied.
8. **Temporal transfer:** no reusable authority lesson admitted; no historical
   authority replay or temporal-transfer proof claimed.

## Eight-pass analytical review

| Pass | Finding and boundary |
| --- | --- |
| Flip | A misleading legend or caption could imply health. Text labels, explicit scope/thresholds and Unknown preserve the existing observation boundary; no all-clear aggregate is computed. |
| Reverse | An accidental action would require calling a reader/writer/benchmark. Area buttons call only existing navigation; Details renders cached sample data. Tests block source reads/saves through group navigation. |
| Invert | Cleaner controls or normal utilization are not proof of enforcement. Exact sample time, VM scope and gaps remain available; failed/missing source observations are unchanged. |
| Inside-Out | Relative age does not authenticate the UI clock or source. Monotonic timing supports only this session's presentation; wall-clock details are recorded local time. |
| Darken | Future/missing/invalid time must not become Updated just now; hidden groups must not leave stray focus targets; age timers must stop. Covered by model/UI/lifecycle tests. |
| Lighten | A paused graph or missing first CPU sample is ordinary observation scope, not an outage or permission failure. No repair or retry is inferred. |
| Amplify | Fixed three groups, bounded area recall, one display timer per resource monitor and existing bounded history. No additional sampling, source polling, history store or auto-save. |
| Negate | Reuse existing views and sample caches. A new service, navigation router, telemetry pipeline or metrics estimator is unnecessary. |

Decision: WSL validation and draft review only. No merge or production deployment.
