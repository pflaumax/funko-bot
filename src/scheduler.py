"""Scheduler for automated Funko product monitoring.

This module coordinates the scraper and bot to check for new products
and post updates on a scheduled interval.
"""

import json
import logging
import signal
import time
from datetime import datetime, timedelta

import schedule

from config.settings import DATA_DIR, IMAGES_DIR, POSTED_PRODUCTS_FILE, config
from src.bot import FunkoBlueskyBot
from src.image_handler import ImageHandler
from src.post_formatter import format_post_text
from src.scraper import FunkoScraper, clean_product_name, product_key

logger = logging.getLogger("funko_bot.scheduler")

# Ring buffer size for data/posted_products.json. At the default 8 posts
# a day this holds roughly 8 months of history in ~300KB.
MAX_POSTED_ENTRIES = 2000

# Scraped products waiting to be posted. One scrape yields ~45 unposted
# products but a cycle posts one, so without this the other ~44 were thrown
# away and re-fetched three hours later: five requests and ~4 minutes of
# anti-detection delays per single post, which is also what was drawing the
# 403s. Refetched once a day so prices do not go stale.
QUEUE_FILE = DATA_DIR / "product_queue.json"
QUEUE_MAX_AGE_HOURS = 24

# Global flag for graceful shutdown
shutdown_requested = False


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    global shutdown_requested
    logger.info(f"Received signal {signum}, initiating graceful shutdown...")
    shutdown_requested = True


def _write_json(path, payload) -> None:
    """Write JSON atomically: tmp file, then rename over the target."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    tmp_path.replace(path)


def _migrate_keys(products: dict[str, dict]) -> dict[str, dict]:
    """Re-key entries written before the product-name fix.

    Entries used to be keyed on md5("{noisy name}_{url}"), where the name
    still carried the CDN's ", , hi-res view 1" suffix. The key is now
    md5(cleaned, casefolded name). Without this pass every historical
    product looks unseen and the bot reposts its entire back catalogue.

    Args:
        products: Ledger as loaded from disk.

    Returns:
        The ledger keyed under the current scheme.
    """
    migrated: dict[str, dict] = {}
    changed = 0

    for key, entry in products.items():
        if not isinstance(entry, dict):
            continue
        name = entry.get("name", "")
        if not name:
            migrated[key] = entry
            continue

        entry["name"] = clean_product_name(name)
        new_key = product_key(name)
        if new_key != key:
            changed += 1
        migrated.setdefault(new_key, entry)

    if changed:
        logger.info(f"Migrated {changed} ledger entries to the current key scheme")
    return migrated


def load_posted_products() -> dict[str, dict]:
    """Load previously posted products from JSON file.

    The file is hand-editable and lives on an SD card, so its shape is
    normalised rather than trusted: under systemd's Restart=always a
    KeyError here would become a restart loop, and treating a corrupt file
    as "nothing posted" would repost the whole back catalogue.

    Returns:
        Dict mapping product_id to product data.
    """
    if not POSTED_PRODUCTS_FILE.exists():
        logger.info("No posted products file found, starting fresh")
        return {}

    try:
        with open(POSTED_PRODUCTS_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"Failed to load posted products: {e}")
        _quarantine_ledger()
        return {}

    if not isinstance(data, dict):
        logger.error("Posted products file is not an object; ignoring it")
        _quarantine_ledger()
        return {}

    data = _migrate_keys(data)
    logger.info(f"Loaded {len(data)} previously posted products")
    return data


def _quarantine_ledger() -> None:
    """Move an unreadable ledger aside instead of silently overwriting it.

    Losing the ledger means reposting everything, so the bad file is kept
    for inspection rather than clobbered by the next save.
    """
    try:
        backup = POSTED_PRODUCTS_FILE.with_suffix(
            f".corrupt-{datetime.now():%Y%m%d%H%M%S}.json"
        )
        POSTED_PRODUCTS_FILE.rename(backup)
        logger.error(f"Moved unreadable ledger to {backup.name}")
    except OSError as e:
        logger.error(f"Could not quarantine the ledger: {e}")


def _sort_key(entry: dict) -> str:
    """Sort ledger entries oldest-first by posting time."""
    return str(entry.get("posted_at") or "")


def save_posted_products(products: dict[str, dict]) -> None:
    """Save posted products to JSON file, atomically.

    Trimmed to a ring buffer rather than a time window. A 90-day cutoff
    used to drop ~37 entries per cycle, which put those products back in
    the queue to be reposted; a bounded count never does.

    Args:
        products: Dict mapping product_id to product data.
    """
    try:
        if len(products) > MAX_POSTED_ENTRIES:
            ordered = sorted(products.items(), key=lambda kv: _sort_key(kv[1]))
            dropped = len(products) - MAX_POSTED_ENTRIES
            products = dict(ordered[dropped:])
            logger.info(
                f"Ledger trimmed to {MAX_POSTED_ENTRIES} entries "
                f"({dropped} oldest dropped)"
            )

        # Atomic: a power cut mid-write must not leave a truncated ledger.
        _write_json(POSTED_PRODUCTS_FILE, products)

        logger.debug(f"Saved {len(products)} posted products")

    except OSError as e:
        logger.exception(f"Failed to save posted products: {e}")


def load_queue() -> list[dict]:
    """Load the pending product queue, or an empty list if it is unusable.

    Returns:
        Queued products, oldest scrape first. Empty when the file is
        missing, malformed, or older than QUEUE_MAX_AGE_HOURS.
    """
    if not QUEUE_FILE.exists():
        return []

    try:
        with open(QUEUE_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Could not read product queue: {e}")
        return []

    if not isinstance(data, dict) or not isinstance(data.get("products"), list):
        logger.warning("Product queue has an unexpected shape; ignoring it")
        return []

    try:
        fetched_at = datetime.fromisoformat(data.get("fetched_at", ""))
    except (TypeError, ValueError):
        logger.warning("Product queue has no readable timestamp; refetching")
        return []

    age = datetime.now() - fetched_at
    if age > timedelta(hours=QUEUE_MAX_AGE_HOURS):
        logger.info(
            f"Product queue is {age.total_seconds() / 3600:.1f}h old; refetching"
        )
        return []

    products = [p for p in data["products"] if isinstance(p, dict) and p.get("id")]
    logger.info(
        f"Product queue: {len(products)} pending, "
        f"{age.total_seconds() / 3600:.1f}h old"
    )
    return products


def save_queue(products: list[dict]) -> None:
    """Persist the pending product queue.

    Args:
        products: Products still waiting to be posted.
    """
    try:
        _write_json(
            QUEUE_FILE,
            {"fetched_at": datetime.now().isoformat(), "products": products},
        )
    except OSError as e:
        logger.error(f"Failed to save product queue: {e}")


def take_products(
    scraper: FunkoScraper,
    posted_products: dict[str, dict],
    count: int,
) -> list[dict]:
    """Return the next products to post, scraping only when the queue is dry.

    Args:
        scraper: Funko scraper instance.
        posted_products: Ledger of what has already gone out.
        count: How many products to take. 0 means every pending product.

    Returns:
        Products to post this cycle, possibly empty.
    """
    queue = [p for p in load_queue() if p["id"] not in posted_products]

    if not queue:
        logger.info("Queue empty — scraping funko.com")
        scraped = scraper.get_new_products(config.fandoms)
        queue = [p for p in scraped if p["id"] not in posted_products]
        logger.info(f"Scrape produced {len(queue)} unposted products")

    taken = queue[:count] if count > 0 else queue

    # A dry run publishes nothing, so it must not consume the queue either.
    if config.dry_run:
        logger.info("[DRY RUN] Queue left untouched")
    else:
        save_queue(queue[len(taken):])

    if taken:
        logger.info(f"Taking {len(taken)} product(s), {len(queue) - len(taken)} left")
    else:
        logger.warning("Nothing to post this cycle")
    return taken


def main_check_job(
    bot: FunkoBlueskyBot,
    scraper: FunkoScraper,
    image_handler: ImageHandler,
    posted_products: dict[str, dict],
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
        products_to_post = take_products(
            scraper, posted_products, max_posts_per_check
        )

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
                    time.sleep(post_delay_seconds)

                # Download and prepare images (returns list)
                image_paths = image_handler.download_and_prepare(product)

                if not image_paths:
                    logger.error(f"No images available for {product['name']}")
                    continue

                # Generate alt text for each image
                alt_texts = []
                for i in range(len(image_paths)):
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
                # Graceful degradation: one bad product must not end the cycle.
                logger.exception(
                    f"Error posting product {product.get('name', 'unknown')}: {e}"
                )
                continue

        # Log posting summary
        logger.info(f"Posted {posts_made} products this check")

        # Save updated posted products
        save_posted_products(posted_products)

        # Cleanup old images
        image_handler.cleanup_old_images(max_age_hours=24)

        logger.info("Scheduled check completed successfully")

    except Exception as e:
        logger.exception(f"Error in main check job: {e}")


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
            time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
            break
        except Exception as e:
            logger.exception(f"Error in scheduler loop: {e}")

    logger.info("Scheduler stopped gracefully")
