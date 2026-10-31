"""Optional challenge-based integrity comparison with a pinned external source."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import secrets
from typing import Callable
from urllib.error import URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import (
    HTTPRedirectHandler,
    Request,
    build_opener,
)

from .. import __version__
from .report import CheckStatus, VerificationCheck

MAX_MANIFEST_BYTES = 64 * 1024
MANIFEST_TIMEOUT_SECONDS = 10
VERIFIED_FILES = (
    "pulpo/__init__.py",
    "pulpo/cli.py",
    "pulpo/verifier/__init__.py",
    "pulpo/verifier/audit.py",
    "pulpo/verifier/authority.py",
    "pulpo/verifier/constitutional.py",
    "pulpo/verifier/custody.py",
    "pulpo/verifier/engine.py",
    "pulpo/verifier/evidence.py",
    "pulpo/verifier/external_integrity.py",
    "pulpo/verifier/report.py",
)

SignatureVerifier = Callable[[bytes, bytes, bytes], bool]


class IntegrityMismatch(ValueError):
    """The trusted source or local verifier failed an integrity condition."""


class _SameOriginRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        source = urlsplit(request.full_url)
        destination = urlsplit(new_url)
        if (
            destination.scheme != "https"
            or destination.hostname != source.hostname
            or destination.port != source.port
            or destination.username is not None
            or destination.password is not None
        ):
            raise URLError("external integrity redirect changed HTTPS origin")
        return super().redirect_request(request, response, code, message, headers, new_url)


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise IntegrityMismatch(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _verify_ed25519(message: bytes, signature: bytes, public_key: bytes) -> bool:
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError as exc:
        raise RuntimeError("signature verification requires the pulpo[authority] extra") from exc

    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(signature, message)
    except (InvalidSignature, ValueError):
        return False
    return True


def _request_url(url: str, nonce: str) -> str:
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise ValueError("integrity manifest URL must be an HTTPS URL without credentials or fragment")
    query = parse_qsl(parsed.query, keep_blank_values=True)
    if any(key == "nonce" for key, _ in query):
        raise ValueError("integrity manifest URL must not already contain a nonce parameter")
    return urlunsplit(parsed._replace(query=urlencode([*query, ("nonce", nonce)])))


def _load_public_key(path: str | Path) -> bytes:
    raw = Path(path).read_bytes()
    if len(raw) == 32:
        return raw
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError as exc:
        raise RuntimeError("PEM public-key loading requires the pulpo[authority] extra") from exc
    try:
        key = serialization.load_pem_public_key(raw)
    except ValueError as exc:
        raise IntegrityMismatch("pinned public key is not a valid Ed25519 key") from exc
    if not isinstance(key, Ed25519PublicKey):
        raise IntegrityMismatch("pinned public key must use Ed25519")
    return key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def _read_manifest(url: str, timeout: int) -> bytes:
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "Pulpo-Verifier/1"})
    opener = build_opener(_SameOriginRedirectHandler())
    with opener.open(request, timeout=timeout) as response:
        body = response.read(MAX_MANIFEST_BYTES + 1)
    if len(body) > MAX_MANIFEST_BYTES:
        raise IntegrityMismatch("integrity manifest exceeds the size limit")
    return body


def check_external_integrity(
    *,
    manifest_url: str,
    public_key_path: str | Path,
    pinned_key_sha256: str,
    max_age_seconds: int = 300,
    root: str | Path | None = None,
    now: datetime | None = None,
    challenge: str | None = None,
    opener: Callable[[str, int], bytes] | None = None,
    signature_verifier: SignatureVerifier | None = None,
) -> VerificationCheck:
    """Compare local verifier files with a fresh, signed, challenge-bound manifest.

    The key fingerprint must be provisioned independently of the manifest
    endpoint. Supplying test-only clock, challenge, transport, or signature
    hooks is intended only for deterministic tests.
    """

    if (
        not isinstance(pinned_key_sha256, str)
        or re.fullmatch(r"[0-9a-f]{64}", pinned_key_sha256) is None
    ):
        raise ValueError("pinned key fingerprint must be a lowercase SHA-256 digest")
    if type(max_age_seconds) is not int or not 1 <= max_age_seconds <= 604800:
        raise ValueError("maximum manifest age must be between 1 and 604800 seconds")
    nonce = challenge or secrets.token_hex(32)
    if re.fullmatch(r"[0-9a-f]{64}", nonce) is None:
        raise ValueError("integrity challenge must be 64 lowercase hexadecimal characters")

    evidence: list[str] = [f"challenge={nonce}"]
    try:
        public_key = _load_public_key(public_key_path)
        observed_fingerprint = hashlib.sha256(public_key).hexdigest()
        evidence.append(f"pinned_key_sha256={observed_fingerprint}")
        if observed_fingerprint != pinned_key_sha256:
            raise IntegrityMismatch("pinned public-key fingerprint mismatch")

        request_url = _request_url(manifest_url, nonce)
        response_body = (
            opener(request_url, MANIFEST_TIMEOUT_SECONDS)
            if opener is not None
            else _read_manifest(request_url, MANIFEST_TIMEOUT_SECONDS)
        )
    except ValueError as exc:
        if isinstance(exc, IntegrityMismatch):
            return _failed_check(str(exc), evidence)
        raise
    except (OSError, URLError, TimeoutError, RuntimeError) as exc:
        return _unverifiable_check(f"external integrity source unavailable: {exc}", evidence)

    try:
        envelope = json.loads(response_body, object_pairs_hook=_reject_duplicate_keys)
        if not isinstance(envelope, dict) or set(envelope) != {"manifest", "signature"}:
            raise IntegrityMismatch("integrity response envelope is invalid")
        manifest = envelope["manifest"]
        signature_hex = envelope["signature"]
        if not isinstance(manifest, dict) or set(manifest) != {
            "schema",
            "version",
            "nonce",
            "generated_at",
            "files",
        }:
            raise IntegrityMismatch("integrity manifest fields are invalid")
        if manifest["schema"] != "pulpo.integrity-manifest.v1":
            raise IntegrityMismatch("unsupported integrity manifest schema")
        if manifest["version"] != __version__:
            raise IntegrityMismatch("integrity manifest version does not match the installed verifier")
        if manifest["nonce"] != nonce:
            raise IntegrityMismatch("integrity response challenge mismatch")
        if not isinstance(signature_hex, str) or re.fullmatch(r"[0-9a-f]{128}", signature_hex) is None:
            raise IntegrityMismatch("integrity manifest signature encoding is invalid")

        generated_at_raw = manifest["generated_at"]
        if not isinstance(generated_at_raw, str):
            raise IntegrityMismatch("integrity manifest timestamp is invalid")
        try:
            generated_at = datetime.fromisoformat(generated_at_raw.replace("Z", "+00:00"))
        except ValueError as exc:
            raise IntegrityMismatch("integrity manifest timestamp is invalid") from exc
        if generated_at.tzinfo is None:
            raise IntegrityMismatch("integrity manifest timestamp must include a timezone")
        current_time = now or datetime.now(timezone.utc)
        if current_time.tzinfo is None:
            raise ValueError("verification clock must include a timezone")
        age = current_time - generated_at.astimezone(timezone.utc)
        if age < timedelta(seconds=-60):
            raise IntegrityMismatch("integrity manifest timestamp is in the future")
        if age > timedelta(seconds=max_age_seconds):
            raise IntegrityMismatch("integrity manifest is stale")

        files = manifest["files"]
        if not isinstance(files, dict) or set(files) != set(VERIFIED_FILES):
            raise IntegrityMismatch("integrity manifest file list does not match the verifier scope")
        signature_check = signature_verifier or _verify_ed25519
        if signature_check(_canonical(manifest), bytes.fromhex(signature_hex), public_key) is not True:
            raise IntegrityMismatch("integrity manifest signature is invalid")

        repository_root = Path(root) if root is not None else Path(__file__).resolve().parents[2]
        mismatches: list[str] = []
        for relative_path in VERIFIED_FILES:
            expected = files[relative_path]
            if not isinstance(expected, str) or re.fullmatch(r"[0-9a-f]{64}", expected) is None:
                raise IntegrityMismatch(f"integrity digest is invalid for {relative_path}")
            try:
                actual = hashlib.sha256((repository_root / relative_path).read_bytes()).hexdigest()
            except OSError as exc:
                return _unverifiable_check(f"cannot read local verifier file {relative_path}: {exc}", evidence)
            if actual != expected:
                mismatches.append(relative_path)
        evidence.extend(
            (
                f"manifest_generated_at={generated_at.astimezone(timezone.utc).isoformat()}",
                f"files_checked={len(VERIFIED_FILES)}",
            )
        )
        if mismatches:
            evidence.append(f"mismatched_files={','.join(mismatches)}")
            return _failed_check("local verifier files differ from the signed manifest", evidence)
        evidence.append("challenge_matched=true")
        return VerificationCheck(
            check_id="external-verifier-integrity",
            category="integrity",
            status=CheckStatus.PASS,
            summary="Local verifier files matched a fresh challenge-bound manifest signed by the pinned key.",
            evidence=tuple(evidence),
            claim_classification="Verified",
        )
    except IntegrityMismatch as exc:
        return _failed_check(str(exc), evidence)
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError, KeyError) as exc:
        return _failed_check(f"integrity manifest is malformed: {exc}", evidence)
    except RuntimeError as exc:
        return _unverifiable_check(str(exc), evidence)


def _failed_check(summary: str, evidence: list[str]) -> VerificationCheck:
    return VerificationCheck(
        check_id="external-verifier-integrity",
        category="integrity",
        status=CheckStatus.FAIL,
        summary=summary,
        evidence=tuple(evidence),
        claim_classification="Verified",
    )


def _unverifiable_check(summary: str, evidence: list[str]) -> VerificationCheck:
    return VerificationCheck(
        check_id="external-verifier-integrity",
        category="integrity",
        status=CheckStatus.UNVERIFIABLE,
        summary=summary,
        evidence=tuple(evidence),
        claim_classification="Unknown",
    )
