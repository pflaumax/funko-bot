"""Tests for the Funko scraper module."""

import pytest
from src.scraper import FunkoScraper


class TestFunkoScraper:
    """Test cases for FunkoScraper class."""

    def test_scraper_initialization(self):
        """Test scraper initializes correctly."""
        scraper = FunkoScraper()
        assert scraper is not None
        assert scraper.session is not None

    def test_generate_product_id(self):
        """Test product ID generation is consistent."""
        scraper = FunkoScraper()

        product_id_1 = scraper._generate_product_id(
            "Test Product", "http://example.com"
        )
        product_id_2 = scraper._generate_product_id(
            "Test Product", "http://example.com"
        )

        assert product_id_1 == product_id_2
        assert len(product_id_1) == 16

    def test_filter_by_fandom(self):
        """Test filtering products by fandom."""
        scraper = FunkoScraper()

        products = [
            {"id": "1", "name": "Spider-Man", "fandom": "Marvel"},
            {"id": "2", "name": "Darth Vader", "fandom": "Star Wars"},
            {"id": "3", "name": "Mickey Mouse", "fandom": "Disney"},
        ]

        filtered = scraper.filter_by_fandom(products, ["Marvel"])
        assert len(filtered) == 1
        assert filtered[0]["name"] == "Spider-Man"

        filtered_all = scraper.filter_by_fandom(products, ["All"])
        assert len(filtered_all) == 3
