"""
Claude.ai Browser Session — Tier 1 Intelligence.

Opens claude.ai in a persistent Playwright browser session via Chrome CDP.
User must be logged in with Claude Max. Session cookies persist in Chrome's profile.

Usage:
    brain = ClaudeBrowser()
    await brain.start()
    response = await brain.think("What is 2+2?")
    print(response)

Architecture:
    1. Launch Chrome with --remote-debugging-port=9222 (or connect to existing)
    2. Connect Playwright via connect_over_cdp()
    3. Navigate to claude.ai/new
    4. Type prompt via keyboard (contenteditable ProseMirror div)
    5. Wait for streaming response to complete
    6. Read response text, return it
"""
import asyncio
import subprocess
import time
from pathlib import Path
from typing import Optional

from jarvis.utils.logger import get_logger

log = get_logger("brain.claude_browser")

CLAUDE_URL = "https://claude.ai/new"
CDP_ENDPOINT = "http://localhost:9222"
CHROME_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
CHROME_PROFILE = Path.home() / "Library" / "Application Support" / "Google" / "Chrome-JARVIS"

# Selectors from research (greasyfork userscripts, Agora project)
INPUT_SELECTORS = [
    'div.ProseMirror[contenteditable="true"]',          # Primary: ProseMirror editor
    '[contenteditable="true"][role="textbox"]',          # Fallback
    'div[contenteditable="true"][translate="no"]',       # Fallback
    '[contenteditable="true"]',                          # Last resort
]

RESPONSE_JS = """() => {
    var msgs = document.querySelectorAll('.font-claude-response');
    if (msgs.length > 0) return msgs[msgs.length - 1].innerText;
    var turns = document.querySelectorAll('div[data-test-render-count]');
    if (turns.length > 0) return turns[turns.length - 1].innerText;
    var md = document.querySelectorAll('[class*="markdown"]');
    if (md.length > 0) return md[md.length - 1].innerText;
    return '';
}"""

STREAMING_JS = """() => {
    // Check data-is-streaming attribute
    if (document.querySelector('[data-is-streaming="true"]')) return true;
    // Check for visible stop button
    const btns = document.querySelectorAll('button');
    for (const btn of btns) {
        const label = (btn.getAttribute('aria-label') || btn.innerText || '').toLowerCase();
        if (label.includes('stop') && btn.offsetParent !== null) return true;
    }
    return false;
}"""


class ClaudeBrowser:
    """Persistent claude.ai browser session for Tier 1 intelligence."""

    def __init__(self):
        self._playwright = None
        self._browser = None
        self._page = None
        self._chrome_proc = None
        self._started = False

    async def start(self) -> bool:
        """Start Chrome and connect Playwright."""
        # Ensure Chrome is running with debugging port
        if not await self._ensure_chrome():
            return False

        # Connect Playwright
        try:
            from playwright.async_api import async_playwright
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.connect_over_cdp(CDP_ENDPOINT)

            # Use first existing context (has cookies/session)
            contexts = self._browser.contexts
            if contexts:
                ctx = contexts[0]
            else:
                ctx = await self._browser.new_context()

            # Find or create claude.ai tab
            self._page = None
            for page in ctx.pages:
                if "claude.ai" in page.url:
                    self._page = page
                    log.info(f"Found existing claude.ai tab: {page.url}")
                    break

            if not self._page:
                self._page = await ctx.new_page()
                await self._page.goto(CLAUDE_URL, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(3)
                log.info("Opened new claude.ai tab")

            # Check if logged in
            logged_in = await self._is_logged_in()
            if not logged_in:
                log.error("Not logged into claude.ai. Log in manually in Chrome first.")
                return False

            self._started = True
            log.info("Claude browser session ready")
            return True

        except Exception as e:
            log.error(f"Failed to connect: {e}")
            return False

    async def _ensure_chrome(self) -> bool:
        """Make sure Chrome is running with remote debugging port."""
        import httpx
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(f"{CDP_ENDPOINT}/json/version", timeout=2)
                if r.status_code == 200:
                    log.info("Chrome already running with CDP")
                    return True
        except Exception:
            pass

        log.info("Launching Chrome with --remote-debugging-port=9222...")
        CHROME_PROFILE.mkdir(parents=True, exist_ok=True)
        self._chrome_proc = subprocess.Popen(
            [CHROME_PATH, "--remote-debugging-port=9222", "--no-first-run",
             "--no-default-browser-check", f"--user-data-dir={CHROME_PROFILE}"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

        for _ in range(15):
            await asyncio.sleep(1)
            try:
                async with httpx.AsyncClient() as client:
                    r = await client.get(f"{CDP_ENDPOINT}/json/version", timeout=2)
                    if r.status_code == 200:
                        log.info("Chrome launched")
                        return True
            except Exception:
                continue

        log.error("Chrome failed to start")
        return False

    async def _is_logged_in(self) -> bool:
        """Check if user is logged into claude.ai."""
        try:
            for sel in INPUT_SELECTORS:
                el = await self._page.query_selector(sel)
                if el:
                    return True
            return False
        except Exception:
            return False

    async def _reconnect(self):
        """Reconnect to Chrome if connection dropped."""
        log.warning("Reconnecting to Chrome...")
        try:
            if self._browser:
                await self._browser.close()
        except Exception:
            pass
        try:
            if self._playwright:
                await self._playwright.stop()
        except Exception:
            pass
        self._started = False
        return await self.start()

    async def think(self, prompt: str, timeout: int = 120) -> str:
        """Send a prompt in a NEW conversation and return the response."""
        try:
            if not self._started:
                await self._reconnect()
            await self._page.goto(CLAUDE_URL, wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(1)
            return await self._send_and_read(prompt, timeout)
        except Exception as e:
            if "closed" in str(e).lower() or "target" in str(e).lower():
                log.warning(f"Connection lost: {e}. Reconnecting...")
                if await self._reconnect():
                    await self._page.goto(CLAUDE_URL, wait_until="domcontentloaded", timeout=20000)
                    await asyncio.sleep(1)
                    return await self._send_and_read(prompt, timeout)
            raise

    async def think_in_conversation(self, prompt: str, timeout: int = 120) -> str:
        """Send a prompt in the CURRENT conversation (no navigation)."""
        try:
            if not self._started:
                await self._reconnect()
            return await self._send_and_read(prompt, timeout)
        except Exception as e:
            if "closed" in str(e).lower() or "target" in str(e).lower():
                log.warning(f"Connection lost: {e}. Reconnecting...")
                if await self._reconnect():
                    return await self._send_and_read(prompt, timeout)
            raise

    async def new_conversation(self):
        """Navigate to a fresh conversation."""
        await self._page.goto(CLAUDE_URL, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(1)

    async def _send_and_read(self, prompt: str, timeout: int) -> str:
        """Fast send + mutation-based response detection."""
        self._turn_count = getattr(self, '_turn_count', 0) + 1

        # Start fresh conversation every 8 turns to prevent slowdown
        if self._turn_count > 8:
            log.info("Conversation getting long, starting fresh")
            await self._page.goto(CLAUDE_URL, wait_until="domcontentloaded", timeout=15000)
            await asyncio.sleep(1)
            self._turn_count = 1

        # Fast text input via execCommand (instant, no clipboard permissions)
        await self._page.evaluate("""(text) => {
            const el = document.querySelector('div.ProseMirror[contenteditable="true"]')
                    || document.querySelector('[contenteditable="true"]');
            if (!el) return;
            el.focus();
            // Select all existing text and replace
            document.execCommand('selectAll', false, null);
            document.execCommand('insertText', false, text);
            el.dispatchEvent(new Event('input', { bubbles: true }));
        }""", prompt)

        await asyncio.sleep(0.1)
        await self._page.keyboard.press("Enter")
        log.info("Prompt sent, waiting for response...")

        # Wait for response using mutation-based detection (much faster than polling)
        response = await self._wait_for_response(timeout)
        log.info(f"Response received ({len(response)} chars)")
        return response

    async def _wait_for_response(self, timeout: int) -> str:
        """Wait for response: fast poll with early exit."""
        start = time.time()
        last_text = ""
        stable = 0

        # Initial wait for response to start appearing
        await asyncio.sleep(1.5)

        while time.time() - start < timeout:
            text = await self._page.evaluate(RESPONSE_JS)
            text = text.strip() if text else ""

            if text and text != last_text:
                last_text = text
                stable = 0
            elif text:
                stable += 1
                # 2 stable reads = done (each 0.5s apart = 1s of no change)
                if stable >= 2:
                    return last_text

            await asyncio.sleep(0.5)

        return last_text or ""

    async def stop(self):
        """Disconnect (doesn't close Chrome)."""
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._started = False
        log.info("Claude browser disconnected")
