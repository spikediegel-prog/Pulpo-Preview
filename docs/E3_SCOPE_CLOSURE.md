# E3 Ubuntu/Linux bounded scope closure

2026-10-29 (America/Phoenix): the agreed E3 Ubuntu engineering test scope is
complete. This is fixture/candidate qualification, not production certification,
publication, merge or deployment authorization.

Preview implementation `6563cc2ace4e7535d49aa8c4b44ce9665252833d` ran 39
migration/persistence tests and the [real historical state handoff](E3_STATE_UPGRADE.md).
The exact unchanged legacy checkpoint
`12d07e37a34c979fc054872299191bb26c8ad387` created a synthetic database; the
current owner retained its audit prefix, verified the chain and refused spent
permit replay after migration and restart. Unknown future schema was rejected
without rewrite. Database downgrade is unsupported.

The companion Control Center branch additionally qualified per-user install,
upgrade/repair/application rollback, killed-upgrade recovery and uninstall without
changing synthetic owner state. It ran 73 app/package/public-release checks at
`4f4dab56f5c39a0d7178fd14b50932ca9d9a1841` (50 app/preferences/archive/launcher
regressions plus 23 release checks), five package-probe boundary checks and ten
genuine privileged cases at `0f7657b004c40b4aab32e4d416d4bbaac2307e51`. Root-owned
application protection, dependency refusal, repair, upgrade/app rollback,
remove/purge and generated-root cleanup passed. Historical overlapping suite
counts must not be added together.

The human created/used the publisher credential outside the governed workspace.
The agent independently checked only its public certificate/signature against
the fingerprint supplied by the human:
`597A00790B96D7B18C9291C7A99CBE51CC00179D`.
The exact Control Center candidate `0.1.0~e3.2`, source
`5308c65a6f8eff00a3595ba090b019fa7848e8ce`, has SHA-256
`015829b1ae744eef9ebb7b759365d77c720e92c61e30dae75c21a9a092031cff`.
Independent verification at Unix `1793328259` succeeded; the public completion
record also reports signing-agent stop command success. Public evidence:
`/home/spikediegel/pulpo-e3-evidence-20261029/release-verification/publisher-candidate/publisher-independent-verification.json`.
No private signing material, raw permit or canonical database was exported.

The signature authenticates that selected distribution candidate at that time;
it grants no canonical governance authority, legal/upstream endorsement or
production permission. The statement expires at Unix `1793932165`; later release
work requires fresh verification/current public revocations and independent pin
confirmation. No signed Preview kernel distribution or automatic release pipeline
is claimed by a Control Center candidate signature.

Production installation/dependency provisioning, deployed service soak, broader
platform versions, physical durability and whole-valid-database rollback remain
unqualified. Customer external storage, backup, retention and external-copy
integrity remain outside scope. No third-party certification is claimed or needed
for this bounded engineering closure.

Doctrine: invariant and canonical authority unchanged; no observer writer or
second kernel/ledger. Only existing owner transitions affect disposable test
state. Evidence above is Verified/Recorded within its bounds; untested claims
remain Unknown. Reuse: canonical migration/persistence, existing app maintenance,
public archive validator and GnuPG. Temporal transfer retains exact historical
SHAs; no future credentials/approvals enter the old checkpoint. Flip/Reverse
distinguish forward migration from unsupported state downgrade; Invert rejects
corrupt/unknown state and wrong/expired/revoked signatures; Inside-Out preserves
the human signing boundary; Darken fails closed on missing authority/tools;
Lighten confines effects to fixtures/public review; Amplify covers transactional
concurrency and bounded inputs; Negate avoids another governance or publishing
service. Review and test success grant no release/deployment authority.
