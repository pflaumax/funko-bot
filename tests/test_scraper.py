"""Tests for the Funko scraper module."""

from src.scraper import clean_product_name, product_key


class TestProductName:
    """The CDN appends noise to image alt text; names must come out bare."""

    def test_strips_hires_view_suffix(self):
        assert (
            clean_product_name("Pop! Fuecoco, , hi-res view 1") == "Pop! Fuecoco"
        )

    def test_strips_image_suffix(self):
        assert clean_product_name("Pop! Stripe, Image 1") == "Pop! Stripe"

    def test_keeps_variant_parentheses(self):
        assert (
            clean_product_name("Pop! Doflamingo (Flocked), , hi-res view 1")
            == "Pop! Doflamingo (Flocked)"
        )

    def test_clean_name_is_unchanged(self):
        assert clean_product_name("Pop! Jumbo Astro Bot") == "Pop! Jumbo Astro Bot"

    def test_empty_input(self):
        assert clean_product_name("") == ""
        assert clean_product_name(None) == ""


class TestProductKey:
    """The dedup key must survive the alt-text fix, or history is lost."""

    def test_noisy_and_clean_names_share_a_key(self):
        assert product_key("Pop! Fuecoco, , hi-res view 1") == product_key(
            "Pop! Fuecoco"
        )

    def test_key_is_case_insensitive(self):
        assert product_key("Pop! Fuecoco") == product_key("POP! FUECOCO")

    def test_distinct_products_differ(self):
        assert product_key("Pop! Fuecoco") != product_key("Pop! Pikachu")

    def test_key_length(self):
        assert len(product_key("Pop! Fuecoco")) == 16


class TestFunkoScraper:
    """Test cases for FunkoScraper class."""

    def test_scraper_initialization(self, scraper):
        assert scraper.session is not None
        assert scraper.currency == "EUR"

    def test_region_selects_currency(self):
        from src.scraper import FunkoScraper

        assert FunkoScraper(region="gb").currency == "GBP"
        assert FunkoScraper(region="us").currency == "USD"

    def test_generate_product_id_is_stable(self, scraper):
        first = scraper._generate_product_id("Test Product", "http://example.com")
        second = scraper._generate_product_id("Test Product", "http://other.com")
        # Keyed on the name alone, so a changed URL must not split the entry.
        assert first == second
        assert len(first) == 16

    def test_filter_by_fandom_allowlist(self, scraper):
        products = [
            {"id": "1", "name": "Spider-Man", "fandom": "Marvel"},
            {"id": "2", "name": "Darth Vader", "fandom": "Star Wars"},
        ]
        filtered = scraper.filter_by_fandom(products, ["Marvel"])
        assert [p["name"] for p in filtered] == ["Spider-Man"]

    def test_all_still_drops_excluded_fandoms(self, scraper):
        """'All' bypasses the allowlist but never the exclusion list."""
        products = [
            {"id": "1", "name": "Spider-Man", "fandom": "Marvel"},
            {"id": "2", "name": "Darth Vader", "fandom": "Star Wars"},
            {"id": "3", "name": "Mickey Mouse", "fandom": "Disney"},
            {"id": "4", "name": "Some Slugger", "fandom": "MLB"},
        ]
        filtered = scraper.filter_by_fandom(products, ["All"])
        assert [p["name"] for p in filtered] == ["Spider-Man", "Darth Vader"]
