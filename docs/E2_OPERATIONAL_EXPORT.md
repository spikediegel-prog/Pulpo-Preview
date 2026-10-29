# E2 canonical-owner operational projection

The explicit `pulpo.operational_export` API projects public status from an
**already-owning** `PulpoOrchestrator` / `GovernanceKernel`, in its owning thread
at an idle boundary. It does not construct a kernel, retain an extra writer,
open a database, initiate a transaction, create schema, migrate, checkpoint,
repair or converge evidence. Control Center must never import this module.

`freeze_operational_observation(owner, check_database=False)` returns immutable
public `pulpo.operational-observation.v1` primitives: owner-instance source ID,
source timestamp, policy fingerprint, canonical audit result, optional database
check and nullable count of unprojected custody-evidence obligations. Existing
public export schemas are unchanged. `export_operational_observation` reuses the
existing owner-private atomic snapshot publisher and its failure semantics.

The policy fingerprint is the existing kernel policy hash, not a new policy
representation or authorization. Canonical head/chain rejection reports a
failed audit, without repairing it. Other unsupported/unavailable database
status is Unknown or export failure; no success is synthesized. A counter is
read only when the existing canonical custody outbox is available on the
owner's existing SQLite connection. Missing/table-read errors return None,
never zero. Status queries bypass diagnostic activity accounting. No human
signing material, permit, identity, raw audit, database path or credential leaves
the owner. This projection is not another ledger or authenticated attestation.

Configure publication explicitly inside the trusted owner's lifecycle. No new
HTTP route, automatic owner timer or service integration is installed. The UI
reads frozen public bytes only. Source timestamps are not refreshed by the UI;
operator file/unit selections are not an authenticated identity binding.

## Invariant and authority record

Invariant: `CANONICAL_STATE_MUTATION == GOVERNED_CAPABILITY`. Authority gained:
none. New canonical mutations/routes: none. Only explicit public diagnostic
publication writes a file via the existing exporter. No second controller,
executor, signer, reconciliation path or canonical evidence plane is added.
Existing pending evidence can only be projected through its existing governed
owner path; observing it never drains it or permits execution retry/deletion.

Tests select `tests.test_operational_export` and `tests.test_custody_evidence`
(13 cases). They cover actual zero/pending/projected outbox states, audit-head
corruption, denied counter/quick-check reads, idle-transaction requirements,
strict primitive fields, private publication, policy change and no new
connection/canonical writes. Fixture creation and projection use existing
canonical APIs on disposable synthetic state; no customer database is inspected.
The companion separate-process handoff validates the matching stripped observer
contract. Final results and exact tested SHA are recorded with the E2 evidence.

Eight-pass review: Flip keeps untrusted public reads non-authoritative; Reverse
removes writer/database-opening routes from the observer; Invert prevents healthy
observations from becoming enforcement; Inside-Out tests the export's own
transaction/read failures; Darken reports missing/corrupt/unavailable state;
Lighten distinguishes unavailable counts from zero or compromise; Amplify checks
repeated exports leave pending obligations intact; Negate reuses the canonical
audit, policy hash, outbox and publisher rather than adding state machinery.

Claim boundary: bounded behavior is Verified by exact checkpoint tests; host
observations and logs are Recorded; deployment authenticity, universal service
topology, customer infrastructure and production readiness are not established.
No historical implementation exists for this additive contract; fresh fixture
evidence is not generalized into a temporal learning claim. No external-storage,
backup, retention, E3 installer, Windows or production action is included.
