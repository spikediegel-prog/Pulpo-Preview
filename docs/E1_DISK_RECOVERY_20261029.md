# E1 disk recovery on the personal Ubuntu VM

Current classification: Verified bounded disk-backed canonical-kernel fixture
in both transient user services and the hardened system-service profile, at
8c542ae0fb825eada5ee2137852ad899c4908e01. Machine reboot and physical power-loss
recovery remain Unknown. Preparation notes below retain earlier claim limits;
the final system-service result is the current record.

## Purpose and smallest proof

The VM is sufficient for bounded service-stop recovery; dedicated hardware is
not required. Parent checkpoint: 21445ccf366e9cd17ff869c959c1bc78fef4c29b. That
parent records the separate verified hardened system-service /run fixture.
This change reuses its canonical local-read fixture and adds exact audit-history
fingerprints. No live/customer database, provider account or human signing key
is used. No reboot or personal application shutdown is performed.

An opt-in live test launches a transient oneshot user service with
NoNewPrivileges, UMask=0077, AF_UNIX-only sockets and control-group termination.
The service uses SQLiteKernelState/GovernanceKernel to issue and consume one
synthetic local-read permit, deny a forbidden action, and close its connection.
Its process exits completely; systemd reports it inactive/unknown. The database
remains in a private temporary directory on ext4. A separately named fresh
service reopens those exact files using the same private test-only kernel secret.
It must reject the spent permit, preserve a valid audit, and match the exact
prior audit fingerprint and row count before appending new records.

The first verified run produced 3 audit rows and a 57,344-byte database. The new
service observed those same 3 rows with an identical SHA-256 audit fingerprint,
then appended replay rejection/denial evidence to reach 5 rows. Worker PIDs were
16126 and 16137. The ext4 mount is the VM's /dev/mapper/ubuntu--vg-ubuntu--lv root
volume. Both units stopped and all generated fixture files were removed. No
pulpo-e1-disk user units remained on independent subsequent enumeration.

The post-commit confirmation report records exact tested commit and source/test
SHA-256 values. Earlier reports are retained; new reports use unique filenames.
Raw reports are synthetic observation artifacts, not a second canonical ledger.

## Validation and execution

50 targeted tests passed: disk/fresh-process and live user-service recovery,
bounded cleanup, proof regressions, existing persistence and guarded recovery.
The existing negative tests cover replay, corrupt/truncated/foreign state,
stale checkpoints and supported tamper cases. These remain synthetic checks.
Disk cleanup tests preserve unrelated paths, reject wrong symlinks/arbitrary
names and retain ambiguous orphan state for inspection.

To repeat the user-service proof on this VM:

    PULPO_E1_USER_SERVICE_PROOF=1 PULPO_E1_EVIDENCE_DIR=/home/spikediegel/pulpo-e1-evidence-20261028 /home/spikediegel/pulpo-workspace/Pulpo-Preview/.venv/bin/python -m unittest tests.test_disk_service_recovery tests.test_service_sandbox_proof tests.test_persistence tests.test_guarded_recovery -v

Run from /home/spikediegel/pulpo-workspace/preview-e1-linux. No sudo is needed
for that bounded proof. Without the opt-in, the live user-service test skips.

The existing root sandbox launcher also has a prepared --disk-state mode. It
uses systemd StateDirectory on /var/lib with DynamicUser, stops the first unit,
checks its cgroup is empty and state remains on nonvolatile storage, and launches
a differently named service against the same StateDirectory. State ownership
changes stay under systemd. Its exact-prefix check is shared with the verified
user test. The full hardened custody combination has NOT run: SSH sudo still
requires a password. It is explicitly unverified and not needed to claim the
bounded user-service result. It must be tested before deployment/admission.

## Authority, state and cleanup boundaries

No authority is gained. Policy remains the existing canonical kernel's synthetic
local-read-only policy. Only newly generated disposable fixture state changes:
permit issue/consume, replay rejection, audit append and forbidden-action denial,
all through the existing kernel/state interfaces. No deployed API, signer,
executor, canonical writer, ledger, route or archival/deletion API is added.
The helper refactor changes test code only; production kernel/state code is
unchanged. The test-only permit and random kernel secret never leave the private
fixture and are removed with it; sanitized reports contain only counts/hashes.

Cleanup removes only this test's generated fixture after its units stop. The
prepared root-mode cleanup accepts an exact generated name, verifies the
systemd private-state alias, refuses unexpected links, and never accepts a live
database path from the operator. Deleting this synthetic fixture is not a claim
that canonical customer evidence may be rotated or pruned. Existing user
changes and separate checkouts remain preserved. No push, merge, release,
production action, persistent unit or permanent service account is introduced.

## Eight-pass review and claim limits

- Flip: a healthy process or readable database cannot substitute for replay
  rejection and exact prior-audit preservation.
- Reverse: require the first service to exit before the fresh service starts.
- Invert: newly initialized state must not count as successful recovery.
- Inside-Out: verify the proof's process IDs, filesystem type and prefix hashes;
  do not promote its configured service settings into enforcement proof.
- Darken: existing corrupt/stale/tamper tests reject; unexpected cleanup links
  and ambiguous state locations are retained instead of followed.
- Lighten: a personal VM can prove bounded process recovery without implying
  dedicated enterprise hardware or production readiness.
- Amplify: separate services and fresh processes must preserve spent-permit
  denial; repeated runs use separate fixtures and unique evidence files.
- Negate: no host reboot, disk exhaustion, provider action, human signing key
  or administrative permission is needed for this bounded user-service proof.

Legacy source: existing sandbox proof and canonical fixture APIs only; no legacy
control path copied. Temporal boundary: the exact parent is an applicable
service-proof checkpoint; its /run lifecycle does not establish disk recovery.
The new ext4 stop/fresh-service proof adds bounded evidence without transporting
authority backward. No whole-system historical replay or generally reusable
organizational-learning claim is made.

This proves supported state survival across a clean service exit and fresh
process start on the personal VM. It does not prove physical durability after
power loss, host storage integrity, VM reboot, recovery from valid whole-database
rollback, production load, actual provider transactions or the combined hardened
system-service disk lifecycle. Those remain separate tests and Unknown claims.

## Final hardened system-service disk result

Verified bounded fixture: user-authorized sudo run at tested commit
8c542ae0fb825eada5ee2137852ad899c4908e01 produced
service-sandbox-1793283285784433656-77d146da.json with passed=true and
storage_mode=disk_stop_and_fresh_service. The following supersedes the earlier
prepared/unverified status of the combined profile.

The first unit pulpo-e1-86ef4589d6.service (worker PID 16975) stopped completely;
its cgroup was empty. The 57,344-byte fixture database remained on ext4 under
the generated private systemd StateDirectory. A distinct unit,
pulpo-e1-86ef4589d6-fresh.service (worker PID 16995), reopened the same files.
Both workers ran as non-root dynamic UID 63080. The initial 3-row audit SHA-256
4572074a6ee9864da24fe06022233c082b822a822330cae5cc764454f3d4e5a2 exactly
matches the fresh service's audit before new mutations. The fresh worker denied
spent-permit replay and the fixture audit grew to 5 valid rows.

Both runs passed code/configuration write denial, root ownership, hidden home
credentials, no-new-privileges, zero effective capabilities, non-root identity,
denied external routing, loopback-only interfaces, writable private state,
missing/malformed authority startup denial without state creation, valid audit,
prior evidence preservation, forbidden-action denial, actual custody HTTP health
and HTTP 403 for an unapproved unknown commitment. The selected unit properties
include DynamicUser, StateDirectoryMode=0700, ProtectSystem=strict,
ProtectHome=tmpfs, PrivateNetwork/PrivateDevices/PrivateTmp, empty capability
bounding set, NoNewPrivileges and control-group termination.

The report's root cleanup checks confirm both units stopped, temporary /opt
staging removed and the generated /var/lib/private fixture plus alias removed.
Subsequent SSH enumeration found no pulpo-e1 system unit, matching /opt staging,
/run runtime or public /var/lib fixture path. No production or personal data,
real provider credential, human signer, persistent unit or permanent service
account was used. No push, merge, release, reboot or power-loss action occurred.

Scope remains exact: this verifies the canonical local-read fixture's on-disk
history/replay behavior alongside the actual custody app's startup/health/denial
behavior under the same hardened service profile. It does not establish recovery
of an actual provider transaction or completed domain purchase. Machine reboot,
physical power loss, storage-device durability, valid whole-database rollback,
production load and allowed enterprise/provider egress remain unverified.

Authority and eight-pass review remain unchanged: only synthetic fixture state
mutates through the existing canonical kernel, cleanup is limited to generated
test paths, and the exact stopped interval/hash comparison upgrades this bounded
combined-profile claim from Unknown to Verified. The user supplied sudo
authorization for this run; no credential or signing capability was copied into
the report. This documentation record adds no execution or authority capability.
