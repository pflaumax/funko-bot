#!/bin/bash
# Cleanup script for Funko Bluesky Bot

echo "=================================="
echo "Funko Bluesky Bot Cleanup"
echo "=================================="
echo ""

# Cleanup old images
if [ -d "data/images" ]; then
    echo "Cleaning up old images (older than 24 hours)..."
    find data/images -type f -mtime +1 -delete
    remaining=$(find data/images -type f | wc -l)
    echo "✓ Cleanup complete. Remaining images: $remaining"
else
    echo "⚠ Images directory not found"
fi

echo ""

# Rotate logs
if [ -f "logs/bot.log" ]; then
    log_size=$(du -h logs/bot.log | cut -f1)
    echo "Current log size: $log_size"
    
    # If log is larger than 10MB, rotate it
    if [ $(stat -f%z logs/bot.log 2>/dev/null || stat -c%s logs/bot.log) -gt 10485760 ]; then
        echo "Rotating large log file..."
        timestamp=$(date +%Y%m%d_%H%M%S)
        mv logs/bot.log "logs/bot.log.$timestamp"
        touch logs/bot.log
        echo "✓ Log rotated to bot.log.$timestamp"
    else
        echo "✓ Log size is acceptable"
    fi
else
    echo "⚠ Log file not found"
fi

echo ""

# Cleanup old posted products (older than 90 days)
if [ -f "data/posted_products.json" ]; then
    echo "Posted products database exists"
    # The bot handles this automatically, just report
    product_count=$(grep -o '"id"' data/posted_products.json | wc -l)
    echo "✓ Current products tracked: $product_count"
else
    echo "⚠ Posted products file not found"
fi

echo ""
echo "=================================="
echo "Cleanup Complete!"
echo "=================================="
