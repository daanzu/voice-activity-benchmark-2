"""Validate retained measurements without importing or executing a VAD backend."""
import ast
import json
from pathlib import Path
import statistics
import unittest

ROOT = Path(__file__).resolve().parents[1]

class RecordedResults(unittest.TestCase):
    def test_scripts_parse(self):
        for name in ('bench.py', 'bench16.py', 'verify_models.py'):
            ast.parse((ROOT / name).read_text())

    def test_measurements(self):
        for stem in ('bench', 'bench16'):
            directory = ROOT / 'results' / '2026-10-02'
            rows = json.loads((directory / f'{stem}-results.json').read_text())
            lines = (directory / f'{stem}-output.txt').read_text().splitlines()
            logged = [json.loads(line) for line in lines if line.startswith('{')]
            self.assertEqual(rows, logged[:15])
            self.assertEqual(len(rows), 15)
            self.assertEqual(len({(r['input'], r['backend']) for r in rows}), 15)
            for row in rows:
                self.assertEqual(len(row['runs']), 5)
                self.assertTrue(all(t > 0 for t in row['runs']))
                self.assertAlmostEqual(row['wall_s_median'], statistics.median(row['runs']))
                self.assertAlmostEqual(row['rtf'], row['wall_s_median'] / 60)
            self.assertEqual(logged[15]['no_context_vs_no_context_max_abs'], 0.0)
            self.assertGreater(logged[15]['no_context_vs_context_max_abs'], 0.0)

if __name__ == '__main__':
    unittest.main()
