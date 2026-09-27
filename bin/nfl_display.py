"""NFL display formatting from the saved pick; no model or outcome changes."""
import math
import re

def probability_text(row):
    if row.get("rating_policy_version") in ("NFL_CONDITIONAL_WIN_BANDS_V1", "NFL_PROP_RELATIVE_QUARTILES_V1"):
        w=float(row["issued_probability"]);s=float(row.get("push_probability",0))
        p=float(row["rating_probability"])
        if not all(map(math.isfinite,(w,s,p))) or min(w,s)<0 or s>=1 or w+s>1+1e-12:
            raise ValueError("Invalid prediction probabilities")
        expected=min(1.,w/(1-s))
        if p!=expected or row.get("rating_probability_basis")!="WIN_CONDITIONAL_ON_NON_PUSH_V1":
            raise ValueError("Displayed percentage differs from saved prediction")
        tier=("WEAK","MODERATE","STRONG","ELITE")[min(3,int(4*float(row["relative_rating_percentile"])))] if row.get("rating_policy_version")=="NFL_PROP_RELATIVE_QUARTILES_V1" else ("WEAK","MODERATE","STRONG","ELITE")[sum(p>=x for x in (.52,.54,.58))]
        if row.get("rating_tier",row.get("tier"))!=tier:
            raise ValueError("Displayed rating differs from saved prediction")
        return f"{math.floor(p*1000)/10:.1f}%"
    value=next((row.get(k) for k in ("win_probability","apex_win_probability","issued_probability") if row.get(k) is not None),None)
    if value is None:return "—"
    try:
        p=float(value)
        return f"{p*100 if p<=1 else p:.1f}%"
    except (TypeError,ValueError):return str(value)

def plain_language(value):
    """Presentation copy only; saved data and calculations are untouched."""
    value = str(value)
    replacements = [
        (r"\brelease cards?\b", "picks"),
        (r"\bpicks card\b", "picks"),
        (r"\binherited V2 serving is active\b", "The NFL models are running"),
        (r"\binherited V2 serving\b", "NFL predictions"),
        (r"\bas-issued model estimates\b", "model predictions"),
        (r"\bnominal model tiers\b", "ratings based on predicted win percentage"),
        (r"\bfrozen-model\b", "model"),
        (r"\bfrozen\b", "saved"),
        (r"\bsealed-to-settled reconciliation\b", "Picks and results check"),
        (r"\bcanonical as-issued tier projection\b", "Ratings and results"),
        (r"\bcanonical settlement receipt\b", "Results verification"),
        (r"\bcanonical results payload\b", "Results data"),
        (r"\bcanonical result\b", "verified results"),
        (r"\bcanonical projection\b", "results report"),
        (r"\bcanonical\b", "verified"),
        (r"\bimmutable issuance\b", "original picks"),
        (r"\bimmutable\b", "original"),
        (r"\bissuance\b", "picks"),
        (r"\bissued contracts\b", "picks"),
        (r"\bcontracts?\b", "definitions"),
        (r"\bsealed\b", "saved"),
        (r"\bsource-lineage\b", "source history"),
        (r"\blineage\b", "source history"),
        (r"\bfactual hydration\b", "data updates"),
        (r"\bhydration\b", "data updates"),
    ]
    for pattern, replacement in replacements:
        value = re.sub(pattern, replacement, value, flags=re.I)
    return value
