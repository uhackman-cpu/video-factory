import json
import unittest
from pathlib import Path

from PIL import Image

from engine.story_animation import (
    draw_story_frame,
    storyboard_narration,
    validate_storyboard,
    write_storyboard_srt,
    retime_storyboard_for_voice,
)


class StoryAnimationTests(unittest.TestCase):
    def setUp(self):
        self.project = {
            "title": "Milo and the Star",
            "language": "en",
            "fps": 24,
            "characters": {
                "milo": {"shape": "box", "color": "#f28a62", "accent": "#fff0c9"}
            },
            "scenes": [{
                "duration": 2,
                "background": "meadow",
                "camera": "push_in",
                "caption": "A star is missing.",
                "narration": "Milo finds a missing star.",
                "characters": [{
                    "id": "milo", "start_x": 0.2, "end_x": 0.7,
                    "y": 0.76, "action": "walk", "emotion": "curious"
                }],
                "props": [{"type": "star", "x": 0.75, "y": 0.55}],
                "kinetic_text": [{"text": "LOOK UP!", "x": 0.5, "y": 0.25, "motion": "pop"}]
            }]
        }

    def test_valid_storyboard_returns_total_duration(self):
        project = validate_storyboard(self.project)
        self.assertEqual(project["duration"], 2.0)
        self.assertEqual(project["fps"], 24)

    def test_scene_timing_expands_to_fit_longer_voice(self):
        adjusted = retime_storyboard_for_voice(self.project, 4.5)
        self.assertAlmostEqual(adjusted["duration"], 4.5, places=2)
        self.assertGreater(adjusted["scenes"][0]["duration"], 2)

    def test_narration_uses_scene_order(self):
        self.assertEqual(
            storyboard_narration(self.project),
            "Milo finds a missing star."
        )

    def test_scene_frame_has_vertical_canvas(self):
        project = validate_storyboard(self.project)
        frame = draw_story_frame(project, 0, 12)
        self.assertIsInstance(frame, Image.Image)
        self.assertEqual(frame.size, (720, 1280))

    def test_unknown_character_is_rejected(self):
        broken = json.loads(json.dumps(self.project))
        broken["scenes"][0]["characters"][0]["id"] = "missing"
        with self.assertRaises(ValueError):
            validate_storyboard(broken)

    def test_unsupported_action_is_rejected(self):
        broken = json.loads(json.dumps(self.project))
        broken["scenes"][0]["characters"][0]["action"] = "teleport"
        with self.assertRaises(ValueError):
            validate_storyboard(broken)

    def test_unknown_kinetic_text_motion_is_rejected(self):
        broken = json.loads(json.dumps(self.project))
        broken["scenes"][0]["kinetic_text"] = [
            {"text": "Hello", "motion": "spin_forever"}
        ]
        with self.assertRaises(ValueError):
            validate_storyboard(broken)

    def test_srt_uses_scene_timing(self):
        project = validate_storyboard(self.project)
        path = Path("test-story.srt")
        try:
            write_storyboard_srt(project, path)
            text = path.read_text(encoding="utf-8")
            self.assertIn("00:00:00,000 --> 00:00:02,000", text)
            self.assertIn("A star is missing.", text)
        finally:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
