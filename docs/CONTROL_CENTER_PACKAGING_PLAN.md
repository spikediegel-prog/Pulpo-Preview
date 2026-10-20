# Control Center packaging plan

Recorded scope decision: 2026-10-20. Status: Proposed; not implemented or
validated by this planning note.

The first WSL-only implementation is now prepared for review; see
[WSL recovery package](WSL_RECOVERY_PACKAGE.md) for its actual behavior and limits.
Updates, general version rollback and the Windows maintenance wizard remain
deferred. This note does not assert a published or deployed installer.

## Current priority: WSL Control Center

Focus installation and recovery development on the application inside an
operator-selected WSL Ubuntu distribution. A native Windows Control Center
installer is deferred.

First increment: a versioned WSL application package supporting installation,
repair/reinstallation and removal, with launch instructions that do not require
Git commands. Preserve saved user settings by default. Keep any settings reset
separate, explicit and backed up. Never remove the WSL distribution as part of
application repair or removal.

Install application files separately from user data and existing development
checkouts. Define and test ownership of every installed path before implementing
removal. Repair must work when Control Center cannot launch. Diagnose missing
dependencies, invalid settings and WSL graphical-display failures separately;
replacing application files does not necessarily repair WSL graphics.

Later WSL increments: explicit version updates, previous-version rollback and a
diagnostic report the operator can review before sharing. Validate fresh install,
repeated repair, interrupted installation and removal while preserving user data
before describing a package as ready for distribution.

Packaging must not create a governance owner, change canonical policy/state,
touch evidence databases or signing credentials, or infer verified enforcement
from successful installation. No merge, release publication or deployment is
authorized by this note.

## Deferred: Windows Control Center development

When native Windows Control Center development resumes, revisit a downloadable
Setup & Repair wizard with Install/Open, Repair/Reinstall, Update, Roll back,
Uninstall and Troubleshoot options. Keep repair available independently of the
main application, preserve settings and evidence, and require explicit choice
for a settings reset.

Review the existing Windows packaging scripts at that time; their current
presence does not establish that a full maintenance wizard already exists.
Windows installer technology, publisher signing, distribution and update trust
remain design decisions for that future work.
