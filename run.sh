#!/usr/bin/env bash
set -e

# Change directory to the script's directory
cd "$(dirname "$0")"

# Check if .env exists
if [ ! -f .env ]; then
    echo "⚠️  No .env file found! Creating one from .env.example..."
    cp .env.example .env
    echo "❗ Please edit '.env' with your BOT_TOKEN and ADMIN_IDS before starting the bot."
    exit 1
fi

# Check if venv exists, create if not
if [ ! -d "venv" ]; then
    echo "📦 Creating Python virtual environment..."
    python3 -m venv venv
    echo "⬇️  Installing required packages..."
    ./venv/bin/pip install --upgrade pip
    ./venv/bin/pip install -r requirements.txt
fi

echo "🚀 Starting Telegram Bot..."
./venv/bin/python bot.py
