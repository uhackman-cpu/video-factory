import tempfile
import unittest
from pathlib import Path

from engine.hybrid_renderer import srt_time, validate_project, write_srt


def sample_project():
    return {
        "title": "समुद्र की रहस्यमयी दुनिया",
        "format": "short",
        "narration": "समुद्र की गहराइयों में सूर्य का प्रकाश नहीं पहुँचता।",
        "scenes": [{
            "kind": "image",
            "url": "https://cdn.example.org/ocean.jpg",
            "duration": 12,
            "caption": "समुद्र की गहराइयों में अंधकार है",
            "license": "CC BY 4.0",
            "source_page": "https://example.org/ocean",
            "credit": "Example Creator"
        }]
    }


class HybridRendererTests(unittest.TestCase):
    def test_valid_project(self):
        validate_project(sample_project())

    def test_rejects_non_https_assets(self):
        project = sample_project()
        project["scenes"][0]["url"] = "http://cdn.example.org/ocean.jpg"
        with self.assertRaises(ValueError):
            validate_project(project)

    def test_rejects_noncommercial_license(self):
        project = sample_project()
        project["scenes"][0]["license"] = "CC BY-NC 4.0"
        with self.assertRaises(ValueError):
            validate_project(project)

    def test_rejects_short_over_90_seconds(self):
        project = sample_project()
        project["scenes"][0]["duration"] = 91
        with self.assertRaises(ValueError):
            validate_project(project)

    def test_srt_timestamps(self):
        self.assertEqual(srt_time(61.25), "00:01:01,250")

    def test_writes_scene_captions(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "captions.srt"
            write_srt(sample_project()["scenes"], target)
            content = target.read_text(encoding="utf-8")
            self.assertIn("00:00:00,000 --> 00:00:12,000", content)
            self.assertIn("समुद्र की गहराइयों", content)


if __name__ == "__main__":
    unittest.main()
