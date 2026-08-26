from pathlib import Path
from datetime import datetime
import json, html, re

site = Path("/opt/apex_site")
data_path = site / "data" / "mlb_today.json"
assets = site / "assets"
assets.mkdir(exist_ok=True)

stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
asset_name = f"apex_static_final_{stamp}.js"
asset_path = assets / asset_name

d = json.loads(data_path.read_text())
games = d.get("games", [])

def esc(x):
    return html.escape("" if x is None else str(x), quote=True)

def et_minutes(raw):
    m = re.search(r"(\d{1,2}):(\d{2})\s*(AM|PM)", str(raw or ""), re.I)
    if not m:
        return 99999
    h = int(m.group(1)) % 12
    if m.group(3).upper() == "PM":
        h += 12
    return h * 60 + int(m.group(2))

def abbr(team):
    table = {
        "Philadelphia Phillies":"PHI","Pittsburgh Pirates":"PIT",
        "Toronto Blue Jays":"TOR","Detroit Tigers":"DET",
        "Baltimore Orioles":"BAL","Washington Nationals":"WAS",
        "Milwaukee Brewers":"MIL","Minnesota Twins":"MIN",
        "Miami Marlins":"MIA","Tampa Bay Rays":"TB",
        "Cincinnati Reds":"CIN","Cleveland Guardians":"CLE",
        "Boston Red Sox":"BOS","Atlanta Braves":"ATL",
        "New York Yankees":"NYY","New York Mets":"NYM",
        "Chicago Cubs":"CHC","Chicago White Sox":"CHW",
        "Texas Rangers":"TEX","Houston Astros":"HOU",
        "Kansas City Royals":"KC","St. Louis Cardinals":"STL",
        "Arizona Diamondbacks":"ARI","Colorado Rockies":"COL",
        "Los Angeles Dodgers":"LAD","Los Angeles Angels":"LAA",
        "San Francisco Giants":"SF","Athletics":"ATH",
        "San Diego Padres":"SD","Seattle Mariners":"SEA",
    }
    return table.get(team, team or "")

def safe_sentences(text):
    text = str(text or "").strip()
    if not text:
        return []
    protected = text.replace("St. Louis", "St__DOT__ Louis")
    parts = [x.strip().replace("St__DOT__ Louis", "St. Louis") for x in re.split(r"(?<=[.!?])\s+", protected) if x.strip()]
    return parts[:8]

def rationale_html(p):
    if isinstance(p.get("rationale_sentences"), list) and p["rationale_sentences"]:
        parts = [str(x).strip() for x in p["rationale_sentences"] if str(x).strip()][:8]
    else:
        parts = safe_sentences(p.get("rationale"))
    return "".join(f"<p>{esc(x)}</p>" for x in parts)

def market_label(p):
    m = str(p.get("market") or "").upper()
    if "ATS" in m:
        return "FIRST FIVE SPREAD"
    if "TOT" in m:
        return "FIRST FIVE TOTAL"
    return p.get("market") or "FIRST FIVE"

def sort_picks(picks):
    def key(p):
        m = str(p.get("market") or "").upper()
        return 0 if "ATS" in m else 1
    return sorted(picks or [], key=key)

def pick_title(p):
    title = str(p.get("pick") or "")
    line = p.get("line")
    if line not in (None, "") and str(line) not in title:
        title = (title + " " + str(line)).strip()
    return title

games = sorted(games, key=lambda g: (et_minutes(g.get("first_pitch_et")), str(g.get("matchup",""))))
position_count = d.get("position_count") or sum(len(g.get("picks", [])) for g in games)

parts = []
parts.append('<div class="wrap">')
parts.append('<div class="section-head">')
parts.append('<div><div class="eyebrow">Today\\\'s Card</div>')
parts.append(f'<div class="date-label">{esc(d.get("date",""))}</div></div>')
parts.append(f'<div class="ticker"><div class="ticker-val">{esc(position_count)}</div><div class="ticker-lbl">Daily Positions</div></div>')
parts.append('</div>')

for idx, g in enumerate(games, 1):
    away = g.get("away_team") or ""
    home = g.get("home_team") or ""
    fp = g.get("first_pitch_et") or ""
    venue = g.get("venue") or ""

    parts.append('<section class="game-card">')
    parts.append('<div class="game-head">')
    parts.append(f'<div class="game-num">{idx:02d}</div>')
    parts.append(f'<div class="game-kicker">GAME {idx:02d} · MAJOR LEAGUE BASEBALL</div>')
    parts.append(f'<div class="matchup">{esc(abbr(away))} @ {esc(abbr(home))}</div>')
    parts.append(f'<div class="venue">{esc(venue)}</div>')
    parts.append(f'<div class="first-pitch"><div class="first-label">FIRST PITCH</div><div class="first-time">{esc(fp)}</div></div>')
    parts.append('</div>')

    for p in sort_picks(g.get("picks", [])):
        tier = str(p.get("tier") or p.get("conviction") or "MODEL").upper()
        parts.append('<div class="pick-row">')
        parts.append(f'<div class="market-label">{esc(market_label(p))}</div>')
        parts.append(f'<div class="pick-title">{esc(pick_title(p))}</div>')
        parts.append(f'<div class="tier">{esc(tier)}</div>')
        parts.append(f'<div class="rationale">{rationale_html(p)}</div>')
        parts.append('</div>')

    parts.append('</section>')

parts.append('<div style="display:flex;justify-content:space-between;color:rgba(255,255,255,.65);font-size:11px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;padding-top:1rem"><span>APEX MLB · FIVE-INNING MARKETS · BET-ALL FLAT 1U</span><span style="font-family:Georgia,serif;font-style:italic;text-transform:none;font-size:15px">apexrigor.com</span></div>')
parts.append('</div>')

final_html = "\n".join(parts)

js = f"""(function(){{
  var html = {json.dumps(final_html)};
  function apply(){{
    var root = document.getElementById("app");
    if (!root) return;
    root.innerHTML = html;
    document.documentElement.setAttribute("data-apex-static-final", "{stamp}");
  }}
  window.APEX_STATIC_FINAL_RENDER = apply;
  if (document.readyState === "loading") {{
    document.addEventListener("DOMContentLoaded", apply);
  }} else {{
    apply();
  }}
  apply();
  setTimeout(apply, 250);
  setTimeout(apply, 1000);
  setTimeout(apply, 2000);
}})();
"""

asset_path.write_text(js)

tag = f'<script src="/assets/{asset_name}"></script>'

for p in [site / "index.html", site / "picks" / "index.html"]:
    if not p.exists():
        continue
    s = p.read_text()
    s = re.sub(r'\s*<script src="/assets/apex_static_final_[^"]+\.js"></script>', '', s)
    if "</body>" in s:
        s = s.replace("</body>", tag + "\n</body>", 1)
    else:
        s += "\n" + tag + "\n"
    p.write_text(s)
    print("INJECTED", p, tag)

total = 0
short = 0
times = []
for g in games:
    times.append(et_minutes(g.get("first_pitch_et")))
    for p in g.get("picks", []):
        total += 1
        if len(safe_sentences(p.get("rationale"))) < 6:
            short += 1

print("STATIC_FINAL_WRITTEN")
print("ASSET", f"/assets/{asset_name}")
print("date", d.get("date"), "games", len(games), "positions", position_count)
print("game01", games[0].get("first_pitch_et"), games[0].get("matchup"))
print("chronological", times == sorted(times))
print("total_picks", total, "positions_with_less_than_6_sentences", short)
