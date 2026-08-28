"""Tests for configuration loading.

The systemd unit is Restart=always, so a bad .env value must exit with a
readable message rather than raise — otherwise a typo becomes a restart loop.
"""

import importlib

import pytest


def _load(monkeypatch, **overrides):
    """Reload config.settings with a controlled environment."""
    base = {
        "BLUESKY_HANDLE": "bot.bsky.social",
        "BLUESKY_APP_PASSWORD": "aaaa-bbbb-cccc-dddd",
    }
    base.update(overrides)
    for key in (
        "CHECK_INTERVAL_MINUTES", "FANDOMS", "LOG_LEVEL", "TEST_MODE", "DRY_RUN",
        "FUNKO_REGION", "MAX_POSTS_PER_CHECK", "POST_DELAY_SECONDS",
        "SCRAPE_PAGES", "SCRAPE_DELAY_MIN", "SCRAPE_DELAY_MAX",
    ):
        monkeypatch.delenv(key, raising=False)
    for key, value in base.items():
        monkeypatch.setenv(key, value)

    # Patch dotenv itself: reload() re-executes `from dotenv import
    # load_dotenv`, which would rebind a patch made on config.settings back
    # to the real function and reload the developer's own .env.
    import dotenv

    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: None)

    import config.settings as settings

    return importlib.reload(settings)


class TestValidation:
    @pytest.mark.parametrize(
        "overrides",
        [
            {"CHECK_INTERVAL_MINUTES": "abc"},
            {"CHECK_INTERVAL_MINUTES": "0"},
            {"MAX_POSTS_PER_CHECK": "-1"},
            {"SCRAPE_DELAY_MIN": "not-a-number"},
            {"LOG_LEVEL": "CHATTY"},
            {"SCRAPE_PAGES": ""},
            {"BLUESKY_APP_PASSWORD": ""},
        ],
    )
    def test_bad_settings_exit_rather_than_raise(self, monkeypatch, overrides):
        with pytest.raises(SystemExit) as exc:
            _load(monkeypatch, **overrides)
        assert exc.value.code == 1

    def test_delay_range_must_be_ordered(self, monkeypatch):
        with pytest.raises(SystemExit):
            _load(monkeypatch, SCRAPE_DELAY_MIN="20", SCRAPE_DELAY_MAX="5")


class TestParsing:
    def test_defaults_load(self, monkeypatch):
        cfg = _load(monkeypatch).config
        assert cfg.check_interval_minutes == 15
        assert cfg.dry_run is False
        assert cfg.funko_region == "pl"

    def test_lists_are_split_and_trimmed(self, monkeypatch):
        cfg = _load(monkeypatch, SCRAPE_PAGES="sale, new-releases ,exclusives").config
        assert cfg.scrape_pages == ["sale", "new-releases", "exclusives"]

    def test_booleans(self, monkeypatch):
        assert _load(monkeypatch, DRY_RUN="true").config.dry_run is True
        assert _load(monkeypatch, DRY_RUN="False").config.dry_run is False
        assert _load(monkeypatch, DRY_RUN="0").config.dry_run is False

    def test_region_is_normalised(self, monkeypatch):
        assert _load(monkeypatch, FUNKO_REGION=" GB ").config.funko_region == "gb"
