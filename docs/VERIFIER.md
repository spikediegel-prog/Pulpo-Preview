# Pulpo Verifier

Run `pulpo verify` (or `python -m pulpo.cli verify`) to execute bounded
in-memory governance probes and write `evidence/verifier_report.json`. Pass
`--report <path>` to select another report destination. The command prints each
check, a coverage score, and the report's overall status.

The verifier tests the actual `GovernanceKernel` APIs for policy constraints,
target binding, one-use permit replay protection, and audit-chain integrity.
Tamper detection is covered by the existing kernel tests; the report run does
not mutate audit state to manufacture a tamper case. It does not open a
configured kernel or canonical database. Probe state is ephemeral; the only
persistent output is the requested JSON report. The verifier does not create,
load, or export human signing credentials, and it does not invoke an executor
or provider.

`PASS` means the named behavior was observed in the isolated probe. `FAIL`
means the probe contradicted its expected behavior. `UNVERIFIABLE` means the
claim needs authority, custody, execution, or independent evidence that this
local harness does not possess. Any failure makes the overall status `FAIL`;
otherwise, any unverifiable check makes it `UNVERIFIABLE`. The score is
`PASS / all checks`, so unknown checks do not count as passes. The command exits
zero only when every check passes.

The harness deliberately leaves deployment claims unknown, including
constitution signature/unauthorized deployed policy changes, trusted
approver identity and signature verification, directive revocation under
deployment authority, custody receipt binding/expiry, custody enforcement at
execution, durable permit behavior across restarts, direct execution boundaries,
and missing audit events. A hash-chain pass does not establish event
completeness. The report classifies claims and states that temporal replay was
not performed; it makes no historical lesson transfer claim.

## Optional external integrity check

For an additional point-in-time comparison, configure `pulpo verify` with an
HTTPS manifest endpoint, an independently provisioned Ed25519 public key, and
the public key's SHA-256 fingerprint obtained through a separate trusted
channel:

```powershell
pulpo verify `
  --integrity-manifest-url https://integrity.example.test/v1/manifest `
  --integrity-public-key C:\ProgramData\Pulpo\integrity-publisher.pub `
  --integrity-key-sha256 <64-character-lowercase-sha256-fingerprint> `
  --integrity-max-age-seconds 300
```

The verifier sends a fresh 256-bit nonce in the `nonce` query parameter. The
endpoint must respond with a JSON envelope containing exactly `manifest` and
`signature`. The signed manifest contains exactly `schema`
(`pulpo.integrity-manifest.v1`), `version`, `nonce`, timezone-qualified
`generated_at`, and `files`. `files` must contain exactly every Python source
file in the first-party `pulpo` package, as enumerated by
`pulpo.verifier.external_integrity.VERIFIED_FILES`, each mapped to its
lowercase SHA-256 digest. This includes the CLI, verifier, kernel, authority,
and audit implementation used by the local probes. It does not authenticate
Python, installed dependencies, loaded code, or the host. The signature is
lowercase hex Ed25519 over the
UTF-8 canonical manifest JSON (sorted keys, compact separators, ASCII escaping).
The endpoint should construct the response for the requested nonce and publish
it promptly; stale, replayed, malformed, wrongly signed, or mismatching
manifests never pass. Network failure is `UNVERIFIABLE`, not `PASS`. The
verification dependency is available through the existing `pulpo[authority]`
extra.

Run this command periodically using an independently managed scheduler (for
example, Windows Task Scheduler or a systemd timer). The source publisher's
private signing key must stay outside this repository and the checked host,
preferably in an independently controlled signing service or HSM. Provision
the public key and its fingerprint through a separate administrative channel.
The report records the challenge, key fingerprint, manifest timestamp, and
file-check result.

**This is tamper evidence, not proof that compromise is impossible.** The
check compares on-disk first-party Pulpo package source with a fresh statement
from a pinned publisher. It cannot prove the currently running process, loaded
memory, interpreter, operating system, scheduler, public-key provisioning, or
publisher has not been compromised. A modified verifier could lie about its
own result. For detection of that threat, an independent monitor on a separate
trust domain must obtain and hash the installation itself, verify the signature
with its own key pin, and retain the result outside the checked host. No
setting inside the verifier can guarantee its own immunity to compromise.

## Adversarial transformation review

| Pass | Verifier-specific analysis |
| --- | --- |
| Flip | A verifier can overstate its own result; status is limited to the exact probe and unknown deployment claims stay visible. |
| Reverse | A harmful unauthorized mutation would require a live writer or executor; the CLI accepts no caller-supplied writer and probes only fresh in-memory kernels. The optional signed manifest detects source mismatch only if this process reports honestly. |
| Invert | A successful outcome through an unobserved route is not treated as governed; this tool does not verify external execution. |
| Inside-Out | The verifier uses only kernel-bound methods on temporary instances; it creates no external approval and holds no live custody store, executor, or signer. The external publisher's private key remains outside the verifier. |
| Darken | Repeated CLI calls can produce repeated local reports, but cannot reuse a live permit or alter a supplied canonical store. |
| Lighten | A report with unknown checks indicates missing evidence, not evidence that the deployment is unsafe or that an incident occurred. |
| Amplify | Score aggregation includes all unknown checks in the denominator; repeated isolated passes do not accumulate authority or deployment proof. |
| Negate | No deployment connection is needed to verify the narrow kernel contracts; stronger claims require the owning governed path to supply evidence. |

**Change record:** This adds a verifier without expanding authority. Probe
transitions are confined to disposable in-memory kernel state; report writing
is a local file output and is not a canonical governance mutation. The optional
check makes an HTTPS request and verifies a signed response; it does not mutate
canonical Pulpo state. Success evidence is the isolated behavioral report plus
the external integrity check and targeted unit tests; external signature
validity for approvals, custody operation, executor enforcement, event
completeness, production state, and deployment identity remain outside that
evidence. Claims are `Verified` only for observed probe behavior and
challenge-bound file comparison; `Unknown` remains for absent deployment
evidence and unavailable sources. Existing kernel and directive contracts are
exercised through their current paths; no alternate control path is introduced.
No reusable lesson is asserted, so temporal transfer is not claimed or
performed.

Run focused validation with:

```powershell
python -W error -m unittest tests.test_verifier tests.test_verifier_external_integrity tests.test_kernel tests.test_directives -v
```
