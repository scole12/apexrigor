# APEX public site

This is the single canonical source repository for the public site at
`apexrigor.com`.

The production path is:

1. GitHub repository `scole12/apexrigor`, branch `main`
2. Vercel project `apexrigor` (`prj_eZTtqClkwx7IcE7NhVAK6UFmBnnB`)
3. Cloudflare registrar/DNS and Cloudflare Web Analytics

The public site is static. The active route outputs are `index.html`,
`picks/index.html`, and `results/index.html`; their source builders live in
`bin/`. Current public JSON required to reproduce the deployment is committed.
Provider credentials, local Vercel linkage, historical droplet backups, and
staged/backup data files are deliberately excluded.

## Validation

Run:

```sh
python3 bin/audit_public_site.py
```

The audit verifies route files, exact APEX icon consistency, manifest coverage,
and the Cloudflare Web Analytics cardinality. All three public routes must have
either zero beacons (owner activation pending) or exactly one each. Mixed or
duplicate states fail.

## Cloudflare Web Analytics

The deployment build reads the public Web Analytics site token from
`CLOUDFLARE_WEB_ANALYTICS_SITE_TOKEN`. When it is present,
`bin/apply_cloudflare_web_analytics.py` installs exactly one beacon in each
active public route. When it is absent, the build leaves the pages unmodified
and reports `OWNER_ACTION_REQUIRED`; it never inserts a placeholder token.

No public beacon belongs on `ops.apexrigor.com`. The operations application is
maintained separately under `/opt/apex_ops` and is protected by Cloudflare
Access.

## Deploy

Production normally deploys from GitHub after the existing Vercel project is
connected to this repository. A deliberate manual rollback can deploy the
verified C06 source archive from the same project, but must not create another
Vercel project.
