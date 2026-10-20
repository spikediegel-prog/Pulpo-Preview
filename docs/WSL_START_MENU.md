# WSL Start menu launcher and real observation setup

Run on Windows, pointing to an existing WSL checkout with its installed virtual environment:

```powershell
./scripts/Install-PulpoWslShortcut.ps1 -Distribution Ubuntu -Checkout /home/spike/pulpo-workspace/Pulpo-Control-Center
```

Search Start for **Pulpo Control Center (WSL)**. This opens the existing `.venv/bin/pulpo tune` via Windows `wsl.exe`; it does not install packages or start a workload, collector or export producer. It does not refresh the checkout. The separately named Windows setup/tuning shortcuts are retained. Re-running updates only this named WSL shortcut. The installer intentionally accepts simple absolute Linux paths without spaces or shell metacharacters, and a single distribution name; unsupported paths are rejected rather than interpolated into a shell. No Linux shell is invoked.

## Real observations require an existing trusted owner

Control Center is an observer. A successful launch or a passing disposable benchmark does not establish governed execution. Without selected exports, Governance, Evidence and connection data stay Unknown.

Identify the actual application process that already owns the canonical `PulpoOrchestrator`. Do not create a replacement kernel, open its state database from the UI, copy signing material, or start a test/demo owner to manufacture live-looking data. The current `pulpo` CLI provides setup and tuning; neither command is a long-running production workload/export service.

In that application's existing authorized lifecycle and owning thread, integrate the existing functions:

```python
from pulpo.mcp_boundary import export_mcp_snapshot
from pulpo.evidence_export import export_evidence_observation

# existing_owner is the application's existing orchestrator, not a new instance.
# Both absolute destinations have existing real parent directories.
export_mcp_snapshot(existing_owner, governance_export_path)
export_evidence_observation(
    existing_owner, evidence_export_path,
    check_database=False,
    ai=latest_usage,  # Existing AIUsage observation, or None; never credentials.
)
```

This is an integration outline, not a runnable service. Select destinations explicitly with the owner/operator. Evidence export requires an idle owner transaction; let the owner's existing lifecycle control scheduling and error handling. Do not add automatic retries around ambiguous publication failures. See [MCP export boundaries](MCP_BOUNDARY.md) and [Evidence monitoring](EVIDENCE_MONITOR.md) for exact contracts and failure handling.

Select the resulting owner-private JSON files in Governance and Evidence. Evidence rates require two distinct recent owner observations; re-reading a frozen file cannot create activity or freshen its source timestamp. Governance's frozen format has no export timestamp; freshness and deployed enforcement remain Unknown. Optionally save source locations through System → Set up → Remember setup; restoring locations does not automatically read them.

## Change record

1. Failure addressed: ambiguous Windows versus WSL launchers and missing owner-export setup context.
2. Authority unchanged; the shortcut opens the existing observation/tuning app.
3. No canonical mutation, new owner, writer, service, credential handling or export API is introduced. Only a named per-user Windows shortcut is written.
4. Validation is recorded in the PR: installer syntax, invalid-input rejection, shortcut readback, WSL GUI construction and native launch inspection. No live owner/export validation is claimed.
5. These checks do not prove live governance, source authenticity, complete system startup behavior or all installations.
6. Verified is limited to recorded local checks; real owner integration remains Proposed until an actual owner is identified and validated.
7. Existing `pulpo tune`, exporter contracts and Windows shortcut mechanism are reused without copying an authority path.
8. No reusable governance lesson is admitted; no temporal replay proof is claimed.

Analytical eight-pass review: **Flip:** a substituted checkout can execute code; launch only the operator-selected existing checkout. **Reverse:** no authority can be inferred from opening a window. **Invert:** successful startup is not an export or governance success. **Inside-Out:** the UI cannot self-create its canonical owner. **Darken:** malformed installer inputs are rejected; a compromised OS/checkout is outside this helper's guarantee. **Lighten:** missing exports mean missing configuration, not proof of failed enforcement. **Amplify:** re-installation updates the named shortcut; repeated launches do not install a producer. **Negate:** use the existing WSL executable and frozen-export boundary without a new daemon or owner.
