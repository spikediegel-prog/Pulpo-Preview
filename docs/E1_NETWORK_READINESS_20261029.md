# E1 Linux enterprise network observations

Classification: Verified bounded fixture behavior; Recorded host configuration.
No deployment-readiness or governance-enforcement attestation is produced.
Parent checkpoint: 017b67c651af7ea51a1c1866e45d0e31225b4090.

## Failure/invariant and smallest change

The existing inbound-listener proof does not describe interface/address state,
main routing tables, resolver configuration, ambient proxy behavior or TLS trust
setup. Add an explicit operator CLI for those observations, with no background
discovery, UI network access, automatic repair or change to enforcement policy.
Unknown/malformed observations are errors, not empty success. Missing network
information must not become governance or enterprise-readiness approval.

Run from the Preview checkout using its Python environment:

    python -m scripts.check_linux_network_readiness

This default makes no network requests, including no DNS query. It reads local
iproute JSON, bounded resolver configuration and the existing transport's public
CA trust setup. Interfaces retain address family, scope, prefix, state, MTU and
reported link kind. Route coverage is explicitly limited to main IPv4/IPv6 tables;
policy routing, route metrics, multipath details and VPN reachability are not
established. A resolver entry is configuration, not evidence of successful DNS.
The resolver file may name a local stub; upstream resolvers remain not_assessed.

An optional --probe HTTPS_ORIGIN sends one direct HEAD request through the
existing pulpo.transport policy. At most four origins are accepted. Only HTTPS
origins without credentials, query, fragment or non-root path are allowed.
Ambient proxies are ignored by that transport; no explicit enterprise proxy
implementation is added. Each probe runs in a child with an 8-second total
timeout, covering resolver hangs as well as connection/TLS work. Each local ip
command has a 5-second timeout and output/row acceptance limits. Successful
collection does not promise a global deadline for public CA/file I/O.

Probes distinguish verified HTTPS response, HTTP error, redirect rejection,
certificate rejection, DNS failure, timeout, refused connection, rejected trust
configuration and unavailable transport/result. Redirects remain blocked and
hostname/certificate verification remains required. Child-output origin, status,
TLS flag and HTTP-code consistency are checked; substituted/malformed success
results do not pass. No TLS verification bypass or direct-route fallback is
added to the existing transport.

--evidence NEW_ABSOLUTE_FILE uses the existing create-only private diagnostic
publisher. Existing regular files and links are preserved; failed/uncertain
publication returns an error before success stdout. Reports contain no proxy
values, credentials, CA override paths or resolver search-domain values. They
do contain local interface/IP/route observations, so treat them as private
operational diagnostics. No canonical database, permit or signing material is
opened, copied or exported.

Exit 0 means collection completed and any explicitly requested probes received
successful HTTPS responses. Exit 1 marks an unconfigured resolver or unsuccessful
probe. Exit 2 marks input, collection, trust-configuration or publication error.
Exit 0 never means enterprise deployment readiness or governance enforcement;
enforcement is always not_assessed and the scope/unknowns remain in the report.
IPv6 absence is an observation, not a blanket failure of an IPv4-only deployment.

## Verified tests and VM observations

50 targeted tests passed, including 18 new tests. Existing listener, report
publication, transport security and GitHub transport suites also passed. The new cases cover
malformed/mixed inventory, unsupported enumeration/timeout, route-family
mismatch, multipath presence, resolver uncertainty, redaction of proxy secrets
and CA paths, origin rejection, no default probes, prior-report preservation,
child timeout/substitution and the actual bounded child execution path.

Disposable HTTPS fixtures exercise real certificate/hostname validation over
IPv4 and IPv6 loopback. An untrusted certificate and a trusted certificate with
the wrong hostname are rejected. An explicitly configured public fixture CA
permits the matching localhost certificate. The fixture's temporary TLS server
key is not a human/governance signing credential and is removed with its private
temporary directory. Redirect rejection is checked with a resolver guard which
would fail if a second destination were contacted. A bound non-listening local
port gives a real refused connection. DNS unavailability is injected at
socket.getaddrinfo through the real transport; no live DNS daemon was stopped.
Child total-timeout handling is tested by a subprocess timeout fixture. No
external endpoint is contacted by these tests.

Recorded on the Ubuntu development VM: eth0 is UP with MTU 1500,
192.168.250.10/24 and link-local IPv6. IPv4 has default gateway 192.168.250.1;
the main IPv6 table has only a link-local route and no default route. The
collector sees the local 127.0.0.53 resolver stub and deliberately leaves DNS
reachability/upstream assessment unknown. Separate read-only resolvectl output
reported 1.1.1.1 and 9.9.9.9 as upstream configuration, not reachability proof.
No proxy/CA override variables were present in the collector's environment.
The existing TLS context observed 120 public CA certificates with required
certificate and hostname checks. No HTTP/DNS connectivity probe was requested
for the host inventory. No live VLAN or VPN compatibility claim is made.

No DNS, route, interface, firewall, proxy, certificate-store or system-service
setting changed. Tests close their loopback listeners and remove TLS fixtures.
The prior service sandbox profile remains unchanged. Control Center source and
its public observation/export schemas are unchanged; it gains no background
network discovery or canonical capability. No push, merge, release or production
operation occurred. The raw reports, test log and exact commit patch are retained
as local evidence; post-commit output is tied to exact source hashes separately.

## Authority/capability record and eight-pass review

Authority unchanged; canonical mutations introduced/exposed: none. Local JSON
reports are host diagnostics, not a second canonical audit source. Active probes
require explicit operator origin arguments and reuse the existing direct HTTPS
transport. Only caller-selected diagnostic publication writes a report. There
is no repair, authority signer, provider action or new approval/execution path.

- Flip: malformed/hostile enumeration and proxy variables cannot silently
  become readiness or authority; values are redacted and observations bounded.
- Reverse: reject unsafe origins before collection/probing, and reject unknown
  collection/child output before accepting a success result.
- Invert: collection success, TLS connectivity and governance enforcement are
  separate facts. Missing data and expected negative fixtures retain their labels.
- Inside-Out: treat the host and probe output as fallible sources; test the
  diagnostic's own error handling and result consistency.
- Darken: missing commands, malformed JSON, DNS failure, invalid certificates,
  refused ports, redirects, timeouts and report collisions fail visibly.
- Lighten: legitimate segmented/IPv4-only deployments or a local DNS stub can
  explain incomplete observations without implying compromise.
- Amplify: cap explicit origins, bound child lifetime, keep evidence create-only
  and never turn repeated failures into permission to bypass TLS or routing.
- Negate: observe local configuration and use disposable loopback fixtures;
  no network reconfiguration, privileged scanner or new proxy route is necessary.

Legacy sources: existing pulpo.transport trust policy and private diagnostic
publisher only; neither control path is copied or replaced. The exact parent
has listener/transport proofs but no host readiness collector checkpoint. No
whole-system temporal transfer or generally reusable organizational-learning
claim is made; no historical authority travels into these observations.

Remaining Unknown/Proposed: production readiness, actual enterprise proxy
support, customer CA rollout and certificate lifecycle, external DNS/HTTPS
reachability, IPv6 default routing, VLAN/VPN/policy-routing behavior and network
segmentation acceptance. These require separate explicit configuration and
deployment tests. This slice adds diagnostics, not those integrations.

## TLS secret-logging boundary found during read-only review

Verified baseline at collector commit 2b60e2a7e58695545f8f5781531bda2918f3c68c:
Python's installed ssl.create_default_context reads SSLKEYLOGFILE and assigns
keylog_filename. In a disposable no-traffic fixture, Pulpo's existing
_ssl_context created a 54-byte log header simply by constructing the context.
No handshake, actual session secret or provider traffic was involved. The file
was removed with the test directory; the baseline JSON is retained. This was
not evidence of prior live credential exposure.

The shared existing transport now rejects a nonempty SSLKEYLOGFILE before
calling ssl.create_default_context, and sanitized_transport_environment removes
that variable. The readiness inventory reports only its presence, never its
value/path. Diagnostic trust evaluation and probes therefore reject that
configuration without opening a log or contacting a destination. There is no
new logging, key export or opt-in bypass. Other trust/proxy/redirect behavior
remains in its existing control path; ordinary matching-CA HTTPS still passes
the real IPv4/IPv6 loopback and bounded-child fixtures.

Authority/capability delta: the ambient TLS secret-export path is narrowed;
no authority is gained and no canonical-state mutation is introduced. This
shared transport check applies to callers on other platforms too, but native
verification here is Ubuntu only. The successful test predicates include no
context constructor call, no resolver call, no key-log file, redacted output,
and removal of the directive from sanitized child environments.

Eight-pass reconciliation: Flip/Inside-Out treat ambient process variables and
the diagnostic's own library initialization as capable of side effects;
Reverse rejects before context construction; Invert prevents a successful
connectivity observation from masking secret export; Darken tests rejected
logging configuration without live traffic; Lighten records only a header
creation, not an observed session-secret leak; Amplify blocks inheritance by
transport child environments; Negate achieves diagnostics without enabling
session-key logging. The exact baseline/candidate fixture comparison is bounded
temporal evidence for this one behavior, not a whole-system historical replay
or a general organizational-learning claim.
