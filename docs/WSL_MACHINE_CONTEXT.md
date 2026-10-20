# WSL machine context and separate observation clocks

The WSL header identifies **this window** and limits CPU, memory and storage
resource graphs to its local Linux VM. This is not a claim about the Windows host,
the separate Hyper-V VM, a collector or a selected export's machine. Narrow
windows use a shorter version with the same scope and unassessed enforcement.
Other platforms retain their existing header and Evidence presentation.

Evidence now separates:

- **Source machine:** Unknown unless the operator adds a local description.
  Existing exports do not contain authenticated machine identity. Source details
  → Describe source, or System → Monitor → Sources → Describe source, opens a
  bounded plain-text dialog. Descriptions always say operator description and
  unverified. They are scoped to the selected path in this window, cleared on
  explicit replacement/Clear, and omitted from saved setup, clipboard hashes,
  export files and support reports. An empty description clears it; Cancel leaves
  it unchanged. No machine discovery, SSH, hostname lookup or network probe occurs.
- **Source-data age:** elapsed time since the usable export's reported timestamp.
  A re-read or description edit cannot advance that timestamp. Missing timestamps
  and timestamps ahead of the window's clock remain Unknown. Reported freshness
  does not authenticate clocks or establish owner liveness.
- **Last successful read:** elapsed local UI wall-clock time since a successful
  file read. A later failed read retains only this historical read time, clears
  current source metrics and shows read failed. Clear/replacement resets it. This
  clock is never substituted for source time.

Source Health shows Data age and Read age in separate columns. Read age means the
last successful local read, not the latest attempt, a collector heartbeat or a
service uptime. Governance's frozen format supplies no export time, so its data
age remains Unknown even after a successful local read. Its last attempt/result
and existing source timestamp details remain available separately.

## Cache-only clock lifecycle

One WSL Evidence display timer refreshes age labels and cached graph state every
second while the page is visible. It continues during Pause for review, so frozen
sample ages remain truthful. It does not open files, contact providers, restart
the owner, alter history, update read timestamps or bypass the restored-source
first-read gate. Existing two-second observation reads are unchanged and stay
paused during review. Hiding, unmapping/minimizing or destroying the window cancels
the display timer; mapping an active page resumes one display timer only.

Descriptions accept at most 48 printable characters and reject control characters,
line breaks and invisible format controls. They are never interpreted as commands,
hostnames, file paths or URLs. A label is an operator statement, not identity proof.

## Required change record

1. **Failure addressed:** local WSL resource scope and remote snapshot origin could
   be confused; a new successful read could make an old export appear current.
2. **Authority:** unchanged. Descriptions and ages are local presentation only.
3. **Canonical mutations:** none introduced or exposed. No kernel, database,
   credential, collector or canonical writer is obtained by these views.
4. **Evidence:** exact core log, code/test hashes and native before/after captures
   are in `control-center-evidence/machine-context`. Tests cover separate clocks,
   frozen re-reads, paused/pending no-I/O display updates, failure clearing,
   label cancellation/validation/reset, non-persistence and timer teardown.
5. **Limits:** no authenticated exporter/host identity, real-time transport,
   deployment governance, accurate owner clock, every DPI setting or screen-reader
   qualification is established. A source at the same path may be substituted;
   an operator label does not prevent or authenticate that substitution.
6. **Classification:** local read times are Recorded UI observations. Data ages
   derive from source-reported timestamps. Descriptions are explicitly unverified
   operator statements; source authenticity and enforcement stay Unknown.
7. **Legacy source:** existing protected snapshot loaders, source/read caches,
   source selectors and optional session preferences are reused unchanged.
8. **Temporal transfer:** no reusable governance lesson is admitted and no temporal
   replay proof is claimed. UI comparisons are not historical authority replay.

## Eight-pass analytical review

| Pass | Boundary |
| --- | --- |
| Flip | Misleading operator text remains a plainly unverified description. No label authorizes anything or triggers a network lookup. |
| Reverse | A false fresh-data claim would require using read time in place of reported source time; these clocks are displayed separately and tested across repeated re-reads. |
| Invert | A successful file read cannot refresh old owner data; a failed read clears its current metrics despite historical read success. |
| Inside-Out | This window identifies only its WSL resource scope. It cannot authenticate the machine that produced a copied file. |
| Darken | Clock rollback/future source times yield Unknown ages. Schema-valid timestamp lies and compromised hosts remain outside the UI trust boundary. |
| Lighten | A frozen file can be old without a failed service; no stopped-owner or outage conclusion is inferred from age. |
| Amplify | Display ticks are cache-only, bounded to one visible-page timer, and cannot accumulate reads, source age refreshes or canonical events. |
| Negate | Two explicit clocks and a session-only description avoid adding a host inventory, transport, collector or identity plane. |

Continue with this presentation-only increment after tests/native inspection.
The smallest next proof is an operator walkthrough labeling a selected test source
and comparing old data with a fresh local re-read. True source identity and live
VM-to-WSL observation delivery remain separate, unverified work.
