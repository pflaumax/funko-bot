"""Tests for the image handler module."""

from src.image_handler import ImageHandler


class TestImageHandler:
    """Test cases for ImageHandler class."""

    def test_handler_initialization(self, tmp_path):
        """Test image handler initializes correctly."""
        handler = ImageHandler(tmp_path)
        assert handler.images_dir == tmp_path
        assert handler.images_dir.exists()

    def test_generate_alt_text(self, tmp_path):
        """Test alt text generation."""
        handler = ImageHandler(tmp_path)

        product = {"name": "Spider-Man", "fandom": "Marvel", "price": 15.99}

        alt_text = handler.generate_alt_text(product)
        assert "Spider-Man" in alt_text
        assert "Marvel" in alt_text
        assert "15.99" in alt_text

    def test_generate_alt_text_no_fandom(self, tmp_path):
        """Test alt text generation without fandom."""
        handler = ImageHandler(tmp_path)

        product = {"name": "Generic Pop", "fandom": "Other", "price": 12.99}

        alt_text = handler.generate_alt_text(product)
        assert "Generic Pop" in alt_text
        assert "12.99" in alt_text


class TestImagePreparation:
    """Every image must leave as a real JPEG, whatever came in."""

    def _png(self, tmp_path, size=(800, 800), mode="RGBA"):
        from PIL import Image

        path = tmp_path / "in.jpg"  # .jpg name, PNG bytes — the live case
        Image.new(mode, size, (200, 30, 30, 255)[: 4 if mode == "RGBA" else 3]).save(
            path, "PNG"
        )
        return path

    def test_small_png_is_still_re_encoded(self, tmp_path):
        """The bug: 800x800 sat under the resize threshold and passed through."""
        from PIL import Image

        handler = ImageHandler(tmp_path)
        path = self._png(tmp_path)
        assert Image.open(path).format == "PNG"

        handler.resize_image(str(path))
        assert Image.open(path).format == "JPEG"

    def test_transparency_is_flattened_onto_white(self, tmp_path):
        from PIL import Image

        handler = ImageHandler(tmp_path)
        path = tmp_path / "t.jpg"
        Image.new("RGBA", (64, 64), (0, 0, 0, 0)).save(path, "PNG")

        handler.resize_image(str(path))
        out = Image.open(path)
        assert out.mode == "RGB"
        assert out.getpixel((0, 0)) == (255, 255, 255)

    def test_oversized_image_is_scaled_down(self, tmp_path):
        from PIL import Image

        handler = ImageHandler(tmp_path)
        path = tmp_path / "big.jpg"
        Image.new("RGB", (3000, 1500), (10, 20, 30)).save(path, "PNG")

        handler.resize_image(str(path))
        assert max(Image.open(path).size) <= 1200

    def test_output_fits_the_upload_budget(self, tmp_path):
        import random

        from PIL import Image

        from src.image_handler import MAX_UPLOAD_BYTES

        handler = ImageHandler(tmp_path)
        path = tmp_path / "noise.jpg"
        # Random noise is the worst case for JPEG and forces the ladder down.
        img = Image.new("RGB", (1200, 1200))
        img.putdata(
            [
                (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
                for _ in range(1200 * 1200)
            ]
        )
        img.save(path, "PNG")

        handler.resize_image(str(path))
        assert path.stat().st_size <= MAX_UPLOAD_BYTES

    def test_unreadable_file_returns_none(self, tmp_path):
        handler = ImageHandler(tmp_path)
        path = tmp_path / "junk.jpg"
        path.write_bytes(b"not an image")
        assert handler.resize_image(str(path)) is None


class TestCleanup:
    def test_dotfiles_are_left_alone(self, tmp_path):
        """cleanup used to delete data/images/.gitkeep out of the repo."""
        import os
        import time

        handler = ImageHandler(tmp_path)
        keep = tmp_path / ".gitkeep"
        keep.touch()
        old_image = tmp_path / "old.jpg"
        old_image.touch()
        stale = time.time() - 60 * 60 * 48
        os.utime(keep, (stale, stale))
        os.utime(old_image, (stale, stale))

        deleted = handler.cleanup_old_images(max_age_hours=24)

        assert deleted == 1
        assert keep.exists()
        assert not old_image.exists()

    def test_recent_images_are_kept(self, tmp_path):
        handler = ImageHandler(tmp_path)
        (tmp_path / "fresh.jpg").touch()
        assert handler.cleanup_old_images(max_age_hours=24) == 0
