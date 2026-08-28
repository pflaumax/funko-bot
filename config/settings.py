"""Configuration module for Funko Bluesky Bot.

This module handles environment variable loading, validation, and logging setup.
"""

import logging
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, NoReturn

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


def _fail(message: str) -> NoReturn:
    """Report a bad setting and exit, rather than raise.

    The systemd unit is Restart=always, so an exception raised while this
    module is imported turns a one-character typo in .env into a restart
    loop that logs only a traceback. Exiting deliberately with the reason
    on stderr is the difference between a fixable error and a mystery.

    Args:
        message: What is wrong with the configuration.
    """
    print(f"CONFIG ERROR: {message}", file=sys.stderr)
    sys.exit(1)


def _number_env(
    name: str, default: str, cast: Callable[[str], Any], minimum: float
) -> Any:
    """Read a numeric environment variable, or exit explaining why not.

    Args:
        name: Environment variable name.
        default: Value used when the variable is unset.
        cast: ``int`` or ``float``.
        minimum: Smallest value that makes sense for this setting.

    Returns:
        The parsed number.
    """
    raw = os.getenv(name, default).strip()
    try:
        value = cast(raw)
    except (TypeError, ValueError):
        _fail(f"{name} must be a number, got {raw!r}")
    if value < minimum:
        _fail(f"{name} must be at least {minimum}, got {value}")
    return value


def _bool_env(name: str, default: bool = False) -> bool:
    """Read a boolean environment variable."""
    raw = os.getenv(name, str(default)).strip().lower()
    return raw in ("1", "true", "yes", "on")


def _list_env(name: str, default: str) -> list[str]:
    """Read a comma-separated environment variable into a list."""
    raw = os.getenv(name, default)
    items = [item.strip() for item in raw.split(",") if item.strip()]
    if not items:
        _fail(f"{name} must list at least one value, got {raw!r}")
    return items


@dataclass
class BotConfig:
    """Bot configuration dataclass with type safety."""

    bluesky_handle: str
    bluesky_app_password: str
    check_interval_minutes: int
    fandoms: list[str]
    log_level: str
    test_mode: bool
    dry_run: bool
    funko_region: str
    max_posts_per_check: int
    post_delay_seconds: int
    scrape_pages: list[str]
    scrape_delay_min: int
    scrape_delay_max: int

    @classmethod
    def from_env(cls) -> "BotConfig":
        """Load configuration from environment variables with validation.

        Returns:
            BotConfig: Validated configuration object.

        Raises:
            SystemExit: If any setting is missing or unparseable.
        """
        bluesky_handle = os.getenv("BLUESKY_HANDLE", "").strip()
        bluesky_app_password = os.getenv("BLUESKY_APP_PASSWORD", "").strip()

        if not bluesky_handle or not bluesky_app_password:
            _fail("BLUESKY_HANDLE and BLUESKY_APP_PASSWORD must be set in .env")

        log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper()
        if not hasattr(logging, log_level):
            _fail(f"LOG_LEVEL must be a logging level name, got {log_level!r}")

        scrape_delay_min = _number_env("SCRAPE_DELAY_MIN", "3", int, minimum=0)
        scrape_delay_max = _number_env("SCRAPE_DELAY_MAX", "8", int, minimum=0)
        if scrape_delay_max < scrape_delay_min:
            _fail(
                f"SCRAPE_DELAY_MAX ({scrape_delay_max}) must be at least "
                f"SCRAPE_DELAY_MIN ({scrape_delay_min})"
            )

        return cls(
            bluesky_handle=bluesky_handle,
            bluesky_app_password=bluesky_app_password,
            check_interval_minutes=_number_env(
                "CHECK_INTERVAL_MINUTES", "15", int, minimum=1
            ),
            fandoms=_list_env("FANDOMS", "Marvel,Star Wars,Disney,Anime"),
            log_level=log_level,
            test_mode=_bool_env("TEST_MODE"),
            dry_run=_bool_env("DRY_RUN"),
            funko_region=os.getenv("FUNKO_REGION", "us").strip().lower(),
            max_posts_per_check=_number_env(
                "MAX_POSTS_PER_CHECK", "0", int, minimum=0
            ),
            post_delay_seconds=_number_env("POST_DELAY_SECONDS", "0", int, minimum=0),
            scrape_pages=_list_env("SCRAPE_PAGES", "sale,new-releases,exclusives"),
            scrape_delay_min=scrape_delay_min,
            scrape_delay_max=scrape_delay_max,
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
        "%(asctime)s - %(name)s - %(levelname)s - "
        "%(funcName)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_format)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger


# Initialize configuration and logger. Bad settings exit via _fail() with a
# readable message; anything else here is a bug and should surface as one.
config = BotConfig.from_env()
logger = setup_logging(config.log_level)
logger.info("Configuration loaded successfully")
