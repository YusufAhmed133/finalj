# JARVIS v3.0

Personal AI operating system. Text JARVIS on Telegram. It responds, remembers, and controls your Mac.

## What it does

1. **Telegram interface** — Text a bot, get intelligent responses. Voice notes transcribed and answered.
2. **Mac control** — Says "check my calendar" and JARVIS opens Calendar and reads it back. Says "send an email" and JARVIS composes, previews, waits for approval, then sends.
3. **Memory** — Every conversation stored. Every action logged. Every pattern learned. JARVIS gets smarter over time.

## Architecture

```
Yusuf → Telegram → Orchestrator → Intelligence (Tier 1: claude.ai browser / Tier 2: API)
                       ↕                  ↕
                    Memory             Computer Use (Mac control)
                    Knowledge Scraping (Reddit, HN, GitHub, RSS)
```

## Quick Start (10 minutes)

```bash
# Clone
git clone git@github.com:YusufAhmed133/finalj.git && cd finalj

# Install
./scripts/install.sh

# Configure
# 1. Create Telegram bot: message @BotFather, get token
# 2. Edit config/secrets.env:
#    TELEGRAM_BOT_TOKEN=your_token_here

# Start
./scripts/start.sh

# Send /start to your bot on Telegram
# Copy the chat_id to TELEGRAM_OWNER_CHAT_ID in secrets.env
```

## Intelligence Tiers

**Tier 1 (default)**: JARVIS controls Chrome to interact with claude.ai. Free (uses your Claude Max subscription). Set `INTELLIGENCE_TIER=1` in secrets.env.

**Tier 2**: Direct Claude API calls. Faster and more reliable. Set `INTELLIGENCE_TIER=2` and provide `ANTHROPIC_API_KEY` in secrets.env.

## Commands

| Command | What it does |
|---------|-------------|
| `/status` | Current mode, memory count, system health |
| `/active` | Normal mode — responds to everything |
| `/focus` | Only urgent messages get through |
| `/sleep` | Only cardiac alerts and emergencies |
| `/memory <query>` | Search stored memories |
| `/briefing` | Generate morning briefing now |
| `/review` | Generate evening review now |
| `/stats` | Detailed system statistics |
| `stop` / `kill` | Halt all in-progress actions immediately |

## Permission System

Actions JARVIS takes on your Mac follow three tiers:

- **Immediate**: Open apps, navigate URLs, search web, read screen → executes, confirms after
- **Approve first**: Compose emails, fill forms, create events → sends preview, waits for YES
- **Critical**: Send emails, submit forms, financial transactions → requires YES + 10-second STOP window

## Importing Data

```bash
# Claude conversation history
./scripts/import.sh claude ~/Downloads/conversations.json

# Google Calendar
./scripts/import.sh calendar ~/Downloads/calendar.ics

# Any document (PDF, CSV, JSON, TXT, MD)
./scripts/import.sh file ~/Documents/notes.pdf

# All files in a directory
./scripts/import.sh directory data/imports/raw/
```

## Dashboard

Admin panel at `http://localhost:7000` — memory stats, search, entity graph, action log.

## 24/7 Operation

```bash
# Install LaunchAgent (auto-starts on boot, auto-restarts on crash)
cp launchagents/com.yusuf.jarvis.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.yusuf.jarvis.plist

# Check status
launchctl list | grep jarvis

# Stop
launchctl unload ~/Library/LaunchAgents/com.yusuf.jarvis.plist
```

## Project Structure

```
finalj/
├── jarvis/
│   ├── main.py              # Entry point
│   ├── orchestrator/        # Core loop, priority, briefings
│   ├── agents/              # Telegram, computer use, knowledge scraping
│   ├── brain/               # Intelligence (browser + API)
│   ├── memory/              # SQLite + FTS5 + vectors + entity graph
│   ├── importers/           # Claude, Calendar, PDF, CSV, JSON, TXT
│   ├── identity/            # Yusuf's profile (always in context)
│   ├── dashboard/           # FastAPI admin panel
│   └── utils/               # Logger, crypto, scheduler
├── data/                    # Runtime data (gitignored)
├── research/                # Component research and debates
├── config/                  # agents.yaml + secrets.env
├── scripts/                 # install, start, stop, import
├── launchagents/            # macOS auto-start
└── tests/                   # Component tests
```

## Development

```bash
# Run tests
python3 tests/test_memory.py
python3 tests/test_importers.py
python3 tests/test_brain.py
python3 tests/test_orchestrator.py
python3 tests/test_telegram.py
python3 tests/test_computer.py
python3 tests/test_knowledge.py

# CLI mode (no Telegram needed)
python3 -m jarvis.main --cli
```
