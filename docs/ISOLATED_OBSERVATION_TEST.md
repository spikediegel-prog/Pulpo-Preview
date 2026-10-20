# Isolated observation test — Ubuntu VM or WSL

This opt-in standalone test creates a new disposable canonical owner solely for
the operator-authorized synthetic workload. It is not a production owner or an
integration with existing services. The dashboard never imports or starts it.

From the updated checkout, run:

```bash
./.venv/bin/python -m pulpo.observation_test
```

No graphical display is needed. It prints two absolute **TEST-ONLY** export paths
and runs 30 cycles at two-second intervals, then exits. To stop early press Ctrl+C.
Optional `--cycles` accepts 1–60 and `--interval` accepts 1–10 seconds. There is no
daemon, listener, automatic restart, network call, external executor, shell command,
human approval or model request. The kernel generates its own ephemeral permit
secret; no existing credential or signing material is read or exported.

Each cycle evaluates one fixed zero-cost `test.inspect` intent, consumes its permit,
checks reuse is rejected, and evaluates a fixed forbidden action. No inspected file
or external resource is actually read or modified by those intents. Canonical test
decisions and permit state are recorded in a fresh SQLite database inside a unique
private temporary directory. This is actual test activity, not invented counters.
The existing exports contain only their established bounded public metadata.
Database/volume readings describe this temporary database and its volume, not the
production evidence store. AI usage remains Unknown. Database quick-check and
audit results are source reports, not independent production enforcement proof.

## Observe the test

Keep the terminal's **TEST ONLY** context visible. In Control Center select
`TEST-ONLY-governance.json` in Governance and `TEST-ONLY-evidence.json` in Evidence.
The standard export schemas carry no authenticated test-origin label, so keep the
TEST-ONLY filenames and folder, and do not mix these sources with production
observations. The UI does not authenticate filenames or source claims. This test
does not install an automatic source selector or change saved preferences.

If the owner runs in the VM and Control Center runs in WSL, the VM's `/tmp` path
is not a WSL path. Transfer only the two public JSON exports through your existing
SSH connection to a private WSL folder and select the WSL copies. Do not copy the
private-state directory, database, permits or credentials. A one-time copy is a
frozen observation; it cannot show live rates. Live rates require two distinct,
recent owner observations and an explicitly arranged transfer. No synchronizer or
new SSH configuration is installed by this change. Running this isolated test in
WSL instead lets Control Center read its local exports directly.

After normal exit, an exception or Ctrl+C, the database connection is closed and
the private test database directory is removed. Only the public exports and a
TEST-ONLY notice remain in the printed folder. A hard kill or power loss can leave
private temporary state; no crash cleanup guarantee is claimed. Do not share it.
Exports become stale after the owner stops; re-reading cannot refresh their source
timestamp. Export failures stop the test without retry; previously published files
may remain. Governance and Evidence are separate atomic publications, not a single
cross-file transaction. Do not infer they describe the same instant.

## Required change record

1. Missing observation sources prevented a bounded dashboard walkthrough.
2. Operator-authorized test authority is confined to a new temporary canonical
   owner and fixed test intents; existing deployment authority is unchanged.
3. The canonical kernel alone records test decisions, issues/reserves/consumes
   test permits and rejects reuse in its fresh SQLite state. No writer is passed
   to the UI, no existing database is accepted and no alternative ledger is added.
4. Tests check actual exported outcomes/counters, audit consistency, unknown AI,
   private export permissions, cleanup after interruption and invalid bounds.
   Native inspection uses these test exports, explicitly labeled as test material.
5. This proves neither real workload integration nor independent human authority,
   production containment, transport authenticity, power-loss cleanup or full
   application enforcement. No external effect execution is demonstrated.
6. Implementation/test checks are Verified only within their recorded conditions;
   selected metadata is Recorded; deployment governance remains Unknown.
7. Existing kernel, SQLite state, orchestrator and frozen-export APIs are reused.
   No test signer or demo approval flow is copied.
8. No reusable governance lesson or temporal-transfer proof is admitted here.

## Analytical transformation review

| Pass | Boundary |
| --- | --- |
| Flip | Hostile observer receives primitive exports, never owner objects or permits. Filenames are not authenticated provenance. |
| Reverse | A production-governed claim would require confusing test exports with deployment evidence; documentation and TEST-ONLY names explicitly prohibit that inference. |
| Invert | A failed permit, denial or audit check stops execution; publication success alone is not test success. |
| Inside-Out | The test owner cannot grant human authority; there is no verifier, authority client or external executor. |
| Darken | Hard kill may leave private temporary state; source substitution and compromised filesystem are not solved here. |
| Lighten | Missing AI usage is Unknown because no model was called; stale exports mean the test stopped, not an enforcement incident. |
| Amplify | Cycles and intervals are bounded; each invocation uses a fresh unique state directory and no existing state path. |
| Negate | An explicit standalone synthetic owner supplies walkthrough data without a production service, new UI writer or credentials. |

Decision: continue only for this explicit isolated test. Smallest next proof is
an operator-run invocation on the Ubuntu VM followed by selecting/copying only
its public test exports. Remaining unknowns include VM execution, cross-machine
transfer, actual production workload integration and independent enforcement.
