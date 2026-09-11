"""Validate, never generate, the public projection of sealed MMA positions."""
from __future__ import annotations
from copy import deepcopy
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import hashlib
import json
import math
import re
import unicodedata

TIERS = {'WEAK', 'MODERATE', 'STRONG', 'ELITE'}
SHA = re.compile(r'^[0-9a-f]{64}$')
SEALED_RELEASE_STATE = 'SEALED_RELEASE_AVAILABLE'
PUBLIC_MARKETS = frozenset({'WINNER', 'METHOD', 'TIME'})

def positions_sha256(positions):
    return hashlib.sha256(json.dumps(positions,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()).hexdigest()

def _name_key(value):
    normalized=unicodedata.normalize('NFKD',str(value or ''))
    return ''.join(character for character in normalized.casefold() if character.isalnum())

def _fighter_pair(row,context):
    fighters=[]
    for key in ('fighter_a','fighter_b'):
        value=row.get(key)
        if not isinstance(value,str) or not value.strip():
            raise ValueError(f'{context} lacks {key}')
        fighters.append(_name_key(value))
    if not all(fighters) or fighters[0]==fighters[1]:
        raise ValueError(f'{context} has an invalid fighter pair')
    return tuple(sorted(fighters))

def validated_card(state):
    card=state.get('card')
    if not isinstance(card,list):
        raise ValueError('MMA official card must be a list')
    fight_count=state.get('fight_count')
    if isinstance(fight_count,bool) or not isinstance(fight_count,int) or fight_count!=len(card):
        raise ValueError('MMA fight count does not reconcile to the official card')
    orders=[];pairs=set();fighters=set();bout_ids=set()
    for number,bout in enumerate(card,1):
        if not isinstance(bout,dict):
            raise ValueError(f'MMA official card bout {number} is not an object')
        order=bout.get('official_display_order')
        if isinstance(order,bool) or not isinstance(order,int):
            raise ValueError(f'MMA official card bout {number} lacks an integer display order')
        orders.append(order)
        pair=_fighter_pair(bout,f'MMA official card bout {number}')
        if pair in pairs or any(fighter in fighters for fighter in pair):
            raise ValueError('MMA official card contains a duplicate bout or fighter')
        pairs.add(pair);fighters.update(pair)
        bout_id=bout.get('bout_id') or bout.get('apex_mma_bout_id')
        if bout_id is not None:
            if not isinstance(bout_id,str) or not bout_id.strip() or bout_id in bout_ids:
                raise ValueError('MMA official card contains an invalid or duplicate bout identity')
            bout_ids.add(bout_id)
    expected=list(range(1,len(card)+1))
    if sorted(orders)!=expected:
        raise ValueError(f'MMA official display order must be unique and contiguous 1..{len(card)}')
    return deepcopy(card)

def validated_positions(state):
    raw=state.get('positions',[])
    if not isinstance(raw,list):
        raise ValueError('MMA positions must be a list')
    published=state.get('picks_published') is True
    if not raw:
        if published:
            raise ValueError('MMA publication claims issued picks but contains no positions')
        return []
    if not published or state.get('release_state')!=SEALED_RELEASE_STATE:
        raise ValueError('MMA positions require a sealed published issuance')
    card=validated_card(state)
    card_pairs={_fighter_pair(bout,f'MMA official card bout {number}'):(bout.get('bout_id') or bout.get('apex_mma_bout_id'))
                for number,bout in enumerate(card,1)}
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
        if row['market'] not in PUBLIC_MARKETS:
            raise ValueError(
                f'MMA position {number} market {row["market"]!r} is not an allowed joint marginal'
            )
        position_pair=_fighter_pair(row,f'MMA position {number}')
        if position_pair not in card_pairs:
            raise ValueError('MMA issued position does not match exactly one official-card fighter pair')
        card_bout_id=card_pairs[position_pair]
        if card_bout_id is not None and row['bout_id']!=card_bout_id:
            raise ValueError('MMA issued position bout identity conflicts with the official card')
        matchup_parts=re.split(r'\s+vs\.?\s+',row['matchup'],maxsplit=1,flags=re.IGNORECASE)
        if len(matchup_parts)!=2 or tuple(sorted(_name_key(part) for part in matchup_parts))!=position_pair:
            raise ValueError('MMA issued position matchup conflicts with its fighter pair')
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
                    'detail':f'{len(positions)} issued positions from the sealed recovery run {when}. The original T-2 deadline was missed; these are not backdated picks. Prices, probabilities, ratings and detailed rationale below match the sealed issuance. A statistically proven market edge has not been established.'}
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
