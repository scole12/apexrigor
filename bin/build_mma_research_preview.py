#!/usr/bin/env python3
"""Render an explicitly unvalidated model preview; never an official issuance."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import argparse, hashlib, html, json, math, re
from _mma_public import head, hero, navigation, close, write
ROOT=Path(__file__).resolve().parents[1]
def esc(value): return html.escape(str(value))
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--date',required=True)
    args=parser.parse_args();day=args.date
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',day):raise ValueError('Invalid date')
    source=ROOT/'data'/f'mma_research_{day}.json';data=json.loads(source.read_text())
    if data['status']!='UNVALIDATED_RESEARCH_NOT_OFFICIAL_ISSUANCE' or data['official_issuance'] is not False or data['scientific_release']!='NO':
        raise ValueError('Research status must remain explicit')
    rows=data['forecasts'];assert len(rows)==data['forecast_count']
    assert len({r['order'] for r in rows})==len(rows)
    created=datetime.fromisoformat(data['generated_at_utc']).astimezone(ZoneInfo('America/New_York'))
    assert datetime.fromisoformat(data['generated_at_utc'])<datetime.fromisoformat(data['event_start_utc'])
    title='APEX — MMA Research Picks — '+day
    page=head(title,'Unvalidated MMA model selections with full evidence and limitations.',f'/mma/research/{day}')+'\n'+hero()+'\n'+navigation('PICKS')
    page+='<main class="picks-page" data-forecast-state="UNVALIDATED_RESEARCH"><div class="section-head"><div class="title">UFC / MMA RESEARCH PICKS</div><div class="meta mono">'+esc(day)+' · '+str(len(rows))+' MODEL SELECTIONS</div></div>'
    page+='<div class="section-head"><div class="title">'+esc(data['event_name'])+'</div><a class="meta mono" href="/mma">OFFICIAL STATUS</a></div>'
    page+='<div class="market-grid market-grid--single"><section class="market-panel"><div class="market-label">RESEARCH ONLY — NOT AN APPROVED T-2 ISSUANCE</div><div class="pick-headline">Actual model output. No demonstrated betting advantage.</div><div class="rationale-copy"><p>Generated '+esc(created.strftime('%I:%M %p ET').lstrip('0'))+' on '+esc(day)+', after the scheduled T-2 time and before the event. This is not backdated.</p><p>The prices below are the original T-2 FanDuel quotes, not a claim of current availability. Probabilities use corrected pre-event features. No validated Strong or Elite rating has been assigned.</p><p>The model failed the existing release tests. These selections are separate from official picks and official performance grading. Missing-history defaults are not observed fighter ability. A likely winner is not necessarily a favorable bet at the displayed price.</p></div></section></div>'
    page+='<div class="section-head"><div class="title">WINNER SELECTIONS & DETAILED RATIONALE</div><div class="meta mono">ALL '+str(len(rows))+' BOUTS · RESEARCH</div></div><div class="picks-board">'
    for row in sorted(rows,key=lambda r:r['order']):
        p=row['probability'];assert isinstance(p,(float,int)) and math.isfinite(p) and 0<=p<=1
        paragraphs=row['rationale'];assert len(paragraphs)==6 and all(isinstance(x,str) and x.strip() for x in paragraphs)
        price=f"{row['price']:+d}"
        page+='<article class="game-module" data-position-state="RESEARCH" data-order="'+str(row['order'])+'"><header class="game-header"><div class="game-num mono">F'+str(row['order']).zfill(2)+'</div><div class="game-meta"><h2 class="game-matchup">'+esc(row['matchup'])+'</h2><p class="meta mono">WINNER FORECAST · UNVALIDATED</p></div></header>'
        page+='<div class="market-grid market-grid--single"><section class="market-panel"><div class="market-label">MODEL SELECTION</div><div class="market-panel-head"><span class="pick-headline">'+esc(row['selection'])+'</span><span class="rating-label">RESEARCH — NO VALIDATED RATING</span></div>'
        page+='<div class="meta mono">MODEL: '+f'{100*p:.1f}'+'% · T-2 FANDUEL: '+esc(price)+' · PRICE BREAK-EVEN: '+f"{100*row['bookmaker_break_even_probability']:.1f}"+'%</div><div class="rationale-copy" aria-label="Research pick rationale">'+''.join('<p>'+esc(text)+'</p>' for text in paragraphs)+'</div></section></div></article>'
    v=data['validation'];ci=v['ci95_delta']
    page+='</div><div class="section-head"><div class="title">VALIDATION REMAINS UNSUCCESSFUL</div></div><div class="rationale-copy"><p>Corrected historical evaluation: '+str(v['oos_rows'])+' out-of-sample bouts across '+str(v['oos_events'])+' events. Winner LogLoss '+f"{v['winner_logloss']:.6f}"+' versus FanDuel '+f"{v['fanduel_logloss']:.6f}"+'. The 95% interval for the difference is '+f'{ci[0]:.6f} to {ci[1]:.6f}'+', which crosses zero.</p><p>Method and duration bets are not displayed: the joint model failed its release test, and the captured T-2 board did not supply those FanDuel markets. No prices or betting lines were invented.</p></div>'
    page+='<p class="meta mono" style="overflow-wrap:anywhere">Model artifact: '+esc(data['model_sha256'])+'</p><p class="meta mono" style="overflow-wrap:anywhere">Research data SHA-256: '+hashlib.sha256(source.read_bytes()).hexdigest()+'</p></main>'+close()
    output=write(f'mma/research/{day}/index.html',page)
    print(json.dumps({'status':'PASS','forecast_count':len(rows),'output':str(output),'official_issuance':False}))
    return 0
if __name__=='__main__':raise SystemExit(main())
