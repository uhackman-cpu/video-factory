import unittest

from engine.render_video import (
    TEMPLATES,
    license_is_commercially_usable,
    make_scenes,
    split_sentences,
    srt_timestamp,
)


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

    def test_scene_limit_and_content_preservation(self):
        source = " ".join(f"Fact {i}." for i in range(20))
        scenes = make_scenes(source, 7)
        self.assertEqual(len(scenes), 7)
        self.assertEqual(" ".join(scenes).count("Fact"), 20)

    def test_empty_text_fallback(self):
        self.assertEqual(split_sentences(""), ["Welcome"])

    def test_invalid_scene_limit(self):
        with self.assertRaises(ValueError):
            make_scenes("A sentence.", 0)

    def test_supported_templates(self):
        self.assertEqual(
            set(TEMPLATES),
            {"educational", "cinematic", "news", "facts", "quote"},
        )

    def test_commons_license_filter(self):
        self.assertTrue(license_is_commercially_usable("CC BY-SA 4.0"))
        self.assertTrue(license_is_commercially_usable("CC0"))
        self.assertTrue(license_is_commercially_usable("Public domain"))
        self.assertFalse(license_is_commercially_usable("CC BY-NC 4.0"))
        self.assertFalse(license_is_commercially_usable("CC BY-ND 4.0"))

    def test_srt_timestamp(self):
        self.assertEqual(srt_timestamp(61.25), "00:01:01,250")


if __name__ == "__main__":
    unittest.main()
