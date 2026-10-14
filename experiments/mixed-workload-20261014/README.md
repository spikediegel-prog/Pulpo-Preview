# Pulpo mixed workload publication package

Experimental design documentation and bounded benchmark fixtures for Preview commit `d935987f016cfc1038b624a7b4cb6a03ad9f8baa`. This package changes no Pulpo runtime implementation. The baseline comparison used `d674dbb7a00b471d69bcca84d2f034cf74705e1a` from Ironnember/Pulpo1.0.

The conservative fixture selection is one SQL writer, two API slots, zero artificial dispatch spacing, and one SQL/API pair every 100 ms. The 95 ms interval remains experimental. Historical early multi-second stalls remain unresolved and are included in the evidence. No production latency or sustainable throughput guarantee is established.

## Claim classifications

**Recorded:** VM benchmark numbers and executed test outcomes in the archived evidence. **Verified:** transferred archive checksums, exported file hashes/inventory, and exact source identity checked during packaging. **Proposed:** selected test settings and any future integration of the completion handling candidate. **Inferred:** coordinator observation delays explain part of the measured latency difference; this is not a diagnosis of all host delays. **Unknown:** the cause of earlier multi-second stalls, real provider latency, production capacity, host containment, and general temporal transfer.

These classifications govern the results and selections in this package. Read [publication boundary review](docs/publication-boundary-review.md) for the authority and adversarial assessment. Run the relative command examples from this experiment directory, using a separate pinned source checkout and an external results directory.

## Run the portable benchmark

Python 3.11 or later and Git are required. Use a clean checkout pinned to the expected SHA, an isolated interpreter, and an empty output directory outside that checkout. No package installation, provider credentials, network calls, or production databases are used by the benchmark itself.

```bash
python -B -W error scripts/benchmark_mixed_arrivals.py \
  --repo /path/to/pinned/Pulpo-Preview \
  --output /path/to/new-results \
  --pairs 30 --repeats 3 \
  --intervals-ms 200 100 90 80 75 \
  --modes fifo ptc ptc_poll
```

For a small smoke check, use `--pairs 2 --repeats 1 --intervals-ms 100`. Every mode still verifies exact effects, canonical permit counts, one-use replay rejection, audit validity, database integrity, and drained slots/queues. Smoke timing is not a performance acceptance test.

The `ptc_poll` candidate changes only the test owner's completion handling. It observes finished workers before further authorizations and dispatches. All modes retain the existing consumption gate and FULL synchronization. The default eight-slot per-lane queues are bounded; a finite caller backlog contains at most twice the configured pair count.

The benchmark records scheduled-arrival-to-observed-completion latency, including authorization, admission, queueing, effects, and slot release. A separate worker-completion timestamp identifies coordinator observation delays. Setup and final verification are outside the latency clock. API work is a 30 ms in-process fake, and SQL work uses disposable databases plus a 2 ms delay. Per-class P95 and individual misses must both be reported; separate stage percentiles must not be added.

Use `--expected-sha` explicitly to test another commit. Retain the new commit, environment, source hashes, and raw samples; do not transfer the historical conclusions automatically. The output guard prevents writing into the source checkout or overwriting a previous run. The working checkout must stay clean throughout execution.

## Export historical evidence

```bash
python scripts/package_evidence.py \
  --results /path/to/original-comparison/results \
  --output /path/to/new-evidence.tar.gz
```

The exporter packages an allowlist of reports, logs, fixture source, and provenance. It excludes databases, unrelated files, and linked files/directories. It requires the original comparison reports, the Ed25519, recovery, stress, arrival and boundary evidence, and a successful portable smoke report before producing an archive. Text paths are replaced with placeholders; measured values remain unchanged. The manifest records original and exported hashes and every redacted file. Original VM evidence remains untouched.

## Publication scope

Publish the documentation, portable fixture, export utility, and reviewed evidence together. Raw historical harnesses and their original source hashes identify which code produced each result. The portable smoke report is separate from that historical evidence. Existing filenames reused during earlier comparison runs contain their latest saved execution; the separate diagnostic directories retain the recorded early failures.

Read `docs/performance-design.md` for selected settings, boundary requirements, results, and criteria for revisiting the design. Runtime integration, merging, pushing, and deployment are separate actions.
