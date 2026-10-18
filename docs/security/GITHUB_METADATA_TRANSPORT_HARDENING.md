# GitHub metadata transport hardening

## Invariant and change

Authenticated metadata reads must not forward their bearer credential through a
redirect, inherit ambient proxy settings, or buffer an unlimited response.

`GitHubRESTMetadataReader` now uses the existing `secure_urlopen` transport:
redirects are rejected before a follow-up request, ambient proxies are ignored,
and trusted CA configuration follows the existing explicit Pulpo policy.
Metadata bodies are limited to 1 MiB, with one extra byte read to detect overflow.
Responses are closed on success, status rejection, oversize rejection and read
failure. Transport exception chains are suppressed so provider-supplied failure
details are not accidentally surfaced as token-bearing traceback text.

The reader's injectable opener remains a trusted construction-time testing and
integration seam. A caller that supplies its own opener owns that transport's
network behavior; it must preserve the same credential boundary. This is not
an agent-supplied redirect or transport parameter.

## Verified reproduction scope

An Ubuntu loopback-only TLS fixture substitutes the fixed GitHub API origin
inside the test process. It uses a temporary self-signed TLS test certificate
and a fresh synthetic bearer value. A successful authenticated HTTPS read is
the positive control. The redirect then changes origin from one loopback HTTPS
port/hostname to another; no actual GitHub endpoint, real credential or external
system is involved.

The pre-fix reader forwarded the synthetic bearer value to that second origin.
It also accepted a 2 MiB fake metadata response using an unbounded `read()` and
did not explicitly close the response. The candidate rejects the redirect
without a destination call and rejects the oversized body after a bounded read.

These observations establish a credential-forwarding transport weakness and
missing response bound. They do not establish control of GitHub's HTTPS
responses by an attacker or compromise of any real account. Exploitation needs
a redirect from the configured trusted origin or an equivalent trusted network
interception condition. No CVE identifier is assigned by these tests.

## Evidence and authority classification

- **Verified:** loopback TLS reproduction, positive control, candidate regression
  tests, exact response-limit boundary, response cleanup and bounded failure
  behavior. The parent audit's raw before/after logs identify the exact tested
  working-source file hashes; a Git commit alone does not identify dirty code.
- **Verified, bounded independent controls:** eight spawned processes consumed
  one SQLite permit once; eight distinct reservations stayed within the shared
  budget; six executors produced one durable fake-provider effect; a process
  opened before directive revocation could not consume afterward. SIGKILL at
  preflight, before a fake effect and after a durable fake effect preserved the
  expected retry/reconciliation boundary without duplicate effects.
- **Unknown:** production exploitability, native Ubuntu behavior outside the
  tested WSL environment, hostile network/proxy control, physical power loss,
  filesystem rollback protection and all possible execution interleavings.
- **Authority delta:** credential-routing and input admission are narrowed. No
  kernel, approval policy, permit authority, budget, credential ownership or
  canonical state writer is added. No canonical mutation is introduced.
- **Legacy disposition:** reuse the existing stateless secure transport; no
  second executor, ledger, authority plane or transport-policy system.
- **Temporal boundary:** compare the same current working source with and
  without this small patch. No cross-checkpoint organizational-learning or
  historical-system transfer claim is made.

## Eight-pass adversarial review

| Pass | Result |
| --- | --- |
| Flip | Treat even the configured provider's redirect as untrusted instructions about credential routing. |
| Reverse | Prevent the follow-up request, before a downstream endpoint can receive the bearer value. |
| Invert | Successful metadata parsing after a credential leak is not a valid transport success. |
| Inside-Out | Apply the existing explicit CA/proxy policy to this Pulpo reader too; custom openers remain trusted code. |
| Darken | A malicious redirect could expose the configured token; no real compromise or origin control is asserted. |
| Lighten | A benign rename redirect can now fail closed and require trusted configuration correction. |
| Amplify | Repeated reads cannot repeatedly leak credentials through followed redirects; response buffers remain bounded. |
| Negate | Use the existing secure opener instead of building another network authority or allowing broader routes. |

The 1 MiB body limit is not a total request deadline, concurrency limit, universal
JSON-complexity bound or host sandbox. Existing socket timeouts and deployment
controls remain necessary. Legitimate redirects are deliberately rejected;
update the trusted repository binding rather than automatically following them.
