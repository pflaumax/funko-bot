"""Funko product scraper for monitoring sale items.

Scrapes the funko.com pages using cloudscraper to bypass Cloudflare.
Region is configurable (default: /pl/ for Poland/EUR).
Falls back to the kennymkchan/funko-pop-data GitHub dataset if the
live site is unreachable.
"""

import time
import logging
import hashlib
from typing import List, Dict, Optional
from datetime import datetime
from random import sample

import requests
import cloudscraper
from bs4 import BeautifulSoup


logger = logging.getLogger("funko_bot.scraper")

RATE_LIMIT_DELAY = 2  # seconds between requests
FUNKO_BASE_URL = "https://funko.com"

# Region-to-currency mapping
# European regions use EUR, UK uses GBP, US (empty region) uses USD
REGION_CURRENCY_MAP = {
    # European Union countries (EUR)
    "at": "EUR",  # Austria
    "be": "EUR",  # Belgium
    "bg": "EUR",  # Bulgaria
    "hr": "EUR",  # Croatia
    "cy": "EUR",  # Cyprus
    "cz": "EUR",  # Czech Republic
    "dk": "EUR",  # Denmark
    "ee": "EUR",  # Estonia
    "fi": "EUR",  # Finland
    "fr": "EUR",  # France
    "de": "EUR",  # Germany
    "gr": "EUR",  # Greece
    "hu": "EUR",  # Hungary
    "ie": "EUR",  # Ireland
    "it": "EUR",  # Italy
    "lv": "EUR",  # Latvia
    "lt": "EUR",  # Lithuania
    "lu": "EUR",  # Luxembourg
    "mt": "EUR",  # Malta
    "nl": "EUR",  # Netherlands
    "pl": "EUR",  # Poland
    "pt": "EUR",  # Portugal
    "ro": "EUR",  # Romania
    "sk": "EUR",  # Slovakia
    "si": "EUR",  # Slovenia
    "es": "EUR",  # Spain
    "se": "EUR",  # Sweden
    # United Kingdom (GBP)
    "gb": "GBP",  # United Kingdom
    "uk": "GBP",  # United Kingdom (alternative)
    # United States (USD) - empty region code
    "": "USD",  # US store (default)
    "us": "USD",  # US store (explicit)
}


class FunkoScraper:
    """Scraper for Funko Pop sale products from funko.com.

    Uses cloudscraper to bypass Cloudflare protection. Targets the
    sale page specifically. Region is configurable via FUNKO_REGION
    env var (default: pl for Poland/EUR).
    """

    def __init__(
        self,
        region: str = "pl",
        pages: List[str] = None,
    ):
        """Initialize the scraper.

        Args:
            region: Funko region code (e.g. 'pl', 'ro', 'de', 'fr', 'gb', 'uk').
                    Leave empty for US store (USD).
            pages: List of page types to scrape (e.g. ['sale', 'new-releases', 'exclusives']).
        """
        from config.settings import config
        
        self.session = cloudscraper.create_scraper(
            browser={"browser": "chrome", "platform": "darwin", "mobile": False}
        )
        self.region = region
        self.currency = REGION_CURRENCY_MAP.get(region.lower(), "EUR")
        self.pages = pages or ["sale"]
        self.last_request_time = 0
        self.delay_min = config.scrape_delay_min
        self.delay_max = config.scrape_delay_max

        # Build base URL
        if region:
            self.base_url = f"{FUNKO_BASE_URL}/{region}/new-featured"
        else:
            self.base_url = f"{FUNKO_BASE_URL}/new-featured"

        logger.info(
            f"Scraper initialized — region: {region or 'US'}, "
            f"currency: {self.currency}, pages: {self.pages}, "
            f"delays: {self.delay_min}-{self.delay_max}s"
        )

    def _rate_limit(self) -> None:
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self.last_request_time
        if elapsed < RATE_LIMIT_DELAY:
            time.sleep(RATE_LIMIT_DELAY - elapsed)
        self.last_request_time = time.time()

    def _generate_product_id(self, name: str, url: str) -> str:
        """Generate a unique product ID from name and URL."""
        return hashlib.md5(f"{name}_{url}".encode()).hexdigest()[:16]

    # ------------------------------------------------------------------
    # Primary source: funko.com sale page
    # ------------------------------------------------------------------

    def _fetch_page(self, url: str) -> Optional[str]:
            """Fetch a page via cloudscraper with one retry.

            Args:
                url: URL to fetch.

            Returns:
                HTML string or None on failure.
            """
            self._rate_limit()

            for attempt in range(1, 3):
                try:
                    logger.info(f"Fetching {url} (attempt {attempt}/2)")

                    # Add random delay to avoid detection
                    import random

                    delay = random.uniform(self.delay_min, self.delay_max)
                    logger.debug(f"Waiting {delay:.1f}s before request")
                    time.sleep(delay)

                    resp = self.session.get(url, timeout=30, allow_redirects=True)
                    resp.raise_for_status()
                    logger.info(f"Got {len(resp.text)} chars")
                    return resp.text
                except requests.exceptions.HTTPError as e:
                    status = e.response.status_code if e.response is not None else 0
                    logger.warning(f"HTTP {status} for {url}")
                    if status == 403:
                        logger.warning("Cloudflare blocked — retrying with longer delay")
                        if attempt < 2:
                            time.sleep(random.uniform(self.delay_max * 2, self.delay_max * 3))
                            continue
                        return None
                    if attempt < 2:
                        time.sleep(5)
                        continue
                    return None
                except requests.exceptions.RequestException as e:
                    logger.error(f"Request error: {e}")
                    if attempt < 2:
                        time.sleep(5)
                        continue
                    return None
            return None

    def _parse_sale_page(self, html: str, page_type: str = "sale") -> List[Dict]:
        """Parse product tiles from the funko.com page HTML.

        The page uses `.product-tile` divs with this structure:
        - img.tile-main-image  -> name (alt), image (src)
        - a.image-link         -> product URL (href)
        - span.sales .value    -> sale price (content attr)
        - span.strike-through .value -> original price (content attr)
        - div.product-license  -> fandom/license
        - div.product-flag     -> badge (exclusive, web exclusive, etc.)

        Args:
            html: Raw HTML string.
            page_type: Type of page (sale, new-releases, back-in-stock, etc.)

        Returns:
            List of product dicts.
        """
        soup = BeautifulSoup(html, "lxml")
        tiles = soup.find_all("div", class_="product-tile")
        logger.info(f"Found {len(tiles)} product tiles on {page_type} page")

        products = []
        for tile in tiles:
            try:
                product = self._parse_tile(tile, page_type)
                if product:
                    products.append(product)
            except Exception as e:
                logger.error(f"Failed to parse tile: {e}", exc_info=True)
                continue

        return products

    def _parse_tile(self, tile, page_type: str = "sale") -> Optional[Dict]:
        """Parse a single product tile element.

        Args:
            tile: BeautifulSoup element for one product-tile.
            page_type: Type of page (sale, new-releases, back-in-stock, etc.)

        Returns:
            Product dict or None.
        """
        # Name + image
        img = tile.find("img", class_="tile-main-image")
        if not img:
            return None
        name = img.get("alt", "").replace(", Image 1", "").strip()
        if not name:
            return None
        image_url = img.get("src", "")

        # Upgrade image resolution: replace sw=346&sh=346 with sw=800&sh=800
        if image_url and "sw=346" in image_url:
            image_url = image_url.replace("sw=346&sh=346", "sw=800&sh=800")
            logger.debug(f"Upgraded image URL to 800x800")

        # Get alternate image (often in-box or lifestyle shot)
        alt_img = tile.find("img", class_="tile-alt-hover-image")
        image_url_alt = None
        if alt_img:
            image_url_alt = alt_img.get("src", "")
            if image_url_alt and "sw=346" in image_url_alt:
                image_url_alt = image_url_alt.replace("sw=346&sh=346", "sw=800&sh=800")
                logger.debug(f"Upgraded alt image URL to 800x800")

        # Product URL
        link = tile.find("a", class_="image-link")
        product_url = link["href"] if link else ""

        # Sale price
        sale_price = 0.0
        sales_el = tile.find("span", class_="sales")
        if sales_el:
            val = sales_el.find("span", class_="value")
            if val:
                try:
                    sale_price = float(val.get("content", "0"))
                except (ValueError, TypeError):
                    pass

        # Original price
        original_price = 0.0
        strike_el = tile.find("span", class_="strike-through")
        if strike_el:
            val = strike_el.find("span", class_="value")
            if val:
                try:
                    original_price = float(val.get("content", "0"))
                except (ValueError, TypeError):
                    pass

        # Fandom / license
        lic_el = tile.find("div", class_="product-license")
        license_name = lic_el.get_text(strip=True) if lic_el else ""
        fandom = self._license_to_fandom(license_name, name)

        # Badge (exclusive, web exclusive, etc.)
        flag_el = tile.find("div", class_="product-flag")
        badge = flag_el.get_text(strip=True) if flag_el else ""
        # Capitalize badge properly (e.g., "web exclusive" -> "Web Exclusive")
        # Filter out null/empty badges
        if badge and badge.lower() not in ["null", "none", ""]:
            badge = badge.title()
        else:
            badge = ""

        # Check for "Coming Soon" status and extract drop date
        coming_soon = False
        drop_date = None
        availability_el = tile.find("div", class_="product-availability")
        if availability_el:
            avail_text = availability_el.get_text(strip=True).lower()
            if "coming soon" in avail_text or "pre-order" in avail_text:
                coming_soon = True
                # Try to extract date from various formats
                # Example: "Drops 16/02 at 05:30 PM GMT"
                import re

                date_match = re.search(r"(\d{1,2}/\d{1,2}(?:/\d{2,4})?)", avail_text)
                time_match = re.search(
                    r"(\d{1,2}:\d{2}\s*(?:AM|PM)?(?:\s*GMT)?)",
                    avail_text,
                    re.IGNORECASE,
                )
                if date_match:
                    drop_date = date_match.group(1)
                    if time_match:
                        drop_date += f" at {time_match.group(1)}"

        # Calculate discount
        price_drop = 0.0
        if original_price > 0 and sale_price < original_price:
            price_drop = round(original_price - sale_price, 2)

        return {
            "id": self._generate_product_id(name, product_url),
            "name": name,
            "price": sale_price,
            "original_price": original_price,
            "price_drop": price_drop,
            "image_url": image_url,
            "image_url_alt": image_url_alt,
            "fandom": fandom,
            "license": license_name,
            "badge": badge,
            "product_url": product_url,
            "availability": "Coming Soon" if coming_soon else "In Stock",
            "drop_date": drop_date,
            "page_type": page_type,
            "source": "funko.com",
            "currency": self.currency,
            "timestamp": datetime.now().isoformat(),
        }

    def _license_to_fandom(self, license_name: str, title: str) -> str:
        """Map a license name to a fandom category.

        Args:
            license_name: License string from the site (e.g. 'Marvel', 'One Piece').
            title: Product title as secondary signal.

        Returns:
            Fandom category string (uses license name directly).
        """
        # Use the license name directly as the fandom
        # The website provides good categorization already
        return license_name if license_name else "Other"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def filter_by_fandom(self, products: List[Dict], fandoms: List[str]) -> List[Dict]:
        """Filter products by fandom list.

        Args:
            products: Product list.
            fandoms: Fandom names to keep. Use ['All'] for no filtering.

        Returns:
            Filtered product list.
        """
        # Excluded fandoms (specific sports leagues, Disney, etc.)
        excluded_fandoms = {
            "mlb",  # Major League Baseball
            "mls",  # Major League Soccer
            "nfl",  # National Football League
            "nba",  # National Basketball Association
            "nhl",  # National Hockey League
            "disney",  # Disney
            "baseball",  # Baseball
            "basketball",  # Basketball
            "hockey",  # Hockey
        }

        # First, filter out excluded fandoms
        filtered = []
        for p in products:
            fandom = p.get("fandom", "").lower()
            license_name = p.get("license", "").lower()

            # Check if fandom or license matches any excluded category
            is_excluded = False
            for excluded in excluded_fandoms:
                if excluded in fandom or excluded in license_name:
                    is_excluded = True
                    break

            if not is_excluded:
                filtered.append(p)

        excluded_count = len(products) - len(filtered)
        if excluded_count > 0:
            logger.info(
                f"Excluded {excluded_count} products from unwanted fandoms (MLB, MLS, NBA, NFL, NHL, Disney, etc.)"
            )

        # Then apply fandom filter if specified
        if not fandoms or "All" in fandoms:
            return filtered

        fandoms_lower = {f.lower() for f in fandoms}
        final_filtered = [
            p for p in filtered if p.get("fandom", "").lower() in fandoms_lower
        ]
        logger.info(
            f"Fandom filter: {len(final_filtered)}/{len(filtered)} products match"
        )
        return final_filtered

    def get_new_products(self, fandoms: List[str]) -> List[Dict]:
        """Fetch products from multiple pages.

        Args:
            fandoms: Fandoms to filter by.

        Returns:
            List of product dicts from all configured pages.
        """
        logger.info(
            f"Fetching products for fandoms: {fandoms} from pages: {self.pages}"
        )

        all_products = []

        # Scrape from each configured page
        for page_type in self.pages:
            page_url = f"{self.base_url}/{page_type}/"
            logger.info(f"Scraping page: {page_type} ({page_url})")

            try:
                # Fetch page with cloudscraper
                html = self._fetch_page(page_url)
                if html:
                    products = self._parse_sale_page(html, page_type)
                    if products:
                        logger.info(f"Got {len(products)} products from {page_type}")
                        all_products.extend(products)
                    else:
                        logger.warning(f"No products found on {page_type}")
                else:
                    logger.warning(f"Failed to fetch {page_type}")

            except Exception as e:
                logger.error(f"Error scraping {page_type}: {e}")
                continue

        if all_products:
            # Remove duplicates (same product might appear on multiple pages)
            unique_products = {}
            for product in all_products:
                product_id = product["id"]
                if product_id not in unique_products:
                    unique_products[product_id] = product

            all_products = list(unique_products.values())
            logger.info(f"Total unique products from all pages: {len(all_products)}")

            # Shuffle products to mix different page types
            from random import shuffle

            shuffle(all_products)
            logger.info("Shuffled products for variety")

            # Filter by fandom
            filtered = self.filter_by_fandom(all_products, fandoms)
            logger.info(f"After fandom filter: {len(filtered)} products")
            return filtered

        # No products found
        logger.warning("No products found from any page")
        return []

    def check_price_drops(self, previous_products: Dict[str, Dict]) -> List[Dict]:
        """Check for price drops vs previously seen products.

        Only works with live funko.com data (GitHub has no prices).

        Args:
            previous_products: Dict of product_id -> product data.

        Returns:
            List of products with price drops.
        """
        logger.info("Checking for price drops")

        html = self._fetch_page(self.sale_url)
        if not html:
            logger.info("No live data for price drop check")
            return []

        current = self._parse_sale_page(html)
        drops = []

        for product in current:
            pid = product["id"]
            if pid in previous_products:
                old_price = previous_products[pid].get("price", 0)
                new_price = product["price"]
                if old_price > 0 and new_price < old_price:
                    product["original_price"] = old_price
                    product["price_drop"] = round(old_price - new_price, 2)
                    drops.append(product)
                    logger.info(
                        f"Price drop: {product['name']} €{old_price} -> €{new_price}"
                    )

        logger.info(f"Found {len(drops)} price drops")
        return drops
