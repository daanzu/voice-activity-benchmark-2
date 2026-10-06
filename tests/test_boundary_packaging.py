"""Lossless packaging checks also work without the original bulk JSON files."""
import gzip
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SPEC = importlib.util.spec_from_file_location(
    "package_boundary_results", Path(__file__).resolve().parents[1] / "scripts" / "package_boundary_results.py")
package_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(package_module)


class BoundaryPackagingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.originals = {}
        for index, name in enumerate(package_module.NAMES):
            raw = ('{\n  "example": ' + str(index) + ',\n  "unicode": "caf\u00e9"\n}\n').encode()
            (self.root / name).write_bytes(raw)
            self.originals[name] = raw

    def test_preserves_exact_source_bytes_and_hashes(self):
        manifest = package_module.package(self.root)
        for name, raw in self.originals.items():
            self.assertEqual(gzip.decompress((self.root / (name + ".gz")).read_bytes()), raw)
            self.assertEqual((self.root / name).read_bytes(), raw)
            self.assertEqual(manifest["artifacts"][name]["uncompressed_sha256"], package_module.sha256(raw))

    def test_repeated_packaging_is_byte_identical(self):
        first = package_module.package(self.root)
        packed = {name: (self.root / (name + ".gz")).read_bytes() for name in package_module.NAMES}
        self.assertEqual(first, package_module.package(self.root))
        for name, raw in packed.items():
            self.assertEqual((self.root / (name + ".gz")).read_bytes(), raw)

    def test_clean_checkout_without_originals(self):
        expected = package_module.package(self.root)
        for name in package_module.NAMES:
            (self.root / name).unlink()
        self.assertEqual(package_module.check(self.root), expected)

    def test_stale_original_rejected(self):
        package_module.package(self.root)
        (self.root / package_module.NAMES[0]).write_bytes(b'{}\n')
        with self.assertRaisesRegex(ValueError, "stale"):
            package_module.check(self.root)

    def test_corrupt_compressed_bytes_rejected(self):
        package_module.package(self.root)
        path = self.root / (package_module.NAMES[0] + ".gz")
        path.write_bytes(path.read_bytes() + b'x')
        with self.assertRaisesRegex(ValueError, "Compressed checksum"):
            package_module.check(self.root)

    def test_uncompressed_hash_mismatch_rejected(self):
        manifest = package_module.package(self.root)
        manifest["artifacts"][package_module.NAMES[0]]["uncompressed_sha256"] = "0" * 64
        (self.root / package_module.MANIFEST).write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "Uncompressed checksum"):
            package_module.check(self.root)

    def test_extra_path_rejected(self):
        manifest = package_module.package(self.root)
        manifest["artifacts"]["other.json"] = {}
        (self.root / package_module.MANIFEST).write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "exactly the three"):
            package_module.check(self.root)


if __name__ == "__main__":
    unittest.main()
