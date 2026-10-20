# Recorded WSL session-restore evidence

Scope, authority boundaries and eight-pass analytical review: [WSL session restore](../../WSL_SESSION_RESTORE.md).

## Validation

- Ubuntu WSL Python 3.14.4: 124 focused tests passed with warnings treated as errors.
- Ubuntu WSL core: 841 tests passed, with two platform-specific skips and no resource warnings.
- Exact logs: [focused](ubuntu-focused.log), [core](ubuntu-core.log), [core summary](ubuntu-core-summary.json).
- [Hashes](source-hashes.json) bind LF-normalized tested source/test files, exact logs and the main base commit.
- Private-file tests cover atomic save/replace/forget, interrupted replacement cleanup, permissions, malformed/duplicate/oversize data, symlink/hardlink/FIFO/directory rejection, unsafe parents and unsupported/extra fields.
- UI tests reopen a new ControlCenter from actual saved preferences while all owner-export readers are blocked, then exercise navigation, ticks and Pause/Resume. Only explicit Re-read loads a private temporary Evidence export and enables its normal visible polling. Forget preserves current selection/cache and the source export; closing does not recreate preferences. Other checks cover no default/autosave writes, invalid-file defaults, narrow layout, WSL gating and Tk-variable teardown.

## Native inspection

All captures are native WSLg images cropped to the application window. Before uses the previous local WSL commit c4522fe7eccdc3840fb97acc45ff72b03c6bf969, whose application files match the recorded main base.

- [Before](pulpo-wsl-session-before.png): existing System view before Session setup.
- [After](pulpo-wsl-session-after.png): new opt-in controls, startup selectors, graph ranges and privacy/forget semantics. Nothing saved by default.
- [Restored](pulpo-wsl-session-restored.png): a clearly titled saved-location fixture starts on Evidence with a remembered, missing export path. No owner export exists or is read. Metrics remain Unknown, the range is restored to 15 minutes, and explicit Re-read is available.
- [Narrow](pulpo-wsl-session-narrow.png): 640 × 600 content window with wrapping tabs, startup choices and vertical scrolling.
- [Narrow controls](pulpo-wsl-session-narrow-controls.png): the same labeled fixture shows its temporary path, restored ranges, unchecked status and explicit Remember/Forget actions without horizontal clipping.

Fixture preferences exist only in isolated private temporary Linux directories, removed when each inspection window closes. No personal saved setup, credential, health result or source content is included in this evidence. No normal user preferences or performance settings were saved by inspection. These Recorded checks do not prove source availability/authenticity, enforcement, full accessibility, encryption, comprehensive filesystem-race protection or crash durability. Windows qualification is outside this WSL-only increment.
