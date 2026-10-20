# NBA publication from the Geekom

After sealing picks and sending the T-6 email, and after grading and sending the
07:00 email, the NBA 2.0 run calls the same command synchronously:

```powershell
python bin/publish_nba.py --date YYYY-MM-DD --checkout C:\Users\scliu\apex2_site\apexrigor
```

Run it from a checkout containing this publisher (after this PR is merged).
Pass the intended NBA slate date explicitly; the grade run can use the current
ET date because the reader also rebuilds the season archive through that date.
No timer or droplet execution is required. Python needs psycopg and timezone data.
The existing `APEX2_SUPABASE_READER_DB_URL` environment variable (or Windows user
environment entry), Git credentials and Geekom Vercel CLI login are prerequisites.
No credential values are logged.

The dedicated clone must be clean and have the canonical origin. Missing clones
are created. Only that clone is fetched and reset to origin/main; unrelated
worktrees are never reset. The reader uses a consistent read-only database
transaction and excludes `baseline:*` engines and versions. Same-day graded
positions leave Picks and remain in Results; pending archive positions retain
their existing Results behavior. No presentation or settlement rules change.

Only `data/nba_today.json`, `data/nba_results_archive.json`, and
`data/nba_results_summary.json` can be committed. A timestamp-only refresh is a
no-op. The author/committer is APEX NBA publish <noreply@anthropic.com>.
A non-fast-forward push gets one fetch/rebase/retry; a conflict aborts the rebase
and fails without force-pushing or discarding the local commit.

Main publication requests a Vercel production deployment of the exact final
pushed SHA using the site's existing v13 Git source route. The command checks
READY plus the apexrigor.com alias for at most five minutes, then fetches the
production NBA page and compares all three live JSON payloads with the clone.
This bounded readiness check is part of the command, not a timer or background job.
Exit 0 means published, unchanged, or a successful explicitly requested dry run;
exit 1 identifies the failed step. Stdout is one JSON line with commit,
deployment_id and ready_time (null when no deployment occurs), plus status.

For an inspection that cannot commit, push, or deploy:

```powershell
python bin/publish_nba.py --date 2026-10-20 --checkout C:\Users\scliu\apex2_site\apexrigor --branch nba/publish-dryrun --dry-run
```

The diff goes to stderr, the result to stdout, and the generated payload changes
are restored after showing the diff so the clone stays clean. Without `--dry-run`,
a non-main `--branch` commits/pushes only that branch and still never deploys.
Production deployment has not been exercised by this dry run. If a production
step fails after push, retain its SHA/deployment ID and reconcile the existing
deployment before rerunning; a subsequent unchanged build does not redeploy.

Offline checks:

```powershell
python tests/test_nba_publish.py
python tests/test_nba_public.py
node tests/nba_results_scope.test.cjs
```
