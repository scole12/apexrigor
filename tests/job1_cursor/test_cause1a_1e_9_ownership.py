"""#23 causes 1a, 1e, 9 and the NHL publish stops: each sport publishes only its own pages.

Oct 20: an NCAAF T-2 publish (8f6b771) ran the shared selector over every page and committed
NHL, NFL, MMA, NBA and MLB pages; with NBA routes not yet listed, the same rewrite failed as
"shared publisher produced unowned paths" (20 times). The rewritten ncaaf/results selector also
broke the approved-layout check in Public site integrity.
"""
import json
import re
import shutil
import subprocess
import sys

import pytest

import pubsupport
from pubsupport import ROOT, git

import site_route_owners as owners


# --- one registry, every built route has an owner ---------------------------------------------
def test_publisher_routes_come_from_the_registry_and_keep_the_nba_hotfix():
    publisher = pubsupport.load_publisher()
    assert publisher.ROUTE_PATHS == set(owners.route_paths())
    assert {"nba/index.html", "nba/results/index.html", "nba/about/index.html"} <= publisher.ROUTE_PATHS
    assert owners.owner_of("nba/results/index.html") == "NBA"


def test_every_committed_site_file_has_exactly_one_owner():
    files = git("ls-files", cwd=ROOT).splitlines()
    tooling = ("bin/", "tests/", "docs/", "tools/", ".github/", ".cursor/")
    repo_docs = {"AGENTS.md", "CLAUDE.md", "CURSOR.md", "README.md", "README_DEPLOY.txt", "vercel.json",
                 ".gitattributes", ".gitignore"}
    site = [f for f in files if not f.startswith(tooling) and f not in repo_docs and not f.startswith("JOB1_")]
    missing = [f for f in site if owners.owner_of(f) is None]
    assert len(site) > 100 and missing == []


def test_every_route_the_site_tools_write_is_declared():
    sys.path.insert(0, str(ROOT / "bin"))
    import apply_shared_sport_selector as selector
    declared = owners.route_paths()
    assert set(selector.ROUTES) | set(selector.NFL_ROUTES) | set(selector.NHL_ROUTES) <= declared
    audit = (ROOT / "bin/audit_public_site.py").read_text()
    for route in re.findall(r'root / "([a-z]+)" / "index.html"', audit):
        assert f"{route}/index.html" in declared, route


@pytest.fixture(scope="module")
def built_site(tmp_path_factory):
    site = pubsupport.site_copy(tmp_path_factory.mktemp("built") / "site")
    run = subprocess.run([sys.executable, "bin/build_vercel_output.py"], cwd=site, capture_output=True, text=True)
    assert run.returncode == 0, run.stderr[-2000:]
    return site / "public"


def test_vercel_build_passes_and_every_built_page_has_an_owner(built_site):
    pages = [p.relative_to(built_site).as_posix() for p in built_site.rglob("*.html")]
    assert "nba/index.html" in pages and "ncaaf/results/index.html" in pages
    assert [p for p in pages if owners.owner_of(p) is None] == []


def test_foreign_paths_names_other_sports_pages():
    changed = ["data/ncaaf_today.json", "ncaaf/index.html", "nhl/index.html", "index.html", "data/apex_results_summary.json"]
    assert owners.foreign_paths("NCAAF", changed) == ["data/apex_results_summary.json", "index.html", "nhl/index.html"]


# --- an NCAAF T-2 publication touches only NCAAF paths ----------------------------------------
STALE_STRIP = re.compile(r'(<span>Overall <strong class="mono">)[^<]*(</strong>)')


def t2_request(publisher, site, payload_root, day="2026-10-20"):
    token = day.replace("-", "")
    files = {
        "data/ncaaf_today.json": site / "data/ncaaf_today.json",
        "ncaaf/index.html": site / "ncaaf/index.html",
        f"data/ncaaf/{day}/NCAAF_T2_FULL_SLATE_{token}.pdf": site / f"data/ncaaf/{day}/NCAAF_T2_FULL_SLATE_{token}.pdf",
        f"data/ncaaf/{day}/NCAAF_T2_PICKS_CARD_{token}.png": site / f"data/ncaaf/{day}/NCAAF_T2_PICKS_CARD_{token}.png",
    }
    hashes = {}
    for relative, source in files.items():
        target = payload_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        hashes[relative] = pubsupport.sha(target)
    manifest = {"sport": "NCAAF", "request_id": "c" * 64, "product": "T2", "slate_date_et": day,
                "display_slate_date_et": day, "count_scope": "EXPLICIT_CANONICAL_AND_DISPLAY",
                "display_date": day, "canonical_game_count": 1, "display_game_count": 1, "issued_game_count": 1,
                "official_position_count": 2, "market_pending_game_count": 0, "internal_market_pending_game_count": 0,
                "canonical_public_payload_sha256": "d" * 64, "sealed_day_payload_sha256": "e" * 64,
                "requested_at_utc": "2026-10-20T21:00:00Z", "source_hashes": hashes}
    return publisher.Request("NCAAF", "c" * 64, manifest, payload_root, day, "T2")


def test_ncaaf_t2_publish_leaves_nhl_nba_mma_and_mlb_pages_alone(tmp_path):
    site = pubsupport.site_copy(tmp_path / "site")
    # Other sports' pages carry an older all-sports record than the shared summary (as on Oct 20).
    stale = {}
    for page in ("nhl/index.html", "nba/index.html", "mma/index.html", "index.html", "ncaaf/results/index.html"):
        path = site / page
        text, count = STALE_STRIP.subn(r"\g<1>2,147-1,954-26P\g<2>", path.read_text(encoding="utf-8"))
        assert count == 1, page
        path.write_text(text, encoding="utf-8")
        stale[page] = text
    pubsupport.commit_all(site, "older record strips on other pages")
    publisher = pubsupport.load_publisher()
    request = t2_request(publisher, site, tmp_path / "payload")
    build = publisher.build_request(request, site)
    changed = build["changed_paths"]
    assert changed and all(owners.owner_of(path) == "NCAAF" for path in changed), changed
    for page, text in stale.items():
        assert (site / page).read_text(encoding="utf-8") == text, page + " was rewritten by an NCAAF publish"


def test_ncaaf_publish_ignores_other_sports_dirty_paths(tmp_path, monkeypatch):
    publisher = pubsupport.load_publisher()
    site = pubsupport.site_copy(tmp_path / "site")
    monkeypatch.setattr(publisher, "copy_queued_payload", lambda request, worktree: None)
    monkeypatch.setattr(publisher, "ncaaf_delivery_manifest", lambda request, worktree: None)
    monkeypatch.setattr(publisher, "dirty_paths", lambda worktree: {"data/ncaaf_today.json", "nba/index.html"})
    request = publisher.Request("NCAAF", "f" * 64, {}, tmp_path / "payload", "2026-10-20", "T3")
    build = publisher.build_request(request, site)
    assert "data/ncaaf_today.json" in build["changed_paths"]
    assert "nba/index.html" not in build["changed_paths"]


# --- cause 9: Public site integrity --------------------------------------------------------------
def test_approved_ncaaf_results_layout_check_passes():
    run = subprocess.run(["node", "tests/ncaaf_results_layout.test.cjs"], cwd=ROOT, capture_output=True, text=True)
    assert run.returncode == 0, run.stdout[-1500:] + run.stderr[-1500:]
    assert "Oct 17 render.js and index.html each fail layout checks" in run.stdout
    reference = json.loads((ROOT / "tests/fixtures/ncaaf_results_layout.reference.json").read_text())
    assert reference["approved_by"] == "Scott Coleman"
