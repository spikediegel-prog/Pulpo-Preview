# Ubuntu evaluation preview

## Status

This is a **source-only evaluation preview** of Pulpo Core, tied to an exact Git
revision. It is not a full product installer or production deployment.

The preview is a dated snapshot of upstream `main` at
`6b3caacbc28a7b40ebf5ea6295bc8058804de6e3`, not a continuously updated
channel. No unmerged upstream PRs were imported; current upstream PR status was
not audited when the snapshot was made.

- **Available for evaluation:** the Python governance kernel and its synthetic
  tests, run directly from a clean source checkout.
- **Not included as deployed products:** Pulpo Node and Pulpo Incident Response.
  Their repository evidence is synthetic-only; it does not authorize hardware
  control or real host remediation.
- **Not an installable runtime:** Gladiator Ultra is validation tooling, not a
  product service.
- **Not provided:** a `.deb`, offline installer bundle, systemd unit, hosted
  authority service, production signing credentials, or OS sandbox.

The canonical Pulpo kernel remains the only authority and canonical evidence
path. The preview adds no authority, signer, service, or canonical state
mutation. Tests use synthetic fixtures and disposable local state.

## Ubuntu support gate

The release target is Ubuntu 24.04 LTS. Do not treat that target as supported
until the exact-head `Ubuntu evaluation preview` CI job passes on
`ubuntu-24.04`. CI is evidence for the tested source and runner only; it is not
production-readiness approval.

**Verified:** exact-head CI run
[41153934426](https://github.com/spikediegel-prog/Pulpo-Preview/actions/runs/41153934426)
passed at commit `3b8800d654d84249aaa7f6186c550425c5bd6d2b` on GitHub-hosted
Ubuntu 24.04 with Python 3.12.3. The full suite ran 422 tests with one skip;
the bounded tournament ran 138 test executions with zero failures, errors, or
skips and 10,600 scheduled mixed operations. The source remained unchanged and
the checkout remained clean. This evidence applies only to that commit and
environment; every later release candidate must pass its own exact-head job.

**Verified:** the bounded exact-source tournament passed at snapshot commit
`f5cae2be2a188fbd54d78cb875e608f30af806ad` on Ubuntu 26.04.1 LTS under WSL2
with Python 3.14.4: 138 test executions, zero failures, errors, or skips, and
10,600 scheduled mixed operations. The source remained unchanged and the
checkout remained clean. The runner result was `PASS_WITH_BOUNDARIES`.

The tournament logs also contain SQLite finalizer `ResourceWarning`s in a
mixed-operation round. The result is not warning-free validation. A separate
Windows-host run failed with SQLite temporary-file/open and cleanup errors;
its cause is not established, and Windows support is not claimed.

## Evaluate from source

Prerequisites: Git and Python 3.11 or newer. No provider credentials or
signing material are needed for these local synthetic checks.

```bash
git clone --branch preview-current-20261030 \
  https://github.com/spikediegel-prog/Pulpo-Preview.git
cd Pulpo-Preview
revision="$(git rev-parse HEAD)"
python3 -W error -m unittest discover -s tests -v
python3 -W error scripts/run_gladiator_tournament.py \
  --repo . \
  --expected-revision "$revision" \
  --output "$HOME/pulpo-evidence-$revision"
```

Keep the evidence output outside the checkout. Read
`tournament-results.json` and the individual logs; do not infer a pass from the
process exit status alone. The tournament is a bounded synthetic software
proof, not an independent review, deployed ingress proof, OS containment proof,
provider-custody proof, or the full 24-condition tournament.

## Release boundary

The Ubuntu evaluation workflow runs on an exact pull-request head with read-only
repository permissions and no production secrets. A passing job supports only
the tested commit and environment. It does not publish an installer, activate
services, grant authority, establish production readiness, or certify customer
outcomes.

## Required change record

1. **Invariant/failure addressed:** Publish a source-only Ubuntu evaluation
   path without misrepresenting synthetic proofs or validation tooling as
   deployable product surfaces.
2. **Authority delta:** None. No authority is gained, narrowed, or changed.
3. **Canonical state mutation/capability boundary:** No runtime mutation or
   writer is introduced. CI runs tests and the existing tournament with
   synthetic local state; workflow permissions are read-only.
4. **Success and adversarial evidence:** Exact-source tournament result and
   command and the exact-head Ubuntu 24.04 CI result are recorded above. A
   later release candidate must pass its own exact-head Ubuntu 24.04 job.
5. **Unproven boundary:** No `.deb`/offline installer, systemd deployment,
   production authority, host isolation, real Node/Incident Response behavior,
   provider containment, independent review, or customer outcome is proved.
6. **Claim classification:** The exact-source tournament and Ubuntu 24.04 CI
   results are **Verified** only for their recorded commits/environments.
   Production deployment remains **Blocked** by the documented gates.
7. **Legacy source disposition:** No historical runtime or control path is
   imported.
8. **Temporal transfer:** No reusable lesson or authority change is introduced.
   The existing historical checkpoint results are preserved in
   `PREVIEW.md`; no new temporal replay is claimed.
