# Preview Control Center: incremental native refinement

Status: Proposed implementation; authority unchanged.

This records the initial UI increment. The later [native resource overview](NATIVE_RESOURCE_OVERVIEW.md)
adds read-only local OS counters and bounded session graphs above expandable
status rows. Its source/read scope and validation supersede the initial
profile-only observation scope described below; authority boundaries stay intact.

## Inspection before implementation

Canonical base: `ff2a4821035b62a99b31d5a4647b0dd4309d9954` on main.
The only general local GUI is `pulpo/tuning_app.py`, opened by `pulpo tune`.
It is a Tk performance tool, not an Ubuntu dashboard. The separate human
authority-service UI is a different trust surface and must not be combined.
The Ubuntu branches add CLI guidance/doctor, not a canonical dashboard API.
The existing tuning window was visually inspected on Windows before editing:
920 x 610, tuning controls above an empty output area, six actions in one row.

## Alternatives considered before changing the UI

1. Extend the existing Tk window (selected): no new runtime dependency, listener,
   credential custody or API; reuse the current entry point and tuning callbacks.
   Native accessibility and Ubuntu scaling still require platform qualification.
2. Local browser dashboard: stronger responsive styling, but would introduce a
   server, packaging, origin/authentication and lifecycle work without an existing
   dashboard API. Defer until native refinement has been evaluated.
3. Qt desktop rewrite: richer widgets, but a large dependency/packaging migration
   with no demonstrated need. Do not rewrite for this iteration.

Use UniFi only as a usability reference: stable labeled navigation, overview
before detail, and easy-to-find logs/diagnostics. No visual assets, branding,
source code or control path are copied. References:
https://help.ui.com/hc/en-us/articles/33349041044119-UniFi-System-Logs-SIEM-Integration
https://help.ui.com/hc/en-us/articles/360049956374-Getting-Support-Files-and-Logs

## Scope and truth contract

Refine the existing native UI with Overview, Connections, Governance, Activity,
Evidence and System navigation. Preserve the existing `launch(profile)`, CLI,
settings validation, benchmark and export paths. No new endpoint or canonical
writer. The window holds only local performance settings and disposable results.
Activity means this window's session messages, never the canonical audit.
No backend supplies connection or enforcement observations: both are Unknown.
Even a future successful connection must not imply verified enforcement.
Synthetic collector equality checks establish only their bounded fixture result.
No invented traffic, uptime, agent count, compliance score or governance metric.

First run opens Overview with explicit next steps; no background benchmark,
setup, service discovery, credential scan or settings write. Missing/invalid
profiles use the existing complete serial fallback and show the fallback reason.
Settings edits remain explicit and validated by existing functions. Pages should
reflow, remain keyboard reachable, retain visible focus, and use status words
alongside color. A shared palette can be revised without changing behavior.

The user specified charcoal, restrained purple accents and soft white.
Use charcoal `#242329`, purple `#674396`, soft white `#F5F4F7` and a near-white
activity surface. Amber/red communicate caution/error with explicit text.

## Authority and adversarial review

Authority delta: unchanged. No canonical state mutation is introduced or exposed.
The pre-existing explicit performance-save/undo paths still write only local
non-authoritative hints after fresh checks; comparisons use disposable fixtures.
No kernel, executor, canonical state backend, signer, human credential or client
is retained by the shell. Reading the local performance profile is the only
file observation on startup. No autonomous service discovery or setup occurs.

- Flip: hostile profile data cannot supply commands, handlers or a Verified flag;
  the existing strict parser rejects unknown fields and falls back to serial.
- Reverse: false governance assurance is prevented at the presentation boundary:
  connection and enforcement each remain Unknown, independently of local results.
- Invert: successful fixture equality is labeled a disposable measurement;
  it cannot become a deployment enforcement or production-readiness claim.
- Inside-Out: session Activity is explicitly separate from canonical audit;
  the window has no canonical writer to manufacture supporting records.
- Darken: missing, corrupt, oversize, stale and unreadable profiles preserve
  complete serial fallback. Failed comparison returns controls to usable state.
- Lighten: an absent local hint is a normal first-run condition, not a breached
  deployment or a failed governance system.
- Amplify: repeated navigation/refresh is non-mutating; the session buffer is
  bounded to 500 lines and the existing operation guard prevents overlap.
- Negate: retain Tk, the CLI, existing settings and fixture functions; avoid a
  network listener, credential-bearing adapter or second authority plane.

Legacy behavior source: only this repository's tuning window; existing callback
control paths are retained. UniFi supplies information-organization references
only. No general reusable governance lesson is admitted: historical checkpoints
exist, but cross-checkpoint temporal transfer was not performed or claimed.

## Qualification limits

Before/after native visual inspection was on Windows with bundled Tk 8.6.
Keyboard navigation, focus, resize and status wording are covered; the Windows
accessibility tree exposes many Tk widgets as panes, so screen-reader support is
not qualified. `pulpo tune --show` remains available as structured terminal text.
Ubuntu CLI/profile/core regression evidence does not prove Ubuntu desktop visual
behavior: the initial Ubuntu interpreter lacked tkinter and no native desktop
visual claim was made in the initial review. A later [WSLg native follow-up](control-center-evidence/WSL_GUI.md)
installs Tk, passes all 36 focused checks without skips and verifies the desktop
layout and resize behavior. High-DPI and assistive-technology checks remain
review items. No merge, deployment, provider connection,
authority enrollment, real canonical audit verification or live containment test
is performed by this change.
