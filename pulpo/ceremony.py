"""Verification-only human-ceremony evidence contracts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from typing import Protocol


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _require_text(value: str, field: str) -> None:
    if type(value) is not str or not value or value != value.strip():
        raise ValueError(f"{field} must be non-empty canonical text")


def _require_sha256(value: str, field: str) -> None:
    if (type(value) is not str or len(value) != 64 or value != value.lower()
            or any(character not in "0123456789abcdef" for character in value)):
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")


@dataclass(frozen=True)
class CeremonyTrust:
    """Public trust anchor, separate from the approval authority key."""

    authority_id: str
    verifier_id: str
    key_id: str
    algorithm: str
    key_fingerprint: str
    method: str
    max_evidence_ttl_ns: int
    schema: str = "pulpo.ceremony-trust.v1"

    def __post_init__(self) -> None:
        for value, field in (
            (self.authority_id, "authority_id"),
            (self.verifier_id, "verifier_id"),
            (self.key_id, "key_id"),
            (self.algorithm, "algorithm"),
            (self.method, "method"),
        ):
            _require_text(value, field)
        _require_sha256(self.key_fingerprint, "key_fingerprint")
        if (type(self.max_evidence_ttl_ns) is not int
                or self.max_evidence_ttl_ns <= 0):
            raise ValueError("max_evidence_ttl_ns must be positive")
        if self.schema != "pulpo.ceremony-trust.v1":
            raise ValueError("unsupported ceremony trust schema")

    @property
    def trust_hash(self) -> str:
        return sha256(_canonical(asdict(self))).hexdigest()


@dataclass(frozen=True)
class CeremonyEvidence:
    """Signed assertion binding a completed ceremony to one approval context."""

    evidence_id: str
    authority_id: str
    verifier_id: str
    key_id: str
    method: str
    trust_hash: str
    approval_id: str
    envelope_hash: str
    intent_hash: str
    policy_hash: str
    principal: str
    session_id: str
    approval_nonce: str
    issued_at_ns: int
    expires_at_ns: int
    signature: str
    schema: str = "pulpo.ceremony-evidence.v1"

    def __post_init__(self) -> None:
        for value, field in (
            (self.evidence_id, "evidence_id"),
            (self.authority_id, "authority_id"),
            (self.verifier_id, "verifier_id"),
            (self.key_id, "key_id"),
            (self.method, "method"),
            (self.approval_id, "approval_id"),
            (self.principal, "principal"),
            (self.session_id, "session_id"),
            (self.approval_nonce, "approval_nonce"),
        ):
            _require_text(value, field)
        for value, field in (
            (self.trust_hash, "trust_hash"),
            (self.envelope_hash, "envelope_hash"),
            (self.intent_hash, "intent_hash"),
            (self.policy_hash, "policy_hash"),
        ):
            _require_sha256(value, field)
        if type(self.issued_at_ns) is not int or self.issued_at_ns <= 0:
            raise ValueError("issued_at_ns must be positive")
        if type(self.expires_at_ns) is not int or self.expires_at_ns <= self.issued_at_ns:
            raise ValueError("expires_at_ns must be greater than issued_at_ns")
        if type(self.signature) is not str:
            raise ValueError("signature must be text")
        if self.schema != "pulpo.ceremony-evidence.v1":
            raise ValueError("unsupported ceremony evidence schema")

    def signing_payload(self) -> dict[str, object]:
        return {key: value for key, value in asdict(self).items() if key != "signature"}

    def signing_bytes(self) -> bytes:
        return _canonical(self.signing_payload())

    @property
    def signing_payload_hash(self) -> str:
        return sha256(self.signing_bytes()).hexdigest()

    @property
    def evidence_hash(self) -> str:
        return sha256(_canonical(asdict(self))).hexdigest()


class CeremonyVerifier(Protocol):
    """Configured verification-only trust boundary for ceremony evidence."""

    authority_id: str
    verifier_id: str
    key_id: str
    algorithm: str
    key_fingerprint: str

    def verify(self, payload: bytes, signature: str) -> bool:
        """Return true only for the separately trusted ceremony signature."""


class _KeyDerivedCeremonyVerifier:
    __slots__ = ("__authority_id", "__verifier_id", "__key_id", "__key_fingerprint")
    algorithm: str

    def __init__(
        self,
        *,
        authority_id: str,
        verifier_id: str,
        key_id: str,
        key_fingerprint: str,
    ) -> None:
        for value, field in (
            (authority_id, "authority_id"),
            (verifier_id, "verifier_id"),
            (key_id, "key_id"),
        ):
            _require_text(value, field)
        _require_sha256(key_fingerprint, "key_fingerprint")
        self.__authority_id = authority_id
        self.__verifier_id = verifier_id
        self.__key_id = key_id
        self.__key_fingerprint = key_fingerprint

    @property
    def authority_id(self) -> str:
        return self.__authority_id

    @property
    def verifier_id(self) -> str:
        return self.__verifier_id

    @property
    def key_id(self) -> str:
        return self.__key_id

    @property
    def key_fingerprint(self) -> str:
        return self.__key_fingerprint


class Ed25519CeremonyVerifier(_KeyDerivedCeremonyVerifier):
    """Verify ceremony evidence against one pinned Ed25519 public key."""

    __slots__ = ("__public_key",)
    algorithm = "ed25519"

    def __init__(
        self,
        *,
        authority_id: str,
        verifier_id: str,
        key_id: str,
        public_key: bytes,
    ) -> None:
        if type(public_key) is not bytes or len(public_key) != 32:
            raise ValueError("Ed25519 public_key must be exactly 32 bytes")
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        except ImportError as exc:
            raise RuntimeError("Ed25519 verification requires the pulpo[authority] extra") from exc
        super().__init__(
            authority_id=authority_id,
            verifier_id=verifier_id,
            key_id=key_id,
            key_fingerprint=sha256(public_key).hexdigest(),
        )
        self.__public_key = Ed25519PublicKey.from_public_bytes(public_key)

    def verify(self, payload: bytes, signature: str) -> bool:
        try:
            from cryptography.exceptions import InvalidSignature

            if (type(signature) is not str or len(signature) != 128
                    or signature != signature.lower()
                    or any(character not in "0123456789abcdef" for character in signature)):
                return False
            self.__public_key.verify(bytes.fromhex(signature), payload)
        except (InvalidSignature, ValueError):
            return False
        return True


class P256CeremonyVerifier(_KeyDerivedCeremonyVerifier):
    """Verify ceremony evidence against one pinned NIST P-256 public key."""

    __slots__ = ("__public_key",)
    algorithm = "ecdsa-p256-sha256"

    def __init__(
        self,
        *,
        authority_id: str,
        verifier_id: str,
        key_id: str,
        public_key: bytes,
    ) -> None:
        if type(public_key) is not bytes or len(public_key) != 65 or public_key[:1] != b"\x04":
            raise ValueError("P-256 public_key must be a 65-byte uncompressed SEC1 point")
        try:
            from cryptography.hazmat.primitives.asymmetric import ec
        except ImportError as exc:
            raise RuntimeError("P-256 verification requires the pulpo[authority] extra") from exc
        try:
            parsed = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), public_key)
        except ValueError as exc:
            raise ValueError("P-256 public_key is not a valid SEC1 point") from exc
        super().__init__(
            authority_id=authority_id,
            verifier_id=verifier_id,
            key_id=key_id,
            key_fingerprint=sha256(public_key).hexdigest(),
        )
        self.__public_key = parsed

    def verify(self, payload: bytes, signature: str) -> bool:
        try:
            from cryptography.exceptions import InvalidSignature
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.asymmetric import ec
            from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

            if (type(signature) is not str or len(signature) != 128
                    or signature != signature.lower()
                    or any(character not in "0123456789abcdef" for character in signature)):
                return False
            raw = bytes.fromhex(signature)
            r = int.from_bytes(raw[:32], "big")
            s = int.from_bytes(raw[32:], "big")
            if r == 0 or s == 0:
                return False
            self.__public_key.verify(
                encode_dss_signature(r, s), payload, ec.ECDSA(hashes.SHA256())
            )
        except (InvalidSignature, ValueError):
            return False
        return True
