"""Bundle completed boundary-latency JSON into a standalone notebook; no inference."""
import argparse
import base64
import hashlib
import gzip
import json
import math
from pathlib import Path
import re
import zlib

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "results/boundary-latency/summary.json"
NOTEBOOK = ROOT / "notebooks/explore_boundaries.py"
GAP_SOURCE = ROOT / "results/boundary-latency/pause-gap-audit.json"
PROBE_SOURCE = ROOT / "results/boundary-pause-probe/summary.json"


def validate_metric(metric):
    """Reject missing denominators, fabricated quantiles, or inconsistent rates."""
    turns = metric["counts"]["turns"]
    if not isinstance(turns, int) or turns < 0:
        raise ValueError("Invalid turn denominator")
    for name in ("onset", "end"):
        boundary = metric[name]
        for kind in ("all_turn_quantiles", "conditional_quantiles"):
            q = boundary[kind]
            if q["observations"] > q["denominator"] or q["observations"] < 0:
                raise ValueError("Invalid quantile observations")
            if kind == "all_turn_quantiles" and q["denominator"] != turns:
                raise ValueError("All-turn quantiles must retain every turn")
            if kind == "conditional_quantiles" and q["denominator"] != q["observations"]:
                raise ValueError("Conditional quantiles must use successful observations")
            for key, fraction in (("p50", .5), ("p90", .9), ("p95", .95)):
                point = q[key]
                expected = q["denominator"] > 0 and math.ceil(fraction*q["denominator"]) <= q["observations"]
                if point["reached"] != expected:
                    raise ValueError("Quantile reachability disagrees with denominator")
                if point["reached"]:
                    if point["seconds"] is None or not math.isfinite(point["seconds"]):
                        raise ValueError("Reached quantiles require finite seconds")
                elif point["seconds"] is not None:
                    raise ValueError("Unreachable quantiles must be null, not zero")
        for deadline in boundary["deadlines_ms"].values():
            _validate_deadline(deadline, turns)
    for deadline in metric["joint_intact_deadlines"].values():
        _validate_deadline(deadline, turns)
    negative_hours = metric["negative_hours"]
    if negative_hours < 0 or not math.isfinite(negative_hours):
        raise ValueError("Invalid negative-time exposure")
    rate = metric["false_starts_per_negative_hour"]
    expected = metric["counts"]["false_starts"]/negative_hours if negative_hours else None
    if rate != expected and (rate is None or expected is None or not math.isclose(rate, expected, rel_tol=1e-9)):
        raise ValueError("False-start rate must use known-negative exposure")


def _validate_deadline(deadline, turns):
    if deadline["total"] != turns or not 0 <= deadline["successes"] <= turns:
        raise ValueError("Deadline success must retain every turn")
    expected = deadline["successes"]/turns if turns else None
    if deadline["fraction"] != expected:
        raise ValueError("Deadline fraction disagrees with counts")


def read_source(source):
    source = Path(source)
    actual = source if source.exists() else Path(str(source)+".gz")
    raw = actual.read_bytes()
    if actual.suffix == ".gz":
        raw = gzip.decompress(raw)
    canonical = Path(str(actual)[:-3]) if actual.suffix == ".gz" else actual
    try:
        name = str(canonical.resolve().relative_to(ROOT))
    except ValueError:
        name = canonical.name
    return json.loads(raw), {name: hashlib.sha256(raw).hexdigest()}, canonical


def build_payload(source=SOURCE, probe_source=None, gap_source=None):
    data, hashes, canonical_source = read_source(source)
    if data.get("schema_version") != 1 or data.get("analysis_type") != "boundary_latency":
        raise ValueError("Unsupported boundary-latency schema")
    if any(not data.get(key) for key in ("shared", "selections", "development_curves", "backends", "manifest_sha256")):
        raise ValueError("Only completed, nonempty boundary results can be embedded")
    for item in data["shared"] + data["selections"]:
        for split in ("dev", "test"):
            if not isinstance(item.get(split), dict):
                raise ValueError("Only completed development and test metrics can be embedded")
            validate_metric(item[split])
        expected = item.get("controller", item["dev"]["controller"])
        if any(item[split]["controller"] != expected for split in ("dev", "test")):
            raise ValueError("Holdout controller must equal frozen development controller")
    for item in data["development_curves"] + data.get("breakdowns", []):
        validate_metric(item["metric"])
    default_source = canonical_source.resolve() == SOURCE.resolve()
    extra_sources = [("primary_gap_audit", gap_source or (GAP_SOURCE if default_source else None)),
                     ("pause_probe", probe_source or (PROBE_SOURCE if default_source else None))]
    for key, extra_source in extra_sources:
        if extra_source is None:
            continue
        extra_source = Path(extra_source)
        if not extra_source.exists() and not Path(str(extra_source)+".gz").exists():
            if key == "primary_gap_audit" or probe_source is not None:
                raise FileNotFoundError(extra_source)
            continue  # The supplemental view stays explicitly unavailable until completed.
        extra, extra_hashes, _ = read_source(extra_source)
        if key == "primary_gap_audit":
            if extra.get("manifest_sha256") != data["manifest_sha256"] or not extra.get("results"):
                raise ValueError("Pause-gap audit must match the primary dataset manifest")
        else:
            if not extra.get("baseline_by_pause"):
                raise ValueError("Only a completed nonempty pause probe can be embedded")
            for row in extra["baseline_by_pause"]:
                validate_metric(row["metric"])
                if row["configuration"] not in ("common-0ms", "common-200ms"):
                    raise ValueError("Pause-specific plots require stored shared baselines")
                expected = {"on": .5, "off": .5, "start_s": 0.,
                            "silence_s": .2 if row["configuration"] == "common-200ms" else 0.}
                if row["metric"]["controller"] != expected:
                    raise ValueError("Probe baseline controller does not match its label")
                bounds = row["actual_rms_gap_ms"]
                if not 0 <= bounds["min"] <= bounds["max"]:
                    raise ValueError("Invalid actual RMS gap range")
        data[key] = extra
        hashes.update(extra_hashes)
    return {**data, "explorer_source_uncompressed_sha256": hashes}


def render(source=SOURCE, notebook=NOTEBOOK, probe_source=None, gap_source=None):
    payload = build_payload(source, probe_source=probe_source, gap_source=gap_source)
    raw = json.dumps(payload, separators=(",", ":"), allow_nan=False).encode()
    encoded = base64.b64encode(zlib.compress(raw, level=9)).decode()
    lines = "\n".join(f'        "{encoded[i:i+100]}"' for i in range(0, len(encoded), 100))
    block = f"# BEGIN EMBEDDED BOUNDARY RESULTS\n    _encoded = (\n{lines}\n    )\n    # END EMBEDDED BOUNDARY RESULTS"
    text, count = re.subn(r"# BEGIN EMBEDDED BOUNDARY RESULTS.*?# END EMBEDDED BOUNDARY RESULTS",
                          lambda _: block, Path(notebook).read_text(), flags=re.DOTALL)
    if count != 1:
        raise ValueError(f"Expected one embedded boundary results block, found {count}")
    return text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    generated = render(args.source)
    if args.check:
        if generated != NOTEBOOK.read_text():
            raise SystemExit("Boundary snapshot is stale; run python scripts/build_boundary_explorer_data.py")
        print("Boundary snapshot matches completed source results")
    else:
        NOTEBOOK.write_text(generated)
        print(f"Wrote {NOTEBOOK.relative_to(ROOT)} ({len(generated):,} bytes)")


if __name__ == "__main__":
    main()
