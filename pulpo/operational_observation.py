"""Primitive operational projection; no credentials, callbacks or authority."""
from dataclasses import dataclass, fields


@dataclass(frozen=True, slots=True)
class OperationalObservation:
    source_id: str
    observed_at_ns: int
    policy_hash: str
    audit_valid: bool
    database_health: str
    pending_evidence_obligations: int | None
    schema: str = "pulpo.operational-observation.v1"

    def __post_init__(self):
        for value, length in ((self.source_id, 32), (self.policy_hash, 64)):
            if type(value) is not str or len(value) != length or any(c not in "0123456789abcdef" for c in value):
                raise ValueError("invalid_operational_fingerprint")
        if type(self.observed_at_ns) is not int or not 0 <= self.observed_at_ns <= 2**63 - 1:
            raise ValueError("invalid_operational_time")
        if type(self.audit_valid) is not bool or type(self.database_health) is not str or self.database_health not in {"ok", "failed", "not_checked", "unavailable"}:
            raise ValueError("invalid_operational_health")
        pending = self.pending_evidence_obligations
        if pending is not None and (type(pending) is not int or not 0 <= pending <= 2**63 - 1):
            raise ValueError("invalid_operational_backlog")
        if type(self.schema) is not str or self.schema != "pulpo.operational-observation.v1":
            raise ValueError("invalid_operational_schema")


def parse_operational(document):
    if type(document) is not dict or set(document) != {field.name for field in fields(OperationalObservation)}:
        raise ValueError("invalid_operational_fields")
    return OperationalObservation(**document)
