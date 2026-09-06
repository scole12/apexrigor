#!/usr/bin/env python3
"""Universal APEX elite black grader email HTML wrapper.

LAW 2026-09-06 (Scott): every sport 7am daily grader email uses the MMA/UFC
elite professional black HTML format. Gold-standard copied from
/opt/apex_mma/bin/apex_mma_grader_parity.py::_html_email (CORRECTED Sep6
Hooker vs Parnasse 10W-4L multipart/alternative send).

Presentation only. No science, engines, settlement, or sealed-card changes.
"""
from __future__ import annotations

import html
import re

BLACK = "#000000"
WHITE = "#ffffff"
PAPER = "#f4f4f4"
GRAY = "#969696"
LINE = "#464646"
LINK = "#7EB6FF"  # light-blue links only (never plain white Gmail body)

LAW_ID = "UNIVERSAL_GRADER_EMAIL_ELITE_BLACK_20260906"
LAW_SOURCE = "MMA/UFC CORRECTED Sep6 10W-4L gold-standard"


def _linkify_escaped(escaped: str) -> str:
    """Turn escaped URLs / APEXRIGOR.COM into light-blue anchors."""

    def repl_url(match: re.Match[str]) -> str:
        url = match.group(0)
        return f'<a href="{url}" style="color:{LINK};text-decoration:underline">{url}</a>'

    out = re.sub(r"https://[^\s<>&\"]+", repl_url, escaped)

    def repl_site(match: re.Match[str]) -> str:
        label = match.group(0)
        return (
            f'<a href="https://apexrigor.com" '
            f'style="color:{LINK};text-decoration:underline">{label}</a>'
        )

    out = re.sub(r"(?<![\"'>])APEXRIGOR\.COM", repl_site, out)
    return out


def body_paragraphs_html(plain_body: str) -> str:
    chunks = (plain_body or "").strip().split("\n\n")
    parts: list[str] = []
    for chunk in chunks:
        if not chunk.strip():
            continue
        escaped = html.escape(chunk).replace("\n", "<br>")
        parts.append(f"<p>{_linkify_escaped(escaped)}</p>")
    return "".join(parts)


def elite_grader_email_html(
    subject: str,
    plain_body: str,
    *,
    receipt_sha256: str | None = None,
    footer_note: str | None = None,
) -> str:
    """Wrap sport-specific plain-text grader body in the locked black HTML shell.

    Exact chrome from MMA gold: black bg, centered A P E X + letter-spacing,
    QUANTITATIVE FORECASTING, thin #464646 divider, white/left body, footer.
    """
    paragraphs = body_paragraphs_html(plain_body)
    if footer_note:
        footer = _linkify_escaped(html.escape(footer_note))
    elif receipt_sha256:
        footer = (
            _linkify_escaped(html.escape("APEXRIGOR.COM"))
            + f" · Receipt {html.escape(str(receipt_sha256))}"
        )
    else:
        footer = _linkify_escaped(html.escape("APEXRIGOR.COM"))

    return (
        f'<!doctype html><html><head><meta charset="utf-8">'
        f"<title>{html.escape(subject)}</title></head>\n"
        f'<body style="margin:0;background:{BLACK};color:{WHITE};'
        f'font-family:Arial,Helvetica,sans-serif">'
        f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" '
        f'style="background:{BLACK}"><tr><td align="center">'
        f'<table role="presentation" width="680" cellspacing="0" cellpadding="0" '
        f'style="max-width:680px;border-collapse:collapse">'
        f'<tr><td align="center" style="padding:42px 24px 8px;font-size:38px;'
        f'font-weight:700;letter-spacing:12px;color:{WHITE}">A P E X</td></tr>'
        f'<tr><td align="center" style="color:{GRAY};font-size:13px;'
        f'padding:0 24px 20px">QUANTITATIVE FORECASTING</td></tr>'
        f'<tr><td style="border-top:1px solid {LINE};padding:26px 28px;'
        f'color:{PAPER};font-size:14px;line-height:1.55;text-align:left">'
        f"{paragraphs}</td></tr>"
        f'<tr><td align="center" style="border-top:1px solid {LINE};padding:20px;'
        f'color:{GRAY};font-size:12px">{footer}</td></tr>'
        f"</table></td></tr></table></body></html>"
    )


def looks_like_elite_html(body: str) -> bool:
    s = (body or "").lower()
    return (
        ("background:#000" in s or "background:#000000" in s)
        and "a p e x" in s
        and "quantitative forecasting" in s
    )


def ensure_elite_html(
    subject: str,
    body: str,
    *,
    receipt_sha256: str | None = None,
) -> tuple[str, str]:
    """Return (text_plain, html). If body is already elite HTML, derive text."""
    raw = body or ""
    stripped = raw.lstrip().lower()
    if stripped.startswith("<!doctype html") or stripped.startswith("<html"):
        if looks_like_elite_html(raw):
            text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", raw)
            text = re.sub(r"(?is)<br\s*/?>", "\n", text)
            text = re.sub(r"(?is)</p>", "\n\n", text)
            text = re.sub(r"(?is)<[^>]+>", " ", text)
            text = re.sub(r"[ \t]+", " ", text)
            text = re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"
            return text, raw
        raise ValueError("grader_email_html_refused_non_elite_chrome")
    html_body = elite_grader_email_html(
        subject, raw, receipt_sha256=receipt_sha256
    )
    plain = raw if raw.endswith("\n") else raw + "\n"
    return plain, html_body
