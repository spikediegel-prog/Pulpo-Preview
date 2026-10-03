# Pulpo Preview — The Mad Lads Playground

Explore upcoming features, share experiments, and help shape what comes next. The Mad Lads Playground is our unofficial preview channel for testing and building excitement before official releases.

This branch in **spikediegel-prog/Pulpo-Preview** is an unofficial preview for testers. It contains unreleased upstream PRs awaiting review. It is not an official Pulpo release or a production-readiness claim. Source PRs remain open upstream, and their review/admission status is unchanged.

## Snapshot: 2026-10-03

**Verified selection:** 18 open, ready-for-review PR heads had all reported GitHub checks passing when inspected. Draft PRs, explicit holds, failed/pending/missing checks, and unverified heads are excluded. The check requirement applies to exact individual PR heads; it is not permission to weaken checks or bypass official review.

**Combined preview:** #230, #235, #237, #238, #249, #275, #276, #277, #289, #293, #294, #295.

**Separate testing only (merge conflicts):** #219, #236, #239, #250, #258, #267. Their exact passing heads are available on this fork as `preview-pr-<number>`. Conflicts were recorded and each merge aborted; no code was invented to resolve them.

Every eligible PR also has an exact-head `preview-pr-<number>` snapshot branch, including those already combined. These branches preserve individual-head provenance and should not be described as combined-preview equivalents.

The [machine-readable manifest](PREVIEW_MANIFEST.json) records PR titles, upstream links, exact commits, check counts, inclusion status, and conflict paths.

## Validation and boundaries

**Verified local execution:** the combined code at `60f73fb0fa04703e711a94d89662237cf93b403e` passed **445 tests**, warnings treated as errors, in 20.146s using Python 3.14.4 in a clean Linux clone under Ubuntu/WSL. [Captured log](perf-results/preview-unit-tests-20261003.log).

The first attempt in a Windows-created worktree had three Linux Git metadata errors; its result was not promoted to passing evidence. A separate Linux-native clone corrected the checkout boundary without changing source.

**Verified historical hosted execution:** [run 37142797818](https://github.com/spikediegel-prog/Pulpo-Preview/actions/runs/37142797818) completed successfully at `60d0a196da44702e3876143e6268e16a9b825257`, before the Dark Mirror repair below. This evidence does not cover later commits. Passing individual-head checks do not prove interactions between PRs; unit tests do not replace all workflow proofs. Physical hardware performance, independent tester reproduction, and production containment remain **Unknown**.

## Dark Mirror Windows repair

The preview now also includes the local repair committed at `3195479663a837f66b2fda58bc43fb9992812767`. It is a preview-specific change, separate from the exact upstream PR snapshot branches.

**Verified diagnosis and repair:** SQLiteBudgetAccount's connection context managers handled transaction exit but left database handles open. Every per-operation connection now closes after its existing transaction context exits, including denial paths; setup failures close the connection too. The Dark Mirror tampering test now actually changes the result for both passing and blocked packets. The runner still requires all eight real cases to pass before producing a Verified claim. Budget limits, replay protections, WAL, FULL synchronization, BEGIN IMMEDIATE, and transaction commit/rollback semantics are preserved; no new authority or canonical writer is introduced.

**Verified Windows execution of the repaired source:** Python 3.12.10, warnings treated as errors. All 32 focused Dark Mirror/commerce/custody execution/reconciliation tests passed in 3.204s, including all three Dark Mirror tests. The full suite ran 446 tests in 51.481s: **9 failures, 54 errors, 5 skips**. The preceding tester run recorded 445 tests with 10 failures, 121 errors, and 5 skips. Diagnostic counts fluctuate; every remaining failing/erroring test identity was already present in the original stored Windows baseline. Windows MCP, artifact access, temporary-file/SQLite cleanup, path/mode and Git-cleanliness issues remain unresolved. This is not a passing full Windows suite.

The execution happened before the code commit, against its identical three-file patch on base `60d0a196da44702e3876143e6268e16a9b825257`. See the [full Windows log](perf-results/dark-mirror-windows-full-tests.log) and [repair review](perf-results/dark-mirror-fix-review.txt). Hosted validation of the repaired head must be checked independently. Performance impact and external reproduction of this repair remain **Unknown**.

The [Unofficial Preview Validation workflow](.github/workflows/preview-validation.yml) runs the existing CI jobs for pushes to `preview`; fork Actions may require enabling from the repository Actions tab. Consult this fork's latest run rather than assuming upstream results cover this combined head.

## Test this preview

```powershell
git clone --branch preview https://github.com/spikediegel-prog/Pulpo-Preview.git Pulpo-preview
cd Pulpo-preview
python -W error -m unittest discover -s tests -v
python -m pulpo.cli setup --json-report perf-results/pulpo-preview-setup.json
```

## Setup/bootstrap included in this branch

**Verified source presence:** this preview contains `pulpo/setup.py`, the `pulpo setup` console command, and `tests/test_setup.py`. Install the Python package from the cloned preview, then run the bootstrap:

```powershell
python -m pip install -e .
pulpo setup --json-report perf-results/pulpo-preview-setup.json
```

Python 3.11 or later is required. Setup detects the host, validates or builds a machine-bound performance profile, and checks a valid and tampered synthetic audit. It does not deploy production authority, install a Windows service, or claim production readiness. A portable Windows `.exe` build is now available through the [Windows executable workflow and tester guide](docs/WINDOWS_PREVIEW_EXE.md). It bundles this setup CLI; it is not an MSI installer or a full Windows feature-validation claim.

For an isolated PR, choose its snapshot at clone time, for example:

```powershell
git clone --branch preview-pr-295 https://github.com/spikediegel-prog/Pulpo-Preview.git Pulpo-pr-295
```

Record the checked-out commit, platform/Python/SQLite versions, full test log, reproduction steps, and expected/actual result when reporting a failure. Keep preview-specific failures separate from upstream recorded pre-existing failures. Windows filesystem/resource differences can matter; do not hide errors merely because a Linux run passed.

Official development and releases remain at [Ironnember/Pulpo1.0](https://github.com/Ironnember/Pulpo1.0). Your fork's `main` is not changed by this preview.

## Updating the preview

This is a dated snapshot, not an automatically updating channel. For the next snapshot: refresh upstream main and PR head/check evidence, reject drafts/holds and nonpassing checks, combine only compatible changes, rerun combined validation, and publish a new manifest. Preserve review and governance invariants throughout. Official merge/release approval remains separate.

Incremental SQL/component efficiency changes should be benchmarked and externally reproduced before stacking the next optimization. No governance invariant is weakened for performance. Do not execute live-provider ceremonies or supply production credentials merely to try this preview.

## Local-copy comparison and checkpoint update

See [local vs PR comparison](LOCAL_PR_COMPARISON.md). The original local SQLite checkout is included. A historical evidence-only tag supplies the exact checkpoint missing from the first hosted test run. Later hosted validation passed at the exact historical head linked above; the Dark Mirror repair has separate evidence and requires its own hosted run.
