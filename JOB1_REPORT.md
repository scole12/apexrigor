# Job 1 (issue #23): Claude Code builder report, apexrigor

Branch `job1-claude` (built on origin/main 6959ba3, with the 64f085b NBA hotfix kept).
Cross tests for the other builder: branch `job1-tests-by-claude`, `tests/job1_cross_by_claude/`.
The NCAAF pipeline half of the job is in `scole12/apex_ncaaf` on the same branch names; its
`JOB1_REPORT.md` covers causes 2 to 8.

**Not pushed.** Both repos' push URL is set to `DISABLED_NO_PUSH_ACTIONS_MINUTES`, so
`git push origin job1-claude` and `git push origin job1-tests-by-claude` fail. I left that guard
in place: Actions minutes are at 100% and every push would start billed runs. The branches are
committed locally and ready to push once Scott re-enables pushing.

## Causes and fixes in this repository

| # | Root cause (from the audit and the code) | Fix | Tests |
|---|---|---|---|
| 1a | NCAAF T-3/T-2 publishes ran `apply_shared_sport_selector`, `apply_*_web_analytics` on the whole site and committed every rewritten page (8f6b771 changed NHL, NFL, MMA, NBA and MLB pages). With NBA routes unlisted this was "shared publisher produced unowned paths". | One owner registry, `bin/site_route_owners.py:15` (`SPORT_ROUTES`, `owner_of` :64). `ROUTE_PATHS` comes from it (`bin/apex_shared_site_publisher.py:69`; the NBA hotfix routes stay). NCAAF T-3/T-2/RESULTS/DISPLAY commit only queued NCAAF bytes. Shared chrome is applied by the Vercel build into `public/` and checked in a disposable copy (`validate_site_build` :787). Any non-NCAAF path is refused (:775). | `test_cause1a_1e_9_ownership.py`: every committed site file and every built page has exactly one owner; the site tools' routes are declared; a real NCAAF T-2 `build_request` on a site copy with stale record strips leaves NHL/NBA/MMA/MLB pages unchanged. |
| 1b | On a retry the publisher reports `PUBLISHED_NO_CONTENT_CHANGE` with the newest origin/main, which other sports keep moving. The T-2 email then waited for that tip to deploy (`DEPLOYMENT_NOT_REQUEST_DESCENDANT`, almost daily). The wait was bounded only by first kickoff. | The email waits for the commit that carries the request's own files (`ncaaf_request_commit` :1339), pinned at the first wait. A deploy of any later commit counts (`commit_contains` :1320, which fetches an unknown deployed commit instead of reading "not descendant"). The wait is bounded to 20 min (`NCAAF_T2_SITE_WAIT_MAX_SECONDS` :72). After that the email goes out with an owner alert (`EMAIL_SENT_AFTER_BOUNDED_SITE_WAIT` :1406). | `test_cause1b_1c_1d_1f_delivery.py`: retry after an NHL push; later deploy; bounded wait with one alert; deployed commit not yet fetched. |
| 1c | `MAX_FAILURES_PER_DAY=10` counted every failure, so the Oct 20 NBA bug skipped NCAAF for 24 h. | Failures are classified as REQUEST, GLOBAL or WAIT (:1844). Only REQUEST failures count (`failure_counts` :1653, `_failure_tally` :1666). `GlobalPublicationFault` (:96) and `GLOBAL_FAULT_MARKERS` (:78) cover other-sport paths, push races, network and Vercel. The marker list includes the Oct 20 "unowned paths" text, so the existing droplet failure records stop counting without manual archiving. Global faults alert once (and again at 30). | 12 Oct-20 unowned-path failures never skip the request; push race not counted; the request's own failure is still capped at 10. |
| 1d | (a) A re-issued request for the same stage/date was blocked by the old request's workflow run (`NCAA_EMAIL_RECONCILIATION_REQUIRED`, 33 times Oct 8-10). (b) A deploy version skew raised `AttributeError: delivery_lock`. (c) A push to main was rejected by a race. | (a) Earlier request directories in `publication_queue/<date>/<product>/` are superseded when `current.json` names the new request (`ncaaf_superseded_request_ids` :1000). Only their *finished* runs are set aside, and never one whose email was delivered (`ncaaf_email_delivered` :1023), so there is no duplicate email. (b) Interface pin `apex.ncaaf.results_email.v2` (:75, `require_results_email_interface` :1418). A mismatch is a named global fault. A module from before the constant is accepted only with every required function, so the two repos can deploy in either order. (c) A rejected push is a global `PUSH_RACE_ORIGIN_ADVANCED` fault (:883); the next run rebuilds on the new origin/main. | Supersede, in-progress still blocks, not-current request, delivered email keeps blocking, interface skew, real local-remote push race. |
| 1e | Other sports blocked NCAAF in three ways: shared tooling rewrites (1a); a site build already broken on main failed the NCAAF request; and the NCAAF email wait slept up to 6 min inside the one publisher lock. | 1a fix. `validate_site_build` (:787) reruns the build on the request's base commit; a failure main already has (same error) does not block the request, and a different one is a global fault. `wait_for_ncaaf_workflow` (:1102) reads the run once and yields with a waiting error. A just-dispatched run gets a 10-min visibility grace and is never re-sent (:1489). | Build failure on main does not block; a request-caused build failure fails closed; workflow is read without sleeping; a dispatched run not yet listed waits and is not re-sent. |
| 1f | /opt/apex_site ran a publisher 25 commits behind origin/main, with uncommitted data. | `deploy_check` (:1754) compares the running publisher with origin/main's copy and lists dirty code/data paths. It is reported in every run's output, with one owner alert per day when stale. It does not move the live data out of the git tree (see below). | Stale publisher and an uncommitted `data/mlb_today.json` are reported against a local remote. |
| 9 | Not Actions minutes: "Verify approved NCAA results layout" failed because 8f6b771 (an NCAAF publish) rewrote `ncaaf/results/index.html`'s shared selector (added the NBA link from PR #11). | Root cause removed by 1a. The layout lock now masks the shared all-sports selector, the same way it already masked the record-strip numbers (`tests/ncaaf_results_layout.test.cjs:15`). The reference hash is updated, and a new self-check proves the page Scott approved on Oct 18 (48451c3) still matches (:50). The Oct 17 regressions still fail. **This changes the approved-layout reference, so it needs Scott's explicit approval in the PR.** | `test_approved_ncaaf_results_layout_check_passes`; `node tests/ncaaf_results_layout.test.cjs` passes. |
| NHL | NHL publish stops: the NCAAF commit changed `nhl/*` pages bound to NHL's own publication. | 1a: an NCAAF publication can no longer change any `nhl/` path. | Covered by the 1a build test (NHL pages unchanged). |

No page body, CSS or layout was changed. The only HTML-facing change is the CI layout lock's masking rule and reference hash.

## Tests

- Own regression tests: `tests/job1_claude/` with 26 tests. All 26 pass on `job1-claude` (Linux, Python 3.12).
  On origin/main 6959ba3, 14 fail and the 8 ownership tests error at import (the registry does
  not exist there). The 4 that pass are guards for behaviour main already had: a later deploy
  counts, an in-progress superseded run blocks, a non-current request supersedes nothing, and a
  delivered email keeps blocking.
- Existing suites on `job1-claude`: `test_ncaaf_email_reconciliation` (23, run with the apex_ncaaf
  module present), `test_ncaaf_t2_site_live_email`, `test_ncaaf_publisher_isolation`,
  `test_ncaaf_results_backlog`, `test_ncaaf_shared_record_scheduling`,
  `test_ncaaf_display_same_date_revision` and `test_mma_shared_publisher_contract` all pass.
  Several tests in `test_nba_*`, `test_nfl_*`, `test_total_apex_results` and two
  `test_oct01_reliability::CatchUp` tests fail identically before and after my change. They read
  `/opt/apex_site` or need droplet state.
- Public site integrity, run locally: all four steps pass (publisher isolation/backlog, layout,
  `bin/build_vercel_output.py`, record scheduling).
- Vercel build: `python3 bin/build_vercel_output.py` passes on Linux for `job1-claude`. It also
  passed for main and the 7 commits before it, so the Vercel production failure could not be
  reproduced as a build error.
- CI: `.github/workflows/job1-tests.yml` runs ruff (E9,F) and every `tests/job1_*` directory on
  push and pull request.
- Cross tests for Codex (`job1-tests-by-claude`, `tests/job1_cross_by_claude/`, 8 tests): 8/8 fail
  on origin/main; 8/8 pass on `job1-claude`. Run locally against `origin/job1-codex`: 6 pass and
  2 fail (the T-2 email retry after another sport's push; the re-issued request blocked by its
  superseded request's finished run).
- Codex's cross tests run locally against `job1-claude`: 8/8 fail. They load single functions out
  of the source by name and assert Codex's own helper names, receipt keys and status strings (for
  example `_is_request_failure`, `site_wait_started_utc_ms`, `EMAIL_RELEASED_AFTER_BOUNDED_SITE_WAIT`,
  `WORKFLOW_PENDING` from a specific function, a `supersedes_request_id` manifest field). Two
  pointed at real gaps, and I fixed both in a685607 (non-blocking workflow read; no supersede
  after a delivered email).

## Not verified / remaining

- Nothing was pushed, so no GitHub Actions run exists for these branches. Results above are local.
- No access to the Vercel team (the connector returned 403), so the failed production deployment's
  own log was not read. The local build passes; whether Vercel's failure was the build, the layout
  check or the deploy wait (1b) is not confirmed.
- The NHL publisher is not in either repository. I verified that NCAAF can no longer change NHL
  pages, not the NHL lane itself.
- 1f is detection only. Moving MLB's live files (`data/apex_results_summary.json`, tier archives,
  `data/mlb_today.json`) out of the git tree, and deploying /opt/apex_site from a clean tag, are
  droplet changes outside this job's rules.
- Global-fault and wait alerts use the existing `apex_notify` path; delivery was not exercised.
- No GitHub issue comment was posted (no `gh` login on this machine).
