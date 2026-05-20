APEXRIGOR VERCEL-ONLY CLEAN SITE

This package contains a static, Vercel-only APEX website with three physical routes:
/picks
/results
/about

It does not use Replit. It does not use hash tabs. It does not redirect About or Results to Picks.

Daily updates should change only:
/data/mlb_today.json
/data/results_archive.json

Recommended install on the server:
1. Backup /opt/apex_site.
2. Copy these files into /opt/apex_site while preserving the existing /opt/apex_site/data/mlb_today.json and /opt/apex_site/data/results_archive.json if present.
3. Deploy from /opt/apex_site with `vercel --prod --yes`.
