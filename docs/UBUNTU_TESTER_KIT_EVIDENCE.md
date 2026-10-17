# Ubuntu guided demo and tester kit evidence

Base: `9099baab9fe4d9122bd7e514866cc5fc7e1c851f` (merged Phase 1).
Executable change: `a6408ca16aee546fabf3b4aee440794f3c3dde00`.

## Verified locally

Ubuntu 26.04.1 LTS / WSL2, Python 3.14.4:

```bash
python3 -W error -m unittest tests.test_orchestrator_demo tests.test_doctor tests.test_setup -v
```

16 tests pass. The demo now renders plain-language results by default and
preserves the existing `pulpo.orchestrator-demo.result.v0` result via `--json`.
Normal and optimized Python runs produce the same checked JSON, including
22 audit records, target mismatch denial before polling, one-use permit,
replay denial, and revoked permit denial. Repeated runs leave the working
directory empty with bytecode caching disabled.

Injected replay acceptance and invalid audit results return failure without
printing a success summary. Optimized Python still rejects replay acceptance.
Unknown execution-like arguments are rejected before the demo starts.

## Authority and effect boundary

Authority is unchanged. The same synthetic kernel and orchestrator perform
the same in-memory governed transitions. Activation and revocation are now
explicit calls rather than side effects inside assertions, so `python -O`
cannot skip them. No canonical service implementation changes. No persistent
canonical state, external execution, human credential, router, executor,
ledger, or authority plane is added or exposed.

The separate tester repository contains packaging, documentation, feedback
forms, and release metadata. Its kit carries an exact source archive from
this Preview repository; it does not maintain a copied control implementation.
Installation creates a kit-local virtual environment. A source archive and
checksums establish provenance and integrity relative to the published hash,
not publisher signing or production readiness.

## Eight-pass review

| Pass | Assessment |
| --- | --- |
| Flip | Callers cannot supply authority or choose execution targets to the demo CLI. |
| Reverse | Success text is reached only after every synthetic control check passes. |
| Invert | Replay acceptance or an invalid audit fails the run; a desired outcome alone is insufficient. |
| Inside-Out | Presentation uses the existing orchestrator and test authority; it does not become a service. |
| Darken | Compromised source or host can falsify reports; checksums are not an independent audit or signature. |
| Lighten | Passing output proves only this synthetic run on the recorded environment. |
| Amplify | Repeated and optimized runs preserve the same checked result and do not persist demo state. |
| Negate | Use a source kit and thin launchers instead of another installer service or governance implementation. |

Decision: continue with a feature PR and explicitly labeled tester prerelease.
Verified means the local behaviors exercised above. The review's capability
assessment is Inferred from code inspection. Release logs are Recorded.
The UX and distribution path remain Proposed pending review.

Unknown: bare-metal Ubuntu, other Ubuntu versions/architectures, independent
human authority, protected storage, external containment, and production
readiness. The kit requires network access to install Python build tooling.
No reusable temporal-learning claim is made; no historical checkpoint for
this new presentation and kit exists in the inspected base. The smallest next
proof is an extracted-kit install/check/demo on Ubuntu plus hosted PR CI.
