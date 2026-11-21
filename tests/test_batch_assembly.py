"""Tests for ratatoss.batch_assembly."""

from hashlib import sha256
import os
from pathlib import Path
import shutil
import tempfile
import unittest

from ratatoss.batch_assembly import assemble_batches, BatchAssemblyError
from ratatoss.manifest import build_manifest, verify_file, Manifest


class TestBatchAssembly(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="ratatoss-test-assembly-"))
        self.store_dir = self.test_dir / "store"
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir = self.test_dir / "temp"
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _create_batches_from_source(self, data: bytes, piece_size: int, batch_size: int):
        src_file = self.test_dir / "source.bin"
        src_file.write_bytes(data)
        manifest = build_manifest(src_file, piece_size=piece_size, batch_size=batch_size)

        batch_map = {}
        for b in manifest.batches:
            b_path = self.store_dir / f"batch_{b.index}.bin"
            b_path.write_bytes(data[b.offset : b.offset + b.size])
            batch_map[b.index] = b_path

        return manifest, batch_map

    def test_assemble_regular_file(self):
        # 100 bytes, piece=16, batch=32 -> 4 batches (32, 32, 32, 4)
        data = b"0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ!@#$%^&*()_+-=[]{}|;':,./<>?~`123456"
        manifest, batch_map = self._create_batches_from_source(data, piece_size=16, batch_size=32)

        temp_output = assemble_batches(manifest, batch_map, self.temp_dir)
        self.assertTrue(temp_output.is_file())
        self.assertEqual(temp_output.parent.resolve(), self.temp_dir.resolve())
        self.assertEqual(temp_output.read_bytes(), data)
        self.assertTrue(verify_file(temp_output, manifest))

    def test_assemble_empty_file(self):
        data = b""
        manifest, batch_map = self._create_batches_from_source(data, piece_size=16, batch_size=32)
        self.assertEqual(len(manifest.batches), 0)

        temp_output = assemble_batches(manifest, batch_map, self.temp_dir)
        self.assertTrue(temp_output.is_file())
        self.assertEqual(temp_output.stat().st_size, 0)
        self.assertEqual(temp_output.read_bytes(), b"")
        self.assertTrue(verify_file(temp_output, manifest))

    def test_assemble_short_last_batch(self):
        # 45 bytes, piece=10, batch=20 -> batches: 20, 20, 5 (short last batch)
        data = os.urandom(45)
        manifest, batch_map = self._create_batches_from_source(data, piece_size=10, batch_size=20)
        self.assertEqual(len(manifest.batches), 3)
        self.assertEqual(manifest.batches[-1].size, 5)

        temp_output = assemble_batches(manifest, batch_map, self.temp_dir)
        self.assertTrue(temp_output.is_file())
        self.assertEqual(temp_output.read_bytes(), data)
        self.assertTrue(verify_file(temp_output, manifest))

    def test_assemble_input_mapping_reversed_order(self):
        # Pass dictionary with keys in reversed order: {2: ..., 1: ..., 0: ...}
        data = os.urandom(70)
        manifest, batch_map = self._create_batches_from_source(data, piece_size=10, batch_size=20)
        reversed_batch_map = {idx: batch_map[idx] for idx in sorted(batch_map.keys(), reverse=True)}

        temp_output = assemble_batches(manifest, reversed_batch_map, self.temp_dir)
        self.assertTrue(temp_output.is_file())
        self.assertEqual(temp_output.read_bytes(), data)
        self.assertTrue(verify_file(temp_output, manifest))

    def test_missing_batch_raises_error_and_cleans_temp(self):
        data = os.urandom(50)
        manifest, batch_map = self._create_batches_from_source(data, piece_size=10, batch_size=20)
        del batch_map[1]  # Missing batch index 1

        existing_file = self.temp_dir / "keep_me.txt"
        existing_file.write_text("important")

        with self.assertRaises(BatchAssemblyError) as ctx:
            assemble_batches(manifest, batch_map, self.temp_dir)

        self.assertIn("Missing batch at index 1", str(ctx.exception))
        # Ensure temp file was cleaned up and existing files remain untouched
        remaining_files = list(self.temp_dir.iterdir())
        self.assertEqual(remaining_files, [existing_file])
        self.assertEqual(existing_file.read_text(), "important")

    def test_batch_wrong_size_raises_and_cleans_temp(self):
        data = os.urandom(50)
        manifest, batch_map = self._create_batches_from_source(data, piece_size=10, batch_size=20)
        # Truncate batch 0
        batch_0 = batch_map[0]
        batch_0.write_bytes(b"short")

        with self.assertRaises(BatchAssemblyError) as ctx:
            assemble_batches(manifest, batch_map, self.temp_dir)

        self.assertIn("Batch size mismatch at index 0", str(ctx.exception))
        # Check no leftover temp files
        temp_files = [f for f in self.temp_dir.iterdir() if f.name.endswith(".tmp")]
        self.assertEqual(temp_files, [])

    def test_batch_corrupted_content_raises_and_cleans_temp(self):
        data = b"A" * 60
        manifest, batch_map = self._create_batches_from_source(data, piece_size=10, batch_size=20)
        # Corrupt batch 1 bytes without changing length
        batch_1 = batch_map[1]
        corrupted_bytes = b"B" * batch_1.stat().st_size
        batch_1.write_bytes(corrupted_bytes)

        existing_file = self.temp_dir / "keep_me.txt"
        existing_file.write_text("existing data")

        neighbor_batch = batch_map[0].read_bytes()

        with self.assertRaises(BatchAssemblyError) as ctx:
            assemble_batches(manifest, batch_map, self.temp_dir)

        self.assertIn("Batch SHA-256 digest mismatch at index 1", str(ctx.exception))
        # Temp cleaned up
        temp_files = [f for f in self.temp_dir.iterdir() if f.name.endswith(".tmp")]
        self.assertEqual(temp_files, [])
        # Neighboring batch untouched
        self.assertEqual(batch_map[0].read_bytes(), neighbor_batch)
        # Existing file untouched
        self.assertEqual(existing_file.read_text(), "existing data")

    def test_invalid_temp_dir(self):
        data = b"123"
        manifest, batch_map = self._create_batches_from_source(data, piece_size=10, batch_size=20)
        non_existent_dir = self.test_dir / "non_existent_subdir"

        with self.assertRaises(BatchAssemblyError):
            assemble_batches(manifest, batch_map, non_existent_dir)

    def test_small_buffer_stream_assembly(self):
        # Test custom small read_size buffer (e.g. 7 bytes) to exercise buffer boundary loops
        data = os.urandom(128)
        manifest, batch_map = self._create_batches_from_source(data, piece_size=16, batch_size=32)

        temp_output = assemble_batches(manifest, batch_map, self.temp_dir, read_size=7)
        self.assertTrue(temp_output.is_file())
        self.assertEqual(temp_output.read_bytes(), data)
        self.assertTrue(verify_file(temp_output, manifest))


if __name__ == "__main__":
    unittest.main()
