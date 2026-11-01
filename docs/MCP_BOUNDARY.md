# MCP boundary

Status: **Verified** for the in-process non-authoritative projection tests at
the exact commit carrying this document. Third-party-host connectivity and any
consequential MCP tool remain **Proposed**, not verified.

## Decision

MCP is a transport and capability-discovery surface. It is not a Pulpo
authority, policy, permit, directive, execution, memory, or evidence source.

`create_mcp_server(snapshot)` intentionally exposes only two projections over
the supplied frozen `MCPReadSnapshot`:

- `pulpo_propose_intent`: validate and return one exact candidate intent; and
- `pulpo_get_evidence`: return integrity metadata copied from that snapshot.

Neither tool accepts an approval flag, authority claim, directive, policy,
clock, state backend, permit, executor, retrieval score, or model summary.
Neither tool can approve, authorize, consume, execute, revoke, supersede, or
reconcile a consequential action.
Proposal text is bounded (256 UTF-8 bytes for target/principal/action/session,
4096 for resource, and 8192 total); cost and version use bounded integer ranges.

## Proven invariant

An MCP client can propose an exact intent and inspect frozen metadata, but MCP
metadata or client assertions cannot raise that intent's authority. The
proposal tool does not evaluate policy, lock a canonical target, append an audit
record, or re-read current evidence. `target_id` and `target_version` label the
proposal only; callers may submit different content under the same values.
Pulpo must resolve and re-evaluate any candidate through its canonical governed
path before treating it as an accepted target or action.

The adapter owns no state and no clock. Both tools are non-mutating projections;
neither appends to the canonical kernel audit chain or creates a second ledger.

## Trusted frozen-snapshot export

`export_mcp_snapshot(orchestrator, destination)` is the trusted-side file
bridge for capability-stripped consumers. It accepts the canonical
`PulpoOrchestrator`, calls the existing `freeze_mcp_snapshot()` projection, and
writes only the six primitive `pulpo.mcp-read-snapshot.v0` fields. The exporter
is not registered as an MCP tool.

The destination must be absolute and its immediate parent must already exist
as a real directory rather than a symlink. On POSIX, the parent must be owned
by the running user or root and not group/world writable; the reader enforces
the same requirement. A symlink or other non-regular destination is rejected.
On POSIX, creation, replacement, cleanup, and synchronization are bound to one
opened parent-directory descriptor, and the file is restricted to owner
read/write mode. On Windows, the exporter rejects
reparse traversal and rechecks parent/file identity, but does not inspect or set
the parent directory's DACL. The operator must place the snapshot under a
directory whose ACL grants access only to trusted identities. The Windows
`0o600` creation mode is not an ACL guarantee.

An error before atomic replacement is reported as `mcp_snapshot_export_failed`.
An error after replacement, including directory synchronization failure or a
failed pathname-binding recheck, is reported as
`mcp_snapshot_export_commit_unknown`: the caller must reconcile the destination
before retrying because a frozen file may already exist. This status is not
permission, verified delivery, or proof that a reader observed the snapshot.

Export does not mutate canonical Pulpo state or append a second audit event.
The resulting file is a frozen derivative: it cannot follow later canonical
mutations, and its presence does not prove live-current freshness, production
authentication, independent deployment, or external consequence containment.
MCP replies set `currentness=not_asserted`; the canonical evidence snapshot
provides no trusted capture time or generation identifier to establish age.

## Consequential-tool admission gate

A future consequential MCP tool must be a narrow adapter over an existing
canonical executor. Before admission it must prove, at minimum:

1. exact intent, target, directive version, policy, principal, session, budget,
   destination, and expiry binding;
2. execution-time directive and authority revalidation;
3. denial after revocation or supersession, including after restart;
4. one-use permit consumption and replay denial;
5. fail-closed behavior when authority, trusted time, or canonical state is
   unavailable; and
6. result reconciliation into the existing evidence chain.

MCP client approval UX is not a substitute for independently authenticated
Pulpo authority. Tool descriptions, prompts, resources, chat text, retrieval
scores, and generated summaries remain non-authoritative inputs.

## SDK boundary

The optional server factory follows the MCP Python SDK 2.x `MCPServer` tool
registration model documented in the official build-server guide:
<https://modelcontextprotocol.io/docs/2026-07-28/develop/build-server>.

Install with `pip install -e '.[mcp]'`. The SDK is optional so the canonical
kernel and its standard CI retain zero runtime dependencies. If connected over
STDIO, operational logging must go to stderr; stdout is reserved for MCP's
JSON-RPC transport.
