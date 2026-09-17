"""One site-wide record strip, outside every sport's navigation and content."""
from html import escape
import re

STRIP_RE = re.compile(r'\s*<aside class="apex-site-record".*?</aside>', re.DOTALL)
CSS_VERSION = "apex-20260917-site-record"


def record_strip(summary):
    overall = summary["overall"]
    counts = [overall[key] for key in ("wins", "losses", "pushes")]
    if any(type(n) is not int or n < 0 for n in counts):
        raise ValueError("Invalid shared record counts")
    wins, losses, pushes = counts
    record = f"{wins:,}-{losses:,}-{pushes}P"
    rate = escape(overall["win_rate_display"])
    return (
        '<aside class="apex-site-record" aria-label="APEX all-sports lifetime record">'
        '<span class="site-record-label">APEX · ALL SPORTS · ALL TIME</span>'
        f'<span>Overall <strong class="mono">{record}</strong></span>'
        f'<span>Win rate <strong class="mono">{rate}</strong></span></aside>'
    )


def apply_record_strip(content, summary):
    content = STRIP_RE.sub("", content)
    marker = '<div class="apex-nav-stack">'
    if content.count(marker) != 1:
        raise ValueError("Shared record requires exactly one sport navigation stack")
    content = content.replace(marker, record_strip(summary) + "\n  " + marker, 1)
    return re.sub(r'/assets/apex\.css(?:\?[^"\s]*)?',
                  f"/assets/apex.css?v={CSS_VERSION}", content)
