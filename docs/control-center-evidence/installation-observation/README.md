# Local installation observation validation

Scope: explicitly invoked fixed read-check application, not production owner
enrollment or a Control Center runtime change. No native VM or installed system
package was accessed by these agent-run tests.

## Test results

- WSL Ubuntu, Python 3.14.4: `python3 -W error scripts/run_unit_tests.py` completed
  906 tests: 904 passed, two Windows-only handle/reparse checks skipped. HOME and
  XDG_CONFIG_HOME were isolated. `unit-tests.log` and `summary.json` record the
  exact output and log hash. This is the core zero-dependency unit selection;
  separate authority-service/Postgres/container CI jobs were not run locally.
- Eight new installation-observation tests passed, including protected path/type
  checks, missing/damaged files without repair, manifest scope change before
  publication, duplicate/escaped manifest entries, gate-before-read denial and
  failed consumption, bounded/root refusal, untouched fixture bytes, compatible
  public exports and closed/removed private run state.
- The extracted Ubuntu preview installer fixture contained 49 manifested files.
  Two cycles matched all 49, reading 2,126,112 actual bytes per cycle. Its
  canonical audit observations reported 98 allowed and 98 consumed, zero denied
  and zero rejected; no fake adversarial traffic was inserted into this run.
  The standalone Control Center readers accepted both exports. File hashes
  before/after the fixture were unchanged; private run state was removed.
- `package-fixture.json` binds the check to installer SHA-256
  `44e6a1debcb67b6dd246f2098d6f0c29a8dbb29ffc9a0c9e0b38544ac3745ab3`.
  The test alone redirected the fixed system root and expected owner UID to the
  extracted fixture. No such path/UID override is exposed by the utility CLI.

## Limits

This is executable evidence for the tested local application and file fixture.
It does not establish independent deployment/authority, hostile-process or
host containment, source authenticity, provider enforcement or production
readiness. Installed-manifest comparison is not publisher authentication.
Private state cleanup is tested for normal/handled outcomes, not hard power loss.
No Control Center visual change was made or visually qualified. Actual native
VM source selection and use remain pending operator execution after review.
No workload, service, package update, merge or release was deployed.

See [workload contract and operator steps](../../LOCAL_INSTALLATION_OBSERVATION.md)
for the eight-point change record and eight-pass analytical review.
