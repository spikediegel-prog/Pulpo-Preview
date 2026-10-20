# Isolated test evidence

Validation performed in Ubuntu WSL, not the user's separate Hyper-V VM.

`ubuntu-tests.log` records 58 tests, with 2 platform-specific Windows skips, using
`python -W error -m unittest tests.test_observation_test tests.test_kernel
tests.test_mcp_boundary tests.test_mcp_plugin tests.test_evidence_observation
tests.test_governance_observer -v`.

Native before/after inspection used the existing Control Center and these actual
test-generated exports. An inspection harness used temporary UI preferences,
selected only the explicit public exports and added the visible TEST ONLY window
title/caption. That harness label is not a shipped UI feature or authenticated
source label. The normal UI displays TEST-ONLY paths and its existing provenance
and enforcement limitations. No personal source selection or saved setup was
changed.

- `evidence-before.png`: no source, unknown metrics and health.
- `test-evidence-live.png`: actual test SQLite reads/writes/commits and health.
- `test-evidence-counters.png`: recorded test counts, Unknown AI usage and event references.
- `test-governance.png`: source audit report, enforcement explicitly unassessed.
- `test-evidence-stale.png`: test stopped; current rates become Unknown and health loses its positive current status, labeled stale.

The workload ran for 60 bounded cycles, using the same canonical APIs as the
regressions. No external effect was executed. The private temporary database was
removed on normal exit; public exports remained. Source hashes bind the new code
and tests to the recorded test log. These checks do not certify production
deployment, VM networking or a new trust boundary.
