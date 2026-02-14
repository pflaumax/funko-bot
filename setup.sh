#!/bin/bash
# Setup script for Funko Bluesky Bot

set -e

echo "=================================="
echo "Funko Bluesky Bot Setup"
echo "=================================="
echo ""

# Check Python version
echo "Checking Python version..."
python_version=$(python3 --version 2>&1 | awk '{print $2}')
required_version="3.10"

if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then
    echo "Error: Python 3.10 or higher is required"
    echo "Current version: $python_version"
    exit 1
fi
echo "✓ Python $python_version detected"
echo ""

# Create virtual environment
echo "Creating virtual environment..."
if [ -d "venv" ]; then
    echo "Virtual environment already exists"
else
    python3 -m venv venv
    echo "✓ Virtual environment created"
fi
echo ""

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate
echo "✓ Virtual environment activated"
echo ""

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip > /dev/null 2>&1
echo "✓ pip upgraded"
echo ""

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt
echo "✓ Dependencies installed"
echo ""

# Create .env file if it doesn't exist
if [ ! -f ".env" ]; then
    echo "Creating .env file from template..."
    cp .env.example .env
    echo "✓ .env file created"
    echo ""
    echo "⚠️  IMPORTANT: Edit .env file with your Bluesky credentials"
    echo "   Run: nano .env"
else
    echo ".env file already exists"
fi
echo ""

# Create necessary directories
echo "Creating directories..."
mkdir -p data/images
mkdir -p logs
echo "✓ Directories created"
echo ""

# Set permissions
echo "Setting permissions..."
chmod +x main.py
chmod +x setup.sh
echo "✓ Permissions set"
echo ""

echo "=================================="
echo "Setup Complete!"
echo "=================================="
echo ""
echo "Next steps:"
echo "1. Edit .env file with your credentials:"
echo "   nano .env"
echo ""
echo "2. Get Bluesky app password:"
echo "   - Go to https://bsky.app/settings"
echo "   - Navigate to App Passwords"
echo "   - Create new app password"
echo "   - Copy to .env file"
echo ""
echo "3. Run the bot:"
echo "   source venv/bin/activate"
echo "   python main.py"
echo ""
echo "4. Or run in test mode:"
echo "   python main.py --dry-run"
echo ""
echo "For more information, see README.md"
echo ""
