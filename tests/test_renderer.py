import unittest
from engine.render_video import make_scenes, split_sentences


class RendererTests(unittest.TestCase):
    def test_hindi_sentence_split(self):
        self.assertEqual(
            split_sentences("भारत महान है। संविधान सर्वोच्च है।"),
            ["भारत महान है।", "संविधान सर्वोच्च है।"],
        )

    def test_english_sentence_split(self):
        self.assertEqual(
            split_sentences("Learn history. Practice daily!"),
            ["Learn history.", "Practice daily!"],
        )

    def test_scene_limit(self):
        scenes = make_scenes(" ".join(f"Fact {i}." for i in range(20)), 7)
        self.assertLessEqual(len(scenes), 7)
        self.assertEqual(len(scenes), 7)

    def test_empty_text_fallback(self):
        self.assertEqual(split_sentences(""), ["Welcome"])


if __name__ == "__main__":
    unittest.main()
