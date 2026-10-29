# Evidence archival: copy-only design and synthetic experiment

Date: 2026-10-29. Baseline: `63c67d6f04abc147934d5c947c5a123aff4897a5`.

Scope update, 2026-10-29: the user assigns external storage, retention,
backup/restore operations and integrity verification of external copies to the
end user. This archival design and its synthetic prototype are retained as
optional exploratory work, not an E1 requirement or approved implementation
roadmap. Independent storage and archival/pruning work are not prerequisites
for the bounded closure in `E1_SCOPE_CLOSURE_20261029.md`. Pulpo's existing
canonical integrity checks remain in scope and unchanged.

## Status and invariant

**Proposed:** a production archival contract. **Verified in bounded tests:** the
synthetic prototype described below. No live evidence exporter, remote durable
receipt, acknowledgment watermark, retention policy or pruning capability is
implemented by this change. It changes no canonical record or service setting.

`CANONICAL_STATE_MUTATION == GOVERNED_CAPABILITY` remains the invariant. One
canonical owner creates evidence and governs any future acknowledgment mutation.
Transport, storage and UI acquire no writer, signer, executor or deletion rights.
An archive receipt is evidence to evaluate, never authority to remove records.

## Current boundaries

The bounded public export is a sanitized projection (at most 24 events), not a
complete archive. Follow `CUSTOMER_EVIDENCE_STORAGE.md`: do not hand off live
databases, raw audit payloads, permits or credentials through that export route.
The authority-service GCP evidence sink is service-specific; its existence does
not establish a generic kernel archive or authorize a second evidence plane.

The canonical audit verifiers start at genesis (`"0" * 64`). Removing an archived
prefix would break that verification contract. Incremental segments and pruning
therefore need a separately reviewed canonical trusted-anchor mechanism, governed
admission and restart proofs. This experiment does not introduce an alternate
chain verifier or pretend that a local file is an independent backup.

## Proposed production contract

1. The trusted canonical owner freezes an immutable, complete prefix from genesis
   at a fixed sequence and tip, without racing live writes. It supplies provenance,
   schema, source identity, range, byte count, digest and tip through a trusted
   channel. Full payload classification, redaction constraints, encryption, key
   custody and recipient access require review before any live exporter exists.
2. A transport receives only approved frozen bytes and public provenance. It
   cannot open canonical storage or reconstruct a signer. The canonical verifier
   checks integrity against the owner pin. A valid chain alone does not establish
   authenticity, completeness or freshness: the expected count/tip must not come
   from the archive's own assertions. Missing pins fail closed.
3. Publication is create-only and content addressed. Exact duplicates are
   reverified; conflicting bytes are preserved and rejected. Partial staging is
   not an archive. Unknown outcomes remain unknown until object retrieval and
   verification resolve them. An unavailable destination never licenses dropping
   canonical evidence or bypassing governed admission.
4. An independent remote receipt must bind destination identity, immutable object
   version, source/range/tip, byte count/digest and backend retention semantics.
   Authentication and independent retrieval/readback must be established, with
   restore testing. Local fsync/reopen observations do not satisfy this contract.
   The adapter and backend, including outage, quota and credential-expiry behavior,
   remain unimplemented and unverified here.
5. Any canonical acknowledgment/watermark is a new governed capability, currently
   absent. Transport/UI cannot self-authorize it. Missing, altered, stale,
   mismatched or unverifiable acknowledgments cause no mutation. A future owner
   must also define ordered retry and rollback/replay protection.
6. Archival copies never imply pruning. Consumed permit/replay guards, unresolved
   custody/outbox/consequences, active directives, tamper evidence and applicable
   holds must remain available to the canonical owner. A hold blocks any future
   retention transition. This document specifies no legal-hold enforcement or
   compliance certification. Until the canonical anchor/admission/recovery design
   is reviewed, canonical deletion and rotation remain unavailable.
7. On destination outage or storage pressure, use the existing trusted-owner
   admission policy. Do not silently discard evidence, expand authority, or build
   a second controller. Capacity thresholds and operational escalation remain
   deployment decisions; the prototype does not change them.

## Disposable prototype

Run as an ordinary Linux user, from the repository, with the approved runtime:

```sh
python -W error -m scripts.prototype_evidence_archive --evidence-dir /absolute/private/evidence-directory
```

The CLI has no live source or archive-destination argument. It accepts only
Pulpo's existing setup-calibration fixture rows, verifies them with
`AuditVerificationEngine(workers=0, cache_size=0)`, and rejects even an otherwise
valid chain containing a nonfixture event. It creates no kernel, database,
permit or signer. Each run uses private disposable directories beside the
repository, removes them, and publishes only a sanitized create-only test report.

The local file experiment uses private owned directories, descriptor-relative
access, no symlink traversal, bounded reads, exact bytes and a frozen fixture pin.
Publication fsyncs a private staging file, creates the final name exclusively,
syncs the directory and reopens/reverifies the object. A directory-sync error
preserves the linked object but returns no successful observation; retry verifies
it again. Only the experiment's own temporary files are cleaned up.

Receipts explicitly say `pruning_authorized=false` and `authority_effect=none`.
Their checker compares exact types/fields, the expected pin and local directory
identity, then reopens the object. Receipts do not self-authenticate and are not
proof against a malicious same-user writer, rollback of an entire store or physical
storage failure. There is no canonical acknowledgment. The child interruption
test kills only its own process after a partial fixture write; it is not a VM
reboot, power-loss test or end-to-end remote recovery test.

## Eight-pass doctrine review

| Pass | Challenge | Boundary/result |
| --- | --- | --- |
| Flip | Storage claims authority over its source | All receipts have zero authority; no canonical mutation entry point. |
| Reverse | Acknowledgment precedes durable publication | No success on write/sync/readback failure; retry must reverify. Remote durability remains unknown. |
| Invert | Valid chain is substituted for the expected complete range | Owner pin includes byte count/digest/count/tip; a valid shorter prefix is rejected. |
| Inside-Out | Transport reaches canonical writers or private signers | Only known fixture rows accepted; no live source CLI; tests block kernel/SQLite constructors during fixture creation. |
| Darken | Lost response, interrupted write, unavailable/full destination | Lost-ack retry, real child kill, injected write failure and directory-sync uncertainty are bounded tests; no pruning follows. |
| Lighten | Minimal evidence hides missing source coverage | Report labels synthetic scope and local observations; public projections cannot become a complete archive by renaming them. |
| Amplify | Duplicates, oversized/hostile inputs, path aliases | Bounded count/bytes, strict JSON/field types, exclusive create, symlink/FIFO rejection; no scale/performance claim. |
| Negate | Receipt absent/forged, corruption, retention transition forbidden | Reject missing/altered/wrong-store observations; preserve conflicting object; no deletion or hold override API. |

## Evidence and claim limits

Targeted command:

```sh
python -W error -m unittest tests.test_archive_prototype tests.test_frozen_audit_verification tests.test_audit_worker_isolation tests.test_network_e1 -v
```

The precommit run recorded 31 passing tests (15 archive-specific). Standalone
proof and committed-source rerun are recorded separately with their exact commit,
hashes and output paths. Tests include corruption/truncation, duplicate keys,
wrong pins/types/stores, valid nonfixture rejection, create-only retry, failed
directory sync, write-full injection, partial child interruption, symlink/FIFO
rejection and scratch cleanup. Injected faults are distinguished from the actual
child interruption. No physical disk exhaustion is induced on the personal VM.

**Recorded:** earlier E1 service acceptance is separate historical evidence and
is not rerun or promoted by this change. **Unknown:** remote retention enforcement,
remote restore, VM reboot/power-loss durability, real payload classification,
customer holds, incremental anchors, canonical archive admission and pruning.
No historical lesson, temporal generalization or production readiness claim is
derived from this prototype. Existing audit verifier, fixture generator and
diagnostic publisher are reused as read-only/test infrastructure, with their
scope unchanged. No legacy authority path is admitted.
