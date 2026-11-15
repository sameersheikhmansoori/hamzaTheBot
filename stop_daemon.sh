#!/usr/bin/env bash
# stop_daemon.sh - Stop Telegram Bot daemon

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PID_FILE="$SCRIPT_DIR/bot.pid"

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    echo "🛑 Stopping daemon PID $PID..."
    kill "$PID" 2>/dev/null || true
    rm -f "$PID_FILE"
fi

# Stop any running python bot.py processes
PIDS=$(pgrep -f "python.*bot\.py" || true)
if [ -n "$PIDS" ]; then
    echo "🛑 Stopping bot process(es): $PIDS..."
    kill $PIDS 2>/dev/null || true
    sleep 1
    kill -9 $PIDS 2>/dev/null || true
fi

echo "✅ Bot stopped."
