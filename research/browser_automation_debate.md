# Browser Automation Research & Debate

## Use Case
JARVIS Tier 1 (local/subscription): Control a browser to interact with claude.ai. Must:
- Maintain persistent logged-in session (Claude Max subscription)
- Type prompts into chat input
- Read streaming responses
- Handle long responses
- Survive browser restarts
- Work on macOS Apple Silicon (M2)

## Candidates Researched

### 1. Playwright (Python API — microsoft/playwright-python)
- **Persistent session**: YES. `browser_type.launch_persistent_context(user_data_dir)` preserves cookies, localStorage, session state across restarts
- **Connect to existing browser**: YES. `browser_type.connect_over_cdp(endpoint_url)` connects to Chrome launched with `--remote-debugging-port`
- **Python API**: First-class, async-native, excellent docs
- **macOS M2**: Fully supported, pre-built binaries
- **Speed**: Fast. Modern protocol, not HTTP-based like Selenium
- **Streaming content**: Can use `page.wait_for_selector()`, `page.evaluate()` to poll for new content, or `MutationObserver` via JS injection
- **Community**: 13K+ stars (Python), massively adopted, Microsoft-maintained
- **Anti-detection**: Standard Playwright is detectable. But with persistent context using real Chrome profile, detection is minimal since it looks like a real user session

### 2. Puppeteer (Node.js only)
- **Language**: JavaScript/TypeScript ONLY. No official Python port
- **Python ports**: pyppeteer (abandoned), pyppeteer2 (minimal maintenance)
- **Persistent session**: Yes via userDataDir
- **DISQUALIFIED**: JARVIS is Python-based. Using Node.js for the core intelligence layer adds unnecessary complexity. Playwright does everything Puppeteer does with better Python support.

### 3. Selenium
- **Persistent session**: Possible but hacky (save/restore cookies, session IDs)
- **Speed**: Slowest of all options. HTTP-based WebDriver protocol
- **API**: Dated, verbose, not async-native
- **Community**: Huge but declining. Playwright is the clear successor
- **REJECTED**: Slower, more complex, less capable than Playwright

### 4. AppleScript + System Events
- **What it can do**: Open apps, click menu items, type text, basic UI interaction
- **What it cannot do**: Interact with specific DOM elements in a webpage. Cannot read content from a specific div. Cannot wait for elements to load. Cannot handle streaming content.
- **REJECTED for primary use**: Too limited for web app interaction. Good for opening Chrome, but useless for interacting with claude.ai's DOM.
- **COMPLEMENTARY USE**: Use via macOS automator MCP for system-level tasks (opening apps, notifications, clipboard)

### 5. Pydoll (Python CDP library)
- **What it is**: Pure Python Chrome DevTools Protocol client. No WebDriver, no browser binary bundled
- **Persistent session**: Connects to existing Chrome instance via CDP
- **Anti-detection**: Better than Playwright since it uses real Chrome, not Chromium
- **Speed**: Fast, direct CDP connection
- **Stars**: ~5K, growing rapidly
- **Downside**: Younger library, smaller community, Chrome-only (no Firefox/WebKit)
- **STRONG CONTENDER**: Worth serious consideration

### 6. browser-use (Python library)
- **What it is**: AI agent framework for browser control. Uses Playwright underneath
- **Focus**: Designed for LLMs to control browsers (exactly our use case)
- **Stars**: 60K+, extremely active
- **Downside**: Opinionated about how AI interacts with browser, may add unnecessary abstraction. Uses its own LLM calls internally which conflicts with our architecture.
- **REJECTED**: Too opinionated. JARVIS needs low-level browser control, not another AI framework making decisions.

## Multi-Agent Debate

### The Advocate (for Playwright Python API)

Playwright is the clear winner for JARVIS's browser intelligence layer:

1. **Persistent context is a first-class feature.** `launch_persistent_context(user_data_dir)` is literally designed for this use case. Point it at Chrome's actual profile directory and it inherits the full session — cookies, localStorage, IndexedDB, everything. Claude Max login persists across restarts.

2. **Best Python API in the space.** Async-native with `async_api`, synchronous fallback with `sync_api`. Type-hinted. Excellent autocomplete. First-class citizens alongside the JS/TS API, not a port.

3. **Battle-tested on macOS Apple Silicon.** Pre-built Chromium binaries for arm64. Microsoft CI tests on macOS. Zero compatibility issues.

4. **CDP connection for flexibility.** Can connect to an already-running Chrome via `connect_over_cdp()`. This means JARVIS can launch Chrome once with a profile, then reconnect to it after restarts without losing the session.

5. **Streaming response handling.** Inject a MutationObserver via `page.evaluate()` to watch claude.ai's response div. Or poll with `page.query_selector_all()`. Or use `page.wait_for_function()` to wait for response completion. Multiple approaches, all well-documented.

6. **Screenshot capability.** `page.screenshot()` for logging, debugging, and computer use integration.

7. **13K+ stars, Microsoft-maintained.** Not going anywhere. Monthly releases. Excellent issue response time.

### The Adversary (for Pydoll as alternative)

1. **Detection risk.** Playwright bundles its own Chromium, which has subtle differences from stock Chrome. claude.ai could detect automation. Pydoll connects to stock Chrome — zero detection risk.

2. **Resource overhead.** Playwright spawns a separate Chromium process. On an M2 MacBook Air, that's significant RAM. Pydoll connects to the Chrome the user already has open.

3. **Session authenticity.** Playwright's persistent context *copies* the profile. Pydoll connects to the *actual* Chrome with the *actual* session. No copying, no sync issues.

4. **Simpler architecture.** Pydoll is pure Python, pure CDP. No binary management. No browser download. Connect to Chrome, done.

5. **Growing fast.** 5K stars and accelerating. The "no WebDriver" approach resonates with the automation community.

### The Judge

**Ruling: Playwright wins, with Pydoll as fallback.**

Point-by-point analysis:

1. **Detection risk (Adversary's strongest point)**: Valid but mitigatable. Playwright CAN connect to stock Chrome via `connect_over_cdp()` — same as Pydoll. If we launch Chrome manually with `--remote-debugging-port=9222`, then connect Playwright to it, we get stock Chrome + Playwright's superior API. Detection risk eliminated.

2. **Resource overhead**: If we use `connect_over_cdp()` to an existing Chrome, Playwright does NOT spawn a separate browser. It connects to the running one. Overhead is negligible — just the Python process.

3. **Session authenticity**: With `connect_over_cdp()`, we connect to the user's actual Chrome with their actual Claude Max session. Same benefit as Pydoll.

4. **API maturity**: Playwright's Python API is years ahead of Pydoll's. Better error handling, better selectors, better waits, better documentation. For a production system, maturity matters.

5. **Fallback value**: Pydoll as a fallback is smart. If Playwright's connection to Chrome breaks for any reason, JARVIS can fall back to Pydoll with minimal code changes (both use CDP underneath).

**Final specification:**

**Primary: Playwright Python (`playwright`) via `connect_over_cdp()`**
- Launch Chrome with: `open -a "Google Chrome" --args --remote-debugging-port=9222`
- Connect: `browser = await playwright.chromium.connect_over_cdp("http://localhost:9222")`
- Navigate to claude.ai, use existing logged-in session
- Interact via selectors for input field, send button, response area

**Fallback: Pydoll (if Playwright CDP connection proves unreliable)**
- Install: `pip install pydoll-python`
- Same CDP connection pattern

**For Tier 2 (API mode):** None of this matters — just use `anthropic` Python SDK directly. Browser automation only needed for Tier 1.

## Implementation Notes

### claude.ai DOM interaction strategy
1. Navigate to `https://claude.ai/new` (or existing conversation)
2. Find the text input: likely a `contenteditable` div or `textarea` — need to inspect live DOM
3. Type the prompt using `page.fill()` or `page.type()`
4. Click send button or press Enter
5. Wait for response: watch for a new message element to appear and stop streaming
6. Read response text from the response element
7. Parse structured output (JARVIS will ask Claude to respond in parseable format)

### Session management
- Store Chrome's user data directory path in config
- Launch Chrome with debugging port as part of JARVIS startup
- Reconnect on connection loss with exponential backoff
- Detect session expiry (Claude asks to log in) and alert Yusuf via Telegram
