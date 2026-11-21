"""Check exact-base pinning, repeatability and preservation of local edits."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location(
    "prepare", Path(__file__).resolve().parents[1] / "scripts/prepare.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PrepareTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.upstream = self.root / "upstream"
        self.upstream.mkdir()
        self.git("init", "-q", "-b", "main")
        (self.upstream / "file.txt").write_text("before\n")
        self.git("add", "file.txt")
        self.git("-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                 "commit", "-qm", "base")
        self.base = self.git("rev-parse", "HEAD").decode().strip()
        (self.upstream / "file.txt").write_text("after\n")
        (self.upstream / "new.txt").write_text("new file\n")
        self.git("add", "-N", "new.txt")
        patch = self.git("diff", "--binary", "HEAD")
        self.git("reset", "--hard", "-q", "HEAD")
        (self.upstream / "new.txt").unlink(missing_ok=True)
        self.package = self.root / "package"
        self.package.mkdir()
        (self.package / "feature.patch").write_bytes(patch)
        self.config = {"repository": str(self.upstream), "ref": "main", "commit": self.base,
                       "patch": "feature.patch", "sha256": hashlib.sha256(patch).hexdigest()}
        self.save_config()
        self.source = self.root / "build"

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.upstream), *args], stderr=subprocess.PIPE)

    def save_config(self):
        (self.package / "source.json").write_text(json.dumps(self.config))

    def test_applies_pinned_patch_and_can_be_repeated(self):
        MODULE.prepare(self.source, self.package)
        self.assertEqual((self.source / "file.txt").read_text(), "after\n")
        self.assertEqual((self.source / "new.txt").read_text(), "new file\n")
        MODULE.prepare(self.source, self.package)
        self.assertEqual(MODULE.git(self.source, "rev-parse", "HEAD").decode().strip(), self.base)

    def test_preserves_edits_after_preparation(self):
        MODULE.prepare(self.source, self.package)
        (self.source / "file.txt").write_text("user edit\n")
        with self.assertRaisesRegex(ValueError, "other changes"):
            MODULE.prepare(self.source, self.package)
        self.assertEqual((self.source / "file.txt").read_text(), "user edit\n")

    def test_preserves_untracked_files(self):
        MODULE.prepare(self.source, self.package)
        (self.source / "notes.txt").write_text("keep me\n")
        with self.assertRaisesRegex(ValueError, "other changes"):
            MODULE.prepare(self.source, self.package)
        self.assertEqual((self.source / "notes.txt").read_text(), "keep me\n")

    def test_rejects_wrong_base_without_applying_patch(self):
        self.config["commit"] = "0" * 40
        self.save_config()
        with self.assertRaisesRegex(ValueError, "pinned upstream commit"):
            MODULE.prepare(self.source, self.package)
        self.assertEqual((self.source / "file.txt").read_text(), "before\n")

    def test_rejects_tampered_patch_before_cloning(self):
        (self.package / "feature.patch").write_text("changed")
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            MODULE.prepare(self.source, self.package)
        self.assertFalse(self.source.exists())


if __name__ == "__main__":
    unittest.main()
