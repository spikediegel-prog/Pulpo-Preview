# Local installation observation workload

This is an explicitly started local validation application in Pulpo-Preview,
separate from the Control Center observer repository and its installer. It reads
the installed Control Center package's public files and compares their hashes
with its root-owned build manifest. It does not install, remove or repair files.
These are measured file reads, not synthetic allow/deny events; the result is
still **LOCAL VALIDATION**, not a production owner, provider consequence proof,
independent human approval or hostile-worker containment claim.

## Run on the Ubuntu VM after reviewing this change

Prerequisites: the trusted system `.deb` is installed and Pulpo-Preview is checked
out at a version containing `pulpo.installation_observation`. Keep the working
Control Center installation intact. No package rebuild or new service is needed.

Run as the ordinary desktop user, using the existing Pulpo-Preview environment:

```bash
cd ~/pulpo-workspace/Pulpo-Preview
./.venv/bin/python -m pulpo.installation_observation --cycles 60 --interval 2
```

The finite run prints two absolute JSON paths under a newly created private
`/tmp/pulpo-LOCAL-VALIDATION-*` directory. In Control Center:

1. Governance → **Select snapshot…**: choose the printed
   `LOCAL-VALIDATION-governance.json` path.
2. Evidence → **Select source…**: choose the printed
   `LOCAL-VALIDATION-evidence.json` path, then check **Test observations**.
3. Read the terminal's file counts (`match`, `mismatch`, `unavailable`, `denied`
   or `rejected`) separately from the dashboard. No scan outcomes are smuggled
   into the existing observation schema. Governance audit-record counts are not
   decision counts; Evidence read/write/commit rates are SQLite activity, not
   filesystem read counts or AI tokens. AI usage remains unavailable.
4. While publication continues, Evidence can obtain two comparable owner
   timestamps for rates. When the run finishes, the files remain as historical
   projections and freshness expires. The Governance v0 export has no source
   timestamp and cannot claim live deployment identity.

No production state or source path is accepted as an argument. If the installed
manifest is absent or invalid, the utility stops before allocating private
state. Run completion does not change dashboard selections automatically.
Use Ctrl+C to stop the utility; do not stop the VM. Exit code 0 means all checked
files matched, 1 means at least one check did not match/complete, 2 is an input or
runtime failure, and 130 is operator interruption. On failure a previous export
may remain; its timestamp still belongs to the previous publication.

## Scope and authority

The only workload action is `installation.inspect`, for the fixed installed
Control Center inventory. The manifest is bounded public bootstrap metadata
under `/usr/share/doc/pulpo-control-center`, not an authority or audit source.
It is validated before creating state. Only the specific application/library,
desktop entry, icon and README paths emitted by the existing package builder
are accepted. Paths outside the installation, links, writable system ancestors,
non-regular files, hard-linked files, oversized inputs, malformed manifests and
duplicate fields fail closed. A manifest change ends the frozen run; the owner
does not silently expand its scope during a package update. No root execution,
arbitrary commands, plugins, callbacks, provider credentials or alternate input
roots are exposed by the CLI.

The operator explicitly starts one local application with its narrowly scoped
policy. That application owns one fresh instance of the existing canonical
kernel and SQLite backend, rather than reopening a production database or
copying a control path into the UI. Each target read follows the existing
`GovernanceKernel.evaluate` and one-use `consume` path. A policy denial or failed
consumption prevents that file read. No new generic executor, router, signer,
authority service, canonical schema or evidence ledger is introduced. Diagnostic
results on stdout are not canonical execution receipts or independent
consequence reconciliation.

The existing `export_mcp_snapshot` and `export_evidence_observation` APIs publish
only public frozen projections. Publication and the read-only quick-check use
the owner connection after its transactions complete. Private temporary state
is closed and removed on normal completion or handled interruption/failure;
published JSON is retained with owner-only permissions. Hard process termination
or host crash can leave private temporary state: do not treat this as an
automatic crash-cleanup guarantee or import such databases into the UI.

This cooperative process can be modified by its operator. It does not protect
against a hostile Python owner, compromised root, malicious installed manifest,
arbitrary other processes or provider bypasses. Hash comparison detects changes
against the local manifest; it does not authenticate the publisher. The scan is
not an atomic snapshot of every file. Metadata checks reduce ordinary read
races, not hostile-host tampering. An installed-file mismatch can coexist with
a passing audit check: those are different observations.

## Eight-point change record

1. Invariant/failure: the installed observer has no workload producing public
   sources. Provide one useful, bounded local check without manufacturing live
   production data or giving the observer canonical mutation capability.
2. Authority: the explicitly started application gets only its local read-check
   scope, under a fresh manifest-bound policy and one-use permits. Production
   authority, independent approvals and provider capabilities are unchanged.
3. Canonical mutations: fresh private SQLite state; normal kernel initialization,
   intent decisions, permit issuance/consumption and canonical audit entries.
   Existing exporters read that owner and publish public metadata. No existing
   state, authority trust, settings or installed payload is changed.
4. Evidence: isolated tests exercise real fixture bytes, gate-before-read,
   mismatch/missing inputs, scope changes and malformed/unsafe paths. See the
   [validation record](control-center-evidence/installation-observation/README.md)
   for exact commands, counts and artifact limits.
5. Limits: local fixture/package checks do not establish production enforcement,
   independent signing, native VM execution of this utility or protected-worker
   containment. The native VM source connection remains an operator step.
6. Classification: tested fixture behavior is bounded implementation evidence;
   exported audit health is source-reported; production owner/enforcement remains
   Unknown. Native execution is Proposed until performed.
7. Reuse: existing kernel, AgentGrant, SQLite backend, orchestrator and both public
   exporters. No canonical control path is copied into Control Center. The older
   observation test remains synthetic and distinct.
8. Temporal transfer: absent. No generally reusable deployment/security lesson or
   historical transfer is claimed from this local validation workload.

## Eight-pass analytical review

- Flip: do not trust the application as a hostile worker boundary. The observer
  receives only projections, never its owner, state, permits or secret.
- Reverse: prevent reads outside the fixed package namespace before opening
  targets; never accept an arbitrary database or configuration root.
- Invert: matched files or a passing audit does not establish legitimate external
  consequence, deployed enforcement, independent authority or publisher identity.
- Inside-Out: the local owner can create its own policy and mutate its private
  state. Therefore it cannot ratify itself as production-governed; that limitation
  remains explicit in the utility, file names and documentation.
- Darken: a compromised root or owner could falsify the manifest/results. This
  utility does not address those threats or duplicate privileged credentials.
- Lighten: missing/changed package files produce mismatch/unavailable outcomes;
  absent AI/provider observations remain Unknown rather than fabricated zeros.
- Amplify: bound the run to 60 cycles, 128 files, 8 MiB per file and 32 MiB per
  cycle. Run state is fresh; repeat runs do not reopen a production ledger. Old
  projections retain their old timestamps rather than claiming continued work.
- Negate: use direct bounded reads after the existing permit gate, not an AI
  worker, shell executor, repair service, external purchase or provider adapter.

Continue with isolated tests and draft review. The smallest next proof is an
operator run against the VM's installed package and explicit selection of its
two public JSON outputs, marked as local validation.
