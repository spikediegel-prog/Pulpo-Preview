#!/usr/bin/env python3
"""Explicit read-only Linux observations; no deployment/enforcement attestation.

Default collection makes no network request. Optional HTTPS-origin HEAD probes
reuse Pulpo's existing trust/redirect/proxy policy in time-bounded children.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import socket
import ssl
import subprocess
import sys
import urllib.error
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request

from pulpo.transport import TransportConfigurationError, _ssl_context, secure_urlopen
from scripts.check_network_exposure import publish_report

LIMIT = 1_048_576
PROXY_NAMES = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
               "http_proxy", "https_proxy", "all_proxy", "no_proxy")
CA_NAMES = ("PULPO_CA_BUNDLE", "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE")


def require(condition):
    if not condition:
        raise ValueError("unrecognized_observation")


def rows(value):
    require(type(value) is list and len(value) <= 512)
    require(all(type(item) is dict for item in value))
    return value


def interfaces(value):
    result = []
    for row in rows(value):
        name = row.get("ifname")
        mtu = row.get("mtu")
        require(type(name) is str and re.fullmatch(r"[^\s/\x00]{1,64}", name))
        require(type(mtu) is int and mtu > 0)
        require(type(row.get("operstate")) is str)
        addresses = []
        for address in rows(row.get("addr_info")):
            family = address.get("family")
            require(family in ("inet", "inet6"))
            parsed = ipaddress.ip_address(address.get("local"))
            require(parsed.version == (4 if family == "inet" else 6))
            prefix = address.get("prefixlen")
            require(type(prefix) is int and 0 <= prefix <= parsed.max_prefixlen)
            require(type(address.get("scope")) is str)
            addresses.append({"address": str(parsed), "prefix": prefix, "scope": address["scope"]})
        info = row.get("linkinfo", {})
        require(type(info) is dict and type(info.get("info_kind", "unspecified")) is str)
        result.append({"name": name, "mtu": mtu, "state": row["operstate"],
                       "kind": info.get("info_kind", "unspecified"), "addresses": addresses})
    return result


def routes(value, version):
    result = []
    for row in rows(value):
        destination = row.get("dst")
        require(type(destination) is str)
        if destination != "default":
            require(ipaddress.ip_network(destination, strict=False).version == version)
        item = {"destination": destination, "type": row.get("type", "unicast"),
                "multipath_present": "nexthops" in row}
        require(type(item["type"]) is str)
        for field in ("dev", "gateway"):
            if field in row:
                require(type(row[field]) is str and 0 < len(row[field]) <= 128)
                if field == "gateway":
                    require(ipaddress.ip_address(row[field]).version == version)
                item[field] = row[field]
        result.append(item)
    return result


def collect_ip(arguments, parser):
    executable = shutil.which("ip", path="/usr/sbin:/usr/bin:/sbin:/bin")
    if executable is None:
        return {"state": "error", "reason": "ip_command_unavailable"}
    try:
        completed = subprocess.run([executable, *arguments], check=True, capture_output=True,
                                   text=True, timeout=5)
        require(len(completed.stdout.encode()) <= LIMIT)
        items = parser(json.loads(completed.stdout))
        return {"state": "observed", "items": items}
    except (OSError, subprocess.SubprocessError, ValueError, TypeError):
        return {"state": "error", "reason": "enumeration_unavailable_or_unrecognized"}


def resolver_observation(path=Path("/etc/resolv.conf")):
    try:
        with path.open("rb") as stream:
            text = stream.read(65_537)
        require(len(text) <= 65_536)
        servers, searches = [], 0
        for raw in text.decode("utf-8").splitlines():
            line = raw.split("#", 1)[0].split(";", 1)[0].split()
            if line and line[0] == "nameserver":
                require(len(line) == 2)
                servers.append(str(ipaddress.ip_address(line[1])))
            elif line and line[0] in ("search", "domain"):
                searches += len(line) - 1
        return {"state": "observed" if servers else "not_configured", "nameservers": servers,
                "search_domain_count": searches, "search_values_redacted": True,
                "reachability": "not_tested", "upstream_resolvers": "not_assessed"}
    except (OSError, ValueError, UnicodeError):
        return {"state": "error", "reason": "resolver_configuration_unavailable_or_unrecognized"}


def trust_observation():
    observation = {"override_variables_present": [name for name in CA_NAMES if os.environ.get(name)],
                   "values_redacted": True, "connectivity": "not_tested"}
    try:
        context = _ssl_context()
        require(context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED)
        observation.update(state="observed", hostname_validation=True, certificate_validation="required",
                           ca_certificates=context.cert_store_stats()["x509_ca"])
    except (OSError, ValueError, ssl.SSLError, TransportConfigurationError):
        observation.update(state="error", reason="existing_transport_trust_configuration_rejected")
    return observation


def validate_origin(value):
    require(type(value) is str and len(value) <= 512 and not any(ord(c) <= 32 or ord(c) >= 127 for c in value))
    parsed = urlsplit(value)
    require(parsed.scheme == "https" and parsed.hostname and parsed.path in ("", "/")
            and not parsed.query and not parsed.fragment and parsed.username is None and parsed.password is None
            and "\\" not in value and "%" not in parsed.hostname)
    host = parsed.hostname
    try:
        ipaddress.ip_address(host)
    except ValueError:
        require(len(host) <= 253 and all(re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", part)
                                       for part in host.split(".")))
    require(parsed.port is None or 1 <= parsed.port <= 65535)
    return urlunsplit(("https", parsed.netloc, "/", "", ""))


def probe_https(origin):
    origin = validate_origin(origin)
    result = {"origin": origin, "state": "error", "tls_verified": False}
    try:
        with secure_urlopen(Request(origin, method="HEAD"), timeout=3) as response:
            result.update(state="https_ok" if 200 <= response.status < 300 else "http_error",
                          tls_verified=True, http_status=response.status)
    except urllib.error.HTTPError as exc:
        result.update(state="redirect_rejected" if 300 <= exc.code < 400 else "http_error",
                      tls_verified=True, http_status=exc.code)
    except (urllib.error.URLError, OSError, TransportConfigurationError) as exc:
        reason = exc.reason if isinstance(exc, urllib.error.URLError) else exc
        if isinstance(reason, ssl.SSLCertVerificationError):
            state = "certificate_rejected"
        elif isinstance(reason, socket.gaierror):
            state = "dns_unavailable"
        elif isinstance(reason, (TimeoutError, socket.timeout)):
            state = "timed_out"
        elif isinstance(reason, ConnectionRefusedError):
            state = "connection_refused"
        elif isinstance(reason, TransportConfigurationError):
            state = "trust_configuration_rejected"
        else:
            state = "transport_unavailable"
        result["state"] = state
    return result


def bounded_probe(origin):
    origin = validate_origin(origin)
    try:
        completed = subprocess.run([sys.executable, "-m", "scripts.check_linux_network_readiness",
            "--probe-worker", origin], check=True, capture_output=True, text=True, timeout=8,
            cwd=Path(__file__).resolve().parents[1])
        require(len(completed.stdout) <= 4096)
        report = json.loads(completed.stdout)
        require(type(report) is dict and report.get("origin") == origin and type(report.get("tls_verified")) is bool
                and report.get("state") in {"https_ok", "redirect_rejected", "http_error", "certificate_rejected",
                    "dns_unavailable", "timed_out", "connection_refused", "trust_configuration_rejected", "transport_unavailable"})
        tls = report["state"] in {"https_ok", "redirect_rejected", "http_error"}
        require(set(report) == {"origin", "state", "tls_verified"} | ({"http_status"} if tls else set())
                and report["tls_verified"] == tls)
        if tls:
            require(type(report["http_status"]) is int and 100 <= report["http_status"] <= 599)
            if report["state"] == "https_ok":
                require(200 <= report["http_status"] < 300)
        return report
    except subprocess.TimeoutExpired:
        return {"origin": origin, "state": "timed_out", "tls_verified": False}
    except (OSError, ValueError, subprocess.SubprocessError):
        return {"origin": origin, "state": "probe_result_unavailable", "tls_verified": False}


def collect():
    return {"schema": "pulpo.linux-network-readiness.v1", "classification": "Recorded",
        "enforcement": "not_assessed", "routing_scope": "main tables only; policy/VPN routing not proven",
        "checks": {
            "interfaces": collect_ip(["-d", "-j", "address", "show"], interfaces),
            "routes_ipv4": collect_ip(["-j", "-4", "route", "show", "table", "main"], lambda v: routes(v, 4)),
            "routes_ipv6": collect_ip(["-j", "-6", "route", "show", "table", "main"], lambda v: routes(v, 6)),
            "resolver": resolver_observation(), "tls_trust": trust_observation(),
            "proxy": {"state": "observed", "variables_present": [n for n in PROXY_NAMES if os.environ.get(n)],
                      "values_redacted": True, "transport_behavior": "ambient proxies ignored; explicit proxy support unavailable"}},
        "probes": []}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, help="New private diagnostic file; never replaces existing evidence")
    parser.add_argument("--probe", action="append", default=[], metavar="HTTPS_ORIGIN")
    parser.add_argument("--probe-worker", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if not sys.platform.startswith("linux"):
        parser.error("Linux required")
    try:
        require(len(args.probe) <= 4)
        if args.probe_worker:
            print(json.dumps(probe_https(args.probe_worker)))
            return 0
        origins = [validate_origin(value) for value in args.probe]
        report = collect()
        report["probes"] = [bounded_probe(origin) for origin in origins]
        payload = json.dumps(report, sort_keys=True)
        if args.evidence:
            publish_report(args.evidence, payload)
        print(payload)
        if any(check["state"] == "error" for check in report["checks"].values()):
            return 2
        incomplete = any(check["state"] == "not_configured" for check in report["checks"].values())
        return 1 if incomplete or any(p["state"] != "https_ok" for p in report["probes"]) else 0
    except (ValueError, OSError):
        print("pulpo_network_readiness_error: invalid input or report publication failed", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
