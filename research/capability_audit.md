# JARVIS Capability Audit — Full System Inventory & Decisions

**Date:** 2026-04-08
**Machine:** MacBook Air M2, macOS Darwin 25.2.0 (Tahoe)
**User:** yusufsahmed

---

## 1. System Inventory

### Runtimes & Languages
| Tool | Version | Path | Status |
|------|---------|------|--------|
| Python | 3.9.6 | /usr/bin/python3 | System Python (Xcode CLI tools) |
| Bun | 1.3.11 | /opt/homebrew/bin/bun | Installed |
| Go | 1.26.1 | /opt/homebrew/bin/go | Installed |
| Rust | 1.94.1 | Homebrew | Installed |
| Node.js | NOT INSTALLED | — | NEEDS INSTALL (brew install node) |
| Ollama | 0.20.3 | ~/.local/bin/ollama | Installed |

### CLI Tools
| Tool | Status |
|------|--------|
| git | Installed (/usr/bin/git) |
| gh (GitHub CLI) | Installed (/opt/homebrew/bin/gh) |
| curl | Installed (/usr/bin/curl) |
| wget | Installed (/opt/homebrew/bin/wget) |
| jq | Installed (/usr/bin/jq) |
| brew | Installed (/opt/homebrew/bin/brew) |
| ffmpeg | NOT INSTALLED — NEEDS INSTALL |
| tesseract | NOT INSTALLED — NEEDS INSTALL |
| npm/npx | NOT INSTALLED (depends on Node.js) |

### Python Packages (Pre-existing)
beautifulsoup4, fastapi, flask, httpx, lxml, praw, pydantic, pyyaml, requests, rich, uvicorn, websocket-client

### Python Packages (Newly Installed for JARVIS)
playwright, python-telegram-bot, faster-whisper, anthropic, aiohttp, apscheduler, cryptography, sqlite-vec, pdfplumber, icalendar, feedparser, Pillow, numpy

### Chromium (Playwright)
Installed at ~/Library/Caches/ms-playwright/chromium_headless_shell-1208 (v145.0.7632.6)

### Homebrew Packages (Selected)
bun, curl, dotnet, fzf, gh, git, go, htop, jq, llvm, lua, openssl, pyenv, python@3.14, ripgrep, ruby, rust, sqlite, starship, supabase, tmux, tree, uv, wget

### Brew Casks
cursor, docker-desktop, visual-studio-code

---

## 2. Existing Configuration

### Claude Code Settings (~/.claude/settings.json)
- Previous: dead jarv MCP server pointing to /Users/yusufsahmed/Downloads/jarv
- Updated: macOS automator MCP server configured

### Claude Desktop (~/Library/Application Support/Claude/)
- Desktop app installed and configured
- Preferences: cowork scheduled tasks, web search, bypass permissions mode, launch preview persist session all enabled
- MCP config: core_brain HTTP server (external)

### Claude Code Built-in Capabilities
Already available WITHOUT any MCP servers:
- **File ops**: Read, Write, Edit, Glob, Grep
- **Shell**: Bash (with timeout and background support)
- **Web**: WebSearch, WebFetch
- **Gmail**: gmail_create_draft, gmail_get_profile, gmail_list_drafts, gmail_list_labels, gmail_read_message, gmail_read_thread, gmail_search_messages
- **Google Calendar**: gcal_create_event, gcal_delete_event, gcal_find_meeting_times, gcal_find_my_free_time, gcal_get_event, gcal_list_calendars, gcal_list_events, gcal_respond_to_event, gcal_update_event

### Environment Variables
No API keys found in environment. All secrets will go in config/secrets.env.

---

## 3. MCP Server Decisions

Full debate in: research/mcp_servers_debate.md

### INSTALLED
| Server | Purpose | Config |
|--------|---------|--------|
| @steipete/macos-automator-mcp | 200+ AppleScript/JXA macOS automation recipes | bunx in settings.json |

### REJECTED (with reason)
| Server | Reason |
|--------|--------|
| filesystem | Redundant with Read/Write/Edit/Glob/Grep |
| memory | JARVIS builds custom memory spine (SQLite+FTS5+vectors) |
| playwright MCP | Using playwright Python library directly instead |
| desktop-commander | Redundant with Bash tool |
| brave-search | Redundant with WebSearch tool |
| fetch | Redundant with WebFetch tool |
| sqlite MCP | Use sqlite3 CLI via Bash |
| github MCP | Use gh CLI via Bash |
| puppeteer | Deprecated, replaced by Playwright |
| screenshot | Computer Use API + screencapture covers this |
| macos-control | Computer Use API is better |
| sequential-thinking | Claude's native reasoning is sufficient |
| browser-use MCP | Too opinionated, using Playwright directly |

### DEFERRED
| Server | Condition |
|--------|-----------|
| notion | Only if Yusuf uses Notion |
| spotify MCP | Only if advanced music control needed (basic via AppleScript) |
| context7 | Install during active development if needed |

### ALREADY AVAILABLE (no install needed)
| Capability | Source |
|------------|--------|
| Gmail | Built-in Claude Code MCP |
| Google Calendar | Built-in Claude Code MCP |
| Web Search | Built-in WebSearch tool |
| URL Fetching | Built-in WebFetch tool |
| File Operations | Built-in Read/Write/Edit/Glob/Grep |
| Shell Execution | Built-in Bash tool |
| GitHub | gh CLI |

---

## 4. Browser Automation Decision

Full debate in: research/browser_automation_debate.md

### Winner: Playwright Python API via connect_over_cdp()

**Architecture:**
- Launch Chrome with `--remote-debugging-port=9222` (preserves user's real Chrome profile with Claude Max session)
- Connect Playwright to it: `playwright.chromium.connect_over_cdp("http://localhost:9222")`
- Interact with claude.ai DOM: type prompts, read responses
- Zero detection risk (stock Chrome, not Playwright Chromium)
- Session persists across JARVIS restarts (Chrome stays open)

**Fallback:** Pydoll (pure Python CDP client) if Playwright CDP connection proves unreliable.

**Tier 2 (API mode):** anthropic Python SDK directly. No browser needed.

---

## 5. Messaging Platform Decision

Full debate in: research/messaging_platform_research.md

### Winner: Telegram Bot API with python-telegram-bot

**Reasons:**
1. WhatsApp bans AI chatbots (Jan 2026 policy)
2. No 24-hour message window — JARVIS can message anytime
3. Completely free forever
4. No phone number sacrifice
5. 5-minute setup
6. Inline keyboards for approval flows
7. python-telegram-bot library (27K+ stars)

---

## 6. Remaining Dependencies (Need Homebrew Fix)

The following require `sudo chown -R $(whoami) /opt/homebrew` before install:

```bash
brew install node ffmpeg tesseract
```

- **Node.js**: Required for any npx-based MCP servers, and for Baileys if WhatsApp is ever added
- **ffmpeg**: Required for voice note conversion (OGG → WAV for faster-whisper)
- **tesseract**: Required for OCR on screenshots

---

## 7. Architecture Summary

```
JARVIS Runtime Stack:
├── Intelligence Layer
│   ├── Tier 1: Playwright → Chrome → claude.ai (free, subscription-based)
│   └── Tier 2: anthropic SDK → Claude API (paid, faster, more reliable)
├── Messaging Layer
│   └── Telegram Bot API via python-telegram-bot
├── Computer Use Layer
│   └── Anthropic Computer Use API (claude-sonnet-4-5)
├── macOS Automation
│   └── macOS Automator MCP (AppleScript/JXA, 200+ recipes)
│   └── osascript via subprocess (direct AppleScript calls)
├── Memory Layer
│   ├── SQLite + FTS5 (full-text search)
│   ├── sqlite-vec (vector embeddings)
│   └── Entity graph (JSON)
├── Knowledge Scraping
│   ├── PRAW (Reddit)
│   ├── feedparser (RSS/Atom)
│   ├── aiohttp (HN Algolia API, GitHub trending)
│   └── Ollama (local relevance scoring)
├── Voice Processing
│   └── faster-whisper (local transcription)
├── Data Import
│   ├── pdfplumber (PDFs)
│   ├── icalendar (.ics files)
│   └── json (Claude export)
└── Web Framework
    └── FastAPI + uvicorn (dashboard at localhost:7000)
```

---

## 8. Action Items Before Phase 1

1. [ ] User must run: `sudo chown -R $(whoami) /opt/homebrew && brew install node ffmpeg tesseract`
2. [x] Playwright + Chromium installed
3. [x] python-telegram-bot installed  
4. [x] faster-whisper installed
5. [x] anthropic SDK installed
6. [x] All other Python dependencies installed
7. [x] macOS automator MCP configured
8. [x] Research files written for all components
9. [x] Git repo initialized at /Users/yusufsahmed/finalj
10. [x] Remote set to git@github.com:YusufAhmed133/finalj.git
