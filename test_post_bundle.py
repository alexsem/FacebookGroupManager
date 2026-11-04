"""Unit tests for PostBundle and PostBundleLoader."""

import tempfile
import unittest
from pathlib import Path

from post_bundle import PostBundleLoader, PostBundle


class TestPostBundleLoader(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.bundle_path = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_directory_not_found(self) -> None:
        non_existent = self.bundle_path / "does_not_exist"
        loader = PostBundleLoader(non_existent)
        with self.assertRaises(FileNotFoundError):
            loader.load()

    def test_missing_txt_file(self) -> None:
        loader = PostBundleLoader(self.bundle_path)
        with self.assertRaises(FileNotFoundError):
            loader.load()

    def test_empty_txt_file(self) -> None:
        txt_path = self.bundle_path / "post_content.txt"
        txt_path.write_text("   \n  ", encoding="utf-8")
        loader = PostBundleLoader(self.bundle_path)
        with self.assertRaises(ValueError):
            loader.load()

    def test_load_text_only(self) -> None:
        txt_path = self.bundle_path / "post_content.txt"
        txt_path.write_text("Mensaje de prueba", encoding="utf-8")

        loader = PostBundleLoader(self.bundle_path)
        bundle = loader.load()

        self.assertEqual(bundle.text, "Mensaje de prueba")
        self.assertEqual(bundle.media_count, 0)
        self.assertFalse(bundle.has_media)

    def test_load_with_multiple_images_and_videos(self) -> None:
        txt_path = self.bundle_path / "post_content.txt"
        txt_path.write_text("Mensaje con multimedia", encoding="utf-8")

        # Create dummy media files
        (self.bundle_path / "image1.jpg").write_bytes(b"dummy image 1")
        (self.bundle_path / "image2.png").write_bytes(b"dummy image 2")
        (self.bundle_path / "video1.mp4").write_bytes(b"dummy video 1")
        (self.bundle_path / "ignored.pdf").write_bytes(b"dummy pdf")

        loader = PostBundleLoader(self.bundle_path)
        bundle = loader.load()

        self.assertEqual(bundle.text, "Mensaje con multimedia")
        self.assertEqual(bundle.media_count, 3)
        self.assertTrue(bundle.has_media)

        media_names = [p.name for p in bundle.media_paths]
        self.assertIn("image1.jpg", media_names)
        self.assertIn("image2.png", media_names)
        self.assertIn("video1.mp4", media_names)
        self.assertNotIn("ignored.pdf", media_names)


if __name__ == "__main__":
    unittest.main()

