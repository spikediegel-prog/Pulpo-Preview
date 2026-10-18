# Pulpo Preview Ubuntu security audit — 17 October 2026

Audited canonical Preview main:
`31dd3b757e16af18986b0608b2b94d534a376165`.
Platform: Ubuntu 26.04.1 LTS in WSL2, Python package
`3.14.4-1ubuntu0.2`, SQLite package `3.46.1-9ubuntu0.3`.
This record applies to `spikediegel-prog/Pulpo-Preview`.

## Application change and priority

**Verified:** the custody HTTP API buffered a 524,313-byte request before
calling the isolated proposal stub. Both declared and streamed oversized bodies
reached application routing. The authority service already had bounded request
admission, but the custody app did not install an equivalent guard.

The custody app now uses the same existing stateless admission implementation,
packaged in `pulpo.http_limits`, with these limits:

- Body: 262,144 bytes; reject with HTTP 413.
- Request target: 8,192 bytes; reject with HTTP 414.
- Headers: 32,768 bytes; reject with HTTP 431.

Malformed/negative Content-Length is rejected with HTTP 400. A declared
oversized request is rejected before reading its body. An oversized stream
stops after the first transport chunk that crosses the limit. Small valid
requests and health checks retain their existing behavior.

**Inferred:** unrestricted larger or repeated requests can threaten service
availability. No OOM or large-scale traffic was attempted. Priority is **P1
before untrusted HTTP exposure without gateway limits**, otherwise **P2**.
This is an application admission issue with no assigned CVE; it is not the MCP
SDK HTTP-body CVE. These limits do not provide rate limiting, slow-client
timeouts, or a complete denial-of-service defense.

## Runtime recommendation: CVE-2026-19672

**Verified in the installed OS runtime:** a generated 10,240-byte tar archive
caused Python's `data` extraction filter to create an unintended empty directory
outside the requested destination. Both the destination and unintended directory
remained inside a single disposable test root. No Pulpo canonical state changed.
No archive extraction path was found in the inspected Pulpo application code.

**Proposed, P2 runtime maintenance:** obtain a reviewed Ubuntu security backport
or a runtime release containing the upstream fix. The Ubuntu tracker listed the
Python 3.14 package as needing evaluation at audit time. The upstream fix is
included in Python 3.14.8; distro backports must be evaluated by package revision,
not just the upstream interpreter version string.

- [Ubuntu advisory](https://ubuntu.com/security/CVE-2026-19672)
- [Exact upstream fix, 16dea1e887ec7dfbed735beedd476b21dcc91a79](https://github.com/python/cpython/commit/16dea1e887ec7dfbed735beedd476b21dcc91a79)
- [Python 3.14.8 security release](https://www.python.org/downloads/release/python-3148/)

`upstream-python-19672.patch` is the seven-line upstream module patch, preserved
as a reference. It applied cleanly to a disposable copy of the installed
`tarfile.py` and prevented the same reproduction while preserving the intended
extracted file. No system Python file was changed. It is not imported or applied
by Pulpo, its installer, or CI. This module-only check does not validate a full
runtime upgrade. Do not vendor a replacement stdlib into Pulpo to work around
OS package maintenance.

## Dependency and MCP disposition

**Recorded:** the fresh Linux resolution used `mcp==2.3.0`,
`fastapi==0.141.1`, `starlette==1.8.0`, `uvicorn==0.52.4`,
`httpx2==2.12.0`, `anyio==4.14.2`, and `cryptography==50.0.1`.
The complete advisory scan covered 92 distributions, including scanner tooling,
and returned zero known matches. That scan does not inspect the interpreter,
system SQLite, OpenSSL, external tunnel binaries, or the kernel.

`constraints/security-audit-ubuntu-py314.txt` preserves the reviewed dependency
closure for application, service tests, and optional cloud integrations. It
excludes scanner-only dependencies. This optional constraint set is specific to
Ubuntu / CPython 3.14; it is not a cross-platform lock or a claim about existing
deployments. New resolutions should be reviewed before refreshing it.

The admitted MCP entrypoint runs stdio with a frozen primitive snapshot and
exactly two proposal/evidence tools. Recent HTTP session, bearer audience,
WebSocket, OAuth client, and cross-origin redirect advisories do not establish
an exploitable path through that entrypoint. The inspected repository has no
TypeScript SDK, `mcp-remote`, or `mcp-server-git` dependency. The real SDK probe
compares the entire disposable canonical SQLite dump, not only permit counts.

No SDK version bump is required by a confirmed exploit in this audit. The
reviewed constraints resolve to 2.3.0 for reproducibility. Future HTTP or OAuth
integrations need a fresh transport/authentication review; upgrades alone do not
enable every audience/issuer validation setting.

The 25-row `advisory-applicability.json` records affected versions, sources,
applicability and priorities. Ubuntu's backported SQLite fixes are accounted for;
the upstream `3.46.1` display alone is not evidence of vulnerability.

## Exact evidence

| Check | Result |
| --- | --- |
| Canonical full core suite | 632 tests; PASS; 2 Windows-only skips |
| Focused security suite, overlapping core | 140 tests; PASS; 2 Windows-only skips |
| Canonical custody service | 32 tests; PASS |
| Candidate custody service | 40 tests; PASS; includes 8 new admission cases |
| Eight new tests against canonical implementation | 6 expected failures; 2 passes |
| Authority service | 67 tests; 63 executed PASS; 4 PostgreSQL tests skipped |
| Real MCP SDK bounded hostile-input calls | Entire canonical SQL dump unchanged |
| Declared oversized body, candidate | HTTP 413; zero body bytes read; no service call |
| Streamed oversized body, candidate | HTTP 413 after 278,528 bytes; no service call |
| Runtime tarfile baseline / isolated fix | Reproduced / prevented |

Raw logs, JSON probes, scanner output and `summary.json` are included beside this
record. Labels for temporary workspace paths in copied JSON are normalized;
test content and results are unchanged. Logs refer to the exact pre-PR base and
the initial application candidate, not an unrecorded future PR head.

The first broad run used a Git archive and failed provenance tests requiring
Git history. The recorded final full suite used all 434 reachable commits and
passed. Preserve full history when rerunning those tests.

From a full checkout on Ubuntu / CPython 3.14:

```sh
python3 -m venv /tmp/pulpo-security-venv
/tmp/pulpo-security-venv/bin/python -m pip install pip==26.2.1
/tmp/pulpo-security-venv/bin/python -m pip install \
  -c constraints/security-audit-ubuntu-py314.txt \
  '.[authority,mcp]' './custody-service[test]' \
  './authority-service[test,gcp-auth,gcp-kms,gcp-storage,gcp-cloud-sql]'
PYTHONPATH=. /tmp/pulpo-security-venv/bin/python -B -W error -m unittest discover -s tests -v
PYTHONPATH=custody-service/src:. /tmp/pulpo-security-venv/bin/python -B -W error -m unittest discover -s custody-service/tests -v
PYTHONPATH=authority-service/src:. /tmp/pulpo-security-venv/bin/python -B -W error -m unittest discover -s authority-service/tests -v
/tmp/pulpo-security-venv/bin/python -B scripts/security/probe_preview_boundaries.py . /tmp/pulpo-security-probes.json --expect-limited
python3 scripts/security/probe_tarfile_19672.py /tmp/pulpo-runtime-probe.json
```

The tarfile probe reports runtime behavior in JSON; it intentionally does not
change the host or treat an OS runtime issue as a Pulpo application test failure.
The CI boundary probe enforces the application admission result.

## Authority, capability and legacy disposition

Authority gained: **none**. The patch narrows transport admission. Canonical
state mutations introduced or exposed: **none**. Valid requests still reach the
existing service/kernel/permit path. All test databases are disposable, providers
are mocked, and no human credential is created, copied, enrolled or exported.

Legacy source: the existing
`authority-service/src/pulpo_authority_service/request_limits.py` supplies the
stateless guard implementation. No router, executor, audit, ledger, policy or
authority path is imported. The authority service retains its standalone
packaging and existing implementation.

No general reusable historical-governance lesson is promoted. The admission
regressions were run against exact base SHA
`31dd3b757e16af18986b0608b2b94d534a376165`; they fail there and pass with the
candidate. This is a bounded baseline/candidate comparison, not a claim of
general temporal transfer. Existing temporal-provenance tests ran using their
specified historical Git states in the full suite.

## Adversarial transformation review

| Pass | Analysis |
| --- | --- |
| Flip | Treat the worker/MCP caller as hostile; bound transport inputs before trusting schemas. The MCP host retains only primitive frozen evidence. |
| Reverse | Unbounded buffering precedes proposal validation; admission is the earliest relevant boundary. No valid authority is needed to send a large body. |
| Invert | Accepting an ephemeral proposal is not executing it. Full canonical SQL must remain unchanged under hostile MCP calls. |
| Inside-Out | Test the governor's persistence too; independently check the OS runtime beneath the application. |
| Darken | Repeated larger bodies could exhaust custody memory; that availability consequence is inferred, not experimentally induced. |
| Lighten | The bounded request was ultimately rejected, and an external gateway cap could already mitigate it. The runtime reproduction only made an empty directory. |
| Amplify | Multiple clients/retries aggregate allocations. The guard bounds individual inputs, not rates or all concurrency. |
| Negate | Reuse the existing stateless guard, retain stdio/frozen capability custody, and obtain a vendor runtime fix instead of adding archive capabilities. |

Decision: continue with reviewable source changes and isolated evidence.
No authority expansion or alternate execution mechanism is introduced.

## Unproven release boundaries

Native Ubuntu 24.04, the Microsoft WSL kernel's CVE status, real providers,
human approval ceremonies, cloud services, external tunnel-client binary and
live PostgreSQL remain unverified. The four PostgreSQL tests require a disposable
DSN. The exact Python 3.11 container packages were not inspected; Ubuntu runtime
results cannot certify those Debian-based images. Windows testing is separate.
No host package update, production data operation, merge or deployment is part
of this patch.

## PR source validation

The complete packaged candidate at `e7e9aa7bf98d3e27052fd5a85677ef351fb7d902` was installed in a fresh
WSL Ubuntu environment using the reviewed constraints. Core: 632 tests PASS
(2 Windows-only skips); custody: 40 PASS; authority: 67 tests with 4 PostgreSQL
skips. The enforcing real SDK/admission probe, compilation and dependency
consistency check passed. `pr-validation/` preserves exact logs, source hashes
and exit codes. Subsequent evidence-only commits leave that executable source
unchanged. The runtime probe still reports the separately tracked OS tarfile
issue; it is not a claim that the host runtime was patched.
