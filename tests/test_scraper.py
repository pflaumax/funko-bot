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


class TestStorefronts:
    """The US storefront is the site root and names one page differently."""

    def _scraper(self, region):
        from src.scraper import FunkoScraper

        return FunkoScraper(region=region, pages=["sale"])

    def test_us_has_no_locale_prefix(self):
        for region in ("us", "US", "", None):
            assert self._scraper(region).base_url == (
                "https://funko.com/new-featured"
            )

    def test_eu_keeps_its_locale_prefix(self):
        assert self._scraper("pl").base_url == "https://funko.com/pl/new-featured"

    def test_us_renames_the_best_sellers_page(self):
        assert self._scraper("us")._page_slug("best-selling") == "best-sellers"

    def test_other_pages_are_unchanged_on_us(self):
        scraper = self._scraper("us")
        for page in ("sale", "new-releases", "back-in-stock", "exclusives"):
            assert scraper._page_slug(page) == page

    def test_eu_never_translates_slugs(self):
        assert self._scraper("pl")._page_slug("best-selling") == "best-selling"

    def test_us_region_is_usd(self):
        assert self._scraper("us").currency == "USD"
        assert self._scraper("").currency == "USD"


class TestCurrencyDetection:
    """Currency is read off the page, not assumed from the region."""

    def _sales(self, html):
        from bs4 import BeautifulSoup

        return BeautifulSoup(html, "lxml").find("span")

    def test_dollar(self, scraper):
        el = self._sales('<span class="sales">$14.99</span>')
        assert scraper._detect_currency(el) == "USD"

    def test_euro(self, scraper):
        el = self._sales('<span class="sales">€ 23,00</span>')
        assert scraper._detect_currency(el) == "EUR"

    def test_pound(self, scraper):
        el = self._sales('<span class="sales">£12.00</span>')
        assert scraper._detect_currency(el) == "GBP"

    def test_no_symbol_returns_none(self, scraper):
        el = self._sales('<span class="sales">14.99</span>')
        assert scraper._detect_currency(el) is None

    def test_none_elements_are_skipped(self, scraper):
        el = self._sales('<span class="sales">$9.99</span>')
        assert scraper._detect_currency(None, el) == "USD"

    def test_falls_back_to_the_region_when_absent(self, scraper):
        assert scraper._detect_currency(None) is None
        assert scraper.currency == "EUR"


class TestNameSources:
    """Tile markup differs per storefront; every path must yield a bare name."""

    def _tile(self, inner):
        from bs4 import BeautifulSoup

        return BeautifulSoup(
            f'<div class="product-tile">'
            f'<img class="tile-main-image" alt="Pop! X, , hi-res view 1" src="i.png"/>'
            f"{inner}</div>",
            "lxml",
        ).find("div", class_="product-tile")

    def test_eu_product_name_div(self, scraper):
        tile = self._tile('<div class="product-name">Pop! Gus Fring (Bloody)</div>')
        assert scraper._parse_tile(tile)["name"] == "Pop! Gus Fring (Bloody)"

    def test_us_pdp_link(self, scraper):
        tile = self._tile('<a class="pdp-link">Pop! Gus Fring (Bloody)</a>')
        assert scraper._parse_tile(tile)["name"] == "Pop! Gus Fring (Bloody)"

    def test_alt_is_the_last_resort_and_still_cleaned(self, scraper):
        assert scraper._parse_tile(self._tile(""))["name"] == "Pop! X"

    def test_empty_name_element_falls_through(self, scraper):
        tile = self._tile('<div class="product-name"></div>')
        assert scraper._parse_tile(tile)["name"] == "Pop! X"
