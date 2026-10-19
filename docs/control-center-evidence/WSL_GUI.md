# WSLg native GUI follow-up

Claim: **Verified**, limited to this local WSLg session and the tests below.
Base: merged UI commit `3dd1b9ce42a85f80257eb53fa5f9f15a03df0158`.

Environment: Ubuntu WSL2, Linux 6.18.33.2-microsoft-standard-WSL2, Python 3.14.4,
Tcl/Tk 8.6.17, DISPLAY=:0, WAYLAND_DISPLAY=wayland-0. Installed Ubuntu's standard
`python3-tk` package and its five dependencies to enable native graphical tests.
No application service, deployment configuration or credential was installed.

## Result

All **36** focused tests pass with **zero skips**, including the four GUI cases
that previously skipped on Linux. The GUI construction smoke check also passes.
The five UI/profile cases pass on Windows after the cleanup change.

```text
python3 -W error -m unittest tests.test_control_center tests.test_evidence_tuning tests.test_setup -v
python3 -m pulpo.cli tune --gui-check
python3 -m pulpo.cli tune --profile ../wsl-ui-test-profile.json
```

Visually inspected actual WSLg windows: Overview, Governance, Evidence and
Activity. Alt+1 and Alt+5 navigate correctly. Both status cards remain Unknown.
An explicit comparison sends session output to Activity and reports canonical
equality PASS on the disposable 64-file fixture. The separate test-profile file
remains absent before and after that comparison. Resizing the live WSLg window
to approximately the minimum width wraps text and keeps Activity scrollable.
Automated tests additionally verify narrow Overview stacking/scroll, repeated
navigation without state writes, failed comparison recovery and explicit save
to a temporary profile. No actual canonical user state or authority is touched.

## Cleanup correction

The first WSL GUI run passed assertions but printed `invalid command name ...poll`
between test windows. Destroying the window deleted the registered Tcl callback
without cancelling its queued timer. A subsequent Tk event loop encountered the
orphan. The app now tracks its own poll timer and cancels it when the root is
destroyed, including explicit close and the test harness's destruction path.
A regression assertion verifies no scheduled callback survives root destruction.
The same assertion fails on the exact pre-fix `tuning_app.py` from the base
commit, loaded in a separate test process with the current test case; that
transcript is `wsl-cleanup-regression-before.log`.
The final WSL transcript has no invalid-command, traceback or resource-warning
messages; no settings or canonical API behavior changes.

## Authority and evidence boundary

Authority and canonical mutations: unchanged; none introduced or exposed.
Flip/Reverse: only the window's owned timer is cancelled, never another
operation's callback. Invert: assert successful teardown, not just passing
operation results. Inside-Out: session output remains distinct from canonical
audit. Darken: destruction with a queued poll is covered. Lighten: the original
message is a UI lifecycle defect, not a governance failure. Amplify: repeated
windows leave no timer behind. Negate: use existing Tk cancellation, without a
new worker, listener, credential or authority surface.

Screen-reader support, high-DPI variants, all Linux desktops and packaged Ubuntu
distribution remain unqualified. The earlier full core run's three resource
warnings are separate, documented issues; this focused follow-up does not claim
that gate is green or rerun it. The existing tuning control path is retained.
No general historical-transfer lesson is admitted by this bounded lifecycle fix.
