#!/bin/bash
# Start JARVIS
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo "Starting JARVIS v3.0..."

# Start dashboard in background
python3 -c "
import sys; sys.path.insert(0, '.')
from jarvis.dashboard.app import run_dashboard
run_dashboard()
" &
DASHBOARD_PID=$!
echo "Dashboard started at http://localhost:7000 (PID: $DASHBOARD_PID)"

# Start main JARVIS process
python3 -m jarvis.main

# Cleanup dashboard on exit
kill $DASHBOARD_PID 2>/dev/null
