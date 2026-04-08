#!/bin/bash
# JARVIS Installation Script
# Gets a fresh Mac to working JARVIS in under 10 minutes

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "================================"
echo "JARVIS v3.0 Installation"
echo "================================"

# 1. Check prerequisites
echo ""
echo "[1/7] Checking prerequisites..."

if ! command -v python3 &>/dev/null; then
    echo "ERROR: Python 3 not found. Install with: brew install python3"
    exit 1
fi

if ! command -v brew &>/dev/null; then
    echo "ERROR: Homebrew not found. Install from https://brew.sh"
    exit 1
fi

echo "  Python: $(python3 --version)"
echo "  Brew: $(brew --version | head -1)"

# 2. Install system dependencies
echo ""
echo "[2/7] Installing system dependencies..."

brew install node ffmpeg tesseract 2>/dev/null || echo "  (some already installed)"

# 3. Install Python dependencies
echo ""
echo "[3/7] Installing Python dependencies..."

pip3 install -r "$PROJECT_DIR/requirements.txt" --quiet

# 4. Install Playwright browsers
echo ""
echo "[4/7] Installing Playwright Chromium..."

python3 -m playwright install chromium

# 5. Pull Ollama embedding model
echo ""
echo "[5/7] Pulling Ollama embedding model..."

if command -v ollama &>/dev/null; then
    ollama pull nomic-embed-text 2>/dev/null || echo "  (Ollama not running — start with: ollama serve)"
else
    echo "  Ollama not installed. Install from: https://ollama.ai"
    echo "  Then run: ollama pull nomic-embed-text"
fi

# 6. Create data directories
echo ""
echo "[6/7] Creating data directories..."

mkdir -p "$PROJECT_DIR/data/"{whatsapp_session,claude_session,imports/{raw,processed},logs/computer_actions}

# 7. Check configuration
echo ""
echo "[7/7] Checking configuration..."

if [ ! -f "$PROJECT_DIR/config/secrets.env" ]; then
    echo "  Creating config/secrets.env template..."
    cat > "$PROJECT_DIR/config/secrets.env" << 'ENVEOF'
# JARVIS Secrets
INTELLIGENCE_TIER=1
ANTHROPIC_API_KEY=
TELEGRAM_BOT_TOKEN=
TELEGRAM_OWNER_CHAT_ID=
REDDIT_CLIENT_ID=
REDDIT_CLIENT_SECRET=
REDDIT_USER_AGENT=jarvis/3.0
BRAVE_API_KEY=
FERNET_KEY=
ENVEOF
fi

echo ""
echo "================================"
echo "Installation complete!"
echo "================================"
echo ""
echo "Next steps:"
echo "  1. Create a Telegram bot: message @BotFather on Telegram, get a token"
echo "  2. Add the token to config/secrets.env: TELEGRAM_BOT_TOKEN=your_token"
echo "  3. Start JARVIS: ./scripts/start.sh"
echo "  4. Send /start to your bot on Telegram"
echo "  5. Copy the chat_id from the response to TELEGRAM_OWNER_CHAT_ID in secrets.env"
echo ""
echo "For CLI testing (no Telegram needed):"
echo "  python3 -m jarvis.main --cli"
echo ""
echo "For API mode (Tier 2), add ANTHROPIC_API_KEY to secrets.env"
echo "  and set INTELLIGENCE_TIER=2"
