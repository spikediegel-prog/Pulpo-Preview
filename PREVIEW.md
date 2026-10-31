# Pulpo Preview — current source snapshot

Snapshot date: 2026-10-30

This branch is a fresh snapshot of `Ironnember/Pulpo1.0` `main` at exact source
commit `6b3caacbc28a7b40ebf5ea6295bc8058804de6e3` (tree
`df6310dc0b6eaec50b7870832dd8cb379096f778`). It contains that upstream source
plus this snapshot record and its manifest. No unmerged PRs were integrated;
current upstream PR status was not audited for this snapshot.

The pre-existing Pulpo Preview `preview` branch was left unchanged at
`606a4c55f092e15a581da099c646d9eea6dabe84` and is additionally preserved at the
`preview-original-2026-10-30` tag. The new branch does not rewrite, replace, or
delete that history or its evidence.

## Required change record

1. **Invariant/failure addressed:** Avoid representing an old combined preview as current. This snapshot starts at the exact upstream `main` commit recorded above.
2. **Authority delta:** None. No authority is gained, narrowed, or changed.
3. **Canonical state mutation/capability boundary:** None introduced or exposed. This is snapshot documentation; no executable code or canonical writer changed.
4. **Success and adversarial evidence:** **Verified:** `python3 -m unittest discover -s tests -v` on the exact source commit passed 422 tests with one skip in Ubuntu 26.04.1 LTS / Python 3.14.4. The exact historical checkpoint commits required by the existing temporal-transfer test were available in the full-history validation clone. **Recorded:** on the same source commit, the Windows-host run of `python -m unittest discover -s tests -v` ran 416 tests and reported 14 failures, 60 errors, and two skips; the causes were not diagnosed.
5. **Evidence boundary:** The Linux result does not establish current upstream PR/check status, Windows compatibility, all cross-platform workflows, production readiness, or deployment behavior. The Windows run was not passing and is not evidence of Windows support. No unmerged PR selection or compatibility audit was performed.
6. **Claim classification:** Source commit and tree identity, original-ref identity, and Linux test result are **Verified** for the recorded Git/runtime. The Windows run is **Recorded**, with its cause and applicability **Unknown**. Current unmerged PR status and all deployment claims are **Unknown**.
7. **Legacy behavior/source:** No legacy control path was copied or used.
8. **Temporal transfer:** No reusable lesson or authority change is introduced. The existing suite's temporal-transfer checks passed against their exact historical commits; this snapshot itself is not a temporal replay.

The snapshot contains only upstream `main` and this record. Treat it as a dated
source snapshot, not a continuously updated channel. Rebuild and revalidate a
new snapshot when the source baseline changes.
