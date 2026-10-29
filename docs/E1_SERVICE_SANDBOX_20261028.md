# E1 Linux service sandbox

Status: Prepared, not verified as a system service. User-service confinement
probe failed; no successful service-isolation claim is made.

Parent: c72bd8ee3bab9d96a1f708e65ae86c2c3e10704c. VM: pulpo-os,
Ubuntu 24.04.5, systemd 255. Existing Preview and Control Center checkouts are
preserved. This change adds only a disposable proof tool and this record.

## Failure, authority and canonical mutations

Non-root execution alone does not establish protected code, isolated networking
or a separate service identity. Early /usr/bin/true probes returned success,
but the complete user-service probe recorded that PrivateNetwork could not be
applied and capability setup failed (218/CAPABILITIES). Command exit success
and configured properties therefore must not be promoted to isolation proof.

The tool tests effective write denials, hidden home credentials, kernel process
status and absence of external routes before starting the actual custody app.
It does not weaken these checks when the VM cannot enforce the profile.

No authority is added to Pulpo, Control Center or a worker. No human signer is
created or read. The existing sandbox-only custody runtime receives a public
fixture verification key, synthetic non-signing secrets and dummy provider
strings; no real provider credential is present. Network access outside the
private namespace must fail. There is no production/provider execution test.

Canonical mutations are confined to newly created, disposable fixture databases
through the existing SQLiteKernelState/GovernanceKernel and custody runtime.
The replay fixture has a policy limited to synthetic local read. Its consumed
permit remains inside temporary state and is never included in report output.
The proof adds no mutation endpoint, kernel, signer, state backend or ledger to
the deployed application. Test fixture state is not live customer evidence.

## Prepared system proof

Run from the development VM using its existing administrative authorization:

    sudo /usr/bin/python3 /home/spikediegel/pulpo-workspace/preview-e1-linux/scripts/prove_linux_service_sandbox.py --system --runtime /home/spikediegel/pulpo-workspace/Pulpo-Preview/.venv --evidence /home/spikediegel/pulpo-e1-evidence-20261028/service-sandbox-system.json

The script stages only application source and the explicit Python environment
under a unique root-owned /run directory. A transient systemd service uses
DynamicUser, NoNewPrivileges, empty capability bounding set, ProtectSystem=strict,
ProtectHome=tmpfs, PrivateTmp, PrivateDevices, PrivateNetwork, a restricted address
family set and private runtime state. No installed unit, enabled service,
firewall rule or network route is changed. No dependency is downloaded.

It checks root ownership and attempted write-open denial for code/configuration,
actual no-new-privileges/zero-effective-capability process status, home masking,
only-loopback interfaces and failed external route. The actual custody entrypoint
must reject missing/malformed authority before state creation. A real loopback
HTTP health request must succeed; an unknown commitment without approval must
return 403. Health alone is not governance attestation.

The service is restarted once using systemctl. The same disposable canonical
fixture must retain valid audit history and reject the previously spent permit.
RuntimeDirectoryPreserve=restart retains this fixture only across that restart.
Finally the service stops; staging and runtime state are removed. Sanitized JSON
records checks, identity, process IDs, audit-row counts, selected unit properties
and cleanup results. The invoking user receives ownership of the report. A failed
run is retained as failure evidence; choose a fresh report name before rerunning.

Administrative access is required because the user manager could not enforce
this VM's full profile. sudo -n true reported that a password is required. The
agent has not requested, read or entered that password. The system proof is
pending the user's sudo action, not a missing chat permission to begin E1.

## Evidence and limits

Verified on the VM before committing the tool: Python compilation/help checks;
9 custody runtime tests passed; 38 persistence/guarded-recovery tests passed;
git diff --check passed. The full user-service attempt failed before running
the workload, and its report records unit_stopped=true and disposable_files_removed=true.
No pulpo-e1 transient user units remained in final unit enumeration.

Unknown: dedicated-identity system-service confinement and service restart until
the sudo proof succeeds. Unit tests do not substitute for that run. The installed
test environment reports fastapi 0.141.1, uvicorn 0.52.4, cryptography 50.0.1;
it is an existing development environment, not dependency admission evidence.

Recorded reconciliation: open dependency/container PR #48 was inspected through
connected GitHub access. It remains separate and held; none of its changes are
merged or copied. Docker is absent. This tool does not clear its package-scan
findings, prove hostile-worker containment, establish production readiness, or
configure a provider-enabled deployment. Root and the service's trusted owner
remain outside this confinement threat model. Durable machine-reboot recovery,
TLS lifecycle, approved outbound endpoint access and production packaging are
outside this disposable /run fixture.

## Adversarial transformation review

- Flip: test effective denial if the service tries to write protected files.
- Reverse: prevent provider effects with absent real credentials and no route.
- Invert: a healthy app with ineffective isolation cannot pass this proof.
- Inside-Out: systemd settings and the proof's own assertions are fallible;
  verify process, filesystem, interface and HTTP behavior directly.
- Darken: absent authority, malformed authority, unexpected routes and failed
  privilege setup reject; no fallback profile is accepted as equivalent proof.
- Lighten: VM privilege limits can explain failed isolation without compromise.
- Amplify: service restart must preserve replay denial and prior audit evidence;
  retries use unique disposable units and never replace an earlier report.
- Negate: no provider execution, human signer, Docker installation, permanent
  account or enabled service is necessary for this bounded service test.

Legacy source: current custody entrypoint and canonical fixture APIs only; no
legacy control path copied. Temporal evidence: the current exact-parent VM user
probe exposed settings-versus-enforcement uncertainty; no historical whole-system
transfer or generally reusable organizational-learning proof is claimed.

Stop/continue: the failed user attempt is reconciled as failed and cleaned up.
Continue only with the explicitly prepared system test under the user's sudo
authorization. Do not declare it verified until its behavioral and cleanup
results pass. No push, merge, release or production operation is authorized here.
