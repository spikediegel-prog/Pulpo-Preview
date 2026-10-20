# Recorded guided WSL setup evidence

Scope and required eight-point/eight-pass review: [Guided WSL setup](../../WSL_GUIDED_SETUP.md).

## Tests

- Ubuntu WSL Python 3.14.4: 127 focused tests passed with warnings treated as errors.
- Ubuntu WSL core: 844 tests passed, with two platform-specific skips and no resource warnings.
- Exact logs: [focused](ubuntu-focused.log), [core](ubuntu-core.log), [core summary](ubuntu-core-summary.json).
- [Source/log hashes](source-hashes.json) bind the LF-normalized tested files, exact log bytes and main base commit.
- UI tests traverse all five guide steps while all source readers and preference saves are blocked. They verify page handoffs/return position, optional connector skip without clearing selections, no unsolicited startup navigation, fixed action/step bounds, narrow sizing/keyboard focus, checklist switching and teardown. A separate test explicitly reads an invalid private temporary Evidence export and confirms that the guide reports the actual failed local read and Unknown service health without copying raw error text or the source path. Source files and preferences remain unchanged by guide navigation.

## Native visual inspection

All screenshots are native WSLg captures cropped to the application window. Before uses the previous local WSL commit 7b524f8680a757a1283a621a280d09ead774a882, whose application code matches the recorded main base. Inspection runs use separate private temporary profile directories, removed when their windows close. No owner export, credential, performance setting or personal preferences were written during inspection.

- [Before](pulpo-wsl-guide-before.png): the existing Setup Readiness checklist.
- [After](pulpo-wsl-guide-after.png): step one explains local/source observations, Unknown and enforcement boundaries.
- [Sources](pulpo-wsl-guide-sources.png): native Next-step navigation to step two, with both sources unselected and read times/freshness Unknown; no fabricated measurements or completion state.
- [Handoff](pulpo-wsl-guide-handoff.png): native Open Governance navigation, preserving step two in the Return to guide banner. Return was clicked and visually confirmed to resume step two.
- [Minimum size](pulpo-wsl-guide-narrow.png): 640 × 600 content window, existing System tabs and wrapped guide text.
- [Narrow controls](pulpo-wsl-guide-narrow-controls.png): vertical scrolling exposes Previous/Next/Close and the guide-position explanation without horizontal clipping.

These Recorded tests/captures do not authenticate sources, establish service health, prove complete accessibility or attest governance, production readiness or a completed setup. Windows qualification is outside this WSL-only increment.
