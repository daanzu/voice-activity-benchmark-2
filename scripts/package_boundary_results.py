#!/usr/bin/env python3
"""Losslessly package the three bulk boundary JSON artifacts for source control.

The original analysis bytes and all decompressed source hashes are unchanged.
Original .json files remain on disk for recovery. A clean checkout needs only
the .json.gz files and packaged-results.json to check their integrity.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results" / "boundary-latency"
NAMES = ("summary.json", "development-curves.json", "per-turn-test.json")
MANIFEST = "packaged-results.json"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compress(raw: bytes) -> bytes:
    """No timestamp or filename is recorded in the reproducible gzip header."""
    output = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", compresslevel=9, mtime=0,
                       fileobj=output) as stream:
        stream.write(raw)
    packed = output.getvalue()
    if gzip.decompress(packed) != raw:
        raise ValueError("Lossless gzip round trip failed")
    return packed


def package(results: Path) -> dict:
    entries = {}
    prepared = {}
    for name in NAMES:
        raw = (results / name).read_bytes()
        json.loads(raw)
        packed = compress(raw)
        prepared[name + ".gz"] = packed
        entries[name] = {
            "path": name + ".gz",
            "uncompressed_bytes": len(raw),
            "uncompressed_sha256": sha256(raw),
            "compressed_bytes": len(packed),
            "compressed_sha256": sha256(packed),
        }
    manifest = {"schema_version": 1, "format": "gzip", "mtime": 0,
                "description": "Lossless original analysis bytes; no JSON reserialization",
                "artifacts": entries}
    for name, data in prepared.items():
        destination = results / name
        temporary = destination.with_name(destination.name + ".tmp")
        temporary.write_bytes(data)
        temporary.replace(destination)
    (results / MANIFEST).write_text(json.dumps(manifest, indent=2) + "\n")
    check(results)
    return manifest


def check(results: Path) -> dict:
    manifest = json.loads((results / MANIFEST).read_bytes())
    if (manifest.get("schema_version"), manifest.get("format"), manifest.get("mtime")) != (1, "gzip", 0):
        raise ValueError("Unsupported packaging manifest")
    if set(manifest.get("artifacts", {})) != set(NAMES):
        raise ValueError("Packaging manifest must contain exactly the three bulk artifacts")
    for name in NAMES:
        entry = manifest["artifacts"][name]
        if entry["path"] != name + ".gz":
            raise ValueError(f"Unexpected compressed path for {name}")
        packed = (results / entry["path"]).read_bytes()
        if (len(packed), sha256(packed)) != (entry["compressed_bytes"], entry["compressed_sha256"]):
            raise ValueError(f"Compressed checksum/size mismatch: {name}")
        if packed[:4] != b"\x1f\x8b\x08\x00" or packed[4:8] != b"\x00\x00\x00\x00":
            raise ValueError(f"Noncanonical timestamp/filename gzip header: {name}")
        raw = gzip.decompress(packed)
        if (len(raw), sha256(raw)) != (entry["uncompressed_bytes"], entry["uncompressed_sha256"]):
            raise ValueError(f"Uncompressed checksum/size mismatch: {name}")
        json.loads(raw)
        original = results / name
        if original.exists() and original.read_bytes() != raw:
            raise ValueError(f"Compressed artifact is stale: {name}; rerun packaging")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=RESULTS)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    manifest = check(args.results) if args.check else package(args.results)
    for name, entry in manifest["artifacts"].items():
        print(f"{name}: {entry['uncompressed_bytes']:,} original bytes -> "
              f"{entry['compressed_bytes']:,} gzip bytes; "
              f"SHA-256 {entry['uncompressed_sha256']}")
    print("All three gzip artifacts preserve the exact original JSON bytes")


if __name__ == "__main__":
    main()
