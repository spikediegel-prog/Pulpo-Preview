# Agent network and disclosure boundaries

## Release requirements

The governance kernel controls effects that pass through its canonical intent,
permit, execution and evidence path. It is not a host firewall or hostile-code
sandbox. A kernel denial does not revoke a process's ambient socket capability.

Before admitting hostile workers, enforce network isolation outside the worker,
keep provider credentials and canonical state exclusively in trusted custody,
and verify that the worker cannot reach providers through alternate routes.
Do not expose host sockets, host networking, custody volumes or a container
management socket to the worker. The existing provider-route proof establishes
only its exact Docker topology; rerun containment checks for the release's
actual network configuration. This document adds no deployment enforcement.

## Exact output approval

`TelegramOutboundMessage.resource` commits the full message object, including
bot identity, destination and text. The governed sender consumes separate
activation and exact-message permits before invoking its transport.

For workflows requiring approval of each outgoing message, include both
`activate_capability` and `telegram_send_message` in the canonical policy's
approval-required actions, with pinned external authority trust. Preserve those
requirements when configuring grants or directives; destination-only scope is
not a substitute for exact-message approval.

Exact approval prevents substituting different text after approval. It does not
independently certify that approved text is safe to disclose. A destination-only
grant can admit private data within that destination scope. A classifier or
worker's assertion that content is public must not create authority.

Where independent information-flow enforcement is required, define trusted
input classification and authorized declassification in the canonical
consequence/approval path before claiming that property. Unknown classification
must not silently widen an existing grant. Do not introduce a second policy
authority, permit issuer or executor. Pattern matching alone cannot establish
semantic confidentiality or prevent arbitrary encodings and side channels.

## Evidence classification

**Verified:** isolated Ubuntu tests execute the existing exact-message,
destination, replay, revocation and transport controls. The boundary
characterizations in `tests/test_security_boundaries.py` show that substituted
plain/encoded canaries reject, exactly approved synthetic private text reaches
a recording transport, a broad destination policy lacks independent data scope,
and direct loopback HTTP can succeed after kernel denial when a synthetic
credential and network route are available. The endpoint rejects the
no-credential control. No real provider or real credential is used.

Passing a characterization means its asserted behavior was reproduced; it
does not certify that the characterized boundary blocks an attack.

**Unknown:** the policy, credential exposure, network containment and sensitive
data paths of any active deployment. These fixtures do not prove a container
escape, production compromise, universal content filtering or native Ubuntu
behavior beyond the tested WSL environment. Test-only HMAC approval helpers do
not prove independent human signing custody.

**Proposed:** independently scoped declassification, if a product requirement
needs it. No new data-label model or automatic secret redaction is implemented.

## Authority and eight-pass review

This hardening narrows HTTP admission and rejects unsafe configured HMAC keys;
it adds no canonical state mutation, approval authority, credential holder or
execution route. Existing configured keys and databases are not rotated or
migrated. Use `CUSTODY_SECRET_CONFIGURATION.md` for startup and migration limits.

| Pass | Boundary and disposition |
| --- | --- |
| Flip | A hostile worker can ignore wrappers; require external containment. |
| Reverse | Prevent usable provider credentials and unauthorized routes from reaching the worker. |
| Invert | An ungoverned successful request is not an authorized kernel transition. |
| Inside-Out | Exact approval does not independently certify content classification; test signers remain test-only. |
| Darken | Broad policy plus private input could disclose data; this is a threat case, not observed production history. |
| Lighten | These are explicit governance and deployment limits, not evidence of forged permits. |
| Amplify | One-use permits do not prevent fresh allowed effects under an overly broad standing policy. |
| Negate | Preserve exact output approval and custody isolation before expanding authority surfaces. |

The local integration preserves the user's existing working changes and reuses
the merged PR #15/#16 hardening. It makes no generalized organizational-learning
or temporal-transfer claim. Historical cross-checkpoint transfer was not tested;
the evidence is limited to this local source plus these changes.
