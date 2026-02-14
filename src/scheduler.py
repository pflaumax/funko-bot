"""Scheduler for automated Funko product monitoring.

This module coordinates the scraper and bot to check for new products
and post updates on a scheduled interval.
"""

import json
import logging
import signal
import sys
from typing import Dict, Set
from datetime import datetime, timedelta
from pathlib import Path

import schedule

from config.settings import config, POSTED_PRODUCTS_FILE, IMAGES_DIR
from src.bot import FunkoBlueskyBot
from src.scraper import FunkoScraper
from src.image_handler import ImageHandler


logger = logging.getLogger("funko_bot.scheduler")

# Global flag for graceful shutdown
shutdown_requested = False


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    global shutdown_requested
    logger.info(f"Received signal {signum}, initiating graceful shutdown...")
    shutdown_requested = True


def load_posted_products() -> Dict[str, Dict]:
    """Load previously posted products from JSON file.

    Returns:
        Dict mapping product_id to product data.
    """
    if not POSTED_PRODUCTS_FILE.exists():
        logger.info("No posted products file found, starting fresh")
        return {}

    try:
        with open(POSTED_PRODUCTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        logger.info(f"Loaded {len(data)} previously posted products")
        return data
    except Exception as e:
        logger.error(f"Failed to load posted products: {e}")
        return {}


def save_posted_products(products: Dict[str, Dict]) -> None:
    """Save posted products to JSON file.

    Args:
        products: Dict mapping product_id to product data.
    """
    try:
        # Cleanup old entries (older than 90 days)
        cutoff_date = datetime.now() - timedelta(days=90)
        cleaned_products = {}

        for product_id, product_data in products.items():
            posted_at_str = product_data.get("posted_at", "")
            try:
                posted_at = datetime.fromisoformat(posted_at_str)
                if posted_at > cutoff_date:
                    cleaned_products[product_id] = product_data
            except (ValueError, TypeError):
                # Keep if we can't parse date
                cleaned_products[product_id] = product_data

        removed_count = len(products) - len(cleaned_products)
        if removed_count > 0:
            logger.info(f"Removed {removed_count} old product entries")

        # Save to file
        POSTED_PRODUCTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(POSTED_PRODUCTS_FILE, "w", encoding="utf-8") as f:
            json.dump(cleaned_products, f, indent=2, ensure_ascii=False)

        logger.debug(f"Saved {len(cleaned_products)} posted products")

    except Exception as e:
        logger.error(f"Failed to save posted products: {e}", exc_info=True)


def extract_hashtag_from_license(license_name: str, name: str = "") -> str:
    """Extract a hashtag from product license (scraped from website).

    The license field from the website contains the specific series name
    (e.g., "Chainsaw Man", "Spider-Man", "Harry Potter") which makes
    perfect hashtags. For generic licenses (Marvel, DC), extracts character
    name from product name.

    Args:
        license_name: License/series name from website (e.g., "Chainsaw Man")
        name: Product name as fallback

    Returns:
        Hashtag without spaces (e.g., "ChainsawMan", "SpiderMan")
    """
    # Use license name if available
    source = license_name if license_name else name

    # If license is generic (Marvel, DC, Anime, etc.), try to extract specific character from name
    generic_licenses = ["marvel", "dc", "anime", "disney", "star wars", "gaming"]
    if source.lower() in generic_licenses and name:
        # Try to extract character/series name from product name
        # Examples: "Pop! Spider-Man" -> "Spider-Man", "Pop! Batman" -> "Batman"
        name_clean = name.replace("Pop!", "").replace("Plus", "").strip()

        # Common character patterns to look for
        characters = [
            "Spider-Man",
            "Iron Man",
            "Captain America",
            "Black Widow",
            "Thor",
            "Hulk",
            "Wolverine",
            "Deadpool",
            "Venom",
            "Batman",
            "Superman",
            "Wonder Woman",
            "Harley Quinn",
            "Joker",
            "Flash",
            "Aquaman",
            "Green Lantern",
        ]

        for char in characters:
            if char.lower() in name_clean.lower():
                source = char
                break
        else:
            # If no character match, try to get first meaningful word from name
            words = name_clean.split()
            if words:
                source = words[0]

    # Remove common prefixes
    source = source.replace("Pop!", "").strip()

    # Convert to PascalCase hashtag (remove spaces, capitalize each word)
    words = source.split()
    hashtag = "".join(word.capitalize() for word in words if word)

    # Remove special characters, keep only alphanumeric
    hashtag = "".join(c for c in hashtag if c.isalnum())

    return hashtag if hashtag else "FunkoPop"


def format_post_text(product: Dict) -> str:
    """Format post text for a product based on page type and status.

    Args:
        product: Product dictionary.

    Returns:
        Formatted post text.
    """
    fandom = product.get("fandom", "")
    name = product.get("name", "Unknown Product")
    price = product.get("price", 0)
    original_price = product.get("original_price", 0)
    price_drop = product.get("price_drop", 0)
    product_url = product.get("product_url", "")
    currency = product.get("currency", "EUR")
    badge = product.get("badge", "")
    page_type = product.get("page_type", "sale")
    availability = product.get("availability", "In Stock")
    drop_date = product.get("drop_date")

    # Currency symbol
    currency_symbols = {
        "EUR": "€",
        "USD": "$",
        "GBP": "£",
    }
    sym = currency_symbols.get(currency, currency)

    # Generate hashtags
    license_name = product.get("license", "")
    series_hashtag = extract_hashtag_from_license(license_name, name)
    hashtags = f"#{series_hashtag} #Funko #FunkoPop"

    # Fandom tag (always show real fandom)
    fandom_tag = f"[{fandom}]" if fandom and fandom != "Other" else ""

    # Product line - ALWAYS show ✨ emoji, with badge if it exists
    if badge and badge.lower() != "null":
        product_line = f"✨ {badge} {name}\n"
    else:
        product_line = f"✨ {name}\n"

    # Determine post type based on page_type and product status
    # Priority: Coming Soon > Sale > Page Type

    if availability == "Coming Soon" or drop_date:
        # Coming Soon / Pre-order
        emoji = "🔜"
        status = "COMING SOON"

        if drop_date:
            drop_line = f"Drops {drop_date}\n"
        else:
            drop_line = ""

        if price > 0:
            text = (
                f"{emoji} {status} {fandom_tag}\n"
                f"{product_line}"
                f"{drop_line}"
                f"Price: {sym}{price:.2f}\n"
                f"\n"
                f"🔗 {product_url}\n"
                f"\n"
                f"{hashtags}"
            )
        else:
            text = (
                f"{emoji} {status} {fandom_tag}\n"
                f"{product_line}"
                f"{drop_line}"
                f"\n"
                f"🔗 {product_url}\n"
                f"\n"
                f"{hashtags}"
            )

    elif price_drop > 0 and original_price > 0:
        # Sale item with price drop
        emoji = "🏷️"
        status = "SALE"

        text = (
            f"{emoji} {status} {fandom_tag}\n"
            f"{product_line}"
            f"Was: {sym}{original_price:.2f} → Now: {sym}{price:.2f}\n"
            f"\n"
            f"🔗 {product_url}\n"
            f"\n"
            f"{hashtags}"
        )

    elif page_type == "new-releases":
        # New releases
        emoji = "🆕"
        status = "NEW RELEASE"

        if price > 0:
            text = (
                f"{emoji} {status} {fandom_tag}\n"
                f"{product_line}"
                f"Price: {sym}{price:.2f}\n"
                f"\n"
                f"🔗 {product_url}\n"
                f"\n"
                f"{hashtags}"
            )
        else:
            text = (
                f"{emoji} {status} {fandom_tag}\n"
                f"{product_line}"
                f"\n"
                f"🔗 {product_url}\n"
                f"\n"
                f"{hashtags}"
            )

    elif page_type == "back-in-stock":
        # Back in stock
        emoji = "🔄"
        status = "BACK IN STOCK"

        if price > 0:
            text = (
                f"{emoji} {status} {fandom_tag}\n"
                f"{product_line}"
                f"Price: {sym}{price:.2f}\n"
                f"\n"
                f"🔗 {product_url}\n"
                f"\n"
                f"{hashtags}"
            )
        else:
            text = (
                f"{emoji} {status} {fandom_tag}\n"
                f"{product_line}"
                f"\n"
                f"🔗 {product_url}\n"
                f"\n"
                f"{hashtags}"
            )

    elif page_type == "exclusives":
        # Exclusives
        emoji = "⭐"
        status = "EXCLUSIVE"

        if price > 0:
            text = (
                f"{emoji} {status} {fandom_tag}\n"
                f"{product_line}"
                f"Price: {sym}{price:.2f}\n"
                f"\n"
                f"🔗 {product_url}\n"
                f"\n"
                f"{hashtags}"
            )
        else:
            text = (
                f"{emoji} {status} {fandom_tag}\n"
                f"{product_line}"
                f"\n"
                f"🔗 {product_url}\n"
                f"\n"
                f"{hashtags}"
            )

    elif page_type == "best-selling":
        # Best selling
        emoji = "🔥"
        status = "BEST SELLER"

        if price > 0:
            text = (
                f"{emoji} {status} {fandom_tag}\n"
                f"{product_line}"
                f"Price: {sym}{price:.2f}\n"
                f"\n"
                f"🔗 {product_url}\n"
                f"\n"
                f"{hashtags}"
            )
        else:
            text = (
                f"{emoji} {status} {fandom_tag}\n"
                f"{product_line}"
                f"\n"
                f"🔗 {product_url}\n"
                f"\n"
                f"{hashtags}"
            )

    else:
        # Default / Sale page without discount
        emoji = "🏷️"
        status = "Funko Pop"

        if price > 0:
            text = (
                f"{emoji} {fandom_tag} {status}\n"
                f"{product_line}"
                f"Price: {sym}{price:.2f}\n"
                f"\n"
                f"🔗 {product_url}\n"
                f"\n"
                f"{hashtags}"
            )
        else:
            text = (
                f"{emoji} {fandom_tag} {status}\n"
                f"{product_line}"
                f"\n"
                f"🔗 {product_url}\n"
                f"\n"
                f"{hashtags}"
            )

    return text


def main_check_job(
    bot: FunkoBlueskyBot,
    scraper: FunkoScraper,
    image_handler: ImageHandler,
    posted_products: Dict[str, Dict],
    max_posts_per_check: int = 0,
    post_delay_seconds: int = 0,
) -> None:
    """Main job that checks for new products and posts updates.

    Args:
        bot: Bluesky bot instance.
        scraper: Funko scraper instance.
        image_handler: Image handler instance.
        posted_products: Dict of previously posted products.
        max_posts_per_check: Maximum posts per check (0 = unlimited).
        post_delay_seconds: Delay between posts in seconds (0 = no delay).
    """
    logger.info("=" * 60)
    logger.info("Starting scheduled product check")
    logger.info("=" * 60)

    try:
        # Get new products
        new_products = scraper.get_new_products(config.fandoms)
        logger.info(f"Found {len(new_products)} products matching fandoms")

        # Filter out already posted products
        products_to_post = []
        for product in new_products:
            product_id = product["id"]
            if product_id not in posted_products:
                products_to_post.append(product)

        logger.info(f"Found {len(products_to_post)} new products to post")

        # Apply rate limiting
        if max_posts_per_check > 0 and len(products_to_post) > max_posts_per_check:
            logger.info(
                f"Rate limiting: {len(products_to_post)} products found, "
                f"posting only {max_posts_per_check} this check"
            )
            products_to_post = products_to_post[:max_posts_per_check]

        # Post each new product
        posts_made = 0
        for product in products_to_post:
            try:
                if config.dry_run:
                    logger.info(f"[DRY RUN] Would post: {product['name']}")
                    continue

                # Add delay between posts (except for first post)
                if posts_made > 0 and post_delay_seconds > 0:
                    logger.info(f"Waiting {post_delay_seconds}s before next post...")
                    import time

                    time.sleep(post_delay_seconds)

                # Download and prepare images (returns list)
                image_paths = image_handler.download_and_prepare(product)

                if not image_paths:
                    logger.error(f"No images available for {product['name']}")
                    continue

                # Generate alt text for each image
                alt_texts = []
                for i, img_path in enumerate(image_paths):
                    if i == 0:
                        # Main image - standard alt text
                        alt_texts.append(image_handler.generate_alt_text(product))
                    else:
                        # Alternate image - mention it's in-box/packaging
                        alt_texts.append(
                            f"{product.get('name', 'Funko Pop')} in original packaging"
                        )

                # Format post text
                post_text = format_post_text(product)

                # Send post with multiple images
                logger.info(
                    f"Posting product: {product['name']} ({len(image_paths)} images)"
                )
                success = bot.send_post(post_text, image_paths, alt_texts)

                if success:
                    # Mark as posted
                    posted_products[product["id"]] = {
                        "name": product["name"],
                        "posted_at": datetime.now().isoformat(),
                        "price": product["price"],
                    }
                    posts_made += 1
                    logger.info(f"Successfully posted: {product['name']}")
                else:
                    logger.error(f"Failed to post: {product['name']}")

            except Exception as e:
                logger.error(
                    f"Error posting product {product.get('name', 'unknown')}: {e}",
                    exc_info=True,
                )
                # Continue with next product (graceful degradation)
                continue

        # Log posting summary
        logger.info(f"Posted {posts_made} products this check")

        # Save updated posted products
        save_posted_products(posted_products)

        # Cleanup old images
        image_handler.cleanup_old_images(max_age_hours=24)

        logger.info("Scheduled check completed successfully")

    except Exception as e:
        logger.error(f"Error in main check job: {e}", exc_info=True)


def run_scheduler(
    bot: FunkoBlueskyBot, scraper: FunkoScraper, run_once: bool = False
) -> None:
    """Run the scheduler loop.

    Args:
        bot: Bluesky bot instance.
        scraper: Funko scraper instance.
        run_once: If True, run once and exit.
    """
    # Initialize components
    image_handler = ImageHandler(IMAGES_DIR)
    posted_products = load_posted_products()

    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Schedule the job
    interval = config.check_interval_minutes
    max_posts = config.max_posts_per_check
    post_delay = config.post_delay_seconds

    logger.info(f"Scheduling checks every {interval} minutes")
    if max_posts > 0:
        logger.info(f"Rate limiting: max {max_posts} posts per check")
    if post_delay > 0:
        logger.info(f"Post delay: {post_delay} seconds between posts")

    # Create job function with bound arguments
    def job():
        main_check_job(
            bot, scraper, image_handler, posted_products, max_posts, post_delay
        )

    if run_once:
        logger.info("Running in single-execution mode")
        job()
        return

    # Schedule recurring job
    schedule.every(interval).minutes.do(job)

    # Run immediately on startup
    logger.info("Running initial check...")
    job()

    # Main scheduler loop
    logger.info("Entering scheduler loop (press Ctrl+C to stop)")
    while not shutdown_requested:
        try:
            schedule.run_pending()
            import time

            time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
            break
        except Exception as e:
            logger.error(f"Error in scheduler loop: {e}", exc_info=True)

    logger.info("Scheduler stopped gracefully")
