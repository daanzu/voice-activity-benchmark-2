"""Boundary explorer integrity and UI tests; fixture measurements exist only here."""
import ast
import base64
import copy
import gzip
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zlib

from scripts.build_boundary_explorer_data import (
    NOTEBOOK, SOURCE, build_payload, render, validate_metric,
)

HAS_UI = all(importlib.util.find_spec(p) is not None for p in ("marimo", "plotly"))


def metric_fixture(controller=None):
    controller = controller or {"on": .5, "off": .5, "start_s": 0., "silence_s": .2}
    all_q = {"observations": 3, "denominator": 4,
             "p50": {"reached": True, "seconds": .04},
             "p90": {"reached": False, "seconds": None},
             "p95": {"reached": False, "seconds": None}}
    conditional_q = {"observations": 3, "denominator": 3,
                     "p50": {"reached": True, "seconds": .04},
                     "p90": {"reached": True, "seconds": .1},
                     "p95": {"reached": True, "seconds": .1}}
    boundary = {"all_turn_quantiles": all_q, "conditional_quantiles": conditional_q,
                "deadlines_ms": {"100": {"successes": 3, "total": 4, "fraction": .75},
                                 "200": {"successes": 3, "total": 4, "fraction": .75}}}
    for band, successes in (("possible", 4), ("certain", 2)):
        boundary[f"uncertainty_{band}_deadlines_ms"] = {str(d): {"successes": successes, "total": 4, "fraction": successes/4} for d in (100, 200)}
    return {"controller": controller,
            "counts": {"turns": 4, "episodes": 4, "missed_turns": 1, "no_distinct_start_turns": 1,
                       "early_active_turns": 0, "censored_turns": 0, "premature_end_turns": 1,
                       "fragmented_turns": 1, "extra_fragments": 1, "merged_episodes": 0,
                       "merged_turns": 0, "internal_pause_cuts": 1, "false_starts": 1,
                       "uncertain_starts": 0, "unassigned_episodes": 1},
            "negative_hours": .5, "false_starts_per_negative_hour": 2.,
            "operational_false_positive_s": 180., "operational_false_positive_fraction": .1,
            "source_aligned_false_positive_s": 90., "source_aligned_false_positive_fraction": .05,
            "source_aligned_speech_recall": .99, "operational_speech_recall": .8,
            "onset": copy.deepcopy(boundary), "end": copy.deepcopy(boundary),
            "joint_intact_deadlines": {"100/100": {"successes": 2, "total": 4, "fraction": .5},
                                       "100/200": {"successes": 2, "total": 4, "fraction": .5}}}


def data_fixture():
    dev = metric_fixture()
    test = metric_fixture()
    test["onset"]["all_turn_quantiles"]["p50"]["seconds"] = .06
    test["onset"]["conditional_quantiles"]["p50"]["seconds"] = .06
    data = {"schema_version": 1, "analysis_type": "boundary_latency", "manifest_sha256": "fixture-only",
            "methodology": {"selection_split": "dev"}, "backends": ["ten", "silero"],
            "shared": [], "selections": [], "development_curves": [], "breakdowns": []}
    for name in data["backends"]:
        for config in ("common-200ms", "common-0ms"):
            d, t = copy.deepcopy(dev), copy.deepcopy(test)
            if config == "common-0ms":
                d["controller"]["silence_s"] = t["controller"]["silence_s"] = 0.
            data["shared"].append({"backend": name, "configuration": config, "dev": d, "test": t})
        data["selections"].append({"backend": name, "policy": "policy-from-source", "label": "Fixture display label", "controller": dev["controller"],
                                   "dev": copy.deepcopy(dev), "test": copy.deepcopy(test)})
        data["development_curves"].append({"backend": name, "metric": copy.deepcopy(dev), "pareto": True})
        data["breakdowns"].append({"backend": name, "policy": "policy-from-source", "condition": "fixture condition",
                                   "metric": copy.deepcopy(test)})
    return data


def probe_fixture():
    rows = []
    for backend in ("ten", "silero"):
        for silence in (0, 200):
            for branch in ("stop", "resume"):
                for pause in (50, 200):
                    m = metric_fixture({"on": .5, "off": .5, "start_s": 0., "silence_s": silence/1000})
                    rows.append({"backend": backend, "configuration": f"common-{silence}ms",
                                 "branch": branch, "pause_ms": pause,
                                 "actual_rms_gap_ms": {"min": pause, "max": pause}, "metric": m})
    return {"schema_version": 1, "analysis_type": "controlled_pause_diagnostic",
            "baseline_by_pause": rows, "methodology": {"independent_holdout": False}}


def embedded_payload():
    tree = ast.parse(NOTEBOOK.read_text())
    node = next(n.value for n in ast.walk(tree) if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "_encoded" for t in n.targets))
    return json.loads(zlib.decompress(base64.b64decode(ast.literal_eval(node))))


class BoundarySnapshotTests(unittest.TestCase):
    def source(self, data, directory):
        path = Path(directory)/"summary.json"
        path.write_text(json.dumps(data, allow_nan=False))
        return path

    def test_build_is_lossless_and_source_hash_is_present(self):
        with tempfile.TemporaryDirectory() as temp:
            data = data_fixture()
            payload = build_payload(self.source(data, temp))
            self.assertEqual({k: v for k, v in payload.items() if k != "explorer_source_uncompressed_sha256"}, data)
            self.assertEqual(len(payload["explorer_source_uncompressed_sha256"]["summary.json"]), 64)

    def test_gzip_and_plain_source_have_identical_snapshot_and_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            plain = self.source(data_fixture(), temp)
            compressed = Path(str(plain)+".gz")
            compressed.write_bytes(gzip.compress(plain.read_bytes(), mtime=0))
            expected = build_payload(plain)
            self.assertEqual(build_payload(compressed), expected)
            expected_render = render(plain)
            plain.unlink()
            self.assertEqual(build_payload(plain), expected)
            self.assertEqual(render(plain), expected_render)

    def test_supplement_and_gap_audit_are_separate_hashed_sources(self):
        with tempfile.TemporaryDirectory() as temp:
            data = data_fixture()
            main = self.source(data, temp)
            probe = Path(temp)/"probe.json"
            probe.write_text(json.dumps(probe_fixture()))
            gap = Path(temp)/"gap.json"
            audit = {"manifest_sha256": data["manifest_sha256"], "results": [{"split": "test"}]}
            gap.write_text(json.dumps(audit))
            payload = build_payload(main, probe_source=probe, gap_source=gap)
            for key, value in data.items():
                self.assertEqual(payload[key], value)
            self.assertEqual(payload["pause_probe"], probe_fixture())
            self.assertEqual(payload["primary_gap_audit"], audit)
            self.assertEqual(set(payload["explorer_source_uncompressed_sha256"]), {"summary.json", "probe.json", "gap.json"})
            compressed = Path(str(probe)+".gz")
            compressed.write_bytes(gzip.compress(probe.read_bytes(), mtime=0))
            probe.unlink()
            self.assertEqual(build_payload(main, probe_source=probe, gap_source=gap), payload)

    def test_supplement_cannot_relabel_a_retuned_controller_as_baseline(self):
        with tempfile.TemporaryDirectory() as temp:
            main = self.source(data_fixture(), temp)
            probe = Path(temp)/"probe.json"
            data = probe_fixture()
            data["baseline_by_pause"][0]["metric"]["controller"]["on"] = .25
            probe.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "baseline controller"):
                build_payload(main, probe_source=probe)

    def test_frozen_controller_cannot_change_on_holdout(self):
        data = data_fixture()
        data["selections"][0]["test"]["controller"]["off"] = .1
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "frozen development controller"):
                build_payload(self.source(data, temp))

    def test_incomplete_results_are_rejected(self):
        data = data_fixture()
        data["development_curves"] = []
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "completed"):
                build_payload(self.source(data, temp))

    def test_failure_denominators_and_null_quantiles_are_enforced(self):
        m = metric_fixture()
        validate_metric(m)
        m["end"]["all_turn_quantiles"]["p90"]["seconds"] = 0
        with self.assertRaisesRegex(ValueError, "Unreachable"):
            validate_metric(m)
        m = metric_fixture()
        m["end"]["deadlines_ms"]["100"]["total"] = 3
        with self.assertRaisesRegex(ValueError, "every turn"):
            validate_metric(m)
        m = metric_fixture()
        m["end"]["all_turn_quantiles"]["p90"]["reached"] = True
        with self.assertRaisesRegex(ValueError, "reachability"):
            validate_metric(m)

    def test_false_start_rate_uses_exposure(self):
        m = metric_fixture()
        m["false_starts_per_negative_hour"] = 0
        with self.assertRaisesRegex(ValueError, "known-negative exposure"):
            validate_metric(m)

    def test_exact_render_and_marker_guard(self):
        with tempfile.TemporaryDirectory() as temp:
            path = self.source(data_fixture(), temp)
            text = render(path)
            self.assertIn("BEGIN EMBEDDED BOUNDARY RESULTS", text)
            with patch.object(Path, "read_text", return_value="missing block"):
                with self.assertRaisesRegex(ValueError, "Expected one"):
                    render(path)

    @unittest.skipUnless(SOURCE.exists() or Path(str(SOURCE)+".gz").exists(), "Completed boundary summary not yet present")
    def test_completed_snapshot_is_reproducible_and_exact(self):
        self.assertEqual(NOTEBOOK.read_text(), render())
        self.assertEqual(embedded_payload(), build_payload())

    def test_standalone_has_no_filesystem_or_detector_dependency(self):
        tree = ast.parse(NOTEBOOK.read_text())
        imports = {n.names[0].name for n in ast.walk(tree) if isinstance(n, ast.Import)}
        self.assertEqual(imports, {"marimo", "base64", "json", "zlib", "plotly.graph_objects"})
        self.assertFalse(any(isinstance(n, ast.ImportFrom) for n in ast.walk(tree)))


@unittest.skipUnless(HAS_UI, "Install marimo and plotly for notebook execution tests")
class BoundaryExplorerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from notebooks.explore_boundaries import app
        _, cls.defs = app.run()

    def fig(self, names=None, choice="shared:common-200ms", view="deadlines", **kwargs):
        return self.defs["make_figure"](data_fixture(), ["ten"] if names is None else names, choice, view, **kwargs)

    def test_defaults_and_labels_prioritize_failure_aware_views(self):
        self.assertEqual(self.defs["view"].value, "deadlines")
        text = self.defs["reading_guide"].text
        for phrase in ("First-episode END includes continuity", "Availability is causal acquisition time",
                       "Operational recall", "Conditional latency is diagnostic only", "EOF", "no hysteresis"):
            self.assertIn(phrase, text)
        choices = self.defs["operating_choices"](data_fixture())
        self.assertIn("selection:policy-from-source", choices.values())
        self.assertIn("Frozen development choice · Fixture display label", choices)

    def test_deadlines_use_all_turn_denominators(self):
        fig, warnings, rows = self.fig()
        self.assertEqual(list(fig.data[0].y), [75., 75.])
        self.assertEqual(list(fig.data[0].text), ["3 / 4 turns"]*2)
        self.assertEqual(tuple(fig.layout.yaxis.range), (0, 100))
        self.assertEqual(rows[0]["split"], "test")
        self.assertFalse(warnings)

    def test_unreachable_quantiles_never_become_zero(self):
        fig, warnings, _ = self.fig(view="quantiles")
        self.assertEqual(list(fig.data[0].x), ["p50"])
        self.assertEqual(list(fig.data[0].y), [40.])
        self.assertTrue(any("p95 unreachable" in w for w in warnings))
        rows = self.defs["comparison_rows"](data_fixture(), ["ten"], "shared:common-200ms")
        self.assertEqual(rows[0]["END all-turn p95"], "Unreachable")
        self.assertEqual(rows[0]["END successful observations"], 3)

    def test_conditional_latency_is_labeled_and_separate(self):
        fig, warnings, rows = self.fig(view="conditional")
        self.assertEqual(list(fig.data[0].y), [40., 100., 100.])
        self.assertIn("Diagnostic only", warnings[0])
        self.assertIn("3 successful observations / 3 denominator", fig.data[0].text[0])
        self.assertIn("Diagnostic only", fig.layout.title.text)

    def test_uncertainty_uses_stored_all_turn_bands_and_explicit_labels(self):
        fig, warnings, rows = self.fig(view="uncertainty")
        self.assertEqual(len(fig.data), 3)
        self.assertEqual(list(fig.data[0].y), [75., 75.])
        self.assertEqual(list(fig.data[1].y), [100., 100.])
        self.assertEqual(list(fig.data[2].y), [50., 50.])
        self.assertIn("possible", fig.data[1].name)
        self.assertIn("certain", fig.data[2].name)
        self.assertIn("4 / 4 turns", fig.data[1].text[0])
        self.assertEqual(rows[0]["split"], "test")
        self.assertFalse(warnings)

    def test_joint_intact_success_is_its_own_metric(self):
        fig, _, _ = self.fig(view="joint")
        self.assertEqual(list(fig.data[0].y), [50., 50.])
        self.assertIn("2 / 4 turns", fig.data[0].text[0])

    def test_frontier_uses_development_only_not_test_values(self):
        fig, warnings, rows = self.fig(view="frontier", boundary="onset")
        self.assertEqual(fig.data[0].y[0], 40.)
        self.assertEqual(fig.data[1].y[0], 40.)
        self.assertEqual(fig.data[1].marker.symbol, "star")
        self.assertTrue(all(r["split"] == "dev" for r in rows))
        self.assertIn("Development only", fig.layout.title.text)
        self.assertFalse(warnings)

    def test_frontier_retains_unreachable_source_rows(self):
        fig, warnings, rows = self.fig(view="frontier", q="p95")
        self.assertFalse(fig.data)
        self.assertIsNone(rows[0]["plotted_y_ms"])
        self.assertIn("unreachable", warnings[0])
        self.assertEqual(len(rows), 1)

    def test_condition_unreachable_statuses_and_no_fabricated_shared_breakdowns(self):
        fig, warnings, rows = self.fig(choice="selection:policy-from-source", view="conditions", q="p95")
        self.assertFalse(fig.data)
        self.assertEqual(rows[0]["quantile_status"], "Unreachable")
        self.assertIn("1 of 1 conditions", warnings[0])
        self.assertEqual(rows[0]["metric"]["counts"]["turns"], 4)
        fig, warnings, rows = self.fig(view="conditions")
        self.assertEqual(rows, [])
        self.assertIn("No held-out condition breakdown", warnings[0])

    def test_empty_single_all_repeated_and_stable_colors(self):
        for names in ([], ["ten"], ["ten", "silero"], ["ten"], []):
            for view in ("deadlines", "uncertainty", "quantiles", "conditional", "joint", "frontier", "conditions"):
                fig, _, _ = self.fig(names=names, choice="selection:policy-from-source", view=view)
                self.assertIsNotNone(fig.to_json())
                if not names:
                    self.assertFalse(fig.data)
                    self.assertIn("Choose a detector", fig.layout.annotations[0].text)
        one, _, _ = self.fig(names=["ten"])
        many, _, _ = self.fig(names=["silero", "ten"])
        self.assertEqual(one.data[0].line.color, next(trace.line.color for trace in many.data if trace.name == "ten"))

    def test_error_counts_and_source_operational_recall_are_both_visible(self):
        rows = self.defs["error_rows"](data_fixture(), ["ten"], "shared:common-200ms")
        self.assertEqual(rows[0]["false_starts"], 1)
        self.assertEqual(rows[0]["known-negative hours"], .5)
        self.assertEqual(rows[0]["false starts / negative hour"], 2.)
        self.assertEqual(rows[0]["operational FP seconds"], 180.)
        self.assertEqual(rows[0]["operational FP / negative time (%)"], 10.)
        paired = self.defs["comparison_rows"](data_fixture(), ["ten"], "shared:common-200ms")
        self.assertEqual(paired[0]["source aligned recall (%)"], 99.)
        self.assertEqual(paired[0]["operational recall (%)"], 80.)
        self.assertEqual(paired[0]["ONSET all-turn p50"], "40.0 ms")
        self.assertEqual(paired[1]["ONSET all-turn p50"], "60.0 ms")
        self.assertEqual(paired[0]["Controller"], paired[1]["Controller"])

    def test_pause_probe_filters_without_main_metric_substitution_or_retuning(self):
        data = data_fixture()
        data["pause_probe"] = probe_fixture()
        original = json.dumps(data, sort_keys=True)
        self.assertEqual(self.defs["probe_options"](data), ([50, 200], ["resume", "stop"], ["common-0ms", "common-200ms"]))
        for branch in ("resume", "stop"):
            for pause in (50, 200):
                for baseline in ("common-0ms", "common-200ms"):
                    fig, warnings, rows = self.defs["make_probe_figure"](data, ["ten"], branch, pause, baseline)
                    self.assertEqual(len(rows), 1)
                    self.assertEqual(rows[0]["backend"], "ten")
                    self.assertEqual(rows[0]["branch"], branch)
                    self.assertEqual(rows[0]["pause_ms"], pause)
                    self.assertEqual(rows[0]["configuration"], baseline)
                    self.assertEqual(list(fig.data[0].y), [75., 75.])
                    self.assertIn("diagnostic", rows[0]["split"])
                    self.assertFalse(warnings)
                    table = self.defs["probe_comparison_rows"](rows)
                    self.assertEqual(table[0]["Paired RESUME RMS gap min (ms)"], pause)
                    self.assertEqual(table[0]["END all-turn p95"], "Unreachable")
        self.assertEqual(json.dumps(data, sort_keys=True), original)
        fig, warnings, rows = self.defs["make_probe_figure"](data, ["ten"], "resume", 999, "common-200ms")
        self.assertFalse(fig.data)
        self.assertEqual(rows, [])
        self.assertIn("not substituted", warnings[0])
        fig, _, rows = self.defs["make_probe_figure"](data, [], "resume", 50, "common-200ms")
        self.assertFalse(fig.data)
        self.assertEqual(rows, [])
        self.assertIn("Choose a detector", fig.layout.annotations[0].text)

    def test_all_real_probe_controls_use_recorded_subgroups(self):
        data = self.defs["boundary_results"]
        if not data.get("pause_probe"):
            self.skipTest("Completed pause probe not embedded")
        names = self.defs["backend_names"](data)
        pauses, branches, baselines = self.defs["probe_options"](data)
        self.assertEqual(set(baselines), {"common-0ms", "common-200ms"})
        self.assertEqual(len(data["pause_probe"]["baseline_by_pause"]), len(names)*len(pauses)*len(branches)*len(baselines))
        for branch in branches:
            for pause in pauses:
                for baseline in baselines:
                    figure, warnings, rows = self.defs["make_probe_figure"](data, names, branch, pause, baseline)
                    self.assertEqual(len(rows), len(names))
                    self.assertTrue(figure.data)
                    self.assertFalse(warnings)
                    self.assertTrue(all(r["pause_ms"] == pause and r["branch"] == branch and r["configuration"] == baseline for r in rows))
                    self.assertTrue(all(r["actual_rms_gap_ms"]["min"] == pause == r["actual_rms_gap_ms"]["max"] for r in rows))

    def test_primary_pause_disclosure_uses_measured_gap_audit(self):
        data = self.defs["boundary_results"]
        if not data.get("primary_gap_audit"):
            self.skipTest("Primary gap audit not embedded")
        self.assertEqual(len(self.defs["primary_gap_rows"]), len(data["primary_gap_audit"]["results"]))
        for text in ("402–508", "1152–1258", "frozen test", "classic mode 0", "RMS"):
            self.assertIn(text, self.defs["gap_caveat"])

    def test_all_real_operating_points_and_views_without_retuning(self):
        data = self.defs["boundary_results"]
        if not data.get("selections"):
            self.skipTest("Completed embedded snapshot not present")
        names = self.defs["backend_names"](data)
        before = json.dumps(data, sort_keys=True)
        choices = self.defs["operating_choices"](data)
        for choice in choices.values():
            points = self.defs["selected_points"](data, names, choice)
            self.assertEqual(len(points), len(names))
            for point in points:
                self.assertEqual(point["dev"]["controller"], point["test"]["controller"])
            for boundary in ("onset", "end"):
                figure, _, rows = self.defs["make_figure"](data, names, choice, "deadlines", boundary)
                self.assertTrue(figure.data)
                self.assertEqual(len(rows), len(names))
                self.assertTrue(all(r["split"] == "test" for r in rows))
        choice = next(value for value in choices.values() if value.startswith("selection:"))
        for view in ("uncertainty", "quantiles", "joint", "conditions", "conditional", "frontier"):
            figure, _, rows = self.defs["make_figure"](data, names, choice, view)
            self.assertIsNotNone(figure.to_json())
            self.assertTrue(rows)
            self.assertTrue(all(r["split"] == ("dev" if view == "frontier" else "test") for r in rows))
        self.assertEqual(json.dumps(data, sort_keys=True), before)

    def test_zero_reference_denominator_is_undefined_not_unreachable(self):
        m = metric_fixture()
        for kind in ("all_turn_quantiles", "conditional_quantiles"):
            m["end"][kind] = {"observations": 0, "denominator": 0,
                              **{q: {"reached": False, "seconds": None} for q in ("p50", "p90", "p95")}}
        self.assertEqual(self.defs["quantile_label"](m, "end", "p95"), "Undefined (no reference turns)")
        self.assertEqual(self.defs["quantile_label"](m, "end", "p95", True), "Undefined (no successful observations)")
        self.assertIsNone(self.defs["quantile_value"](m, "end", "p95"))

    def test_presets_and_error_axes(self):
        pick = self.defs["preset_selection"]
        names = ["classic-0", "silero", "silero-lite-0.4.0", "ten", "fsmn"]
        self.assertEqual(pick(names, "None"), [])
        self.assertEqual(pick(names, "All"), names)
        self.assertEqual(len(pick(names, "Small comparison")), 3)
        self.assertEqual(pick(names, "Classic modes"), ["classic-0"])
        self.assertEqual(len(pick(names, "Silero family")), 2)
        m = metric_fixture()
        self.assertEqual(self.defs["error_value"](m, "missed_turns"), 25.)
        self.assertEqual(self.defs["error_value"](m, "operational_false_positive_s"), 180.)
        self.assertEqual(self.defs["error_value"](m, "operational_false_positive_fraction"), 10.)
        self.assertAlmostEqual(self.defs["error_value"](m, "operational_miss"), 20.)


if __name__ == "__main__":
    unittest.main()
