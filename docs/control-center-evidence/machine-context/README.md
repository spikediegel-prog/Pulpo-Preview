# Machine context validation

Native before/after inspection used the same two already-copied public VM
TEST-ONLY exports. No new VM connection, credential or production state read was
used. Temporary inspection profiles avoided personal setup/preference changes.

- `before-evidence.png`: actual WSL checkout at `a1b7587`, 1200×950.
- `after-evidence.png`: WSL resource scope, an explicitly applied inspection
  description `Pulpo-OS-Dev` (operator description; unverified), old source data
  versus a fresh local read. The helper supplied this operator label from the
  user's description; the application did not discover or authenticate the VM.
- `after-paused-ages.png`: after pausing, the last-read age advances while no new
  source read occurs; source-data age still derives from the frozen owner time.
- Other after captures show Sources and the narrow larger-text view. All captures
  are cropped to the application. Unknown or stale rates are not fabricated.

The final core command was:

```bash
python scripts/run_pulpo_tests.py --suite core --log-dir ../machine-context-core-results
```

The exact log and summary record 872 tests with 5 skips: three optional Ed25519
checks require `pulpo[authority]`, and two require Windows handle/reparse behavior.
Warnings run as errors; the packaged log was checked for ResourceWarnings and Tk
callback exceptions. The targeted machine/clarity checks also passed 18 tests.
Source hashes bind the final five changed source/test files and exact core log.

Checks establish only the recorded cache/read/time distinction and native UI
behavior. They do not authenticate clocks or exporter identity, prove production
enforcement, or certify all fonts, display scales and screen readers. No schema,
API, optional preference format, merge or deployment was changed.
