# Glass-inspired Control Center appearance

Status: **Recorded implementation, native inspection and regression evidence.**
Base: `fb382ba7b2a763896c2dfbc48c3ccc387da2853f`.

The existing native Tk UI remains suitable. This increment adds a consistent
charcoal header/sidebar, restrained purple selection and focus, a pale neutral
workspace, soft-white cards, subtle edges and small fixed shadows. Shared theme
tokens cover inputs, tables, tabs, text selections and scrollbars. Resource,
Evidence and Activity graphs remain fully opaque and retain their existing
series, thresholds, scales, timestamps and missing-data behavior.

The appearance suggests layered glass without real backdrop blur. It uses ordinary
Tk frames and styles, with no desktop sampling, transparency, GNOME extension,
new dependency, GPU effect, animation, timer, worker or system setting. No full
window opacity is reduced, so labels and plots stay crisp. Real compositor blur
is outside this increment; it is not needed to run the Control Center.

The user-supplied Pulpo badge is packaged unchanged in `pulpo/assets/pulpo-badge.png`
and centered immediately above the sidebar motto. Tk displays a smaller cached
image in windows shorter than 720 pixels, keeping navigation and the motto visible.
The 96- and 128-pixel display assets are prepared using Lanczos anti-aliasing and
loaded at their exact size, avoiding Tk's pixel-skipping subsampling. The original
artwork stays unchanged. `scripts/prepare_sidebar_logo.py` uses Pillow only when
regenerating these bundled assets; the application has no Pillow dependency.
The decorative image does not take keyboard focus; unavailable image data does not
prevent diagnostics from opening. Images are released on the UI thread at shutdown.
See the [logo follow-up evidence](control-center-evidence/sidebar-logo/README.md)
for packaging verification and UI regression results after this addition.

The dark header uses a separate wrapped caption; narrow layouts retain stacked
charts, expanded status summaries and the existing page scrolling. Purple focus
outlines and contrasting selection states remain visible. Numeric checks cover
21 key sRGB foreground/background pairs: text and chart labels at least 4.5:1,
control borders and scrollbar thumbs at least 3:1. Decorative panel edges/shadows
are not status indicators. These checks and screenshots are not an accessibility
certification, screen-reader qualification or exhaustive OS/high-DPI test.

See [review evidence](control-center-evidence/appearance/README.md) for actual
Windows before/after, minimum-size screenshots, native Ubuntu WSLg captures,
contrast measurements, retained test logs and source hashes. No new metrics or
connected/governed state is introduced. Resource readings in screenshots are real
session observations from their labeled Windows or WSL environment, taken at
different times; they are not a performance comparison.

## Required change record

1. **Invariant/failure:** visual polish must preserve readable evidence, explicit
   Unknown states and connected-versus-enforcement distinctions. Low-contrast
   scrollbar styling found during inspection was corrected before final capture.
2. **Authority:** unchanged. This increment contains presentation only; no UI
   provider client, credentials, command runner or desktop configuration route.
3. **Canonical mutations:** none introduced or exposed. Existing explicit actions,
   file selection, observation readers and governed boundaries remain unchanged.
4. **Evidence:** native wide/minimum-size inspection, keyboard navigation/scroll,
   numeric contrast checks and existing Windows/Ubuntu regression suites. Existing
   failure, unknown, stale-source, governance, benchmark and Tk lifecycle cases
   run without changes to their assertions. No palette-mirroring tests added.
5. **Limits:** no production-readiness, performance improvement, authenticated
   provider compatibility, source provenance or enforcement claim follows from
   appearance or these tests. Native Ubuntu was inspected through WSLg, not on
   every Ubuntu desktop/compositor combination.
6. **Classification:** implementation, screenshots, contrast and test results are
   Recorded. Enforcement and live API compatibility remain Unknown where they
   were already Unknown.
7. **Legacy reuse:** StatusRow, monitor samplers, graph drawing, navigation,
   observation selection, dialogs and actions retain their existing control
   paths. Shared styling is extracted, not a UI/backend rewrite.
8. **Temporal transfer:** no reusable authority lesson is admitted and no historical
   replay or temporal-transfer proof is claimed. The before view records the
   exact base UI, not a replay of authority or credentials.

## Eight-pass presentation review

Purpose: polish the existing enterprise Control Center without obscuring evidence
or widening its capabilities. Exact outcome: shared glass-inspired opaque styling.
Authority boundary: presentation only; existing trusted-owner operations unchanged.

| Pass | Finding / boundary |
| --- | --- |
| Flip | Styling cannot turn a hostile or dishonest source into trusted evidence. Unknown labels and unassessed enforcement remain explicit. |
| Reverse | A false verified-health conclusion would require changed labels, states or thresholds. These paths are unchanged; selected/purple decoration has no pass/authority meaning. |
| Invert | Visual polish and successful rendering do not count as governance or provider success. No metric is synthesized to fill a graph. |
| Inside-Out | The UI cannot self-attest enforcement through its theme. Background, frame and widget style helpers retain no kernel, provider or canonical writer. |
| Darken | Credible presentation risk: reduced contrast, obscured warnings or clipped content could mislead an operator. Opaque plots, independent text, contrasting controls, reflow tests and native inspection bound this risk; exhaustive accessibility remains unproven. |
| Lighten | A changed resource reading between screenshots is ordinary independent sampling, not evidence of a regression or improvement caused by styling. |
| Amplify | Fixed frame layers add bounded widgets, not polling, animations, worker loops, global desktop effects or new background work. Existing teardown and repeated-navigation tests pass. |
| Negate | Opaque layered panels achieve the requested polish without compositor blur, desktop extensions, transparency or a framework rewrite. |

Decision: continue to draft review. Smallest next proof: reviewer inspection of
the retained native captures and tests. No merge or deployment is part of this
change. Remaining unknowns include untested desktop/DPI/accessibility combinations
and all previously unverified provider or enforcement claims.
