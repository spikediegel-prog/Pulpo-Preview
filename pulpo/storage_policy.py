"""Customer storage planning metadata only; no exporter or canonical writer."""
from pathlib import PurePosixPath

REVISION = "pulpo.customer-evidence-storage.v1"
CHOICES = {
    "local": "Local filesystem · manual public-export handoff",
    "nas": "Mounted NAS (SMB/NFS) · manual public-export handoff",
    "san": "SAN-backed filesystem · manual public-export handoff",
}
PLANNED = "Planned, unavailable here: SIEM/syslog forwarding; S3-compatible delivery; automated hybrid delivery."
RESPONSIBILITY = (
    "Pulpo provides documented evidence generation, integrity checks and supported exports. "
    "Local observation history is bounded; the canonical audit is not automatically pruned. "
    "Customers manage long-term storage, retention obligations, backups, restore tests and legal holds. "
    "A dashboard snapshot is not a complete audit archive or proof of external durability."
)
ACKNOWLEDGMENT = (
    "I acknowledge the customer's responsibility for long-term evidence storage, retention obligations, "
    "backups and legal holds. This plan does not enable transfer or deletion."
)


def validate(value):
    if (type(value) is not dict or set(value) != {"revision", "choice", "destination", "acknowledged"}
            or value["revision"] != REVISION or type(value["choice"]) is not str
            or value["choice"] not in CHOICES or value["acknowledged"] is not True):
        raise ValueError("storage_plan_requires_supported_choice_and_acknowledgment")
    path = value["destination"]
    if (type(path) is not str or not 1 < len(path) <= 4096 or not path.startswith("/")
            or path.startswith("//") or ".." in PurePosixPath(path).parts
            or any(ord(c) < 32 or ord(c) == 127 for c in path)):
        raise ValueError("storage_plan_requires_absolute_mounted_path")
    return value
