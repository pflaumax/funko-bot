"""Shared test fixtures.

Credentials are injected before anything imports ``config.settings``, which
validates them at import time. Tests never reach the network.
"""

import os

os.environ.setdefault("BLUESKY_HANDLE", "test-bot.bsky.social")
os.environ.setdefault("BLUESKY_APP_PASSWORD", "test-test-test-test")

import pytest  # noqa: E402


@pytest.fixture
def scraper():
    """A scraper with no network access performed."""
    from src.scraper import FunkoScraper

    return FunkoScraper(region="pl", pages=["sale"])
