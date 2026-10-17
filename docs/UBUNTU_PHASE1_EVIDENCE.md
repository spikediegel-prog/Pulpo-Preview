# Ubuntu Preview Phase 1 evidence

## Scope and provenance

Preview base: `e29e46c494d4f00a00bc2b4206b2d64974ee74c6`.
Philosophy was documented first in
`a02fb58b84d5ebaa1126e6b53f959f391bb8ac91`.
Implementation tested: `dbf88a09dc04c7fc0ee24b5d4109acc83e48b676`.
Subsequent evidence-only commits do not change executable behavior.

The recovered market-readiness conversation provided the user's Ubuntu-first
and simplicity preferences; its assistant messages were unavailable references.
No additional Phase 1 specification is inferred from those missing messages.

Inspected: `pyproject.toml` (Python >=3.11, base package and `pulpo` entry point),
`pulpo/cli.py`, `pulpo/setup.py`, setup/tuning tests, existing orchestrator demo
and its test, contribution rules, and CI/Preview workflows. No package metadata
change was needed. The PR workflow already runs unittest discovery on Ubuntu
with Python 3.11, including the new doctor tests.

## Verification

**Verified locally:** Ubuntu 26.04.1 LTS under WSL2, Python 3.14.4.

```bash
python3 -W error -m unittest tests.test_doctor tests.test_setup tests.test_orchestrator_demo tests.test_evidence_tuning -v
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/python scripts/demo_orchestrator.py
```

- 37 focused tests passed, including six new doctor tests.
- Wheel build and base installation succeeded in a new virtual environment.
- Installed `pulpo doctor` and `pulpo doctor --json` succeeded from the parent
  directory, outside the checkout; this exercises installed package imports.
- Doctor accepts the valid synthetic audit and rejects a tampered hash using
  the existing setup verifier. Rejection of valid data or acceptance of tampered
  data produces failure; verifier cleanup runs even on an exception.
- Failure output returns 1 and offers diagnosis instead of the next demo step.
- Repeated JSON calls preserve a malformed existing profile. Substituted
  benchmark, evidence-install, and profile options are rejected with status 2.
- Existing demo: mismatch denied before polling, first permit consumed,
  replay rejected, revoked directive permit rejected, 22 audit records valid.
- Committed changes pass `git diff --check` using the Windows Git checkout.
  Linux Git against that same Windows checkout interpreted CRLF conversion as
  whole-tree changes; that mixed-checkout whitespace result is not used as
  source-change evidence. No repository-wide line-ending rewrite was made.

Recorded outputs:

- [Focused test log](../perf-results/ubuntu-phase1-focused-tests.log)
- [Installed doctor JSON](../perf-results/ubuntu-phase1-doctor.json)
- [Existing demo JSON](../perf-results/ubuntu-phase1-demo.json)

## Authority and mutation boundary

Authority is unchanged. Doctor constructs only a conservative computation
tuner and the existing audit verification engine over synthetic rows. It
does not retain a kernel, orchestrator, executor, canonical state backend, or
credential. No canonical mutation is introduced or exposed. Python imports
may write bytecode caches; package installation writes its virtual environment.
Neither is canonical governance state.

The guided demo reuses existing checkout-only test fixtures and existing
in-memory governed transitions. No router, executor, ledger, authority service,
or signing path was copied or added. Canonical `Ironnember/Pulpo1.0` was not
modified. No merge or deployment is part of this work.

## Adversarial transformation review

Purpose: the smallest Ubuntu install/check/demo path. Exact outcome: install
the base package, check synthetic verification, then explain the existing demo.

| Pass | Assessment |
| --- | --- |
| Flip | Untrusted callers receive no profile, benchmark, tuning, or state options on doctor. |
| Reverse | Reaching live state would require a canonical writer; doctor creates none. |
| Invert | Accepting tampered data fails the self-check; success is scoped to synthetic verification. |
| Inside-Out | The diagnostic shares the existing verifier and cannot originate authority. |
| Darken | A compromised host or verifier could falsify output; doctor does not establish host integrity. |
| Lighten | A passing check establishes only the installed synthetic computation path. |
| Amplify | Repeated calls remain bounded to 64 rows and preserve profile contents in subprocess tests. |
| Negate | Reuse package installation, setup verification, and demo instead of adding services or an installer. |

Decision: continue with a reviewable feature PR. No alternate privileged route
or credential custody was introduced. Assessments above are **Inferred** from
code inspection except the behaviors exercised by the cited tests, which are
**Verified** locally and **Recorded** in the logs.

## Limits and next proof

**Unknown:** bare-metal Ubuntu installation, other Ubuntu releases, hosted CI
outcomes until the PR runs, and production deployment readiness. This work does
not verify live governance state, independent human authority, protected
storage, external containment, or optional services. It does not rerun the
entire governance/service suite locally.

No historical checkpoint for this new doctor command exists in the inspected
Preview base. No temporal-transfer or general reusable-learning claim is made.
The smallest next proof is PR CI on Python 3.11 and a clean Ubuntu machine
following the guide. These limits do not block review of this bounded change.
