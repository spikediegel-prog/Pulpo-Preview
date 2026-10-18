"""Canonical kernel state backends.

The state backend persists replay guards, one-use permits, directives, and the
audit chain for the existing governance kernel. It is storage for that kernel,
not another router, policy engine, or evidence ledger.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import hmac
import json
from os import PathLike
import sqlite3
from threading import RLock
from typing import Any, Callable, Protocol

from .audit_parallel import audit_row_has_valid_types


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


def _audit_record(previous_hash: str, event: str, payload: dict[str, Any], timestamp_ns: int) -> dict[str, Any]:
    body = {"event": event, "payload": payload, "previous_hash": previous_hash, "timestamp_ns": timestamp_ns}
    return {**body, "hash": sha256(_canonical(body)).hexdigest()}


@dataclass(frozen=True)
class ApprovalUse:
    approval_id: str
    nonce: str
    audit_payload: dict[str, Any]


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
    def issue_permit(self, permit: str, intent_hash: str, decision_reason: str, timestamp_ns: int, approval: ApprovalUse | None = None, *, policy_hash: str | None = None, issuer_hash: str | None = None, expires_at_ns: int | None = None) -> str | None: ...
    def bind_permit_to_directive(self, permit: str, intent_hash: str, binding: DirectivePermitBinding, timestamp_ns: int) -> None: ...
    def consume_permit(self, permit: str, intent_hash: str, timestamp_ns: int, *, policy_hash: str | None = None, issuer_hash: str | None = None) -> bool: ...
    def directive_hash_status(self, directive_hash: str) -> str: ...
    def append(self, event: str, payload: dict[str, Any], timestamp_ns: int) -> None: ...
    def append_unique(self, event: str, identity_field: str, identity_value: Any, payload: dict[str, Any], timestamp_ns: int) -> dict[str, Any] | None: ...


class InMemoryKernelState:
    def __init__(self) -> None:
        self._issued: dict[str, str] = {}
        self._spent: set[str] = set()
        self._permit_context: dict[str, tuple[str | None, int, int | None, str | None]] = {}
        self._approval_ids: set[str] = set()
        self._approval_nonces: set[str] = set()
        self._directives: dict[tuple[str, int], tuple[str, bool]] = {}
        self._permit_directives: dict[str, DirectivePermitBinding] = {}
        self._audit: list[dict[str, Any]] = []
        self._audit_lock = RLock()

    @property
    def audit(self) -> list[dict[str, Any]]:
        return self._audit

    def approval_replay_reason(self, approval_id: str, nonce: str) -> str | None:
        with self._audit_lock:
            if approval_id in self._approval_ids: return "approval_id_replayed"
            if nonce in self._approval_nonces: return "approval_nonce_replayed"
            return None

    def issue_permit(self, permit: str, intent_hash: str, decision_reason: str, timestamp_ns: int, approval: ApprovalUse | None = None, *, policy_hash: str | None = None, issuer_hash: str | None = None, expires_at_ns: int | None = None) -> str | None:
        with self._audit_lock:
            if approval is not None:
                replay = self.approval_replay_reason(approval.approval_id, approval.nonce)
                if replay: return replay
                self._approval_ids.add(approval.approval_id); self._approval_nonces.add(approval.nonce)
                self.append("approval_verified", approval.audit_payload, timestamp_ns)
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
            self._permit_directives[permit] = binding
            self.append("permit_bound_to_directive", {"intent_hash": intent_hash, **binding.audit_payload()}, timestamp_ns)

    def consume_permit(self, permit: str, intent_hash: str, timestamp_ns: int, *, policy_hash: str | None = None, issuer_hash: str | None = None) -> bool:
        with self._audit_lock:
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
            if valid: self._spent.add(permit)
            self.append("permit_consumed" if valid else "permit_rejected", payload, timestamp_ns)
            return valid

    def activate_directive(self, directive, authority_evidence: dict[str, object], timestamp_ns: int) -> None:
        with self._audit_lock:
            key = (directive.directive_id, directive.version)
            if key in self._directives: raise ValueError("directive version is immutable")
            parent_hash = getattr(directive, "parent_directive_hash", None)
            if parent_hash is not None and self.directive_hash_status(parent_hash) != "active":
                raise ValueError("parent directive is not active for activation")
            self._directives[key] = (directive.directive_hash, False)
            self.append("directive_activated", {"directive_id": directive.directive_id, "version": directive.version, "directive_hash": directive.directive_hash, "authority_evidence": authority_evidence}, timestamp_ns)

    def revoke_directive(self, directive_id: str, version: int, authority_evidence: dict[str, object], timestamp_ns: int) -> None:
        with self._audit_lock:
            key = (directive_id, version)
            if key not in self._directives: raise ValueError("directive version not found")
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
            self._audit.append(_audit_record(previous, event, payload, timestamp_ns))

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
            self._audit.append(_audit_record(previous, event, payload, timestamp_ns))
            return None


class SQLiteKernelState:
    def __init__(self, path: str | PathLike[str], *, index_audit_events: bool = False) -> None:
        self._connection = sqlite3.connect(path)
        self._closed = False
        try:
            self._initialize(index_audit_events=index_audit_events)
        except BaseException:
            self.close()
            raise

    def _initialize(self, *, index_audit_events: bool) -> None:
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA synchronous = FULL")
        # executescript commits an existing transaction before running. Execute
        # each DDL statement under one explicit transaction instead, including
        # validation, legacy ALTERs, head adoption and trigger publication.
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            self._initialize_transaction(index_audit_events=index_audit_events)

    def _initialize_transaction(self, *, index_audit_events: bool) -> None:
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
            CREATE TABLE IF NOT EXISTS audit (sequence INTEGER PRIMARY KEY, event TEXT NOT NULL, payload_json TEXT NOT NULL, previous_hash TEXT NOT NULL, timestamp_ns INTEGER NOT NULL, hash TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS audit_verification_checkpoint (id INTEGER PRIMARY KEY CHECK (id = 1), checkpoint_json TEXT NOT NULL);
        """
        for statement in schema.split(";"):
            if statement.strip():
                self._connection.execute(statement)
        # Opt in for event-heavy histories: the index speeds filtered reads but
        # adds maintenance to every durable audit insert. Existing indexes stay.
        if index_audit_events:
            self._connection.execute("CREATE INDEX IF NOT EXISTS audit_event_sequence ON audit(event, sequence)")
        permit_columns = {row[1] for row in self._connection.execute("PRAGMA table_info(permits)")}
        for name, kind in (("policy_hash", "TEXT"), ("issued_at_ns", "INTEGER"), ("expires_at_ns", "INTEGER"), ("issuer_hash", "TEXT")):
            if name not in permit_columns:
                self._connection.execute(f"ALTER TABLE permits ADD COLUMN {name} {kind}")
        columns = {row[1] for row in self._connection.execute("PRAGMA table_info(permit_directives)").fetchall()}
        if "parent_directive_hash" not in columns:
            self._connection.execute("ALTER TABLE permit_directives ADD COLUMN parent_directive_hash TEXT")
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

    @property
    def audit(self) -> list[dict[str, Any]]:
        rows = self._checked_audit_rows()
        return [{"event": e, "payload": json.loads(p), "previous_hash": ph, "timestamp_ns": ts, "hash": h} for _,e,p,ph,ts,h in rows]

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
            if rows:
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

    def approval_replay_reason(self, approval_id: str, nonce: str) -> str | None: return self._approval_replay_reason(approval_id, nonce)
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

    def issue_permit(self, permit: str, intent_hash: str, decision_reason: str, timestamp_ns: int, approval: ApprovalUse | None = None, *, policy_hash: str | None = None, issuer_hash: str | None = None, expires_at_ns: int | None = None) -> str | None:
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            if approval is not None:
                replay = self._approval_replay_reason(approval.approval_id, approval.nonce)
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

    def consume_permit(self, permit: str, intent_hash: str, timestamp_ns: int, *, policy_hash: str | None = None, issuer_hash: str | None = None) -> bool:
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
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
            rows = self._connection.execute(
                "SELECT payload_json FROM audit WHERE event = ? ORDER BY sequence",
                (event,),
            )
            # Stream raw rows within the same locked transaction. Still scan
            # every row: later duplicates or malformed JSON must not be hidden.
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
        row = self._connection.execute("SELECT hash FROM audit ORDER BY sequence DESC LIMIT 1").fetchone()
        previous = row[0] if row else "0" * 64
        rows = []
        for event, payload in events:
            record = _audit_record(previous, event, payload, timestamp_ns)
            rows.append((event, _canonical(payload).decode(), previous, timestamp_ns, record["hash"]))
            previous = record["hash"]
        self._connection.executemany(
            "INSERT INTO audit (event, payload_json, previous_hash, timestamp_ns, hash) VALUES (?, ?, ?, ?, ?)",
            rows,
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
