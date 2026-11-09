# Pulpo Preview — Governance-Aware Execution Fabric

## Give AI intelligence. Never give it authority.

Pulpo is a governance-aware execution fabric for AI and autonomous systems.

It separates intelligence from authority so that consequential actions occur only through explicitly governed execution paths.

**Intelligence proposes. Governance disposes. Execution obeys. Evidence reports.**

Pulpo Preview is the public testing ground for upcoming Pulpo capabilities, governance proofs, execution controls, performance improvements, persistence work, and validation efforts. It exists to explore new ideas without weakening the core invariant:

> Intelligence may become more capable.
>
> It must never gain authority simply because it became more capable.

---

# Why Pulpo Exists

AI systems are rapidly becoming more capable.

Most architectures connect intelligence directly to execution:

```text
AI
 ↓
Tool
 ↓
Action
```

As capability increases, so do the consequences of mistakes, compromise, replay attacks, unauthorized actions, and incorrect assumptions.

Pulpo takes a different approach.

Instead of asking:

> "What should the AI do?"

Pulpo asks:

> "What is authorized to happen?"

That distinction matters.

Capability does not create authority.

Learning does not create authority.

Memory does not create authority.

Performance does not create authority.

Successful execution does not create authority.

Authority must be granted explicitly.

---

# Three-Minute Tour

Traditional agent architecture:

```text
AI
 ↓
Tool
 ↓
Action
```

Pulpo architecture:

```text
AI
 ↓
Intent
 ↓
Governance
 ↓
Permit
 ↓
Execution
 ↓
Evidence
 ↓
Reconciliation
```

The AI proposes.

Pulpo evaluates.

Execution occurs only when governance authorizes it.

Every consequential action is bounded, recorded, and subject to later verification.

---

# The Permit Model

At the center of Pulpo is the concept of an execution permit.

Every consequential action requires an explicit permit.

Permits can be bound to:

- identity
- intent
- policy
- budget
- approvals
- execution context
- deployment
- expiration windows
- resource constraints

Permits are intentionally narrow.

A permit authorizes exactly the action it was created for.

Permits cannot be expanded by an agent.

Permits cannot be upgraded by a model.

Permits cannot be reinterpreted after issuance.

Permits can be consumed once.

Replay attempts fail.

Expired permits fail.

Revoked permits fail.

No permit means no execution.

---

# Why Pulpo Is Different

Most AI governance systems focus on monitoring agents.

Pulpo focuses on governing execution.

Most systems attempt to observe or influence behavior after an agent begins operating.

Pulpo establishes authority boundaries before execution occurs.

Governance remains separate from:

- models
- prompts
- agents
- plugins
- tools
- providers
- workflows
- memory systems
- optimization layers

Changing intelligence does not automatically change authority.

This separation allows intelligence to improve without weakening governance.

---

# Example

An AI assistant proposes:

> "Transfer $500 to Vendor X."

Pulpo evaluates:

- Is this action allowed?
- Is budget available?
- Is approval required?
- Is the permit valid?
- Has this permit already been consumed?
- Has authorization expired?
- Does the request match policy?

If approved:

```text
Permit
  ↓
Execution
  ↓
Evidence
```

If denied:

```text
Decision
  ↓
Evidence
  ↓
No Execution
```

The action never occurs.

The denial remains visible.

The evidence remains available for review.

---

# The Three-Plane Model

| Plane | Responsibility |
|---------|---------|
| **Intelligence** | Reasons, plans, learns, optimizes, and proposes. It cannot create authority. |
| **Governance** | Resolves identity, authority, policy, approvals, budgets, permits, evidence, reconciliation, and governed memory. |
| **Execution** | Performs only the exact consequence authorized by a valid permit. |

---

# Lifecycle

Pulpo treats execution as an explicit governance process:

```text
Purpose
    ↓
Intent
    ↓
Authority
    ↓
Policy
    ↓
Decision
    ↓
Permit
    ↓
Execution
    ↓
Evidence
    ↓
Reconciliation
    ↓
Memory
    ↓
Adaptation
    ↓
Purpose
```

Intelligence may participate in several stages.

Authority remains governed throughout the entire lifecycle.

---

# What Pulpo Provides

Pulpo provides capabilities across several governance domains.

## Governance

- Explicit authority evaluation
- Policy enforcement
- Approval workflows
- One-use permit issuance
- Exact-intent binding
- Execution-context binding
- Replay protection
- Authority expiration
- Resource constraints
- Budget controls

## Evidence

- Durable audit chains
- Tamper detection
- Evidence generation
- Audit verification
- Consequence reconciliation
- Governance projections
- Validation reporting

## Persistence

- SQLite-backed governance state
- Approval persistence
- Nonce persistence
- Permit persistence
- Commerce persistence
- Restart-safe recovery
- Transactional state management

## SQLite reconciliation scans

**Verified:** `SQLiteKernelState.append_unique()` streams the complete ordered
audit scan and deterministically closes its SELECT cursor, including when
malformed JSON raises and the caller retains the exception traceback. It keeps
`BEGIN IMMEDIATE`, original replay payloads without writes, ambiguity rejection,
and the existing canonical append and commit/rollback path.

**Verified in local tests:** The malformed-nonfinal-row regression checks
rollback and a successful second-connection COMMIT while the traceback remains
retained. WSL2 Linux with Python 3.12.14 / SQLite 3.53.1 passes 34 focused and
381 core tests with warnings treated as errors. Native Windows with Python
3.12.10 / SQLite 3.49.1 passes all eight unique-scan tests; its broader suite
has the same failing tests on the original and revised PR head.

**Verified in the local allocation benchmark:** At 10,000 same-event rows,
Python allocation peak is 7,640 bytes with cursor cleanup, compared with
7,504 bytes for the original streaming scan and 11,354,317 bytes for `fetchall()`.
This measures Python allocations; general throughput and physical power-loss
durability remain **Unknown**. See the [unique-scan tests](tests/test_unique_audit_scan.py),
[benchmark](scripts/benchmark_unique_audit_scan.py), and
[original streaming change record](docs/UNIQUE_AUDIT_SCAN_STREAMING.md).

## Verification

- Verifier-backed approvals
- Approval envelopes
- Pinned trust relationships
- Deployment constraints
- Signature verification
- Audit validation
- Governance verification tooling

## Learning library

[Source-linked learning library](docs/learning/README.md): 18 annotated book sources, Python and financial-literacy curriculum, and a runnable **offline synthetic** input-verification lab. This material is educational and does not grant a permit, spending authority, access to production systems, or independent runtime custody. Books not available as authorized full text are linked by publisher excerpt or table of contents, not mirrored.

---

# Performance Without Authority Expansion

Pulpo includes optimization paths designed to increase throughput without moving authority outside the governance boundary.

Current areas of work include:

- multi-core audit verification
- bounded audit caches
- parallel evidence collection
- adaptive worker sizing
- adaptive batch sizing
- memory-scaling benchmarks
- SQLite benchmarking
- performance-profile generation

Workers may accelerate calculations.

Workers do not:

- issue permits
- create approvals
- grant authority
- change policy
- bypass replay protection
- modify governance outcomes

Performance never becomes authority.

---

# Persistence and Recovery

Pulpo treats persistence as part of governance rather than an implementation detail.

Current work includes:

- durable audit history
- restart recovery
- replay protection
- permit persistence
- approval persistence
- commerce persistence
- spend tracking
- reservation tracking
- audit-chain validation
- rollback-focused testing
- tamper-focused testing

Recovery is intended to preserve governance invariants rather than merely restore application state.

---

# Enterprise Readiness

Pulpo Preview includes engineering validation across several readiness areas.

## E1 — Core Linux Engineering Scope

Validated areas include:

- service isolation
- privilege reduction
- local persistence
- audit integrity
- recovery behavior
- configuration validation
- storage diagnostics

## E2 — Operational Visibility

Focused on:

- owner operational projections
- integrity visibility
- canonical audit visibility
- read-only operational status
- deployment comparison workflows

## E3 — Lifecycle Qualification

Focused on:

- installation
- recovery
- upgrades
- rollback handling
- package verification
- state migration
- publisher verification

These stages represent bounded engineering validation and should not be interpreted as production certification.

---

# Evidence Before Claims

Pulpo intentionally keeps proof boundaries visible.

Repository tests and validation efforts establish controls only within their tested scope.

They do not automatically establish:

- universal cloud containment
- operating system integrity
- hardware trust
- model provider custody
- hostile code isolation
- production readiness
- deployment authenticity

## Host bound and Pulpo bound

Pulpo is only as secure as the host it is running on. The kernel, permit store, and evidence journal assume that host is still the host that was installed and that it is still enforcing process, file, and boot policy. Pulpo does not own the boot chain, firmware, NVRAM, unused or hidden partitions, storage-controller firmware, the management controller, service-account privileges, or the decision to keep operating a machine that can no longer be measured. An OS reimage, snapshot, or rollback does not restore those layers. A compromised host can skip the process, replace local state, or omit a record. That is an operator incident, not a Pulpo control failure.

Pulpo is accountable for the contract it states, on a host that is still enforcing it: unknown, incomplete, and over-budget intents fail closed; a permit is bound to one exact intent and cannot be replayed; loss of contact does not widen a grant; uncertain execution remains unknown and does not become retry authority; a visible broken audit chain fails closed. A defect in that contract is a Pulpo failure. Survival of host compromise, rollback-proof storage, trusted verifier bootstrap, network isolation, and hostile-code sandboxing are not part of that contract.

Three principles guide the project:

> Architecture is not proof.
>
> Execution is not authority.
>
> Evidence is not permission.

---

# External Storage Responsibilities

Pulpo is not an indefinite evidence archive.

Customers remain responsible for:

- retention
- backups
- tested recovery
- legal holds
- access controls
- external storage integrity
- long-term archival strategy

Pulpo provides governance evidence and export mechanisms.

It does not eliminate operational responsibility.

---

# Setup

Install Pulpo and generate an initialization report:

```bash
pulpo setup --json-report perf-results/pulpo-setup-report.json
```

Or directly from source:

```bash
python -m pulpo.cli setup \
  --json-report perf-results/pulpo-preview-setup.json
```

Setup can:

- detect platform characteristics
- generate performance profiles
- validate synthetic audit chains
- verify tamper detection
- calibrate performance settings

Setup reports:

```text
Authority changes ........ NONE
```

Performance configuration is never an authority credential.

---

# Verify Governance Contracts

Run:

```bash
pulpo verify
```

or

```bash
python -m pulpo.cli verify
```

The verifier exercises governance probes and produces validation evidence.

Checks requiring deployment-specific infrastructure remain explicitly identified instead of silently assumed.

---

# Pulpo Preview

Pulpo Preview is the testing and validation channel for future Pulpo capabilities.

Preview builds may include:

- upcoming governance features
- persistence improvements
- verifier work
- recovery experiments
- execution-boundary hardening
- Control Center enhancements
- benchmarking efforts
- validation tooling

Preview artifacts are for testing, experimentation, and qualification.

They should not be represented as production certification merely because a feature, benchmark, workflow, or test passes.

---

# Philosophy

The objective is not to create a smarter agent.

The objective is to ensure that increasing intelligence does not automatically produce increasing authority.

Pulpo exists to keep those concerns separate.

```text
Intent proposes.

Authority decides.

Execution obeys.

Evidence reports.
```
