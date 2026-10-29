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

## First system attempt and correction

Recorded failure at parent 3a146e597bb164304ed117b970bd4f2da3335e1f:
the system service started but its worker exited when socket.if_nameindex()
attempted the disallowed AF_NETLINK family. The launcher obscured the immediate
exit with a 25-second report timeout. No report or isolation pass was produced.
The unit stopped and staging/private runtime contents were removed. Inspection
found a dangling /run/pulpo-e1-8dbb800ba2 marker. The original cleanup check used
Path.exists(), so it incorrectly treated a dangling link as fully removed.
That original failure JSON is preserved without editing or replacing it.

The corrected interface observation reads this process's /proc/net/dev, retaining
the same no-external-interface acceptance rule and the original restricted
address families. It neither adds AF_NETLINK permission nor falls back to a
weaker network profile. The supervisor checks active unit state while awaiting
reports and surfaces early exits immediately. Runtime cleanup now checks lexical
existence and removes only the exact expected dangling private/<unit> link;
it never deletes a target directory or follows another link. The --cleanup-unit
option accepts only an exact stopped pulpo-e1-<10 hex> unit and applies the same
bounded dangling-marker cleanup to the previous failed test.

Verified correction evidence: five regression tests cover interface recognition,
malformed observation rejection, expected dangling-marker removal, preservation
of live/wrong targets and files, and rejection of arbitrary names. A systemd user
subprocess under RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6 reproduces the
original EAFNOSUPPORT failure and succeeds using the new observation, reporting
eth0 and lo. Thus an unrestricted host is not misclassified as loopback-only.
This does not prove the pending system service's network isolation. No additional
service privilege or canonical-state mutation is introduced by the correction.

The next system run must use a new output path, service-sandbox-system-v2.json,
and --cleanup-unit pulpo-e1-8dbb800ba2. Administrative command access still requires
the user's sudo action. The complete system lifecycle remains Unknown pending
that run. The existing eight-pass review applies unchanged: this correction
especially tests Invert (settings are not success), Inside-Out (the proof can
fail), Darken (report/cleanup uncertainty), and Negate (no extra socket capability).

## V2 result and diagnostic preparation

Recorded: service-sandbox-system-v2.json already existed when the command was
submitted again. The second invocation correctly refused to replace it. Its
earlier run at e7f20c934b74a8cb061de164948c3946908ba302 failed before producing
a positive report: missing_authority_startup_denied and
malformed_authority_startup_denied were false. The worker captured child stderr
but did not retain it, so the underlying child exception is Unknown. This is
not evidence that missing or malformed authority was accepted by the app.

Verified cleanup from the report plus current host inspection: previous marker
removed, unit stopped, staging removed, runtime directory/marker removed, and
no pulpo-e1 system unit or runtime path remains. The failed v2 JSON is retained.

Unprivileged staged-startup reproduction copied the same code/environment and
exercised missing, malformed and valid synthetic configurations. Missing and
malformed configurations raised RuntimeConfigError without creating state;
valid configuration imported the actual app and created disposable state. This
also passed under a user-manager filesystem mask and the same address-family
restriction. It is not a reproduction of the full DynamicUser system profile.

The next version preserves bounded child tracebacks and return codes in the
sanitized report even when a startup assertion fails. It also normalizes read
and directory-traversal permission on root-owned staged code/runtime copies,
while removing shared write permission. A private launcher umask must not make
staged dependencies unreadable to DynamicUser. No live source permission,
real secret, service network privilege or governance policy changes. Whether
readability caused the v2 failure remains Unknown until further system evidence.

Seven regression tests pass, including umask/private-mode staging, removal of
shared write permission and preserving symlink targets. Child-observation read
failure cannot skip the cleanup path. Next output: service-sandbox-system-v3.json;
no previous-marker cleanup option is needed. Full isolation/HTTP/restart proof
remains pending the next user-authorized sudo run.
