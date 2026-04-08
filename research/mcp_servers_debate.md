# MCP Server Debate — Advocate / Adversary / Judge

## Critical Constraint (from community research)
- Limit to 5-6 active MCP servers max (each spawns subprocess, eats tokens for tool definitions)
- Playwright MCP alone uses ~114K tokens per session
- 67K+ tokens consumed before first prompt with just 4 servers
- Claude Code already has built-in tools: Read, Write, Edit, Grep, Glob, Bash, WebSearch, WebFetch
- Claude Code has Gmail and Google Calendar MCP servers ALREADY CONNECTED (see system reminders)

## Servers Already Available (No Install Needed)

### Gmail — ALREADY CONNECTED
Claude Code already has: gmail_create_draft, gmail_get_profile, gmail_list_drafts, gmail_list_labels, gmail_read_message, gmail_read_thread, gmail_search_messages.
**Verdict: DO NOT INSTALL a separate Gmail MCP. Already have it.**

### Google Calendar — ALREADY CONNECTED  
Claude Code already has: gcal_create_event, gcal_delete_event, gcal_find_meeting_times, gcal_find_my_free_time, gcal_get_event, gcal_list_calendars, gcal_list_events, gcal_respond_to_event, gcal_update_event.
**Verdict: DO NOT INSTALL a separate Google Calendar MCP. Already have it.**

---

## Debate: @modelcontextprotocol/server-filesystem

### Advocate
Essential for JARVIS. File operations are core — reading config, writing logs, managing imports, accessing documents. The security model with allowed directories prevents accidents. 13 tools covering every file operation needed.

### Adversary
Claude Code ALREADY HAS Read, Write, Edit, Glob, Grep, and Bash tools that do everything filesystem MCP does, plus more. Installing filesystem MCP adds redundant tools that consume tokens for tool definitions. The only unique value is the directory tree visualization, which `find` or `ls -R` can replicate.

### Judge
**REJECT.** Claude Code's built-in tools completely supersede this. Adding it wastes tokens on redundant tool definitions. Use Read/Write/Edit/Glob/Grep/Bash instead.

---

## Debate: @modelcontextprotocol/server-memory

### Advocate
JARVIS's memory spine is custom-built (sqlite + FTS5 + vectors). The MCP memory server uses a flat JSON knowledge graph — different architecture. However, having it as an MCP server means Claude Desktop and other tools can also write to JARVIS's memory. Could be useful for cross-tool memory sharing.

### Adversary
JARVIS will have its own memory system with SQLite, FTS5, vector search, entity graphs, and tier compaction. The MCP memory server stores everything in a single `memory.json` file — no search, no compaction, no tiers, no vectors. It's a toy compared to what we're building. Adding it creates confusion about which memory system is authoritative.

### Judge
**REJECT.** JARVIS's custom memory spine will be vastly more capable. The MCP memory server's flat JSON approach doesn't scale. One authoritative memory system, not two.

---

## Debate: @playwright/mcp

### Advocate
This is THE critical MCP for Tier 1 (browser-based intelligence). JARVIS needs to control a browser to interact with claude.ai. Playwright MCP gives full browser automation: navigate, click, fill forms, take screenshots, read accessibility trees. It's maintained by Microsoft, has 23K+ stars, and is the official replacement for the deprecated Puppeteer MCP. Multi-browser support (Chrome, Firefox, WebKit).

### Adversary
114K tokens per session is massive — that's context window space not available for actual work. JARVIS's brain/claude_browser.py will be custom code using Playwright's Python API directly, not through MCP. The MCP server is designed for Claude to control a browser, but JARVIS's orchestrator needs to control the browser programmatically. MCP adds an unnecessary layer. Also, for the actual JARVIS build, we'll use Playwright as a Python library, not as an MCP server.

### Judge
**REJECT FOR JARVIS RUNTIME. INSTALL FOR DEVELOPMENT/TESTING ONLY.**
During development, Playwright MCP is useful for testing browser automation patterns. But JARVIS's production code will use Playwright Python API directly (playwright-python library) for the claude.ai browser session. The MCP server is the wrong abstraction for production — too many tokens, unnecessary indirection. Install playwright-python as a pip dependency instead.

**Action: `pip install playwright && python -m playwright install chromium`**

---

## Debate: @wonderwhy-er/desktop-commander

### Advocate
Terminal execution with timeout, background mode, and process management. JARVIS needs to run shell commands (start services, check processes, manage files). Desktop Commander provides this with security controls (blocked commands, allowed directories). 5.3K stars, actively maintained.

### Adversary
Claude Code already has Bash tool with full shell access, timeout support, and background execution. Desktop Commander's file operations duplicate Read/Write/Edit. Its process management (list/kill PIDs) can be done with `ps` and `kill` via Bash. The security controls are nice but unnecessary — JARVIS's permission system handles dangerous actions at a higher level.

### Judge
**REJECT.** Claude Code's Bash tool already provides everything Desktop Commander offers. The additional security layer is redundant with JARVIS's own permission system. Don't waste a server slot on this.

---

## Debate: @brave/brave-search-mcp-server

### Advocate
Live web search is essential for JARVIS — finding information, researching topics, checking news. Brave Search has a generous free tier and privacy-respecting index. JARVIS's knowledge scraping agent can use it for real-time queries.

### Adversary
Claude Code already has WebSearch and WebFetch built-in tools. These provide the same capability without requiring a Brave API key or an additional MCP server. The built-in WebSearch already works for current events and recent data.

### Judge
**REJECT.** Claude Code's WebSearch and WebFetch are already available and functional. No need for a separate search MCP. If JARVIS needs programmatic search in its Python code, use the `requests` library with a search API directly.

---

## Debate: mcp-server-fetch

### Advocate
URL fetching with HTML-to-markdown conversion, chunked reading, proxy support. Useful for scraping web content into LLM-digestible format.

### Adversary
Claude Code has WebFetch built-in. For JARVIS's Python code, `requests` + `beautifulsoup4` (already installed) handles HTML fetching and parsing. Adding another fetch tool is pure redundancy.

### Judge
**REJECT.** WebFetch is built-in. BeautifulSoup4 is already installed for Python-side fetching.

---

## Debate: @steipete/macos-automator-mcp

### Advocate
200+ pre-built AppleScript/JXA recipes for macOS automation. Toggle dark mode, clipboard operations, system notifications, control Safari/Chrome/Finder/Mail/Terminal. This is exactly what JARVIS needs for Mac control — a huge library of tested automation scripts. 735 stars, macOS-specific.

### Adversary
JARVIS will use Claude's Computer Use API with claude-sonnet-4-5 for Mac automation. That's vision-based control (screenshots + mouse/keyboard) which is more general and doesn't need pre-built recipes. The AppleScript recipes are useful for specific tasks but overlap heavily with computer use. Also, JARVIS's orchestrator will call AppleScript directly via `subprocess.run(['osascript', '-e', ...])` when needed — no MCP layer required.

### Judge
**INSTALL.** This one is worth it despite the overlap. The 200+ pre-built recipes represent months of macOS automation knowledge. JARVIS should use Computer Use for visual tasks (navigating UIs, reading screens) and AppleScript for system tasks (notifications, clipboard, volume, dark mode, app management). They're complementary, not redundant. The MCP server makes these recipes immediately available without reimplementing them.

---

## Debate: @modelcontextprotocol/server-sqlite

### Advocate
JARVIS stores everything in SQLite (context.db, knowledge.db, vectors.db). Having an MCP server that can query these databases means Claude can inspect JARVIS's memory, debug issues, run analytics on stored data during development.

### Adversary
One server instance per database. JARVIS has 3 databases. That's 3 server slots just for SQLite inspection. Bash + `sqlite3` command does the same thing. During development, we can just read the databases directly.

### Judge
**REJECT.** Use `sqlite3` via Bash for development inspection. Not worth 1-3 server slots for something used occasionally during debugging.

---

## Debate: github/github-mcp-server

### Advocate
28K+ stars, official by GitHub. 100+ tools for GitHub API — repo management, code search, PRs, issues. JARVIS could use this to manage Yusuf's repos, review PRs, track issues.

### Adversary
Claude Code already has the `gh` CLI tool available via Bash, which covers all GitHub operations. The MCP server adds 100+ tool definitions to the context — massive token overhead for capability we already have.

### Judge
**REJECT.** `gh` CLI via Bash is already available and sufficient. 100+ tool definitions would be devastating for token budget.

---

## Debate: @notionhq/notion-mcp-server

### Advocate
If Yusuf uses Notion for notes/planning, this gives JARVIS direct access to create, read, and update pages and databases.

### Adversary
No evidence Yusuf uses Notion. Installing speculative MCP servers wastes a server slot. Can be added later if needed.

### Judge
**DEFER.** Only install if Yusuf confirms he uses Notion. Not installing speculatively.

---

## Debate: Spotify MCP

### Advocate
Quality-of-life feature. JARVIS could control music, create playlists, play study music when Yusuf starts studying.

### Adversary
Requires Spotify Premium + Developer credentials + OAuth setup. Non-essential for JARVIS's core mission. Can be done via AppleScript ("tell application Spotify to play") through the macOS automator MCP or via osascript.

### Judge
**DEFER.** Not a core capability. AppleScript can handle basic Spotify control. Install dedicated MCP only if Yusuf wants advanced playlist management.

---

## Debate: @kazuph/mcp-screenshot

### Advocate
Screen capture + OCR. JARVIS needs to see the screen for computer use tasks.

### Adversary
Claude's Computer Use API already includes screenshot capability. The macOS `screencapture` command works via Bash. OCR via tesseract (once installed) handles text extraction. This is redundant three ways.

### Judge
**REJECT.** Computer Use API + screencapture + tesseract cover this completely.

---

## Debate: PeterHdd/macos-control-mcp (SEE-THINK-ACT)

### Advocate
Screenshot + OCR + click at coordinates + type text. Designed specifically for giving AI agents "eyes and hands" on macOS. Uses Apple Vision framework for OCR.

### Adversary
This is literally what Claude's Computer Use API does, but worse (custom implementation vs Anthropic's battle-tested system). Computer Use API has claude-sonnet-4-5 behind it for vision understanding. This MCP server reinvents that wheel with less capability.

### Judge
**REJECT.** Computer Use API is the correct solution for vision-based Mac control.

---

## Debate: Sequential Thinking MCP

### Advocate
Structured reasoning with revision and branching. Useful for complex decisions.

### Adversary
Claude already does chain-of-thought reasoning natively. Adding an MCP server to structure thinking is like adding a plugin to help Claude think — Claude already thinks. The extended thinking/analysis features in Claude are more powerful than any external reasoning framework.

### Judge
**REJECT.** Claude's native reasoning is sufficient. This adds no real capability.

---

## Debate: Context7 MCP

### Advocate
Community's #1 recommended MCP. Fetches current, version-specific documentation for libraries. Eliminates stale documentation hallucinations.

### Adversary
Useful for general coding tasks, but JARVIS isn't a coding assistant — it's a personal AI operating system. During JARVIS development, Claude Code already has access to documentation via WebSearch/WebFetch. In production, JARVIS won't be looking up library docs.

### Judge
**INSTALL FOR DEVELOPMENT.** Extremely useful while building JARVIS. Can be removed for production runtime to save a server slot.

---

## Final Installation List

### Install Now (Production + Development)
1. **@steipete/macos-automator-mcp** — 200+ macOS automation recipes, complementary to Computer Use

### Install Now (Development Only — Remove for Production)
2. **Context7** — Version-specific library docs during development

### Install as Python Libraries (Not MCP Servers)
3. **playwright** (pip) — For claude.ai browser session (Tier 1 intelligence)
4. **python-telegram-bot** (pip) — For messaging interface

### Already Available (No Action Needed)
- Gmail MCP (already connected)
- Google Calendar MCP (already connected)
- Filesystem operations (Read/Write/Edit/Glob/Grep)
- Web search (WebSearch tool)
- URL fetching (WebFetch tool)
- Shell execution (Bash tool)
- GitHub operations (gh CLI)

### Deferred (Install Only If Needed)
- Notion MCP — if Yusuf uses Notion
- Spotify MCP — if advanced music control needed
- Any database MCP — if direct Claude-to-DB queries needed
