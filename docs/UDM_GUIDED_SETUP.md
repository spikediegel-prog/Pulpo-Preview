# Guided UDM setup

Status: **Recorded implementation and fixture validation. Live API compatibility,
credential permissions and enforcement remain Unknown.** Reference target supplied
by the operator: UniFi OS 5.1.33 / Network 10.6.106, not observed installed versions.

Open **Connections → Guided UDM setup…**. The existing charcoal navigation,
restrained purple accents and soft white content remain in place. The guide is
incremental: it uses existing observation selection and protected JSON file
publication, with no replacement of the Control Center or provider APIs.

## Four steps

1. **Trust.** Confirm the private HTTPS address. The displayed address is an
   example, not a discovered device. System certificate verification must succeed,
   or select a public CA certificate obtained through a known trusted management
   process. The certificate must match the private IP, including its IP subject
   alternative name. This version does not accept DNS hostnames. Do not select
   private keys, trust a certificate solely because the unverified peer supplied
   it, install trust through this guide, or disable verification. If no trusted
   management path exists, stop live collection and establish one separately.
2. **Find site.** Choose an absolute site-report output path in an existing private
   directory. Review and save the non-secret setup file, then copy its collector
   command. Run it separately in the same Windows or Linux environment with the
   existing `PULPO_UNIFI_API_KEY` configured only on the trusted collector side.
   The new fixed GET reads the first local-sites page (offset 0, limit 100). It
   exports canonical UUIDs, a timestamp, configured-origin fingerprint and a
   more-pages indicator; site names and raw responses are discarded. Load that
   report and explicitly choose a UUID. Nothing is selected automatically.
3. **Collect.** Use the chosen UUID or one already known through trusted management.
   Choose a different absolute inventory output path, review/save another setup
   file, and run its copied command separately. Existing bounded device/client
   collection is unchanged. The guide does not run commands or receive API keys.
4. **Review.** Select the resulting inventory observation through the existing UDM
   row. Inspect age, authentication, returned-page coverage and reported failure.
   Successful reads do not verify governance enforcement or credential scope.

Site reports expire after 15 minutes (future clock tolerance five seconds).
Malformed, expired or wrong-origin reports clear the previous site choice. A
loaded choice cannot be used after changing the configured origin without loading
a matching report again. These are local consistency checks, not authenticated
provenance or cryptographic replay protection. A manual known UUID remains an
explicit operator choice.

## Non-secret handoff and CLI

The strict `pulpo.udm-setup.v1` document accepts only `origin`, `mode`, `output`,
`ca_file`, `site_id`, and `schema`. Extra fields, including credentials, are
rejected. Absolute paths are specific to the environment where they were saved.
The file is configuration, not approval, a permit, a signed command or evidence
that a connection was made. Review its exact contents before running the collector.
Changes to fields require saving again before the guide copies another command.

The guide copies single-quoted PowerShell syntax on Windows and POSIX-shell syntax
on Linux. Paths with control characters or typographic quote characters cannot
be copied as commands. No shell is invoked by the UI.

```text
python -m pulpo.connection_collector unifi --setup-profile ABSOLUTE_SETUP_FILE
```

Existing explicit CLI options remain supported. Site discovery can also be invoked
explicitly using `unifi --origin HTTPS_ORIGIN --discover-sites --output ABSOLUTE_OUTPUT`
with `--ca-file TRUSTED_PUBLIC_CA_FILE` when needed. A setup profile cannot be mixed
with these options or used with another provider. Output cannot overwrite the
selected setup or CA file. Existing protected-reader/publisher rules apply; choose
owner-private directories, with appropriate Windows ACLs set separately.

Failure exports use the existing sanitized observation schema. Inspect process
exit status and timestamps: discovery failure is not an empty valid site list, and
publication failure may leave an older file. Exit 1 means collection failed;
exit 2 means publication failed. No retries, redirects or fallback endpoints.

## Recorded live boundary

An explicit unauthenticated Windows TLS check against the operator-supplied UDM
address on 2026-10-19 returned `certificate_validation_failed`. Verification was
enabled. The failure occurred during the handshake, before any HTTP API request
or credential was sent. The operator has no trusted CA file or known site UUID.
No certificate was auto-trusted or fetched through a verification bypass. This
result does not establish a cause beyond certificate validation failure, API
availability, account entitlement, installed version, or successful compatibility.
The local full result is retained outside the repository; public evidence omits
the operator's address. Next proof: after independent certificate trust and the
existing key are configured by the operator, explicitly discover sites and collect
one bounded inventory observation.

## Authority and adversarial change record

Purpose/outcome: reduce first-run UDM setup mistakes while keeping provider clients
and credentials outside the UI. Authority boundary: the guide creates only explicit
local configuration files; the separate trusted-owner collector performs bounded
reads after an operator runs it. No canonical Pulpo writer, permit transition,
kernel, executor, signing material or second ledger/router is introduced.

| Pass | Review and boundary |
| --- | --- |
| Flip | Hostile setup/report fields cannot add credentials, routes, commands or provider options; strict schemas and origin validation reject substitution. A dishonest local export can still lie about its source; provenance is labeled unverified. |
| Reverse | To alter network settings, a mutation route/client would be needed. The guide has no provider client or command runner; the collector route guard accepts only its fixed reads. Saving local setup is not canonical state mutation. |
| Invert | A returned page is source-reported data, never enforcement verification. Certificate failure is preserved rather than converted into a successful connection by disabling TLS. |
| Inside-Out | Pulpo cannot self-ratify CA trust, provider grants or exported provenance. The operator separately establishes trust and effective read permissions; configured-origin hashing proves neither identity nor permissions. |
| Darken | Bounded threat: an operator could run a collector with an over-scoped key or import a forged local report. Fixed reads narrow implementation behavior, not the secret's external authority; no broad entitlement or authenticated-export claim is made. |
| Lighten | The observed TLS failure may be an ordinary trust/name configuration issue. It does not prove compromise or that the API is unavailable. |
| Amplify | One site page, at most 100 unique UUIDs and 1 MiB, checked timeout budget, no retries/pagination/background polling. Invalid report imports clear choices; stale/changed handoffs cannot silently become a new copied command. |
| Negate | Reuse protected files and explicit operator execution. No SDK, key field, TLS bypass, embedded terminal, privileged service or second authority plane is necessary. |

Required record:

1. Invariant addressed: connected is distinct from governed; guided setup must not
   import provider credentials or execution capability into the UI.
2. Authority: no UI authority gained. The trusted-owner CLI gains one explicitly
   requested fixed site-list GET; its existing credential and network boundary
   remains separate. No real credential was accessed or activated during testing.
3. Canonical mutations: none. Local setup/report publication uses the existing
   atomic private file primitive and is not a canonical audit source.
4. Success/adversarial evidence: [native screenshots, focused/core test logs and
   source hashes](control-center-evidence/udm-setup/README.md), including malformed
   fields, credential fields, option mixing, output clobber, stale reports,
   wrong-origin imports, explicit UUID selection and safe command quoting.
5. Limits: no authenticated live collection, actual provider grant validation,
   production readiness, accessibility certification or governance enforcement.
6. Claims: Recorded implementation/tests/TLS result; live compatibility and
   enforcement Unknown. Threat cases are analytical, not observed incidents.
7. Legacy behavior reused: existing Connections observation selection, protected
   reader/publisher and bounded collector transport, without kernel control paths.
8. Temporal transfer: no material reusable lesson is admitted here; historical
   replay was not performed and no temporal-transfer proof is claimed.

Decision: continue local guide/testing/review; stop live API validation at the
unresolved trust boundary. Remaining unknowns: trusted certificate/IP match, site
UUID, effective API-key grants, installed-version behavior and live returned data.

Reference: the official [Network 10.6.106 List Local Sites API](https://developer.ui.com/network/v10.6.106/getsiteoverviewpage)
defines the paginated UUID-bearing site list. See [existing connector transport
scope](CONNECTION_CONNECTORS.md) for TLS, body limits and timeout caveats.
