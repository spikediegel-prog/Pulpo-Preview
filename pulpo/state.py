"""Canonical kernel state backends.

The state backend persists replay guards, one-use permits, directives, and the
audit chain for the existing governance kernel. It is storage for that kernel,
not another router, policy engine, or evidence ledger.
"""

from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from hashlib import sha256
import hmac
import json
from os import PathLike
from pathlib import Path
import sqlite3
from threading import RLock
from typing import Any, Callable, Iterator, Protocol

from .audit_parallel import audit_row_has_valid_types
from .database_activity import ObservedConnection


# Reuse the unchanged encoder configuration; per-call state stays in encode().
_CANONICAL_ENCODER = json.JSONEncoder(sort_keys=True, separators=(",", ":"))

# Shared definitions bind publication and subsequent startup validation to the
# same protections. Names alone do not establish what a stored trigger does.
_AUDIT_HEAD_TRIGGERS = {
    "audit_head_check_insert": """
        CREATE TRIGGER audit_head_check_insert BEFORE INSERT ON audit BEGIN
            SELECT CASE WHEN
                (SELECT COUNT(*) FROM audit_head) != 1 OR
                NOT EXISTS (SELECT 1 FROM audit_head WHERE id = 1
                    AND sequence = COALESCE((SELECT sequence FROM audit ORDER BY sequence DESC LIMIT 1), 0)
                    AND hash = COALESCE((SELECT hash FROM audit ORDER BY sequence DESC LIMIT 1),
                        '0000000000000000000000000000000000000000000000000000000000000000')
                    AND hash = NEW.previous_hash)
                THEN RAISE(ABORT, 'audit head missing or mismatched') END;
        END
    """,
    "audit_head_advance": """
        CREATE TRIGGER audit_head_advance AFTER INSERT ON audit BEGIN
            UPDATE audit_head SET sequence = NEW.sequence, hash = NEW.hash WHERE id = 1;
        END
    """,
}


def _normalized_trigger_sql(sql: str) -> str:
    return " ".join(sql.split()).rstrip(";").casefold()


def _canonical(value: Any) -> bytes:
    return _CANONICAL_ENCODER.encode(value).encode()


class AuditSigningKey(Protocol):
    """The signer/verifier seam for audit records.

    A state backend holds one of these: it signs each appended
    record's hash and verifies every signature on the chain at boot.
    ``AuditSigner`` (HMAC) is the original implementation;
    ``Ed25519AuditSigner`` adds the asymmetric era, and
    ``CompositeAuditSigner`` verifies across eras during a
    transition. Verification is the security-critical half: a
    missing, malformed, or wrong-era signature must never verify.
    """

    algorithm: str

    def sign(self, record_hash: str) -> str: ...

    def verify(self, record_hash: str, signature: Any) -> bool: ...


#: Audit signature algorithms, ordered oldest era first. The order is
#: the era order: once a chain carries a signature from a later era,
#: a signature from an earlier era is a downgrade and is refused at
#: verification (see GovernanceKernel.verify_audit_report).
AUDIT_SIGNATURE_ALGORITHMS = ("hmac-sha256", "ed25519")

_ED25519_SIGNATURE_PREFIX = "ed25519:"


def audit_signature_algorithm(signature: Any) -> str | None:
    """Classify a stored audit signature value by era.

    HMAC-era signatures are the bare 64-character lowercase hex of the
    original record shape — byte-identical to every signature written
    before the Ed25519 era existed, so existing chains classify
    without any record being rewritten. Ed25519-era signatures carry
    the explicit ``ed25519:`` tag over the 128-character hex of the
    64-byte signature. Anything else — including a bare tag with no
    well-formed signature behind it — is malformed and classifies as
    None: it verifies under no era.
    """

    if not isinstance(signature, str) or not signature:
        return None
    if signature.startswith(_ED25519_SIGNATURE_PREFIX):
        encoded = signature[len(_ED25519_SIGNATURE_PREFIX):]
        if len(encoded) == 128 and all(
            character in "0123456789abcdef" for character in encoded
        ):
            return "ed25519"
        return None
    if len(signature) == 64 and all(
        character in "0123456789abcdef" for character in signature
    ):
        return "hmac-sha256"
    return None


class AuditSigner:
    """HMAC-SHA256 signer/verifier for audit records (Phase 2, Item 1).

    One signer per deployment, keyed by a dedicated ``audit-secret``
    that is deliberately NOT the kernel secret: a single theft must not
    yield both permit minting and undetectable history forgery. The
    signature covers the record's own ``hash`` and is stored as a
    sibling field, excluded from the hashed body — the exact pattern
    ``AuditAnchor`` uses (``signing_payload()`` excludes ``signature``).
    The field is algorithm-agile: the Ed25519 signer below succeeds
    this class behind the same record shape without changing the
    chain math. Verification is constant-time; a missing, non-string,
    malformed, or wrong-era signature never verifies.
    """

    algorithm = "hmac-sha256"

    def __init__(self, secret: bytes) -> None:
        if not secret:
            raise ValueError("audit secret must be non-empty")
        self._secret = secret

    def sign(self, record_hash: str) -> str:
        if not isinstance(record_hash, str):
            raise TypeError("record hash must be a string")
        return hmac.new(self._secret, record_hash.encode("utf-8"), sha256).hexdigest()

    def verify(self, record_hash: str, signature: Any) -> bool:
        if audit_signature_algorithm(signature) != "hmac-sha256":
            # A tagged Ed25519-era value, or anything malformed, is
            # not an HMAC signature and never verifies as one.
            return False
        try:
            expected = self.sign(record_hash)
        except (AttributeError, TypeError, ValueError):
            return False
        return hmac.compare_digest(expected, signature)


def _ed25519_private_key_class() -> Any:
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    except ImportError as exc:
        raise RuntimeError(
            "Ed25519 audit signing requires the pulpo[authority] extra"
        ) from exc
    return Ed25519PrivateKey


def _ed25519_public_key_class() -> Any:
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError as exc:
        raise RuntimeError(
            "Ed25519 audit verification requires the pulpo[authority] extra"
        ) from exc
    return Ed25519PublicKey


class Ed25519AuditVerifier:
    """Verification-only audit signer pinned to one Ed25519 public key.

    This is the publishable half of the Ed25519 era: anyone holding
    the public key — exported as a standalone artifact (see
    ``Ed25519AuditSigner.public_artifact``) — can verify an
    Ed25519-era chain without holding any deployment secret, the
    property the symmetric HMAC era cannot offer. It holds no private
    material and cannot sign.
    """

    algorithm = "ed25519"

    def __init__(self, public_key: bytes) -> None:
        if len(public_key) != 32:
            raise ValueError("Ed25519 public_key must be exactly 32 bytes")
        self._public_key_bytes = bytes(public_key)
        self._public_key = _ed25519_public_key_class().from_public_bytes(
            self._public_key_bytes
        )
        self.key_fingerprint = sha256(self._public_key_bytes).hexdigest()

    @classmethod
    def from_public_key_hex(cls, text: str) -> "Ed25519AuditVerifier":
        if not isinstance(text, str):
            raise TypeError("public key hex must be a string")
        try:
            public_key = bytes.fromhex(text.strip())
        except ValueError as exc:
            raise ValueError("public key hex is malformed") from exc
        return cls(public_key)

    @classmethod
    def from_artifact(cls, artifact: dict[str, Any]) -> "Ed25519AuditVerifier":
        """Build a verifier from a published verification-key artifact.

        The artifact's fingerprint is checked against the key it
        carries: a substituted key under a copied fingerprint (or the
        reverse) is refused here, before any chain is trusted to it.
        """

        if not isinstance(artifact, dict):
            raise TypeError("verification-key artifact must be a mapping")
        if artifact.get("algorithm") != "ed25519":
            raise ValueError("verification-key artifact is not an Ed25519 key")
        verifier = cls.from_public_key_hex(artifact.get("public_key"))
        fingerprint = artifact.get("key_fingerprint")
        if fingerprint is not None and fingerprint != verifier.key_fingerprint:
            raise ValueError(
                "verification-key artifact fingerprint does not match its key"
            )
        return verifier

    def public_key_bytes(self) -> bytes:
        return self._public_key_bytes

    def public_key_hex(self) -> str:
        return self._public_key_bytes.hex()

    def sign(self, record_hash: str) -> str:
        raise RuntimeError("an Ed25519 audit verifier holds no signing key")

    def verify(self, record_hash: str, signature: Any) -> bool:
        if audit_signature_algorithm(signature) != "ed25519":
            # A bare HMAC-era value, or anything malformed, is not an
            # Ed25519 signature and never verifies as one.
            return False
        encoded = signature[len(_ED25519_SIGNATURE_PREFIX):]
        if len(encoded) != 128 or any(
            character not in "0123456789abcdef" for character in encoded
        ):
            return False
        if not isinstance(record_hash, str):
            return False
        try:
            from cryptography.exceptions import InvalidSignature

            self._public_key.verify(
                bytes.fromhex(encoded), record_hash.encode("utf-8")
            )
        except (InvalidSignature, ValueError):
            return False
        return True


class Ed25519AuditSigner:
    """Ed25519 signer/verifier for audit records.

    The asymmetric successor to ``AuditSigner``: the signature still
    covers the record's ``hash`` and is stored as the same sibling
    field, but the stored value is tagged (``ed25519:<hex>``) so a
    chain can carry both eras and verification can dispatch per
    record. The private key is a 32-byte seed held as a custody file
    (hex text in an owner-only file beside the state it attests —
    the ``audit-secret`` pattern, with asymmetric custody: the file
    is the deployment's signing key and must never be published);
    the public key is exportable as a standalone artifact for
    publication, so third parties verify with
    ``Ed25519AuditVerifier`` and no secret at all.
    """

    algorithm = "ed25519"

    def __init__(self, private_key: bytes) -> None:
        if len(private_key) != 32:
            raise ValueError("Ed25519 private_key must be exactly 32 bytes")
        self._private_key = _ed25519_private_key_class().from_private_bytes(
            bytes(private_key)
        )
        self._verifier = Ed25519AuditVerifier(self.public_key_bytes())

    @classmethod
    def generate(cls) -> "Ed25519AuditSigner":
        private_key = _ed25519_private_key_class().generate()
        from cryptography.hazmat.primitives import serialization

        seed = private_key.private_bytes(
            serialization.Encoding.Raw,
            serialization.PrivateFormat.Raw,
            serialization.NoEncryption(),
        )
        return cls(seed)

    @classmethod
    def from_custody_file(cls, path: str | PathLike[str]) -> "Ed25519AuditSigner":
        """Load the signing key from its custody file.

        The file holds the 32-byte seed as hex text (the deployment
        secret-file shape). Loading never creates or repairs the
        file: provisioning is an explicit operator act
        (``save_custody_file``), mirroring the load-only half of the
        ops secret custody split.
        """

        with open(path, "rb") as handle:
            raw = handle.read()
        try:
            seed = bytes.fromhex(raw.decode("utf-8").strip())
        except (UnicodeDecodeError, ValueError):
            seed = raw.strip()
        if len(seed) != 32:
            raise ValueError("Ed25519 audit custody file is malformed")
        return cls(seed)

    def save_custody_file(self, path: str | PathLike[str]) -> None:
        """Write the signing key to a new owner-only custody file.

        Refuses to overwrite: a collision means a key already lives
        there, and silently replacing a deployment's audit signing
        key would orphan every chain it signed. The caller owns the
        path; rotation is generate-new + re-provision, never an
        in-place rewrite.
        """

        import os
        import stat as _stat

        seed = self._seed_bytes()
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.fchmod(fd, _stat.S_IRUSR | _stat.S_IWUSR)
            view = memoryview((seed.hex() + "\n").encode("utf-8"))
            while view:
                view = view[os.write(fd, view):]
            os.fsync(fd)
        finally:
            os.close(fd)

    def _seed_bytes(self) -> bytes:
        from cryptography.hazmat.primitives import serialization

        return self._private_key.private_bytes(
            serialization.Encoding.Raw,
            serialization.PrivateFormat.Raw,
            serialization.NoEncryption(),
        )

    def public_key_bytes(self) -> bytes:
        from cryptography.hazmat.primitives import serialization

        return self._private_key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )

    def public_key_hex(self) -> str:
        return self._verifier.public_key_hex()

    @property
    def key_fingerprint(self) -> str:
        return self._verifier.key_fingerprint

    def public_artifact(self) -> dict[str, Any]:
        """The publishable verification-key artifact for this signer.

        Carries everything a third party needs to verify an
        Ed25519-era chain and nothing that can sign: the algorithm,
        the public key, and its fingerprint. Suitable for publication
        at a well-known evidence URL.
        """

        return {
            "schema": "pulpo.audit-verification-key.v1",
            "algorithm": "ed25519",
            "public_key": self.public_key_hex(),
            "key_fingerprint": self.key_fingerprint,
        }

    def verifier(self) -> Ed25519AuditVerifier:
        """The verification-only half of this signer."""

        return self._verifier

    def sign(self, record_hash: str) -> str:
        if not isinstance(record_hash, str):
            raise TypeError("record hash must be a string")
        signature = self._private_key.sign(record_hash.encode("utf-8"))
        return _ED25519_SIGNATURE_PREFIX + signature.hex()

    def verify(self, record_hash: str, signature: Any) -> bool:
        return self._verifier.verify(record_hash, signature)


class CompositeAuditSigner:
    """Dual-era audit signer: signs in the current era, verifies all.

    The transition handle. ``signer`` (when given) signs every new
    record — during an HMAC → Ed25519 transition it is the Ed25519
    signer; with no signer the composite is verification-only.
    ``verifiers`` carries one verifier per era the chain may contain
    (the signer's own era is included automatically). Verification
    dispatches on the record's own signature form, so a mixed chain
    verifies end to end, while a record signed in an era the
    deployment never configured verification for is refused — there
    is nothing it could be verified against. Era monotonicity (no
    downgrade after a transition) is enforced by the kernel's
    verification pass, which classifies each signature with
    ``audit_signature_algorithm``.
    """

    def __init__(
        self,
        signer: AuditSigningKey | None = None,
        verifiers: Any = (),
    ) -> None:
        self._signer = signer
        by_algorithm: dict[str, AuditSigningKey] = {}
        for verifier in verifiers:
            by_algorithm[verifier.algorithm] = verifier
        if signer is not None:
            by_algorithm.setdefault(signer.algorithm, signer)
        self._verifiers = by_algorithm
        self.algorithm = signer.algorithm if signer is not None else "dual-era"

    def sign(self, record_hash: str) -> str:
        if self._signer is None:
            raise RuntimeError("this composite audit signer is verification-only")
        return self._signer.sign(record_hash)

    def verify(self, record_hash: str, signature: Any) -> bool:
        algorithm = audit_signature_algorithm(signature)
        if algorithm is None:
            return False
        verifier = self._verifiers.get(algorithm)
        if verifier is None:
            return False
        return verifier.verify(record_hash, signature)


def _audit_record(previous_hash: str, event: str, payload: dict[str, Any], timestamp_ns: int, signer: AuditSigningKey | None = None) -> dict[str, Any]:
    body = {"event": event, "payload": payload, "previous_hash": previous_hash, "timestamp_ns": timestamp_ns}
    record = {**body, "hash": sha256(_canonical(body)).hexdigest()}
    if signer is not None:
        # The signature is computed over the record hash and stored as a
        # sibling field: it is NOT part of the hashed body, so the
        # unkeyed chain math is unchanged and old verifiers recomputing
        # the body still agree on the hash. Verification of the
        # signature is the kernel's job (verify_audit), not this
        # constructor's.
        record["signature"] = signer.sign(record["hash"])
    return record


@dataclass(frozen=True)
class ApprovalUse:
    approval_id: str
    nonce: str
    audit_payload: dict[str, Any]
    ceremony_evidence_id: str | None = None


@dataclass(frozen=True)
class DirectivePermitBinding:
    directive_id: str
    version: int
    directive_hash: str
    issued_at_ns: int
    expires_at_ns: int
    parent_directive_hash: str | None = None

    def audit_payload(self) -> dict[str, Any]:
        payload = {
            "directive_id": self.directive_id,
            "directive_version": self.version,
            "directive_hash": self.directive_hash,
            "directive_issued_at_ns": self.issued_at_ns,
            "directive_expires_at_ns": self.expires_at_ns,
        }
        if self.parent_directive_hash is not None:
            payload["parent_directive_hash"] = self.parent_directive_hash
        return payload


class KernelState(Protocol):
    @property
    def audit(self) -> list[dict[str, Any]]: ...
    def approval_replay_reason(self, approval_id: str, nonce: str) -> str | None: ...
    def ceremony_replay_reason(self, evidence_id: str) -> str | None: ...
    def issue_permit(self, permit: str, intent_hash: str, decision_reason: str, timestamp_ns: int, approval: ApprovalUse | None = None, *, policy_hash: str | None = None, issuer_hash: str | None = None, expires_at_ns: int | None = None, clock: Callable[[], int] | None = None) -> str | None: ...
    def bind_permit_to_directive(self, permit: str, intent_hash: str, binding: DirectivePermitBinding, timestamp_ns: int) -> None: ...
    def consume_permit(self, permit: str, intent_hash: str, timestamp_ns: int, *, policy_hash: str | None = None, issuer_hash: str | None = None, clock: Callable[[], int] | None = None) -> bool: ...
    def revalidate_consumed_permit(self, permit: str, intent_hash: str, timestamp_ns: int, *, policy_hash: str | None = None, issuer_hash: str | None = None) -> str: ...
    def directive_hash_status(self, directive_hash: str) -> str: ...
    def append(self, event: str, payload: dict[str, Any], timestamp_ns: int) -> None: ...
    def append_unique(self, event: str, identity_field: str, identity_value: Any, payload: dict[str, Any], timestamp_ns: int) -> dict[str, Any] | None: ...


class InMemoryKernelState:
    def __init__(self, audit_signer: AuditSigningKey | None = None, legacy_audit_records: int = 0) -> None:
        # Audit signing (Phase 2, Item 1): when a signer is supplied,
        # every appended record carries an HMAC over its hash. When no
        # signer is supplied the backend stays in legacy mode — records
        # are unsigned and a later kernel configured with a signer
        # refuses the chain rather than silently trusting it.
        # ``legacy_audit_records`` is the count of unsigned records at
        # the head of the chain the backend inherits (for example from
        # a pre-signing snapshot): verification skips them instead of
        # treating the whole chain as unsigned. It is 0 for a fresh
        # backend.
        self.audit_signer = audit_signer
        self.legacy_audit_records = legacy_audit_records
        self._issued: dict[str, str] = {}
        self._spent: set[str] = set()
        self._permit_context: dict[str, tuple[str | None, int, int | None, str | None]] = {}
        self._approval_ids: set[str] = set()
        self._approval_nonces: set[str] = set()
        self._directives: dict[tuple[str, int], tuple[str, bool]] = {}
        self._permit_directives: dict[str, DirectivePermitBinding] = {}
        self._audit: list[dict[str, Any]] = []
        self._audit_lock = RLock()

    def _require_audit_signing_available(self) -> None:
        # Finding 7 (Codex P1 on PR #420): every mutating transition
        # below appends its signed audit record AFTER recording its
        # mutations, so a signer that cannot sign — a verification-only
        # CompositeAuditSigner raises on every sign() — failed the
        # transition with the mutations already landed: canonical state
        # changed with no signed evidence, irreversibly for a spent
        # permit. Signing availability is a property of the signer's
        # configuration, not of the record (every signer behind the
        # AuditSigningKey seam either signs any record hash or none),
        # so each transition probes the signer BEFORE its first
        # mutation, inside the same locked sequence: a signer that
        # cannot sign refuses the transition here, against an unchanged
        # state, and a signer that passes the probe signs the
        # transition's appends. The probe signature is discarded; it
        # is recorded nowhere.
        if self.audit_signer is not None:
            self.audit_signer.sign("0" * 64)

    @property
    def audit(self) -> list[dict[str, Any]]:
        return self._audit

    def approval_replay_reason(self, approval_id: str, nonce: str) -> str | None:
        with self._audit_lock:
            if approval_id in self._approval_ids: return "approval_id_replayed"
            if nonce in self._approval_nonces: return "approval_nonce_replayed"
            return None

    def ceremony_replay_reason(self, evidence_id: str) -> str | None:
        with self._audit_lock:
            for record in self._audit:
                if record.get("event") != "approval_verified":
                    continue
                payload = record.get("payload")
                if not isinstance(payload, dict):
                    raise ValueError("approval audit payload invalid")
                if payload.get("ceremony_evidence_id") == evidence_id:
                    return "ceremony_evidence_replayed"
            return None

    def issue_permit(self, permit: str, intent_hash: str, decision_reason: str, timestamp_ns: int, approval: ApprovalUse | None = None, *, policy_hash: str | None = None, issuer_hash: str | None = None, expires_at_ns: int | None = None, clock: Callable[[], int] | None = None) -> str | None:
        with self._audit_lock:
            previous_ns = timestamp_ns
            timestamp_ns = _sample_post_lock_timestamp(timestamp_ns, clock)
            if clock is not None and type(expires_at_ns) is int and type(previous_ns) is int:
                # Preserve the permit lifetime the kernel computed, anchored at
                # the post-lock sample instead of the pre-lock one. A None
                # expiry ("no expiry") is preserved unchanged.
                expires_at_ns = timestamp_ns + (expires_at_ns - previous_ns)
            if approval is not None:
                replay = self.approval_replay_reason(approval.approval_id, approval.nonce)
                if replay: return replay
                self._require_audit_signing_available()
                if approval.ceremony_evidence_id is not None:
                    replay = self.ceremony_replay_reason(approval.ceremony_evidence_id)
                    if replay: return replay
                self._approval_ids.add(approval.approval_id); self._approval_nonces.add(approval.nonce)
                self.append("approval_verified", approval.audit_payload, timestamp_ns)
            self._require_audit_signing_available()
            self._issued[permit] = intent_hash
            self._permit_context[permit] = (policy_hash, timestamp_ns, expires_at_ns, issuer_hash)
            self.append("decision", {"outcome": "allow", "reason": decision_reason, "intent_hash": intent_hash, "policy_hash": policy_hash, "issuer_hash": issuer_hash, "issued_at_ns": timestamp_ns, "expires_at_ns": expires_at_ns}, timestamp_ns)
            return None

    def bind_permit_to_directive(self, permit: str, intent_hash: str, binding: DirectivePermitBinding, timestamp_ns: int) -> None:
        with self._audit_lock:
            if self._issued.get(permit) != intent_hash or permit in self._spent: raise ValueError("permit unavailable for directive binding")
            context = self._permit_context.get(permit)
            if context is not None and (timestamp_ns < context[1] or (context[2] is not None and timestamp_ns >= context[2]) or (context[0] is not None and context[2] is None)):
                raise ValueError("permit unavailable for directive binding")
            if permit in self._permit_directives: raise ValueError("permit directive binding is immutable")
            if self.directive_status(binding.directive_id, binding.version, binding.directive_hash) != "active": raise ValueError("directive is not active for permit binding")
            if binding.parent_directive_hash is not None and self.directive_hash_status(binding.parent_directive_hash) != "active": raise ValueError("parent directive is not active for permit binding")
            self._require_audit_signing_available()
            self._permit_directives[permit] = binding
            self.append("permit_bound_to_directive", {"intent_hash": intent_hash, **binding.audit_payload()}, timestamp_ns)

    def consume_permit(self, permit: str, intent_hash: str, timestamp_ns: int, *, policy_hash: str | None = None, issuer_hash: str | None = None, clock: Callable[[], int] | None = None) -> bool:
        with self._audit_lock:
            timestamp_ns = _sample_post_lock_timestamp(timestamp_ns, clock)
            valid = self._issued.get(permit) == intent_hash and permit not in self._spent
            context = self._permit_context.get(permit)
            if policy_hash is not None:
                valid = valid and context is not None and context[0] == policy_hash and context[3] == issuer_hash and type(context[2]) is int
            if context is not None:
                valid = valid and type(timestamp_ns) is int and timestamp_ns >= context[1]
                valid = valid and (context[2] is None or timestamp_ns < context[2])
            binding = self._permit_directives.get(permit)
            payload: dict[str, Any] = {"intent_hash": intent_hash}
            if binding is not None:
                status = self.directive_status(binding.directive_id, binding.version, binding.directive_hash)
                if status == "active" and binding.parent_directive_hash is not None:
                    status = self.directive_hash_status(binding.parent_directive_hash)
                if status == "active" and not (binding.issued_at_ns <= timestamp_ns < binding.expires_at_ns): status = "directive_inactive"
                valid = valid and status == "active"
                payload.update(binding.audit_payload()); payload["directive_status"] = status
            # Finding 7: signing availability is established before
            # the first mutation on either path below — the spend on
            # the valid path, the rejection record on the invalid one.
            # The spend stays on its own one-line form: the race test
            # in test_governance_security_regressions anchors its
            # trace on that line's text.
            self._require_audit_signing_available()
            if valid: self._spent.add(permit)
            self.append("permit_consumed" if valid else "permit_rejected", payload, timestamp_ns)
            return valid

    def revalidate_consumed_permit(self, permit: str, intent_hash: str, timestamp_ns: int, *, policy_hash: str | None = None, issuer_hash: str | None = None) -> str:
        # Read-only re-check of the exact state consume_permit validated, under
        # the same lock, for the window between consumption and execution. It
        # appends nothing: callers record the refusal or unknown outcome.
        # A NULL expires_at_ns means no expiry (load-bearing fork semantics);
        # this re-check must not re-impose a stricter expiry invariant.
        with self._audit_lock:
            if permit not in self._issued:
                return "permit_not_found"
            if self._issued.get(permit) != intent_hash:
                return "permit_intent_mismatch"
            if permit not in self._spent:
                return "permit_not_consumed"
            context = self._permit_context.get(permit)
            if policy_hash is not None:
                if context is None or context[0] != policy_hash:
                    return "permit_policy_mismatch"
                if context[3] != issuer_hash:
                    return "permit_issuer_mismatch"
            if context is not None:
                if type(timestamp_ns) is not int or timestamp_ns < context[1]:
                    return "permit_not_yet_valid"
                if context[2] is not None and timestamp_ns >= context[2]:
                    return "permit_expired"
            binding = self._permit_directives.get(permit)
            if binding is not None:
                status = self.directive_status(binding.directive_id, binding.version, binding.directive_hash)
                if status == "active" and binding.parent_directive_hash is not None:
                    status = self.directive_hash_status(binding.parent_directive_hash)
                if status == "active" and not (binding.issued_at_ns <= timestamp_ns < binding.expires_at_ns):
                    status = "directive_inactive"
                if status != "active":
                    return status
            return "valid"

    def activate_directive(self, directive, authority_evidence: dict[str, object], timestamp_ns: int) -> None:
        with self._audit_lock:
            key = (directive.directive_id, directive.version)
            if key in self._directives: raise ValueError("directive version is immutable")
            parent_hash = getattr(directive, "parent_directive_hash", None)
            if parent_hash is not None and self.directive_hash_status(parent_hash) != "active":
                raise ValueError("parent directive is not active for activation")
            self._require_audit_signing_available()
            self._directives[key] = (directive.directive_hash, False)
            self.append("directive_activated", {"directive_id": directive.directive_id, "version": directive.version, "directive_hash": directive.directive_hash, "authority_evidence": authority_evidence}, timestamp_ns)

    def revoke_directive(self, directive_id: str, version: int, authority_evidence: dict[str, object], timestamp_ns: int) -> None:
        with self._audit_lock:
            key = (directive_id, version)
            if key not in self._directives: raise ValueError("directive version not found")
            self._require_audit_signing_available()
            digest, _ = self._directives[key]; self._directives[key] = (digest, True)
            self.append("directive_revoked", {"directive_id": directive_id, "version": version, "directive_hash": digest, "authority_evidence": authority_evidence}, timestamp_ns)

    def directive_status(self, directive_id: str, version: int, directive_hash: str) -> str:
        with self._audit_lock:
            value = self._directives.get((directive_id, version))
            if value is None: return "directive_not_authorized"
            digest, revoked = value
            if digest != directive_hash: return "directive_version_mismatch"
            return "directive_revoked" if revoked else "active"

    def directive_hash_status(self, directive_hash: str) -> str:
        with self._audit_lock:
            for digest, revoked in self._directives.values():
                if digest == directive_hash:
                    return "directive_parent_revoked" if revoked else "active"
            return "directive_parent_not_authorized"

    def append(self, event: str, payload: dict[str, Any], timestamp_ns: int) -> None:
        with self._audit_lock:
            previous = self._audit[-1]["hash"] if self._audit else "0" * 64
            record = _audit_record(previous, event, payload, timestamp_ns, signer=self.audit_signer)
            self._audit.append(record)

    def append_unique(
        self,
        event: str,
        identity_field: str,
        identity_value: Any,
        payload: dict[str, Any],
        timestamp_ns: int,
    ) -> dict[str, Any] | None:
        if not event or not identity_field or payload.get(identity_field) != identity_value:
            raise ValueError("unique audit identity invalid")
        with self._audit_lock:
            matches = [
                record["payload"]
                for record in self._audit
                if record.get("event") == event
                and isinstance(record.get("payload"), dict)
                and record["payload"].get(identity_field) == identity_value
            ]
            if len(matches) > 1:
                raise ValueError("unique audit identity ambiguous")
            if matches:
                return matches[0]
            previous = self._audit[-1]["hash"] if self._audit else "0" * 64
            record = _audit_record(previous, event, payload, timestamp_ns, signer=self.audit_signer)
            self._audit.append(record)
            return None


class StateRecoveryError(ValueError):
    """Recovery cannot establish equality with the independently trusted state."""


class StateClockError(ValueError):
    """A post-lock clock sample failed, or the clock regressed between the
    pre-lock sample and the post-lock sample.

    Fail-closed: the write is refused rather than stamping canonical evidence
    with an untrusted time. For SQLite the enclosing transaction rolls back,
    so a refused consume leaves the permit unspent.
    """


def _sample_post_lock_timestamp(timestamp_ns: int, clock: Callable[[], int] | None) -> int:
    """Re-sample the clock after the lock; fall back to the caller's timestamp.

    Call only after BEGIN IMMEDIATE (SQLite) or after acquiring _audit_lock
    (in-memory), so the returned timestamp cannot predate the lock. This is
    the custody pattern (``_custody_now`` in custody.py) ported to the kernel
    paths: expiry/validity checks inside the transaction then run on a
    post-lock timestamp instead of the kernel's pre-lock sample.

    The regression check compares the post-lock sample against the same
    clock's pre-lock sample, not against the audit tip. Custody can compare
    against its head time because one custody store has one clock and the head
    time was written by that same clock. Kernel state has no clock of its own:
    its audit tip conflates timestamps from every kernel sharing the state
    (each with its own injected clock) and from direct state callers, and
    legacy adoption deliberately preserves non-monotonic histories (see
    test_audit_integrity_migration's seed: 100, 10, 10, -1). A tip comparison
    would reject legitimate skewed-clock writes -- e.g. two kernels sharing
    state with clocks 1 ns apart (test_governance_security_regressions).
    Adjacent samples from one clock are the faithful analogue, and the
    strongest per-clock check available without new state: a regression
    between the two samples means the clock went backwards across exactly
    the lock boundary the TOCTOU fix closes. With no clock supplied the
    caller owns the timestamp and no regression check applies; the
    permit-window checks still bound it.
    """
    if clock is None:
        return timestamp_ns
    try:
        fresh = clock()
    except Exception as exc:
        raise StateClockError("state_clock_unavailable") from exc
    if type(fresh) is not int or fresh <= 0:
        raise StateClockError("state_clock_invalid")
    if type(timestamp_ns) is int and fresh < timestamp_ns:
        raise StateClockError("state_clock_rollback")
    return fresh


_RECOVERY_PREFIX = "pulpo.sqlite.recovery.v1:"
_RECOVERY_TABLES = frozenset({"permits", "approvals", "directives", "permit_directives",
                              "audit", "audit_head", "audit_integrity_schema"})


def _validate_recovery_checkpoint(value: str) -> None:
    if (type(value) is not str or not value.startswith(_RECOVERY_PREFIX)
            or len(value) != len(_RECOVERY_PREFIX) + 64
            or any(char not in "0123456789abcdef" for char in value[len(_RECOVERY_PREFIX):])):
        raise StateRecoveryError("a valid independently trusted recovery checkpoint is required")


def _recovery_checkpoint(connection: sqlite3.Connection) -> str:
    """Fingerprint canonical data in the caller's single SQLite transaction.

    A digest is a comparison value, not evidence of freshness or an approval.
    The disposable audit-verification cache is deliberately excluded. Unexpected
    tables/views are refused rather than silently leaving state outside the pin.
    """
    objects = connection.execute(
        "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name"
    ).fetchall()
    tables = {name for kind, name, _, _ in objects if kind == "table" and not name.startswith("sqlite_")}
    if (tables - {"audit_verification_checkpoint"} != _RECOVERY_TABLES
            or any(kind == "view" or (sql and "CREATE VIRTUAL TABLE" in sql.upper())
                   for kind, _, _, sql in objects)):
        raise StateRecoveryError("unsupported or incomplete recovery schema")
    digest = sha256(_RECOVERY_PREFIX.encode())
    def add(value):
        encoded = _canonical(value)
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    add([obj for obj in objects if not (obj[0] == "table" and obj[1] == "audit_verification_checkpoint")
         and not obj[1].startswith("sqlite_")])
    for table in sorted(_RECOVERY_TABLES):
        add(table)
        # Identifiers come only from the fixed canonical table allowlist.
        rows = connection.execute('SELECT * FROM "' + table + '"').fetchall()
        for encoded in sorted(_canonical(row) for row in rows):
            digest.update(len(encoded).to_bytes(8, "big"))
            digest.update(encoded)
    return _RECOVERY_PREFIX + digest.hexdigest()


class SQLiteKernelState:
    def __init__(self, path: str | PathLike[str], *, audit_signer: AuditSigningKey | None = None,
                 legacy_audit_records: int = 0, migrate_schema: bool = True,
                 index_audit_events: bool = False,
                 expected_recovery_checkpoint: str | None = None) -> None:
        if expected_recovery_checkpoint is not None:
            _validate_recovery_checkpoint(expected_recovery_checkpoint)
            # Recovery must never turn a missing snapshot into a new empty state.
            path = Path(path).absolute().as_uri() + "?mode=rw"
        elif not migrate_schema:
            # A read-only open cannot create or migrate a state file: a
            # missing path fails here instead of materializing an empty
            # database, and an unmigrated schema is reported rather than
            # rewritten. ``as_uri()`` already percent-encodes the path.
            path = Path(path).absolute().as_uri() + "?mode=ro"
        # Audit signing (Phase 2, Item 1): see InMemoryKernelState for
        # the semantics. ``_audit_has_signature`` records whether the
        # audit table carries the signature column after migration;
        # it is set by _initialize_transaction before any read or
        # append can observe the state.
        self.audit_signer = audit_signer
        self.legacy_audit_records = legacy_audit_records
        self._migrate_schema = migrate_schema
        self._read_only = expected_recovery_checkpoint is None and not migrate_schema
        self._audit_has_signature = False
        self._connection = sqlite3.connect(path, factory=ObservedConnection,
                                           uri=expected_recovery_checkpoint is not None or not migrate_schema)
        self._closed = False
        try:
            self._initialize(index_audit_events=index_audit_events,
                             expected_recovery_checkpoint=expected_recovery_checkpoint,
                             migrate_schema=migrate_schema)
        except BaseException:
            self.close()
            raise

    @classmethod
    def recover(cls, path: str | PathLike[str], *, expected_checkpoint: str) -> "SQLiteKernelState":
        """Open restored state only against a separately retained CURRENT pin.

        Keep execution stopped. If the latest trusted pin is unavailable, do not
        derive it from this backup or use ordinary construction as a fallback.
        This does not protect raw file replacement or co-rollback of the pin.
        """
        _validate_recovery_checkpoint(expected_checkpoint)
        return cls(path, expected_recovery_checkpoint=expected_checkpoint)

    def recovery_checkpoint(self) -> str:
        """Capture a read-only comparison pin after canonical audit verification.

        Quiesce all writers and retain the pin independently of backup rollback.
        Every subsequent canonical write invalidates it; freshness is the trusted
        operator's responsibility. No checkpoint store or writer is created.
        """
        if self._connection.in_transaction:
            raise StateRecoveryError("checkpoint capture requires no pending transaction")
        with self._connection:
            self._connection.execute("BEGIN")
            self._checked_audit_rows()
            return _recovery_checkpoint(self._connection)

    def _initialize(self, *, index_audit_events: bool, migrate_schema: bool = True,
                    expected_recovery_checkpoint: str | None = None) -> None:
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA synchronous = FULL")
        # executescript commits an existing transaction before running. Execute
        # each DDL statement under one explicit transaction instead, including
        # validation, legacy ALTERs, head adoption and trigger publication.
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            if expected_recovery_checkpoint is not None:
                actual = _recovery_checkpoint(self._connection)
                if not hmac.compare_digest(actual, expected_recovery_checkpoint):
                    raise StateRecoveryError("restored state does not match the trusted current checkpoint")
            self._initialize_transaction(index_audit_events=index_audit_events, migrate_schema=migrate_schema)

    def _initialize_transaction(self, *, index_audit_events: bool, migrate_schema: bool = True) -> None:
        tables = {row[0] for row in self._connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )}
        upgraded = "audit_integrity_schema" in tables
        if upgraded and "audit_head" not in tables:
            raise ValueError("audit head table missing")
        schema = """
            CREATE TABLE IF NOT EXISTS permits (permit TEXT PRIMARY KEY, intent_hash TEXT NOT NULL, spent INTEGER NOT NULL DEFAULT 0 CHECK (spent IN (0, 1)));
            CREATE TABLE IF NOT EXISTS approvals (approval_id TEXT PRIMARY KEY, nonce TEXT NOT NULL UNIQUE);
            CREATE TABLE IF NOT EXISTS directives (directive_id TEXT NOT NULL, version INTEGER NOT NULL, directive_hash TEXT NOT NULL, revoked INTEGER NOT NULL DEFAULT 0 CHECK (revoked IN (0, 1)), PRIMARY KEY (directive_id, version));
            CREATE TABLE IF NOT EXISTS permit_directives (permit TEXT PRIMARY KEY REFERENCES permits(permit) ON DELETE CASCADE, directive_id TEXT NOT NULL, directive_version INTEGER NOT NULL, directive_hash TEXT NOT NULL, directive_issued_at_ns INTEGER NOT NULL, directive_expires_at_ns INTEGER NOT NULL, parent_directive_hash TEXT);
            CREATE TABLE IF NOT EXISTS audit (sequence INTEGER PRIMARY KEY, event TEXT NOT NULL, payload_json TEXT NOT NULL, previous_hash TEXT NOT NULL, timestamp_ns INTEGER NOT NULL, hash TEXT NOT NULL, signature TEXT);
            CREATE TABLE IF NOT EXISTS audit_verification_checkpoint (id INTEGER PRIMARY KEY CHECK (id = 1), checkpoint_json TEXT NOT NULL);
        """
        if migrate_schema:
            for statement in schema.split(";"):
                if statement.strip():
                    self._connection.execute(statement)
        else:
            required = {"permits", "approvals", "directives", "permit_directives", "audit", "audit_verification_checkpoint"}
            if not required <= tables:
                raise ValueError("state schema requires migration; open with migration enabled")
        # Opt in for event-heavy histories: the index speeds filtered reads but
        # adds maintenance to every durable audit insert. Existing indexes stay.
        if index_audit_events and migrate_schema:
            self._connection.execute("CREATE INDEX IF NOT EXISTS audit_event_sequence ON audit(event, sequence)")
        if migrate_schema:
            permit_columns = {row[1] for row in self._connection.execute("PRAGMA table_info(permits)")}
            for name, kind in (("policy_hash", "TEXT"), ("issued_at_ns", "INTEGER"), ("expires_at_ns", "INTEGER"), ("issuer_hash", "TEXT")):
                if name not in permit_columns:
                    self._connection.execute(f"ALTER TABLE permits ADD COLUMN {name} {kind}")
            columns = {row[1] for row in self._connection.execute("PRAGMA table_info(permit_directives)").fetchall()}
            if "parent_directive_hash" not in columns:
                self._connection.execute("ALTER TABLE permit_directives ADD COLUMN parent_directive_hash TEXT")
        audit_columns = {row[1] for row in self._connection.execute("PRAGMA table_info(audit)")}
        if migrate_schema and "signature" not in audit_columns:
            self._connection.execute("ALTER TABLE audit ADD COLUMN signature TEXT")
            audit_columns.add("signature")
        self._audit_has_signature = "signature" in audit_columns
        if upgraded:
            versions = self._connection.execute("SELECT * FROM audit_integrity_schema").fetchall()
            if (versions != [(1, 1)]
                    or any(type(value) is not int for row in versions for value in row)):
                raise ValueError("audit head schema invalid")
            self._assert_audit_head()
            triggers = dict(self._connection.execute(
                "SELECT name, sql FROM sqlite_master WHERE type = 'trigger' AND tbl_name = 'audit'"
            ))
            for name, expected in _AUDIT_HEAD_TRIGGERS.items():
                actual = triggers.get(name)
                if not isinstance(actual, str) or _normalized_trigger_sql(actual) != _normalized_trigger_sql(expected):
                    raise ValueError("audit head trigger missing or substituted")
            return

        # Legacy adoption cannot establish whether history was lost before this
        # upgrade. Validate every existing record before trusting its current tip.
        previous = "0" * 64
        for event, encoded, link, timestamp, digest in self._connection.execute(
            "SELECT event, payload_json, previous_hash, timestamp_ns, hash FROM audit ORDER BY sequence"
        ):
            try:
                payload = json.loads(encoded)
                valid = (type(event) is str and type(encoded) is str
                         and isinstance(payload, dict) and type(timestamp) is int
                         and type(link) is str and type(digest) is str
                         and link == previous
                         and digest == _audit_record(link, event, payload, timestamp)["hash"])
            except (ValueError, TypeError):
                valid = False
            if not valid:
                raise ValueError("legacy audit chain invalid")
            previous = digest
        if not migrate_schema:
            # The chain above is valid, but adoption writes the head,
            # the integrity schema, and the audit triggers: a read-only
            # open refuses rather than rewriting the schema it was
            # asked only to inspect.
            raise ValueError("state schema requires migration; open with migration enabled")
        self._connection.execute("""
            CREATE TABLE IF NOT EXISTS audit_head (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                sequence INTEGER NOT NULL CHECK (sequence >= 0),
                hash TEXT NOT NULL CHECK (length(hash) = 64)
            )
        """)
        if "audit_head" in tables:
            # A preexisting head is evidence to reconcile, never overwrite it.
            self._assert_audit_head()
        else:
            tip = self._connection.execute(
                "SELECT sequence, hash FROM audit ORDER BY sequence DESC LIMIT 1"
            ).fetchone() or (0, "0" * 64)
            self._connection.execute("INSERT INTO audit_head VALUES (1, ?, ?)", tip)
        self._connection.execute("""
            CREATE TABLE audit_integrity_schema (
                id INTEGER PRIMARY KEY CHECK (id = 1), version INTEGER NOT NULL CHECK (version = 1)
            )
        """)
        self._connection.execute("INSERT INTO audit_integrity_schema VALUES (1, 1)")
        # Both existing canonical append paths (kernel and custody projection)
        # advance this subordinate tip metadata in the audit insert transaction.
        for sql in _AUDIT_HEAD_TRIGGERS.values():
            self._connection.execute(sql)

    def _assert_audit_head(self, rows=None) -> None:
        if rows is None:
            tip = self._connection.execute(
                "SELECT sequence, hash FROM audit ORDER BY sequence DESC LIMIT 1"
            ).fetchone() or (0, "0" * 64)
        else:
            tip = (rows[-1][0], rows[-1][-1]) if rows else (0, "0" * 64)
        heads = self._connection.execute("SELECT id, sequence, hash FROM audit_head").fetchall()
        valid_types = (len(heads) == 1 and type(heads[0][0]) is int
                       and type(heads[0][1]) is int and type(heads[0][2]) is str)
        if not valid_types or heads != [(1, *tip)]:
            raise ValueError("audit head missing or mismatched")

    def _checked_audit_rows(self):
        def read():
            rows = self._connection.execute(
                "SELECT sequence, event, payload_json, previous_hash, timestamp_ns, hash FROM audit ORDER BY sequence"
            ).fetchall()
            self._assert_audit_head(rows)
            self._validate_audit_row_types(rows)
            return rows
        if self._connection.in_transaction:
            return read()
        with self._connection:
            self._connection.execute("BEGIN")
            return read()

    @staticmethod
    def _validate_audit_row_types(rows) -> None:
        for sequence, *body in rows:
            if type(sequence) is not int or not audit_row_has_valid_types(body):
                raise ValueError("audit row types invalid")

    def iter_audit(
        self,
        *,
        event: str | None = None,
        reverse: bool = False,
    ) -> Iterator[dict[str, Any]]:
        """Stream audit records without materializing the whole chain.

        Preview adaptation of upstream #250: Preview's audit table has no
        delta columns (delta-audit projection not adopted), so only the
        canonical columns are selected. The chain is NOT verified here.
        """
        order = "DESC" if reverse else "ASC"
        columns = "event, payload_json, previous_hash, timestamp_ns, hash"
        if self._audit_has_signature:
            columns += ", signature"
        if event is None:
            cursor = self._connection.execute(
                f"SELECT {columns} FROM audit ORDER BY sequence {order}"
            )
        else:
            cursor = self._connection.execute(
                f"SELECT {columns} FROM audit WHERE event = ? ORDER BY sequence {order}",
                (event,),
            )
        for row in cursor:
            record: dict[str, Any] = {"event": row[0], "payload": json.loads(row[1]), "previous_hash": row[2], "timestamp_ns": row[3], "hash": row[4]}
            if self._audit_has_signature and row[5] is not None:
                record["signature"] = row[5]
            yield record

    @property
    def audit(self) -> list[dict[str, Any]]:
        # Validation (head + row types) and the signature read share one
        # transaction, so a concurrent append cannot shift the rows
        # between the two reads.
        if self._connection.in_transaction:
            return self._audit_records_with_signatures()
        with self._connection:
            self._connection.execute("BEGIN")
            return self._audit_records_with_signatures()

    def _audit_records_with_signatures(self) -> list[dict[str, Any]]:
        rows = self._checked_audit_rows()
        records = [{"event": e, "payload": json.loads(p), "previous_hash": ph, "timestamp_ns": ts, "hash": h} for _, e, p, ph, ts, h in rows]
        if self._audit_has_signature:
            signatures = [row[0] for row in self._connection.execute("SELECT signature FROM audit ORDER BY sequence")]
            if len(signatures) != len(records):
                raise ValueError("audit signature read inconsistent")
            for record, signature in zip(records, signatures):
                # The key exists only when a signature exists: an
                # unsigned record carries no "signature" key at all
                # (not None), so the record shape is identical to the
                # pre-signing shape and hash recomputation over the
                # body is unchanged.
                if signature is not None:
                    record["signature"] = signature
        return records

    def audit_verification_rows(self) -> list[tuple[str, str, str, int, str]]:
        """Return raw immutable audit row bodies for optional decode/hash workers."""
        rows = self._checked_audit_rows()
        return [
            (event, payload_json, previous_hash, timestamp_ns, digest)
            for _, event, payload_json, previous_hash, timestamp_ns, digest in rows
        ]

    def verify_audit_bootstrap(self, secret: bytes, full_verify: Callable[[], bool]) -> bool:
        """Use a disposable authenticated cache, never a source of authority.

        Read *all* prefix bytes on every restart. A head-only checkpoint cannot
        detect historical edits. The MAC uses the existing kernel secret with
        a separate domain; neither the secret nor new authority is persisted.
        BEGIN IMMEDIATE keeps validation and cache publication in one snapshot.
        """
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            rows = self._connection.execute(
                "SELECT sequence, event, payload_json, previous_hash, timestamp_ns, hash "
                "FROM audit ORDER BY sequence"
            ).fetchall()
            self._assert_audit_head(rows)
            # Validate even authenticated cached prefixes. Older optional
            # verifiers could publish a cache after coercing malformed values.
            self._validate_audit_row_types(rows)
            # Signatures are verified over the same snapshot as the hash
            # chain, before any cached prefix can short-circuit the boot:
            # a wrong-secret or keyless verifier kernel refuses the
            # signed chain here instead of trusting it.
            if not self._verify_audit_signatures(rows):
                return False
            cached = self._connection.execute(
                "SELECT checkpoint_json FROM audit_verification_checkpoint WHERE id = 1"
            ).fetchone()
            prefix_length = 0
            previous = "0" * 64
            if cached is not None:
                try:
                    checkpoint = json.loads(cached[0])
                    if set(checkpoint) != {"schema", "sequence", "head", "prefix_digest", "mac"}:
                        raise ValueError("checkpoint fields")
                    if checkpoint["schema"] != "pulpo.audit-checkpoint.v1":
                        raise ValueError("checkpoint version")
                    sequence = checkpoint["sequence"]
                    if type(sequence) is not int or sequence < 1:
                        raise ValueError("checkpoint sequence")
                    for field in ("head", "prefix_digest", "mac"):
                        value = checkpoint[field]
                        if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                            raise ValueError("checkpoint digest")
                    body = {k: v for k, v in checkpoint.items() if k != "mac"}
                    expected = hmac.new(secret, b"pulpo.audit-checkpoint.v1\0" + _canonical(body), sha256).hexdigest()
                    if not hmac.compare_digest(checkpoint["mac"], expected):
                        raise ValueError("checkpoint authentication")
                    prefix_length = next(i + 1 for i, row in enumerate(rows) if row[0] == sequence)
                    prefix = rows[:prefix_length]
                    if prefix[-1][-1] != checkpoint["head"] or sha256(_canonical(prefix)).hexdigest() != checkpoint["prefix_digest"]:
                        raise ValueError("checkpoint prefix changed")
                    previous = checkpoint["head"]
                except (ValueError, TypeError, KeyError, StopIteration):
                    prefix_length = 0
                    previous = "0" * 64
            if prefix_length:
                if prefix_length == len(rows):
                    return True
                for _, event, payload_json, link, timestamp, digest in rows[prefix_length:]:
                    if link != previous or not hmac.compare_digest(
                        digest, _audit_record(link, event, json.loads(payload_json), timestamp)["hash"]
                    ):
                        return False
                    previous = digest
            elif not full_verify():
                return False
            if rows and not self._read_only:
                # The cache is disposable: a read-only inspection
                # open verifies without publishing it.
                body = {"schema": "pulpo.audit-checkpoint.v1", "sequence": rows[-1][0],
                        "head": rows[-1][-1], "prefix_digest": sha256(_canonical(rows)).hexdigest()}
                checkpoint = {**body, "mac": hmac.new(
                    secret, b"pulpo.audit-checkpoint.v1\0" + _canonical(body), sha256
                ).hexdigest()}
                self._connection.execute(
                    "INSERT OR REPLACE INTO audit_verification_checkpoint VALUES (1, ?)",
                    (_canonical(checkpoint).decode(),),
                )
            return True

    def _verify_audit_signatures(self, rows) -> bool:
        """Cryptographic signature check for a boot-time chain read.

        Mirrors the kernel report's per-record rules without era
        monotonicity (that is the report's job, applied at kernel
        construction through verify_audit_report): a present
        signature must verify under the configured signer, and a
        missing signature at or after the legacy prefix fails when a
        signer is configured. A signature present with no signer
        configured is refused, not ignored. Runs inside the caller's
        BEGIN IMMEDIATE transaction, over the same snapshot as the
        hash validation.
        """
        if not self._audit_has_signature:
            return True
        signatures = [row[0] for row in self._connection.execute("SELECT signature FROM audit ORDER BY sequence")]
        if len(signatures) != len(rows):
            return False
        signer = self.audit_signer
        for index, (row, signature) in enumerate(zip(rows, signatures)):
            record_hash = row[5]
            if signature is not None:
                if signer is None or not signer.verify(record_hash, signature):
                    return False
            elif signer is not None and index >= self.legacy_audit_records:
                return False
        return True

    def approval_replay_reason(self, approval_id: str, nonce: str) -> str | None: return self._approval_replay_reason(approval_id, nonce)
    def ceremony_replay_reason(self, evidence_id: str) -> str | None:
        rows = self._connection.execute(
            "SELECT payload_json FROM audit WHERE event = 'approval_verified' ORDER BY sequence"
        )
        for (encoded,) in rows:
            payload = json.loads(str(encoded))
            if not isinstance(payload, dict):
                raise ValueError("approval audit payload invalid")
            if payload.get("ceremony_evidence_id") == evidence_id:
                return "ceremony_evidence_replayed"
        return None

    def _approval_replay_reason(self, approval_id: str, nonce: str) -> str | None:
        row = self._connection.execute(
            """
            SELECT CASE
                WHEN EXISTS (SELECT 1 FROM approvals WHERE approval_id = ?) THEN 'approval_id_replayed'
                WHEN EXISTS (SELECT 1 FROM approvals WHERE nonce = ?) THEN 'approval_nonce_replayed'
                ELSE NULL
            END
            """,
            (approval_id, nonce),
        ).fetchone()
        return row[0] if row is not None else None

    def issue_permit(self, permit: str, intent_hash: str, decision_reason: str, timestamp_ns: int, approval: ApprovalUse | None = None, *, policy_hash: str | None = None, issuer_hash: str | None = None, expires_at_ns: int | None = None, clock: Callable[[], int] | None = None) -> str | None:
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            previous_ns = timestamp_ns
            timestamp_ns = _sample_post_lock_timestamp(timestamp_ns, clock)
            if clock is not None and type(expires_at_ns) is int and type(previous_ns) is int:
                # Preserve the permit lifetime the kernel computed, anchored at
                # the post-lock sample instead of the pre-lock one. A None
                # expiry ("no expiry") is preserved unchanged.
                expires_at_ns = timestamp_ns + (expires_at_ns - previous_ns)
            if approval is not None:
                replay = self._approval_replay_reason(approval.approval_id, approval.nonce)
                if replay: return replay
                if approval.ceremony_evidence_id is not None:
                    replay = self.ceremony_replay_reason(approval.ceremony_evidence_id)
                    if replay: return replay
                self._connection.execute("INSERT INTO approvals (approval_id, nonce) VALUES (?, ?)", (approval.approval_id, approval.nonce))
            self._connection.execute("INSERT INTO permits (permit, intent_hash, policy_hash, issued_at_ns, expires_at_ns, issuer_hash) VALUES (?, ?, ?, ?, ?, ?)", (permit, intent_hash, policy_hash, timestamp_ns, expires_at_ns, issuer_hash))
            events = []
            if approval is not None:
                events.append(("approval_verified", approval.audit_payload))
            events.append(("decision", {"outcome": "allow", "reason": decision_reason, "intent_hash": intent_hash, "policy_hash": policy_hash, "issuer_hash": issuer_hash, "issued_at_ns": timestamp_ns, "expires_at_ns": expires_at_ns}))
            self._append_many(events, timestamp_ns)
        return None

    def bind_permit_to_directive(self, permit: str, intent_hash: str, binding: DirectivePermitBinding, timestamp_ns: int) -> None:
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            row = self._connection.execute("SELECT intent_hash, spent, issued_at_ns, expires_at_ns, policy_hash FROM permits WHERE permit = ?", (permit,)).fetchone()
            if row is None or row[0] != intent_hash or row[1] != 0: raise ValueError("permit unavailable for directive binding")
            if ((row[2] is not None and timestamp_ns < row[2]) or (row[3] is not None and timestamp_ns >= row[3]) or (row[4] is not None and row[3] is None)):
                raise ValueError("permit unavailable for directive binding")
            if self._connection.execute("SELECT 1 FROM permit_directives WHERE permit = ?", (permit,)).fetchone(): raise ValueError("permit directive binding is immutable")
            directive = self._connection.execute("SELECT directive_hash, revoked FROM directives WHERE directive_id = ? AND version = ?", (binding.directive_id, binding.version)).fetchone()
            if directive is None or directive[0] != binding.directive_hash or directive[1] != 0: raise ValueError("directive is not active for permit binding")
            if binding.parent_directive_hash is not None and self.directive_hash_status(binding.parent_directive_hash) != "active": raise ValueError("parent directive is not active for permit binding")
            self._connection.execute("INSERT INTO permit_directives (permit, directive_id, directive_version, directive_hash, directive_issued_at_ns, directive_expires_at_ns, parent_directive_hash) VALUES (?, ?, ?, ?, ?, ?, ?)", (permit, binding.directive_id, binding.version, binding.directive_hash, binding.issued_at_ns, binding.expires_at_ns, binding.parent_directive_hash))
            self._append("permit_bound_to_directive", {"intent_hash": intent_hash, **binding.audit_payload()}, timestamp_ns)

    def consume_permit(self, permit: str, intent_hash: str, timestamp_ns: int, *, policy_hash: str | None = None, issuer_hash: str | None = None, clock: Callable[[], int] | None = None) -> bool:
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            timestamp_ns = _sample_post_lock_timestamp(timestamp_ns, clock)
            permit_row = self._connection.execute("SELECT intent_hash, spent, policy_hash, issued_at_ns, expires_at_ns, issuer_hash FROM permits WHERE permit = ?", (permit,)).fetchone()
            valid = permit_row is not None and permit_row[0] == intent_hash and permit_row[1] == 0
            if policy_hash is not None:
                valid = valid and permit_row[2] == policy_hash and permit_row[3] is not None and permit_row[5] == issuer_hash and type(permit_row[4]) is int
            if permit_row is not None and permit_row[3] is not None:
                valid = valid and type(timestamp_ns) is int and timestamp_ns >= permit_row[3]
                valid = valid and (permit_row[4] is None or timestamp_ns < permit_row[4])
            payload: dict[str, Any] = {"intent_hash": intent_hash}
            row = self._connection.execute("SELECT directive_id, directive_version, directive_hash, directive_issued_at_ns, directive_expires_at_ns, parent_directive_hash FROM permit_directives WHERE permit = ?", (permit,)).fetchone()
            if row is not None:
                binding = DirectivePermitBinding(row[0], row[1], row[2], row[3], row[4], row[5])
                directive = self._connection.execute("SELECT directive_hash, revoked FROM directives WHERE directive_id = ? AND version = ?", (binding.directive_id, binding.version)).fetchone()
                if directive is None: status = "directive_not_authorized"
                elif directive[0] != binding.directive_hash: status = "directive_version_mismatch"
                elif directive[1] != 0: status = "directive_revoked"
                elif binding.parent_directive_hash is not None: status = self.directive_hash_status(binding.parent_directive_hash)
                else: status = "active"
                if status == "active" and not (binding.issued_at_ns <= timestamp_ns < binding.expires_at_ns): status = "directive_inactive"
                valid = valid and status == "active"
                payload.update(binding.audit_payload()); payload["directive_status"] = status
            if valid:
                cursor = self._connection.execute("UPDATE permits SET spent = 1 WHERE permit = ? AND intent_hash = ? AND spent = 0", (permit, intent_hash))
                valid = cursor.rowcount == 1
            self._append("permit_consumed" if valid else "permit_rejected", payload, timestamp_ns)
        return valid

    def revalidate_consumed_permit(self, permit: str, intent_hash: str, timestamp_ns: int, *, policy_hash: str | None = None, issuer_hash: str | None = None) -> str:
        # Read-only re-check of the exact state consume_permit validated, under
        # the same BEGIN IMMEDIATE discipline, for the window between
        # consumption and execution. It appends nothing: callers record the
        # refusal or unknown outcome. A NULL expires_at_ns means no expiry
        # (load-bearing fork semantics); this re-check must not re-impose a
        # stricter expiry invariant.
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            permit_row = self._connection.execute("SELECT intent_hash, spent, policy_hash, issued_at_ns, expires_at_ns, issuer_hash FROM permits WHERE permit = ?", (permit,)).fetchone()
            if permit_row is None:
                return "permit_not_found"
            if permit_row[0] != intent_hash:
                return "permit_intent_mismatch"
            if permit_row[1] != 1:
                return "permit_not_consumed"
            if policy_hash is not None:
                if permit_row[2] != policy_hash:
                    return "permit_policy_mismatch"
                if permit_row[5] != issuer_hash:
                    return "permit_issuer_mismatch"
            if permit_row[3] is not None:
                if type(timestamp_ns) is not int or timestamp_ns < permit_row[3]:
                    return "permit_not_yet_valid"
                if permit_row[4] is not None and timestamp_ns >= permit_row[4]:
                    return "permit_expired"
            row = self._connection.execute("SELECT directive_id, directive_version, directive_hash, directive_issued_at_ns, directive_expires_at_ns, parent_directive_hash FROM permit_directives WHERE permit = ?", (permit,)).fetchone()
            if row is not None:
                binding = DirectivePermitBinding(row[0], row[1], row[2], row[3], row[4], row[5])
                directive = self._connection.execute("SELECT directive_hash, revoked FROM directives WHERE directive_id = ? AND version = ?", (binding.directive_id, binding.version)).fetchone()
                if directive is None: status = "directive_not_authorized"
                elif directive[0] != binding.directive_hash: status = "directive_version_mismatch"
                elif directive[1] != 0: status = "directive_revoked"
                elif binding.parent_directive_hash is not None: status = self.directive_hash_status(binding.parent_directive_hash)
                else: status = "active"
                if status == "active" and not (binding.issued_at_ns <= timestamp_ns < binding.expires_at_ns): status = "directive_inactive"
                if status != "active":
                    return status
            return "valid"

    def activate_directive(self, directive, authority_evidence: dict[str, object], timestamp_ns: int) -> None:
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            if self._connection.execute("SELECT 1 FROM directives WHERE directive_id=? AND version=?", (directive.directive_id, directive.version)).fetchone(): raise ValueError("directive version is immutable")
            parent_hash = getattr(directive, "parent_directive_hash", None)
            if parent_hash is not None:
                parent = self._connection.execute("SELECT revoked FROM directives WHERE directive_hash=?", (parent_hash,)).fetchone()
                if parent is None or parent[0] != 0:
                    raise ValueError("parent directive is not active for activation")
            self._connection.execute("INSERT INTO directives (directive_id, version, directive_hash) VALUES (?, ?, ?)", (directive.directive_id, directive.version, directive.directive_hash))
            self._append("directive_activated", {"directive_id": directive.directive_id, "version": directive.version, "directive_hash": directive.directive_hash, "authority_evidence": authority_evidence}, timestamp_ns)

    def revoke_directive(self, directive_id: str, version: int, authority_evidence: dict[str, object], timestamp_ns: int) -> None:
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            row = self._connection.execute("SELECT directive_hash FROM directives WHERE directive_id=? AND version=?", (directive_id, version)).fetchone()
            if row is None: raise ValueError("directive version not found")
            self._connection.execute("UPDATE directives SET revoked=1 WHERE directive_id=? AND version=?", (directive_id, version))
            self._append("directive_revoked", {"directive_id": directive_id, "version": version, "directive_hash": row[0], "authority_evidence": authority_evidence}, timestamp_ns)

    def directive_status(self, directive_id: str, version: int, directive_hash: str) -> str:
        row = self._connection.execute("SELECT directive_hash, revoked FROM directives WHERE directive_id=? AND version=?", (directive_id, version)).fetchone()
        if row is None: return "directive_not_authorized"
        if row[0] != directive_hash: return "directive_version_mismatch"
        return "directive_revoked" if row[1] else "active"

    def directive_hash_status(self, directive_hash: str) -> str:
        row = self._connection.execute("SELECT revoked FROM directives WHERE directive_hash=?", (directive_hash,)).fetchone()
        if row is None: return "directive_parent_not_authorized"
        return "directive_parent_revoked" if row[0] else "active"

    def append(self, event: str, payload: dict[str, Any], timestamp_ns: int) -> None:
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE"); self._append(event, payload, timestamp_ns)

    def append_unique(
        self,
        event: str,
        identity_field: str,
        identity_value: Any,
        payload: dict[str, Any],
        timestamp_ns: int,
    ) -> dict[str, Any] | None:
        if not event or not identity_field or payload.get(identity_field) != identity_value:
            raise ValueError("unique audit identity invalid")
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            with closing(self._connection.execute(
                "SELECT payload_json FROM audit WHERE event = ? ORDER BY sequence",
                (event,),
            )) as rows:
                # Stream raw rows within the same locked transaction. Still scan
                # every row: later duplicates or malformed JSON must not be hidden.
                # Close even on failure: a retained traceback must not hold a read lock.
                matches: list[dict[str, Any]] = []
                for (encoded,) in rows:
                    candidate = json.loads(str(encoded))
                    if isinstance(candidate, dict) and candidate.get(identity_field) == identity_value:
                        matches.append(candidate)
            if len(matches) > 1:
                raise ValueError("unique audit identity ambiguous")
            if matches:
                return matches[0]
            self._append(event, payload, timestamp_ns)
            return None

    def _append(self, event: str, payload: dict[str, Any], timestamp_ns: int) -> None:
        self._append_many([(event, payload)], timestamp_ns)

    def _append_many(self, events: list[tuple[str, dict[str, Any]]], timestamp_ns: int) -> None:
        # Callers hold BEGIN IMMEDIATE. Keep the tip local to this transaction:
        # another connection may advance it immediately after we commit.
        if self.audit_signer is not None and not self._audit_has_signature:
            # A signer-configured backend must never silently append
            # unsigned records: the chain would then verify as unsigned
            # under a signer that expects every record signed.
            raise RuntimeError("audit signing is enabled but the state schema has no signature column")
        row = self._connection.execute("SELECT hash FROM audit ORDER BY sequence DESC LIMIT 1").fetchone()
        previous = row[0] if row else "0" * 64
        rows = []
        for event, payload in events:
            record = _audit_record(previous, event, payload, timestamp_ns, signer=self.audit_signer)
            rows.append((event, _canonical(payload).decode(), previous, timestamp_ns, record["hash"], record.get("signature")))
            previous = record["hash"]
        if self._audit_has_signature:
            self._connection.executemany(
                "INSERT INTO audit (event, payload_json, previous_hash, timestamp_ns, hash, signature) VALUES (?, ?, ?, ?, ?, ?)",
                rows,
            )
        else:
            # A pre-signature schema opened read-only: the insert
            # itself is refused by the connection, but keep the
            # statement valid against the columns that exist.
            self._connection.executemany(
                "INSERT INTO audit (event, payload_json, previous_hash, timestamp_ns, hash) VALUES (?, ?, ?, ?, ?)",
                [row[:5] for row in rows],
            )

    def close(self) -> None:
        if not self._closed:
            self._connection.close()
            self._closed = True

    def __enter__(self) -> "SQLiteKernelState":
        if self._closed:
            raise sqlite3.ProgrammingError("kernel state is closed")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        # Closing rolls back pending work; cleanup must never authorize a commit.
        self.close()


def capture_recovery_pin(path: str | PathLike[str]) -> str:
    """Run the required operator pin-capture step; see docs/RECOVERY_PIN_OPERATOR_STEP.md.

    Opens the state (ordinary construction verifies the audit head and schema),
    verifies the full hash linkage of the audit chain, then captures the pin.
    The pin is returned, never written anywhere: retaining it is the trusted
    operator's job, and it must live independently of the state file and its
    backups. Deliberately no store is created here — a pin persisted alongside
    state would roll back with the file it is meant to detect, which is
    exactly the co-rollback the recovery docstring warns about.

    Call only with writers quiesced. Every subsequent canonical write
    invalidates the pin, so capture it fresh at each backup. Refuses a broken
    audit chain instead of pinning it.
    """
    state = SQLiteKernelState(path)
    try:
        previous = "0" * 64
        for record in state.audit:
            # The signature is a sibling of ``hash``, excluded from the
            # hashed body: recomputation must exclude it too, or a
            # signed chain fails closed spuriously at pin capture.
            body = {key: value for key, value in record.items() if key not in ("hash", "signature")}
            if (record["previous_hash"] != previous
                    or record["hash"] != _audit_record(body["previous_hash"], body["event"],
                                                       body["payload"], body["timestamp_ns"])["hash"]):
                raise StateRecoveryError("recovery pin capture refused: audit chain invalid")
            previous = record["hash"]
        return state.recovery_checkpoint()
    finally:
        state.close()
