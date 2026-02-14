"""Configuration module for Funko Bluesky Bot.

This module handles environment variable loading, validation, and logging setup.
"""

import os
import logging
from dataclasses import dataclass
from typing import List
from pathlib import Path
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv


# Load environment variables
load_dotenv()

# Project paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
IMAGES_DIR = DATA_DIR / "images"
LOGS_DIR = BASE_DIR / "logs"
POSTED_PRODUCTS_FILE = DATA_DIR / "posted_products.json"

# Create directories if they don't exist
DATA_DIR.mkdir(exist_ok=True)
IMAGES_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)


@dataclass
class BotConfig:
    """Bot configuration dataclass with type safety."""

    bluesky_handle: str
    bluesky_app_password: str
    check_interval_minutes: int
    fandoms: List[str]
    price_drop_threshold: float
    log_level: str
    test_mode: bool
    dry_run: bool
    funko_region: str
    max_posts_per_check: int
    post_delay_seconds: int
    scrape_pages: List[str]

    @classmethod
    def from_env(cls) -> "BotConfig":
        """Load configuration from environment variables with validation.

        Returns:
            BotConfig: Validated configuration object.

        Raises:
            ValueError: If required environment variables are missing.
        """
        bluesky_handle = os.getenv("BLUESKY_HANDLE")
        bluesky_app_password = os.getenv("BLUESKY_APP_PASSWORD")

        if not bluesky_handle or not bluesky_app_password:
            raise ValueError(
                "BLUESKY_HANDLE and BLUESKY_APP_PASSWORD must be set in .env file"
            )

        fandoms_str = os.getenv("FANDOMS", "Marvel,Star Wars,Disney,Anime")
        fandoms = [f.strip() for f in fandoms_str.split(",")]

        scrape_pages_str = os.getenv("SCRAPE_PAGES", "sale,new-releases,exclusives")
        scrape_pages = [p.strip() for p in scrape_pages_str.split(",")]

        return cls(
            bluesky_handle=bluesky_handle,
            bluesky_app_password=bluesky_app_password,
            check_interval_minutes=int(os.getenv("CHECK_INTERVAL_MINUTES", "15")),
            fandoms=fandoms,
            price_drop_threshold=float(os.getenv("PRICE_DROP_THRESHOLD", "10")),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            test_mode=os.getenv("TEST_MODE", "false").lower() == "true",
            dry_run=os.getenv("DRY_RUN", "false").lower() == "true",
            funko_region=os.getenv("FUNKO_REGION", "pl"),
            max_posts_per_check=int(os.getenv("MAX_POSTS_PER_CHECK", "0")),
            post_delay_seconds=int(os.getenv("POST_DELAY_SECONDS", "0")),
            scrape_pages=scrape_pages,
        )


# Fandom mappings for filtering and categorization
FANDOM_MAPPINGS = {
    "marvel": [
        "Marvel",
        "Avengers",
        "Spider-Man",
        "X-Men",
        "Iron Man",
        "Captain America",
    ],
    "star_wars": ["Star Wars", "Mandalorian", "Baby Yoda", "Grogu", "Darth Vader"],
    "disney": ["Disney", "Mickey Mouse", "Minnie Mouse", "Frozen", "Moana", "Encanto"],
    "anime": [
        "Anime",
        "Dragon Ball",
        "Naruto",
        "One Piece",
        "My Hero Academia",
        "Demon Slayer",
    ],
    "dc": [
        "DC",
        "Batman",
        "Superman",
        "Wonder Woman",
        "Justice League",
        "Harley Quinn",
    ],
    "harry_potter": ["Harry Potter", "Hogwarts", "Dumbledore", "Hermione"],
    "pokemon": ["Pokemon", "Pikachu", "Charizard", "Eevee"],
    "gaming": ["Gaming", "Fortnite", "Minecraft", "Overwatch", "League of Legends"],
}


def setup_logging(log_level: str = "INFO") -> logging.Logger:
    """Configure logging with rotating file handler.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).

    Returns:
        logging.Logger: Configured logger instance.
    """
    logger = logging.getLogger("funko_bot")
    logger.setLevel(getattr(logging, log_level.upper()))

    # Remove existing handlers to avoid duplicates
    logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_format = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(console_format)

    # Rotating file handler (max 5MB, 5 backups)
    file_handler = RotatingFileHandler(
        LOGS_DIR / "bot.log",
        maxBytes=5 * 1024 * 1024,  # 5MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(getattr(logging, log_level.upper()))
    file_format = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_format)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger


# Initialize configuration and logger
try:
    config = BotConfig.from_env()
    logger = setup_logging(config.log_level)
    logger.info("Configuration loaded successfully")
except Exception as e:
    # Fallback logger if config fails
    logging.basicConfig(level=logging.ERROR)
    logging.error(f"Failed to load configuration: {e}")
    raise
