#!/bin/bash
# Monitoring script for Funko Bluesky Bot

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=================================="
echo "Funko Bluesky Bot Monitor"
echo "=================================="
echo ""

# Check if bot is running
check_process() {
    if pgrep -f "python.*main.py" > /dev/null; then
        echo -e "${GREEN}✓${NC} Bot is running"
        echo "  PID: $(pgrep -f 'python.*main.py')"
        return 0
    else
        echo -e "${RED}✗${NC} Bot is not running"
        return 1
    fi
}

# Check systemd service
check_service() {
    if systemctl is-active --quiet funko-bot 2>/dev/null; then
        echo -e "${GREEN}✓${NC} Service is active"
        systemctl status funko-bot --no-pager | grep "Active:"
    else
        echo -e "${YELLOW}⚠${NC} Service not found or inactive"
    fi
}

# Check Docker container
check_docker() {
    if docker ps | grep -q funko-bot; then
        echo -e "${GREEN}✓${NC} Docker container is running"
        docker ps | grep funko-bot
    else
        echo -e "${YELLOW}⚠${NC} Docker container not found"
    fi
}

# Check logs for errors
check_logs() {
    if [ -f "logs/bot.log" ]; then
        error_count=$(grep -c "ERROR" logs/bot.log 2>/dev/null || echo "0")
        warning_count=$(grep -c "WARNING" logs/bot.log 2>/dev/null || echo "0")
        
        echo ""
        echo "Log Statistics:"
        echo "  Errors: $error_count"
        echo "  Warnings: $warning_count"
        
        if [ "$error_count" -gt 0 ]; then
            echo ""
            echo "Recent errors:"
            grep "ERROR" logs/bot.log | tail -n 3
        fi
    else
        echo -e "${YELLOW}⚠${NC} Log file not found"
    fi
}

# Check disk space
check_disk() {
    echo ""
    echo "Disk Usage:"
    
    if [ -d "data/images" ]; then
        image_size=$(du -sh data/images 2>/dev/null | cut -f1)
        image_count=$(find data/images -type f 2>/dev/null | wc -l)
        echo "  Images: $image_size ($image_count files)"
    fi
    
    if [ -d "logs" ]; then
        log_size=$(du -sh logs 2>/dev/null | cut -f1)
        echo "  Logs: $log_size"
    fi
}

# Check posted products
check_posted() {
    if [ -f "data/posted_products.json" ]; then
        product_count=$(grep -o '"id"' data/posted_products.json | wc -l)
        echo ""
        echo "Posted Products: $product_count"
    fi
}

# Main monitoring
echo "Process Status:"
check_process
process_running=$?

echo ""
echo "Service Status:"
check_service

echo ""
echo "Docker Status:"
check_docker

check_logs
check_disk
check_posted

echo ""
echo "=================================="

# Exit with process status
exit $process_running
