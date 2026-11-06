import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from render import prepare_inputs, render, validate_capture, SHOWTIME_COMMIT


class RenderInputsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        self.root = self.base / "upstream"
        (self.root / "scripts").mkdir(parents=True)
        (self.root / "profiles").mkdir()
        for name in ("compose_pilot.py", "showtime_doctor.py", "render_quality.py"):
            (self.root / "scripts" / name).write_text("")
        self.profile = {"path_base": "config", "device": {"source": "../assets/phone.png", "manifest": "../assets/phones.json"}, "background": {"source": "../assets/source.json"}, "tap": {"sequence": "../assets/tap_%05d.png"}}
        (self.root / "profiles/telegram-product.json").write_text(json.dumps(self.profile))
        self.capture = self.base / "capture.mp4"
        self.capture.write_bytes(b"original")
        self.events = self.base / "events.json"
        self.events.write_text("[]")
        self.output = self.base / "result.mp4"

    def prepare(self):
        return prepare_inputs(self.root, self.capture, self.events, self.output, "full")

    def test_moved_profile_keeps_absolute_asset_paths(self):
        with patch("render.subprocess.check_output", side_effect=[SHOWTIME_COMMIT + "\n", ""]):
            *_, profile = self.prepare()
        self.assertEqual(profile["device"]["source"], str(self.root / "assets/phone.png"))
        self.assertEqual(profile["tap"]["sequence"], str(self.root / "assets/tap_%05d.png"))
        self.assertEqual(profile["layout"], "full")
        self.assertFalse(self.output.with_suffix(".showtime").exists())

    def test_refuses_existing_output_or_source_as_output(self):
        for output in (self.output, self.capture):
            output.write_bytes(b"keep")
            with self.subTest(output=output), self.assertRaisesRegex(ValueError, "already exist"):
                prepare_inputs(self.root, self.capture, self.events, output, "full")
            self.assertEqual(output.read_bytes(), b"keep")

    def test_wrong_commit_or_dirty_checkout_never_runs_scripts(self):
        for replies in (["wrong\n"], [SHOWTIME_COMMIT + "\n", " M scripts/media_io.py\n"]):
            with self.subTest(replies=replies), patch("render.subprocess.check_output", side_effect=replies), patch("render.subprocess.run") as run:
                with self.assertRaises(ValueError):
                    render(self.root, self.capture, self.events, self.output)
                run.assert_not_called()
                self.assertFalse(self.output.with_suffix(".showtime").exists())

    def test_missing_capture_or_invalid_events_creates_nothing(self):
        self.capture.unlink()
        with self.assertRaisesRegex(ValueError, "Input file"):
            self.prepare()
        self.capture.write_bytes(b"original")
        self.events.write_text('{"events": "not a list"}')
        with patch("render.subprocess.check_output", side_effect=[SHOWTIME_COMMIT, ""]), self.assertRaisesRegex(ValueError, "Events"):
            self.prepare()
        self.assertFalse(self.output.with_suffix(".showtime").exists())

    def test_capture_must_fit_without_silently_cropping_old_promo(self):
        profile = {"device": {"source_size": [1350, 2760], "screen_insets": [70, 73, 70, 73]}}
        metadata = {"streams": [{"codec_type": "video", "width": 402, "height": 874, "duration": "12"}]}
        validate_capture(metadata, profile)
        metadata["streams"][0].update(width=1080, height=1350)
        with self.assertRaisesRegex(ValueError, "aspect ratio"):
            validate_capture(metadata, profile)
        metadata["streams"][0].update(width=402, height=874, duration="9")
        with self.assertRaisesRegex(ValueError, "at least 10 seconds"):
            validate_capture(metadata, profile)


if __name__ == "__main__":
    unittest.main()
