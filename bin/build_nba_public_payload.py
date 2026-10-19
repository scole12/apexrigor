#!/usr/bin/env python3
"""Render only NBA public files from the stored, public-safe NBA contract.

No database, engine, outcome source, tier calculation or clock-based deletion.
The upstream publisher owns issuance, settlement and rollover; see nba/DATA_INTERFACE.md.
"""
import html
import json
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo
from pathlib import Path
from apply_shared_sport_selector import navigation, STACK_RE

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    value = json.loads((ROOT / 'data' / name).read_text(encoding='utf-8'))
    if value.get('sport') != 'NBA':
        raise ValueError('NBA sport boundary')
    return value


def esc(value):
    return html.escape('Not yet available' if value is None else str(value))


def build():
    today = load('nba_today.json')
    archive = load('nba_results_archive.json')
    positions = today['positions']
    if today['status'] != 'ISSUED' and positions:
        raise ValueError('unissued positions must be empty')
    cards = {}
    for p in positions:
        if p['market'] not in ('ATS', 'TOTALS') or p.get('tier') not in (None, 'Weak', 'Moderate', 'Strong', 'Elite'):
            raise ValueError('invalid stored market/tier')
        probability = p.get('probability')
        if probability is not None and (isinstance(probability, bool) or not 0 <= probability <= 1):
            raise ValueError('probability must be a stored fraction in [0, 1]')
        if probability is None:
            probability = 'Not yet available'
        else:
            probability = format(Decimal(str(probability)) * 100, 'f')
            probability = (probability.rstrip('0').rstrip('.') if '.' in probability else probability) + '%'
        key = p.get('game_id') or p['position_id']
        cards.setdefault(key, [p.get('matchup'), []])[1].append('<section class="market-panel"><div class="market-label">' + esc(p['market']) + '</div><div class="market-panel-head"><span class="pick-headline">' + esc(p.get('selection')) + ' · ' + esc(p.get('role')) + '</span><span class="tier-badge">' + esc(p.get('tier')) + '</span></div><p>Prediction: ' + esc(p.get('prediction')) + ' · Probability: ' + probability + '</p><p>FanDuel line: ' + esc(p.get('line')) + ' · Price: ' + esc(p.get('price')) + '</p><div class="rationale-copy"><p>' + esc(p.get('rationale')) + '</p></div></section>')
    release = datetime.fromisoformat(today['release_at'])
    if release.tzinfo is None:
        raise ValueError('release_at requires timezone')
    release = release.astimezone(ZoneInfo('America/New_York')).strftime('%Y-%m-%d %H:%M Eastern')
    picks = '<section class="nhl-board" aria-label="NBA today card"><div class="section-head picks-board-head"><div class="title" id="slate-title">TODAY\'S CARD</div><div class="meta mono">Slate ' + esc(today['slate_date']) + ' · ' + esc(today['scheduled_games']) + ' planned games · ' + esc(today['planned_positions']) + ' planned positions · ATS · TOTALS</div></div><p class="mono">Common release ' + release + ' · six hours before FIRST tip</p><p>' + esc(today['status']) + ' · ' + str(len(positions)) + ' issued positions</p><div class="picks-board" id="games" aria-live="polite">'
    for key, (matchup, panels) in cards.items():
        picks += '<article class="game-module" data-game="' + esc(key) + '"><header class="game-header"><div class="game-meta"><h2 class="game-matchup">' + esc(matchup) + '</h2></div></header><div class="market-grid">' + ''.join(panels) + '</div></article>'
    if not positions:
        picks += '<article class="game-module"><div class="market-grid"><section class="market-panel" data-position-state="UNISSUED"><div class="market-label">STATUS</div><div class="market-panel-head"><span class="pick-headline">UNISSUED — AWAITING T-6</span></div><div class="rationale-copy"><p>No NBA picks have been issued. Original predictions, probabilities, FanDuel lines and prices, tiers and rationale will appear when available.</p></div></section></div></article>'
    picks += '</div></section>'
    rows = [p for slate in archive['slates'] for p in slate['positions']]
    if len({p['position_id'] for p in rows}) != len(rows):
        raise ValueError('duplicate archived position_id')
    if any(p['market'] not in ('ATS', 'TOTALS') for p in rows):
        raise ValueError('invalid archived market')
    def record(items):
        w, l, p = (sum(x.get('result') == result for x in items) for result in ('W', 'L', 'P'))
        if not w + l + p:
            return 'Not yet available'
        rate = f'{100*w/(w+l):.1f}%' if w+l else 'Not yet available'
        return f'{w}-{l}-{p}P · {rate}'
    results = '<div class="section-head"><div class="title">NBA RESULTS</div></div><p>Win% = W / (W + L). Pending games remain tracked. Tiers are retained as issued.</p>'
    groups = [('Season', rows)]
    for key in ('slate_date', 'week_start'):
        for value in sorted({s[key] for s in archive['slates']}):
            groups.append((('Daily ' if key == 'slate_date' else 'Week ') + value, [p for s in archive['slates'] if s[key] == value for p in s['positions']]))
    for label, items in groups:
        results += '<section><h2>' + esc(label) + '</h2><p>' + str(len(items)) + ' positions tracked · ' + str(sum(p.get('result') not in ('W','L','P','V') for p in items)) + ' pending</p>'
        for market in ('ATS', 'TOTALS'):
            market_rows = [p for p in items if p['market'] == market]
            results += '<h3>' + market + '</h3><p>' + record(market_rows) + '</p>'
            for tier in ('Weak','Moderate','Strong','Elite'):
                results += '<p>' + tier + ' · ' + record([p for p in market_rows if p.get('tier') == tier]) + '</p>'
        results += '</section>'
    if not archive['slates']:
        results += '<p>Daily and weekly records: Not yet available. No settled NBA observations.</p>'
    about = '<div class="section-head"><div class="title">APEX NBA</div></div><p>Two pregame engines: full-game ATS and full-game totals. Both use a bet-all policy: one spread position and one Over or Under for each eligible game, without forced Favorite or Underdog leans. No moneyline positions.</p><p>Pregame source types include schedules, team and player statistics, availability reports and captured FanDuel markets. Source availability does not establish that a field is a validated model input. The accepted engine input manifest determines validated inputs; that manifest is not yet available for this public lane.</p><p>Evaluation requires chronological four-score comparison with timestamp-aligned market comparators. Accepted score definitions and validation results are not yet available here. No achieved performance is claimed.</p><p>All games share the slate release six hours before FIRST tip. Original stored predictions, probabilities, FanDuel lines and prices, Weak/Moderate/Strong/Elite tiers and rationale are preserved. Missing values remain unavailable. Results use as-issued tiers and retain unfinished games through morning rollover.</p><p>Forecasts do not guarantee outcomes.</p>'
    about = about.replace('chronological four-score comparison', 'chronological four-score comparison (residual MAE, log-loss, calibration error, Brier)')
    import re
    for section, body in (('picks',picks),('results',results),('about',about)):
        target = ROOT / 'nba' / ('' if section == 'picks' else section) / 'index.html'
        template = (ROOT / 'nhl' / ('' if section == 'picks' else section) / 'index.html').read_text(encoding='utf-8')
        template = template.replace('NHL','NBA').replace('/nhl','/nba')
        template = STACK_RE.sub(navigation('nba', section, True, True, True), template, count=1)
        template = re.sub(r'<main\b[^>]*>.*?</main>', '<main class="picks-page">' + body + '</main>', template, flags=re.S)
        template = re.sub(r'<script src="/nba/results/render.js[^<]*</script>', '', template)
        template = re.sub(r'<meta name="description"[^>]*>', '<meta name="description" content="NBA pregame ATS and totals forecasts and as-issued results.">', template)
        template = template.replace('data-picks-state="unissued"', 'data-picks-state="' + today['status'].lower() + '"').replace('data-public-issuance="false"', 'data-public-issuance="' + str(today['status'] == 'ISSUED').lower() + '"')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(template, encoding='utf-8')


if __name__ == '__main__':
    build()
