#!/usr/bin/env bash
# start_daemon.sh - Run Telegram Bot in background with auto-restart

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PID_FILE="$SCRIPT_DIR/bot.pid"
LOG_FILE="$SCRIPT_DIR/bot.log"

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "⚠️ Bot is already running with PID $PID"
        exit 0
    else
        rm -f "$PID_FILE"
    fi
fi

# Also check for any orphaned python bot.py processes
ORPHANS=$(pgrep -f "python.*bot\.py" || true)
if [ -n "$ORPHANS" ]; then
    echo "⚠️ Found running bot instance (PID $ORPHANS). Stopping it first..."
    kill $ORPHANS 2>/dev/null || true
    sleep 1
fi

echo "🚀 Starting Telegram Bot daemon with auto-restart..."

# Background supervisor loop
nohup bash -c '
    while true; do
        echo "[$(date "+%Y-%m-%d %H:%M:%S")] Starting bot.py..." >> "'"$LOG_FILE"'"
        ./venv/bin/python bot.py >> "'"$LOG_FILE"'" 2>&1
        EXIT_CODE=$?
        echo "[$(date "+%Y-%m-%d %H:%M:%S")] bot.py exited with code $EXIT_CODE. Restarting in 3 seconds..." >> "'"$LOG_FILE"'"
        sleep 3
    done
' > /dev/null 2>&1 &

DAEMON_PID=$!
echo $DAEMON_PID > "$PID_FILE"

echo "✅ Bot started successfully in background! (PID: $DAEMON_PID)"
echo "📄 Logs: tail -f bot.log"
echo "🛑 To stop: ./stop_daemon.sh"
