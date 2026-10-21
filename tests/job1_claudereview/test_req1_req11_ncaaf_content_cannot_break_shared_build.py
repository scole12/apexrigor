"""#23 hard rule (one sport can never block another) and item 11 (a content
change can't crash the build).

The branch removed every build check from the NCAAF publication path. An NCAAF
page that the Vercel audit rejects is therefore accepted, committed and pushed
to main; the production build then fails for every sport until someone repairs
the NCAAF page by hand. Checking NCAAF's own pages is not checking another
sport, so the publisher must refuse such a page before it reaches main.
"""
from __future__ import annotations

import re

import pytest
import reviewsupport

T2_REQUESTED = "2026-10-20T21:00:30Z"


def _break_ncaaf_page(site):
    """An NCAAF-only content defect the shared audit rejects: the page lost its viewport tag."""
    page = site / "ncaaf" / "index.html"
    text = page.read_text(encoding="utf-8")
    broken, count = re.subn(r'<meta[^>]*name="viewport"[^>]*>', "", text)
    assert count == 1, "fixture: the NCAAF viewport tag was not found once"
    page.write_text(broken, encoding="utf-8")


@pytest.fixture
def publisher(tmp_path, monkeypatch):
    module = reviewsupport.load_publisher()
    monkeypatch.setattr(module, "STATE_ROOT", tmp_path / "state")
    monkeypatch.setattr(module, "NCAAF_QUEUE", tmp_path / "queue")
    return module


def test_vercel_build_rejects_the_broken_ncaaf_page(tmp_path):
    """Control: the shared build really fails on this NCAAF-only change."""
    site = reviewsupport.site_copy(tmp_path / "site")
    _break_ncaaf_page(site)
    built = reviewsupport.vercel_build(site)
    assert built.returncode != 0
    assert "audit_public_site.py" in built.stdout + built.stderr


@pytest.mark.parametrize("product", ["T2", "DISPLAY"])
def test_ncaaf_publication_refuses_a_page_that_breaks_the_shared_build(publisher, tmp_path, monkeypatch, product):
    site = reviewsupport.site_copy(tmp_path / "site")
    # The queued payload carries the broken NCAAF page; everything else is real.
    monkeypatch.setattr(publisher, "copy_queued_payload", lambda request, worktree: _break_ncaaf_page(worktree))
    monkeypatch.setattr(publisher, "ncaaf_delivery_manifest", lambda request, worktree: None)
    payload = tmp_path / "payload"
    payload.mkdir()
    request = publisher.Request(
        "NCAAF", "c" * 64,
        {"requested_at_utc": T2_REQUESTED, "source_hashes": {"ncaaf/index.html": "0" * 64}},
        payload, "2026-10-20", product,
    )
    try:
        accepted = publisher.build_request(request, site)
    except Exception as error:  # noqa: BLE001 - any refusal before the push is correct
        assert "NCAA" in str(error) or "audit" in str(error).lower() or "build" in str(error).lower()
        return
    # Accepted: these paths would be committed and pushed to main. Prove the push breaks production.
    assert "ncaaf/index.html" in accepted["changed_paths"]
    built = reviewsupport.vercel_build(site)
    assert built.returncode == 0, (
        "NCAAF publication accepted ncaaf/index.html, but the shared Vercel build of the "
        "pushed tree fails:\n" + (built.stdout + built.stderr)[-1500:]
    )
