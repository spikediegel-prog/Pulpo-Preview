# WSL evidence clarity validation

Native inspection used the existing public TEST-ONLY exports from the completed
WSL walkthrough. These are synthetic test observations, not production metrics.
Before and after use fresh sessions, the same frozen export and 1200×950 windows.
Temporary inspection profiles prevent changes to personal setup/preferences.

- `before-summary.png`: previous UI from the actual WSL checkout at `abc6b6a`.
- `after-summary.png`: revised test header, stale-state explanation and summary.
- `after-events.png`, `after-event-details.png`: compact public-reference browser.
- `after-source-details.png`: cached selected-file/last-success information.
- `after-large-text.png`, `after-large-controls.png`: 640×600 at Tk scaling 2.0;
  legends and controls wrap, full explanations remain accessible by scrolling.

Source-read timestamps differ from the frozen owner's timestamp; no freshness is
manufactured. Captures are cropped to the application, without unrelated windows.
The final wording shortened the notes button and test checkbox after the event
screenshots; those fields carry no additional metrics or authority.

`ubuntu-core.log` is the exact final core run, using:

```bash
python scripts/run_pulpo_tests.py --suite core --log-dir ../clarity-core-results
```

The summary records 863 tests and 5 skips: three optional Ed25519 tests require
`pulpo[authority]`, and two require Windows handle/reparse behavior. No dependency
or trust configuration was changed to satisfy those unrelated platform checks.
The runner enables warnings as errors and rejects ResourceWarnings. Core output
was additionally checked for Tk callback exceptions. A separate focused pass ran
136 tests; the final nine clarity tests also passed after larger-text adjustments.

Source hashes use LF-normalized bytes. The core summary redacts the local checkout
path; no source contents, credentials, personal configuration or test database is
included. Existing API, authority and optional session-save boundaries are covered
by the unchanged regression suites. No full screen-reader/DPI certification or
production enforcement result is claimed.
