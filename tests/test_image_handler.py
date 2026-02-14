"""Tests for the image handler module."""

import pytest
from pathlib import Path
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
