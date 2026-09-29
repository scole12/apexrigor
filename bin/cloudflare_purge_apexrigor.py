#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

CREDS_CANDIDATES = [
    Path("/etc/apex/credentials/apex-ops-cloudflare.env"),
    Path("/etc/apex/mlb.env"),
]


def load_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def load_cf_creds() -> tuple[dict[str, str], str]:
    merged: dict[str, str] = {}
    source = ""
    for path in CREDS_CANDIDATES:
        env = load_env(path)
        if env.get("CLOUDFLARE_API_TOKEN") and env.get("CLOUDFLARE_ZONE_ID"):
            # Prefer first file that has both; still allow later keys to fill gaps.
            if not merged.get("CLOUDFLARE_API_TOKEN"):
                source = str(path)
            for k, v in env.items():
                merged.setdefault(k, v)
    return merged, source


def purge(files: list[str] | None = None) -> dict:
    env, source = load_cf_creds()
    token = env.get("CLOUDFLARE_API_TOKEN")
    zone = env.get("CLOUDFLARE_ZONE_ID")
    if not token or not zone:
        raise SystemExit("missing CF creds")
    body = {"purge_everything": True} if not files else {"files": files}
    req = urllib.request.Request(
        f"https://api.cloudflare.com/client/v4/zones/{zone}/purge_cache",
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.load(resp)
    except urllib.error.HTTPError as exc:
        err_body = ""
        try:
            err_body = exc.read().decode("utf-8", "replace")[:800]
        except Exception:
            err_body = str(exc)
        return {
            "success": False,
            "http_status": exc.code,
            "errors": [{"message": err_body}],
            "creds_source": source,
            "exact_blocker": (
                "CLOUDFLARE_API_TOKEN_UNAUTHORIZED"
                if exc.code in {401, 403}
                else f"CLOUDFLARE_PURGE_HTTP_{exc.code}"
            ),
        }
    result = dict(result or {})
    result["creds_source"] = source
    return result


def main() -> int:
    files = sys.argv[1:] or None
    result = purge(files)
    ok = bool(result.get("success"))
    print(json.dumps({"ok": ok, "result": result}, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
