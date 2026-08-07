"""APEX — Single source of truth for the HTML <head> branding block.

DO NOT inline favicon/OG/manifest tags in any builder. Always import
get_head_block() from this module. If branding needs to change, change it
HERE — every page picks it up on next build.

REQUIRED TAGS (the contract):
  - <title>
  - <link rel="icon" type="image/svg+xml" href="/assets/favicon.svg">
  - <link rel="apple-touch-icon" href="/assets/apple-touch-icon.png">
  - <meta property="og:image" content="https://apexrigor.com/assets/og-image.png">
  - <meta name="twitter:card" content="summary_large_image">
  - <link rel="stylesheet" href="/assets/apex.css">
"""

REQUIRED_MARKERS = [
    'favicon.svg',
    'apple-touch-icon',
    'og:image',
    'twitter:card',
    'apex.css',
]

CACHE_VER = "apex-20260629-tier-perf"

META_DESC_DEFAULT = (
    "APEX is a quantitative forecasting platform for multi-sport model-driven picks, results, and research."
)
OG_DESC_DEFAULT = "Quantitative forecasting for model-driven sports markets."


def get_head_block(
    page_title: str,
    page_path: str = "/",
    page_desc: str = "",
    og_desc: str = "",
) -> str:
    """Return the full APEX branding head block for a given page.

    page_title: e.g. "APEX — Picks"
    page_path:  e.g. "/" or "/results" or "/about" (no domain)
    page_desc:  meta description (falls back to sport-neutral default)
    og_desc:    OG/Twitter card description (falls back to sport-neutral default)
    """
    if not page_desc:
        page_desc = META_DESC_DEFAULT
    if not og_desc:
        og_desc = OG_DESC_DEFAULT
    url = f"https://apexrigor.com{page_path}"
    v = CACHE_VER
    return f'''<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0,viewport-fit=cover">
<title>{page_title}</title>
<meta name="description" content="{page_desc}">
<link rel="icon" type="image/svg+xml" href="/favicon.svg?v={v}">
<link rel="icon" type="image/x-icon" href="/favicon.ico?v={v}" sizes="32x32">
<link rel="icon" type="image/png" sizes="32x32" href="/favicon-32x32.png?v={v}">
<link rel="icon" type="image/png" sizes="16x16" href="/favicon-16x16.png?v={v}">
<link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png?v={v}">
<link rel="manifest" href="/site.webmanifest?v={v}">
<meta name="theme-color" content="#000000">
<meta name="apple-mobile-web-app-title" content="APEX">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta property="og:type" content="website">
<meta property="og:site_name" content="APEX">
<meta property="og:title" content="{page_title}">
<meta property="og:description" content="{og_desc}">
<meta property="og:url" content="{url}">
<meta property="og:image" content="https://apexrigor.com/og-image.png?v={v}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="APEX — Quantitative Forecasting">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{page_title}">
<meta name="twitter:description" content="{og_desc}">
<meta name="twitter:image" content="https://apexrigor.com/og-image.png?v={v}">
<link rel="stylesheet" href="/assets/apex.css?v={v}">'''

def verify_branding(html: str) -> tuple:
    """Return (ok: bool, missing: list[str]). True if every required marker is present."""
    missing = [m for m in REQUIRED_MARKERS if m not in html]
    return (len(missing) == 0, missing)
