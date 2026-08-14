"""Unit tests for cross-platform final-submission verification helpers."""

from __future__ import annotations

import tempfile
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from verify_final_submission import check_file_hash, is_lfs_pointer, sha256_bytes


class VerificationHelperTests(unittest.TestCase):
    def test_detects_lfs_pointer_before_hashing(self) -> None:
        pointer = (
            "version https://git-lfs.github.com/spec/v1\n"
            "oid sha256:" + "a" * 64 + "\nsize 100\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.pth"
            path.write_text(pointer, encoding="utf-8")
            self.assertTrue(is_lfs_pointer(path))
            message = check_file_hash(path, "b" * 64)
            self.assertIn("git lfs pull", message or "")

    def test_hash_mismatch_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.json"
            path.write_text('{"文本": "中文"}\n', encoding="utf-8")
            message = check_file_hash(path, "0" * 64)
            self.assertIn("SHA-256 mismatch", message or "")

    def test_utf8_bytes_hash_is_stable(self) -> None:
        data = "中文证据".encode("utf-8")
        self.assertEqual(sha256_bytes(data), sha256_bytes(data))


if __name__ == "__main__":
    unittest.main()
