"""Recall-first display integrity; fixture values below are only test inputs."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.build_explorer_data import build_payload

ROOT = Path(__file__).resolve().parents[1]
HAS_UI = all(importlib.util.find_spec(p) is not None for p in ("marimo", "plotly"))


def sample_metrics(threshold, recall=0.995, fp=10, negative=1000):
    return {
        "threshold": threshold, "speech_frame_recall": recall,
        "missed_speech_fraction": 1 - recall, "false_positive_fraction": fp / negative,
        "tp": round(recall * 1000), "fn": round((1 - recall) * 1000), "fp": fp, "tn": negative - fp,
        "negative_hours": negative * 0.01 / 3600,
        "false_activations_per_negative_hour": 2.0, "event_recall": 0.75,
    }


def fixture():
    dev = sample_metrics(0.00001)
    test = sample_metrics(0.00001, 0.98, fp=40)
    native = sample_metrics(0.5, 0.96, fp=5)
    return {
        "schema_version": 1, "analysis_type": "recall_first",
        "targets": [{"id": "recall_99", "label": "99% speech-frame recall", "recall": 0.99, "reference_backend": None}],
        "selections": [
            {"backend": "silero", "target_id": "recall_99", "target_recall": 0.99,
             "feasible": True, "threshold": 0.00001, "dev": dev, "test": test},
            {"backend": "classic-0", "target_id": "recall_99", "target_recall": 0.99,
             "feasible": False, "threshold": None, "dev": None, "test": None,
             "max_dev_recall": 0.96, "reason": "Native binary recall is below the goal"},
        ],
        "classic_references": [{"backend": "classic-0", "threshold": 0.5, "dev": native, "test": native}],
        "diagnostics": [{"backend": "silero", "threshold": 0, "dev": sample_metrics(0, 1, 1000),
                         "test": sample_metrics(0, 1, 1000)}],
        "curves": {"silero": [sample_metrics(0, 1, 1000), dev, sample_metrics(0.5, 0.9)], "classic-0": [native]},
        "dataset": {"generation": {"frame_s": 0.01}, "streams": 2, "hours": 1,
                    "split_counts": {"dev": 1, "test": 1}},
        "manifest_sha256": "test-fixture-only", "provenance": {"fixture": True},
    }


class RecallArtifactTests(unittest.TestCase):
    def test_real_sources_are_bundled_without_changing_legacy_sets(self):
        payload = build_payload()
        self.assertEqual(list(payload), ["recall-first", "silero-lite-comparison", "synthetic"])
        data = payload["recall-first"]
        summary = json.loads((ROOT / "results/recall-first/summary.json").read_text())
        for key in ("targets", "selections", "classic_references", "diagnostics", "provenance"):
            self.assertEqual(data[key], summary[key])
        self.assertEqual(len(data["curves"]), 12)
        self.assertEqual(len(data["classic_references"]), 4)
        self.assertEqual(sorted(t["recall"] for t in data["targets"] if t["reference_backend"] is None), [0.99, 0.995, 0.999])
        self.assertEqual({t["reference_backend"] for t in data["targets"] if t["reference_backend"]},
                         {f"classic-{i}" for i in range(4)})
        for point in data["diagnostics"]:
            self.assertEqual(point["threshold"], 0)
        for item in data["selections"]:
            if item["feasible"]:
                self.assertGreater(item["threshold"], 0)
                self.assertEqual(item["threshold"], item["dev"]["threshold"])
                self.assertEqual(item["threshold"], item["test"]["threshold"])
                self.assertGreaterEqual(item["dev"]["speech_frame_recall"] + 1e-12, item["target_recall"])
            else:
                for key in ("threshold", "dev", "test"):
                    self.assertIsNone(item[key])
        self.assertEqual(len(payload["silero-lite-comparison"]["results"]), 9)
        self.assertEqual(len(payload["synthetic"]["results"]), 7)

    def bundle_fixture(self, data):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "results" / "fixture"
            destination.mkdir(parents=True)
            (destination / "summary.json").write_text(json.dumps(data))
            (destination / "development-curves.json").write_text(json.dumps(data["curves"]))
            with patch("scripts.build_explorer_data.ROOT", root):
                return build_payload(["fixture"])

    def test_builder_rejects_zero_operational_choice(self):
        data = fixture()
        data["selections"][0]["threshold"] = 0
        with self.assertRaisesRegex(ValueError, "exclude threshold zero"):
            self.bundle_fixture(data)

    def test_builder_rejects_holdout_retuning(self):
        data = fixture()
        data["selections"][0]["test"]["threshold"] = 0.2
        with self.assertRaisesRegex(ValueError, "frozen development"):
            self.bundle_fixture(data)

    def test_builder_rejects_fabricated_infeasible_result(self):
        data = fixture()
        data["selections"][1]["test"] = sample_metrics(0)
        with self.assertRaisesRegex(ValueError, "Infeasible"):
            self.bundle_fixture(data)


@unittest.skipUnless(HAS_UI, "Install marimo and plotly for notebook execution tests")
class RecallPlotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from notebooks.explore_results import app
        _, cls.defs = app.run()

    def setUp(self):
        self.data = fixture()

    def figure(self, kind="recall_holdout", names=None, metric="false_positive_fraction", **kwargs):
        return self.defs["make_recall_figure"](self.data, names if names is not None else ["silero", "classic-0"],
                                                kind, metric, "recall_99", **kwargs)

    def test_holdout_uses_actual_recall_and_reports_unattainable(self):
        fig, warnings, rows = self.figure()
        self.assertEqual(len(fig.data), 1)
        self.assertEqual(fig.data[0].y[0], 98)
        self.assertEqual(fig.data[0].x[0], 4)
        self.assertTrue(any("Threshold stays frozen" in w for w in warnings))
        self.assertTrue(any("unattainable" in w and "96.00000%" in w for w in warnings))
        self.assertEqual(rows[0]["threshold"], 0.00001)
        self.assertFalse(rows[1]["feasible"])

    def test_positive_log_sweep_keeps_exact_cutoff_and_excludes_zero(self):
        fig, _, rows = self.figure("recall_threshold", metric="speech_frame_recall")
        self.assertEqual(fig.layout.xaxis.type, "log")
        self.assertTrue(all(row["threshold"] > 0 for row in rows))
        self.assertEqual(list(fig.data[1].x), [0.00001])
        self.assertEqual(fig.data[2].mode, "markers")
        self.assertIn(0.00001, list(fig.data[0].x))

    def test_duration_and_event_rate_are_distinct(self):
        seconds, _, _ = self.figure(names=["silero"], metric="fp_seconds")
        minutes, _, _ = self.figure(names=["silero"], metric="fp_minutes_per_negative_hour")
        events, _, _ = self.figure(names=["silero"], metric="false_activations_per_negative_hour")
        self.assertAlmostEqual(seconds.data[0].x[0], 0.4)
        self.assertAlmostEqual(minutes.data[0].x[0], 2.4)
        self.assertEqual(events.data[0].x[0], 2)

    def test_comparison_table_keeps_dev_test_and_failure_separate(self):
        rows = self.defs["recall_selection_rows"](self.data, ["silero", "classic-0"], "recall_99")
        self.assertEqual(rows[0]["Dev frame recall (%)"], 99.5)
        self.assertEqual(rows[0]["Holdout frame recall (%)"], 98)
        self.assertFalse(rows[0]["Holdout meets dev target?"])
        self.assertAlmostEqual(rows[0]["Holdout FP seconds"], 0.4)
        self.assertIsNone(rows[1]["Frozen threshold"])
        self.assertIsNone(rows[1]["Holdout frame recall (%)"])
        self.assertEqual(rows[1]["Max attainable dev frame recall (%)"], 96)

    def test_diagnostic_is_separate_and_classic_reference_is_native(self):
        diagnostic, _, rows = self.figure("recall_diagnostic", ["silero"])
        self.assertIn("Diagnostic only", diagnostic.layout.title.text)
        self.assertEqual(list(diagnostic.data[0].x), [100])
        self.assertEqual(rows[0]["threshold"], 0)
        reference, _, rows = self.figure("recall_classic_refs", ["classic-0"])
        self.assertEqual(list(reference.data[0].y), [96])
        self.assertEqual(rows[0]["threshold"], 0.5)
        diagnostic_rows = self.defs["recall_selection_rows"](self.data, ["silero"], "recall_99", "recall_diagnostic")
        self.assertIn("excluded from selection", diagnostic_rows[0]["Status"])
        self.assertIsNone(diagnostic_rows[0]["Holdout meets dev target?"])

    def test_all_views_empty_single_repeated_and_full_axes(self):
        for names in ([], ["silero"], list(self.data["curves"])):
            for kind in ("recall_holdout", "recall_dev_tradeoff", "recall_threshold", "recall_dev_choices",
                         "recall_classic_refs", "recall_diagnostic"):
                fig, _, _ = self.figure(kind, names, full_axes=True, points=True)
                self.assertIsNotNone(fig.to_json())
                if not names:
                    self.assertFalse(fig.data)
        fig, _, _ = self.figure(full_axes=True)
        self.assertEqual(tuple(fig.layout.xaxis.range), (0, 100))
        self.assertEqual(tuple(fig.layout.yaxis.range), (0, 100))

    def test_matched_classic_can_be_included_without_resetting_subset(self):
        data = fixture()
        data["targets"][0]["reference_backend"] = "classic-0"
        names = ["silero"]
        pick = self.defs["recall_names"]
        self.assertEqual(pick(data, names, "recall_99", True), ["silero", "classic-0"])
        self.assertEqual(pick(data, names, "recall_99", False), ["silero"])
        self.assertEqual(pick(data, [], "recall_99", True), [])
        self.assertEqual(pick(data, ["classic-0"], "recall_99", True), ["classic-0"])
        self.assertEqual(names, ["silero"])

    def test_positive_cutoff_can_be_feasible_but_already_all_positive(self):
        self.data["selections"][0]["dev"] = sample_metrics(0.00001, 1.0, 1000)
        fig, warnings, _ = self.figure(names=["silero"])
        self.assertEqual(len(fig.data), 1)
        self.assertTrue(any("positive cutoff already produces all-positive" in warning for warning in warnings))
        rows = self.defs["recall_selection_rows"](self.data, ["silero"], "recall_99")
        self.assertIn("Feasible", rows[0]["Status"])
        self.assertIn("all-positive", rows[0]["Status"])
        self.assertEqual(rows[0]["Dev FP duration (%)"], 100)

    def test_selection_changes_do_not_retune_or_mutate_source(self):
        before = copy.deepcopy(self.data)
        self.figure()
        self.figure("recall_dev_tradeoff", ["classic-0"])
        self.figure("recall_diagnostic", ["silero"])
        self.assertEqual(self.data, before)

    def test_all_real_targets_and_views_render_without_retuning(self):
        data = self.defs["result_sets"]["recall-first"]
        names = list(data["curves"])
        before = copy.deepcopy(data["selections"])
        for target in data["targets"]:
            for kind in ("recall_holdout", "recall_dev_tradeoff", "recall_threshold", "recall_dev_choices",
                         "recall_classic_refs", "recall_diagnostic"):
                metric = "speech_frame_recall" if kind == "recall_threshold" else "false_positive_fraction"
                fig, _, rows = self.defs["make_recall_figure"](data, names, kind, metric, target["id"], include_reference=True)
                self.assertTrue(fig.data)
                self.assertIsNotNone(fig.to_json())
                if kind in {"recall_dev_tradeoff", "recall_threshold"}:
                    self.assertTrue(all(row["threshold"] > 0 for row in rows))
            table = self.defs["recall_selection_rows"](data, names, target["id"])
            self.assertEqual(len(table), 12)
        self.assertEqual(data["selections"], before)

    def test_reading_guide_explains_frame_event_and_diagnostic(self):
        guide = self.defs["reading_guide"].text
        for explanation in ("speech-frame recall goals", "Event recall is different", "order statistics",
                            "holdout recall can miss", "always-positive diagnostic", "FP seconds"):
            self.assertIn(explanation, guide)


if __name__ == "__main__":
    unittest.main()
