#!/bin/bash
# Import data into JARVIS memory
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

if [ $# -lt 2 ]; then
    echo "Usage: ./scripts/import.sh <type> <path>"
    echo ""
    echo "Types:"
    echo "  claude     - Claude.ai conversation export (conversations.json)"
    echo "  calendar   - Google Calendar export (.ics)"
    echo "  file       - Any supported file (PDF, CSV, JSON, TXT, MD)"
    echo "  directory  - All supported files in a directory"
    echo ""
    echo "Examples:"
    echo "  ./scripts/import.sh claude ~/Downloads/conversations.json"
    echo "  ./scripts/import.sh calendar ~/Downloads/calendar.ics"
    echo "  ./scripts/import.sh directory data/imports/raw/"
    exit 1
fi

python3 -m jarvis.importers.run "$@"
