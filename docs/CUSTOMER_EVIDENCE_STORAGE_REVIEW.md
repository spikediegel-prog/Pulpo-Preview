# Customer evidence storage change record

1. **Invariant/failure:** storage ownership and capacity must be explicit without
   confusing a bounded observer projection with a complete archive or authorizing
   deletion when export fails.
2. **Authority delta:** none. Acknowledgment is private local settings metadata,
   never a signed approval, retention authorization or verified connection.
3. **Canonical mutations/boundaries:** none introduced. Reuse the private session
   preferences writer only. The UI has no exporter, kernel, new state backend,
   archive ledger, mount/credential capability or background network worker.
4. **Success/adversarial evidence:** `test_storage_policy` covers legacy setup,
   supported choices, rejected planned integrations, stale revision, forged/nonbool
   acknowledgment, unknown fields, invalid paths, atomic-save failure preservation,
   forget preserving archive, real Tk save/restore, edited-plan reacknowledgment
   and clearing a plan. Existing export publication, audit tamper/replay and custody
   convergence suites remain the canonical behavior evidence. Preview adds a
   failed-export regression asserting unchanged audit, prior projection and
   canonical writes, valid integrity and continued consumed-permit rejection.
   Full run results and package checks are recorded with the PR and delivery report.
5. **Limits:** no full-audit archiving/receipt/pruning, native Windows storage UI,
   remote durability, NAS/SAN certification, legal-hold engine, production volume
   measurements or appliance qualification proved. Tk tests prove construction and
   interaction at narrow size, not visible WSLg visual acceptance. No release or
   production deployment performed.
6. **Claims:** Recorded source/test results; Proposed future integrations and
   appliance sizing; Unknown customer durability, retention compliance and
   production enforcement. No external effect promoted to Verified.
7. **Legacy sources reused:** existing session preferences validation/private
   publication, session setup and walkthrough, Evidence display, owner exports,
   canonical SQLite state and custody convergence. The existing Preview UI and
   extracted Control Center receive the same storage-plan component; neither
   copies or changes a canonical control path. Existing GCS authority evidence
   sink is documented only in its separate service scope.
8. **Temporal transfer:** no relevant historical checkpoint implements this new
   storage acknowledgment. No reusable governance lesson or historical authority
   transfer is claimed. Current tests are bounded to this implementation and its
   existing export/state contracts; no future authority is replayed backward.

## Eight analytical passes

| Pass | Finding and boundary |
| --- | --- |
| Flip | Hostile/forged preferences can at most claim a local plan; exact fields/revision/types are validated and no consumer activates a transfer. |
| Reverse | Audit loss would require deletion or a new state writer; neither is added. Export failure preserves the prior source and snapshot in the injected pre-replace failure. |
| Invert | Saved acknowledgment and successful projection publication do not prove archive completeness, durability, compliance or enforcement. |
| Inside-Out | Observer and settings writer never acquire the owner exporter or canonical backend. Only the existing owner publishes public projections. |
| Darken | An unavailable mount, full volume or missing archive can interrupt operations. No silent local deletion or fabricated success masks it; capacity admission/archival automation remains unimplemented. |
| Lighten | A customer can document an existing filesystem handoff with no new remote integration. Unknown readiness remains Unknown. |
| Amplify | Repeated edits clear acknowledgment; settings remain bounded/private and repeated saves do not grow a ledger. Tk callbacks are explicitly released on window destruction. |
| Negate | Responsibility and manual planning use existing setup persistence; no new uploader, credential custody, canonical router or ledger is necessary. |
