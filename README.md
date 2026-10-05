# Pulpo Preview — The Mad Lads Playground

> **Unofficial Pulpo preview and tester branch maintained in `spikediegel-prog/Pulpo-Preview`.**
>
> Explore upcoming Pulpo features, combined PR work, performance improvements, Windows packaging, and governance proofs before upstream release.
>
> **This is not the official Pulpo release branch and does not modify `Ironnember/Pulpo1.0`.**

### Give AI intelligence. Never give it authority.

**Pulpo is a governance and execution-control layer for AI and autonomous systems—built so intelligence can propose actions without gaining the authority to execute them.**

> **Intelligence proposes. Governance disposes. Execution obeys. Evidence reports.**

Pulpo Preview is the testing ground for work that extends that model while preserving the core invariant: **learning, performance, memory, successful execution, or added capability never grants authority.**

## ⭐ Featured: Windows Preview Installer Experience

Pulpo Preview now includes a **portable Windows x64 setup executable** designed to make testing much easier.

Instead of requiring testers to manually prepare a Python environment just to try the setup path, the Windows preview packages the setup CLI and Python runtime into:

```text
pulpo-preview.exe
```

### Quick start

1. Open the [Windows Preview Executable workflow](https://github.com/spikediegel-prog/Pulpo-Preview/actions/workflows/windows-preview-exe.yml).
2. Select a successful run for the preview commit you want to test.
3. Download the `pulpo-preview-windows-x64-<commit>` artifact.
4. Extract the ZIP.
5. Double-click **`pulpo-preview.exe`**.

Quick start performs Pulpo's conservative setup self-check and writes:

```text
%LOCALAPPDATA%\PulpoPreview\setup-report.json
```

The executable verifies that a valid synthetic audit is accepted and a tampered stored hash is rejected. Quick start does **not** request an authority change.

For the full setup interface:

```powershell
.\pulpo-preview.exe --help
.\pulpo-preview.exe setup --json-report setup-report.json
```

The artifact includes the executable, instructions, source commit, SHA-256 checksum, and smoke-test evidence.

**Verified local prototype:** Windows 11 x64, bundled Python 3.12.10, PyInstaller 6.22.3, with **7 executable smoke checks passing** while project source and the host Python installation were removed from the search path.

The current executable is an **unsigned portable preview build**, not an MSI, Windows service, production deployment, or publisher-signed release. See [Windows Preview Executable](docs/WINDOWS_PREVIEW_EXE.md) for build reproduction, evidence, and limitations.

---

## What's in Pulpo Preview

The current `preview` branch combines selected upstream PR work plus preview-specific validation and repair work.

The snapshot manifest records exact PR heads, checks, inclusion state, conflicts, and provenance. See [PREVIEW.md](PREVIEW.md) and [PREVIEW_MANIFEST.json](PREVIEW_MANIFEST.json).

### Combined preview PRs

The recorded 2026-10-03 combined preview includes:

**#230 · #235 · #237 · #238 · #249 · #275 · #276 · #277 · #289 · #293 · #294 · #295**

PRs **#219, #236, #239, #250, #258, and #267** are retained as separate `preview-pr-<number>` testing branches because their exact passing heads conflicted with the combined preview. Their conflicts were recorded rather than silently resolved by inventing code.

This branch is currently **88 commits ahead of this fork's `main` branch**.

## Major improvements represented in the preview

### Performance and adaptive verification

Pulpo Preview adds performance paths intended to increase throughput without moving governance authority away from the canonical kernel:

- multi-core audit verification;
- bounded audit digest caching;
- parallel read-only evidence collection;
- sharded evidence-digest caching;
- machine-bound performance profiles;
- adaptive worker-count and batch-size selection;
- memory-scaling benchmarks;
- SQLite state benchmarks;
- performance-profile generation;
- recorded benchmark and comparison artifacts.

Workers can accelerate immutable calculations, but they do **not** issue permits, change policy, grant authority, bypass replay protection, reconcile consequences, or append canonical evidence.

Historical development measurements recorded roughly **2.7× faster** verification on a 10,000-record synthetic audit using four warm workers. That is a recorded development measurement, not a universal performance guarantee.

### SQLite persistence and evidence work

The preview contains extensive SQLite persistence work and evidence, including:

- restart-safe governance state;
- approval-ID, nonce and permit persistence;
- durable audit history;
- transactional commerce state;
- spend and reservation persistence;
- audit-chain tamper detection;
- SQLite benchmarking and reconciliation artifacts;
- conservative connection cleanup;
- replay, restart, rollback and tamper-focused testing.

The preview-specific **Dark Mirror Windows repair** closes commerce budget SQLite connections after transaction handling while preserving WAL, FULL synchronization, `BEGIN IMMEDIATE`, replay protection, budget limits, and transaction semantics.

The focused repaired Windows path passed **32 tests** with warnings treated as errors.

### Governance and authority hardening

The preview carries work around:

- exact-intent permit binding;
- one-use permit semantics;
- verifier-backed approval envelopes;
- pinned verifier/key/algorithm/deployment constraints;
- bounded authority lifetimes;
- bounded agent action/resource/cost grants;
- execution-context binding;
- capability derivation versus capability-use separation;
- external authority-service composition;
- authority request limits;
- explicit transport and execution boundaries.

The core rule remains unchanged:

**Intelligence can improve a proposal. It cannot promote itself into greater authority.**

### MCP and execution-boundary work

The preview includes additional MCP and execution-boundary work such as:

- MCP boundary hardening;
- Secure MCP Tunnel binding;
- trusted frozen MCP snapshot behavior;
- execution-context checks;
- network exposure inspection;
- transport-security controls;
- provider-route isolation proofs;
- Windows MCP-related preview work.

These surfaces do not make MCP, plugins, workers, models, shells, or providers sources of canonical authority.

### Consequence, reconciliation and governed memory

Pulpo Preview extends the consequence path with:

- effect reconciliation;
- bounded commerce execution;
- outcome-memory gating;
- canonical custody evidence requirements;
- uncertain-consequence handling;
- external execution/evidence proofs;
- Redsys sandbox governance work;
- Dark Mirror proof tooling.

Pulpo preserves uncertainty rather than converting it into permission:

```text
AUTHORIZED / ATTEMPTED / CONSEQUENCE UNKNOWN
```

An unknown consequence does not automatically create retry authority.

## Setup from source

The preview also includes the `pulpo setup` bootstrap path.

After installing the package in your environment:

```powershell
pulpo setup --json-report perf-results\pulpo-setup-report.json
```

Or directly from the source checkout:

```powershell
python -m pulpo.cli setup --json-report perf-results\pulpo-preview-setup.json
```

Setup can:

- detect OS, Python version, and logical CPU count;
- reuse a matching machine performance profile;
- reject stale or mismatched profiles;
- run bounded local calibration over synthetic audit data;
- verify valid and deliberately tampered audit cases;
- persist a local performance profile for later adaptive verification.

An existing benchmark can also seed setup:

```powershell
pulpo setup --benchmark perf-results\memory-scaling-ddr4-3200-cl14-batched.json
```

The setup path reports:

```text
Authority changes ........ NONE
```

Performance configuration is not an authority credential.

## Test the preview

```powershell
git clone --branch preview https://github.com/spikediegel-prog/Pulpo-Preview.git Pulpo-preview
cd Pulpo-preview
python -W error -m unittest discover -s tests -v
python -m pulpo.cli setup --json-report perf-results/pulpo-preview-setup.json
```

### Recorded validation

The combined preview has recorded clean Linux/WSL validation of **445 tests passing with warnings treated as errors** on Python 3.14.4.

The Windows Dark Mirror repair has a separate focused validation of **32 passing tests**. The full Windows suite still has known pre-existing failures and therefore is **not** claimed as fully passing.

See [PREVIEW.md](PREVIEW.md) for the exact tested commits, logs, hosted-run boundary, Windows results, and remaining unknowns.

## Pulpo's three-plane model

| Plane | Responsibility |
| --- | --- |
| **Intelligence** | Reasons, plans, learns, and proposes. It cannot create authority. |
| **Governance** | Resolves identity, authority, policy, budget, approvals, permits, evidence, reconciliation, and governed memory. |
| **Execution** | Performs only the exact consequence authorized by a valid permit. |

The lifecycle is explicit:

```text
Purpose → Intent → Authority → Policy → Decision → Permit → Execution → Evidence → Reconciliation → Memory → Adaptation → Purpose
# Pulpo

For pulpo-preview, click on the link in the upper right-hand corner under About, or go to the preview tree here: https://github.com/spikediegel-prog/Pulpo-Preview/tree/preview

Pulpo is the governance and evidence plane between AI intelligence and consequential execution. It turns explicit intent into deterministic governance, binds allowed work to narrowly scoped one-use permits, and preserves durable evidence for verification and reconciliation.

This repository is the clean canonical Pulpo project. The older `Iron-Ember/pulpo` repository remains historical reference material; its accumulated plans, generated evidence, machine-specific scripts, and CI workarounds are intentionally not imported here.

## Proven now

The base dependency-free suite and optional asymmetric-authority suite prove:

- unknown, incomplete, and over-budget intents fail closed;
- selected high-impact actions require a verifier-backed approval envelope;
- authority policy pins verifier, key, algorithm, public-key fingerprint,
  deployment, and maximum approval lifetime;
- optional Ed25519 verification contains public material only and exposes no
  signer;
- caller-controlled boolean approval and authorization timestamps are absent
  from the evaluation API;
- permits are bound to the exact intent and cannot be replayed;
- an optional SQLite state backend preserves approval-ID, nonce, permit, and
  audit state across process restart in the same canonical kernel;
- persisted audit-chain tampering fails closed when the kernel restarts;
- configured agent roles cannot exceed their action, resource, or cost grant.
- a bounded domain order is bound to its full request, quote, reserved budget, and one-use permit.
- a configured external verifier checks v2 approval envelopes bound to trust,
  deployment, intent, policy, principal, session, nonce, issue time, and expiry
  using the kernel's trusted clock.
- transactional SQLite commerce state preserves reservations, attempted orders,
  reconciliation, and spend across restart.

PulpoGit provides a read-only clarity projection for local source state. It
distinguishes canonical, proposal, stale, diverged, detached, and dirty
checkouts without inferring tests or authority. See the
[PulpoGit clarity proof](proofs/git_clarity/README.md).

```bash
python -m unittest discover -s tests -v
```

## Minimal example

```python
from pulpo import GovernanceKernel, Intent, Policy

kernel = GovernanceKernel(
    Policy(
        allowed_actions=frozenset({"read", "write"}),
        max_cost=100,
    )
)

intent = Intent("agent:builder", "write", "repo:README.md", cost=5)
decision = kernel.evaluate(intent)

if decision.outcome == "allow":
    assert kernel.consume(decision.permit, intent)
```

## Evidence before claims

Pulpo Preview intentionally keeps proof boundaries visible.

Repository tests and bounded provider proofs establish controls only in their tested topology. They do not automatically prove universal cloud containment, operating-system integrity, model-provider custody, hardware trust, hostile-code isolation, or production readiness.

**Architecture is not proof. Execution is not authority. Evidence is not permission.**

For the current preview evidence and limitations, start with:

- [Preview status and validation](PREVIEW.md)
- [Machine-readable preview manifest](PREVIEW_MANIFEST.json)
- [Windows preview executable](docs/WINDOWS_PREVIEW_EXE.md)
- [Audit CPU workers and performance](docs/AUDIT_CPU_WORKERS.md)
- [Current state](docs/CURRENT_STATE.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Governance](docs/GOVERNANCE.md)
- [Persistence](docs/PERSISTENCE.md)

## Host bound and Pulpo bound

Pulpo is only as secure as the host enforcing it. The kernel, permit store, and evidence journal assume the host remains the host that was installed and continues enforcing its process, file, and boot policy.

Pulpo does not own firmware, the boot chain, hidden storage, management controllers, host administrator privileges, or the operator's decision to continue running a machine that can no longer be trusted.

Pulpo remains accountable for the contract it states on a host that is still enforcing it: fail-closed governance, exact permit binding, replay protection, bounded grants, uncertain-consequence handling, and visible audit-chain integrity.

Survival of arbitrary host compromise, rollback-proof storage, trusted verifier bootstrap, network isolation, and hostile-code sandboxing require separately established deployment controls.

---

## Preview status

**Pulpo Preview is for testing, validation, benchmarking, experimentation, and early access to selected work.**

It is not an official Pulpo release and should not be represented as production-ready merely because a test, benchmark, executable, or individual PR check passes.

For official Pulpo development and releases, see [Ironnember/Pulpo1.0](https://github.com/Ironnember/Pulpo1.0).
