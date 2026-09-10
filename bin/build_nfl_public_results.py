#!/usr/bin/env python3
"""Render NFL results from the published issuance and immutable grade archive.

FOREVER: no Flat/1u/UNITS chrome. Public NFL results UI is MLB-mirrored SEASON RECORD via render.js.
"""
from collections import Counter, defaultdict
from datetime import datetime
from html import escape
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo


def record(rows):
    counts = Counter(row['result'] for row in rows)
    value = f"{counts['WIN']}-{counts['LOSS']}"
    if counts['PUSH']:
        value += f"-{counts['PUSH']}P"
    return value


def table(headers, rows):
    head = ''.join(f'<th scope="col">{escape(h)}</th>' for h in headers)
    body = ''.join('<tr>' + ''.join(f'<td>{escape(str(cell))}</td>' for cell in row) + '</tr>' for row in rows)
    return f'<div class="nfl-results-scroll"><table class="results"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def build(root: Path):
    summary = json.loads((root / 'data/nfl_results_summary.json').read_text())
    archive = json.loads((root / 'data/nfl_results_archive.json').read_text())
    positions = {}
    for issuance in archive['issuances']:
        day = issuance.get('game_date') or datetime.fromisoformat(issuance['issued_at'].replace('Z', '+00:00')).astimezone(ZoneInfo('America/New_York')).date().isoformat()
        for position in issuance['positions']:
            positions[position['position_id']] = {**position, 'game_date': day}
    rows = []
    for grade in archive['grades']:
        for settlement in grade['settlements']:
            rows.append({**positions[settlement['position_id']], **settlement})
    assert len(rows) == summary['graded_position_count']
    assert len({r['position_id'] for r in rows}) == len(rows)
    days = defaultdict(list)
    for row in rows:
        days[row['game_date']].append(row)
    latest = max(days) if days else None
    decided = sum(row['result'] in {'WIN', 'LOSS'} for row in rows)
    wins = sum(row['result'] == 'WIN' for row in rows)
    win_rate = f'{100 * wins / decided:.1f}%' if decided else '—'
    body = '<style>.nfl-results-scroll{overflow-x:auto;margin-bottom:28px}.nfl-results-scroll table{width:100%;min-width:620px}.nfl-results-scroll td,.nfl-results-scroll th{text-align:left;padding:14px 12px}.nfl-results-section{margin:28px 0}.nfl-results-note{color:#999;line-height:1.6}.nfl-results-metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:#333;border:1px solid #333;margin:20px 0}.nfl-results-metrics>div{background:#000;padding:22px 15px}.nfl-results-metrics strong{display:block;font-size:25px;margin-top:8px}.nfl-results-metrics span{color:#aaa;font-size:11px;text-transform:uppercase;letter-spacing:.08em}@media(max-width:640px){.nfl-results-metrics{grid-template-columns:repeat(2,1fr)}} </style>'
    body += '<div class="section-head"><div class="title">NFL RESULTS</div><div class="meta mono">2026 SEASON · AS ISSUED</div></div>'
    body += '<div class="nfl-results-metrics">' + ''.join(f'<div><span>{label}</span><strong class="mono">{value}</strong></div>' for label, value in [('Record', record(rows)), ('Win Rate', win_rate), ('Graded Picks', str(len(rows)))]) + '</div>'
    body += f'<p class="nfl-results-note">{len(positions)} issued · {len(rows)} graded · {len(positions)-len(rows)} pending. Results use the selections, FanDuel prices and APEX probabilities published before kickoff.</p>'
    body += '<section class="nfl-results-section"><div class="section-head"><div class="title">PERFORMANCE BY RATING</div></div>'
    tiers = []
    for tier in ('WEAK', 'MODERATE', 'STRONG', 'ELITE'):
        selected = [r for r in rows if r.get('rating_tier') == tier]
        tiers.append([tier, len(selected), record(selected)])
    body += table(['As-issued rating', 'Graded', 'Record'], tiers) + '</section>'
    body += '<section class="nfl-results-section"><div class="section-head"><div class="title">DAILY ARCHIVE</div></div>'
    body += table(['Slate date (ET)', 'Graded', 'Record'], [[day, len(values), record(values)] for day, values in sorted(days.items(), reverse=True)]) + '</section>'
    for day, values in sorted(days.items(), reverse=True):
        body += f'<section class="nfl-results-section"><div class="section-head"><div class="title">SLATE DETAIL — {escape(day)}</div><div class="meta mono">{len(values)} GRADED PICKS</div></div>'
        details = []
        for row in sorted(values, key=lambda r: (r['game_id'], r['market'], r['position_id'])):
            evidence = row['settlement_evidence']
            actual = evidence.get('official_value', evidence.get('official_total'))
            if actual is None:
                actual = f"{evidence['covered_margin']:+g} vs spread"
            details.append([row.get('display_selection') or row['selection'], f"{row['issued_american_price']:+d}", f"{100*row['issued_probability']:.1f}%", row.get('rating_tier', '—'), actual, row['result']])
        body += table(['As-issued pick', 'FanDuel', 'APEX', 'Rating', 'Actual', 'Result'], details) + '</section>'
    if not rows:
        body += '<p class="nfl-results-note">No graded picks yet.</p>'
    path = root / 'nfl/results/index.html'
    text = path.read_text()
    text = re.sub(r'<main class="picks-page">.*?</main>', '<main class="picks-page">' + body + '</main>', text, count=1, flags=re.S)
    text = re.sub(r'<script>NFLBoard\.mount.*?</script>', '', text, flags=re.S)
    text = re.sub(r'<script>\s*const esc=.*?</script>', '', text, flags=re.S)
    text = text.replace('ONLY SEALED ISSUANCE IS ELIGIBLE FOR GRADING', 'AS-ISSUED PICKS · OFFICIAL GAME AND PLAYER RESULTS')
    text = text.replace('AS-ISSUED PICKS · OFFICIAL GAME AND PLAYER RESULTS · ZERO UNITS', 'AS-ISSUED PICKS · OFFICIAL GAME AND PLAYER RESULTS')
    path.write_text(text)
    # A concise result link remains visible on Picks after the slate flips.
    picks = root / 'nfl/index.html'
    text = re.sub(r'<!-- NFL_LATEST_RESULTS_START -->.*?<!-- NFL_LATEST_RESULTS_END -->', '', picks.read_text(), flags=re.S)
    if latest:
        values = days[latest]
        text = text.replace('<!-- NFL_BOARD_START -->', f'<!-- NFL_LATEST_RESULTS_START --><p class="nfl-ledger-note">{latest} results: {record(values)} · {len(values)} graded picks. <a href="/nfl/results">View results</a></p><!-- NFL_LATEST_RESULTS_END -->\n<!-- NFL_BOARD_START -->', 1)
    picks.write_text(text)
    print(f'NFL_PUBLIC_RESULTS={len(rows)} RECORD={record(rows)}')


if __name__ == '__main__':
    build(Path('/opt/apex_site/public'))
