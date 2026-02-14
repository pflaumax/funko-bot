# Funko Pop Bluesky Bot

Automated Bluesky bot that monitors Funko.com for new products, sales, and restocks, then posts updates with images to your Bluesky account.

## Features

- Scrapes multiple Funko.com pages (sales, new releases, back in stock, exclusives, best sellers)
- Posts product updates with high-quality images to Bluesky
- Automatic fandom filtering (excludes sports leagues, Disney, etc.)
- Configurable posting schedule and rate limiting
- Multi-region support (EUR, GBP, USD)
- Automatic image cleanup and log rotation
- Duplicate detection to avoid reposting

## Requirements

- Python 3.10 or higher
- Bluesky account with app password
- 500MB+ free disk space

## Quick Setup

### 1. Clone Repository

```bash
git clone https://github.com/yourusername/funko-bluesky-bot.git
cd funko-bluesky-bot
```

### 2. Run Setup Script

```bash
chmod +x setup.sh
./setup.sh
```

This will:
- Create virtual environment
- Install dependencies
- Create `.env` file from template
- Set up required directories

### 3. Configure Bot

Edit `.env` file with your credentials:

```bash
nano .env
```

Required settings:
```env
BLUESKY_HANDLE=your-bot-handle.bsky.social
BLUESKY_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
FUNKO_REGION=pl
SCRAPE_PAGES=sale,new-releases,back-in-stock,exclusives,best-selling
```

Get your Bluesky app password:
1. Go to https://bsky.app/settings
2. Navigate to "App Passwords"
3. Click "Add App Password"
4. Copy the generated password to `.env`

### 4. Run Bot

```bash
source venv/bin/activate
python main.py
```

Test mode (no actual posts):
```bash
python main.py --dry-run
```

Single post test:
```bash
python test_single_post.py
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `BLUESKY_HANDLE` | Your bot's Bluesky handle | Required |
| `BLUESKY_APP_PASSWORD` | App password from Bluesky | Required |
| `CHECK_INTERVAL_MINUTES` | Minutes between checks | 180 |
| `FUNKO_REGION` | Region code (pl, gb, us) | pl |
| `SCRAPE_PAGES` | Pages to scrape (comma-separated) | sale,new-releases,back-in-stock,exclusives,best-selling |
| `MAX_POSTS_PER_CHECK` | Max posts per cycle (0=unlimited) | 1 |
| `FANDOMS` | Fandoms to include (All or comma-separated) | All |
| `LOG_LEVEL` | Logging level (INFO, DEBUG) | INFO |

### Posting Schedule

Default configuration posts 1 product every 3 hours (8 posts/day):
- Scrapes ~100 products from 5 pages
- Filters out unwanted fandoms (MLB, NBA, NFL, NHL, Disney)
- Results in ~84 unique products
- Complete cycle every ~10 days

## Deployment

### Raspberry Pi (Systemd Service)

1. Edit service file with your paths:
```bash
nano funko-bot.service
```

2. Update these lines:
```ini
User=your-username
WorkingDirectory=/path/to/funko-bluesky-bot
Environment="PATH=/path/to/funko-bluesky-bot/venv/bin"
ExecStart=/path/to/funko-bluesky-bot/venv/bin/python main.py
ReadWritePaths=/path/to/funko-bluesky-bot/data /path/to/funko-bluesky-bot/logs
```

3. Install and start service:
```bash
sudo cp funko-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable funko-bot
sudo systemctl start funko-bot
```

4. Check status:
```bash
sudo systemctl status funko-bot
sudo journalctl -u funko-bot -f
```

### Docker

Build and run:
```bash
docker-compose up -d
```

View logs:
```bash
docker-compose logs -f
```

Stop:
```bash
docker-compose down
```

## Project Structure

```
funko-bluesky-bot/
├── config/
│   └── settings.py          # Configuration management
├── data/
│   ├── images/              # Temporary image storage
│   └── posted_products.json # Posted products tracking
├── logs/
│   └── bot.log              # Application logs
├── scripts/
│   ├── cleanup.sh           # Cleanup old files
│   └── monitor.sh           # Monitor bot status
├── src/
│   ├── bot.py               # Bluesky API client
│   ├── scraper.py           # Funko.com scraper
│   ├── image_handler.py     # Image processing
│   └── scheduler.py         # Job scheduling
├── tests/
│   ├── test_scraper.py      # Unit tests
│   └── test_image_handler.py
├── .env                     # Configuration (not in git)
├── .env.example             # Configuration template
├── main.py                  # Entry point
├── test_single_post.py      # E2E test script
└── requirements.txt         # Python dependencies
```

## Maintenance

### Manual Cleanup

```bash
bash scripts/cleanup.sh
```

Removes:
- Images older than 24 hours
- Rotates logs larger than 10MB

### Monitor Status

```bash
bash scripts/monitor.sh
```

Shows:
- Bot running status
- Recent errors/warnings
- Disk usage
- Posted products count

### View Logs

```bash
tail -f logs/bot.log
```

## License

MIT License 
