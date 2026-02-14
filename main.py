#!/usr/bin/env python3
"""Main entry point for Funko Bluesky Bot.

This script initializes the bot, scraper, and scheduler to monitor
Funko Pop products and post updates to Bluesky.
"""

import sys
import argparse
import logging

from config.settings import config, logger
from src.bot import FunkoBlueskyBot
from src.scraper import FunkoScraper
from src.scheduler import run_scheduler


def parse_arguments():
    """Parse command line arguments.

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        description="Funko Bluesky Bot - Monitor and post Funko Pop sales"
    )

    parser.add_argument(
        "--test-mode",
        action="store_true",
        help="Run in test mode (uses test account if configured)",
    )

    parser.add_argument(
        "--once", action="store_true", help="Run once and exit (no scheduling loop)"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run mode (log actions without posting)",
    )

    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default=None,
        help="Override log level from config",
    )

    return parser.parse_args()


def main():
    """Main function to run the Funko Bluesky Bot."""
    # Parse command line arguments
    args = parse_arguments()

    # Override config with command line arguments
    if args.test_mode:
        config.test_mode = True
        logger.info("Running in TEST MODE")

    if args.dry_run:
        config.dry_run = True
        logger.info("Running in DRY RUN mode (no posts will be sent)")

    if args.log_level:
        logger.setLevel(getattr(logging, args.log_level))
        logger.info(f"Log level set to {args.log_level}")

    # Display configuration
    logger.info("=" * 60)
    logger.info("Funko Bluesky Bot Starting")
    logger.info("=" * 60)
    logger.info(f"Bluesky Handle: {config.bluesky_handle}")
    logger.info(f"Check Interval: {config.check_interval_minutes} minutes")
    logger.info(f"Monitoring Fandoms: {', '.join(config.fandoms)}")
    logger.info(f"Price Drop Threshold: ${config.price_drop_threshold}")
    logger.info(f"Test Mode: {config.test_mode}")
    logger.info(f"Dry Run: {config.dry_run}")
    logger.info("=" * 60)

    try:
        # Initialize bot
        logger.info("Initializing Bluesky bot...")
        bot = FunkoBlueskyBot(
            handle=config.bluesky_handle, app_password=config.bluesky_app_password
        )

        # Initialize scraper
        logger.info("Initializing Funko scraper...")
        scraper = FunkoScraper(
            region=config.funko_region,
            pages=config.scrape_pages,
        )

        # Run scheduler
        logger.info("Starting scheduler...")
        with bot:
            run_scheduler(bot, scraper, run_once=args.once)

        logger.info("Bot stopped successfully")
        return 0

    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
        return 0

    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
