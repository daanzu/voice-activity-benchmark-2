"""Notebook data integrity plus optional UI-graph tests (no detector inference)."""
import ast
import base64
import importlib.util
import json
from pathlib import Path
import unittest
import zlib

from scripts.build_explorer_data import build_payload, render

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "notebooks/explore_results.py"
HAS_UI = all(importlib.util.find_spec(p) is not None for p in ("marimo", "plotly"))


def embedded_payload():
    tree = ast.parse(NOTEBOOK.read_text())
    value = next(n.value for n in ast.walk(tree) if isinstance(n, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == "_encoded" for t in n.targets))
    return json.loads(zlib.decompress(base64.b64decode(ast.literal_eval(value))))


class ExplorerSnapshotTests(unittest.TestCase):
    def test_snapshot_is_reproducible_and_exact(self):
        self.assertEqual(NOTEBOOK.read_text(), render())
        self.assertEqual(embedded_payload(), build_payload())

    def test_missing_embedded_marker_is_an_error(self):
        from unittest.mock import patch
        with patch.object(Path, "read_text", return_value="no embedded block"):
            with self.assertRaisesRegex(ValueError, "Expected one"):
                render()

    def test_splits_and_counts(self):
        data = embedded_payload()["silero-lite-comparison"]
        self.assertEqual(len(data["results"]), 9)
        self.assertEqual(len(data["curves"]), 12)
        self.assertEqual(data["dataset"]["split_counts"], {"dev": 96, "test": 144})
        for name, curve in data["curves"].items():
            self.assertEqual(len(curve), 133)
            chosen = data["dev_choices"][name]
            point = next(p for p in curve if p["threshold"] == chosen["threshold"])
            self.assertEqual(point["missed_speech_fraction"], chosen["missed_speech_fraction"])
            self.assertLessEqual(point["false_positive_fraction"], 0.01)
            self.assertLessEqual(point["false_activations_per_negative_hour"], 5)
        for row in data["results"]:
            self.assertEqual(row["dev"]["threshold"], row["test"]["threshold"])
        self.assertEqual(data["curves"]["silero"], data["curves"]["silero-lite-0.4.0"])

    def test_notebook_is_standalone(self):
        tree = ast.parse(NOTEBOOK.read_text())
        imports = {n.names[0].name for n in ast.walk(tree) if isinstance(n, ast.Import)}
        self.assertEqual(imports, {"marimo", "base64", "json", "zlib", "plotly.graph_objects"})
        self.assertFalse(any(isinstance(n, ast.ImportFrom) for n in ast.walk(tree)))


@unittest.skipUnless(HAS_UI, "Install marimo and plotly for notebook execution tests")
class ExplorerPlotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from notebooks.explore_results import app
        _, cls.defs = app.run()
        cls.data = cls.defs["result_sets"]["silero-lite-comparison"]

    def figure(self, names, kind="dev_roc", metric="missed_speech_fraction", **kw):
        return self.defs["make_figure"](self.data, names, kind, metric, **kw)

    def test_default_is_small_and_colors_stable(self):
        self.assertEqual(len(self.defs["detectors"].value), 3)
        one, _, _ = self.figure(["ten"])
        many, _, _ = self.figure(["silero", "ten"])
        self.assertEqual(one.data[0].line.color, many.data[2].line.color)
        self.assertEqual(len(one.data[0].x), 133)

    def test_empty_single_all_and_repeated_views(self):
        for names in ([], ["silero"], list(self.data["curves"])):
            for kind in ("dev_roc", "dev_events", "dev_threshold", "holdout_metric",
                         "holdout_tradeoff", "reference_metric", "performance", "speed_accuracy"):
                metric = "wall_rtf" if kind == "performance" else "missed_speech_fraction"
                fig, _, _ = self.figure(names, kind, metric)
                self.assertIsNotNone(fig.to_json())
                if not names:
                    self.assertFalse(fig.data)
                    self.assertIn("Choose a detector", fig.layout.annotations[0].text)

    def test_binary_modes_are_not_interpolated(self):
        fig, _, _ = self.figure(["classic-0", "classic-2"])
        self.assertEqual(fig.data[0].mode, "markers")
        self.assertEqual(fig.data[2].mode, "markers")
        self.assertEqual(len(set(zip(fig.data[0].x, fig.data[0].y))), 2)

    def test_holdout_and_reference_are_distinct(self):
        fig, warnings, rows = self.figure(["classic-2"], "holdout_metric")
        self.assertFalse(fig.data)
        self.assertIn("classic-2", warnings[0])
        self.assertFalse(rows)
        ref, warnings, rows = self.figure(["classic-2"], "reference_metric")
        expected = self.data["references"]["classic-2"]["missed_speech_fraction"] * 100
        self.assertEqual(ref.data[0].x[0], expected)
        self.assertFalse(warnings)
        self.assertNotIn("wall_rtf", rows[0])

    def test_missing_latency_and_negative_delay_preserved(self):
        fig, warnings, rows = self.figure(["classic-0"], "holdout_metric", "end_notification_p95_s")
        self.assertFalse(fig.data)
        self.assertIn("unavailable (not zero)", warnings[0])
        self.assertIsNone(rows[0]["end_notification_p95_s"])
        # Exercise the signed-delay path independently of this snapshot's p95 signs.
        import copy
        data = copy.deepcopy(self.data)
        data["results"][0]["test"]["end_notification_p95_s"] = -0.25
        fig, _, _ = self.defs["make_figure"](data, ["agc2"], "holdout_metric", "end_notification_p95_s")
        self.assertEqual(fig.data[0].x[0], -250)

    def test_performance_does_not_claim_holdout_or_threshold(self):
        fig, _, rows = self.figure(["silero"], "performance", "wall_rtf")
        self.assertEqual(rows[0]["runtime_split"], "all streams")
        self.assertNotIn("threshold", rows[0])
        self.assertNotIn("Threshold:", fig.data[0].hovertemplate)
        self.assertNotIn("missed_speech_fraction", rows[0])

    def test_percentage_bounds_and_source_values(self):
        fig, _, rows = self.figure(["ten"], full_axes=True)
        self.assertEqual(tuple(fig.layout.xaxis.range), (0, 100))
        self.assertEqual(tuple(fig.layout.yaxis.range), (0, 100))
        self.assertEqual(fig.data[0].x[0], rows[0]["false_positive_fraction"] * 100)
        self.assertEqual(fig.data[0].y[0], 100 * (1 - rows[0]["missed_speech_fraction"]))
        for row in rows:
            self.assertEqual(row["split"], "development")

    def test_presets_and_result_switch(self):
        names = list(self.data["curves"])
        pick = self.defs["preset_selection"]
        self.assertEqual(pick(names, "None"), [])
        self.assertEqual(pick(names, "All"), names)
        self.assertEqual(len(pick(names, "Silero family")), 3)
        old = self.defs["result_sets"]["synthetic"]
        self.assertEqual(pick(list(old["curves"]), "Small comparison"), ["silero", "ten", "fsmn"])


if __name__ == "__main__":
    unittest.main()
