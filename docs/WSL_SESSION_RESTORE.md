# WSL session setup

System → Session setup offers explicit Remember this setup and Forget saved setup
actions. Nothing is saved on launch, preference changes or close. Remember captures
only the currently selected five owner-export locations, Overview/System/Evidence
graph ranges (60/900/3600 seconds), chosen startup page and System subtab. Startup
choices are explicit dropdowns, separate from the page used to save them. Update
the saved setup by pressing Remember again after changing selections or ranges.

## Restoring locations without reading sources

On WSL only, after normal construction and before the UI event loop, the app reads
one optional `control-center-session.json` beside its configured performance
profile. The standard location is `~/.config/PulpoPreview/control-center-session.json`.
A custom profile uses the same filename in its parent directory. This is private
presentation configuration, not an authority/state database or support export.

A valid remembered source sets only its existing path selector and enables the
existing Re-read button. No source path is resolved, statted, opened or parsed by
restore; missing paths are permitted and shown as Not checked this session.
Read results, activity, source observations, evidence history, benchmark reports,
health, credentials, approvals, permits and UDM guide configuration are not stored.
No old observation can be restored as current or governed. File selection itself
does not authenticate the exporter or authorize consequential action.

The Evidence reader has a specific pending-re-read gate. Page activation, map
events, scheduled ticks and Pause/Resume do not read a restored Evidence path.
Only explicit Re-read, explicit Troubleshooting check or a new explicit file
selection reaches the existing validated reader. Once that first explicit read is
requested, normal existing visible-page polling resumes, including existing
failure and freshness handling. Governance and connectors retain their explicit
reader behavior. Restored connections are not live reconnections or logins.

Preference errors retain normal startup defaults and show a generic status on
Session setup. Invalid values are rejected before any location is applied.
Unsupported pages, unknown fields, duplicate JSON fields, unexpected source keys,
relative/parent-traversal/network-form paths, control characters and unsupported
ranges are rejected. Absolute paths are bounded to 4096 characters each and the
entire file to 16 KiB. Locations may still be on mounted filesystems; restoring
one performs no reachability or availability check.

## Local persistence and forgetting

New preference files use mode 0600. Existing files must be regular, owned by the
current UID, private, single-linked and within the size limit. File opens use
nonblocking/no-follow flags; the final parent directory is opened with no-follow,
must be owned by the current UID and not group/world writable. Operations use
that directory descriptor. Missing parent directories are created only on an
explicit save. A fresh exclusive temporary file is written/fsynced and atomically
replaces a valid existing preferences document. No crash-durability claim beyond
these operations or concurrent-window conflict detection is made.

Malformed/unrelated documents, symlinks, hardlinks, devices, FIFOs, directories,
unsafe permissions and unsafe final parents are rejected without repair or
permission changes. Save/Forget validate any existing document before replacing
or unlinking it. Corrupt or unsafe files require manual inspection; the UI will
not delete or overwrite them as if they were valid saved preferences. No parent
ancestor-chain attestation, hard filesystem deadline, encryption or defense
against a fully compromised same-UID account is claimed.

Forget removes only a validated preferences document. Current window selections,
cached results and ranges stay as they are, and no source export or performance
profile is deleted. Closing does not recreate forgotten preferences. Preferences
contain local paths, which may include personal names: do not publish them with
support evidence. No upload or external messaging is introduced.

## Required change record

1. **Invariant:** remembered configuration cannot become a live observation or
   trigger an implicit source read. Opt-in setup persistence cannot grant
   authority, restore results as current, or erase source exports.
2. **Authority:** unchanged. No kernel, canonical writer, signer, provider client,
   credential access or canonical state backend is retained or introduced.
3. **Canonical mutations:** none. New writes replace/unlink only the explicit
   private preferences file through Remember/Forget. Restoring changes ephemeral
   selectors/ranges/navigation. Existing source readers remain the only read
   paths; the new Evidence gate narrows implicit reads for restored selections.
4. **Evidence:** [exact WSL logs, source hashes and native captures](control-center-evidence/wsl-session/README.md).
   Tests exercise actual private persistence/replacement/forget, unsafe and
   malformed files, failed replacement cleanup, no default/close writes, a new
   ControlCenter restoring saved source locations without reader calls,
   gated Evidence navigation/ticks/Pause/Resume, explicit real Evidence re-read,
   missing source paths, exact preferences fields/ranges, WSL gating, narrow
   layout and Tk-variable teardown.
5. **Not proved:** source availability/authenticity, independent authority,
   enforcement, complete filesystem race immunity, encryption, full
   accessibility, power-loss durability or safe canonical recovery. No service,
   credential or network probe is performed during restore.
6. **Classification:** implementation, tests and captures Recorded. Remembered
   paths are configuration only; current source results and enforcement Unknown
   until separately observed, with no attestation implied by a successful read.
7. **Legacy reuse:** existing path selectors, checked source readers, graph-range
   controls, navigation, theme and UI lifecycle. No canonical control path copied
   or second router/ledger/executor introduced.
8. **Temporal transfer:** no reusable authority lesson admitted. No historical
   authority replay performed or temporal-transfer proof claimed.

## Eight-pass analytical review

| Pass | Finding and boundary |
| --- | --- |
| Flip | A poisoned preferences file must not inject code, credentials, readers or results. Strict bounded schema/enums; fixed local store; restored paths are inert selectors. |
| Reverse | An automatic read would require an activation/tick/resume route. Evidence blocks these while pending; connectors/Governance already require explicit reads. Tests hold all readers closed during construction/navigation. |
| Invert | A valid preferences file or successful startup is not a verified source or restored health. Results/history are absent; all source reads begin unobserved. |
| Inside-Out | The preference file and UI cannot authenticate themselves or their referenced exporters. Local ownership/permissions are bounded checks, not authority or source provenance. |
| Darken | Malformed, oversized, linked or unsafe files must not be overwritten/deleted. No raw exceptions are displayed. An interrupted replacement preserves the prior document and removes its temporary file in the tested failure case. |
| Lighten | A missing remembered export is an ordinary setup gap. Do not infer outage, fix permissions, scan for replacements or retry a governed operation. |
| Amplify | One bounded file, explicit saves, no autosave/timer/history; repeated navigation reads no remembered sources. Multiple windows may explicitly overwrite preferences; no consensus or canonical state claim. |
| Negate | Save only locations and presentation choices, keeping credentials/results/authority outside the format. Reuse existing readers instead of adding reconnect, repair or credential-discovery machinery. |

Decision: WSL validation and draft review only. No merge or production deployment.
