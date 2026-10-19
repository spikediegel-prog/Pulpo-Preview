# Connections and opt-in provider read collectors

Status: **Recorded implementation and fixture tests; live compatibility Unknown.**
Reference UDM target supplied by the operator: UniFi OS 5.1.33 and Network
10.6.106. These are compatibility targets, not measured installed versions.

## Architecture and first-run behavior

`ConnectionsPage` imports only the capability-free observation contract. It
selects/re-reads a manually supplied owner-private JSON export using the existing
protected snapshot reader. The UI has no provider credentials, HTTP client,
kernel, executor, orchestrator, canonical writer or service-management client.
No startup discovery, network scan, account login or automatic collector runs.

The separate `python -m pulpo.connection_collector` command is a trusted-owner
operation, not an agent/provider tool or an automatically launched GUI worker.
It performs explicit HTTPS reads, optionally issues an OAuth client-credentials
token, discards private response fields, and atomically publishes only validated
enums, a source fingerprint, observation time and bounded returned-record counts.
It reuses the existing `_publish_snapshot` primitive; no new durable audit source
or canonical state mutation interface is created.

Reachability, authentication and enforcement remain separate. A valid completed
read is source-reported HTTP Responded/Auth Accepted, while enforcement stays
unassessed. Read permissions describe only completed requests; the UI does not
infer that the credential has no write privileges. Provenance is not authenticated
by selecting an export or seeing a recent timestamp. Rows stay gray for
unassessed governance; reported errors, invalid files and stale data need review.

The UI keeps one selected observation per provider, not a multi-tenant inventory.
After 60 seconds a sample is historical. No source file is polled: the active-page
timer updates age labels only. Wrong-provider, future-clock, malformed and
in-session out-of-order/substituted observations clear previous metrics. The
ordering check is UI bookkeeping, not cryptographic replay protection. Clear
selection does not disconnect a provider. Copy omits selected file paths and
credentials. Source/collection transitions appear under Connections in Activity.

## Implemented provider reads

| Provider | Authentication and fixed calls | Exported metrics |
| --- | --- | --- |
| UniFi UDM | `X-API-KEY`; GET `/proxy/network/integration/v1/sites/{siteId}/devices` and `/clients`, offset 0, limit 100 | Returned device count, ONLINE count within that page, returned connected-client count |
| NinjaOne | POST `/ws/oauth/token`, `client_credentials`, explicit `scope=monitoring`; GET `/v2/devices?pageSize=100`, GET `/v2/alerts` | Returned device count and active-alert record count |
| CrowdStrike | POST `/oauth2/token`, `client_credentials`; GET `/devices/queries/devices/v1?limit=100&offset=0` and `/alerts/queries/alerts/v2?limit=100&offset=0` | Returned host-ID and alert-ID counts; no claim these are open-alert totals |

All displayed counts describe returned records, not fleet totals or complete
history. No automatic pagination. NinjaOne alert arrays over 200 are rejected;
device/client/host/alert-ID pages over 100 are rejected. Payloads over 1 MiB,
redirects, compressed bodies, duplicate JSON keys, non-finite numbers, unsupported
formats and partial failures produce a sanitized failure report with all metrics
Unknown. Missing data never becomes zero. Raw names, IPs, MACs, host IDs, alert
payloads, tokens and error bodies are not exported. A fingerprint is a stable
hash of configured source identifiers, not a secret or proof of source identity.

HTTP 401 is authentication rejection; 403 is missing access/entitlement with
authentication unassessed; 429 is rate limiting. Certificate validation, timeout,
unavailability and response failures have separate fixed troubleshooting text.
No automatic retries or fallback endpoints. TLS validation is always on, proxies
are not inherited, and each collection checks a 20-second elapsed budget between
operations/reads with at most five seconds per socket wait. This is not a hard
wall-clock bound on DNS, TLS/header processing or a stalled OS; no RAM sandbox or
host containment is claimed. The operator can terminate the standalone process.

## Owner configuration and activation

Use existing dedicated least-privilege provider credentials. Provider-side grant
configuration must be checked by the trusted operator: a fixed-read implementation
does not strip excess privileges from an over-scoped secret. No real credentials
were accessed, created, copied, enrolled or activated during this change. Keep
secrets out of the repository, snapshots, screenshots, chat and command arguments.
Only the explicit CLI reads these environment variable names:

- UniFi: `PULPO_UNIFI_API_KEY`.
- NinjaOne: `PULPO_NINJAONE_CLIENT_ID`, `PULPO_NINJAONE_CLIENT_SECRET`; request
  monitoring only, without management/control permissions.
- CrowdStrike: `PULPO_CROWDSTRIKE_CLIENT_ID`, `PULPO_CROWDSTRIKE_CLIENT_SECRET`;
  configure Hosts READ and Alerts READ for the intended cloud/tenant.

UDM requires an explicitly selected site UUID from the official List Local Sites
API. This initial transport accepts private numeric RFC1918/ULA addresses on
HTTPS port 443 only; public, loopback and link-local addresses are rejected. The
certificate must validate for that IP, including the IP subject alternative name.
An explicit trusted CA file is supported; an untrusted/self-signed or name-mismatch
failure is not bypassed. Hostname-based UDM configuration and Site Manager are
outside this increment. Consult the installed Network application's Integrations
documentation to obtain the site UUID and confirm the API key's effective role.

Cloud origins are explicit allowlisted provider hosts in `connection_collector.py`.
No arbitrary external URL, token endpoint, filter, query or command can be supplied
through the UI or CLI. Select the correct regional host before live testing.

Example invocation shapes (operator supplies their actual origin, site, CA and
absolute output location; examples are not run automatically):

```text
python -m pulpo.connection_collector unifi --origin https://192.168.1.1 --site-id SITE_UUID --ca-file TRUSTED_CA.pem --output /absolute/private/unifi-observation.json
python -m pulpo.connection_collector ninjaone --origin https://app.ninjarmm.com --output /absolute/private/ninjaone-observation.json
python -m pulpo.connection_collector crowdstrike --origin https://api.crowdstrike.com --output /absolute/private/falcon-observation.json
```

The parent directory must exist. The existing publisher applies its protected
atomic file rules; POSIX observations must be owner-private. Set appropriate
Windows directory ACLs separately. Select the resulting file in its Connections
row. Read collection failures still publish a sanitized failure report; exit 1
means collection failed, exit 2 means publication failed. A publication failure
can leave the previous file in place, so inspect collector exit status and the
sample timestamp. No claim that live UDM, NinjaOne or Falcon access already works.

WAN telemetry, patch posture, sensor-health details, event streams, account
discovery, automatic refresh and remediation are deferred. There are no device
adoption/reboot, host-containment, remote-script, firewall or patch-deployment calls.

## Source references

- [Official UniFi 10.6.106 OpenAPI](https://developer.ui.com/network/v10.6.106/openapi.json)
  supplies the local console server prefix and paginated read schemas.
- [NinjaOne core OpenAPI](https://app.ninjaone.com/apidocs/NinjaRMM-API-v2.json)
  and [authorization schema](https://app.ninjaone.com/apidocs/authorization.json)
  supply the device/alert routes, token flow and monitoring scope.
- [CrowdStrike Hosts](https://developer.crowdstrike.com/api-reference/collections/hosts/)
  and [Alerts](https://developer.crowdstrike.com/api-reference/collections/alerts/)
  document the read queries and scopes. No legacy Detects fallback.

## Required change record and eight-pass review

Purpose: inspect selected provider observations without making Connections an
execution or credential-custody surface. Exact requested outcome: native
Connections plus first read collectors for NinjaOne, CrowdStrike and the specified
UDM reference versions. New capability: explicit provider HTTPS reads and OAuth
token issuance in the trusted owner CLI. UI and consequential Pulpo authority
remain unchanged. No canonical mutation is introduced or exposed. Local effects
are explicit private observation publication and ephemeral UI selection/copy.

| Pass | Analysis and boundary |
| --- | --- |
| Flip | A hostile UI/export cannot supply a URL, credential, command or a Verified flag. Credentials stay in the owner process, whose compromise remains a trust assumption. Over-scoped credentials require provider-side correction. |
| Reverse | Provider effects would require write endpoints or broader credential use. Collector routes are fixed reads plus token issuance; no UI client exists. No canonical writer is available. |
| Invert | A reachable HTTP endpoint or token does not establish successful collection, correctness of data, host identity beyond TLS assumptions, or enforcement. Partial results are discarded. |
| Inside-Out | Provider reports and local fingerprints do not authenticate themselves. OAuth success does not grant Pulpo policy/permit authority. Frozen exports are not a second audit truth source. |
| Darken | Threat case: redirected/slow/oversized/sensitive responses. Reject redirects/compression, bound bodies/arrays, sanitize failure codes, check deadlines and export only public fields; no hard OS containment claim. |
| Lighten | Missing permissions or stale observations can be benign configuration/collection problems. Unknown is not zero, offline, incident resolution or authorization to retry effects. |
| Amplify | At most three fixed sequential calls per collection; no retries, automatic pagination or UI polling. Counts are bounded samples, not fleet coverage. Repeated UI re-read does not append duplicate unchanged reports. |
| Negate | Keep credentials/network reads in the explicit owner collector and reuse the existing private snapshot reader/publisher; no SDK framework, background service, alternate executor or kernel route is needed. |

Evidence and limits: [review artifacts](control-center-evidence/connections/README.md)
record fixtures, native inspection and regression logs. Claims are Recorded
implementation/test observations; real account connectivity, read-role setup,
OS 5.1.33 device behavior, production readiness and enforcement remain Unknown.
No reusable historical lesson or temporal-transfer proof is admitted. Existing
reader/publisher, StatusRow, navigation and Activity are reused without copying
kernel control paths. Before inspection is at base
`41d7bab56d0c0c46d55efffc2844f813196db992`, not a replay of authority or credentials.
Continue only within the described observation boundaries; separate governed
design/authorization would be required for consequential provider actions.
