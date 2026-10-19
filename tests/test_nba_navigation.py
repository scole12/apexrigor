"""Prove the shared navigation insertion preserves every existing link."""
import ast
from pathlib import Path
import re
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


def functions(source):
    tree = ast.parse(source)
    tree.body = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in ('anchor', 'unavailable', 'navigation')]
    namespace = {}
    exec(compile(tree, '<navigation>', 'exec'), namespace)
    return namespace['navigation']


class Navigation(unittest.TestCase):
    def test_only_nba_anchor_added(self):
        base = subprocess.check_output(['git','show','b4cf214769cadafa4d186f6c3756d45493c6ea0d:bin/apply_shared_sport_selector.py'], cwd=ROOT, text=True)
        old = functions(base)
        new = functions((ROOT / 'bin/apply_shared_sport_selector.py').read_text())
        for sport in ('mlb','ncaaf','mma','nfl','nhl'):
            for section in ('picks','results','about'):
                before = old(sport, section, True, True)
                after = new(sport, section, True, True, True)
                self.assertEqual(len(re.findall(r'>NBA</a>', after)), 1)
                self.assertEqual(re.sub(r'\n    <a href="/nba[^"]*">NBA</a>', '', after), before)


if __name__ == '__main__':
    unittest.main()
