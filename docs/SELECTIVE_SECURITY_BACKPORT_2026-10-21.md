# Selective Pulpo1.0 security backport, October 21, 2026

Status: locally tested candidate; no push, PR, merge or deployment performed.
Preview base: `c6f6e8e9e269616857df2f36a228eccfa9af75eb`.
Branch: `backport/selective-pulpo-security-20261021`.

## Eligibility and exact source

GitHub's open-PR collection contained 83 PRs, of which 73 were non-draft.
The complete non-draft file diffs were inspected and pinned in the accompanying
evidence manifest. A final refresh found no eligibility/head changes and no
change to Preview main. Closed and draft PR content was not used.

- #307 head `cba8ce63477a708d88ce4bf869ec8d2b98315175` has an empty
  current PR file diff. Its original fix commit
  `0f6ea3a357cce911e0480e1e1cee5bc2b05dcf34` supplied the table-row
  immutability and claimed-attempt recovery regression. The same missing early
  target/reservation checks remain in eligible #311's current exact diff at
  `3db22fe80c4d407b1a117f5e6f1b43528f79910e`.
- #242 `4b656c8f06fc0679e8f6d99fc95eabf92e8412c8`: extract only the
  bounded JSON reader, authority/Name.com/Telegram response integration, and
  relevant regression tests. The same reader is split out in eligible #282
  `1b3c7f8f0d32a00fbe26df70f0eadbad43295881`.
- #285 `7e2495397b3e7607824291d1fdd650887b46d864`: extract snapshot
  file-size, depth and entry admission checks and the oversized-file regression.

## Actual behavior change

Preview already rejected altered custody handles, but resolving the full
authorization first opened a kernel whose startup wrote an audit-verification
checkpoint. The extracted test exposed that mutation on a rejected target-hash
request. Early target and original reservation checks now reject those altered
issuance fields before kernel startup. Preview's stronger persisted full
authorization/receipt validation remains in place for requests that pass these
checks; it was not replaced by upstream's simpler reference construction.

The #307 matrix covers six altered fields, execute/reconcile, and both no pending
evidence and a claimed attempt with pending evidence: 24 rejection subcases.
Each checks HTTP 409, identical rows in every SQLite table and zero provider or
observer calls. The original handle then executes once and reconciles, including
claim recovery. Existing restart, replay, receipt/commitment tamper and missing
authorization tests remain intact.

Name.com success and HTTP-error reads now stop at 1 MiB plus one byte and reject
oversize bodies. External JSON receives byte, depth, item and string bounds.
Two local integration adjustments normalize parser recursion into a resource
rejection and close Name.com's HTTP-error response; focused tests cover both.
Telegram resource rejection retains EXTERNAL_REALITY_UNKNOWN and never retries.
Snapshots reject regular files over 64 MiB before hashing, depth over 64 and
more than 100,000 entries. Existing digest cache and parallel capture paths stay
intact. Excluded files stay excluded.

## Controls deliberately retained and deferred

- #243/#278: existing permit TTL and approval-expiry cap retained. Existing
  expiry, approval replay, permit replay and restart tests passed.
- #245/#275: existing authority and shared custody 413/414/431 middleware
  retained; authority API and custody admission tests passed. No second copy.
- #247/#276: retain Preview's Windows native-handle snapshot reader and existing
  hardened publication path. Existing Windows replacement/handle-release tests
  passed. Five POSIX-only controls explicitly skipped on Windows.
- #316 `570e78c8430b73e09d9f9fcef5fa8769c60eaf48` also has an empty
  current PR file diff. Preview's Ollama adapter and tests are already present;
  they passed without downloading a model or making live inference calls.
- #311/#253 renewal binding and budget connection cleanup are already present;
  no wholesale combined import. Proposal restart/upgrade regression passed.
- #237/#281 transport trust, #238/#277 network exposure, #284 evidence durability
  and #286 proposal durability have existing/equivalent implementations.
- Performance PRs #246/#248/#251/#267/#293/#295/#297/#300/#301 are deferred.
  No performance change or performance claim was made, so no benchmark was used
  to justify one. #250/#258 consolidation branches were not imported wholesale.
- Additional ceremony/provenance schemas, proof labs, documentation and
  packaging changes were not imported. Mac-specific local-intelligence proof
  changes (#241/#287) need separate platform evidence and capability review;
  this Windows run makes no containment claim for those scripts. No container
  build, dependency audit, live provider or production proof was performed.

## Reproduced evidence

Python 3.12.14 on Windows, warnings treated as errors; dependency versions and
commands are included with the exported logs.

- Original Preview runtime plus added custody regressions: 13 methods, 24 failed
  row-equality subcase assertions. They share the first checkpoint mutation;
  these are not 24 independent vulnerabilities. Repaired custody suite: 50 passed.
- External-response probes against original Preview: 3 methods, 6 failing
  assertions, including accepted deep JSON, accepted oversized valid JSON and
  unbounded reads. Candidate: all 3 methods pass, including HTTP-error closure.
- Telegram structure regression: two failing subcases on the original runtime;
  candidate custody suite passes both with one call and UNKNOWN classification.
- Snapshot oversized-before-open probe fails on the original runtime. Candidate
  size/depth/entry/exclusion tests pass. The baseline depth/entry probe also errors
  because its patched limit constants do not exist there; that is not counted as
  a behavioral exploit reproduction.
- Focused core selection: 147 run, 142 passed, 5 POSIX-only skips.
- Entire custody-service test discovery: 50 passed.
- Authority API test selection: 9 passed.
- Total primary passing selections: 206 run, 201 passed, 5 skips. A final
  Name.com/response recheck after import ordering cleanup passed 11 methods.
- Initial sandbox-account core run hit profile-path and Windows ownership
  permission errors. The same selection passed as the normal Windows user with
  LOCALAPPDATA redirected to a task-local test folder. These initial errors are
  retained in the evidence archive; assertions were not weakened.

## Authority and adversarial transformation record

Purpose: reject malformed handles and bounded resource exhaustion before
consequential owner operations, preserving the existing governance path.
Authority gained: none. Admission is narrowed. Canonical mutations introduced or
exposed: none. Existing valid authorization, evidence projection, transmission
and reconciliation remain controlled by their original kernel/custody owners.

- Flip: hostile worker/provider metadata is bounded and checked against existing
  canonical records; no cooperative-worker assumption.
- Reverse: supplied target/reservation rejection precedes checkpoint-writing
  kernel startup; JSON bounds precede provider response interpretation.
- Invert: HTTP rejection alone does not establish immutability; table-row
  equality and adapter call counts provide the stronger test.
- Inside-Out: the canonical custodian and stores remain trusted; signed receipt
  and commitment validation is preserved. No hostile-store claim is made.
- Darken: malformed calls with pending obligations cannot flush evidence or
  mutate rows in the tested matrix; oversized/deep responses fail closed.
- Lighten: the observed custody difference was a disposable checkpoint write,
  not a demonstrated purchase or authority grant through a forged handle.
- Amplify: replay/restart/tamper tests retain one transmission; Telegram does
  not retry after ambiguous provider responses. Concurrent baseline controls
  remain part of the focused persistence/executor suites.
- Negate: reuse existing stores, middleware, executor and projection; add no
  router, ledger, authority plane or credential path.

Decision: continue to local reviewable candidate only. Verified: stated local
test outcomes and diff. Recorded: pinned GitHub eligibility and source metadata.
Proposed: admission of this branch. Unknown: production/provider consequences,
POSIX semantics on this host, arbitrary hostile-store resistance and complete
resource/host containment. JSON structural checks occur after a byte-bounded
decode; snapshot checks are frozen admission thresholds, not a general sandbox.

Temporal boundary: baseline tests reconstructed exact Preview commit
`c6f6e8e9e269616857df2f36a228eccfa9af75eb` in a detached checkout with only
candidate tests added. Original policy, synthetic credentials and budget remain
the same; no future authority was transferred. Evidence applies to this base and
candidate, not to every historical or future deployment.
