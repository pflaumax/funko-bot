# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

A Python bot that scrapes funko.com product listings and posts them to Bluesky on a schedule. It runs live on a Raspberry Pi under systemd as `funko-bot.service`.

## Commands

The repo has a `.venv/` (Python 3.13); `setup.sh` and the README create `venv/`, which is what the Pi uses. Dev tools live in `requirements-dev.txt`, not `requirements.txt`.

```bash
source .venv/bin/activate

python main.py                  # scheduler loop (checks immediately, then every CHECK_INTERVAL_MINUTES)
python main.py --once           # single check cycle, then exit
python main.py --dry-run        # scrape + log, no posting, queue left untouched
python main.py --log-level DEBUG

python -m pytest -q             # 79 tests, all passing
python -m pytest tests/test_queue.py::TestTakeProducts -v   # one class
python -m ruff check . --exclude .venv,.mypy_cache          # clean
```

Overriding env vars on the command line is the fast way to exercise one page without waiting on the anti-detection delays:

```bash
SCRAPE_DELAY_MIN=1 SCRAPE_DELAY_MAX=2 SCRAPE_PAGES=best-selling python main.py --once --dry-run
```

Ops scripts: `bash scripts/cleanup.sh`, `bash scripts/monitor.sh`.

## Deployment

The Pi is reached through the SSH alias `pi` (user `reiberry`, key-based) — run remote commands as `ssh pi "..."`.

| | |
|---|---|
| Checkout | `/home/reiberry/personal/funko-bot` |
| Virtualenv | `venv/` (not `.venv/`) |
| Service | `funko-bot.service`, `Restart=always` |
| Remote | `github` → `git@github.com:pflaumax/funko-bot.git` |

Deploy is `git pull` + `sudo systemctl restart funko-bot`. `.env` is gitignored and lives only on the Pi, so new settings must be added there by hand. A restart runs a check immediately, and unless `DRY_RUN=true` that is a real public post.

Day-to-day commands on the Pi, run from `~/personal/funko-bot`:

```bash
sudo systemctl status funko-bot             # also: start | stop | restart | enable | disable
sudo journalctl -u funko-bot -f             # live; -n 100 for the last 100 lines
tail -f logs/bot.log                        # the app's own log file
git pull && sudo systemctl restart funko-bot                      # deploy
sudo systemctl daemon-reload && sudo systemctl restart funko-bot  # after editing /etc/systemd/system/funko-bot.service
venv/bin/python main.py --dry-run --once    # one cycle, nothing posted; without --dry-run it posts
nano .env && sudo systemctl restart funko-bot                     # change a setting
```

The Pi tracks `main`. `development`, GitHub's default branch, is older (6 commits behind `main` on 2026-10-26), so never check it out there.

**Never delete `data/posted_products.json` to "start fresh".** It is the dedup history; without it the bot reposts the whole back catalogue to the public feed, one product per cycle. Images older than 24h are pruned after every cycle, so `data/images/` needs no manual cleanup.

## Architecture

Data flows one way: `scraper` → `scheduler` → (`image_handler`, `post_formatter`, `bot`).

- `config/settings.py` — loads `.env` into a `BotConfig` dataclass **at import time** as a module-level singleton `config`, and creates `data/`, `data/images/`, `logs/`. Also exports the shared `logger`. Every module imports `config` from here rather than being passed settings; `main.py` mutates `config.test_mode` / `config.dry_run` from CLI flags.
- `src/scraper.py` — `FunkoScraper` fetches `funko.com/{region}/new-featured/{page_type}/` for each page in `SCRAPE_PAGES`, parses `div.product-tile`, de-duplicates across pages, and shuffles so posts mix page types.
- `src/scheduler.py` — orchestration plus both JSON ledgers. Uses the `schedule` library with a module-global `shutdown_requested` flag and SIGINT/SIGTERM handlers.
- `src/post_formatter.py` — post text and hashtags. Owns the house style; kept out of the scheduler so wording can be changed and tested without touching the posting loop.
- `src/image_handler.py` — downloads the main and alt product images, re-encodes them, generates alt text, prunes images older than 24h after each cycle.
- `src/bot.py` — `FunkoBlueskyBot` wraps atproto `Client`. Login, blob upload, and posting each retry 3× with exponential backoff. Builds richtext facets for URLs and hashtags manually, in **byte** offsets (not character offsets), and truncates text at 300 chars.

### Product identity is the name, not the URL

`product_key()` in `src/scraper.py` hashes the cleaned, casefolded product name. That looks odd — a URL is the more natural key — but the posted-products ledger has only ever recorded names, so a name is the one scheme the existing history could be migrated to. Names carry their variant in parentheses ("Pop! Doflamingo (Flocked)"), so they are unique in practice.

Changing how a name is derived therefore **invalidates the entire dedup history** and reposts the back catalogue to a public feed. This already happened once in the making: image `alt` attributes carry a CDN suffix (`"Pop! Fuecoco, , hi-res view 1"`), which went into 461 live posts before the name moved to `div.product-name`. `_migrate_keys()` in the scheduler re-keys old entries on load and is what made that fix safe; `tests/test_ledger.py` pins it.

### Storefronts and currency

`FUNKO_REGION` picks which storefront is scraped, and that alone decides the currency of the posted price. **Nothing is ever converted** — the price posted is the price that storefront charges, read off the page. The default is `us` (USD).

Three things differ between storefronts and all three are handled in `src/scraper.py`:

- **URL shape.** The US store is the site root and takes no locale segment (`funko.com/new-featured/…`); `/us/new-featured/` 404s. `US_REGIONS` covers both `"us"` and `""`.
- **Page slugs.** The US store calls one page `best-sellers` where the EU stores call it `best-selling`. `SCRAPE_PAGES` and the stored `page_type` keep the canonical EU name so `post_formatter.PAGE_STYLES` stays region-independent; only the URL is translated, via `_page_slug()`.
- **Tile markup.** EU tiles carry `div.product-name`; US tiles only `.pdp-link`. `_parse_tile` walks a cascade ending at the image `alt`, which always needs `clean_product_name()`.

Currency is read from the rendered symbol (`$14.99`, `€ 23,00`) rather than assumed, because the price markup has no structured currency field — `REGION_CURRENCY_MAP` is only the fallback.

Switching regions is safe for dedup: `product_key()` hashes the name, and names are identical across storefronts, so products already posted stay suppressed. It is *not* safe for a queue already on disk, so `data/product_queue.json` records its region and is discarded when that changes — otherwise dollar prices would go out labelled as euros until the queue drained.

`div.product-availability` is no longer rendered on either storefront, so coming-soon status comes from the `product-flag` badge instead. The parser still reads the old element when present, because it is the only source of a drop date.

### Cloudflare handling

The scraper uses `curl_cffi` with `impersonate="chrome131"` (it previously used `cloudscraper`, which stopped working). On top of that: a fixed 2s `RATE_LIMIT_DELAY`, a random `SCRAPE_DELAY_MIN`–`SCRAPE_DELAY_MAX` sleep before every fetch, and on HTTP 403 one retry after 2–3× `SCRAPE_DELAY_MAX`.

**The exception types in `_fetch_page` must come from `curl_cffi`, not `requests`.** `curl_cffi.requests.exceptions.HTTPError` descends from `OSError`, not from `requests.exceptions.HTTPError`, so catching the `requests` ones silently disables every retry — the exception escapes to the outer `except Exception` in `get_new_products` and the 403 path never runs. That was live for months after the cloudscraper swap, visible only as "Cloudflare blocked" disappearing from the logs while 403s kept arriving.

If the site starts blocking again, raise the env delays before touching the fetch logic.

### State: two ledgers, both atomic

Both are written via `_write_json()` (tmp file + rename) because a power cut on an SD card must not leave a truncated file behind.

- `data/posted_products.json` — dedup, keyed as above. A **2000-entry ring buffer**, trimmed oldest-first. It used to be trimmed by a 90-day cutoff instead, which dropped ~37 entries per cycle and quietly queued those products up to be posted again. An unreadable file is renamed to `.corrupt-<timestamp>.json` rather than overwritten, because silently treating it as "nothing posted" reposts everything.
- `data/product_queue.json` — products scraped and not yet posted, with a `fetched_at` stamp and a 24h TTL. `take_products()` scrapes **only when this is empty or stale**. Without it a cycle fetched five pages, spent ~4 minutes in anti-detection delays, posted one product and discarded the other ~44 — which was also most of what was drawing the 403s. A dry run deliberately does not consume it.

### Config must not be able to loop the boot

The systemd unit is `Restart=always`, so anything that raises while `config/settings.py` is imported becomes a restart loop rather than a visible failure. Every setting goes through `_number_env` / `_bool_env` / `_list_env`, which report the offending value and `sys.exit(1)`. `tests/test_config.py` covers it. Note the tests patch `dotenv.load_dotenv` itself, not `config.settings.load_dotenv`: `importlib.reload` re-executes the `from dotenv import ...` line and would otherwise rebind the real function and read the developer's own `.env`.

### Images are always re-encoded

`resize_image()` re-encodes every image to JPEG, not just oversized ones, stepping quality 95→40 until under `MAX_UPLOAD_BYTES`. Funko serves 800×800 PNGs, which sat below the resize threshold and were uploaded byte-for-byte under a `.jpg` filename — ~590KB of PNG where JPEG costs under a tenth of that. Transparency is flattened onto white, since product shots are cut out on alpha and JPEG has no alpha channel.

`cleanup_old_images()` skips dotfiles; it used to delete `data/images/.gitkeep` out of the repo.

## Conventions

- Google-style docstrings on every function/class; module-level logger named `funko_bot.<module>`.
- Failures degrade rather than raise: parse errors, image failures, and post failures are logged and the loop continues. `ruff.toml` ignores `BLE001` for this reason, and `G004` because f-strings in log calls are the established style.
- Post text is assembled in `post_formatter.format_post_text` from a headline table (`PAGE_STYLES`) plus `_classify()`. Precedence is availability → discount → page type. Adding a new page type means adding both a `SCRAPE_PAGES` value and a `PAGE_STYLES` entry.
- The default headline puts the fandom before the status (`🏷️ [X] Funko Pop`) while every other one puts it after (`🔥 BEST SELLER [X]`). That asymmetry is inherited and deliberate — the feed already reads that way.
- `filter_by_fandom` applies `EXCLUDED_FANDOMS` (sports leagues, Disney) *before* the `FANDOMS` allowlist, so `FANDOMS=All` still excludes those. `tests/test_scraper.py` pins it.
- Hashtags upper only the first letter of each word rather than using `str.capitalize()`, which would lowercase the rest and produce `#Spiderman` and `#Dc`.
