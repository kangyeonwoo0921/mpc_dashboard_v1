import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from scripts.sync_web_assets import main, sync


class WebAssetSyncTests(unittest.TestCase):
    def test_sync_creates_destination_and_overwrites_deterministically(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "dist" / "greenhouse.glb"
            target = root / "static" / "models" / "greenhouse.glb"
            source.parent.mkdir()
            source.write_bytes(b"glTF" + b"phase17")
            self.assertTrue(sync(source, target))
            self.assertEqual(target.read_bytes(), source.read_bytes())
            target.write_bytes(b"glTFstale")
            self.assertTrue(sync(source, target))
            self.assertEqual(target.read_bytes(), source.read_bytes())
            self.assertTrue(sync(source, target, check_only=True))

    def test_missing_source_fails_clearly_and_command_prints_both_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "dist" / "greenhouse.glb"
            target = root / "static" / "greenhouse.glb"
            output = io.StringIO()
            errors = io.StringIO()
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                status = main(["--source", str(source), "--target", str(target)])
            self.assertEqual(status, 1)
            self.assertIn("GLB not found", errors.getvalue())
            source.parent.mkdir()
            source.write_bytes(b"glTF" + b"asset")
            with contextlib.redirect_stdout(output):
                status = main(["--source", str(source), "--target", str(target)])
            self.assertEqual(status, 0)
            text = output.getvalue()
            self.assertIn(f"source: {source.resolve()}", text)
            self.assertIn(f"target: {target.resolve()}", text)


if __name__ == "__main__":
    unittest.main()
