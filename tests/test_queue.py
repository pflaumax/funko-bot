"""Tests for the pending-product queue.

Without the queue a cycle scraped five pages to publish one product and
discarded the other ~44. These pin that a scrape happens only when the
queue is genuinely dry or stale.
"""

import json
from datetime import datetime, timedelta

import pytest

import src.scheduler as scheduler
from src.scheduler import QUEUE_MAX_AGE_HOURS, load_queue, save_queue, take_products


@pytest.fixture
def queue_path(tmp_path, monkeypatch):
    path = tmp_path / "product_queue.json"
    monkeypatch.setattr(scheduler, "QUEUE_FILE", path)
    return path


class FakeScraper:
    """Records how often the network would have been hit."""

    def __init__(self, products):
        self.products = products
        self.calls = 0

    def get_new_products(self, fandoms):
        self.calls += 1
        return list(self.products)


def _products(n, start=0):
    return [{"id": f"id{i}", "name": f"Pop! {i}"} for i in range(start, start + n)]


class TestQueueFile:
    def test_missing_file_is_empty(self, queue_path):
        assert load_queue() == []

    def test_round_trip(self, queue_path):
        save_queue(_products(3))
        assert [p["id"] for p in load_queue()] == ["id0", "id1", "id2"]

    def test_stale_queue_is_discarded(self, queue_path):
        stale = datetime.now() - timedelta(hours=QUEUE_MAX_AGE_HOURS + 1)
        queue_path.write_text(
            json.dumps({"fetched_at": stale.isoformat(), "products": _products(5)})
        )
        assert load_queue() == []

    def test_fresh_queue_is_kept(self, queue_path):
        fresh = datetime.now() - timedelta(hours=QUEUE_MAX_AGE_HOURS - 1)
        queue_path.write_text(
            json.dumps({"fetched_at": fresh.isoformat(), "products": _products(5)})
        )
        assert len(load_queue()) == 5

    def test_malformed_file_is_ignored(self, queue_path):
        queue_path.write_text("{not json")
        assert load_queue() == []

    def test_unexpected_shape_is_ignored(self, queue_path):
        queue_path.write_text(json.dumps({"products": "nope"}))
        assert load_queue() == []

    def test_write_is_atomic(self, queue_path):
        save_queue(_products(2))
        assert not queue_path.with_suffix(".tmp").exists()


class TestTakeProducts:
    def test_first_call_scrapes(self, queue_path):
        scraper = FakeScraper(_products(10))
        taken = take_products(scraper, {}, count=1)

        assert scraper.calls == 1
        assert len(taken) == 1

    def test_later_calls_reuse_the_queue(self, queue_path):
        scraper = FakeScraper(_products(10))

        seen = []
        for _ in range(9):
            seen += [p["id"] for p in take_products(scraper, {}, count=1)]

        # One scrape served nine cycles, and never repeated a product.
        assert scraper.calls == 1
        assert len(set(seen)) == 9

    def test_rescrapes_once_drained(self, queue_path):
        scraper = FakeScraper(_products(2))
        take_products(scraper, {}, count=1)
        take_products(scraper, {}, count=1)
        assert scraper.calls == 1

        take_products(scraper, {}, count=1)
        assert scraper.calls == 2

    def test_already_posted_products_are_skipped(self, queue_path):
        scraper = FakeScraper(_products(3))
        posted = {"id0": {}, "id1": {}}

        taken = take_products(scraper, posted, count=5)
        assert [p["id"] for p in taken] == ["id2"]

    def test_count_zero_takes_everything(self, queue_path):
        scraper = FakeScraper(_products(4))
        assert len(take_products(scraper, {}, count=0)) == 4

    def test_empty_scrape_returns_nothing(self, queue_path):
        assert take_products(FakeScraper([]), {}, count=1) == []


class TestDryRun:
    def test_dry_run_does_not_consume_the_queue(self, queue_path, monkeypatch):
        scraper = FakeScraper(_products(5))
        take_products(scraper, {}, count=1)  # populate
        before = [p["id"] for p in load_queue()]

        monkeypatch.setattr(scheduler.config, "dry_run", True)
        take_products(scraper, {}, count=1)

        assert [p["id"] for p in load_queue()] == before


class TestRegionChange:
    """Prices are never converted, so a queue must not outlive its region."""

    def test_queue_from_another_region_is_discarded(self, queue_path, monkeypatch):
        monkeypatch.setattr(scheduler.config, "funko_region", "pl")
        save_queue(_products(5))
        assert len(load_queue()) == 5

        monkeypatch.setattr(scheduler.config, "funko_region", "us")
        assert load_queue() == []

    def test_same_region_is_kept(self, queue_path, monkeypatch):
        monkeypatch.setattr(scheduler.config, "funko_region", "us")
        save_queue(_products(3))
        assert len(load_queue()) == 3

    def test_queue_written_before_this_field_is_tolerated(self, queue_path):
        queue_path.write_text(
            json.dumps(
                {"fetched_at": datetime.now().isoformat(), "products": _products(2)}
            )
        )
        assert len(load_queue()) == 2
