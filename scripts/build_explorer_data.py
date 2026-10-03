"""Bundle committed JSON into the standalone explorer; never runs a benchmark."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import zlib

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "notebooks/explore_results.py"
DEFAULTS = ["silero-lite-comparison", "synthetic"]
LABELS = {
    "silero-lite-comparison": "Published Silero Lite comparison · 9 report candidates",
    "synthetic": "Original synthetic evaluation · 7 report candidates",
}


def build_payload(names=DEFAULTS):
    payload = {}
    for name in names:
        directory = ROOT / "results" / name
        source = {p: (directory / p).read_bytes() for p in ("summary.json", "development-curves.json")}
        summary = json.loads(source["summary.json"])
        if summary["schema_version"] not in (1, 2) or summary["calibration"]["split"] != "dev":
            raise ValueError(f"Unsupported schema or calibration split: {name}")
        payload[name] = {
            "label": LABELS.get(name, name),
            "report_url": f"https://github.com/daanzu/voice-activity-benchmark-2/blob/main/results/{name}/REPORT.md",
            "source_sha256": {f"results/{name}/{p}": hashlib.sha256(b).hexdigest() for p, b in source.items()},
            "manifest_sha256": summary["manifest_sha256"],
            "dataset": summary["dataset"],
            "calibration": summary["calibration"],
            "environment": summary["results"][0]["environment"],
            "curves": json.loads(source["development-curves.json"]),
            "dev_choices": summary["all_development_choices"],
            "references": summary["reference_points"],
            "results": [{k: r[k] for k in ("backend", "dev", "test", "performance")} for r in summary["results"]],
        }
    return payload


def encoded_payload(names=DEFAULTS):
    raw = json.dumps(build_payload(names), separators=(",", ":"), allow_nan=False).encode()
    return base64.b64encode(zlib.compress(raw, level=9)).decode()


def render(names=DEFAULTS):
    encoded = encoded_payload(names)
    lines = "\n".join(f'        "{encoded[i:i+100]}"' for i in range(0, len(encoded), 100))
    block = f"# BEGIN EMBEDDED RESULTS\n    _encoded = (\n{lines}\n    )\n    # END EMBEDDED RESULTS"
    rendered, count = re.subn(r"# BEGIN EMBEDDED RESULTS.*?# END EMBEDDED RESULTS", lambda _: block,
                              NOTEBOOK.read_text(), flags=re.DOTALL)
    if count != 1:
        raise ValueError(f"Expected one embedded results block, found {count}")
    return rendered


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail if the embedded snapshot is stale")
    parser.add_argument("--result-set", action="append", dest="names", help="Result directory name; repeat to bundle multiple sets")
    args = parser.parse_args()
    generated = render(args.names or DEFAULTS)
    if args.check:
        if generated != NOTEBOOK.read_text():
            raise SystemExit("Explorer snapshot is stale; run python scripts/build_explorer_data.py")
        print("Explorer snapshot matches committed source results")
    else:
        NOTEBOOK.write_text(generated)
        print(f"Wrote {NOTEBOOK.relative_to(ROOT)} ({len(generated):,} bytes)")


if __name__ == "__main__":
    main()
