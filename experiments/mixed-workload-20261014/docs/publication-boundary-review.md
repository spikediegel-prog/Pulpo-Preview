# Publication boundary review

## Purpose and requested outcome

Publish experimental design documentation, portable benchmark fixtures, and reviewed evidence in a draft PR in spikediegel-prog/Pulpo-Preview. The human explicitly authorized a new branch, commit, push, and draft PR after reviewing the package. Merge and deployment are outside that request.

## Authority and canonical state boundaries

**Verified by publication file scope:** the change adds only files under this experiment directory. It changes no kernel, state backend, traffic controller, orchestrator, authority, policy, or production adapter source.

**Proposed experiment scope:** a trusted local owner runs disposable fixture governance through the existing kernel. The benchmark's calls issue and consume permits, append canonical fixture audit events, and append replay-rejection evidence during postchecks. These are governed canonical mutations even though the fixture grants no production authority. Canonical fixture SQLite remains on the owner thread; workers receive exact fixture intents and use only disposable effect connections.

No new canonical transition is introduced or exposed through a transport, MCP surface, daemon, or production adapter. The candidate changes when the owner observes completed futures and releases slots, without moving permit consumption, policy decisions, or canonical mutation into workers. Never pre-consume a capability for a real executor that already controls its own consumption point.

Publication itself changes GitHub repository state through the existing authenticated GitHub connection within the human's authorization. It does not create, derive, export, or impersonate a human signing credential.

## Eight pass analytical review

| Pass | Finding and boundary |
| --- | --- |
| Flip | A hostile same-process execution owner or hostile selected source checkout remains outside the fixture's containment proof. Exact pinned source and clean-checkout guards provide provenance, not a sandbox. Queued claims still face canonical consumption. |
| Reverse | An unintended effect would require the owner to dispatch a wrong intent or access a live adapter. The fixture has only disposable SQL writes and an in-process API-style delay; result targets, exact rows, consumption counts, and audit are checked. No provider route is added. |
| Invert | Faster timing does not count as legitimate success when effect, permit, replay, integrity, or audit checks fail. P95 success is reported separately from individual deadline misses and correctness. The exporter requires passing correctness-stage exits; timing failures remain included. |
| Inside Out | The operator and host producing the measurements are the same trust domain as the fixture. Hashes bind bytes and source identity; they do not independently certify host behavior, power loss, or hardware integrity. Archive review does not elevate VM timing to a production guarantee. |
| Darken | Bounded adversarial cases include queue saturation, forged/replayed claims in archived regression coverage, early timing stalls, uncertain commit/receipt boundaries, and nonzero correctness stages. Portable pair/repeat arguments and queues are bounded. No claim of indefinite-load survival is made. |
| Lighten | The early slow regime is consistent with waiting or host scheduling/storage variation, but its cause is Unknown. Retain those trials rather than recategorizing them as harmless warm-up. |
| Amplify | Repeated arrivals can accumulate caller backlog or delay API completion observation. The fixture has finite jobs and local slot bounds, not fleet-wide caps. Repeated canonical permit consumption rejects replay; no effect retry, renewal, or durable queue is introduced. |
| Negate | Publication can preserve the measured lesson without changing runtime scheduling, durability, policy, or capability custody. Keep the completion candidate in the external fixture and leave source integration for a separately justified change. |

## Evidence and claim classifications

**Recorded:** archived VM full-suite, focused Ed25519, recovery, stress, backend and traffic comparisons, arrival experiments, and three portable fresh-checkout smoke reports. The historical measurements identify the archived harness and source they used. The portable entry point has smoke evidence, not a new full latency sweep. Windows-specific tests remain skipped on Ubuntu.

**Verified:** the transferred outer archive checksum, embedded evidence archive checksum, 97 exported file hashes and lengths, retained earlier slow samples, and script/document agreement with the reviewed draft. Ten files have declared path redactions with original and exported hashes separately recorded.

**Proposed:** 100 ms per pair as the conservative local test setting, 95 ms experimental, and any future incorporation of earlier completion observation into a runtime owner.

**Inferred:** completion observation ordering accounts for part of the fixture's latency difference because worker-finished and owner-observed timestamps differ. Whole-process CPU increments can include overlapping worker CPU and do not isolate every delay source.

**Unknown:** earlier multi-second stall causes, actual provider response times, sustainable service capacity, hostile-host containment, power-loss durability, and general lesson transfer. Material scope limits are retained in the design and README.

## Legacy behavior and temporal transfer

The fixture uses the existing kernel, state backend, traffic controller, and orchestrator consumption seam. Its FIFO control follows the existing disposable benchmark pattern in `scripts/demo_traffic.py`; this does not replace or duplicate a production executor control path.

The SQLite backend comparison loads the exact baseline state backend from `d674dbb7a00b471d69bcca84d2f034cf74705e1a` in a fixed current harness. That is a component comparison, not a historical-system replay or temporal transfer proof. No relevant historical completion-observation/PTC checkpoint has been established for a full governed lesson replay. General reusable temporal-transfer claims remain Unknown; no future authority, credentials, or approvals are imported into the baseline.

## Continue decision and next proof

Continue with publication of experimental documentation, fixtures, and evidence only. No alternate provider route, credential-state export, signing capability, or runtime authority expansion is introduced by this publication scope. Do not merge or deploy as part of opening the draft PR.

The smallest next proof for runtime integration would reconstruct the chosen exact source, investigate the early stalls, and measure a representative real workload with independent class latency and miss counts while retaining all original authority, replay, audit, reconciliation, and durability checks. Hosted checks on the publication commit must be assessed separately from archived measurements.
