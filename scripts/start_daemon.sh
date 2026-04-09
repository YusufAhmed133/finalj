#!/bin/bash
# JARVIS daemon starter — used by LaunchAgent
# Ensures Chrome is running with CDP, then starts JARVIS

PROJECT_DIR="/Users/yusufsahmed/finalj"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
CHROME_PROFILE="$HOME/Library/Application Support/Google/Chrome-JARVIS"

cd "$PROJECT_DIR"

# Ensure Chrome is running with debugging port
if ! curl -s http://localhost:9222/json/version >/dev/null 2>&1; then
    echo "Starting Chrome with CDP..."
    mkdir -p "$CHROME_PROFILE"
    "$CHROME" --remote-debugging-port=9222 '--remote-allow-origins=*' --user-data-dir="$CHROME_PROFILE" --no-first-run --no-default-browser-check &
    sleep 5
fi

# Start JARVIS
exec python3 -u -m jarvis.main
