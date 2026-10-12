# Service and tuning-window validation

Verified locally after filling the previously recorded gaps:

- Authority service: 67 tests pass with no skips and zero resource warnings,
  including all four real PostgreSQL integration tests.
- Custody service: 26 tests pass with zero resource warnings.
- GUI: standard Tk construction passes, and the actual tuning window constructs
  in a hidden test with serial-default, opt-in helper, comparison and apply
  controls present. The test writes no settings and destroys the window.
- 42 focused Tcl-path, tuning, connection and lifecycle tests pass.

## Dependencies and database isolation

Dependencies were installed in the checkout's `.venv`, using the exact direct
pins in both service pyprojects and their test extras. The environment list is
saved with the validation evidence. Python's shared environment was unchanged.
Short workspace temporary paths avoid Windows' editable-build path-length limit.

Four authority tests require a real PostgreSQL database and otherwise skip.
They ran against a fresh authenticated instance of portable PostgreSQL 18.6
bound to 127.0.0.1 on a dynamically selected port, using a new fixture database.
The runner verifies its unique data directory before tests. Existing databases
and DSNs are not used. The test's table resets apply only to that fixture.
Server shutdown is confirmed in `stop.log` and `fixture.json`. Test databases
remain stopped in the workspace for inspection; no Windows service is installed.
The portable archive came from [EDB's binary distribution](https://www.enterprisedb.com/download-postgresql-binaries),
and its URL and observed SHA-256 are recorded. This is a disposable test fixture,
not production database or power-loss validation.

The authority restart acceptance adapter had four operation-owned SQLite
transaction contexts that committed/rolled back without closing. They now use
`closing(connection), connection`, preserving transaction exit before close.
Active borrowed connections retain their existing lifetime. The tamper fixture
connection also closes. Regression tests assert closed connections after
initialization and restart; existing restart, interrupted evidence and concurrent
instance tests pass unchanged.
Transaction-lock cleanup now also handles interruption/SystemExit paths; an
interrupted-entry regression verifies the connection closes and another thread
can acquire the released mutex. The exception is propagated rather than suppressed.

## Tcl/Tk startup

This checkout uses a custom bundled Python environment. Its Tcl DLL and data
versions match, but native Tcl cannot resolve the same absolute paths as Python.
A checkout-local copy of Tcl/Tk data works with normalized relative paths.

The tuning app now sets library paths before importing Tk or `_tkinter`.
Importing `_tkinter` first was insufficient because it can initialize Tcl's
environment before the paths are set. Existing explicit environment choices
are retained. The resolver recognizes frozen `_tcl_data`/`_tk_data` directories
and local `sys.prefix/tcl` layouts; only pairs with `init.tcl` and `tk.tcl` are
selected. Missing runtime data is not silently fabricated.

The PowerShell `Launch-Pulpo-Tuning.ps1` prepares data inside this checkout and
starts the source tuning app. `-Check` runs the construction smoke check instead.
The shared Python installation and global environment are not rewritten.
The separate packaged executable was not rebuilt by this task.

## Analytical boundary review

Flip/Inside-Out: runtime library discovery stays in the trusted Python/bundle
roots; user-provided paths remain explicit choices. It exposes no new governed
writer or authority. Reverse/Invert: library startup and service cleanup cannot
authorize approval, fabricate evidence or declare a failed test successful.
Darken: failed SQL operations retain rollback; existing tamper and concurrent
restart tests pass, and explicit library paths remain respected. Lighten:
the environment mismatch is resolved without blaming absent files. Amplify:
operation connections close deterministically instead of accumulating locks;
Tcl setup precedes initialization on every new GUI process. Negate: local runtime
data and a disposable database avoid global installation or live-account access.

These new service cleanup/Tcl source fixes have local validation. Earlier full
Linux validation precedes them; the refreshed kit includes their portable unit
tests, while Linux service integration still needs its test dependencies.
