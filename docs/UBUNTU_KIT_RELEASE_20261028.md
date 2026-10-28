# Ubuntu kit release scope and authority review

The October 28 kit packages current merged main with a narrowly scoped Linux
listener parser backport and cryptography 50.0.2. The standalone Control Center
is the separately published Preview 15, with unchanged artifact bytes. The kit
targets Ubuntu x86_64 and CPython 3.12 and includes offline core and authority
verifier wheels. It contains no service container, real credential or canonical
user state and starts no service or provider connection.

## Required change record

1. Invariant or failure: unsupported Linux listener enumeration must remain
   unknown/error rather than becoming an empty successful proof. The kit must
   install a consistent patched authority-verifier dependency.
2. Authority delta: no authority gained. Listener evidence acceptance narrows;
   the cryptography patch preserves the existing approval-verifier interface.
3. Canonical mutations: none introduced or exposed. The parser has no socket,
   policy, permit, backend or execution capability. Synthetic tests use the
   existing kernel boundaries; no private authority material is used.
4. Success and adversarial evidence: exact tests and artifact hashes accompany
   the release. Parser regressions cover unsupported protocol/header/tcp6 rows,
   valid-prefix plus bad row, collector propagation, CLI exit 2 with no new
   evidence file, and valid empty output. Dependency resolution must agree for
   root, service proof and reviewed constraints. Required CI must pass before
   merge; final offline installation and dependency audit must pass before
   publication. At this initial commit these release checks remain pending.
5. Limits: synthetic parsing does not prove deployed containment or network
   performance. Offline installation does not prove production authority,
   native installer elevation, every Ubuntu version or hostile-host security.
   The broader container-scanning findings in PR #48 remain unresolved and are
   not waived. Service images and optional MCP dependencies are not shipped.
6. Classification: implementation Proposed until required checks and merge;
   exact executable results Verified only for their recorded runtime and SHA;
   logs and prior PR evidence Recorded; deployment enforcement Unknown.
7. Reused sources: parser/test backport from PR #53 commit
   0fd6ed17d4c72e7a8223d8ec551de2917f28a1cc, preserving its attribution. The
   original draft targets independent preview and is not merged or retargeted.
   The cryptography 50.0.2 version was previously tested in PR #48; this narrow
   patch receives fresh tests and does not import that PR's control paths,
   image remediation, admission exceptions or incomplete scan result.
8. Temporal transfer: the same unsupported-row fixtures were evaluated against
   exact main 74aae79c4fd7410c610f281a00e00c6258881d60 and the exact PR #53
   source; base silently discards all three and the candidate rejects all
   three. No historical authority, credentials or budgets are transferred.
   Dependency behavior receives fresh paired tests; no universal historical
   compatibility or organizational-learning claim is made.

## Adversarial transformation review

Flip: collector output is untrusted. Reverse: reject unsupported rows before
report construction. Invert: an empty parsed set is not success when input is
unrecognized. Inside Out: the collector cannot ratify its own correctness.
Darken: a valid prefix followed by an invalid row rejects the whole proof.
Lighten: benign format drift can explain rejection; it is not evidence of an
attack. Amplify: repeated bad rows cannot accumulate partial success and no
socket, firewall or route changes occur. Negate: reuse the parser and existing
verifier; add no scanner, privilege, router, signer or second evidence plane.

Continue decision: validate this main-targeting patch through normal required
checks. Preserve PRs #48, #52, #53 and #54 independently. A kit release is a
tester prerelease, not a deployment or production-readiness assertion.
