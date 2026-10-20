"""NBA card rationales from the sealed pick and the T-6 rows the champions actually read.

The coefficients, standardisers, shrink weight and sigmas are the published champion files
ats_shrink_c3.v2 (content sha256 e507e2e52791bcbd3c873ec586de3f15975c240ef2ee2a70ba5a9d8ffbf14fec)
and totals_d4_ratings_lag1.v2 (content sha256 cab25ae11a73df3ff858a170ed237891d978e6ad789d7118239a615491b97a5b).
Nothing here refits a model. A feature that is not on the sealed row and cannot be rebuilt from the
stored T-6 tables is omitted, not filled in.
"""
import math
import re

SHRINK = 0.75
ATS_INTERCEPT = -0.0018246240290608507
ATS_SIGMA = 13.620276213741434
TOTAL_SIGMA = 18.080271108951884
TOTAL_DIRECT_INTERCEPT = 0.028754043347643646
TOTAL_DIST_INTERCEPT = 0.5580244974865718
PLAYER_CAP = 48.0
TEAM_MINUTES = 240.0

# mean, sd, coefficient. Missing-indicator coefficients are applied only when the rebuilt value is absent.
ATS = {
    'line': (-2.174937185929648, 7.09848190445064, 1.1565972747426014),
    'ls_dnt_off': (0.19571732131612093, 5.2555012478474605, 0.19769822835096718),
    'ls_dnt_def': (0.08029042018261964, 3.9085915753509393, 0.4647563875518534),
    'ls_dnt_net': (0.27602945418765745, 8.094788463750572, 0.3527067738110024),
    'rotation_size': (-0.0010992462311557789, 1.2501879447448538, 0.07628566419836837),
    'top5_min_share': (-0.0006083896042713568, 0.06105516693819257, -0.20660642530541176),
    'players_projected': (-0.004239949748743719, 0.9593566535211364, -0.03805526304698004),
    'dnt_missing_min_share': (-7.578187814070352e-05, 0.021789785379933986, 0.11655522696916791),
    'min_shift_abs': (-0.6286852397670029, 63.950400790458694, -0.7109837399165573),
    'new_player_min_share': (-0.00026611528995543, 0.08233255499516953, -0.22138030824346008),
    'ast36_mw': (0.004716410660043713, 0.640803585502566, 0.2913263257582874),
    'reb36_mw': (0.0024222801571501485, 0.7082668779409923, 0.1528086180219155),
    'blk36_mw': (0.0008470916053793488, 0.21970227910586893, 0.06820975717177165),
    'fg3a_rate_mw': (-0.0005565077897342484, 0.07073326338713355, 0.021694806214759294),
}
ATS_LABEL = {
    'line': 'home spread',
    'ls_dnt_off': 'minutes-weighted offensive EPM',
    'ls_dnt_def': 'minutes-weighted defensive EPM',
    'ls_dnt_net': 'minutes-weighted EPM',
    'rotation_size': 'rotation size (home minus away)',
    'top5_min_share': 'top-five minute share',
    'players_projected': 'players on the minute projection',
    'dnt_missing_min_share': 'minute share without an EPM',
    'min_shift_abs': 'absolute minute shift from the last five games',
    'new_player_min_share': 'minute share with fewer than five games this season',
    'ast36_mw': 'minutes-weighted assists per 36 over the last 20 games',
    'reb36_mw': 'minutes-weighted rebounds per 36 over the last 20 games',
    'blk36_mw': 'minutes-weighted blocks per 36 over the last 20 games',
    'fg3a_rate_mw': 'minutes-weighted three-point attempt rate over the last 20 games',
}

# Direct and distribution coefficients follow the champion beta with the intercept removed.
# The last five are the CTG inputs; each coefficient is 0.
TOTAL_FEATURES = (
    'strength_edge', 'neutral', 's_efg', 's_tov', 's_orb', 's_ftr', 's_par3', 'rtg_sum', 'pace_sum',
    'box_total_edge', 'dnt_points', 'dnt_missing', 'paid_epm_diff', 'paid_game_optimized_epm_diff',
    'paid_team_rating_missing', 'paid_predicted_margin', 'paid_predicted_total', 'paid_home_win_probability',
    'paid_prediction_missing', 'ctg_offense_diff_10', 'ctg_defense_diff_10', 'ctg_offense_sum_10',
    'ctg_defense_sum_10', 'ctg_missing',
)
_TOTAL_DIRECT_COEF = (
    -0.007227541480102529, -0.008474850558721488, -0.03724904036491894, -0.001757137157830269,
    -0.0045501646407338754, -0.008993246031747292, -0.005218431789377258, -0.02954171363384452,
    0.016076990846313123, 0.0342256511525922, 0.020974804524956422, -0.0035861662339164565,
    -0.01388616011724592, -0.006499156596366126, -0.0035861662339164565, 0.0070089408088351325,
    0.028480963970291026, 0.0031923280084292477, -0.016658312029312596, 0.0, 0.0, 0.0, 0.0, 0.0,
)
_TOTAL_DIST_COEF = (
    -0.027672607193436866, 0.05375334151369644, -0.2191636865598173, -0.0984830876719196,
    0.005356260496110891, -0.10372405802950325, -0.07096082637475705, -0.1346820930507889,
    0.052385350442385965, 0.03309665528656177, 0.02931064023616453, -0.024264667382421785,
    -0.12726781279160745, -0.08662446780064709, -0.024264667382421782, -0.005250830577668344,
    0.16841212210261294, -0.021559406182806752, -0.039170694651086316, 0.0, 0.0, 0.0, 0.0, 0.0,
)
_TOTAL_DIRECT_MEAN = (
    0.37423447177782715, 0.004440215667618141, 0.0005886328286456308, 0.0014788399855954612,
    0.0024848520548640374, 0.003189237525724462, 0.0021986076351006626, 0.044070575139775234,
    0.18815693544811704, -0.8437166972033089, 0.18090058521439875, 0.004757373929590866,
    -0.028842689502061702, 0.04024310180780222, 0.004757373929590866, 2.0753409451316243,
    224.65875356803105, 0.5528119885823005, 0.0003171582619727244, 0.0, 0.0, 0.0, 0.0, 2.0,
)
_TOTAL_DIRECT_SD = (
    4.754087350824808, 0.06648684194969236, 0.017599671208563202, 0.014007063499000676,
    0.0323438185266966, 0.025494484168871834, 0.05673826653306385, 1.7859665749971187,
    2.2342465160206086, 7.1733223323053155, 4.481827966517994, 0.09578599579534043,
    7.520108748774506, 7.9242483541848845, 0.09578599579534043, 6.703096258272284,
    8.38388405586588, 0.17037192801526782, 0.017806113349340052, 1.0, 1.0, 1.0, 1.0, 1.0,
)
_TOTAL_DIST_MEAN = (
    0.3605812242175198, 0.0043969849246231155, 0.0006196251746091169, 0.001460137521190263,
    0.0024543966562800335, 0.0031260730450994264, 0.002265146586148391, 0.04645979668371655,
    0.19263190851036602, -0.8597709948688511, 0.18783255608699717, 0.004711055276381909,
    -0.033319409547738925, 0.03534846105527655, 0.004711055276381909, 2.0760521356783945,
    224.63161118090508, 0.5527570351758778, 0.00047110552763819093, 0.0, 0.0, 0.0, 0.0, 2.0,
)
_TOTAL_DIST_SD = (
    4.7606557199027595, 0.0661638228051821, 0.01760176325930826, 0.014003652710253854,
    0.03229578504204313, 0.025487648589471085, 0.05679287486331075, 1.7859213209534925,
    2.2351132143331927, 7.18131941033506, 4.479049864239552, 0.09531970498899663,
    7.524046365790174, 7.922725447628048, 0.09531970498899663, 6.706505339904413,
    8.840580388191514, 0.1705181623035528, 0.021699852239587574, 1.0, 1.0, 1.0, 1.0, 1.0,
)
TOTAL_LABEL = {
    'dnt_points': 'sum of each team\'s offensive EPM minus defensive EPM',
    'dnt_missing': 'count of teams missing a lagged rating',
    'paid_epm_diff': 'home team EPM minus away team EPM',
    'paid_game_optimized_epm_diff': 'home game-optimized EPM minus away',
    'paid_team_rating_missing': 'count of teams missing a usable team EPM',
    'paid_predicted_margin': 'Dunk & Threes predicted home margin',
    'paid_predicted_total': 'Dunk & Threes predicted total',
    'paid_home_win_probability': 'Dunk & Threes home win probability',
    'paid_prediction_missing': 'missing Dunk & Threes game prediction',
    'ctg_offense_diff_10': 'CTG offensive points per possession, home minus away',
    'ctg_defense_diff_10': 'CTG defensive points per possession, home minus away',
    'ctg_offense_sum_10': 'CTG offensive points per possession, home plus away',
    'ctg_defense_sum_10': 'CTG defensive points per possession, home plus away',
    'ctg_missing': 'count of teams missing CTG games',
}


def _check_lengths():
    n = len(TOTAL_FEATURES)
    for name, seq in (
        ('direct coef', _TOTAL_DIRECT_COEF), ('direct mean', _TOTAL_DIRECT_MEAN), ('direct sd', _TOTAL_DIRECT_SD),
        ('dist coef', _TOTAL_DIST_COEF), ('dist mean', _TOTAL_DIST_MEAN), ('dist sd', _TOTAL_DIST_SD),
    ):
        if len(seq) != n:
            raise ValueError(f'{name} has {len(seq)} entries, champion features have {n}')


_check_lengths()


def normsinv(p):
    """Inverse standard normal, Acklam's approximation, accurate past 1e-9 on (0, 1)."""
    if not 0 < p < 1:
        raise ValueError('probability out of range')
    a = (-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00)
    b = (-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01)
    c = (-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00)
    d = (7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00, 3.754408661907416e+00)
    plow = 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
            ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p > 1 - plow:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
            ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
        (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)


def american_implied(price):
    price = float(price)
    if price < 0:
        return -price / (-price + 100.0)
    return 100.0 / (price + 100.0)


def no_vig(price_a, price_b):
    a, b = american_implied(price_a), american_implied(price_b)
    return a / (a + b)


def scale_to_total(minutes, total=TEAM_MINUTES, cap=PLAYER_CAP):
    """The champion minutes scaler: proportional, no player above 48, team sum 240."""
    out = {p: max(float(m or 0.0), 0.0) for p, m in minutes.items()}
    total = min(total, cap * sum(1 for m in out.values() if m > 0))
    capped = set()
    for _ in range(len(out) + 1):
        free = {p: m for p, m in out.items() if p not in capped and m > 0}
        room = total - cap * len(capped)
        s = sum(free.values())
        if s <= 0:
            break
        factor = room / s
        over = {p for p, m in free.items() if m * factor > cap + 1e-9}
        if not over:
            for p, m in free.items():
                out[p] = m * factor
            break
        capped |= over
        for p in over:
            out[p] = cap
    return out


def redistribute(minutes, out_players, cap=PLAYER_CAP, total=TEAM_MINUTES):
    team_total = min(total, sum(minutes.values()))
    rest = {p: m for p, m in minutes.items() if p not in out_players}
    adj = scale_to_total(rest, team_total, cap)
    adj.update({p: 0.0 for p in minutes if p in out_players})
    return adj


def _wmean(pairs):
    pairs = [(v, w) for v, w in pairs if v is not None and w]
    weight = sum(w for _, w in pairs)
    return sum(v * w for v, w in pairs) / weight if weight else None


def _f(value, digits):
    return f'{float(value):.{digits}f}'


def _signed_line(value):
    value = float(value)
    text = f'{value:.1f}'
    return text if text.startswith('-') else '+' + text


def sentence_count(text):
    """Sentences end with a period and a space, or with the final period. Decimal points have no space after them."""
    return text.count('. ') + (1 if text.endswith('.') else 0)


def _join(sentences):
    if not 5 <= len(sentences) <= 8:
        raise ValueError(f'rationale has {len(sentences)} sentences')
    text = ' '.join(s.rstrip('.') + '.' for s in sentences)
    if sentence_count(text) != len(sentences):
        raise ValueError('a sentence contains a period followed by a space')
    low = text.lower()
    if 'rest' in low or 'travel' in low:
        raise ValueError('rationale mentions rest or travel')
    for banned in ('q_b0', 'p_c3', 'coef', 'sigma', 'intercept', 'logit', 'sigmoid',
                   'not stored', 'unstored', 'rapm', 'lineup', 'champion'):
        if banned in low:
            raise ValueError(f'rationale contains {banned}')
    if re.search(r'\bphi\b', low):
        raise ValueError('rationale contains phi')
    return text


def rotation(players):
    raw = {p['player_id']: max(float(p.get('p_mp') or 0.0), 0.0) for p in players}
    proj = scale_to_total(raw) if raw else {}
    outs = {p['player_id'] for p in players if p.get('status') == 'Out'}
    adj = redistribute(proj, outs) if outs & set(proj) else dict(proj)
    moved = any(proj.get(i, 0.0) > 1e-9 for i in outs)
    return proj, adj, outs, moved


def _team_block(players, adj):
    total = sum((adj.get(p['player_id']) or 0.0) for p in players)

    def ls(col):
        vals = []
        for p in players:
            w = adj.get(p['player_id']) or 0.0
            v = p.get(col)
            if v is not None and w:
                vals.append((w / 48.0) * float(v))
        return sum(vals) if vals else None

    missing = sum((adj.get(p['player_id']) or 0.0) for p in players if p.get('epm') is None)
    shifts = [abs((adj.get(p['player_id']) or 0.0) - float(p['min_recent5']))
              for p in players if p.get('min_recent5') is not None]
    new = sum((adj.get(p['player_id']) or 0.0) for p in players if int(p.get('games_season') or 0) < 5)
    return {
        'ls_dnt_off': ls('oepm'),
        'ls_dnt_def': ls('depm'),
        'ls_dnt_net': ls('epm'),
        'rotation_size': float(sum(1 for v in adj.values() if v >= 10)),
        'top5_min_share': (sum(sorted(adj.values(), reverse=True)[:5]) / total) if total else None,
        'players_projected': float(len(players)),
        'dnt_missing_min_share': (missing / total) if total else None,
        'min_shift_abs': sum(shifts) if shifts else None,
        'new_player_min_share': (new / total) if total else None,
        'ast36_mw': _wmean([(p.get('ast36'), adj.get(p['player_id']) or 0.0) for p in players]),
        'reb36_mw': _wmean([(p.get('reb36'), adj.get(p['player_id']) or 0.0) for p in players]),
        'blk36_mw': _wmean([(p.get('blk36'), adj.get(p['player_id']) or 0.0) for p in players]),
        'fg3a_rate_mw': _wmean([(p.get('fg3a_rate'), adj.get(p['player_id']) or 0.0) for p in players]),
    }


def _diff(home, away, name):
    a, b = home.get(name), away.get(name)
    if a is None or b is None:
        return None
    return a - b


def ats_features(row, players):
    """Home-minus-away inputs the spread champion standardises. Line is the home number."""
    home = [p for p in players if p.get('is_home')]
    away = [p for p in players if not p.get('is_home')]
    _, hadj, _, _ = rotation(home)
    _, aadj, _, _ = rotation(away)
    h, a = _team_block(home, hadj), _team_block(away, aadj)
    out = {'line': float(row['line'])}
    for name in ATS:
        if name == 'line':
            continue
        out[name] = _diff(h, a, name)
    return out, hadj, aadj


def coef_z(table, name, value):
    mean, sd, coef = table[name]
    if value is None or sd in (0, None):
        return None
    return coef * ((float(value) - mean) / sd)


def _rank(items, side_is_a):
    ranked = []
    for name, raw, cz in items:
        if cz is None:
            continue
        toward = cz if side_is_a else -cz
        ranked.append((abs(cz), toward, name, raw, cz))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked


def _player_pieces(players, adj_by_id, side_is_a):
    _, _, coef = ATS['ls_dnt_net']
    sd = ATS['ls_dnt_net'][1]
    pieces = []
    for p in players:
        minutes = adj_by_id.get(p['player_id']) or 0.0
        if not minutes or p.get('epm') is None:
            continue
        sign = 1.0 if p.get('is_home') else -1.0
        cz = (coef / sd) * sign * (minutes / 48.0) * float(p['epm'])
        toward = cz if side_is_a else -cz
        pieces.append((abs(cz), toward, p, minutes, cz))
    pieces.sort(key=lambda item: item[0], reverse=True)
    return pieces


def _and(items):
    items = list(items)
    if not items:
        return ''
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f'{items[0]} and {items[1]}'
    return ', '.join(items[:-1]) + ' and ' + items[-1]


def _line_text(public):
    if public['market'] == 'ATS':
        return _signed_line(public['line'])
    return _f(public['line'], 1)


def _quality(player):
    """The stored rating that actually carries this player's number."""
    offense, defense, net = player.get('oepm'), player.get('depm'), player.get('epm')
    if net is None:
        return None, None
    if defense is not None and offense is not None and defense > 0 and offense <= 0:
        return 'defensive EPM', defense
    if offense is not None and defense is not None and offense > 0 and defense <= 0:
        return 'offensive EPM', offense
    return 'EPM', net


def _player_bit(player, minutes):
    label, value = _quality(player)
    if label is None:
        return None
    return f"{player['name']}'s {_f(value, 1)} {label} over {_f(minutes, 1)} minutes"


def _cap(text):
    return text[:1].upper() + text[1:] if text else text


def _the(name):
    return name if str(name).lower().startswith('the ') else f'the {name}'


def _direction_sentence(clauses, selection, favors):
    clauses = [c for c in clauses if c]
    if not clauses:
        return None
    target = _the(selection)
    verb = 'favors' if favors else 'works against'
    if len(clauses) == 1:
        return f'{_cap(clauses[0])} {verb} {target}'
    return f'{_cap(clauses[0])} {verb} {target}, as does {clauses[1]}'


def _team_clause(name, raw, home, away):
    raw = float(raw)
    gap = abs(raw)
    higher = home if raw >= 0 else away
    lower = away if raw >= 0 else home
    if name == 'line':
        return f'a home line of {_signed_line(raw)}'
    if name == 'min_shift_abs':
        if _f(gap, 1) == '0.0':
            return None
        return (f'a minute change from the last five games that is {_f(gap, 1)} larger for the {higher} '
                f'than for the {lower}')
    if name == 'ast36_mw':
        if _f(gap, 2) == '0.00':
            return None
        return (f'an assist rate {_f(gap, 2)} per 36 higher for the {higher} than for the {lower} '
                f'over the last 20 games')
    if name == 'reb36_mw':
        if _f(gap, 2) == '0.00':
            return None
        return (f'a rebound rate {_f(gap, 2)} per 36 higher for the {higher} than for the {lower} '
                f'over the last 20 games')
    if name == 'blk36_mw':
        if _f(gap, 2) == '0.00':
            return None
        return (f'a block rate {_f(gap, 2)} per 36 higher for the {higher} than for the {lower} '
                f'over the last 20 games')
    if name == 'fg3a_rate_mw':
        if _f(gap, 3) == '0.000':
            return None
        return (f'a three-point shot share {_f(gap, 3)} higher for the {higher} than for the {lower} '
                f'over the last 20 games')
    if name == 'rotation_size':
        if _f(gap, 1) == '0.0':
            return None
        return (f'{_f(gap, 1)} more players projected for 10 or more minutes for the {higher} '
                f'than for the {lower}')
    if name == 'top5_min_share':
        if _f(gap, 3) == '0.000':
            return None
        return (f'a top-five minute share {_f(gap, 3)} higher for the {higher} than for the {lower}')
    if name == 'players_projected':
        if _f(gap, 1) == '0.0':
            return None
        shown = str(int(round(gap))) if abs(gap - round(gap)) < 0.05 else _f(gap, 1)
        return f'a roster with {shown} more players on the minute projection for the {higher} than for the {lower}'
    if name == 'dnt_missing_min_share':
        if _f(gap, 3) == '0.000':
            return None
        return (f'a {_f(gap, 3)} larger share of minutes on players without an EPM for the {higher} '
                f'than for the {lower}')
    if name == 'new_player_min_share':
        if _f(gap, 3) == '0.000':
            return None
        return (f'a {_f(gap, 3)} larger share of minutes for players with fewer than five games this season '
                f'for the {higher} than for the {lower}')
    return None


def _out_sentence(players):
    groups = []
    moved = False
    teams = []
    for player in players:
        if player['team'] not in teams:
            teams.append(player['team'])
    for team in teams:
        team_players = [p for p in players if p['team'] == team]
        proj, _, outs, _ = rotation(team_players)
        by_id = {p['player_id']: p for p in team_players}
        names = [by_id[pid]['name'] for pid in sorted(outs, key=lambda i: by_id[i]['name'])]
        if names:
            groups.append(f"{_and(names)} as Out for the {team}")
        if any(proj.get(pid, 0.0) > 1e-9 for pid in outs):
            moved = True
    if not groups:
        return 'The injury report before T-6 listed no Out player on either minute projection'
    tail = ('their projected minutes were given to teammates' if moved
            else 'each of those projections was already at zero minutes')
    return f"Before T-6 the injury report listed {_and(groups)}, and {tail}"


def _pad(sentences, public):
    """Fill toward 6 sentences from sealed fields only. The FanDuel price is already on the card."""
    selection = public['selection']
    extras = [
        f"The line on {selection} is {_line_text(public)}",
        f"{public.get('matchup') or selection} is the matchup on this card",
    ]
    for extra in extras:
        if len(sentences) >= 6:
            break
        if extra not in sentences:
            sentences.append(extra)
    return sentences


def _tier_sentence(public):
    tier = public.get('tier')
    if tier:
        return f'The tier is {tier}'
    return f"The published market is {public['market']}"


def fallback_rationale(row, public):
    """Sealed pick only. Player and team stats are omitted when the T-6 rows are absent, not invented."""
    selection = public['selection']
    action = 'to cover' if public['market'] == 'ATS' else 'on the total'
    side = public.get('probability_side') or public['market']
    sentences = [
        f"{selection} {_line_text(public)} is a {_f(100 * public['win_probability'], 1)}% chance {action}",
        f"{row['away']} plays at {row['home']}",
        f"The published side is {side}",
        f"The line on {selection} is {_line_text(public)}",
        _tier_sentence(public),
    ]
    return _join(sentences)


def spread_rationale(row, public):
    players = row['t6']['players']
    features, hadj, aadj = ats_features(row, players)
    side_is_a = row['side'] == 'a'
    home_name = next(p['team'] for p in players if p['team_id'] == row['home_team_id'])
    away_name = next(p['team'] for p in players if p['team_id'] == row['away_team_id'])
    items = [(name, features[name], coef_z(ATS, name, features[name])) for name in ATS if name not in (
        'ls_dnt_off', 'ls_dnt_def', 'ls_dnt_net')]
    ranked = _rank(items, side_is_a)
    favor = [item for item in ranked if item[1] > 0][:2]
    against = [item for item in ranked if item[1] < 0][:1]
    adj = {}
    adj.update(hadj)
    adj.update(aadj)
    pieces = _player_pieces(players, adj, side_is_a)
    with_pick = [piece for piece in pieces if piece[1] > 0][:2]
    against_player = next((piece for piece in pieces if piece[1] < 0), None)
    selection = public['selection']
    sentences = [
        f"{selection} {_line_text(public)} is a {_f(100 * public['win_probability'], 1)}% chance to cover",
    ]
    if with_pick:
        bits = [b for b in (_player_bit(p, minutes) for _, _, p, minutes, _ in with_pick) if b]
        if len(bits) > 1:
            sentences.append(f"{_and(bits)} favor {_the(selection)}")
        elif bits:
            sentences.append(f"{bits[0]} favors {_the(selection)}")
    if against_player:
        _, _, player, minutes, _ = against_player
        label, value = _quality(player)
        sentences.append(
            f"{player['name']} is the biggest factor against the pick, with a {_f(value, 1)} {label} "
            f"over {_f(minutes, 1)} minutes for the {player['team']}"
        )
    sentences.append(_direction_sentence(
        [_team_clause(name, raw, home_name, away_name) for _, _, name, raw, _ in favor], selection, True))
    sentences.append(_direction_sentence(
        [_team_clause(name, raw, home_name, away_name) for _, _, name, raw, _ in against], selection, False))
    sentences.append(_out_sentence(players))
    sentences.append(_tier_sentence(public))
    sentences = _pad([s for s in sentences if s], public)
    return _join(sentences[:8])


def _total_values(row):
    t6 = row['t6']
    home_id, away_id = row['home_team_id'], row['away_team_id']
    teams = t6['teams']
    pred = t6.get('prediction')
    home, away = teams.get(home_id), teams.get(away_id)
    values = {}
    if home and away and home.get('oepm') is not None and away.get('oepm') is not None:
        values['dnt_points'] = (home['oepm'] - home['depm']) + (away['oepm'] - away['depm'])
        values['dnt_missing'] = 0.0
        values['paid_epm_diff'] = home['epm'] - away['epm']
        values['paid_game_optimized_epm_diff'] = home['epm_go'] - away['epm_go']
        values['paid_team_rating_missing'] = 0.0
    else:
        values['dnt_missing'] = float((home is None) + (away is None))
        values['paid_team_rating_missing'] = values['dnt_missing']
        values['paid_epm_diff'] = 0.0
        values['paid_game_optimized_epm_diff'] = 0.0
        values['dnt_points'] = 0.0
    if pred:
        values['paid_predicted_margin'] = pred['home'] - pred['away']
        values['paid_predicted_total'] = pred['home'] + pred['away']
        values['paid_home_win_probability'] = pred['win']
        values['paid_prediction_missing'] = 0.0
    else:
        values['paid_predicted_margin'] = 0.0
        values['paid_predicted_total'] = 0.0
        values['paid_home_win_probability'] = 0.0
        values['paid_prediction_missing'] = 1.0
    for name in TOTAL_FEATURES:
        if name.startswith('ctg_'):
            values[name] = None
    return values


def _total_table(coef, mean, sd):
    return {name: (mean[i], sd[i], coef[i]) for i, name in enumerate(TOTAL_FEATURES)}


def _total_clause(name, raw, home, away):
    raw = float(raw)
    if name == 'paid_predicted_total':
        return f'a Dunk & Threes projection of {_f(raw, 1)} points'
    if name == 'paid_predicted_margin':
        team = home['name'] if raw >= 0 else away['name']
        return f'a Dunk & Threes margin of {_f(abs(raw), 1)} points for the {team}'
    if name == 'paid_home_win_probability':
        return f"a Dunk & Threes win chance of {_f(100 * raw, 1)}% for the {home['name']}"
    if name == 'dnt_points':
        return f'offensive EPM minus defensive EPM adding to {_f(raw, 1)} across both teams'
    if name in ('paid_epm_diff', 'paid_game_optimized_epm_diff'):
        label = 'game-optimized team EPM' if name == 'paid_game_optimized_epm_diff' else 'team EPM'
        home_value = home['epm_go'] if 'game_optimized' in name else home['epm']
        away_value = away['epm_go'] if 'game_optimized' in name else away['epm']
        return (f"{label} of {_f(home_value, 1)} for the {home['name']} and {_f(away_value, 1)} "
                f"for the {away['name']}")
    return None


def total_rationale(row, public):
    values = _total_values(row)
    direct = _total_table(_TOTAL_DIRECT_COEF, _TOTAL_DIRECT_MEAN, _TOTAL_DIRECT_SD)
    dist = _total_table(_TOTAL_DIST_COEF, _TOTAL_DIST_MEAN, _TOTAL_DIST_SD)
    side_is_a = row['side'] == 'a'
    home = row['t6']['teams'][row['home_team_id']]
    away = row['t6']['teams'][row['away_team_id']]
    skip = {'dnt_missing', 'paid_team_rating_missing', 'paid_prediction_missing'}
    items = []
    for name in TOTAL_FEATURES:
        if name.startswith('ctg_') or name in skip or name not in values or values[name] is None:
            continue
        if name not in ('dnt_points', 'paid_epm_diff', 'paid_game_optimized_epm_diff',
                        'paid_predicted_margin', 'paid_predicted_total', 'paid_home_win_probability'):
            continue
        direct_z = coef_z(direct, name, values[name]) or 0.0
        dist_z = coef_z(dist, name, values[name]) or 0.0
        items.append((name, values[name], direct_z + dist_z))
    ranked = _rank(items, side_is_a)
    # Keep the stored signals that actually move the total. A near-zero contribution is not narrated.
    ranked = [item for item in ranked if item[0] >= 0.01] or ranked[:1]
    favor = [item for item in ranked if item[1] > 0][:2]
    against = [item for item in ranked if item[1] < 0][:2]
    selection = public['selection']
    pred = row['t6'].get('prediction')
    score = None
    if pred and pred.get('home') is not None and pred.get('away') is not None:
        score = (f"Dunk & Threes had {_the(home['name'])} at {_f(pred['home'], 1)} points and "
                 f"{_the(away['name'])} at {_f(pred['away'], 1)} points")
    mentioned = {name for _, _, name, _, _ in favor + against}
    epm_line = None
    if 'paid_epm_diff' not in mentioned and home.get('epm') is not None and away.get('epm') is not None:
        epm_line = _cap(f"{_the(home['name'])} team EPM is {_f(home['epm'], 1)} and "
                        f"{_the(away['name'])} team EPM is {_f(away['epm'], 1)}")
    sentences = [
        f"{selection} {_line_text(public)} is a {_f(100 * public['win_probability'], 1)}% chance on the total",
        _direction_sentence(
            [_total_clause(name, raw, home, away) for _, _, name, raw, _ in favor], selection, True),
        _direction_sentence(
            [_total_clause(name, raw, home, away) for _, _, name, raw, _ in against], selection, False),
        score,
        epm_line,
        _out_sentence(row['t6']['players']),
        _tier_sentence(public),
    ]
    sentences = _pad([s for s in sentences if s], public)
    return _join(sentences[:8])


def compose_rationale(row, public):
    market = public['market']
    if row.get('rationale'):
        return row['rationale']
    t6 = row.get('t6')
    if not t6 or not t6.get('players'):
        return fallback_rationale(row, public)
    if market == 'ATS':
        return spread_rationale(row, public)
    return total_rationale(row, public)


def _num(value):
    return None if value is None else float(value)


def load_t6(conn, game_ids):
    """Read the T-6 minutes, ratings, injuries, team ratings, score predictions and last-20 box rows.

    The cutoff for every game is that date's first tip minus six hours, the card release. Ratings use the
    champion's extra day of lag. Returns {game_id: context}. An empty game list still runs the reads so the
    call shape stays fixed.
    """
    ids = [int(g) for g in game_ids]
    meta = conn.execute("""select g.game_id, g.home_team_id, g.away_team_id, g.season_id,
        (select min(s.scheduled_tip) from core.games s
          where coalesce((s.scheduled_tip at time zone 'America/New_York')::date, s.game_date)
              = coalesce((g.scheduled_tip at time zone 'America/New_York')::date, g.game_date))
          - interval '6 hours' as release_at
        from core.games g where g.game_id = any(%s)""", (ids,)).fetchall()
    players = conn.execute("""with meta as (
        select g.game_id, g.home_team_id, g.away_team_id,
          (select min(s.scheduled_tip) from core.games s
            where coalesce((s.scheduled_tip at time zone 'America/New_York')::date, s.game_date)
                = coalesce((g.scheduled_tip at time zone 'America/New_York')::date, g.game_date))
            - interval '6 hours' as release_at
        from core.games g where g.game_id = any(%s)
      ), mins as (
        select distinct on (m.game_id, m.team_id, m.player_id)
          m.game_id, m.team_id, m.player_id, m.p_mp, m.observed_at, m.fetch_id
        from dnt.minutes_predictions m join meta on meta.game_id = m.game_id
        where m.observed_at < meta.release_at
        order by m.game_id, m.team_id, m.player_id, m.observed_at desc, m.fetch_id desc
      ), latest as (
        select game_id, team_id, max(observed_at) as obs from mins group by 1, 2
      ), latest_fetch as (
        select m.game_id, m.team_id, max(m.fetch_id) as fetch_id
        from mins m join latest l on l.game_id = m.game_id and l.team_id = m.team_id and l.obs = m.observed_at
        group by 1, 2
      ), chosen as (
        select m.* from mins m
        join latest l on l.game_id = m.game_id and l.team_id = m.team_id and l.obs = m.observed_at
        join latest_fetch f on f.game_id = m.game_id and f.team_id = m.team_id and f.fetch_id = m.fetch_id
      ), rates as (
        select distinct on (r.player_id, c.release_at)
          r.player_id, c.release_at, r.rating_date, r.oepm, r.depm, r.epm
        from dnt.player_ratings r
        join (select distinct release_at from meta) c on true
        where r.game_optimized and r.observed_at < c.release_at
        order by r.player_id, c.release_at, r.rating_date desc, r.observed_at desc, r.fetch_id desc
      ), inj_time as (
        select i.game_id, i.team_id, max(i.published_at) as published_at
        from injury.reports i join meta on meta.game_id = i.game_id
        where i.published_at < meta.release_at
        group by 1, 2
      ), inj as (
        select i.game_id, i.player_id, i.status
        from injury.reports i
        join inj_time t on t.game_id = i.game_id and t.team_id = i.team_id and t.published_at = i.published_at
      )
      select distinct on (c.game_id, c.player_id)
        c.game_id, c.team_id, tm.full_name as team, pl.first_name || ' ' || pl.last_name as name,
        c.player_id, c.p_mp, r.oepm, r.depm, r.epm, i.status,
        (c.team_id = meta.home_team_id) as is_home
      from chosen c
      join meta on meta.game_id = c.game_id
      join core.teams tm on tm.team_id = c.team_id
      join core.players pl on pl.player_id = c.player_id
      left join rates r on r.player_id = c.player_id and r.release_at = meta.release_at
      left join inj i on i.game_id = c.game_id and i.player_id = c.player_id
      order by c.game_id, c.player_id""", (ids,)).fetchall()
    ratings = conn.execute("""with meta as (
        select distinct g.home_team_id as team_id,
          (select min(s.scheduled_tip) from core.games s
            where coalesce((s.scheduled_tip at time zone 'America/New_York')::date, s.game_date)
                = coalesce((g.scheduled_tip at time zone 'America/New_York')::date, g.game_date))
            - interval '6 hours' as release_at
        from core.games g where g.game_id = any(%s)
        union
        select g.away_team_id,
          (select min(s.scheduled_tip) from core.games s
            where coalesce((s.scheduled_tip at time zone 'America/New_York')::date, s.game_date)
                = coalesce((g.scheduled_tip at time zone 'America/New_York')::date, g.game_date))
            - interval '6 hours'
        from core.games g where g.game_id = any(%s)
      )
      select distinct on (m.team_id, m.release_at)
        m.team_id, m.release_at, r.rating_date, r.team_epm, r.team_epm_game_optimized, r.other
      from meta m
      join dnt.team_ratings r on r.team_id = m.team_id
      where r.observed_at < m.release_at - interval '1 day'
        and r.team_epm is not null and r.team_epm_game_optimized is not null
        and (r.rating_date + interval '1 day') at time zone 'America/New_York' < m.release_at - interval '1 day'
      order by m.team_id, m.release_at, r.rating_date desc, r.observed_at desc, r.fetch_id desc""", (ids, ids)).fetchall()
    box = conn.execute("""with meta as (
        select g.game_id, g.season_id,
          (select min(s.scheduled_tip) from core.games s
            where coalesce((s.scheduled_tip at time zone 'America/New_York')::date, s.game_date)
                = coalesce((g.scheduled_tip at time zone 'America/New_York')::date, g.game_date))
            - interval '6 hours' as release_at
        from core.games g where g.game_id = any(%s)
      ), roster as (
        select distinct c.player_id, meta.release_at, meta.season_id
        from (
          select distinct on (m.game_id, m.team_id, m.player_id)
            m.game_id, m.player_id, m.p_mp, m.observed_at, m.fetch_id, m.team_id
          from dnt.minutes_predictions m join meta on meta.game_id = m.game_id
          where m.observed_at < meta.release_at
          order by m.game_id, m.team_id, m.player_id, m.observed_at desc, m.fetch_id desc
        ) c
        join meta on meta.game_id = c.game_id
        where c.p_mp > 0
      ), ranked as (
        select b.player_id, r.release_at, b.minutes::float as minutes, b.ast::float as ast,
          (coalesce(b.oreb, 0) + coalesce(b.dreb, 0))::float as reb, b.blk::float as blk,
          b.fg3a::float as fg3a, b.fga::float as fga,
          (g.season_id = r.season_id) as this_season,
          row_number() over (partition by b.player_id, r.release_at
            order by g.scheduled_tip desc nulls last, g.game_id desc) as rn
        from stats.player_game_box b
        join core.games g on g.game_id = b.game_id
        join roster r on r.player_id = b.player_id
        where b.observed_at < r.release_at and g.scheduled_tip < r.release_at
          and not coalesce(b.did_not_play, false) and coalesce(b.minutes, 0) > 0
      )
      select player_id, release_at,
        avg(minutes) filter (where rn <= 5) as min5,
        sum(minutes) filter (where rn <= 20) as min20,
        sum(ast) filter (where rn <= 20) as ast20,
        sum(reb) filter (where rn <= 20) as reb20,
        sum(blk) filter (where rn <= 20) as blk20,
        sum(fg3a) filter (where rn <= 20) as fg3a20,
        sum(fga) filter (where rn <= 20) as fga20,
        count(*) filter (where this_season) as games_season
      from ranked
      group by player_id, release_at""", (ids,)).fetchall()
    preds = conn.execute("""select distinct on (p.game_id)
        p.game_id, p.p_home_score, p.p_away_score, p.home_win_prob
      from dnt.game_predictions p
      join core.games g on g.game_id = p.game_id
      where p.game_id = any(%s)
        and p.observed_at < (
          select min(s.scheduled_tip) from core.games s
          where coalesce((s.scheduled_tip at time zone 'America/New_York')::date, s.game_date)
              = coalesce((g.scheduled_tip at time zone 'America/New_York')::date, g.game_date))
          - interval '6 hours'
        and p.p_home_score is not null and p.p_away_score is not null and p.home_win_prob is not null
      order by p.game_id, p.observed_at desc, p.fetch_id desc""", (ids,)).fetchall()
    return _assemble(meta, players, ratings, box, preds)


def _per36(total, minutes):
    minutes = _num(minutes)
    if not minutes:
        return None
    return 36.0 * float(total or 0) / minutes


def _assemble(meta, players, ratings, box, preds):
    release_of = {int(r['game_id']): r['release_at'] for r in meta}
    box_of = {}
    for r in box:
        box_of[(int(r['player_id']), r['release_at'])] = r
    by_game = {}
    for r in meta:
        by_game[int(r['game_id'])] = {
            'home_team_id': int(r['home_team_id']),
            'away_team_id': int(r['away_team_id']),
            'players': [],
            'teams': {},
            'prediction': None,
        }
    for r in players:
        gid = int(r['game_id'])
        if gid not in by_game:
            continue
        stats = box_of.get((int(r['player_id']), release_of[gid]), {})
        min20 = _num(stats.get('min20')) if stats else None
        fga20 = _num(stats.get('fga20')) if stats else None
        by_game[gid]['players'].append({
            'player_id': int(r['player_id']),
            'team_id': int(r['team_id']),
            'team': r['team'],
            'name': r['name'],
            'is_home': bool(r['is_home']),
            'p_mp': _num(r['p_mp']) or 0.0,
            'oepm': _num(r['oepm']),
            'depm': _num(r['depm']),
            'epm': _num(r['epm']),
            'status': r.get('status'),
            'min_recent5': _num(stats.get('min5')) if stats else None,
            'games_season': int(stats.get('games_season') or 0) if stats else 0,
            'ast36': _per36(stats.get('ast20'), min20) if stats else None,
            'reb36': _per36(stats.get('reb20'), min20) if stats else None,
            'blk36': _per36(stats.get('blk20'), min20) if stats else None,
            'fg3a_rate': (float(stats['fg3a20']) / float(fga20)) if stats and fga20 else None,
        })
    teams_by_release = {}
    for r in ratings:
        other = r.get('other') or {}
        teams_by_release[(int(r['team_id']), r['release_at'])] = {
            'epm': _num(r['team_epm']),
            'epm_go': _num(r['team_epm_game_optimized']),
            'oepm': _num(other.get('team_oepm')),
            'depm': _num(other.get('team_depm')),
            'rating_date': str(r['rating_date']),
        }
    for gid, ctx in by_game.items():
        rel = release_of[gid]
        for team_id in (ctx['home_team_id'], ctx['away_team_id']):
            row = teams_by_release.get((team_id, rel))
            if row:
                name = next((p['team'] for p in ctx['players'] if p['team_id'] == team_id), None)
                ctx['teams'][team_id] = dict(row, name=name)
    for r in preds:
        gid = int(r['game_id'])
        if gid in by_game:
            by_game[gid]['prediction'] = {
                'home': _num(r['p_home_score']),
                'away': _num(r['p_away_score']),
                'win': _num(r['home_win_prob']),
            }
    return by_game
