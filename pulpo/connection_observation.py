"""Public, bounded connection observations. No network or credential capability."""
from dataclasses import dataclass, fields
import time


PROVIDERS = ("UniFi UDM", "NinjaOne", "CrowdStrike")
REASONS = {
    "ok": "Read collection completed; permissions beyond these requests are unassessed.",
    "unknown": "No collection observation supplied.",
    "authentication": "Authentication rejected. Inspect the collector's credential configuration.",
    "permission": "Access denied. Inspect the provider's read permissions and entitlement.",
    "rate_limit": "Provider rate limit reached. No automatic retry was performed.",
    "tls": "TLS validation failed. Inspect certificate trust and the intended endpoint.",
    "timeout": "Read timed out. Current service health remains Unknown.",
    "unavailable": "Service could not be reached. Inspect the owner-side network and endpoint.",
    "response": "Unsupported, redirected, oversized or malformed response. Previous metrics cleared.",
    "configuration": "Collector configuration is invalid or incomplete; no connection result inferred.",
}


def count(value):
    return value is None or type(value) is int and 0 <= value <= 2**63 - 1


@dataclass(frozen=True, slots=True)
class ConnectionObservation:
    provider: str
    observed_at_ns: int
    reachability: str = "Unknown"
    authentication: str = "Unknown"
    reason: str = "unknown"
    source_id: str = "Unknown"
    devices_seen: int | None = None
    online_seen: int | None = None
    clients_seen: int | None = None
    alerts_seen: int | None = None
    schema: str = "pulpo.connection-observation.v1"

    def __post_init__(self):
        if (self.provider not in PROVIDERS or self.schema != "pulpo.connection-observation.v1"
                or type(self.source_id) is not str or (self.source_id != "Unknown" and
                    (len(self.source_id) != 32 or any(c not in "0123456789abcdef" for c in self.source_id)))
                or type(self.observed_at_ns) is not int or not 0 <= self.observed_at_ns <= 2**63 - 1
                or self.reachability not in {"Unknown", "Responded", "Unavailable"}
                or self.authentication not in {"Unknown", "Accepted", "Rejected"} or self.reason not in REASONS
                or any(not count(getattr(self, name)) for name in ("devices_seen", "online_seen", "clients_seen", "alerts_seen"))):
            raise ValueError("invalid_connection_observation")
        metrics = (self.devices_seen, self.online_seen, self.clients_seen, self.alerts_seen)
        if self.reason != "ok" and any(v is not None for v in metrics):
            raise ValueError("failed_collection_has_metrics")
        if self.reason == "ok" and (self.reachability != "Responded" or self.authentication != "Accepted"):
            raise ValueError("invalid_collection_success")
        if self.online_seen is not None and (self.devices_seen is None or self.online_seen > self.devices_seen):
            raise ValueError("invalid_online_count")
        if self.provider != "UniFi UDM" and (self.online_seen is not None or self.clients_seen is not None):
            raise ValueError("unsupported_provider_metric")
        if self.provider == "UniFi UDM" and self.alerts_seen is not None:
            raise ValueError("unsupported_provider_metric")

    def freshness(self, now_ns=None):
        seconds = ((time.time_ns() if now_ns is None else now_ns) - self.observed_at_ns) / 1e9
        return "Clock mismatch" if seconds < -5 else "Stale" if seconds > 60 else "Recent source timestamp"


def load_connection_observation(path):
    from .mcp_plugin import read_snapshot_document
    value = read_snapshot_document(path)
    if type(value) is not dict or set(value) != {f.name for f in fields(ConnectionObservation)}:
        raise ValueError("invalid_connection_fields")
    result = ConnectionObservation(**value)
    if result.freshness() == "Clock mismatch":
        raise ValueError("connection_clock_mismatch")
    return result
