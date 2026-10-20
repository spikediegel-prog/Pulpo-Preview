# Configuration Comparison · WSL only

System → Configuration compares the existing effective evidence-worker hint with
the shared proposed worker count. It is constructed only under the existing
WSL runtime gate; other platforms keep their three System tabs. No Windows
implementation or qualification is added. WSL tabs use multiple rows as needed.

## Current settings, proposal and history

The two-row table shows evidence workers and derived collector mode. Workers 0
and 1 both mean serial collection; higher supported counts use threads. The
proposal shares the exact candidate variable and validation with Tuning &
benchmarks. There is no second setting, alternate configuration format, imported
comparison report, policy/grant control or OS tuning interface.

Entering Configuration, Re-check current settings, existing diagnostic refresh
and completed System operations observe the configured performance profile.
The observer uses the existing bounded profile validation, serial-default/fallback
rules, raw profile token, machine context and benchmark implementation digest.
It rejects observed non-regular files and oversize reads, and refuses a profile
token that changes across the check. Invalid format/checksum/machine/source data
uses the existing serial fallback, explicitly labeled. Missing profiles use the
serial default without creating a file. Unavailable observations show Unknown
instead of manufacturing a current value. Raw content, paths and errors are not
displayed by this observer. It is not a hard filesystem-read deadline or complete
protection against adversarial path replacement; saving remains independently
checked by the existing backend.

The check time is UI wall-clock time, not the profile's modification time or an
authenticated timestamp. An initial candidate suggestion has no invented edit
time. A later edit receives an explicitly local observed time. Historical profile
change time, operator motivation and reason remain Unknown because the existing
profile format records none of them. Its `previous_settings` value is labeled as
a **recorded rollback worker count**, not necessarily a previously saved profile
(the existing save path can retain a validated fallback).

At most one successful System save/restore observation is held in memory: before
and after worker counts, operation enum and time completion was received by this
UI. It replaces the previous observation and resets on close. Its reason is the
observed explicit Save tested candidate or Restore previous setting action;
operator motivation remains unrecorded. It is not a persistent history, audit
ledger, complete record of other UI controls or external changes, or proof of an
exact filesystem write time. Failed/cancelled operations create no successful
change observation.

## Benchmark evidence and explicit save

The view reads only the current session report produced by the existing benchmark
path. Applicability requires matching schema/correctness, five repetitions,
authority_effect none, exact baseline/proposed workers, last-checked raw profile
token, machine and implementation context, finite positive measurements with
consistent ranges and completion age between zero and 900 seconds. Future,
expired, missing, malformed or mismatched reports never supply current proposal
measurements. Displayed medians/classification come from the actual report.
Faster/Slower/Inconclusive remain workload-scoped, not production recommendations.

The label is **Applicable to last checked context**. Changes outside this window
require Re-check current settings; the visible-only one-second timer only renders
cached context and expires evidence. It performs no profile or source-code reads.
The timestamp describes when context was checked, not continuous file monitoring.
Neither the fingerprint nor a passing benchmark is governance attestation.

Open benchmark controls navigates to the existing Tuning & benchmarks view.
Run, cancellation, Save tested candidate and Restore previous setting remain
there, through the same checked worker path. The new view never saves or restores
automatically and adds no alternate writer. Save still rechecks current profile,
age, machine/code context and fresh serial-equality correctness. A display match
does not authorize bypassing those checks. Cleanup-blocked operations remain
blocked. Shared candidate controls disable while a System operation is busy or
cleanup is unverified.

## Required change record

1. **Invariant:** a proposed performance hint, current effective settings and
   applicable evidence must remain distinct. Stale measurements cannot become
   results for new settings; local tuning must not expand authority.
2. **Authority:** unchanged. Only the existing supported performance worker count
   is proposed. No canonical writer, kernel, provider client, signing credential,
   policy, grant or OS-setting capability is introduced/retained by the view.
3. **Canonical mutation:** none. Existing performance save/restore behavior is
   observed, not copied or bypassed. No schema/API changes, second executor,
   ledger, persistent history or new save route. Local hints remain subject to
   existing correctness and applicability checks.
4. **Evidence:** [WSL native captures, actual disposable benchmark, exact logs and source hashes](control-center-evidence/wsl-configuration/README.md).
   Tests cover defaults/fallback/rollback metadata, bounded/non-regular/changing
   profiles, candidate validation, exact report/context matches, expiry/future
   clocks, malformed reports, source/machine/profile changes, no idle reads,
   explicit save/restore observations, no inferred external history, WSL-only
   exposure, minimum layout, timer cancellation and teardown.
5. **Not proved:** production speedups, universally optimal settings, governance
   enforcement, independently authenticated profile/time/history, complete audit
   history, hard read deadlines, continuous external-change detection or full
   accessibility. Existing benchmark fingerprints/cache semantics are reused,
   not upgraded into independent provenance or loaded-code attestation.
6. **Classification:** implementation, tests, captures and benchmark output
   Recorded. Proposal Proposed; history not present in the format Unknown.
   No fabricated measurements, retrospective motivations or verification claims.
7. **Legacy reuse:** evidence_tuning profile validation/fallback, System candidate,
   benchmark/report binding and checked worker path, shared theme and navigation.
   No canonical control path copied or authority writer duplicated.
8. **Temporal transfer:** no reusable authority lesson admitted. Historical
   authority replay was not performed; no temporal-transfer proof claimed.

## Eight-pass analytical review

Purpose: compare supported WSL performance hints with appropriately scoped evidence.
Boundary: read-only context/report projection and shared ephemeral proposal;
explicit mutation remains in the existing performance-settings path.

| Pass | Finding / boundary |
| --- | --- |
| Flip | A malformed profile/report or injected text must not create a writer or plausible result. Strict existing profile validation, finite metrics, fixed enums and redacted errors bound display. Reports are session-produced, not imported. |
| Reverse | An unsupported or stale save would require bypassing the existing backend. New UI only navigates; the same checked save/restore functions run and validate again. |
| Invert | A faster disposable test is not production readiness or governance success. Equal serial modes remain explicit; saved correctness is freshly rechecked rather than trusting the displayed PASS. |
| Inside-Out | The view cannot certify source provenance, reconstruct historical reasons or treat its local clock as write-time proof. Unknown history remains Unknown; display matches only the last context check. |
| Darken | Bounded threat: external edits, future/expired reports, wrong worker pairs or invalid profiles could mislead. Tests reject these promotions and suppress stale measurements; no continuous monitoring or adversarial filesystem deadline is promised. |
| Lighten | Missing/stale settings can simply trigger the normal serial fallback. No incident, enforcement failure or performance recommendation is inferred. |
| Amplify | One snapshot, one optional last successful System observation and one visible-only display timer remain bounded. Idle updates read no files; proposal edits never save. Worker cleanup and mutual exclusion remain unchanged. |
| Negate | Reuse the existing candidate, benchmark and checked writer. A second configuration service, imported-report executor, history database, OS tuning surface or authority change is unnecessary. |

Decision: proceed to WSL validation, native inspection and draft review only.
Smallest next proof: inspect exact context/report matching and actual workload
results without applying a candidate to the user's profile. No PR merge or
production deployment is authorized by this display.
