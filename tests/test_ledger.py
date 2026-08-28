"""Tests for the posted-products ledger.

The ledger is the only persistent state; losing or mis-keying it means the
bot reposts its back catalogue to a public feed, so its failure modes are
pinned here.
"""

import json

import pytest

import src.scheduler as scheduler
from src.scheduler import (
    MAX_POSTED_ENTRIES,
    load_posted_products,
    save_posted_products,
)


@pytest.fixture
def ledger_path(tmp_path, monkeypatch):
    """Point the ledger at a temp file for the duration of a test."""
    path = tmp_path / "posted_products.json"
    monkeypatch.setattr(scheduler, "POSTED_PRODUCTS_FILE", path)
    return path


def _entry(name, posted_at="2026-08-01T00:00:00"):
    return {"name": name, "posted_at": posted_at, "price": 1.0}


class TestMigration:
    """Entries predate the product-name fix and must survive it."""

    def test_old_keys_are_rekeyed_to_clean_names(self, ledger_path):
        ledger_path.write_text(
            json.dumps({"deadbeefdeadbeef": _entry("Pop! Fuecoco, , hi-res view 1")})
        )
        loaded = load_posted_products()

        assert "deadbeefdeadbeef" not in loaded
        key = scheduler.product_key("Pop! Fuecoco")
        assert key in loaded
        assert loaded[key]["name"] == "Pop! Fuecoco"

    def test_a_freshly_scraped_name_matches_migrated_history(self, ledger_path):
        ledger_path.write_text(
            json.dumps({"oldkey0000000000": _entry("Pop! Fuecoco, , hi-res view 1")})
        )
        loaded = load_posted_products()

        # What the scraper will produce on the next cycle:
        assert scheduler.product_key("Pop! Fuecoco") in loaded

    def test_migration_is_idempotent(self, ledger_path):
        ledger_path.write_text(
            json.dumps({"oldkey0000000000": _entry("Pop! Fuecoco, , hi-res view 1")})
        )
        first = load_posted_products()
        save_posted_products(first)
        assert load_posted_products() == first


class TestCorruptFile:
    """A truncated or hand-broken file must not cost the whole history."""

    def test_truncated_json_is_quarantined_not_overwritten(self, ledger_path):
        ledger_path.write_text('{"a": {"name": "Pop! X"')  # truncated
        assert load_posted_products() == {}

        assert not ledger_path.exists()
        backups = list(ledger_path.parent.glob("*.corrupt-*.json"))
        assert len(backups) == 1

    def test_non_object_is_rejected(self, ledger_path):
        ledger_path.write_text("[1, 2, 3]")
        assert load_posted_products() == {}

    def test_missing_file_starts_empty(self, ledger_path):
        assert load_posted_products() == {}

    def test_entries_without_names_are_kept(self, ledger_path):
        ledger_path.write_text(json.dumps({"somekey": {"posted_at": "x"}}))
        assert "somekey" in load_posted_products()


class TestSave:
    def test_write_is_atomic(self, ledger_path):
        save_posted_products({"k": _entry("Pop! X")})
        assert ledger_path.exists()
        assert not ledger_path.with_suffix(".tmp").exists()
        assert json.loads(ledger_path.read_text())["k"]["name"] == "Pop! X"

    def test_ring_buffer_drops_oldest_first(self, ledger_path):
        products = {
            f"key{i:013d}": _entry(f"Pop! {i}", posted_at=f"2026-01-01T00:{i:04d}")
            for i in range(MAX_POSTED_ENTRIES + 10)
        }
        save_posted_products(products)

        saved = json.loads(ledger_path.read_text())
        assert len(saved) == MAX_POSTED_ENTRIES
        assert "key0000000000000" not in saved       # oldest dropped
        assert f"key{MAX_POSTED_ENTRIES + 9:013d}" in saved  # newest kept

    def test_under_the_cap_nothing_is_dropped(self, ledger_path):
        save_posted_products({f"k{i}": _entry(f"Pop! {i}") for i in range(50)})
        assert len(json.loads(ledger_path.read_text())) == 50
