"""Post text and hashtags for a scraped product.

Kept out of the scheduler so the wording can be changed and tested without
touching the posting loop.
"""

import logging

logger = logging.getLogger("funko_bot.post_formatter")

CURRENCY_SYMBOLS = {
    "EUR": "€",
    "USD": "$",
    "GBP": "£",
}

# emoji + status headline per scraped page. Anything not listed here falls
# through to DEFAULT_STYLE, which orders its header differently.
PAGE_STYLES: dict[str, tuple[str, str]] = {
    "new-releases": ("\U0001f195", "NEW RELEASE"),
    "back-in-stock": ("\U0001f504", "BACK IN STOCK"),
    "exclusives": ("⭐", "EXCLUSIVE"),
    "best-selling": ("\U0001f525", "BEST SELLER"),
}
COMING_SOON_STYLE = ("\U0001f51c", "COMING SOON")
SALE_STYLE = ("\U0001f3f7️", "SALE")
DEFAULT_STYLE = ("\U0001f3f7️", "Funko Pop")

# Licenses too broad to make a good hashtag on their own — for these the
# character name is pulled out of the product title instead.
GENERIC_LICENSES = {"marvel", "dc", "anime", "disney", "star wars", "gaming"}

KNOWN_CHARACTERS = [
    "Spider-Man", "Iron Man", "Captain America", "Black Widow", "Thor",
    "Hulk", "Wolverine", "Deadpool", "Venom", "Batman", "Superman",
    "Wonder Woman", "Harley Quinn", "Joker", "Flash", "Aquaman",
    "Green Lantern",
]


def extract_hashtag_from_license(license_name: str, name: str = "") -> str:
    """Build a series hashtag from a product's license.

    The scraped license is usually the specific series ("Chainsaw Man"),
    which makes a good tag as-is. Broad licenses fall back to a character
    name taken from the product title.

    Args:
        license_name: License/series name from the site.
        name: Product name, used as a fallback source.

    Returns:
        Hashtag body without the leading '#'.
    """
    source = license_name or name

    if source.lower() in GENERIC_LICENSES and name:
        name_clean = name.replace("Pop!", "").replace("Plus", "").strip()
        for character in KNOWN_CHARACTERS:
            if character.lower() in name_clean.lower():
                source = character
                break
        else:
            words = name_clean.split()
            if words:
                source = words[0]

    source = source.replace("Pop!", "").strip()
    # Upper the first letter only: str.capitalize() would lowercase the rest
    # and turn "Spider-Man" into #Spiderman and "DC" into #Dc.
    hashtag = "".join(
        word[0].upper() + word[1:] for word in source.split() if word
    )
    hashtag = "".join(c for c in hashtag if c.isalnum())

    return hashtag or "FunkoPop"


def _classify(product: dict) -> str:
    """Decide which headline a product gets.

    Precedence is availability, then a discount, then the page it came
    from — a pre-order announces itself before its price does.

    Args:
        product: Product dictionary.

    Returns:
        One of "coming_soon", "sale", a PAGE_STYLES key, or "default".
    """
    if product.get("availability") == "Coming Soon" or product.get("drop_date"):
        return "coming_soon"
    if product.get("price_drop", 0) > 0 and product.get("original_price", 0) > 0:
        return "sale"
    page_type = product.get("page_type")
    if page_type in PAGE_STYLES:
        return page_type
    return "default"


def _header(product: dict, kind: str) -> str:
    """Build the headline for a classified product.

    Args:
        product: Product dictionary.
        kind: Result of _classify().

    Returns:
        The first line of the post.
    """
    fandom = product.get("fandom", "")
    fandom_tag = f"[{fandom}]" if fandom and fandom != "Other" else ""

    if kind == "coming_soon":
        emoji, status = COMING_SOON_STYLE
    elif kind == "sale":
        emoji, status = SALE_STYLE
    elif kind in PAGE_STYLES:
        emoji, status = PAGE_STYLES[kind]
    else:
        # The fallback headline puts the fandom before the status. Kept
        # as-is so old and new posts read the same in the feed.
        emoji, status = DEFAULT_STYLE
        return f"{emoji} {fandom_tag} {status}"

    return f"{emoji} {status} {fandom_tag}"


def _price_lines(product: dict, kind: str, symbol: str) -> list[str]:
    """Return the price line for a product, which may be absent.

    A sale shows both prices; everything else shows one, and a product
    with no price shows none. A discounted pre-order deliberately shows
    only its current price — the headline is already about the drop date.

    Args:
        product: Product dictionary.
        kind: Result of _classify().
        symbol: Currency symbol.

    Returns:
        Zero or one formatted price line.
    """
    price = product.get("price", 0)
    original = product.get("original_price", 0)

    if kind == "sale":
        return [f"Was: {symbol}{original:.2f} → Now: {symbol}{price:.2f}"]
    if price > 0:
        return [f"Price: {symbol}{price:.2f}"]
    return []


def format_post_text(product: dict) -> str:
    """Format the Bluesky post body for a product.

    Args:
        product: Product dictionary.

    Returns:
        Post text, under Bluesky's 300-character limit for typical products.
    """
    name = product.get("name", "Unknown Product")
    badge = product.get("badge", "")
    currency = product.get("currency", "EUR")
    symbol = CURRENCY_SYMBOLS.get(currency, currency)

    product_line = f"✨ {badge} {name}" if badge else f"✨ {name}"

    kind = _classify(product)

    detail_lines: list[str] = []
    if kind == "coming_soon" and product.get("drop_date"):
        detail_lines.append(f"Drops {product['drop_date']}")
    detail_lines += _price_lines(product, kind, symbol)

    series_hashtag = extract_hashtag_from_license(product.get("license", ""), name)
    hashtags = f"#{series_hashtag} #Funko #FunkoPop"

    parts = [
        _header(product, kind),
        product_line,
        *detail_lines,
        "",
        f"\U0001f517 {product.get('product_url', '')}",
        "",
        hashtags,
    ]
    return "\n".join(parts)
