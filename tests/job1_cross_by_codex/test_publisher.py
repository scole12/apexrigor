"""Issue 23 behavior checks; no production access, fixed clock."""

import ast
import json
import os
import re
import shutil
import subprocess
import tempfile
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock


class FixedDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls.fromtimestamp(1792530000, tz)


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "bin/apex_shared_site_publisher.py"


def functions(*names, **bindings):
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    nodes = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names
    ]
    scope = {
        "Path": Path,
        "Any": object,
        "Request": object,
        "tempfile": tempfile,
        "shutil": shutil,
        "PurePosixPath": __import__("pathlib").PurePosixPath,
        **bindings,
    }
    exec(  # noqa: S102 - execute only AST-selected functions from the local repo
        compile(
            ast.fix_missing_locations(
                ast.Module(
                    body=[
                        ast.ImportFrom(
                            module="__future__",
                            names=[ast.alias(name="annotations")],
                            level=0,
                        ),
                        *nodes,
                    ],
                    type_ignores=[],
                )
            ),
            str(SOURCE),
            "exec",
        ),
        scope,
    )
    return types.SimpleNamespace(**scope)


class PublisherRegression(unittest.TestCase):
    def test_ncaaf_t3_never_rewrites_other_sports_or_runs_their_generators(self):
        commands = []
        tools = lambda root, name, *args: commands.append(name) or ""
        p = functions(
            "build_request",
            copy_queued_payload=Mock(),
            ncaaf_delivery_manifest=Mock(),
            python_tool=tools,
            dirty_paths=lambda root: set(),
            allowed_site_change=lambda name: True,
        )
        request = types.SimpleNamespace(sport="NCAAF", product="T3", manifest={})
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            p.build_request(request, Path(directory))
        self.assertFalse(
            set(commands)
            & {
                "apply_shared_sport_selector.py",
                "apply_cloudflare_web_analytics.py",
                "apply_vercel_web_analytics.py",
                "build_vercel_output.py",
            },
            commands,
        )

    def test_global_generator_fault_does_not_trip_request_breaker(self):
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request = types.SimpleNamespace(sport="NCAAF", request_id="fixture")
            folder = root / "failures/ncaaf/fixture"
            folder.mkdir(parents=True)
            (folder / "one.json").write_text(
                json.dumps(
                    {
                        "error": "RuntimeError:shared publisher produced unowned paths: [nba/index.html]"
                    }
                )
            )
            os.utime(folder / "one.json", (1792530000, 1792530000))
            p = functions(
                "failure_counts",
                "_is_wait_error",
                "_is_request_failure",
                STATE_ROOT=root,
                time=types.SimpleNamespace(time=lambda: 1792530000),
                load_json=lambda path: json.loads(path.read_text()),
                WAIT_ERROR_MARKERS=("PENDING",),
            )
            self.assertEqual(p.failure_counts(request)[0], 0)

    def test_analytics_route_inventory_includes_nba(self):
        import sys

        sys.path.insert(0, str(ROOT / "bin"))
        import apply_cloudflare_web_analytics as cf
        import apply_vercel_web_analytics as va

        for tool in (cf, va):
            routes = {
                path.relative_to(ROOT).as_posix() for path in tool.active_outputs(ROOT)
            }
            for route in (
                "nba/index.html",
                "nba/results/index.html",
                "nba/about/index.html",
            ):
                self.assertIn(route, routes)

    def test_published_request_keeps_its_commit_on_retry(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request = types.SimpleNamespace(
                sport="NCAAF", request_id="a" * 64, product="T2", manifest={}
            )
            intent = root / "publication_intents/ncaaf" / (request.request_id + ".json")
            intent.parent.mkdir(parents=True)
            intent.write_text(
                json.dumps(
                    {
                        "request_id": request.request_id,
                        "published_commit": "b" * 40,
                        "status": "PUBLISHED",
                    }
                )
            )
            git = Mock(
                side_effect=AssertionError(
                    "a published request must not rebuild or chase a newer commit"
                )
            )
            p = functions(
                "publish",
                STATE_ROOT=root,
                load_json=lambda path: json.loads(path.read_text()),
                git=git,
            )
            self.assertEqual(
                p.publish(request, dry_run=False)["published_commit"], "b" * 40
            )
            git.assert_not_called()

    def test_ready_descendant_deployment_is_accepted(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            def git(*args):
                return subprocess.run(
                    ["git", *args],
                    cwd=root,
                    check=True,
                    capture_output=True,
                    text=True,
                    env={
                        **os.environ,
                        "GIT_AUTHOR_DATE": "2026-10-20T12:00:00Z",
                        "GIT_COMMITTER_DATE": "2026-10-20T12:00:00Z",
                    },
                ).stdout.strip()

            git("init")
            git("config", "user.name", "Fixture")
            git("config", "user.email", "fixture@example.invalid")
            git("commit", "--allow-empty", "-m", "request")
            request = git("rev-parse", "HEAD")
            git("commit", "--allow-empty", "-m", "other sport")
            deployed = git("rev-parse", "HEAD")
            deployment = {
                "readyState": "READY",
                "target": "production",
                "alias": ["apexrigor.com"],
                "meta": {"githubCommitSha": deployed},
            }
            p = functions(
                "ncaaf_deployment_serves",
                ROOT=root,
                re=re,
                subprocess=subprocess,
                vercel_deployment=lambda: deployment,
            )
            self.assertTrue(p.ncaaf_deployment_serves(request)[0])

    def test_reissued_request_supersedes_only_proven_unsent_delivery(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            old = "b" * 64
            request = types.SimpleNamespace(
                sport="NCAAF",
                request_id="a" * 64,
                product="T2",
                slate_date="2026-10-20",
                manifest={
                    "requested_at_utc": "2026-10-20T12:00:00Z",
                    "supersedes_request_id": old,
                },
            )
            history = {
                "total_count": 1,
                "workflow_runs": [
                    {"id": 1, "display_title": "NCAA T2 2026-10-20 " + old}
                ],
            }
            receipt = root / "receipts/ncaaf" / (old + ".json")
            receipt.parent.mkdir(parents=True)
            evidence = {
                "sport": "NCAAF",
                "product": "T2",
                "slate_date": "2026-10-20",
                "email_dispatch": "REJECTED_BEFORE_ACCEPTANCE",
                "email_external_action_count": 0,
            }
            receipt.write_text(json.dumps(evidence))
            p = functions(
                "matching_ncaaf_workflow_runs",
                "safe_relative",
                STATE_ROOT=root,
                ROOT=root,
                datetime=datetime,
                timedelta=timedelta,
                timezone=timezone,
                json=json,
                run=lambda *args, **kwargs: json.dumps(history),
                load_json=lambda path: json.loads(path.read_text()),
            )
            self.assertEqual(p.matching_ncaaf_workflow_runs(request), [])
            evidence["email_external_action_count"] = 1
            receipt.write_text(json.dumps(evidence))
            with self.assertRaisesRegex(RuntimeError, "RECONCILIATION_REQUIRED"):
                p.matching_ncaaf_workflow_runs(request)

    def test_deployment_delay_has_bound_and_alert(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            clock = 1792530000000
            receipt = root / "receipt.json"
            receipt.write_text(
                json.dumps({"site_wait_started_utc_ms": clock - 31 * 60000})
            )
            request = types.SimpleNamespace(
                sport="NCAAF", product="T2", request_id="a" * 64
            )
            alert = Mock()
            p = functions(
                "ncaaf_t2_site_live_before_email",
                receipt_path=lambda request: receipt,
                load_json=lambda path: json.loads(path.read_text()),
                ncaaf_first_kickoff_ms=lambda request: clock + 2 * 3600000,
                ncaaf_deployment_serves=lambda commit: (False, {}),
                owner_notice=alert,
                time=types.SimpleNamespace(time=lambda: 1000),
                NCAAF_LIVE_POLL_SECONDS=0,
                datetime=FixedDatetime,
                timezone=timezone,
            )
            result = p.ncaaf_t2_site_live_before_email(
                request, {"published_commit": "b" * 40}, now_ms=clock
            )
            self.assertEqual(
                result["site_live_check"]["status"],
                "EMAIL_RELEASED_AFTER_BOUNDED_SITE_WAIT",
            )
            alert.assert_called_once()


if __name__ == "__main__":
    unittest.main()
