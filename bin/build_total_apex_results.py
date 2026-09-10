#!/usr/bin/env python3
"""Publish the shared total from saved sport books and refresh static Overall cells."""
from __future__ import annotations

import argparse
from html import escape
import json
import os
from pathlib import Path
import re

from apex_total_results import fuse_summary

ROOT = Path(__file__).resolve().parents[1]


def total_banner(content, summary):
    overall = summary["overall"]
    record = f"{overall['wins']:,}-{overall['losses']:,}"
    if overall["pushes"]:
        record += f"-{overall['pushes']}P"
    for label, value in (("Overall", record), ("Win Rate", overall["win_rate_display"])):
        content, count = re.subn(
            rf'(<div class="label">{label}</div><div class="val mono">)[^<]*(</div>)',
            lambda match: match[1] + escape(value) + match[2], content, count=1)
        if count != 1:
            raise ValueError(f"Missing static results cell: {label}")
    for attribute, value in (("data-apex-season-record", record),
                             ("data-apex-season-win-rate", overall["win_rate_display"])):
        content, count = re.subn(rf'{attribute}="[^"]*"', f'{attribute}="{escape(value)}"', content, count=1)
        if count != 1:
            raise ValueError(f"Missing static results attribute: {attribute}")
    content, count = re.subn(r'\b[\d,]+ POSITIONS TRACKED',
                           f"{overall['positions_tracked']:,} POSITIONS TRACKED", content, count=1)
    if count != 1:
        raise ValueError("Missing tracked positions label")
    return content


def write_full(path, content):
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(content, encoding="utf-8")
        if path.exists():
            temporary.chmod(path.stat().st_mode & 0o777)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def build(root=ROOT):
    root = Path(root)
    source = root / "data/apex_results_summary.json"
    summary = fuse_summary(json.loads(source.read_text(encoding="utf-8")), data_dir=source.parent)
    # Prepare and validate all outputs before replacing the shared summary.
    outputs = {source: json.dumps(summary, indent=2, ensure_ascii=False) + "\n"}
    for relative in ("results/index.html", "results.html"):
        path = root / relative
        if path.exists():
            outputs[path] = total_banner(path.read_text(encoding="utf-8"), summary)
    for path, content in outputs.items():
        write_full(path, content)
    print(f"TOTAL_APEX={summary['overall_wins']}W-{summary['overall_losses']}L-{summary['overall_pushes']}P SPORTS={','.join(summary['sports_included'])}")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    build(parser.parse_args().root)
