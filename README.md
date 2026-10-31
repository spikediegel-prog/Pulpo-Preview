# Pulpo Preview — The Mad Lads Playground

Customer data handling: see [evidence storage responsibilities and supported choices](docs/CUSTOMER_EVIDENCE_STORAGE.md).

> **Unofficial Pulpo preview and tester branch maintained in `spikediegel-prog/Pulpo-Preview`.**
>
> Explore upcoming Pulpo features, combined PR work, performance improvements, Windows packaging, and governance proofs before upstream release.
>
> **This is not the official Pulpo release branch and does not modify `Ironnember/Pulpo1.0`.**

### Give AI intelligence. Never give it authority.

**Pulpo is a governance and execution-control layer for AI and autonomous systems—built so intelligence can propose actions without gaining the authority to execute them.**

> **Intelligence proposes. Governance disposes. Execution obeys. Evidence reports.**

Pulpo Preview is the testing ground for work that extends that model while preserving the core invariant: **learning, performance, memory, successful execution, or added capability never grants authority.**

## Enterprise readiness: tested stages

**As of 2026-10-29, the bounded E1 Linux engineering scope is complete.**
Testing used an Ubuntu 24.04.5 development VM and an isolated Python 3.12.3
acceptance environment. This establishes the behavior below in its tested
fixtures; it is not production certification or release/deployment approval.

The following are stages within E1, not claims that later enterprise readiness
phases have been completed.

| E1 stage | What was tested | Evidence and status |
| --- | --- | --- |
| 1. Linux service security | Root-owned staged code/configuration, dynamic non-root service identity, no effective capabilities, no-new-privileges, isolated networking, private writable state, authority rejection and fixture cleanup | **Recorded:** successful disposable hardened system-service proof at `da4913186bcb494cf3a9252bdc36294a9d46b4da`. [Service security evidence](docs/E1_SERVICE_SANDBOX_20261028.md). No production service installation claimed. |
| 2. Networking diagnostics and configuration validation | Strict listener parsing and explicit allowlists; create-only reports; TLS/certificate/hostname checks; redirect, timeout and failure handling; rejection of ambient TLS key logging | **Verified:** bounded fixture behavior. **Recorded:** VM inventory without external probes. [Network readiness evidence](docs/E1_NETWORK_READINESS_20261029.md). Customer network integration remains unverified. |
| 3. Local evidence and storage diagnostics | Capacity/inode headroom, read-only flags, path/device uncertainty and report-publication failures; supported SQLite storage-failure fixtures | **Verified:** bounded diagnostics and negative checks. **Recorded:** current shared-volume observations. [Storage evidence](docs/E1_STORAGE_PRESSURE_20261029.md). Local capacity remains operator-managed; no automatic canonical rotation or pruning. |
| 4. Restart recovery and canonical integrity | Full disposable service exit, fresh processes/services reopening saved ext4 fixture state, exact prior audit preservation, spent-permit replay rejection and supported tamper/failure checks | **Verified:** fresh user-service restart and targeted recovery checks. [Recovery evidence](docs/E1_DISK_RECOVERY_20261029.md) and [scope closure](docs/E1_SCOPE_CLOSURE_20261029.md). No OS-reboot, power-loss or whole-database rollback guarantee. |

**Latest targeted E1 verification:** 83 tests passed with warnings treated as
errors, zero skips/failures/errors, at
`74378f5d90ca3e0ef894a19bd138f788b1118cd7`. This included the explicitly enabled
disposable user-service restart proof and clear transient-unit enumeration
afterward. The subsequent scope-closure commit changed documentation only.

**Earlier consolidated acceptance:** 1,055 successful tests and 59 skips across
core, authority and custody suites at
`da4913186bcb494cf3a9252bdc36294a9d46b4da`. The skips cover graphical/platform/
Python-version cases and four PostgreSQL cases without a disposable test DSN;
they are not passes. The suite logs, hardened system-service report and nine
relevant runtime source hashes were rechecked during closure. This was not a
new full-suite or privileged system-service run. These test counts describe
separate runs and must not be added together. See the [acceptance record](docs/E1_ACCEPTANCE_20261029.md).

**Remaining deployment checks:** customer proxy/CA rollout and certificate
lifecycle, routed IPv6, VLAN/VPN and external reachability; skipped GUI/platform/
PostgreSQL coverage; hardware durability and whole-valid-database rollback;
current dependency/container/release admission. These remain **Unknown** or
unassessed, rather than completed enterprise stages.

**External storage is the end user's responsibility:** provisioning, integrity
verification of external copies, backups/tested recovery, access controls,
retention and legal holds. External storage integration and independent backup
durability are outside E1. The optional synthetic archive/VM-to-host experiments
do not change that boundary or establish an independent backup. Pulpo retains
its documented canonical integrity and replay checks. See the [E1 scope closure](docs/E1_SCOPE_CLOSURE_20261029.md).

### E2: owner operational status for Ubuntu Control Center

The additive [owner operational projection](docs/E2_OPERATIONAL_EXPORT.md)
exposes a public policy fingerprint, canonical audit result, optional database
check and nullable count of unprojected custody evidence. The already-owning
process publishes it explicitly through the existing private snapshot exporter;
Control Center never receives a kernel, writer, signer or raw database path.

The companion Ubuntu E2 Operations view combines that frozen metadata with
explicit read-only local service/dependency samples and a session policy
comparison baseline. Missing/stale/failed data stays visible; no UI control
changes policy, drains evidence, retries execution or repairs services. Source
authenticity and deployed enforcement are not inferred from running processes,
matching fingerprints or zero pending evidence. Existing export schemas are
unchanged and no installed service/owner timer is automatically configured.

Owner validation selects 13 export/canonical-convergence checks; companion
Control Center validation selects 94 Ubuntu/Pulpo checks and a separate-process
handoff proof. Exact final commits/results are retained with E2 evidence.
Customer storage/backups/retention/external-copy integrity, Windows/WSL and E3
installation/upgrade are excluded. This is bounded development validation,
not production or release admission.

### E3: Ubuntu lifecycle, state upgrade and publisher verification

**The bounded E3 Ubuntu/Linux engineering test scope is complete.** Tests cover
application install/upgrade/repair/rollback/removal and interruption recovery,
genuine privileged package checks with verified cleanup, canonical legacy-state
migration/restart/replay protection, and a real human-publisher signature checked
against an independently supplied fingerprint and exact Control Center candidate.
No observer kernel/writer or agent-held human signing credential was introduced.

See [E3 scope closure, exact commits, evidence and limits](docs/E3_SCOPE_CLOSURE.md)
and the [state-upgrade proof](docs/E3_STATE_UPGRADE.md). This is local VM/candidate
qualification, not production release admission, publication, certification or a
promise of all-version compatibility. Database downgrade is unsupported. Customer
external storage, backups, retention and external-copy integrity remain excluded.

## Evidence storage and customer responsibilities

**Pulpo is not an indefinite evidence archive or a NAS.** Pulpo provides its
documented evidence generation, integrity checks and supported exports. Customers
are responsible for long-term storage, integrity verification of external copies,
retention obligations, access controls, backups, tested recovery and legal holds.
A saved storage plan or acknowledgment
does not establish compliance, archive completeness or verified delivery.

Local observation history and dashboard exports are bounded. The Evidence
snapshot contains counters and at most **24 recent sanitized events**; subsequent
publication replaces the snapshot. It is not a complete historical audit archive.
The canonical audit currently has **no automatic size/time retention or safe
pruning API** and continues to grow. Monitor capacity and manage workload through
the existing governed owner path; no automatic capacity admission controller is
provided by these settings.

| Customer infrastructure | Current support |
| --- | --- |
| Local filesystem | Explicit owner publication of public JSON snapshots; manual archival handoff |
| Mounted NAS (SMB/NFS) | Same file publisher, conditional on an already mounted filesystem meeting its private ownership, non-symlink path, atomic replacement and directory-sync requirements |
| SAN-backed filesystem | Same conditional file publication; customer provisions and operates the filesystem |
| SIEM/syslog | Not implemented; outside E1 |
| S3-compatible storage | Object delivery is not implemented; outside E1 |
| Hybrid local/remote | Customers may handle public exports manually; automated delivery is outside E1 |

These are filesystem deployment choices, not certified NAS/SAN adapters. In
**System → Setup & storage → Storage & saved setup**, record the intended
public-export destination and acknowledge customer responsibilities, then use
**Remember this setup** to save. The plan does not mount, connect, test, transfer,
schedule, set a retention quota or delete data. Editing its choice/path clears
acknowledgment. Store no credentials in the plan.

**Failed or uncertain export must never cause silent evidence deletion.** Even a
successful dashboard export grants no permission to delete canonical audit or
enforcement-critical state. Preserve replay guards, consumed permits/approvals,
directives, unresolved consequences, custody obligations and tamper evidence.
Do not move a live state database, raw audit payloads or signing material through
the public-export handoff. Integrity checks alone do not establish offsite
durability or protection against a complete database rollback.

Full-audit archival, verified archive receipts, safe pruning and automated legal
holds remain unimplemented. See the [complete data-handling policy, export
boundaries and proposed appliance sizing](docs/CUSTOMER_EVIDENCE_STORAGE.md).
Appliance capacity figures there are proposals, not enforced limits or measured
workload guarantees.

## ⭐ Featured: Windows Preview Installer Experience

For the separate Ubuntu Control Center, an optional
[local installation observation workload](docs/LOCAL_INSTALLATION_OBSERVATION.md)
checks its installed public files through the existing one-use permit path and
publishes the existing Governance/Evidence projections. It is explicitly local
validation, not a production enforcement claim, and is never started by the UI.

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

The historical 2026-10-03 preview snapshot records exact PR heads, checks, inclusion state, conflicts, and provenance; it is not current PR or workflow status. See [PREVIEW.md](PREVIEW.md) and [PREVIEW_MANIFEST.json](PREVIEW_MANIFEST.json).

### Combined preview PRs

The recorded 2026-10-03 combined preview includes:

**#230 · #235 · #237 · #238 · #249 · #275 · #276 · #277 · #289 · #293 · #294 · #295**

PRs **#219, #236, #239, #250, #258, and #267** are retained as separate `preview-pr-<number>` testing branches because their exact passing heads conflicted with the combined preview. Their conflicts were recorded rather than silently resolved by inventing code.

This branch is currently **88 commits ahead of this fork's `main` branch**.

## Major improvements represented in the preview

Local idle-routing candidate: trusted owners can mark disposable work with
`Path(..., background=True)` to give foreground claims priority through the
existing router and permit gate. See [idle background routing](docs/IDLE_BACKGROUND_ROUTING.md)
for integration, shared bounds and durability limits. This is an opt-in library
feature, not a running SQL service or automatic canonical-write batching.
Owners can use [resource lifecycle cleanup](docs/RESOURCE_LIFECYCLE.md) to release
owned workers and database connections on normal exit, errors and interrupts.
See [idle batch stress fixtures](docs/IDLE_BATCH_STRESS.md) for bounded load,
concurrent observers and the remaining starvation/non-preemption limits.
Evidence helpers are [opt-in for testers](docs/EVIDENCE_TUNING.md); serial
collection is the default and fallback, with full evidence checks preserved.

### Minimal SQL/API traffic controller

The existing controller keeps one SQL writer, two API slots, bounded queues and
zero artificial pacing. Optional queue TTL now drops stale queued work without
consuming or renewing permits. Finite monotonic scheduling time and strict slot
release checks close invalid-clock and boolean-token edge cases. Every dispatch
still uses the original kernel consume gate; no second router or executor is
added. See [configuration, tests and limits](docs/TRAFFIC_CONTROL.md).

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

### Local Control Center

Run `pulpo tune` (or `python -m pulpo.cli tune`) to open the existing native
window with Overview, Connections, Governance, Activity, Evidence and System
navigation. On an Ubuntu graphical desktop, install `python3-tk` for the Python
interpreter used by your environment if Tk is missing.

The window opens with real local CPU, memory and storage graphs above expandable
status rows. Sampling runs while Overview is visible; session-only history
starts empty and missing observations stay Unknown. WSL readings describe the
Linux VM, not the full Windows host. Resource thresholds cannot attest governance.
The window performs no automatic fixture checks or configuration writes.
Evidence retains the existing validated performance settings and disposable
benchmarks. Connections and enforcement remain **Unknown** because this window
has no live observer or canonical authority client. Activity is session output,
not the canonical audit. A local comparison never proves deployed enforcement.
For terminal access to the same resolved tuning settings, use `pulpo tune --show`.

See [design alternatives and qualification boundaries](docs/CONTROL_CENTER_DESIGN.md).
See [native resource sources, status semantics and limits](docs/NATIVE_RESOURCE_OVERVIEW.md).
For the WSL-only offline installation and repair preview, see
[WSL recovery package](docs/WSL_RECOVERY_PACKAGE.md). The Windows maintenance
wizard is deferred; the WSL package does not replace an existing checkout.

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

- [Historical preview snapshot and validation](PREVIEW.md)
- [Machine-readable 2026-10-03 preview manifest](PREVIEW_MANIFEST.json)
- [Windows preview executable](docs/WINDOWS_PREVIEW_EXE.md)
- [Audit CPU workers and performance](docs/AUDIT_CPU_WORKERS.md)
- [Current state](docs/CURRENT_STATE.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Governance](docs/GOVERNANCE.md)
- [Persistence](docs/PERSISTENCE.md)
- [Custody secret configuration and rejected test keys](docs/security/CUSTODY_SECRET_CONFIGURATION.md)
- [Agent network and disclosure boundaries](docs/security/AGENT_NETWORK_AND_DISCLOSURE_BOUNDARIES.md)
- [GitHub metadata transport hardening](docs/security/GITHUB_METADATA_TRANSPORT_HARDENING.md)

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
