"""Validate, never generate, the public projection of sealed MMA positions."""
from __future__ import annotations
from copy import deepcopy
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import hashlib
import json
import math
import re

TIERS = {'WEAK', 'MODERATE', 'STRONG', 'ELITE'}
SHA = re.compile(r'^[0-9a-f]{64}$')

def positions_sha256(positions):
    return hashlib.sha256(json.dumps(positions,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()).hexdigest()

def validated_positions(state):
    raw=state.get('positions',[])
    if not isinstance(raw,list):
        raise ValueError('MMA positions must be a list')
    published=state.get('picks_published') is True
    if not raw:
        if published:
            raise ValueError('MMA publication claims issued picks but contains no positions')
        return []
    if not published or state.get('release_state')!='SEALED_RELEASE_AVAILABLE':
        raise ValueError('MMA positions require a sealed published issuance')
    model_sha=str(state.get('active_model_sha256') or '')
    if not state.get('active_model') or not SHA.fullmatch(model_sha):
        raise ValueError('MMA published positions lack an identified model artifact')
    issuance_id=str(state.get('issuance_id') or '')
    if not issuance_id or str(state.get('issuance_status') or '') not in {'SEALED','ALREADY_ISSUED'}:
        raise ValueError('MMA public state lacks a sealed issuance identity')
    seen=set()
    for number,row in enumerate(raw,1):
        if not isinstance(row,dict):
            raise ValueError(f'MMA position {number} is not an object')
        for key in ['bout_id','matchup','market','selection','rationale']:
            if not isinstance(row.get(key),str) or not row[key].strip():
                raise ValueError(f'MMA position {number} lacks {key}')
        trace=row.get('trace') or {}
        if str(trace.get('issuance_id') or row.get('issuance_id') or '')!=issuance_id:
            raise ValueError('MMA position issuance identity mismatch')
        if str(trace.get('model_sha256') or row.get('model_sha256') or '')!=model_sha:
            raise ValueError('MMA position model identity mismatch')
        if row.get('sportsbook')!='FanDuel' or row.get('tier') not in TIERS:
            raise ValueError('MMA position has invalid bookmaker or issued rating')
        p=row.get('probability'); price=row.get('price')
        if isinstance(p,bool) or not isinstance(p,(int,float)) or not math.isfinite(p) or not 0<=p<=1:
            raise ValueError('MMA issued probability must be a finite fraction')
        if isinstance(price,bool) or not isinstance(price,(int,float)) or not math.isfinite(price) or abs(price)<100:
            raise ValueError('MMA position lacks authentic American odds')
        line=row.get('line')
        if line is not None and (isinstance(line,bool) or not isinstance(line,(int,float)) or not math.isfinite(line)):
            raise ValueError('MMA market line must be numeric or absent')
        identity=(row['bout_id'],row['market'],row['selection'],line)
        if identity in seen:
            raise ValueError('Duplicate MMA issued position')
        seen.add(identity)
    if state.get('positions_sha256')!=positions_sha256(raw):
        raise ValueError('MMA position payload checksum mismatch')
    return deepcopy(raw)

def forecast_status(state,positions,now=None):
    if positions:
        t2 = state.get('t2') or {}
        if t2.get('status') == 'SEALED_LATE_RECOVERY' or t2.get('timeliness') == 'FAIL':
            when = 'after the scheduled T-2 time'
            try:
                stamp = datetime.fromisoformat(str(t2['actual_utc']).replace('Z','+00:00'))
                when = 'at ' + stamp.astimezone(ZoneInfo('America/New_York')).strftime('%I:%M %p %Z').lstrip('0')
            except (KeyError,TypeError,ValueError):
                pass
            return {'code':'FORECASTS_ISSUED','headline':'Forecasts issued — late recovery',
                    'detail':f'{len(positions)} winner forecasts from the sealed recovery run {when}. The original T-2 deadline was missed; these are not backdated picks. Prices, probabilities, ratings and detailed rationale below match the sealed issuance. A statistically proven market edge has not been established.'}
        return {'code':'FORECASTS_ISSUED','headline':'Forecasts issued',
                'detail':f'{len(positions)} issued positions. Picks, FanDuel prices, probabilities, ratings and rationale below are read from the same sealed T-2 issuance.'}
    t2=state.get('t2') or {}; status=str(t2.get('status') or '')
    if any(term in status for term in ['FAIL','BLOCKED','NO_RELEASE']) and 'AWAITING_TARGET' not in status:
        return {'code':'NO_FORECASTS_ISSUED','headline':'No forecasts issued',
                'detail':'The T-2 run did not produce an approved forecast card. There are no issued picks or pick rationales for this event. The fight schedule below is not a set of selections.'}
    try:
        due=datetime.fromisoformat(str(t2['scheduled_utc']).replace('Z','+00:00'))
        current=now or datetime.now(timezone.utc)
        if due.tzinfo is not None and current>=due:
            return {'code':'NO_FORECASTS_ISSUED','headline':'No forecasts published',
                    'detail':'The scheduled T-2 time has passed, but no sealed forecast card is available. The fight schedule below is not a set of selections.'}
    except (KeyError,TypeError,ValueError):
        pass
    return {'code':'AWAITING_T2','headline':'Awaiting the T-2 forecast run',
            'detail':'No forecasts have been issued yet. Any published card will show the selection, captured FanDuel price, APEX probability, rating and full model-supported rationale.'}
