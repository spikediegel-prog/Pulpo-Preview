# Ubuntu/Linux cold reproduction and source provenance

This procedure prepares an independently checkable **source** artifact for
`pulpo-linux-v*` tags. It is an engineering evidence step, not a production
release or a complete consequence-custody proof.

## What the tagged workflow establishes

The `Ubuntu Linux Source Attestation` workflow runs on the exact tagged commit
on a GitHub-hosted Ubuntu runner. It requires a clean checkout, runs the
repository test suite and randomized constitutional sequence, runs the
constitutional mutation harness, confirms that the harness restored the clean
tree, archives the exact commit, and asks GitHub's artifact-attestation service
to issue build provenance for that archive. The 90-day workflow artifact
contains the archive, a digest/source/runtime manifest, test logs, the installed
Python package inventory, and mutation results. The attestation covers the
source archive; the adjacent logs and manifest are supporting workflow
evidence, not separate attested subjects.

This is stronger than a locally generated checksum: an independent reviewer
can verify the GitHub attestation identity and repository/workflow provenance.
It is **not** an independent implementation or a cold reproduction; the
workflow still executes the submitted source and relies on GitHub-hosted
infrastructure. The tag-triggered workflow must first be merged to the
repository's default branch; a tag pushed before that may not trigger it.
Branch/tag protection, review, and release authorization remain
repository-owner responsibilities.

## Independent operator procedure

Use a trusted Ubuntu 24.04 VM, a current GitHub CLI (`gh`), Git, and Python 3.12.
Obtain the archive from a successful run of the workflow at the exact intended
tag. Keep the downloaded archive and workflow manifest unchanged.

1. Verify the artifact attestation against this repository:

   ```bash
   gh attestation verify pulpo-linux-source-<commit>.tar.gz \
     --repo spikediegel-prog/Pulpo-Preview
   ```

   The command must succeed and identify the expected repository, source
   revision, and workflow identity. If the attestation is missing, invalid, or
   names a different source, stop; do not rely on the adjacent checksum alone.

2. Compare the archive digest to `archive_sha256` in
   `linux-source-manifest.json`:

   ```bash
   sha256sum pulpo-linux-source-<commit>.tar.gz
   ```

3. Use a full Git clone of the attested tag for the test run. Several repository
   tests intentionally inspect Git history, so running directly from the
   source-only archive is not a valid reproduction. Extract the attested
   archive and compare its complete source tree against `git archive` of the
   exact tagged commit before running tests:

   ```bash
   set -euo pipefail
   archive="pulpo-linux-source-<commit>.tar.gz"
   manifest="linux-source-manifest.json"
   tag="$(python3.12 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["tag"])' "$manifest")"
   commit="$(python3.12 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["commit"])' "$manifest")"
   mkdir -p "$HOME/pulpo-cold-reproduction/archive" \
     "$HOME/pulpo-cold-reproduction/expected"
   git clone --branch "$tag" \
     https://github.com/spikediegel-prog/Pulpo-Preview.git \
     "$HOME/pulpo-cold-reproduction/checkout"
   repo="$HOME/pulpo-cold-reproduction/checkout"
   test "$(git -C "$repo" rev-parse HEAD)" = "$commit"
   tar -xzf "$archive" -C "$HOME/pulpo-cold-reproduction/archive"
   git -C "$repo" archive --format=tar \
     --prefix="pulpo-${commit}/" "$commit" \
     | tar -xf - -C "$HOME/pulpo-cold-reproduction/expected"
   diff -r \
     "$HOME/pulpo-cold-reproduction/archive/pulpo-${commit}" \
     "$HOME/pulpo-cold-reproduction/expected/pulpo-${commit}"
   cd "$repo"
   python3.12 -m venv "$HOME/pulpo-cold-reproduction/venv"
   source "$HOME/pulpo-cold-reproduction/venv/bin/activate"
   python3.12 -m pip install '.[authority]'
   python3.12 -m pip check
   python3.12 -W error -m unittest discover -s tests -v
   python3.12 -W error -m unittest tests.test_constitutional_sequences -v
   sha256sum pulpo/state.py pulpo/kernel.py > /tmp/pulpo-mutated-files.before
   python3.12 scripts/run_constitutional_mutations.py \
     --output /tmp/pulpo-constitutional-survival.json
   sha256sum pulpo/state.py pulpo/kernel.py > /tmp/pulpo-mutated-files.after
   diff -u /tmp/pulpo-mutated-files.before /tmp/pulpo-mutated-files.after
   test -z "$(git status --porcelain --untracked-files=all)"
   ```

   Require every command to succeed and the mutation report to say `pass`, with
   zero invalid and zero surviving mutations. The tree comparison proves the
   downloaded source archive matches the exact commit; the before/after digest
   and Git status checks confirm the mutation harness restored its changes.
   Keep all logs and reports outside the checkout.

4. Return a reproduction record to the assurance owner containing:
   - verifier name/organization and the UTC start/end times;
   - Ubuntu image/provider and VM isolation details, Python version, and exact
     commit from the manifest;
   - the successful attestation verification output and archive SHA-256;
   - each exact command and exit code, full-suite summary, mutation counts,
     before/after source digests, and digests of retained logs/reports;
   - any deviation, failure, or unavailable check, including the reason; and
   - the evidence-retention location and its access controls.

   Retain the record and raw outputs in storage independent of the tested VM
   and GitHub workflow artifact. Do not send secrets, credentials, raw permits,
   or customer data. A second run by the same operator or in the same cloud
   trust domain is useful repeatability evidence, but is not an independent
   third-party reproduction.

5. Classify results narrowly. A successful reproduction verifies those exact
   source tests on that independent VM. It does not show that a production
   deployment is using that artifact or that a third-party effect was properly
   authorized, executed, observed, and reconciled.

No human signing credential or provider credential is required for these
source-level checks. Do not copy secrets, live databases, or raw permits into
the reproduction packet.

## Remaining market assurance gaps

This workflow closes the **signed exact-source provenance** gap for tagged
source archives once repository owners configure protected tags and operate an
authorized tag/release ceremony. It does not sign a Linux binary or prove
byte-for-byte reproducible builds. The documented Phase II gaps remain:

- independent deployment of the pinned authority service and its accepted
  bounded deployment receipt;
- current-canonical reproduction of the real external consequence through the
  existing authority, custody, execution, observation, and reconciliation
  path;
- an independent operator's completed cold reproduction with evidence retained
  outside the checked host;
- customer deployment identity, host/boot integrity, and actual service
  enforcement;
- third-party security review or any applicable certification.

These require current human authorization, an actual Ubuntu VM/deployment,
independent operator participation, and separate external evidence retention.
The workflow deliberately does not manufacture these facts or claim production
readiness. Windows packaging and qualification are excluded from this Linux
scope.

## External validation handoff

The external tester should receive the successful workflow URL, exact tag and
commit, the complete downloaded artifact, and this procedure. The assurance
owner should record the independent reproduction as **Pending** until the
tester returns the reproduction record and retained evidence reference above.
Do not treat CI logs, a green workflow, a local WSL run, or an operator statement
without retained evidence as completion of the independent check.

## Required change record

Invariant addressed: exact source identity and independent provenance for a
bounded Ubuntu source-test artifact. Authority gained: none. Canonical mutation:
none; tests use existing disposable fixtures. The CI runner has read-only
repository access and GitHub's scoped OIDC/attestation permissions solely to
attest the exact archive. Success evidence is the workflow run, exact commit,
archive digest, artifact attestation, and mutation report. The evidence does not
prove live authority, custody, provider outcome, production host integrity,
independent cold reproduction completion, or certification. Existing kernel,
test, and mutation-harness paths are reused; no second governance or audit
system is introduced. No material reusable lesson or historical-transfer
claim is made.

Adversarial passes: **Flip**—the workflow/source may be dishonest, so the
attestation proves origin, not correctness; **Reverse**—a wrong or modified
archive fails identity or digest verification before reproduction; **Invert**—
green CI is not deployment authorization; **Inside-Out**—GitHub's workflow and
OIDC are in the trust boundary and not independently audited by this job;
**Darken**—a compromised repository owner or runner could publish malicious
source with valid provenance; **Lighten**—failure to reproduce is a discrepancy
to investigate, not proof of compromise; **Amplify**—each tag is evaluated and
attested separately, with no transfer of old results; **Negate**—a source
archive and public attestation provide useful provenance without signing
customer credentials or creating a new authority plane.
