"""Opt-in trusted-owner collectors. Never import this module into the UI.

Fixed HTTPS reads only; OAuth token issuance is the only POST. No kernel,
canonical store, remediation, model inference, retries or background service.
"""
from dataclasses import replace
from hashlib import sha256
import http.client
import ipaddress
import json
import os
import re
import socket
import ssl
import time
from urllib.parse import urlencode, urlsplit
from uuid import UUID

from .connection_observation import ConnectionObservation


NINJA_HOSTS = ("app.ninjarmm.com", "app.ninjaone.com", "eu.ninjarmm.com", "oc.ninjarmm.com")
FALCON_HOSTS = ("api.crowdstrike.com", "api.us-2.crowdstrike.com", "api.eu-1.crowdstrike.com",
                "api.laggar.gcw.crowdstrike.com", "api.us-gov-2.crowdstrike.mil")
MAX_BYTES = 1024 * 1024


class CollectionError(ValueError):
    def __init__(self, reason, responded=False):
        self.reason, self.responded = reason, responded
        super().__init__(reason)  # Never include a URL, header or response body.


def _text(value):
    if type(value) is not str or not 1 <= len(value) <= 4096 or any(ord(c) < 33 or ord(c) > 126 for c in value):
        raise CollectionError("configuration")
    return value


def _origin(provider, origin):
    parsed = urlsplit(_text(origin))
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
        raise CollectionError("configuration")
    try:
        if provider == "UniFi UDM":
            ip = ipaddress.ip_address(parsed.hostname)
            networks = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7")
            if not any(ip in ipaddress.ip_network(n) for n in networks):
                raise CollectionError("configuration")
            if parsed.port not in (None, 443): raise CollectionError("configuration")
        elif parsed.hostname not in (NINJA_HOSTS if provider == "NinjaOne" else FALCON_HOSTS) or parsed.port not in (None, 443):
            raise CollectionError("configuration")
    except (ValueError, TypeError):
        raise CollectionError("configuration") from None
    return parsed.hostname


def _pairs(items):
    value = {}
    for key, item in items:
        if key in value: raise CollectionError("response", True)
        value[key] = item
    return value


def _request(host, path, context, *, token=None, api_key=None, form=None, deadline):
    # Internal fixed-route guard also rejects query/path substitution.
    unifi = re.fullmatch(r"/proxy/network/integration/v1/sites/[0-9a-f-]{36}/(?:devices|clients)\?offset=0&limit=100", path)
    reads = ("/v2/devices?pageSize=100", "/v2/alerts", "/devices/queries/devices/v1?limit=100&offset=0",
             "/alerts/queries/alerts/v2?limit=100&offset=0")
    if form is not None:
        if path not in ("/ws/oauth/token", "/oauth2/token") or token or api_key:
            raise CollectionError("configuration")
    elif path not in reads and not unifi:
        raise CollectionError("configuration")
    remaining = deadline - time.monotonic()
    if remaining <= 0: raise CollectionError("timeout")
    headers = {"Accept": "application/json", "Accept-Encoding": "identity"}
    if token: headers["Authorization"] = "Bearer " + _text(token)
    if api_key: headers["X-API-KEY"] = _text(api_key)
    body = urlencode(form).encode() if form is not None else None
    if form is not None: headers["Content-Type"] = "application/x-www-form-urlencoded"
    connection = http.client.HTTPSConnection(host, timeout=min(5, remaining), context=context)
    try:
        connection.request("POST" if form is not None else "GET", path, body=body, headers=headers)
        response = connection.getresponse()
        if response.status != 200:
            reason = {401: "authentication", 403: "permission", 429: "rate_limit"}.get(response.status, "response")
            if form is not None and response.status == 400: reason = "authentication"
            raise CollectionError(reason, True)
        if response.getheader("Content-Encoding", "identity").lower() != "identity": raise CollectionError("response", True)
        if response.getheader("Content-Type", "").split(";")[0].strip().lower() != "application/json":
            raise CollectionError("response", True)
        raw = bytearray()
        while True:
            if time.monotonic() >= deadline: raise CollectionError("timeout", True)
            # Refresh read timeout too: a slow trickle cannot reset a whole collection budget.
            if connection.sock: connection.sock.settimeout(max(.001, min(5, deadline - time.monotonic())))
            block = response.read1(min(65536, MAX_BYTES + 1 - len(raw)))
            if not block: break
            raw.extend(block)
            if len(raw) > MAX_BYTES: raise CollectionError("response", True)
        if time.monotonic() >= deadline: raise CollectionError("timeout", True)
        try:
            return json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                parse_constant=lambda value: (_ for _ in ()).throw(CollectionError("response", True)))
        except (ValueError, UnicodeError, RecursionError):
            raise CollectionError("response", True) from None
    except ssl.SSLError:
        raise CollectionError("tls") from None
    except (TimeoutError, socket.timeout):
        raise CollectionError("timeout") from None
    except (OSError, http.client.HTTPException):
        raise CollectionError("unavailable") from None
    finally:
        connection.close()


def _list(value, *, key=None, limit=200):
    if key is not None:
        if type(value) is not dict or value.get("errors") or key not in value: raise CollectionError("response", True)
        value = value[key]
    if type(value) is not list or len(value) > limit: raise CollectionError("response", True)
    return value


def _unifi_page(value):
    rows = _list(value, key="data", limit=100)
    if (any(type(row) is not dict for row in rows) or type(value.get("count")) is not int or value["count"] != len(rows)
            or value.get("offset") != 0 or type(value.get("offset")) is not int
            or type(value.get("totalCount")) is not int or value["totalCount"] < len(rows)):
        raise CollectionError("response", True)
    return rows


def collect(provider, origin, *, api_key=None, site_id=None, client_id=None, client_secret=None, ca_file=None):
    """One explicit collection; return only public enums and bounded counts.

    Caller owns provider credentials. Export says nothing about credential
    write scopes, daemon identity, installed versions or Pulpo enforcement.
    """
    observation = ConnectionObservation(provider, time.time_ns())
    try:
        host = _origin(provider, origin)
        if provider == "UniFi UDM":
            try:
                if str(UUID(site_id)) != site_id: raise ValueError()
            except (ValueError, TypeError, AttributeError):
                raise CollectionError("configuration") from None
            _text(api_key)
        else:
            _text(client_id)
            _text(client_secret)
        source = sha256((provider + "|" + origin + "|" + (site_id or "") + "|" + (client_id or "")).encode()).hexdigest()[:32]
        observation = replace(observation, source_id=source)
        context = ssl.create_default_context(cafile=ca_file)
        deadline = time.monotonic() + 20
        request = lambda path, **kwargs: _request(host, path, context, deadline=deadline, **kwargs)
        if provider == "UniFi UDM":
            prefix = f"/proxy/network/integration/v1/sites/{site_id}"
            devices = _unifi_page(request(prefix + "/devices?offset=0&limit=100", api_key=api_key))
            clients = _unifi_page(request(prefix + "/clients?offset=0&limit=100", api_key=api_key))
            states = {"ONLINE", "OFFLINE", "PENDING_ADOPTION", "UPDATING", "GETTING_READY", "ADOPTING", "DELETING", "CONNECTION_INTERRUPTED", "ISOLATED", "U5G_INCORRECT_TOPOLOGY"}
            if any(row.get("state") not in states for row in devices): raise CollectionError("response", True)
            metrics = dict(devices_seen=len(devices), online_seen=sum(d["state"] == "ONLINE" for d in devices), clients_seen=len(clients))
        else:
            form = {"grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret}
            if provider == "NinjaOne": form["scope"] = "monitoring"
            auth = request("/ws/oauth/token" if provider == "NinjaOne" else "/oauth2/token", form=form)
            if type(auth) is not dict or type(auth.get("token_type")) is not str or auth["token_type"].lower() != "bearer": raise CollectionError("response", True)
            token = _text(auth.get("access_token"))
            if provider == "NinjaOne":
                devices = _list(request("/v2/devices?pageSize=100", token=token), limit=100)
                alerts = _list(request("/v2/alerts", token=token))
                if any(type(row) is not dict for row in devices + alerts): raise CollectionError("response", True)
            else:
                devices = _list(request("/devices/queries/devices/v1?limit=100&offset=0", token=token), key="resources", limit=100)
                alerts = _list(request("/alerts/queries/alerts/v2?limit=100&offset=0", token=token), key="resources", limit=100)
                if any(type(row) is not str or not row for row in devices + alerts): raise CollectionError("response", True)
            metrics = dict(devices_seen=len(devices), alerts_seen=len(alerts))
        return replace(observation, observed_at_ns=time.time_ns(), reachability="Responded", authentication="Accepted", reason="ok", **metrics)
    except CollectionError as error:
        return replace(observation, observed_at_ns=time.time_ns(), reason=error.reason,
            reachability="Responded" if error.responded else "Unavailable" if error.reason == "unavailable" else "Unknown",
            authentication="Rejected" if error.reason == "authentication" else "Unknown")
    except (ValueError, TypeError, OSError):
        return replace(observation, observed_at_ns=time.time_ns(), reason="configuration")


def main(argv=None):
    import argparse
    from pathlib import Path
    from .mcp_boundary import _publish_snapshot
    parser = argparse.ArgumentParser(description="Explicit trusted-owner read collector; no provider changes or retries.")
    parser.add_argument("provider", choices=("unifi", "ninjaone", "crowdstrike"))
    parser.add_argument("--origin", required=True, help="Exact HTTPS origin; UDM requires a private numeric IP and trusted TLS")
    parser.add_argument("--site-id", help="UniFi site UUID from the official List Local Sites API")
    parser.add_argument("--ca-file", type=Path, help="Explicit trusted certificate authority file, never a TLS bypass")
    parser.add_argument("--output", required=True, type=Path, help="Absolute owner-private observation destination")
    args = parser.parse_args(argv)
    if not args.output.is_absolute() or not args.output.parent.is_dir():
        parser.error("--output must be absolute with an existing parent directory")
    provider = {"unifi": "UniFi UDM", "ninjaone": "NinjaOne", "crowdstrike": "CrowdStrike"}[args.provider]
    prefix = {"unifi": "PULPO_UNIFI", "ninjaone": "PULPO_NINJAONE", "crowdstrike": "PULPO_CROWDSTRIKE"}[args.provider]
    result = collect(provider, args.origin, site_id=args.site_id, ca_file=args.ca_file,
        api_key=os.environ.get(prefix + "_API_KEY"), client_id=os.environ.get(prefix + "_CLIENT_ID"), client_secret=os.environ.get(prefix + "_CLIENT_SECRET"))
    try:
        _publish_snapshot(result, args.output)
    except (OSError, ValueError, RuntimeError):
        print("Observation publication failed; inspect destination access. No contents logged.")
        return 2
    print(f"{provider}: {result.reason}; source-reported read observation only; enforcement Unknown.")
    return 0 if result.reason == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
