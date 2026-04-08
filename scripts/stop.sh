#!/bin/bash
# Stop JARVIS
echo "Stopping JARVIS..."

# Find and kill JARVIS processes
pkill -f "jarvis.main" 2>/dev/null
pkill -f "jarvis.dashboard" 2>/dev/null
pkill -f "uvicorn.*7000" 2>/dev/null

echo "JARVIS stopped."
