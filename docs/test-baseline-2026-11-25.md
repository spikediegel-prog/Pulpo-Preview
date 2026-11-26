# Full-suite test baseline — 2026-11-25

Recorded so that no later PR has to assert from memory that the full-suite
failures are pre-existing. The claim is checkable: run the two commands
below and compare the failure sets.

## Baseline

- **Baseline commit:** `19556af` (main after merging PR #154,
  the Gladiator verdict-echo hardening)
- **Command (full suite):** `python3 -m unittest discover -s tests -t .`
- **Command (failing modules only):**
  `python3 -m unittest tests.test_disk_installer
  tests.test_installation_observation tests.test_authority_client
  tests.test_ceremony_evidence tests.test_external_response_bounds
  tests.test_disk_service_recovery tests.test_accountability_context`

## Results

| Run | Tests | Failures | Errors | Skipped | Expected failures |
| --- | --- | --- | --- | --- | --- |
| Full suite, 19556af + verdict-echo hardening-2 patch | 1751 | 14 | 17 | 94 | 1 |
| Failing modules only, pristine 19556af checkout | 203 | 14 | 17 | 13 | 0 |

The failure sets are identical. The one line that differs between the two
runs is a loader naming artifact, not a different failure:
`tests.test_accountability_context` (full-suite discovery) vs
`test_accountability_context` (subset run) — the same module failing to
load, counted as one error in both runs.

## Failing tests (31)

### `tests.test_disk_installer` — 13 failures

- `PulpoConfigScriptTests.test_bad_config_fails_the_install`
- `PulpoConfigScriptTests.test_config_is_copied_and_imported`
- `InstallCcDebTests.test_main_fails_when_bundle_missing`
- `VerifyInitramfsTests.test_main_fails_with_no_initrd`
- `InstallCcDebTests.test_main_writes_step_log_on_verify_failure`
- `PulpoConfigScriptTests.test_missing_zoneinfo_warns_and_proceeds`
- `PulpoConfigScriptTests.test_no_config_warns_and_proceeds`
- `PulpoConfigScriptTests.test_no_interface_retries_with_fallback_and_proceeds`
- `PulpoConfigScriptTests.test_saved_timezone_is_applied_to_target`
- `TrustLauncherTests.test_script_is_world_readable`
- `InstallCcDebTests.test_verify_release_installs_expired_but_authentic_release_and_logs_notice`
- `InstallCcDebTests.test_verify_release_refuses_unverified_release`
- `PulpoConfigScriptTests.test_written_configs_are_private_files_the_app_will_load`

### `tests.test_installation_observation` — 1 failure, 2 errors

- FAIL `InstallationObservationTests.test_changed_manifest_stops_without_new_export`
- ERROR `InstallationObservationTests.test_actual_package_reads_and_exports_remain_private_and_state_is_removed`
- ERROR `InstallationObservationTests.test_private_state_and_exports_are_not_allocated_without_installed_manifest`

### `tests.test_authority_client` — 8 errors

- `AuthorityClientTests.test_approved_poll_parses_ceremony_evidence`
- `AuthorityClientTests.test_approved_poll_parses_exact_envelope`
- `AuthorityClientTests.test_client_exposes_only_request_and_poll`
- `AuthorityClientTests.test_https_transport_rejects_oversized_response`
- `AuthorityClientTests.test_malformed_ceremony_evidence_is_not_silently_discarded`
- `AuthorityClientTests.test_non_https_and_cross_origin_human_urls_fail_closed`
- `AuthorityClientTests.test_request_and_poll_use_only_fixed_worker_paths`
- `AuthorityClientTests.test_request_validates_optional_provenance_hash`

### `tests.test_ceremony_evidence` — 1 error

- `CeremonyEvidenceTests.test_authority_poll_and_orchestrator_forward_ceremony_evidence`

### `tests.test_external_response_bounds` — 4 errors

- `ExternalResponseBoundsTests.test_authority_rejects_depth_items_and_parser_recursion` (length=23504)
- `ExternalResponseBoundsTests.test_authority_rejects_depth_items_and_parser_recursion` (length=330)
- `ExternalResponseBoundsTests.test_authority_rejects_depth_items_and_parser_recursion` (length=4030)
- `ExternalResponseBoundsTests.test_namecom_bounds_success_and_http_error_reads_and_closes_both`

### `tests.test_disk_service_recovery` — 1 error

- `DiskRecoveryTests.test_saved_state_survives_two_fresh_processes_with_exact_audit_prefix`

### `tests.test_accountability_context` — 1 error (module fails to load)

- `unittest.loader._FailedTest`

## What this establishes — and does not

- **Establishes:** the 14 failures + 17 errors exist on a pristine
  checkout of the baseline commit, with no echo changes present, and
  the same set appears with the echo patch applied. None of the failing
  modules imports the verdict-echo module. The echo's own suites
  (`test_gladiator_verdict_echo`, `test_gladiator_gate`,
  `test_gladiator_audit_projection`) pass: 66 tests.
- **Does not establish:** why these tests fail, whether they fail on
  other machines or in CI, or that they are safe to ignore. They are
  pre-existing, not proven unrelated to anything else — the claim is
  only that this patch did not cause them. Fixing them is separate work.

## Resolved — 2026-11-26 (PR: fix/live-environment-test-failures, main 30f74a9)

All 31 failures were environmental, not logic bugs — the same suite
passes on CI's non-root runner with no ambient CA variables and a
disk-backed temp dir. Fixed in six groups; production code untouched
(`pulpo/transport.py`'s fail-closed guard is unchanged and still
covered by `test_transport_security` and `test_linux_network_readiness`):

- **Ambient CA bundle (13):** `test_authority_client` (8),
  `test_ceremony_evidence` (1), `test_external_response_bounds` (4).
  The tests strip ambient CA/proxy controls with the repo's own
  `sanitized_transport_environment()` around client/transport
  construction. The transports are mocks; no real connection is made.
- **Root refusal (3):** `test_installation_observation`. The app
  refuses root by design. The suite must run as a non-root user, as
  CI does.
- **Missing `ubuntu` user (11):** `test_disk_installer`
  (PulpoConfigScriptTests + InstallCcDebTests). The tests now set
  `PULPO_IMPORT_USER` / `PULPO_VERIFY_USER` to the current user — the
  contract the Calamares scripts already document. Needs a non-root
  user that exists in the live session.
- **Script mode (1):** `TrustLauncherTests.test_script_is_world_readable`.
  No repo change: git records 755. A checkout under umask 0007 lands
  the file at 770; a normal (022) checkout is 755 and the test passes.
- **Initramfs tools (1):** `VerifyInitramfsTests.test_main_fails_with_no_initrd`
  now skips when neither `lsinitramfs` nor `unmkinitramfs` is
  installed, like its siblings.
- **Tmpfs fixture (1):** `test_disk_service_recovery`.
  `disk_mount_observation()` now reads the topmost `findmnt` entry:
  container runtimes can stack mounts at the same target, and the
  serving mount is the one that decides disk vs volatile. The
  volatile-fstype rejection is unchanged.
- **Loader artifact (1):** `test_accountability_context` fails to load
  only under `discover -s tests -t .` (top-level dir = repo root); the
  CI-style runner (`scripts/run_unit_tests.py`, top-level dir =
  `tests`) imports it. Not a test failure; use the CI-style runner.

## How to run the suite green

- As a **non-root** user that owns the checkout (as CI's `runner` does).
- With a **normal umask (022)** at checkout, or `chmod 755` on the
  Calamares scripts if a restrictive umask stripped the other-read bit.
- Command: `python3 -W error scripts/run_unit_tests.py`
- Full-suite result on the fix branch, non-root testuser-owned clone:
  **1776 tests, 0 failures, 0 errors, 95 skipped, 1 expected failure**
  (the 95 skips are the environment-gated tests: initramfs tools
  absent, real Control Center not installed, and similar).
