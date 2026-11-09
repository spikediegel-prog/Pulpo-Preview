# Pulpo Preview — The Mad Lads Playground

Customer data handling: see [evidence storage responsibilities](docs/CUSTOMER_EVIDENCE_STORAGE.md).

Explore upcoming features, share experiments, and help shape what comes next. The Mad Lads Playground is our unofficial preview channel for testing and building excitement before official releases.

This branch in **spikediegel-prog/Pulpo-Preview** is an unofficial preview for testers. It contains unreleased upstream PRs awaiting review. It is not an official Pulpo release or a production-readiness claim. Source PRs remain open upstream, and their review/admission status is unchanged.

## Snapshot: 2026-11-08

This is the current snapshot. It supersedes the 2026-11-05 section below as the current record; the 2026-11-05 and 2026-10-03 sections are preserved as history, untouched.

**Fork main recorded:** `9c388e6f3bc674496f3fd6b3fa821fab54d1411a` (merge of PR #79, Nov 5 snapshot refresh). Upstream main re-verified at `f08486305736346750aba1c8c6ad1e3c16e061ca` on 2026-11-08 (still #342, merged 2026-11-05; 0 merges since).

**Ancestry correction — read this first:** the merge-base of Preview main `9c388e6` and upstream main `f084863` is `d674dbb` (2026-09-26), **not** `f084863`. None of the 13 post-Oct-3 upstream main commits is an ancestor of Preview main as a git commit. Content from those commits is present only where the fork re-applied it under different SHAs (for example the ceremony check, present as the fork gate `2c31f78`, not as merged upstream #338). Genuinely absent content includes the Pulpo 3.5 tournament files (#318 / #306), the Phase 1 node proof (`561e64f`), and the incident-response proof (`6b3caac`) — the last of these is vendored inside port PR #93 so #333's fixture has its dependency. The Nov 5 refresh's "0 behind" ancestry claim is corrected here. See the triage record (`preview-needs-triage-2026-11-08.md`, §1).

**What this snapshot records:** the 2026-11-08 port run — **34 open fork PRs (#80–#113)**, one per STILL NEEDED / PARTIALLY item from the triage of 102 upstream PRs (74 open + 28 closed-unmerged: ALREADY IN 12, ALREADY PATCHED 16, PARTIALLY 17, STILL NEEDED 20, NOT NEEDED 29, NEEDS DECISION 8). Band 1: #236→#99, #244→#94, #72→#89, #280→#98, #294→#90. Band 2: #239→#101, #333→#93, #327→#92, #299→#91, #241→#107, #300→#110, #304→#104, #147→#105, #141→#109, #232→#106. Band 3: #341→#80, #306→#102, #305→#82, #309→#83, #292→#86. Remainders: #250→#111, #258→#112, #267→#97, #219→#95, #316→#81, #311→#85, #314→#103, #287→#96, #297→#100, #302→#113, #325→#108, #212→#87, #171→#88. Side-project: #330→#84 (Autonomous/Pi, not Phase II core). Pre-existing fork PRs #48 and #52 remain open and are unrelated to the port run.

**Validation scope — the most important part:** all 34 port PRs are OPEN and none is merged, so there is **NO combined head to validate and NO combined validation is claimed**. Validation is per-branch only, recorded per port in the [machine-readable manifest](PREVIEW_MANIFEST.json): 19 branches ran the full suite (1086–1118 tests, all OK), the rest ran focused tests or, for docs-only ports, tree/file checks. A combined validation run must be re-done after Mike merges, on the merged head, before any combined claim is made. The Nov 5 refresh said the Oct 3 combined set no longer stands; the same holds for any combined claim about this port run — the refreshed manifest stands on its own as a per-branch record.

**Fork main as-is:** the last direct full-suite run of fork main was at `dc38bf2` (1086 tests OK, 66 skipped, 2026-11-05). The only commit between `dc38bf2` and `9c388e6` is the docs-only Nov 5 snapshot refresh (PR #79: `PREVIEW.md` + `PREVIEW_MANIFEST.json` only), so that validation still describes the code at `9c388e6`. No direct bare-main run at `9c388e6` was performed in this refresh — this is a docs-only change, so no test-suite run was needed for it.

**Upstream check status, re-checked live 2026-11-08:** of the 34 upstream heads, 25 report all checks passing, 8 fail only on `admission-hold` (a process/admission gate, not a test failure: #141, #147, #171, #212, #232, #311, #314, #325), and 1 fails real tests upstream (#292: `unit-tests` + `test` fail at its head — pre-existing on its base, unrelated to the single-PDF port). Upstream states: 22 open, 12 closed-unmerged. The 18 PRs from the Oct 3 / Nov 5 lists were also re-checked live: heads unchanged since Nov 5, all checks passing.

**Blocked slices (recorded, not silently dropped):** #250's delta-audit / `state.py` slice (port #111) needs a Mike/Austin design decision — token vs fork checkpoint, changes canonical audit bytes; #141 (port #109) has one pre-existing upstream test defect that fails identically on upstream base `6b3caac`; #300's benchmark (port #110) is flaky under load — re-run on a quiet machine before treating it as a gate; #306 vs #314 (ports #102/#103) both carry the prove-pulpo35 files — whichever merges first, the other needs a rebase; #292's PDF (port #86) is `d674dbb`-era stale — ported as-is for reference, do not present as current; #241 Seatbelt (port #107) is unverifiable on the Linux VM — macOS verification still needed.

**Keep/drop decisions:** #289 DROP — its README section was already removed by fork rewrites; #293 KEEP and #295 KEEP — both load-bearing for the fork perf train (multi-core verification + setup path, and the opt-in audit-event index).

**Not ported in this run:** the 8 NEEDS DECISION (#64, #262, #315, #334, #288, #291, #221, #131); the perf trio #246/#248/#251 (delta-audit / `data_version` token design decision — the fork checkpoint + digest cache is the incumbent); and the 29 NOT NEEDED — none ported. Details and per-PR reasons are in the manifest.

**Boundaries:** the Windows full suite was not re-run; the Oct 3 Windows result (446 tests, 9 failures, 54 errors, 5 skips) stands as historical and still failing. Hosted validation of the new head is pending. Passing individual-branch checks do not prove interactions between PRs; unit tests do not replace all workflow proofs. Physical hardware performance, independent tester reproduction, and production containment remain **Unknown**.

## Snapshot: 2026-11-05

This is the current snapshot. The 2026-10-03 snapshot below is preserved as history.

**Fork main recorded:** `dc38bf2c935168d70090ac24cdeec0fbd10b5e87` (merge of PR #78, installation-observation fixture fix). Upstream main re-verified at `f08486305736346750aba1c8c6ad1e3c16e061ca` on 2026-11-05.

**Verified fork-main execution:** fork main at `dc38bf2` passed **1086 tests**, result **OK**, 66 skipped, in 123.767s using Python 3.12.3 on the Pulpo-OS-Dev VM (Ubuntu 24.04, 4 CPUs / 3.8 GiB RAM), warnings treated as errors. [Captured log](perf-results/preview-full-tests-20261105.log).

**Upstream PR status, re-checked 2026-11-05:** of the 18 PRs in the Oct 3 selection, 15 are still open and 3 are closed unmerged (#289, #293, #295, all closed 2026-11-03). Six have new heads since Oct 3 (#219, #230, #237, #239, #289, #293); all reported checks pass at their current heads. The Oct 3 combined-preview list (#230, #235, #237, #238, #249, #275, #276, #277, #289, #293, #294, #295) no longer stands as a combined set, because three of its members are closed — this snapshot records fork main as-is and does not claim a fresh combined preview.

**Not re-evaluated in this refresh:** 74 upstream PRs are open (7 drafts). Fourteen numbered above 295 are new since Oct 3 (#341, #333, #330, #327, #316, #315, #314, #311, #309, #307, #306, #305, #301, #299); they were listed in the manifest, not evaluated. The Oct 3 excluded list was status-checked only, not re-decided — notably #241–#245 and #247 (Phase II admission-train items) are still open and non-draft, and their check status was not re-verified here.

**Boundaries:** the Windows full suite was not re-run; the Oct 3 Windows result (446 tests, 9 failures, 54 errors, 5 skips) stands as historical and still failing. Hosted validation of the new head is pending. Passing individual-head checks do not prove interactions between PRs; unit tests do not replace all workflow proofs. Physical hardware performance, independent tester reproduction, and production containment remain **Unknown**.

**What changed in fork main since Oct 3:** Sextant workload-monitor work, the kernel ceremony evidence gate, Control Center drift monitoring, and the installation-observation fixture fix (PR #78); see the fork's merge history. The [machine-readable manifest](PREVIEW_MANIFEST.json) records the per-PR status as of 2026-11-05.

## Snapshot: 2026-10-03

This document and `PREVIEW_MANIFEST.json` preserve the 2026-10-03 snapshot.
PR heads, checks, branch names, and hosted-run results below are historical
evidence, not current project, PR, or workflow status. Re-verify the exact
candidate and its checks before relying on them.

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
