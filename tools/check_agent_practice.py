#!/usr/bin/env python3
"""Check the current APEX practice files and removal of superseded entry points."""

import hashlib
import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
manifest = json.loads((root / "docs/AGENT_PRACTICE_MANIFEST.json").read_text(encoding="utf8"))
errors = []
for name, wanted in manifest["managed_files"].items():
    p = root / name
    got = hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else "MISSING"
    if got != wanted:
        errors.append(name + ": content differs from adopted practice")
for name in manifest["removed_files"]:
    if (root / name).exists():
        errors.append(name + ": obsolete instruction remains")
for error in errors:
    print(error)
print("APEX practice " + manifest["version"] + ": " + ("FAIL" if errors else "PASS"))
sys.exit(bool(errors))
