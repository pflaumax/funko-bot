"""Tests for post text generation.

These pin the shape of what goes into a public feed: the headline that
each kind of product gets, and the price line that goes with it.
"""

from src.post_formatter import extract_hashtag_from_license, format_post_text


def _product(**overrides):
    product = {
        "name": "Pop! Fuecoco",
        "price": 18.0,
        "original_price": 0,
        "price_drop": 0,
        "product_url": "https://funko.com/pl/product/1",
        "currency": "EUR",
        "badge": "",
        "page_type": "best-selling",
        "availability": "In Stock",
        "drop_date": None,
        "fandom": "Pokemon",
        "license": "Pokemon",
    }
    product.update(overrides)
    return product


class TestHeadline:
    def test_sale_shows_both_prices(self):
        text = format_post_text(
            _product(page_type="sale", price=12.0, original_price=20.0, price_drop=8.0)
        )
        assert text.startswith("\U0001f3f7️ SALE [Pokemon]")
        assert "Was: €20.00 → Now: €12.00" in text

    def test_coming_soon_beats_the_page_type(self):
        text = format_post_text(
            _product(page_type="exclusives", availability="Coming Soon")
        )
        assert text.startswith("\U0001f51c COMING SOON")

    def test_drop_date_is_shown(self):
        text = format_post_text(
            _product(availability="Coming Soon", drop_date="16/02 at 05:30 PM")
        )
        assert "Drops 16/02 at 05:30 PM" in text

    def test_discounted_pre_order_shows_one_price(self):
        """The headline already carries the news; two prices would crowd it."""
        text = format_post_text(
            _product(availability="Coming Soon", price=12.0,
                     original_price=20.0, price_drop=8.0)
        )
        assert "Price: €12.00" in text
        assert "Was:" not in text

    def test_each_page_type_has_its_own_headline(self):
        for page_type, marker in [
            ("new-releases", "NEW RELEASE"),
            ("back-in-stock", "BACK IN STOCK"),
            ("exclusives", "EXCLUSIVE"),
            ("best-selling", "BEST SELLER"),
        ]:
            assert marker in format_post_text(_product(page_type=page_type))

    def test_unknown_page_type_falls_back(self):
        text = format_post_text(_product(page_type="something-new"))
        assert text.startswith("\U0001f3f7️ [Pokemon] Funko Pop")


class TestBody:
    def test_badge_is_prefixed_to_the_name(self):
        assert "✨ Web Exclusive Pop! Fuecoco" in format_post_text(
            _product(badge="Web Exclusive")
        )

    def test_no_badge_leaves_no_double_space(self):
        assert "✨ Pop! Fuecoco" in format_post_text(_product())

    def test_missing_price_omits_the_line(self):
        assert "Price:" not in format_post_text(_product(price=0))

    def test_other_fandom_is_not_tagged(self):
        assert "[Other]" not in format_post_text(_product(fandom="Other"))

    def test_currency_symbol_follows_the_region(self):
        assert "£18.00" in format_post_text(_product(currency="GBP"))
        assert "$18.00" in format_post_text(_product(currency="USD"))

    def test_url_and_hashtags_are_present(self):
        text = format_post_text(_product())
        assert "https://funko.com/pl/product/1" in text
        assert text.endswith("#Pokemon #Funko #FunkoPop")

    def test_typical_post_fits_bluesky(self):
        """Bluesky truncates at 300 characters."""
        text = format_post_text(
            _product(name="Pop! Jude Duarte (Coronation Gown) (The Cruel Prince)",
                     badge="Web Exclusive", drop_date="16/02 at 05:30 PM",
                     availability="Coming Soon")
        )
        assert len(text) <= 300


class TestHashtags:
    def test_specific_license_is_used_directly(self):
        assert extract_hashtag_from_license("Chainsaw Man") == "ChainsawMan"

    def test_generic_license_falls_back_to_the_character(self):
        assert extract_hashtag_from_license("Marvel", "Pop! Spider-Man") == "SpiderMan"

    def test_generic_license_with_no_known_character(self):
        assert extract_hashtag_from_license("Marvel", "Pop! Rocket") == "Rocket"

    def test_empty_license_falls_back_to_the_name(self):
        assert extract_hashtag_from_license("", "Pop! Fuecoco") == "Fuecoco"

    def test_nothing_usable_yields_a_default(self):
        assert extract_hashtag_from_license("", "") == "FunkoPop"

    def test_punctuation_is_stripped(self):
        assert extract_hashtag_from_license("Five Nights at Freddy's") == (
            "FiveNightsAtFreddys"
        )
