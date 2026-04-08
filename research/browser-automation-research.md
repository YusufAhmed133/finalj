# JARVIS Browser Automation Research: Controlling claude.ai from Python

**Date:** 2026-04-08
**Goal:** JARVIS opens claude.ai in a browser, maintains a persistent logged-in session (Claude Max), types prompts into the chat input, reads streaming responses back, and does this repeatedly without opening/closing the browser each time.

---

## 0. The claude.ai DOM Challenge

Before evaluating tools, the target matters. claude.ai is a React single-page application. Key findings:

- **The chat input is a `contenteditable` div, NOT a `<textarea>`.** You read its value via `el.innerText`, not `el.value`. You cannot simply `element.type("text")` -- you must click into the editor and use keyboard input, or dispatch synthetic input events.
- **CSS class names are hashed/generated** (typical of React/Next.js builds). They change across deployments. Never rely on class-based selectors.
- **Stable selectors** include attribute-based selectors (e.g., `[data-placeholder]`, `[contenteditable="true"]`, `role="textbox"`) and structural selectors (the contenteditable div inside a known parent structure).
- **The editor is likely ProseMirror/Tiptap-based**, which means it manages its own internal state. Setting `innerText` directly may not trigger the editor's internal update. The reliable approach is: click to focus, then use keyboard events (`page.keyboard.type()`).
- **Streaming responses** render incrementally into the DOM. To read a response, you need to either poll the response container or use a MutationObserver (via JavaScript injection) to detect when streaming is complete.
- **The "send" action** is triggered by pressing Enter (without Shift) or clicking the send button.

---

## 1. Playwright (Microsoft)

### 1.1 What It Is

The dominant browser automation framework in 2025-2026. Maintained by Microsoft with a dedicated team. Official Python bindings (`playwright-python`) with full feature parity to the Node.js version.

### 1.2 Persistent Session Support

**Excellent.** Two complementary approaches:

**Approach A: `launch_persistent_context(user_data_dir)`**
- Launches Chromium using a real Chrome profile directory
- All cookies, localStorage, sessionStorage, and IndexedDB persist across runs
- If you point it at your actual Chrome profile (`~/Library/Application Support/Google/Chrome/Default`), it inherits your logged-in session on claude.ai
- Caveat: Chrome must be fully closed before Playwright can use the profile (they cannot share it simultaneously)

**Approach B: `connect_over_cdp("http://localhost:9222")`**
- Connects to an **already-running** Chrome instance via Chrome DevTools Protocol
- Chrome must be launched with `--remote-debugging-port=9222`
- Playwright attaches to the live browser -- your existing logged-in tabs, cookies, everything
- You can keep Chrome open indefinitely and reconnect Playwright on every JARVIS invocation
- This is the ideal approach for JARVIS: launch Chrome once with debugging enabled, connect/disconnect as needed

**Approach C: `storage_state` save/restore**
- Save cookies + localStorage to a JSON file after logging in
- Restore them into a fresh browser context on next run
- Lighter weight but may not capture all session state (e.g., IndexedDB, service workers)

### 1.3 Python API Quality

Best-in-class. Official, first-party Python package:
```
pip install playwright
playwright install chromium
```

Async and sync APIs both available. Full type hints. Excellent documentation. The Python API mirrors the Node.js API almost exactly.

### 1.4 macOS Apple Silicon Compatibility

**Officially supported.** Playwright downloads ARM64 browser binaries for Apple Silicon. Minor historical issues (some reports of Chromium launching Intel binaries in headed mode, resolved in recent versions). Firefox and WebKit work natively. Use a recent version (1.40+) to avoid any M1/M2/M3 quirks.

### 1.5 Speed

Playwright communicates via a persistent WebSocket connection to the browser, which is significantly faster than Selenium's HTTP-based approach. Benchmarks show Playwright is 1.5-2x faster than Selenium per action (~290ms vs ~536ms average). For the JARVIS use case (type prompt, wait for streaming response), the bottleneck is Claude's response time (seconds), not framework overhead (milliseconds).

### 1.6 Handling Dynamic Content

**Excellent.** Built-in auto-waiting, `wait_for_selector`, `wait_for_function`, and the ability to inject JavaScript (including MutationObservers) to detect when streaming completes. Playwright's `page.evaluate()` runs arbitrary JS in the page context.

### 1.7 Limitations

- `connect_over_cdp` is described as "lower fidelity" than Playwright's native protocol, but for the JARVIS use case (typing, clicking, reading text) this is irrelevant -- those are basic CDP operations.
- Playwright installs its own browser binaries by default. To use your system Chrome, you need CDP connection or `channel="chrome"` flag.
- The Node.js Playwright server process adds a small layer between Python and the browser (Python <-> WebSocket <-> Node.js Playwright server <-> WebSocket <-> Browser). This is the latency browser-use cited when migrating away.

### 1.8 Community & Maintenance

- 70k+ GitHub stars, extremely active development
- Microsoft-backed with full-time engineering team
- Releases every ~2 weeks
- Massive ecosystem: Playwright MCP, Playwright CLI, Codegen, trace viewer
- Dominant framework for browser automation in 2025-2026

---

## 2. Puppeteer (Google)

### 2.1 What It Is

Google's browser automation library for Chrome/Chromium. Originally Node.js only.

### 2.2 Persistent Session Support

**Good, similar to Playwright.** Supports:
- `puppeteer.connect({ browserWSEndpoint })` to attach to existing Chrome with `--remote-debugging-port=9222`
- `--user-data-dir` for persistent profile data
- Important: do NOT call `browser.close()` if you want the browser to stay open

### 2.3 The Python Problem

**This is the dealbreaker for JARVIS.** Puppeteer is Node.js only. The Python port, **Pyppeteer**, has been effectively abandoned:
- Last release: January 2022
- No updates in 4+ years
- Missing features from modern Puppeteer
- Small community, difficult to troubleshoot
- Not recommended for new projects in 2025-2026

If JARVIS were Node.js-based, Puppeteer would be a strong contender. But JARVIS is Python. Using Puppeteer would require either:
1. Running a Node.js subprocess from Python (messy, fragile)
2. Using the dead Pyppeteer library (risky)
3. Rewriting JARVIS components in JavaScript (not viable)

### 2.4 Verdict

**Eliminated due to no viable Python support.** Playwright is the direct successor with better Python bindings.

---

## 3. Selenium

### 3.1 What It Is

The oldest browser automation framework (2004). Still widely used, but showing its age.

### 3.2 Persistent Session Support

**Possible but hacky.** Methods include:
- Starting Chrome with `--remote-debugging-port` and attaching via `debugger_address` option
- Saving/restoring `session_id` and `command_executor._url` for reconnection
- Custom `PersistentRemote` subclass that hijacks session creation
- All approaches feel like workarounds rather than supported features

### 3.3 Python Support

Good. Selenium has official Python bindings. However:
- API is more verbose than Playwright
- No built-in auto-waiting (you write explicit waits everywhere)
- WebDriver-based architecture adds overhead

### 3.4 Speed

**Slowest of the three major frameworks.** Selenium uses HTTP requests to communicate with the browser driver (ChromeDriver), adding latency on every command. Benchmarks show ~1.5-2x slower than Playwright. Uses 50-60% more memory per test.

### 3.5 macOS Apple Silicon

Works, but requires matching ChromeDriver to your Chrome version. `webdriver-manager` helps but adds another dependency.

### 3.6 Handling Dynamic Content

Adequate but manual. No auto-waiting. You must use `WebDriverWait` + `expected_conditions` for every dynamic element. More boilerplate, more room for flaky behavior.

### 3.7 Verdict

**Not recommended.** Slower, more verbose, weaker persistent session support, and more fragile than Playwright. No advantage for the JARVIS use case.

---

## 4. AppleScript + System Events

### 4.1 What It Is

macOS-native automation via `osascript`. Can control Chrome by executing JavaScript in tabs.

### 4.2 How It Works

```applescript
tell application "Google Chrome"
    tell active tab of window 1
        execute javascript "document.querySelector('[contenteditable]').focus()"
    end tell
end tell
```

### 4.3 Key Advantage

JavaScript executes inside the **user's actual Chrome process** -- same V8 context, same cookies, same session. No separate browser instance. No debugging port. Chrome doesn't even need to be launched specially.

### 4.4 Key Limitations

**Critical issues for JARVIS:**

1. **Must enable "Allow JavaScript from Apple Events"** in Chrome's Developer menu. If Chrome updates and resets this flag, JARVIS silently breaks.
2. **No structured return values.** `execute javascript` returns strings. Parsing complex DOM state requires serializing to JSON strings and deserializing in Python.
3. **No event listeners or callbacks.** You cannot set up a MutationObserver and get notified when streaming completes. You must poll (execute JS, check result, sleep, repeat).
4. **No waiting primitives.** No `wait_for_selector`, no auto-retry. Everything is manual polling.
5. **Error handling is primitive.** AppleScript errors are opaque strings.
6. **Slow for rapid interactions.** Each `osascript` call has ~50-100ms overhead for process spawning.
7. **React state management.** Setting `innerText` on a ProseMirror/Tiptap contenteditable div will NOT update React's internal state. You need to simulate keyboard events, which requires complex JavaScript injection.
8. **Fragile.** No community building production automation tools on AppleScript in 2025-2026.

### 4.5 Verdict

**Not recommended as the primary approach.** Could work as a quick hack or fallback, but too fragile and limited for a production assistant. The polling-based approach for reading streaming responses would be slow and wasteful. No ecosystem support.

**However:** AppleScript has one unique strength -- it can control Chrome without any special launch flags. This could be useful as a "last resort" fallback if CDP connection fails.

---

## 5. CDP (Chrome DevTools Protocol) Directly

### 5.1 What It Is

The raw WebSocket protocol that Chrome exposes for debugging and automation. Playwright, Puppeteer, and browser-use all use CDP under the hood. You can use it directly without any framework.

### 5.2 Python Libraries

- **PyCDP / python-cdp** -- Low-level Python wrappers for CDP commands. Asyncio-based.
- **PyChromeDevTools** -- Simpler synchronous wrapper.
- **Pydoll** -- Newer (2025), async-first, CDP-direct library with 5.9k+ GitHub stars. No WebDriver dependency. Type-checked with mypy. Supports parallel tabs via `asyncio.gather`. Has structured data extraction via Pydantic models.
- **Raw websockets** -- CDP is just JSON over WebSocket. Python's `websockets` library is sufficient.

### 5.3 Why browser-use Migrated to Raw CDP

In early 2026, browser-use dropped Playwright and switched to raw CDP. Their reasons:
- Playwright's Node.js server adds a second WebSocket hop (Python -> Node.js Playwright server -> Browser), adding latency when doing thousands of CDP calls
- AI browser agents have narrower needs than Playwright's full surface area
- Direct CDP gives deeper control (e.g., proper cross-origin iframe support, async reaction capabilities)
- Massively increased speed for element extraction and screenshots

### 5.4 For JARVIS Specifically

**Overkill.** Raw CDP gives maximum control and performance, but at the cost of:
- Writing low-level protocol commands for every action (navigate, click, type, read DOM)
- No auto-waiting, no high-level selectors, no convenience methods
- More code to maintain
- The performance gains matter when doing thousands of actions per second (browser-use's use case), not when typing one prompt and reading one response (JARVIS's use case)

### 5.5 Pydoll as a Middle Ground

Pydoll deserves special mention. It is:
- Python-native, async-first, no Node.js dependency
- Direct CDP connection (no Playwright server overhead)
- Higher-level API than raw CDP (element finding, clicking, typing)
- Actively maintained (2025-2026)
- 5.9k+ GitHub stars

However, it is primarily designed for web scraping, not session management. Its persistent session story is less mature than Playwright's.

### 5.6 Verdict

**Not recommended as the primary approach for JARVIS.** The overhead savings of raw CDP are irrelevant when the bottleneck is Claude's response time. Playwright's higher-level API is worth the trivial latency cost. However, Pydoll is worth watching as it matures.

---

## 6. browser-use

### 6.1 What It Is

Open-source Python library (89.1% benchmark success rate) specifically designed for AI agents to control browsers. Uses LLMs to interpret page structure and plan actions. As of early 2026, migrated from Playwright to raw CDP internally.

### 6.2 Key Features

- LLM-native API: describe what you want in natural language
- Visual understanding + HTML structure extraction
- Supports persistent sessions via `storage_state` parameter or CDP endpoint connection
- Active community, well-documented edge cases
- Supports GPT-4o, Claude, Gemini as the driving LLM

### 6.3 For JARVIS Specifically

**Interesting but wrong abstraction layer.** browser-use is designed for AI agents that need to figure out how to navigate unknown websites. JARVIS knows exactly what it needs to do on claude.ai:
1. Find the input field
2. Type a prompt
3. Press Enter
4. Wait for and read the response

Using browser-use for this is like using a self-driving car to drive down a straight road. It adds:
- LLM API calls (cost + latency) for every browser action
- Non-deterministic behavior (the LLM might interpret the page differently each time)
- A heavy dependency (browser-use + its LLM provider)
- Unnecessary complexity

### 6.4 When browser-use WOULD Make Sense

If JARVIS needed to navigate arbitrary websites (e.g., "go to Amazon and find the cheapest X"), browser-use would be excellent. For a fixed target like claude.ai, scripted automation is simpler, faster, cheaper, and more reliable.

### 6.5 Verdict

**Not recommended for the claude.ai use case.** Over-engineered for a fixed-target interaction. The LLM overhead (cost and latency) provides no benefit when the interaction is fully deterministic.

---

## 7. Head-to-Head Comparison

| Criterion | Playwright | Puppeteer | Selenium | AppleScript | Raw CDP / Pydoll | browser-use |
|---|---|---|---|---|---|---|
| **Python support** | Official, first-party | Dead (Pyppeteer) | Official | Via subprocess | Native | Native |
| **Persistent session** | Excellent (3 methods) | Good (2 methods) | Hacky | Inherent (same Chrome) | Manual | Via storage_state |
| **Connect to existing browser** | `connect_over_cdp` | `connect()` | Possible | Inherent | Native | Via CDP endpoint |
| **Speed (framework overhead)** | Fast (~290ms/action) | Fast | Slow (~536ms/action) | Slow (process spawn) | Fastest | Slow (LLM calls) |
| **Auto-waiting** | Built-in | Built-in | Manual | None | None/Manual | LLM-driven |
| **Streaming response detection** | JS injection, polling, MutationObserver | Same | Same but verbose | Polling only | Full control | LLM interprets |
| **macOS Apple Silicon** | Officially supported | N/A (Node.js) | Works with setup | Native | Works | Works |
| **Community/maintenance** | 70k+ stars, Microsoft | 89k stars, Google (but Node.js) | 32k stars, aging | Tiny | Growing (Pydoll 5.9k) | Growing |
| **Complexity for JARVIS** | Low | N/A | Medium | Medium-High | High | Over-engineered |
| **Deterministic behavior** | Yes | Yes | Yes | Yes | Yes | No (LLM-dependent) |
| **Additional cost** | None | None | None | None | None | LLM API calls |
| **Node.js dependency** | Yes (Playwright server) | Yes (native) | No (ChromeDriver) | No | No | No (since CDP migration) |

---

## 8. Recommendation

### Use Playwright with `connect_over_cdp`. It is the clear winner.

**The architecture:**

```
JARVIS (Python)
    |
    | playwright.chromium.connect_over_cdp("http://localhost:9222")
    |
    v
Chrome (launched once with --remote-debugging-port=9222)
    |
    | Already logged into claude.ai with Claude Max
    |
    v
claude.ai tab (persistent, never closes)
```

**Why Playwright:**

1. **Best persistent session story.** Three approaches (CDP connection, persistent context, storage state), all well-documented and production-tested. `connect_over_cdp` is perfect for JARVIS: Chrome stays open with your Claude Max login, JARVIS connects when needed and disconnects when done.

2. **Official, excellent Python API.** First-party package from Microsoft. Async and sync. Full type hints. Not a community port, not abandoned, not behind the Node.js version.

3. **Right level of abstraction.** High enough that you write `page.keyboard.type("my prompt")` and `page.wait_for_selector(".response-complete")`, but low enough that you can inject custom JavaScript for streaming detection. You don't need to write raw WebSocket commands, and you don't need an LLM to figure out what to click.

4. **Battle-tested on macOS Apple Silicon.** Officially supported, ARM64 binaries, thousands of users on M1/M2/M3.

5. **Dominant ecosystem.** Any problem you hit, someone has already solved it. Stack Overflow, GitHub issues, blog posts, tutorials -- the support surface is unmatched.

6. **Speed is irrelevant but Playwright is fast anyway.** The bottleneck is Claude generating a response (seconds to minutes), not Playwright dispatching a click (milliseconds). Even so, Playwright is the fastest mainstream framework.

7. **No additional cost.** Unlike browser-use (which burns LLM tokens on every action), Playwright is free and deterministic.

### Recommended Implementation Plan

**Step 1: Launch Chrome with debugging enabled (one-time setup)**
```bash
# Add to JARVIS launch script or launchd plist
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
    --remote-debugging-port=9222 \
    --user-data-dir="$HOME/Library/Application Support/Google/Chrome"
```
This launches Chrome with your real profile (all cookies, all logins, Claude Max session intact).

**Step 2: JARVIS connects via CDP**
```python
from playwright.sync_api import sync_playwright

def connect_to_claude():
    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp("http://localhost:9222")
    context = browser.contexts[0]  # existing browser context
    # Find or open the claude.ai tab
    page = None
    for p in context.pages:
        if "claude.ai" in p.url:
            page = p
            break
    if not page:
        page = context.new_page()
        page.goto("https://claude.ai")
    return pw, browser, page
```

**Step 3: Type a prompt**
```python
def send_prompt(page, prompt_text):
    # Click the contenteditable input to focus it
    editor = page.wait_for_selector('[contenteditable="true"]')
    editor.click()
    # Type the prompt via keyboard (respects ProseMirror state)
    page.keyboard.type(prompt_text)
    # Send with Enter
    page.keyboard.press("Enter")
```

**Step 4: Read the streaming response**
```python
def read_response(page, timeout=120000):
    # Wait for response to start appearing
    # Wait for streaming to complete (send button reappears, or stop button disappears)
    page.wait_for_selector('[aria-label="Send"]', timeout=timeout)
    # Read the last response
    response = page.evaluate('''
        () => {
            const messages = document.querySelectorAll('[data-is-streaming]');
            // Or find the last assistant message container
            const allMessages = document.querySelectorAll('.font-claude-message');
            const last = allMessages[allMessages.length - 1];
            return last ? last.innerText : null;
        }
    ''')
    return response
```

**Note on selectors:** The selectors above are illustrative. The actual selectors for claude.ai will need to be determined by inspecting the live DOM. Class names are hashed and change frequently. The reliable approach is:
- Use attribute selectors (`[contenteditable="true"]`, `[role="textbox"]`, `[data-*]`)
- Use structural selectors (nth-child, parent-child relationships)
- Fall back to XPath if needed
- Build a selector discovery function that JARVIS runs on first connect to find the current selectors

**Step 5: Disconnect cleanly (browser stays open)**
```python
def disconnect(pw, browser):
    browser.close()  # disconnects from CDP, does NOT close Chrome
    pw.stop()
```

### Fallback Strategy

If `connect_over_cdp` has issues (rare but possible):
1. **Fallback to `launch_persistent_context`** with a dedicated Chrome profile directory. Requires closing the main Chrome first, but creates a clean separate instance.
2. **Fallback to AppleScript** for emergency single-shot commands (execute JavaScript in the existing Chrome tab without any debugging port).

### Dependencies to Add

```
playwright>=1.40
```

Plus one-time setup:
```bash
playwright install chromium  # or use system Chrome via channel="chrome"
```

---

## 9. What About the Playwright Node.js Dependency?

One valid concern: Playwright Python communicates with browsers through a Node.js Playwright server process. This adds:
- A Node.js runtime dependency on the system
- A second WebSocket hop (Python -> Node.js -> Browser)
- ~10-20ms additional latency per command

For JARVIS, this is completely irrelevant. The interaction is: type prompt (1 action), press Enter (1 action), wait 5-60 seconds for Claude to respond, read response (1 action). Three commands per interaction. The 30-60ms total overhead from the Node.js hop is invisible.

If this ever becomes a concern (it won't), Pydoll offers a CDP-direct Python alternative without Node.js. But there is no reason to optimize for this.

---

## Sources

- [Playwright Python API: BrowserType](https://playwright.dev/python/docs/api/class-browsertype)
- [Playwright: Connecting to Existing Browser (BrowserStack)](https://www.browserstack.com/guide/playwright-connect-to-existing-browser)
- [Playwright Persistent Context (Medium)](https://medium.com/@anandpak108/using-persistent-context-in-playwright-for-browser-sessions-c639d9a5113d)
- [Playwright connect_over_cdp Examples (LambdaTest)](https://www.lambdatest.com/automation-testing-advisor/python/playwright-python-connect_over_cdp)
- [How to Use Playwright with External Chrome (DEV Community)](https://dev.to/sonyarianto/how-to-use-playwright-with-externalexisting-chrome-4nf1)
- [Playwright GitHub Issue #11442: Connect to Existing Session](https://github.com/microsoft/playwright/issues/11442)
- [Playwright vs Selenium 2026 (BrowserStack)](https://www.browserstack.com/guide/playwright-vs-selenium)
- [Performance Benchmark: Playwright vs Cypress vs Selenium 2026 (TestDino)](https://testdino.com/blog/performance-benchmarks/)
- [Playwright Apple Silicon Issues (GitHub #19602)](https://github.com/microsoft/playwright/issues/19602)
- [Playwright MCP Server (GitHub)](https://github.com/microsoft/playwright-mcp)
- [Playwright MCP Save Session (Jeremy Watt)](https://neonwatty.com/posts/playwright-profiles-claude-code-plugin/)
- [Puppeteer: Use Existing Chrome (GitHub Issue #3543)](https://github.com/puppeteer/puppeteer/issues/3543)
- [Puppeteer Reconnect API (Browserless)](https://www.browserless.io/blog/reconnect-api)
- [Pyppeteer Status (PyPI)](https://pypi.org/project/pyppeteer/)
- [Python Puppeteer Alternatives 2026 (Thunderbit)](https://thunderbit.com/blog/python-puppeteer-and-alternatives)
- [Selenium: Interact with Existing Session (codestudy.net)](https://www.codestudy.net/blog/can-selenium-interact-with-an-existing-browser-session/)
- [Reuse Existing Selenium Session (Qxf2)](https://qxf2.com/blog/reuse-existing-selenium-browser-session/)
- [AppleScript Chrome Automation (DEV Community)](https://dev.to/haoyang_pang_a9f08cdb0b6c/the-browser-automation-cheat-code-nobody-talks-about-applescript-chrome-52ha)
- [Chrome AppleScript Support (Chromium Docs)](https://www.chromium.org/developers/design-documents/applescript/)
- [Chrome 59: AppleScript JS Disabled (Keyboard Maestro Forum)](https://forum.keyboardmaestro.com/t/chrome-59-executing-javascript-through-applescript-is-no-longer-supported/6763)
- [Chrome DevTools Protocol Official Docs](https://chromedevtools.github.io/devtools-protocol/)
- [python-cdp (GitHub)](https://github.com/HMaker/python-cdp)
- [PyChromeDevTools (GitHub)](https://github.com/marty90/PyChromeDevTools)
- [Pydoll (GitHub)](https://github.com/autoscrape-labs/pydoll)
- [Pydoll Official Site](https://pydoll.tech/)
- [CDP: The Invisible Engine (Caminho Solo)](https://www.caminhosolo.com.br/en/2026/03/chrome-devtools-protocol-automation/)
- [browser-use (GitHub)](https://github.com/browser-use/browser-use)
- [browser-use: Leaving Playwright for CDP](https://browser-use.com/posts/playwright-to-cdp)
- [browser-use Sessions (Medium)](https://sahilkumar1210.medium.com/mastering-browser-sessions-with-browser-use-the-backbone-of-reliable-ai-automations-f285e449f661)
- [11 Best AI Browser Agents in 2026 (Firecrawl)](https://www.firecrawl.dev/blog/best-browser-agents)
- [claude-playwright (GitHub)](https://github.com/smartlabsAT/claude-playwright)
- [What's New with Playwright in 2026 (Decipher)](https://getdecipher.com/blog/whats-new-with-playwright-in-2026)
- [Stagehand: Moving Beyond Playwright (Browserbase)](https://www.browserbase.com/blog/stagehand-playwright-evolution-browser-automation)
