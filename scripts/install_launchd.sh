#!/bin/bash
# Install JARVIS LaunchAgent for 24/7 operation
set -e

PLIST_SRC="/Users/yusufsahmed/finalj/launchagents/com.yusuf.jarvis.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.yusuf.jarvis.plist"

echo "Installing JARVIS LaunchAgent..."

# Unload if already loaded
launchctl unload "$PLIST_DST" 2>/dev/null || true

# Copy plist
cp "$PLIST_SRC" "$PLIST_DST"

# Ensure log directory exists
mkdir -p /Users/yusufsahmed/finalj/data/logs

# Load
launchctl load "$PLIST_DST"

echo "JARVIS LaunchAgent installed and loaded."
echo "Check status: launchctl list | grep jarvis"
echo "Logs: tail -f /Users/yusufsahmed/finalj/data/logs/jarvis_launchd.log"
echo ""
echo "To uninstall: launchctl unload ~/Library/LaunchAgents/com.yusuf.jarvis.plist"
