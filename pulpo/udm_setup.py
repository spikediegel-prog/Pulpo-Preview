"""Non-secret UDM handoff validation. No network, credentials or execution."""
from dataclasses import dataclass, fields
import ipaddress
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID
from hashlib import sha256


def discovery_source(origin):
    return sha256(("UniFi UDM|" + private_origin(origin)).encode()).hexdigest()[:32]


def collector_command(path, windows=False):
    import shlex
    import unicodedata
    if type(path) is not str or any(ord(c) < 32 or unicodedata.category(c) in ("Pi", "Pf") for c in path):
        raise ValueError("Use a setup filename without control characters or typographic quotes.")
    quoted = "'" + path.replace("'", "''") + "'" if windows else shlex.quote(path)
    return "python -m pulpo.connection_collector unifi --setup-profile " + quoted


def private_origin(origin):
    if type(origin) is not str or not 1 <= len(origin) <= 4096 or any(ord(c) < 33 or ord(c) > 126 for c in origin):
        raise ValueError("Enter an HTTPS address with a private numeric IP.")
    parsed = urlsplit(origin)
    try:
        ip = ipaddress.ip_address(parsed.hostname)
        if (parsed.scheme != "https" or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment
                or parsed.port not in (None, 443)
                or not any(ip in ipaddress.ip_network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7"))):
            raise ValueError()
    except (ValueError, TypeError):
        raise ValueError("Use HTTPS port 443 and a private numeric IP; no credentials, path or query in the address.") from None
    return origin


@dataclass(frozen=True, slots=True)
class UdmSetup:
    origin: str
    mode: str
    output: str
    ca_file: str | None = None
    site_id: str | None = None
    schema: str = "pulpo.udm-setup.v1"

    def __post_init__(self):
        private_origin(self.origin)
        if self.schema != "pulpo.udm-setup.v1" or self.mode not in ("sites", "collect"):
            raise ValueError("Invalid UDM setup mode or format.")
        for value in (self.output, self.ca_file):
            if value is not None and (type(value) is not str or not value or any(ord(c) < 32 for c in value) or not Path(value).is_absolute()):
                raise ValueError("Use absolute file paths without control characters.")
        if not self.output or self.ca_file == self.output:
            raise ValueError("Choose a separate output file.")
        if self.mode == "collect":
            try:
                if str(UUID(self.site_id)) != self.site_id: raise ValueError()
            except (ValueError, TypeError, AttributeError):
                raise ValueError("Choose a canonical site UUID before collecting inventory.") from None
        elif self.site_id is not None:
            raise ValueError("Site discovery must not select a site.")


def load_setup(path):
    from .mcp_plugin import read_snapshot_document
    value = read_snapshot_document(path)
    if type(value) is not dict or set(value) != {f.name for f in fields(UdmSetup)}:
        raise ValueError("Invalid setup fields; credentials and extra options are forbidden.")
    return UdmSetup(**value)


@dataclass(frozen=True, slots=True)
class UdmSites:
    observed_at_ns: int
    source_id: str
    site_ids: tuple[str, ...]
    more_available: bool
    schema: str = "pulpo.udm-sites.v1"

    def __post_init__(self):
        if (type(self.observed_at_ns) is not int or not 0 <= self.observed_at_ns <= 2**63-1
                or type(self.source_id) is not str or len(self.source_id) != 32 or any(c not in "0123456789abcdef" for c in self.source_id)
                or type(self.site_ids) is not tuple or len(self.site_ids) > 100 or len(set(self.site_ids)) != len(self.site_ids)
                or type(self.more_available) is not bool or self.schema != "pulpo.udm-sites.v1"):
            raise ValueError("Invalid site discovery report.")
        for value in self.site_ids:
            try:
                if type(value) is not str or str(UUID(value)) != value: raise ValueError()
            except (ValueError, TypeError, AttributeError):
                raise ValueError("Invalid site identifier.") from None


def load_sites(path):
    import time
    from .mcp_plugin import read_snapshot_document
    value = read_snapshot_document(path)
    if type(value) is not dict or set(value) != {f.name for f in fields(UdmSites)} or type(value["site_ids"]) is not list:
        raise ValueError("Invalid site report fields.")
    value["site_ids"] = tuple(value["site_ids"])
    result = UdmSites(**value)
    age = (time.time_ns() - result.observed_at_ns) / 1e9
    if not -5 <= age <= 900: raise ValueError("Site report is stale or has a clock mismatch; discover again.")
    return result
