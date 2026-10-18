# Upstream security repairs applied to the local Preview candidate

Claim: **Verified** for the source comparison and bounded WSL tests below; production protection remains **Unknown**. Source is the user's existing dirty working tree, not a claim that local HEAD contains earlier patches. No commit, branch switch, index update, deployed database change or service restart is part of local integration.

## Source and focused adaptations

- [Pulpo1.0 #312](https://github.com/Ironnember/Pulpo1.0/pull/312), main `dc563a089dbd9e67d6d81518d21c36916a62ec7b`: bind strict `auto_renew_enabled` to the request/order hashes, canonical intent and provider object. The Name.com pilot requires false. Independent observation must explicitly agree; absent readback stays unresolved and substitution fails without another purchase. A pre-upgrade proposal cannot silently gain new meaning. Existing Preview signed-handle reconstruction and validation are retained.
- [#278](https://github.com/Ironnember/Pulpo1.0/pull/278), `e23c75109a2ab6868e66e7840cb80e052aedaeb3`: add a positive integer `permit_ttl_ns`, default 300 seconds, included in policy identity. All kernel-issued permits expire; approval permits expire at the earlier of policy TTL and envelope expiry. Memory and SQLite enforce expiry at consumption and directive binding. Preserve Preview policy/issuer checks, in-memory transition lock and existing SQLite migration. Context-bound permits without recorded expiry fail closed. Trusted raw state fixture APIs remain compatible and do not bypass the kernel's context checks.
- [Draft #302](https://github.com/Ironnember/Pulpo1.0/pull/302), `38a23ad7a8fa7af0173b2b89d14cef8c0a6acd94`: selectively port the pure digest helper and fixed-operation `python -I -S` worker pool. No governor fork, caller environment or inherited descriptors are forwarded. Coordinator retains strict row types, chain/hash checks, cache validation and serialized verification. Preserve Preview canonical JSON helper, audit head/checkpoint integrity and existing failure behavior. Do not import unrelated setup/cache/performance rewrites.
- [Draft #315](https://github.com/Ironnember/Pulpo1.0/pull/315), `6d9e27b4898b852177edeab7f6bb7a9a2882ff7b`: port the PostgreSQL driver extra, disposable CI service and strict runner. The gate requires explicit test reset opt-in, a dedicated loopback database, a nonempty successful suite and zero skips; ambient PG routing variables are removed. Keep Preview's request-ownership tests.

Draft status and green upstream checks are not approval or deployment evidence. Upstream #288's unfinished ceremony design and #271's forked-state replay proof were not imported.

## Compatibility and authority

Policy hashes now include permit TTL, so existing approvals/permits require fresh issuance. Old canonical purchase/proposal hashes do not silently acquire the new renewal semantics; fresh trusted proposals are required. No production store was migrated or opened during these tests.

No authority is gained. Existing canonical permit issuance, replay consumption, directive binding and proposal/order commitment paths carry the narrower context; they remain controlled by the same kernel/custody transitions. New calculation workers receive audit data only, with no canonical writer object, general task API, signing material, provider route, executor or second ledger. The budget reservation helper is a read-only durable lookup. CI database mutations affect only a new synthetic test database.

## Verification

The final independent acceptance runs used WSL Ubuntu and Python 3.14.4, warnings as errors. Core: 682 tests, 680 passed, two Windows-only skips. Custody: 47 passed. Authority: 70 passed with PostgreSQL enabled, no skips. Total: **797 passed, 2 skipped**, 799 counted. Twenty-seven new tests were added; four previously skipped PostgreSQL cases now executed. Existing constitutional mutation harness: **19/19 killed**, zero invalid or surviving mutants. Those checks are separate from the suite totals.

The ordinary-permit +24-hour regression fails with `AssertionError: True is not false` on the exact pre-fix tree and passes on the candidate. New expiry coverage includes exact deadlines, replay, SQLite restart, missing expiry, directive binding and policy TTL validation/identity. Audit tests cover synthetic inherited environment/descriptors, fresh worker bootstrap, dead workers, cache type aliases and seeded tampering. Renewal tests cover exact binding, absent/mismatched observation and no second purchase.

The imported audit test initially expected a false result, but Preview's independent head validation raises earlier; the test was adapted to that stronger existing rejection. A subsequent attempted removal of a private canonical helper broke existing compatibility tests; the helper was restored. Failed attempts remain in the raw logs and are excluded from final results. An earlier core run close to the mutation harness is not relied upon; `acceptance-core` ran after mutation restoration without concurrent source mutation.

The PostgreSQL server was rootless, installed only by extracting official Ubuntu packages inside the isolated fixture, bound to 127.0.0.1 on a disposable port, and stopped afterward. Local reproduction used PostgreSQL **18.6** and psycopg **3.3.6**; CI is configured for PostgreSQL **16**. Hosted PostgreSQL 16 execution is not claimed here. Docker was unavailable to this user, so no Docker permission or system service configuration was changed. Initial helper extraction and missing-library errors were resolved before any successful database run and are not passing evidence.

Exact acceptance commands, cwd and environment are below. Raw commands/logs, preimages, candidate hashes and integration evidence are retained in the task's `outputs/upstream-fixes/` folder. All Python sources compile, authority TOML parses and `git -c core.whitespace=cr-at-eol diff --check` passes; existing CRLF file formats are preserved and new text files end in one newline.

```text
acceptance-core: exit=0; seconds=40.548
/home/spike/pulpo-security-watch-cyjg_dnl/venv/bin/python -B -X utf8 -W error -m unittest discover -s tests -v
final-custody: exit=0; seconds=1.969
/home/spike/pulpo-security-watch-cyjg_dnl/venv/bin/python -B -X utf8 -W error -m unittest discover -s custody-service/tests -v
authority-postgres: exit=0; seconds=1.181
/home/spike/pulpo-security-watch-cyjg_dnl/venv/bin/python -B -W error scripts/run_authority_postgres_proof.py
constitutional: exit=0; seconds=7.44
/home/spike/pulpo-security-watch-cyjg_dnl/venv/bin/python -B -X utf8 -W error scripts/run_constitutional_mutations.py --output /mnt/c/Users/spike/Documents/Codex/2026-10-18/referenced-chatgpt-conversation-this-is-an/outputs/upstream-fixes/constitutional.json
cwd: /home/spike/pulpo-upstream-fixes-64jg2r57/source
PYTHONDONTWRITEBYTECODE=1
PYTHONPATH=/home/spike/pulpo-upstream-fixes-64jg2r57/source:/home/spike/pulpo-upstream-fixes-64jg2r57/source/custody-service/src:/home/spike/pulpo-upstream-fixes-64jg2r57/source/authority-service/src
PULPO_AUTHORITY_TEST_ALLOW_RESET=1 (PostgreSQL run only)
PULPO_AUTHORITY_TEST_POSTGRES_DSN=postgresql://pulpo_test@127.0.0.1:38651/pulpo_authority_test (disposable run only)
```

## Adversarial transformation and temporal boundary

Flip: treat substituted fields, stale permits and helper inputs as hostile. Reverse: bind the renewal consequence and deadline before execution. Invert: registration success with absent/wrong renewal is unresolved/failure. Inside-Out: workers must not inherit governor custody; coordinator still judges audit integrity. Darken: fail on missing expiry, dead workers, malformed rows and incomplete database execution. Lighten: retain legitimate bounded execution, restart, canonical encoding and handle behavior. Amplify: seeded audit/cache repetition and two-call reconciliation cannot reopen purchase authority. Negate: narrow the existing paths without adding an authority plane or importing the broader draft branches.

Historical-transfer claim: none. The before/after expiry check uses the exact current starting tree `b4b96f568223addaf7a7c092b364843764d72b1e`; it is bounded regression evidence, not proof of reuse across unrelated historical versions. Source/adaptations and synthetic tests are Verified; upstream authors' reports are Recorded; deployed behavior is Unknown. Host/provider token revocation, external ambient I/O, OS worker confinement, state rollback/fork resistance, native Windows execution, live registrar behavior, KMS/IAM/Cloud SQL and independent ceremony provenance remain outside this proof.

## Pull request verification

The exact PR candidate was separately tested on GitHub main `44c2732ae32bcd1976996676278b56328b26ecb2`.
Its complete base tree matched `0d77ce71b0a094f62b60b11abdcf32b11f2d8348` before applying the 26-file delta.
All changed existing file preimages matched the local tested baseline after newline normalization;
the published patch history was retained and only this entry appended. No unrelated local changes
were copied. The exact PR candidate independently passed 682 core tests (two Windows-only skips),
47 custody tests and 70 authority tests against a fresh rootless PostgreSQL 18.6 server with zero
authority skips: 797 passed, 2 skipped. All 19 existing constitutional mutations were killed.
The disposable server was stopped, runtime hashes remained unchanged, and both the PR delta and
the whole staged tree passed whitespace validation. Hosted PostgreSQL 16 CI remains pending.
See [the validation manifest](2026-10-18/upstream-fixes/summary.json) for source/log hashes and
exact commands, and [the regression transcript](2026-10-18/upstream-fixes/regression-summary.log).
