# Pulpo Preview E1 acceptance check — 2026-10-29

Scope update: see `E1_SCOPE_CLOSURE_20261029.md` for the later bounded E1 closure
and the user's external-storage responsibility decision. This document retains
the exact historical acceptance results and original gaps below; external
archival work is not a current E1 completion requirement.

Status: Bounded functional acceptance checks passed at the current tested source
commit, including the hardened disk-system-service proof. Enterprise deployment
admission and production readiness remain unassessed.

Source: da4913186bcb494cf3a9252bdc36294a9d46b4da on
codex/preview-e1-linux-20261028. The source working tree is clean. No application
code changed during this acceptance run. Kernel/state/service source hashes,
runtime versions and log hashes are retained in acceptance-summary.json.

## Current results

| Area | Result | Scope |
| --- | --- | --- |
| Core suite | Verified: 939 successful, 55 skipped | 994 tests; strict warning mode; no resource warnings |
| Authority suite | Verified: 66 successful, 4 skipped | 70 tests; synthetic service/adapters; no live approval ceremony |
| Custody suite | Verified: 50 successful | 50 tests; synthetic providers; no real domain purchase |
| Total | 1,055 successful, 59 skipped | 1,114 tests considered; no failed suite in the isolated runtime |
| Disk recovery via user services | Verified at current commit | Distinct services, complete exit, saved ext4 state, exact audit prefix, spent-permit rejection, cleanup |
| Network diagnostics | Verified fixtures; Recorded VM inventory | IPv4/IPv6 loopback TLS, hostname/certificate rejection, DNS-error injection, redirect/refusal/timeout cases, redaction and TLS key-log denial |
| Storage diagnostics | Verified fixtures; Recorded current capacity | Space/inodes/reserves, read-only flags, path/device uncertainty, report-write failure, existing SQLite FULL/recovery cases |
| Hardened disk system service | Verified at current tested commit | Full stop, empty old cgroup, saved ext4 state, fresh service, exact audit prefix, spent-permit rejection |
| Temporary service cleanup | Verified fixture cleanup; Recorded host enumeration clear | Both system-test units stopped; staging/private state removed; no pulpo-e1 system/user unit remained |

The core skips comprise 52 graphical/display cases, two Windows-specific cases
and one finalizer-warning case requiring Python 3.13+. The four authority skips
require a disposable PostgreSQL test DSN, which is not configured. Skips are not
successful executions of those cases. Visible GUI behavior and live PostgreSQL
behavior remain Unknown.

## Acceptance environment and initial failed run

VM: Ubuntu 24.04.5, kernel 6.8.0-147-generic, Python 3.12.3. The original
development environment contained cryptography 50.0.1 and no webauthn package.
The first strict run passed core/custody but could not import two authority test
modules. That run and its original logs remain preserved as run1; it is not
promoted to a complete pass.

A separate environment was created at
/home/spikediegel/pulpo-workspace/e1-acceptance-runtime-20261029. It contains
public Python packages only, not SSH/session state, human credentials or live
governance databases. The original environment was not altered; its package
versions were independently rechecked after preparing the new one.

Selected direct dependency pins match the repository: cryptography 50.0.2,
webauthn 3.0.0, fastapi 0.141.1, uvicorn 0.52.4, httpx2 2.12.0 and anyio 4.14.2.
The missing packages were downloaded as wheels from the explicitly selected
official PyPI index, then installed offline into this environment. A previously
published kit wheel supplied the matching cryptography binary. Download/install
logs, wheel hashes and installed package versions are retained. pip check passed.
This establishes dependency consistency, not vulnerability clearance, image
admission or a release-ready dependency lock.

The complete strict core/authority/custody run was repeated in that environment
as run2. The live user-service recovery fixture was explicitly enabled. No live
cloud, production provider, actual human enrollment, reboot or power-loss action
was part of these tests. Source tests which use synthetic assertions/signers do
not prove independent human custody in a deployed installation.

## Current host observations

The network inventory was refreshed with no external connectivity probe.
IPv4 has a default route; no IPv6 default route was observed. The resolver file
names a local DNS stub; upstream reachability is not tested. System TLS trust
loads with required certificate/hostname verification. There are no ambient
proxy/CA override variables in this collector environment. These facts do not
prove enterprise proxy support, routed IPv6, VLAN/VPN behavior, external DNS/HTTPS
reachability or certificate lifecycle management.

The storage report observes the shared filesystem at the existing evidence
directory, under the selected 85%/95% review thresholds. Current pressure is ok;
this is not evidence-quota, directory-write, mount/export identity or admission
verification. No live database was opened or copied. No evidence was pruned or
rotated. Canonical replay guards, pending consequences and custody records remain
outside these read-only diagnostics.

## Current-commit hardened disk-system-service result

The earlier hardened disk-service report remains preserved at its original
8c542ae commit. It was not promoted to current evidence. A fresh user-authorized
sudo run validated source da4913186bcb494cf3a9252bdc36294a9d46b4da with the
isolated acceptance runtime and produced
service-sandbox-1793291445788850062-5e71c81d.json with passed=true.

The first worker PID 30293 and fresh worker PID 30313 used dynamic non-root UID
62509. The first service stopped with an empty cgroup; its 57,344-byte synthetic
database remained on ext4. The initial three-row audit SHA-256
7a3aa33a8bed1693e6ea01f0e5634725d2068109523c65a0579097b5cbc5d0fa matches
the fresh service's prior history exactly. The fresh service rejected the spent
permit and appended supported rejection/denial evidence, reaching five rows.

All 18 initial and 19 fresh-worker checks passed, including write-protected
root-owned code/configuration, hidden home credentials, no-new-privileges, zero
effective capabilities, loopback-only interfaces, denied external route, private
writable state, missing/malformed authority rejection before state creation,
valid audit, forbidden-action rejection, actual custody health and HTTP 403 for
an unapproved unknown commitment. The replay database is a separate synthetic
canonical-kernel fixture; no real provider transaction recovery is claimed.

Both generated units stopped and root-side checks confirmed staging/state
removal. Subsequent independent SSH enumeration found no matching system/user
unit or public /opt, /run or /var/lib test path. The final acceptance summary
validates the source commit, required boolean predicates, audit fingerprints,
disk stop interval and cleanup. Its overall result is
bounded_functional_checks_passed. This is not a signed attestation or authority.

To repeat that disposable proof, run in the development VM's SSH session:

    sudo /usr/bin/python3 /home/spikediegel/pulpo-workspace/preview-e1-linux/scripts/prove_linux_service_sandbox.py --system --disk-state --runtime /home/spikediegel/pulpo-workspace/e1-acceptance-runtime-20261029 --evidence-dir /home/spikediegel/pulpo-e1-evidence-20261028/e1-acceptance-20261029/run2

This is the already-reviewed disposable test. It uses root-owned staged code,
DynamicUser, no effective capabilities/no-new-privileges, isolated networking,
private on-disk synthetic state, actual custody health/rejection checks and a
complete first-service stop before a separately named fresh service. It verifies
the exact prior audit and spent-permit rejection, then removes its own generated
services, staging and fixture state. It neither reboots the VM nor changes
network/mount settings. The user supplied sudo locally for this completed run.
SSH sudo -n requires a password; no password was requested, read or retained by
the agent.

## Remaining gaps after the bounded acceptance checks

- Graphical/platform and live PostgreSQL coverage listed above remains skipped.
- No VM reboot, physical power loss, hardware durability or protection against
  rollback of an entire older valid database was established.
- External networking, enterprise proxy integration, customer CA rollout,
  certificate lifecycle, VLAN/VPN/policy routing and IPv6 default routing remain
  unverified or unimplemented.
- Safe canonical archival receipts, retention/pruning, quotas and capacity-based
  admission remain unimplemented. A public projection is not a full audit archive.
- Current package/container vulnerability scans and release/merge admission were
  not rerun. The held dependency/container work remains separate.
- The original development environment remains preserved and does not match the
  selected acceptance dependency profile; use the isolated environment for these
  reproducible checks. No installed product or production environment was updated.

## Doctrine and claim boundary

Authority gained: none. No application capability, API, signer, ledger or
canonical-state writer is added by this check. Canonical mutations occur only
inside existing synthetic test fixtures through their existing governed paths.
No live provider or human credential material is read, created or copied.
The acceptance report/logs are observations, not a new authority/evidence plane.

Flip/Reverse validate the test boundary before treating a result as current;
Invert/Inside-Out preserve failed/absent evidence and dependency mismatches;
Darken exercises supported denial/failure/replay/tamper cases without filling
the personal VM's disk; Lighten distinguishes absent optional infrastructure from
observed compromise; Amplify includes fresh-process and service lifecycles;
Negate avoids reboots, production changes and new governance mechanisms.

Temporal boundary: prior exact service proof remains at its original commit;
it is not promoted across later code/runtime changes. The full source suites
and current fixtures establish only the current bounded run. No whole-system
historical replay or generally reusable authority lesson is claimed. No push,
merge, release, deployment or production-readiness claim is part of this work.
