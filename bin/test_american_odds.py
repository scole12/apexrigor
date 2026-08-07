#!/usr/bin/env python3
"""Unit tests for the corrected American-odds break-even formulas.

+A -> 100/(A+100);  -A -> A/(A+100).
Run directly: exits non-zero on any failure and prints a JSON report.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from apex_factual_rationale_renderer import american_break_even

CASES = {
    "+100": 100.0 / 200.0,
    "+114": 100.0 / 214.0,
    "+116": 100.0 / 216.0,
    "+140": 100.0 / 240.0,
    "-102": 102.0 / 202.0,
    "-104": 104.0 / 204.0,
    "-114": 114.0 / 214.0,
    "-116": 116.0 / 216.0,
    "-140": 140.0 / 240.0,
}

def main() -> int:
    rows, failures = [], 0
    for label, expected in CASES.items():
        got = american_break_even(float(label))
        ok = abs(got - expected) < 1e-12
        failures += (not ok)
        rows.append({"price": label, "expected": expected, "got": got, "pass": ok})
    spot = {
        "+116_pct": f"{american_break_even(116) * 100:.6f}",
        "-116_pct": f"{american_break_even(-116) * 100:.6f}",
        "+116_expected": "46.296296", "-116_expected": "53.703704",
    }
    spot_ok = (abs(american_break_even(116) - 100.0 / 216.0) < 1e-12
               and abs(american_break_even(-116) - 116.0 / 216.0) < 1e-12)
    report = {"cases": rows, "spot_check": spot, "spot_check_pass": spot_ok,
              "failures": failures + (0 if spot_ok else 1),
              "POSITIVE_ODDS_FORMULA_TEST": "PASS" if all(
                  r["pass"] for r in rows if r["price"].startswith("+")) else "FAIL",
              "NEGATIVE_ODDS_FORMULA_TEST": "PASS" if all(
                  r["pass"] for r in rows if r["price"].startswith("-")) else "FAIL"}
    print(json.dumps(report, indent=1))
    return 0 if report["failures"] == 0 else 1

if __name__ == "__main__":
    raise SystemExit(main())
