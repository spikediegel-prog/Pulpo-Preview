# Opt-in local Ollama proposals in Preview

This port reuses the proposal-only adapter from Austin's Pulpo1.0 commit
`fc411a61b1921a32c90a0cd59b0b4522876effd2`, on Preview main
`838a996f8f2e4cf4d2bece0fc6d0de3c7e4e7968`. It adds no agent framework,
automatic launcher, UI action, SDK dependency, model installation, worker sandbox
or provider integration. The Mac offline profile and tournament are separate
candidates and are not included.

## Behavior and authority

`pulpo.ollama_proposal` offers two separate operations:

- `request_local_proposal(prompt, LocalModel(tag, digest))` makes bounded
  inference requests to an already running daemon at literal `127.0.0.1:11434`.
  It checks the selected installed tag/digest and rejects declared remote aliases,
  redirects, incomplete/oversized/compressed/malformed responses and tool calls.
  It reads no files, downloads no model, sends no authorization header, consults
  no proxy/host/API-key environment configuration and does not retry failures.
- `project_local_proposal(content, snapshot, principal=..., session_id=...,
  target_id=...)` accepts only action/resource/integer-cost output and calls the
  existing frozen MCP projection. Identity comes from the separately trusted
  caller, not from the model. The resulting proposal is ephemeral and grants
  no approval, directive, permit, locked target or execution right.

Nothing is sent until a trusted caller explicitly invokes the inference helper.
Provide only data already permitted for that model context. The daemon is an
existing trusted dependency: loopback and a model digest response do not prove
daemon identity, egress containment or immutable model identity during inference.
The socket timeout is not a total wall-clock/CPU deadline or process memory cap.

The existing kernel remains responsible for current policy/approval decisions,
one-use permits, expiry, issuer/policy binding, evidence and reconciliation.
Model success and valid JSON do not authorize an effect. This library does not
make the entire assistant, host, browser, shell or daemon Pulpo-enforced.

## Optional manual synthetic probe

The probe is not run automatically and is not connected to a provider or live
database. Use an already installed local model and independently verified tag
and digest, with context already permitted for that daemon:

```text
python -B -X utf8 -m scripts.probe_ollama_proposal --model EXISTING_LOCAL_TAG --digest EXACT_64_HEX_DIGEST
```

It asks for synthetic read/delete proposals and exercises an in-memory fixture
policy. It refuses optimized Python before argument parsing/inference because
its acceptance checks use assertions. Missing models, changed digests and
unavailable inference stop the probe; do not change daemon settings, pull a model
or substitute a digest to manufacture a passing result. No live inference was
performed during this port's automated validation.

## Source disposition and tests

The adapter, main upstream test module and manual proposal probe are copied
unchanged from the pinned upstream commit. The precondition test loops are
limited to the proposal probe; the unported Mac worker-isolation probe is
excluded. Preview-specific tests check exact permit expiry, policy/issuer
binding across restart, repeated frozen proposals, rejected authority-context
fields and inference failure without canonical evidence publication.

The HTTP protocol test uses a temporary loopback fixture and redirects the
adapter's connection constructor to that fixture; it never contacts Ollama or
an external provider. Other transport tests use mocks. SQLite fixtures are
disposable. Test output, exact commands, source hashes and baseline/candidate
failure comparison accompany the local delivery record. Passing local fixtures
do not establish installed-model compatibility, deployment or independent review.

## Eight-pass change record

- **Flip:** hostile model responses cannot supply identity, authority, permits,
  directives or execution fields; hostile actions remain proposals for denial.
- **Reverse:** the adapter has inference HTTP and primitive snapshot/projection
  inputs, with no canonical writer, authority client or consequence adapter.
- **Invert:** successful inference and schema-valid output cannot certify either
  authorization or consequence. Positive and denial controls use the real kernel.
- **Inside-Out:** caller identity and daemon metadata remain trust assumptions;
  they do not authenticate themselves through a generated proposal.
- **Darken:** malformed output, substitution, remote aliases, environment routing,
  response truncation, timeout, tool calls and replay must reject or remain
  non-authoritative. Host/daemon compromise is outside this bounded proof.
- **Lighten:** cooperative local inference is useful for drafting proposals; it
  still requires current canonical evaluation before any stateful action.
- **Amplify:** seeded/concurrent projection remains non-mutating; Preview expiry,
  rotated policy/key and restart/replay controls remain effective.
- **Negate:** reuse the existing projection and installed local model through
  minimal standard-library HTTP. Add no second runtime or authority route and
  do not activate the Mac profile or a live executor.

Authority gained: no governed authority. Canonical mutations introduced or
exposed: none. Proposal inference adds an explicit opt-in call to an existing
local service; it is not authority to disclose protected context or execute a
provider action. No actual service capability was activated during validation.
Stop/continue: no credential export, live executor connection or alternate
provider route was created. Those integrations require their own exact authority.

Claim classification: source equivalence and exercised synthetic tests may be
Verified at their logged exact source; real daemon/provider behavior, OS
containment, production suitability and independent approval remain Unknown.
Temporal boundary: the pinned upstream adapter and pinned Preview base establish
a bounded compatibility comparison with the same synthetic policies, identities
and budgets. No earlier Preview local-inference checkpoint exists and no general
historical lesson or future authority is imported into the baseline.

## Recorded local validation

28/28 proposal/upstream/precondition/Preview tests pass with zero skips. All
three deliberate guard weakenings are killed by assertions, and the adapter
is restored byte-for-byte to upstream. A controlled native Windows comparison
runs baseline711/candidate739 tests with the same7 failures and12 errors and
identical GUI exclusions; no new problem identities. The seven native
ControlCenter GUI cases are explicitly skipped in both, following an unrestricted
candidate Tcl process abort. The whole Windows suite remains non-green. Existing
historical fixtures and ancestry were restored in the isolated Git store; all9
temporal-proof tests pass. These are local results, not a live-daemon or GUI proof.
