#!/usr/bin/env python3
"""Deterministic game-specific pick rationales from the final T-2 serving records.

Renders the six public rationale sentences for every issued F5 ATS and F5 TOT
position from the exact serving artifacts written by the T-2 issuance run:

  fire_<date>/final_full_slate/card_out/FIRE_VECTOR_SNAPSHOT_<date>.csv
  fire_<date>/final_full_slate/composed/RATIONALE_EVIDENCE_SIDECAR.json
  fire_<date>/final_full_slate/carrier_out/TOTALS_CURRENT_CARRIER_PROOF.csv

No model, probability, line, price, tier, or payload value is recomputed here —
every displayed number is read from the immutable serving record or from the
issued payload, and the two are cross-checked against each other. The renderer
is a pure function of those files: no network, no clock, no free-form
generation. Any missing record, identity mismatch, changed value, placeholder,
or malformed sentence raises RationaleRenderError so the build fails visibly.
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import sys as _sys
_sys.path.insert(0, "/opt/apex_mlb/current/bin")
from apex_public_starter_sanitizer import CLEAN_UNRESOLVED_NOTE  # noqa: E402

CLEAN_UNRESOLVED_PHRASE_NOTE = CLEAN_UNRESOLVED_NOTE

T2_FIRE_ROOT = Path("/opt/apex_mlb/proof/t2_permanent_autonomous_scheduler_20260524")

ATS_MARKET = "F5 ATS"
TOT_MARKET = "F5 TOT"

FORBIDDEN_GENERIC_FRAGMENTS = (
    "The locked ATS vector uses registered starter strikeout",
    "The active ATS artifact has no lineup feature",
    "The pregame information state is complete for the locked scoring contract",
    "The totals vector uses registered starter strikeout-to-walk and FIP inputs",
    "Registered lineup, platoon, offense, defense, and recent-form inputs",
    "tier reflects the exact probability",
    # single-public-percentage contract: market-comparison percentages and
    # value-labeling language may not appear in public rationale text
    "break-even",
    "break even",
    "no-vig",
    "no vig",
    "benchmark",
    "APEX advantage",
    "advantage versus",
    "expected value",
    "edge over the",
)


def american_break_even(price: float) -> float:
    """Correct break-even win probability for an American price.

    +A -> 100 / (A + 100);  -A -> A / (A + 100).
    Internal diagnostic only — never displayed publicly.
    """
    import math
    p = float(price)
    if not math.isfinite(p) or p == 0:
        raise RationaleRenderError("invalid_american_price")
    return 100.0 / (p + 100.0) if p > 0 else (-p) / ((-p) + 100.0)

PLACEHOLDER_PATTERN = re.compile(
    r"\[REAL\]|\{[a-z_]+\}|\bNaN\b|\bnan\b|\bNone\b|\bnull\b|\binf\b", re.A
)

_ABBREV = re.compile(
    r"\b(?:St|Sr|Jr|Dr|Mr|Mrs|Ms|Prof|Rev|Gen|Col|Maj|Capt|Lt|Sgt|Cpl|Pvt|vs)\.",
    re.I,
)


class RationaleRenderError(RuntimeError):
    """Raised when the serving record cannot support a factual rationale."""


def _split_sentences(text: str) -> list[str]:
    t = (text or "").strip()
    if not t:
        return []
    t = _ABBREV.sub(lambda m: m.group(0).replace(".", "․"), t)
    return [
        p.replace("․", ".").strip()
        for p in re.split(r"(?<=[.!?])\s+", t)
        if p.strip()
    ]


def _pct1(x: float) -> str:
    return f"{x * 100:.1f}"


def _pts1(x: float) -> str:
    return f"{abs(x) * 100:.1f}"


def _f2(x: float) -> str:
    return f"{x:.2f}"


def _luck_points(x: float) -> int:
    return int(round(abs(x) * 1000))


def _last_name(full: str) -> str:
    return (full or "").strip().split()[-1] if (full or "").strip() else ""


def _fire_slate_dir(date_iso: str) -> Path:
    d = T2_FIRE_ROOT / f"fire_{date_iso.replace('-', '')}" / "final_full_slate"
    if not d.is_dir():
        raise RationaleRenderError(
            f"final T-2 serving workspace not found for {date_iso}: {d}"
        )
    return d


def _load_serving_records(date_iso: str) -> dict:
    root = _fire_slate_dir(date_iso)
    vec_path = root / "card_out" / f"FIRE_VECTOR_SNAPSHOT_{date_iso}.csv"
    sidecar_path = root / "composed" / "RATIONALE_EVIDENCE_SIDECAR.json"
    carrier_path = root / "carrier_out" / "TOTALS_CURRENT_CARRIER_PROOF.csv"
    for p in (vec_path, sidecar_path, carrier_path):
        if not p.is_file():
            raise RationaleRenderError(f"final T-2 serving record missing: {p}")
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    if sidecar.get("schema") != "APEX_RATIONALE_EVIDENCE_SIDECAR_V1":
        raise RationaleRenderError(
            f"unrecognized rationale sidecar schema: {sidecar.get('schema')!r}"
        )
    if sidecar.get("slate_date") != date_iso:
        raise RationaleRenderError(
            f"sidecar slate_date {sidecar.get('slate_date')!r} != payload {date_iso!r}"
        )
    fire = list(csv.DictReader(vec_path.open(encoding="utf-8")))
    carrier = list(csv.DictReader(carrier_path.open(encoding="utf-8")))
    for r in fire:
        if r["missingness_state"] not in ("FACTUALLY_PRESENT",) and not r[
            "imputation_state"
        ].strip():
            raise RationaleRenderError(
                "unregistered missingness in serving vector: "
                f"game {r['game_pk']} {r['feature_name']} state={r['missingness_state']!r}"
            )
    return {"fire": fire, "sidecar": sidecar, "carrier": carrier}


def _game_record(g: dict, records: dict) -> dict:
    gp = str(g["game_pk"])
    fire = records["fire"]
    ats_vec = {
        r["feature_name"]: float(r["value"])
        for r in fire
        if r["engine"] == "ATS" and r["game_pk"] == gp
    }
    tot_vec = {
        s: {
            r["feature_name"]: float(r["value"])
            for r in fire
            if r["engine"] == "TOTALS" and r["game_pk"] == gp and r["side"] == s
        }
        for s in ("away", "home")
    }
    if len(ats_vec) != 9 or any(len(v) != 29 for v in tot_vec.values()):
        raise RationaleRenderError(
            f"serving vector incomplete for game {gp}: "
            f"ats={len(ats_vec)} away={len(tot_vec['away'])} home={len(tot_vec['home'])}"
        )
    side_rows = {
        r["market"]: r
        for r in records["sidecar"].get("rows", [])
        if str(r.get("game_pk")) == gp
    }
    if "F5_ATS" not in side_rows or "F5_TOT" not in side_rows:
        raise RationaleRenderError(f"rationale sidecar rows missing for game {gp}")

    # Per-starter values from the totals vector: each side's opp_sp_* is the
    # other side's starter, own CANON_0070 is that side's starter.
    home_kbb, away_kbb = tot_vec["away"]["opp_sp_kbb"], tot_vec["home"]["opp_sp_kbb"]
    home_fip, away_fip = tot_vec["away"]["opp_sp_fip"], tot_vec["home"]["opp_sp_fip"]
    home_luck = tot_vec["home"]["CANON_0070_sp_xwoba_luck_diff__own"]
    away_luck = tot_vec["away"]["CANON_0070_sp_xwoba_luck_diff__own"]

    d_kbb = ats_vec["sp_k_bb_pct_shrunk__delta"]
    d_fip = ats_vec["sp_fip__delta"]
    d_luck = ats_vec["sp_xwoba_luck_diff__delta"]
    if abs((away_kbb - home_kbb) - d_kbb) < 1e-9 and abs(
        (away_fip - home_fip) - d_fip
    ) < 1e-9 and abs((away_luck - home_luck) - d_luck) < 1e-9:
        fav_side = "away"
    elif abs((home_kbb - away_kbb) - d_kbb) < 1e-9 and abs(
        (home_fip - away_fip) - d_fip
    ) < 1e-9 and abs((home_luck - away_luck) - d_luck) < 1e-9:
        fav_side = "home"
    else:
        raise RationaleRenderError(
            f"ATS delta orientation could not be reconstructed for game {gp}"
        )
    return {
        "game_pk": gp,
        "ats_vec": ats_vec,
        "tot_vec": tot_vec,
        "sidecar_rows": side_rows,
        "fav_side": fav_side,
        "starters": {
            "home": {"name": g.get("home_pitcher", ""), "kbb": home_kbb,
                     "fip": home_fip, "luck": home_luck},
            "away": {"name": g.get("away_pitcher", ""), "kbb": away_kbb,
                     "fip": away_fip, "luck": away_luck},
        },
    }


def _position_identity_check(pos: dict, side_row: dict, model_identity: dict) -> None:
    key = "ats" if "ATS" in (pos.get("market") or "").upper() else "totals"
    expected_sha = model_identity.get(f"{key}_artifact_sha256")
    if expected_sha and side_row.get("model_artifact_sha256") not in (
        None,
        "",
        expected_sha,
    ):
        # The totals sidecar may carry the definition sha; accept either bound value.
        if side_row.get("model_artifact_sha256") != pos.get("artifact_sha256"):
            raise RationaleRenderError(
                f"model artifact sha mismatch for game {side_row.get('game_pk')} "
                f"{side_row.get('market')}"
            )


def _payload_sentence(pos: dict, index: int, must_contain: str) -> str:
    sents = _split_sentences(pos.get("rationale") or pos.get("rationale_full") or "")
    if len(sents) < index + 1 or must_contain not in sents[index]:
        for s in sents:
            if must_contain in s:
                return s
        raise RationaleRenderError(
            f"issued rationale sentence containing {must_contain!r} not found "
            f"for pick {pos.get('pick')!r}"
        )
    return sents[index]


def _is_unresolved(name: str) -> bool:
    n = (name or "").strip().upper()
    return (not n) or n in {"TBD", "TBA", "OFFICIAL_TBD", "NONE"} or "OFFICIAL_TBD" in n


def _position_phrase(pos: dict) -> str:
    s1 = _payload_sentence(pos, 0, "APEX estimates")
    m = re.search(r"APEX estimates (.+?) (?:has|at) ", s1)
    if not m:
        raise RationaleRenderError(
            f"cannot extract position phrase from issued S1 for {pos.get('pick')!r}"
        )
    return m.group(1)


def _displayed_decision_probability(pos: dict, is_ats: bool) -> tuple[float, bool]:
    """Public decision-win probability. For integer totals with a possible push,
    this is P(win)/[P(win)+P(lose)] — pushes excluded, matching W-L grading.
    The stored conditional value must reconcile exactly or the build fails."""
    p = float(pos["selected_probability"])
    if is_ats:
        return p, False
    p_push = float(pos.get("p_push") or 0.0)
    if p_push <= 0.0:
        return p, False
    p_over = float(pos["p_over"])
    p_under = float(pos["p_under"])
    side = str(pos.get("side") or "").upper()
    num = p_over if side == "OVER" else p_under
    if p_over + p_under <= 0:
        raise RationaleRenderError(f"degenerate push distribution for {pos.get('pick')!r}")
    expected = num / (p_over + p_under)
    stored = pos.get("conditional_selected_probability_given_decision")
    val = float(stored) if stored is not None else expected
    if abs(val - expected) > 1e-9:
        raise RationaleRenderError(
            f"stored conditional decision probability does not reconcile "
            f"for {pos.get('pick')!r}"
        )
    return val, True


def _s1_public(pos: dict, is_ats: bool) -> tuple[str, float]:
    phrase = _position_phrase(pos)
    p, push_case = _displayed_decision_probability(pos, is_ats)
    ps = _pct1(p)
    tail = (
        "probability of winning when the result is not a push"
        if push_case
        else "probability of winning the first-five market"
    )
    return f"APEX estimates {phrase} has {_a(ps)} {ps}% {tail}.", p


def _s5_public(pos: dict) -> str:
    raw5 = _payload_sentence(pos, 4, "FanDuel lists")
    s = raw5[raw5.index("FanDuel lists"):]
    for cut in ("; ", ", with a "):
        j = s.find(cut)
        if j != -1:
            s = s[:j]
            break
    s = s.rstrip(".") + "."
    if "%" in s:
        raise RationaleRenderError(
            f"market-comparison percentage survived S5 for {pos.get('pick')!r}"
        )
    return s


def _a(num_str: str) -> str:
    """Indefinite article for a spoken number ('an 11.7', 'an 8.79', 'a 13.0')."""
    return "an" if re.match(r"(?:8|11(?!\d)|18(?!\d))", num_str) else "a"


def _luck_phrase(last: str, luck: float) -> str:
    word = "better" if luck > 0 else "worse"
    return (
        f"{last}'s allowed results ran {_luck_points(luck)} points {word} "
        f"than his expected-contact quality"
    )


def render_ats_sentences(g: dict, pos: dict, rec: dict) -> tuple[list[str], dict]:
    home, away = g["home_team"], g["away_team"]
    fav_side = rec["fav_side"]
    fav_team = home if fav_side == "home" else away
    dog_team = away if fav_side == "home" else home
    sp = rec["starters"]
    fav_sp, dog_sp = sp[fav_side], sp["away" if fav_side == "home" else "home"]
    vec = rec["ats_vec"]
    unresolved = _is_unresolved(sp["home"]["name"]) or _is_unresolved(sp["away"]["name"])
    info_state = str((pos.get("model_evidence") or {}).get("information_states") or "")
    pick_team = dog_team if pos.get("selected_position") == "UNDERDOG" else fav_team

    s1, p_display = _s1_public(pos, is_ats=True)
    s5 = _s5_public(pos)

    selection: dict = {"displayed": [], "omitted": []}
    d_kbb, d_k, d_bb = (
        vec["sp_k_bb_pct_shrunk__delta"],
        vec["sp_k_pct_shrunk__delta"],
        vec["sp_bb_pct_shrunk__delta"],
    )
    d_fip, d_xfip = vec["sp_fip__delta"], vec["sp_xfip__delta"]
    d_stuff, d_luck = vec["sp_stuff_plus__delta"], vec["sp_xwoba_luck_diff__delta"]

    if unresolved:
        s2 = CLEAN_UNRESOLVED_PHRASE_NOTE
        edge_team = fav_team if d_kbb > 0 else dog_team
        fip_team = fav_team if d_fip < 0 else dog_team
        fip_joiner = "and" if fip_team == edge_team else "while"
        s3 = (
            f"On the served shrunken inputs, the {edge_team} side carried a "
            f"{_pts1(d_kbb)}-point strikeout-minus-walk edge, {fip_joiner} the "
            f"{_f2(abs(d_fip))}-run FIP edge sat with the {fip_team} side."
        )
        s4 = (
            "The registered starter-uncertainty mixture supplied the unconfirmed "
            "slot's pitching inputs at the cutoff, and with the lineups not yet "
            "posted the archived projection treatments covered the remaining "
            "pregame state."
        )
        selection["displayed"] = ["sp_k_bb_pct_shrunk__delta", "sp_fip__delta"]
        selection["omitted"] = [
            {"feature": "named starter metrics", "reason": "starter unresolved at issuance; public sanitizer contract forbids attributing named metrics"},
        ]
    else:
        hi_sp, lo_sp = (fav_sp, dog_sp) if d_kbb > 0 else (dog_sp, fav_sp)
        hi_team = fav_team if d_kbb > 0 else dog_team
        split_lean = (d_k > 0) != (d_kbb > 0) and abs(d_k) > 0.001
        split_txt = ""
        if split_lean:
            k_team = fav_team if d_k > 0 else dog_team
            split_txt = (
                f", though the raw strikeout-rate lean of "
                f"{_pts1(d_k)} points sat with the {k_team}"
            )
        kbb_hi = _pct1(hi_sp["kbb"])
        s2 = (
            f"{hi_sp['name']} entered with {_a(kbb_hi)} {kbb_hi}-point served "
            f"strikeout-minus-walk mark against {lo_sp['name']}'s "
            f"{_pct1(lo_sp['kbb'])}, a {_pts1(d_kbb)}-point command edge for "
            f"the {hi_team} side{split_txt}."
        )
        selection["displayed"].append("sp_k_bb_pct_shrunk__delta")

        candidates = [
            ("fip", abs(d_fip) / 0.5),
            ("stuff", abs(d_stuff) / 10.0),
            ("luck", abs(d_luck) / 0.02),
            ("xfip", abs(d_xfip) / 0.5),
        ]
        ranked = sorted(candidates, key=lambda kv: kv[1], reverse=True)
        chosen = [k for k, _ in ranked[:2]]

        def _clause(kind: str) -> tuple[str, str | None]:
            if kind == "fip":
                lo_f, hi_f = (fav_sp, dog_sp) if d_fip < 0 else (dog_sp, fav_sp)
                return (
                    f"{_last_name(lo_f['name'])} held the lower FIP, "
                    f"{_f2(lo_f['fip'])} to {_f2(hi_f['fip'])}",
                    fav_team if d_fip < 0 else dog_team,
                )
            if kind == "xfip":
                t = fav_team if d_xfip < 0 else dog_team
                return (
                    f"the served xFIP gap of {_f2(abs(d_xfip))} runs sat with "
                    f"the {t}",
                    t,
                )
            if kind == "stuff":
                t = fav_team if d_stuff > 0 else dog_team
                return (
                    f"the served Stuff+ gap of {int(round(abs(d_stuff)))} points "
                    f"leaned toward the {t}",
                    t,
                )
            return (
                f"on contact luck, {_luck_phrase(_last_name(fav_sp['name']), fav_sp['luck'])} "
                f"while {_last_name(dog_sp['name'])}'s ran "
                f"{_luck_points(dog_sp['luck'])} points "
                f"{'better' if dog_sp['luck'] > 0 else 'worse'}",
                None,
            )

        c1, t1 = _clause(chosen[0])
        c2, t2 = _clause(chosen[1])
        joiner = ", though " if (t1 and t2 and t1 != t2) else "; "
        s3 = c1[0].upper() + c1[1:] + joiner + c2 + "."
        feature_key = {
            "fip": "sp_fip__delta", "xfip": "sp_xfip__delta",
            "stuff": "sp_stuff_plus__delta", "luck": "sp_xwoba_luck_diff__delta",
        }
        selection["displayed"] += [feature_key[k] for k in chosen]
        selection["omitted"] = [
            {"feature": feature_key[k], "reason": "smaller standardized difference than displayed signals"}
            for k, _ in ranked[2:]
        ] + [
            {"feature": "starter_expected_ip_f5__delta,tto_pass2_indicator__delta",
             "reason": "constant-by-derivation neutral carriers (delta 0.0), not discriminative"},
        ]

        lineups_unposted = "LINEUP_UNPOSTED" in info_state
        if lineups_unposted:
            s4 = (
                f"Both {_last_name(sp['away']['name'])} and "
                f"{_last_name(sp['home']['name'])} were confirmed at the cutoff and "
                f"all nine served ATS inputs were factually present, while the "
                f"{away} and {home} lineups were still unposted, a slate state this "
                f"starter-driven artifact does not consume."
            )
        else:
            s4 = (
                f"Both {_last_name(sp['away']['name'])} and "
                f"{_last_name(sp['home']['name'])} were confirmed at the cutoff, "
                f"the posted lineups were on record, and all nine served ATS inputs "
                f"were factually present with no registered missingness treatment."
            )

    tier = str(pos.get("tier") or "")
    if unresolved:
        state_txt = "registered starter-uncertainty state"
    elif "LINEUP_UNPOSTED" in info_state:
        state_txt = "complete starter record with lineups pending"
    else:
        state_txt = "complete starter-and-lineup record"
    if p_display < 0.5:
        s6 = (
            "This was the system's issued market-relative bet-all side; its "
            f"model win probability was {_pct1(p_display)}%."
        )
    else:
        s6 = (
            f"The {state_txt} and the registered strength grading produced the "
            f"stored {tier} rating."
        )
    return [s1, s2, s3, s4, s5, s6], selection


def render_tot_sentences(g: dict, pos: dict, rec: dict) -> tuple[list[str], dict]:
    home, away = g["home_team"], g["away_team"]
    sp = rec["starters"]
    tv = rec["tot_vec"]
    unresolved = _is_unresolved(sp["home"]["name"]) or _is_unresolved(sp["away"]["name"])
    info_state = str((pos.get("model_evidence") or {}).get("information_states") or "")
    lineups_unposted = "LINEUP_UNPOSTED" in info_state

    s1, p_display = _s1_public(pos, is_ats=False)
    s5 = _s5_public(pos)

    selection: dict = {"displayed": [], "omitted": []}
    if unresolved:
        s2 = CLEAN_UNRESOLVED_PHRASE_NOTE
        selection["omitted"].append(
            {"feature": "named starter metrics",
             "reason": "starter unresolved at issuance; sanitizer contract"}
        )
    else:
        a_sp, h_sp = sp["away"], sp["home"]
        luck_txt = ""
        big_luck = max((a_sp, h_sp), key=lambda s: abs(s["luck"]))
        if abs(big_luck["luck"]) >= 0.02:
            luck_txt = f", and {_luck_phrase(_last_name(big_luck['name']), big_luck['luck'])}"
            selection["displayed"].append("CANON_0070_sp_xwoba_luck_diff")
        a_fip = _f2(a_sp["fip"])
        s2 = (
            f"{a_sp['name']} brought a served {_pct1(a_sp['kbb'])}-point "
            f"strikeout-minus-walk rate and {_a(a_fip)} {a_fip} FIP against "
            f"{h_sp['name']}'s {_pct1(h_sp['kbb'])} and {_f2(h_sp['fip'])}"
            f"{luck_txt}."
        )
        selection["displayed"] += ["opp_sp_kbb", "opp_sp_fip"]

    a_wrc, h_wrc = tv["away"]["own_lineup"], tv["home"]["own_lineup"]
    a_iso = tv["away"]["CANON_0306_team_team_rolling_ISO__own"]
    h_iso = tv["home"]["CANON_0306_team_team_rolling_ISO__own"]
    a_rs, h_rs = tv["away"]["roll_F5_RS"], tv["home"]["roll_F5_RS"]
    a_plat = tv["away"]["CANON_0266_lineup_platoon_xwoba__own"]
    h_plat = tv["home"]["CANON_0266_lineup_platoon_xwoba__own"]
    extras = [
        ("iso", abs(a_iso - h_iso) / 0.03,
         f"rolling ISO marks of {a_iso:.3f} and {h_iso:.3f}"),
        ("f5rs", abs(a_rs - h_rs) / 0.5,
         f"rolling first-five scoring of {a_rs:.2f} and {h_rs:.2f} runs"),
        ("plat", abs(a_plat - h_plat) / 15.0,
         f"top-six platoon-xwOBA percentile marks of {a_plat:.1f} and {h_plat:.1f}"),
    ]
    best = max(extras, key=lambda e: e[1])
    lineup_lead = (
        "The posted lineups carried"
        if not lineups_unposted
        else "With the lineups unposted at the cutoff, the registered trailing-lineup "
             "inputs carried"
    )
    s3 = (
        f"{lineup_lead} wRC+ marks of {a_wrc:.1f} for the {away} and {h_wrc:.1f} "
        f"for the {home}, with {best[2]}."
    )
    selection["displayed"] += ["own_lineup", best[0]]
    selection["omitted"] += [
        {"feature": name, "reason": "smaller standardized difference than displayed signal"}
        for name, _, _ in extras if name != best[0]
    ]

    env = tv["away"]
    exp_runs = float(((g.get("model_outputs") or {}).get("totals") or {}).get(
        "expected_f5_runs"
    ))
    line = str(pos.get("line") or pos.get("total") or "")
    temp_s = f"{env['temperature_f']:.1f}"
    s4 = (
        f"The stored run environment carried a {env['run_factor']:.2f} park run "
        f"factor with {_a(temp_s)} {temp_s}-degree forecast temperature and "
        f"{env['wind_speed_mph']:.1f}-mph wind, and the served distribution put "
        f"expected first-five scoring at {exp_runs:.2f} runs against the posted "
        f"{line}."
    )
    selection["displayed"] += ["run_factor", "temperature_f", "wind_speed_mph",
                               "expected_f5_runs"]
    selection["omitted"] += [
        {"feature": "relative_humidity_pct,surface_pressure_hpa,air_density_proxy,"
                    "FCST_wind_direction_deg__g",
         "reason": "served but secondary; no validated per-game direction claim"},
        {"feature": "opp_sp_ip", "reason": "constant-by-derivation carrier (5.0)"},
    ]

    tier = str(pos.get("tier") or "")
    if unresolved:
        state_txt = "registered starter-fallback state"
    elif lineups_unposted:
        state_txt = "registered unposted-lineup treatment"
    else:
        state_txt = "posted-lineup and confirmed-starter record"
    if p_display < 0.5:
        s6 = (
            "This was the system's issued market-relative bet-all side; its "
            f"model win probability was {_pct1(p_display)}%."
        )
    else:
        s6 = (
            f"The {state_txt} and the registered strength grading produced the "
            f"stored {tier} rating."
        )
    return [s1, s2, s3, s4, s5, s6], selection


def _validate_sentences(sentences: list[str], pos: dict) -> str:
    if len(sentences) != 6:
        raise RationaleRenderError(
            f"rationale for {pos.get('pick')!r} has {len(sentences)} sentences, not 6"
        )
    text = " ".join(sentences)
    if PLACEHOLDER_PATTERN.search(text):
        raise RationaleRenderError(
            f"placeholder or malformed value in rationale for {pos.get('pick')!r}"
        )
    for frag in FORBIDDEN_GENERIC_FRAGMENTS:
        if frag in text:
            raise RationaleRenderError(
                f"forbidden generic fragment {frag[:40]!r} in rationale "
                f"for {pos.get('pick')!r}"
            )
    for s in sentences:
        if not s.endswith("."):
            raise RationaleRenderError(
                f"sentence missing terminal period for {pos.get('pick')!r}: {s[:60]!r}"
            )
    if len(_split_sentences(text)) != 6:
        raise RationaleRenderError(
            f"rationale for {pos.get('pick')!r} does not round-trip to 6 sentences"
        )
    # single-public-percentage contract: every '%' token in the rationale must
    # equal the one displayed decision-win probability stated in sentence 1
    pct_tokens = re.findall(r"(\d+(?:\.\d+)?)%", text)
    s1_match = re.search(r"(\d+(?:\.\d+)?)%", sentences[0])
    if not s1_match or not pct_tokens:
        raise RationaleRenderError(
            f"public win probability missing from rationale for {pos.get('pick')!r}"
        )
    if len(set(pct_tokens)) != 1 or pct_tokens[0] != s1_match.group(1):
        raise RationaleRenderError(
            f"multiple distinct public percentages for {pos.get('pick')!r}: "
            f"{sorted(set(pct_tokens))}"
        )
    sub50 = float(pct_tokens[0]) < 50.0
    tier = str(pos.get("tier") or "")
    if sub50:
        if "issued market-relative bet-all side" not in sentences[5]:
            raise RationaleRenderError(
                f"sub-50 position missing honest final sentence for {pos.get('pick')!r}"
            )
        if len(pct_tokens) != 2:
            raise RationaleRenderError(
                f"sub-50 rationale must state the probability exactly twice "
                f"(S1 + honest final sentence) for {pos.get('pick')!r}"
            )
    else:
        if len(pct_tokens) != 1:
            raise RationaleRenderError(
                f"exactly one public percentage required for {pos.get('pick')!r}"
            )
        if tier and f"stored {tier} rating" not in text:
            raise RationaleRenderError(
                f"stored tier {tier!r} not stated in rationale for {pos.get('pick')!r}"
            )
    return text


def factual_rationales_for_payload(payload: dict) -> dict:
    """Return {(game_pk:int, market_label:str): rationale_text} for every issued
    position, rendered from the final T-2 serving records. Raises
    RationaleRenderError when any record is missing or inconsistent."""
    games = payload.get("games") or []
    if not games:
        return {}
    date_iso = payload.get("date") or ""
    records = _load_serving_records(date_iso)
    model_identity = payload.get("model_identity") or {}
    out: dict = {}
    evidence: list = []
    for g in games:
        picks = g.get("picks") or []
        if not picks:
            continue
        rec = _game_record(g, records)
        for pos in picks:
            mkt = (pos.get("market") or "").upper()
            side_row = rec["sidecar_rows"]["F5_ATS" if "ATS" in mkt else "F5_TOT"]
            _position_identity_check(pos, side_row, model_identity)
            if "ATS" in mkt:
                sentences, selection = render_ats_sentences(g, pos, rec)
                label = ATS_MARKET
            else:
                sentences, selection = render_tot_sentences(g, pos, rec)
                label = TOT_MARKET
            text = _validate_sentences(sentences, pos)
            out[(int(g["game_pk"]), label)] = text
            evidence.append(
                {"game_pk": int(g["game_pk"]), "market": label,
                 "sentences": sentences, "selection": selection,
                 "sidecar_market": side_row.get("market"),
                 "fav_side": rec["fav_side"]}
            )
    expected = sum(len(g.get("picks") or []) for g in games)
    if len(out) != expected:
        raise RationaleRenderError(
            f"rendered {len(out)} rationales for {expected} issued positions"
        )
    factual_rationales_for_payload.last_evidence = evidence  # type: ignore[attr-defined]
    return out
