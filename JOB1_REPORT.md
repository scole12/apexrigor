# Job 1 / issue #23 ? Codex site candidate

Status: PARTIAL CANDIDATE, not ready for merge or deployment. Work is on `job1-codex`; independent tests are on `job1-tests-by-codex`, based on origin/main. No production stage, live database write, main push, merge, deployment, timer change or Docker shutdown was performed.

## Findings and changes

| Audit cause | Site implementation / evidence | Remaining verification |
| --- | --- | --- |
| 1a: NBA unowned paths | Preserved main hotfix 64f085b. `bin/sport_routes.py:21` declares active sport ownership; selector, analytics and publisher consume it. `bin/build_vercel_output.py:102` rejects every unowned built HTML route. Retained historical URLs have declared owners but cannot become active publisher outputs. | NHL runtime lives outside the two supplied repos; no live NHL request was run. |
| 1b: deployment wait | `bin/apex_shared_site_publisher.py:751` persists NCAAF publication intent, retaining its original published SHA across retries. Existing ancestor acceptance at `:1169` is retained and tested using a real local Git descendant. `:1187` performs one observation per turn and releases delivery after 30 minutes or first kickoff, with an alert and explicit non-live evidence. | Production Vercel state and real email acceptance were not exercised. |
| 1c: breaker | `:1445` counts explicit request-validation faults, excluding unrelated generators and infrastructure faults. Environment faults remain retryable and alert separately. | Error classification is deliberately conservative; unknown faults do not consume the request budget. |
| 1d: reconciliation / version skew | `:923` permits a manifest-declared supersession only with matching durable proof of zero email side effects and rejection before acceptance. Unknown or accepted deliveries remain held. `:1229` pins RESULTS email API v1, paired with the NCAAF module constant. | Existing ambiguous historical emails still need retained provider evidence; no blind resend is introduced. API mismatch fails explicitly until both reviewed versions are installed. |
| 1e: sports isolation | `:683` validates NCAAF immutable payload/delivery manifests and commits only NCAAF output; it never invokes shared page generators or whole-site builds during NCAAF publication. Explicit `--sport NCAAF` queue selection is available. Email workflow polling at `:993` observes once and yields instead of holding the shared publisher for up to six minutes; pending discovery never authorizes a resend. | The full static deployment is still globally audited by Vercel. A malformed unrelated deployment artifact can still reject a deployment; the email wait is bounded. |
| 1f: stale/dirty installed source | `:1850` requires a clean exact-tagged installed release with state outside the checkout. Publisher no longer fast-forwards installed code while publishing; disposable content worktrees still use fetched origin/main. | No installed checkout was migrated or tagged. Existing production data cleanup is an operator rollout task; this branch does not perform it. |
| 2: grader | See counterpart NCAAF report: final-dependent retry window and schema validation. | Full historical grader replay unavailable. |
| 3: roster | See NCAAF correction no-op and existing per-game isolation. | Full roster fixture replay unavailable. |
| 4: hydration budget | See NCAAF resumable content-verified endpoint cache using existing earlier sweep. | Full provider fixture replay unavailable. |
| 5: T3 snapshot / bindings | Existing singleton snapshot adapter retained. Candidate controller and both engine bindings are updated together; read-only candidate check added in NCAAF. | Complete frozen dependencies and eight-date replay are missing. |
| 6: schedule | NCAAF rearm now alerts and preserves existing timers after rejected refresh. Existing parity code already compares canonical authority rows, not the prior catalog file. | The specific rejected catalog inputs were not supplied; the parity guard remains intact. |
| 7: late T3 | NCAAF window gate allows a retry before kickoff when T2 has not sealed. | Actual late T3-to-T2 market/cutoff compatibility needs replay; no physical-time checks were weakened. |
| 8: hydration score conflict | Existing per-game quarantine retained and independently tested in NCAAF. | Full player-box fixture coverage remains incomplete. |
| 9: integrity hash | Reproduced actual `5af79c28...` vs expected `d2be6f35...`. Diff against 531aefd is the already-added NBA selector link plus normalized lifetime numbers. Only `tests/fixtures/ncaaf_results_layout.reference.json:6` changes. No HTML, CSS, renderer, table, layout or copy changes. | PR review must review this narrow hash update under the issue's explicit instruction. |

## Local verification

- Independent suite: `python -m unittest discover -s tests/job1_cross_by_codex -v`: **8/8 pass** on candidate; **1/8 pass, 5 assertion failures, 2 behavior exceptions** on origin/main plus the identical test-only commits. Descendant acceptance already passed main; the other seven reproduce missing behavior.
- Existing email reconciliation/evidence suite: **23/23 pass** under WSL with the paired NCAAF module explicitly loaded from its assigned worktree. A first unpinned import correctly failed the API-version guard; no external mail call was made.
- Existing publisher checks under WSL: isolation **1/1**, results backlog **8/8**, shared record scheduling **8/8**, MMA ownership **3/3**.
- `node tests/ncaaf_results_layout.test.cjs`: PASS, including rejection of the unwanted Oct 17 layout and lifetime-number mutation checks.
- `python bin/build_vercel_output.py`: PASS; output audit reports no errors. Existing generators run locally as part of the required build; their tracked by-products were restored and were not committed. Local build success does not prove a production deploy.
- Ruff was run on affected Python files. There are pre-existing findings in the publisher and related scripts; comparison against origin/main found **zero newly introduced findings**. New registry and cross tests pass their isolated Ruff check.
- Added branch CI workflow for the focused checks; remote results must be read separately and are not inferred from local results.

## Open acceptance items

The job is not complete: no full isolated replay for Oct 6, 9, 10, 13, 15, 17, 18, 20; required frozen NCAAF dependencies are absent; production NHL and deployed Vercel behavior are unverified; the other builder's test branch was not present when checked. No fresh Claude/Grok reviews or winner selection occurred in this builder session. The test-only branch intentionally fails against main, as requested. Reports and branch links are recorded on issue #23; Scott's approval is still required for anything live.

## GitHub evidence

Public site integrity [39510279380](https://github.com/scole12/apexrigor/actions/runs/39510279380), focused publisher regressions [39510279509](https://github.com/scole12/apexrigor/actions/runs/39510279509), and agent practice [39510279405](https://github.com/scole12/apexrigor/actions/runs/39510279405) all passed at source commit 5bcfa91. The later nonblocking email-poll change is locally verified and is submitted for a new CI run. NCAAF CI repeatedly fails before runner assignment (empty steps and runner name), including a retry; no test assertion or build step was reported. Its exact external startup cause could not be retrieved through the connector; no browser surface was available to inspect the annotation. Do not label it a test success or assume it is an Actions-minutes failure.
