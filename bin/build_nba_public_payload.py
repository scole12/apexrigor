#!/usr/bin/env python3
"""Read sealed NBA facts with --date YYYY-MM-DD; otherwise render the saved payload.

No engine execution, forecast calculation or database writes.
"""
import argparse
import html
import json
import os
import sys
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo
from pathlib import Path
from apply_shared_sport_selector import navigation, STACK_RE

ROOT = Path(__file__).resolve().parents[1]
ET = ZoneInfo('America/New_York')


def reader_url():
    name = 'APEX2_SUPABASE_READER_DB_URL'
    url = os.environ.get(name)
    if not url and sys.platform == 'win32':
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Environment') as key:
                url = winreg.QueryValueEx(key, name)[0]
        except OSError:
            pass
    if not url:
        raise ValueError(name + ' is required for --date')
    return url


def public_position(row):
    """Map stored fields only; absent model details stay null."""
    if any(str(row.get(k, '')).startswith('baseline:') for k in ('engine', 'engine_version')):
        raise ValueError('baseline predictions cannot be published')
    market = {'spread': 'ATS', 'total': 'TOTALS'}[row['market']]
    return dict(position_id=str(row['prediction_id']), game_id=str(row['game_id']),
                market=market, matchup=row['away'] + ' @ ' + row['home'],
                selection=(row['home'] if row['side'] == 'a' else row['away'])
                if market == 'ATS' else ('Over' if row['side'] == 'a' else 'Under'),
                role=row.get('role'), prediction=row.get('prediction'),
                probability=row['p'], probability_side='home' if market == 'ATS' else 'Over',
                line=row['line'], price=row['price_a'] if row['side'] == 'a' else row['price_b'],
                tier=row.get('tier'), rationale=row.get('rationale'),
                engine=row['engine'], engine_version=row['engine_version'],
                issued_at=row['issued_at'].isoformat(),
                result={None: None, 'win': 'W', 'loss': 'L', 'push': 'P', 'void': 'V'}[row['outcome']])


def refresh(day):
    import psycopg
    from psycopg.rows import dict_row
    # Explicit read-only transaction, one consistent snapshot and bounded queries.
    try:
        conn = psycopg.connect(reader_url(), connect_timeout=20, row_factory=dict_row,
                               options='-c default_transaction_read_only=on -c statement_timeout=20000')
    except psycopg.Error:
        raise RuntimeError('NBA reader connection failed; credentials withheld') from None
    with conn:
        conn.execute('set transaction isolation level repeatable read, read only')
        games = conn.execute("""select g.game_id, a.full_name away, h.full_name home,
            g.scheduled_tip, g.season_type from core.games g
            join core.teams a on a.team_id=g.away_team_id
            join core.teams h on h.team_id=g.home_team_id
            where coalesce((g.scheduled_tip at time zone 'America/New_York')::date,g.game_date)=%s
            order by g.scheduled_tip,g.game_id""", (day,)).fetchall()
        rows = conn.execute("""select p.*, a.full_name away, h.full_name home, gr.outcome
            from ops.predictions p join core.games g on g.game_id=p.game_id
            join core.teams a on a.team_id=g.away_team_id
            join core.teams h on h.team_id=g.home_team_id
            left join ops.grades gr on gr.prediction_id=p.prediction_id
              and not exists(select 1 from ops.grades n where n.supersedes=gr.grade_id)
            where p.season_id=%s and p.game_date<=%s
              and p.issued_at is not null and p.issued_at<=CURRENT_TIMESTAMP
              and p.engine not like 'baseline:%%'
              and p.engine_version not like 'baseline:%%'
            order by p.game_date,p.game_id,p.market""",
            (day.year - (day.month < 8), day)).fetchall()
    positions = [public_position(r) for r in rows]
    current = [p for r, p in zip(rows, positions) if r['game_date'] == day]
    stamp = datetime.now(timezone.utc).isoformat()
    today = dict(sport='NBA', schema_version='APEX_NBA_PUBLIC_V1',
                 status='ISSUED' if current else 'UNISSUED', slate_date=day.isoformat(),
                 release_at=datetime.combine(day, time(9), ET).isoformat(),
                 schedule_updated_at=stamp, scheduled_games=len(games),
                 games=[dict(game_id=str(g['game_id']), away=g['away'], home=g['home'],
                             tip=g['scheduled_tip'].isoformat() if g['scheduled_tip'] else None,
                             season_type=g['season_type']) for g in games], positions=current)
    slates = {}
    for row, position in zip(rows, positions):
        d = row['game_date']
        slate = slates.setdefault(d, dict(slate_date=d.isoformat(),
            week_start=(d-timedelta(days=d.weekday())).isoformat(), positions=[]))
        slate['positions'].append(position)
    archive = dict(sport='NBA', slates=list(slates.values()))
    # Records are counts of sealed grades only. No observations means unavailable.
    summary = dict(sport='NBA', status='AVAILABLE' if positions else 'UNAVAILABLE',
                   source='sealed predictions and grades only', markets={})
    for market in ('ATS', 'TOTALS'):
        mine = [p for p in positions if p['market'] == market]
        w, l, pushes = (sum(p['result'] == r for p in mine) for r in ('W', 'L', 'P'))
        summary['markets'][market] = dict(w=w, l=l, p=pushes, win_pct=100*w/(w+l) if w+l else None)
    for name, payload in (('today', today), ('results_archive', archive), ('results_summary', summary)):
        (ROOT / 'data' / ('nba_' + name + '.json')).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f'NBA_READER date={day} games={len(games)} positions={len(current)} archive={len(positions)} readonly=on')


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
    for p in positions + [p for s in archive['slates'] for p in s['positions']]:
        if any(str(p.get(k, '')).startswith('baseline:') for k in ('engine', 'engine_version')):
            raise ValueError('baseline predictions cannot be published')
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
        probability_label = ' (' + esc(p['probability_side']) + ')' if p.get('probability_side') else ''
        line_label = ' (home)' if p.get('probability_side') == 'home' else ''
        cards.setdefault(key, [p.get('matchup'), []])[1].append('<section class="market-panel"><div class="market-label">' + esc(p['market']) + '</div><div class="market-panel-head"><span class="pick-headline">' + esc(p.get('selection')) + ' · ' + esc(p.get('role')) + '</span><span class="tier-badge">' + esc(p.get('tier')) + '</span></div><p>Prediction: ' + esc(p.get('prediction')) + ' · Probability: ' + probability + probability_label + '</p><p>FanDuel line: ' + esc(p.get('line')) + line_label + ' · Price: ' + esc(p.get('price')) + '</p><div class="rationale-copy"><p>' + esc(p.get('rationale')) + '</p></div></section>')
    day = date.fromisoformat(today['slate_date'])
    games = today.get('games', [])
    label = day.strftime('%A, %B ') + str(day.day) + day.strftime(', %Y')
    picks = '<section class="nhl-board" aria-label="NBA today card"><div class="section-head picks-board-head"><div class="title" id="slate-title">TODAY\'S CARD</div><div class="meta mono" id="slate-meta">' + label.upper() + ' · ' + str(len(games)) + ' GAMES · ' + str(len(positions)) + ' POSITIONS · ATS · TOTALS</div></div><div class="picks-board" id="games" aria-live="polite">'
    # Fixtures may supply sealed positions without schedule metadata; real refreshes
    # always include every scheduled game, even when it has no issued position.
    schedule = list(games)
    known = {str(g['game_id']) for g in schedule}
    schedule += [dict(game_id=k, matchup=v[0], tip=None) for k,v in cards.items() if str(k) not in known]
    for index, game in enumerate(schedule, 1):
        key = str(game['game_id'])
        number = f'G{index:02d}'
        matchup = game.get('matchup') or (game['away'] + ' @ ' + game['home'] if game.get('away') and game.get('home') else None)
        tip = datetime.fromisoformat(game['tip']).astimezone(ET).strftime('%I:%M %p').lstrip('0') + ' ET' if game.get('tip') else 'Tip: Not yet available'
        picks += '<article class="game-module" data-game="' + number + '" data-nba-game-id="' + esc(key) + '"><header class="game-header"><div class="game-num mono">' + number + '</div><div class="game-meta"><h2 class="game-matchup">' + esc(matchup) + '</h2><p class="game-pitchers mono">' + esc(game.get('season_type', 'regular').replace('_', ' ').upper() + (' SEASON' if game.get('season_type', 'regular') == 'regular' else '')) + '</p></div><div class="game-time mono">' + esc(tip) + '</div></header><div class="market-grid">'
        if key in cards:
            picks += ''.join(cards[key][1])
        else:
            picks += '<section class="market-panel" data-position-state="UNISSUED"><div class="market-label">STATUS</div><div class="market-panel-head"><span class="pick-headline">UNISSUED — AWAITING 9:00 AM RELEASE</span><span class="tier-badge tier-badge--moderate">SCHEDULED</span></div><div class="rationale-copy"><p>Listed from the official schedule. No sealed FanDuel-issued APEX positions yet.</p></div></section>'
        picks += '</div></article>'
    updated = datetime.fromisoformat(today['schedule_updated_at']).astimezone(ET).strftime('%I:%M %p').lstrip('0')
    picks += '</div><p class="nhl-updated mono" id="nba-refresh-status">SCHEDULE UPDATED ' + updated + ' ET</p></section>'
    rows = [p for slate in archive['slates'] for p in slate['positions']]
    if len({p['position_id'] for p in rows}) != len(rows):
        raise ValueError('duplicate archived position_id')
    if any(p['market'] not in ('ATS', 'TOTALS') for p in rows):
        raise ValueError('invalid archived market')
    about = '<div class="section-head"><div class="title">APEX NBA</div></div><p>Two pregame engines: full-game ATS and full-game totals.</p><p>Both use a bet-all policy: one spread side and one Over or Under for every eligible game with captured FanDuel markets. No moneyline positions.</p><p>All games share one 9:00 AM ET release. The issued card keeps the original picks, lines, prices and confidence tiers.</p><p>The all-sports banner shows the Total Apex record. NBA results use only sealed NBA picks and their grades, with tiers kept as issued.</p>'
    import re
    for section, body in (('picks',picks),('results',None),('about',about)):
        target = ROOT / 'nba' / ('' if section == 'picks' else section) / 'index.html'
        template = (ROOT / 'nhl' / ('' if section == 'picks' else section) / 'index.html').read_text(encoding='utf-8')
        template = template.replace('NHL','NBA').replace('/nhl','/nba')
        template = STACK_RE.sub(navigation('nba', section, True, True, True), template, count=1)
        if section != 'results':
            template = re.sub(r'<main\b[^>]*>.*?</main>', '<main class="picks-page">' + body + '</main>', template, flags=re.S)
        template = re.sub(r'<meta name="description"[^>]*>', '<meta name="description" content="NBA pregame ATS and totals forecasts and as-issued results.">', template)
        template = template.replace('data-picks-state="unissued"', 'data-picks-state="' + today['status'].lower() + '"').replace('data-public-issuance="false"', 'data-public-issuance="' + str(today['status'] == 'ISSUED').lower() + '"')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(template, encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--date', type=date.fromisoformat, help='refresh from the read-only NBA database')
    args = parser.parse_args()
    if args.date:
        refresh(args.date)
    build()
