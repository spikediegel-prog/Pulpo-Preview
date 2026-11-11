#!/usr/bin/env python3
"""Validate a Pulpo Preview installer config document.

Mirrors the rules in the Control Center's ``system_config.py``
(PR #55 guided setup), so a config the installer writes is one
``pulpo-control-center config import`` will accept:

- schema must be ``pulpo.control-center-customer-config.v1``
- display_timezone must be a real IANA name (zoneinfo)
- NTP primary/secondary must be valid hostnames/IPs and must differ
- network: ``dhcp`` (default, takes no manual values) or ``static``
  (requires a CIDR address; a gateway, when set, must be on that
  subnet; at most 3 DNS servers). Gateway unset = no default route =
  no internet access: a valid, deliberate choice, not an error.
- storage: kind ``external``/``local``; retention_hours 1..24;
  retention_percent 1..100; ``acknowledged`` must be true
  ("Pulpo is NOT responsible for your data, backups, or storage.")

Usage: python3 validate_config.py <config.json> [...]
Exit 0 when every file is valid, 1 otherwise. Prints one line per file.
No authority is granted or changed by this check; it only reads.
"""

from __future__ import annotations

import ipaddress
import json
import re
import sys
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

SCHEMA = "pulpo.control-center-customer-config.v1"
_HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)([A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?)"
    r"(\.[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$"
)


def _is_ntp_server(value):
    if not isinstance(value, str) or not value:
        return False
    if _HOSTNAME_RE.match(value):
        return True
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def validate(doc):
    errors = []
    if not isinstance(doc, dict):
        return ["document must be a JSON object"]
    if doc.get("schema") != SCHEMA:
        errors.append(f"schema must be {SCHEMA!r}")
    tz = doc.get("display_timezone")
    if not isinstance(tz, str) or not tz:
        errors.append("display_timezone is required")
    else:
        try:
            ZoneInfo(tz)
        except (ZoneInfoNotFoundError, ValueError):
            errors.append(f"display_timezone {tz!r} is not a known IANA timezone")

    time_cfg = doc.get("time")
    if not isinstance(time_cfg, dict):
        errors.append("time must be an object with primary/secondary")
    else:
        primary, secondary = time_cfg.get("primary"), time_cfg.get("secondary")
        for name, value in (("primary", primary), ("secondary", secondary)):
            if value is not None and not _is_ntp_server(value):
                errors.append(f"time.{name} {value!r} is not a valid NTP server")
        if primary and secondary and primary == secondary:
            errors.append("time.primary and time.secondary must differ")

    net = doc.get("network")
    if not isinstance(net, dict):
        errors.append("network must be an object with mode/address/gateway/dns")
    else:
        mode = net.get("mode")
        if mode not in ("dhcp", "static"):
            errors.append(f"network.mode must be 'dhcp' or 'static', got {mode!r}")
        elif mode == "dhcp":
            if net.get("address") or net.get("gateway") or net.get("dns"):
                errors.append("dhcp takes no manual address/gateway/dns values")
        else:
            address = net.get("address")
            interface = None
            if not address:
                errors.append("static network requires address (CIDR, e.g. 192.168.1.10/24)")
            else:
                try:
                    interface = ipaddress.IPv4Interface(address)
                except ValueError:
                    errors.append(f"network.address {address!r} is not valid CIDR")
            gateway = net.get("gateway")
            if gateway is not None:
                try:
                    gw = ipaddress.IPv4Address(gateway)
                    if interface is not None and gw not in interface.network:
                        errors.append("network.gateway is not on the static subnet")
                except ValueError:
                    errors.append(f"network.gateway {gateway!r} is not a valid IPv4 address")
            dns = net.get("dns") or []
            if not isinstance(dns, list):
                errors.append("network.dns must be a list")
            else:
                if len(dns) > 3:
                    errors.append("network.dns allows at most 3 servers")
                for server in dns:
                    try:
                        ipaddress.IPv4Address(server)
                    except ValueError:
                        errors.append(f"network.dns entry {server!r} is not a valid IPv4 address")

    storage = doc.get("storage")
    if not isinstance(storage, dict):
        errors.append("storage must be an object")
    else:
        if storage.get("kind") not in ("external", "local"):
            errors.append("storage.kind must be 'external' or 'local'")
        path = storage.get("path")
        if path is not None and (not isinstance(path, str) or not path.startswith("/")):
            errors.append("storage.path must be an absolute path when set")
        hours = storage.get("retention_hours")
        if type(hours) is not int or hours < 1:
            errors.append("storage.retention_hours must be an integer >= 1")
        elif hours > 24:
            errors.append("storage.retention_hours exceeds the 24h limit")
        percent = storage.get("retention_percent")
        if type(percent) is not int or percent < 1 or percent > 100:
            errors.append("storage.retention_percent must be an integer 1..100")
        if storage.get("acknowledged") is not True:
            errors.append("storage.acknowledged must be true (responsibility warning seen)")

    return errors


def main(argv):
    if not argv:
        print("usage: validate_config.py <config.json> [...]", file=sys.stderr)
        return 2
    failed = False
    for name in argv:
        path = Path(name)
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"FAIL {name}: cannot read as JSON: {exc}")
            failed = True
            continue
        errors = validate(doc)
        if errors:
            failed = True
            print(f"FAIL {name}:")
            for error in errors:
                print(f"  - {error}")
        else:
            print(f"OK   {name}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
