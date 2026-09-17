#!/usr/bin/env python3
"""Publish the shared total from saved sport books for the shared site header."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from apex_total_results import fuse_summary

ROOT = Path(__file__).resolve().parents[1]


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
    for path, content in outputs.items():
        write_full(path, content)
    print(f"TOTAL_APEX={summary['overall_wins']}W-{summary['overall_losses']}L-{summary['overall_pushes']}P SPORTS={','.join(summary['sports_included'])}")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    build(parser.parse_args().root)
