"""
Claude.ai Browser Session Manager — Tier 1 Intelligence Layer.

Controls Chrome via Playwright CDP to interact with claude.ai.
User must be logged in with Claude Max subscription.

Architecture:
- Chrome launched with --remote-debugging-port=9222
- Playwright connects via connect_over_cdp()
- Uses the user's actual Chrome profile (session persists)
- Types prompts via keyboard events (contenteditable ProseMirror div)
- Reads streaming responses via DOM polling
- Parses structured output from Claude

DOM Notes (from research):
- Input: contenteditable div, NOT textarea
- Selectors: Use [contenteditable="true"], [role="textbox"], data-* attributes
- CSS classes are hashed and change across deployments — never rely on them
- Send: Enter key (not a button click, though button exists)
- Response: streams into a div; watch for completion signal
"""
import asyncio
import subprocess
import time
from typing import Optional

from jarvis.utils.logger import get_logger

log = get_logger("brain.claude_browser")

CLAUDE_URL = "https://claude.ai/new"
CDP_URL = "http://localhost:9222"
CHROME_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


class ClaudeBrowserSession:
    """Manages a persistent claude.ai browser session for Tier 1 intelligence."""

    def __init__(self, cdp_url: str = CDP_URL, headless: bool = False):
        self.cdp_url = cdp_url
        self.headless = headless
        self.browser = None
        self.context = None
        self.page = None
        self._playwright = None
        self._chrome_process = None

    async def ensure_chrome_running(self):
        """Launch Chrome with debugging port if not already running."""
        import httpx
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{self.cdp_url}/json/version", timeout=2.0)
                if resp.status_code == 200:
                    log.info("Chrome already running with debugging port")
                    return True
        except Exception:
            pass

        log.info("Starting Chrome with remote debugging port...")
        cmd = [
            CHROME_PATH,
            f"--remote-debugging-port=9222",
            "--no-first-run",
            "--no-default-browser-check",
        ]
        self._chrome_process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        # Wait for Chrome to start
        for _ in range(10):
            await asyncio.sleep(1)
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(f"{self.cdp_url}/json/version", timeout=2.0)
                    if resp.status_code == 200:
                        log.info("Chrome started successfully")
                        return True
            except Exception:
                continue

        log.error("Failed to start Chrome with debugging port")
        return False

    async def connect(self) -> bool:
        """Connect Playwright to Chrome via CDP."""
        try:
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()
            self.browser = await self._playwright.chromium.connect_over_cdp(self.cdp_url)
            contexts = self.browser.contexts
            if contexts:
                self.context = contexts[0]
            else:
                self.context = await self.browser.new_context()

            # Find or create claude.ai tab
            self.page = await self._find_or_create_claude_tab()
            log.info("Connected to Chrome, claude.ai tab ready")
            return True

        except Exception as e:
            log.error(f"Failed to connect to Chrome: {e}")
            return False

    async def _find_or_create_claude_tab(self):
        """Find an existing claude.ai tab or create a new one."""
        for page in self.context.pages:
            if "claude.ai" in page.url:
                log.info(f"Found existing claude.ai tab: {page.url}")
                return page

        # No existing tab — create one
        page = await self.context.new_page()
        await page.goto(CLAUDE_URL, wait_until="networkidle", timeout=30000)
        log.info(f"Created new claude.ai tab: {page.url}")
        return page

    async def is_logged_in(self) -> bool:
        """Check if user is logged into Claude."""
        try:
            # Look for the chat input — if present, user is logged in
            input_el = await self.page.query_selector(
                '[contenteditable="true"], [role="textbox"], textarea[placeholder]'
            )
            return input_el is not None
        except Exception:
            return False

    async def send_prompt(self, prompt: str, timeout: int = 120) -> str:
        """Send a prompt to Claude and wait for the complete response.

        Args:
            prompt: The text to send to Claude
            timeout: Maximum seconds to wait for response

        Returns:
            Claude's response text
        """
        if not self.page:
            raise RuntimeError("Not connected to claude.ai")

        # Navigate to new conversation if needed
        if "/new" not in self.page.url and "/chat/" not in self.page.url:
            await self.page.goto(CLAUDE_URL, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(2)

        # Find the input element
        input_selector = '[contenteditable="true"][role="textbox"], [contenteditable="true"][data-placeholder], div.ProseMirror[contenteditable="true"]'
        try:
            await self.page.wait_for_selector(input_selector, timeout=10000)
        except Exception:
            # Fallback: try any contenteditable
            input_selector = '[contenteditable="true"]'
            await self.page.wait_for_selector(input_selector, timeout=10000)

        input_el = await self.page.query_selector(input_selector)
        if not input_el:
            raise RuntimeError("Could not find chat input on claude.ai")

        # Click to focus
        await input_el.click()
        await asyncio.sleep(0.3)

        # Type the prompt using keyboard (necessary for ProseMirror/contenteditable)
        # Clear any existing text first
        await self.page.keyboard.press("Meta+a")
        await asyncio.sleep(0.1)

        # Type in chunks to avoid issues with very long prompts
        chunk_size = 500
        for i in range(0, len(prompt), chunk_size):
            chunk = prompt[i:i + chunk_size]
            await self.page.keyboard.type(chunk, delay=5)
            await asyncio.sleep(0.1)

        await asyncio.sleep(0.5)

        # Count existing response elements before sending
        response_count_before = await self._count_responses()

        # Send with Enter
        await self.page.keyboard.press("Enter")
        log.info("Prompt sent, waiting for response...")

        # Wait for response to start streaming
        response = await self._wait_for_response(response_count_before, timeout)
        return response

    async def _count_responses(self) -> int:
        """Count current response message elements."""
        # Claude's responses are in elements with specific data attributes
        # Try multiple selectors since DOM changes
        selectors = [
            '[data-is-streaming]',
            '[class*="response"]',
            '[class*="message"][class*="assistant"]',
            'div[data-testid*="message"]',
        ]
        for selector in selectors:
            elements = await self.page.query_selector_all(selector)
            if elements:
                return len(elements)
        # Fallback: count by role
        elements = await self.page.query_selector_all('[data-message-author-role="assistant"]')
        return len(elements)

    async def _wait_for_response(self, count_before: int, timeout: int) -> str:
        """Wait for Claude's response to complete streaming.

        Strategy:
        1. Wait for a new response element to appear
        2. Poll the response text until it stops changing (streaming complete)
        3. Return the final text
        """
        start = time.time()
        response_text = ""
        stable_count = 0

        while time.time() - start < timeout:
            await asyncio.sleep(1.0)

            # Try to get the latest response text
            current_text = await self._get_latest_response_text()

            if current_text and current_text != response_text:
                response_text = current_text
                stable_count = 0
            elif current_text:
                stable_count += 1

            # Check if streaming indicator is gone (response complete)
            is_streaming = await self._is_streaming()

            if not is_streaming and response_text and stable_count >= 2:
                log.info(f"Response complete ({len(response_text)} chars)")
                return response_text

            # Also check if stop button is gone as completion signal
            if response_text and stable_count >= 3:
                log.info(f"Response stable for 3 polls ({len(response_text)} chars)")
                return response_text

        if response_text:
            log.warning(f"Response timeout but got partial text ({len(response_text)} chars)")
            return response_text

        raise TimeoutError(f"No response from claude.ai within {timeout}s")

    async def _get_latest_response_text(self) -> str:
        """Extract text from the most recent assistant response."""
        # Try multiple selector strategies
        text = await self.page.evaluate("""() => {
            // Strategy 1: Find by data attribute
            const msgs = document.querySelectorAll('[data-message-author-role="assistant"]');
            if (msgs.length > 0) {
                return msgs[msgs.length - 1].innerText;
            }
            // Strategy 2: Find by class patterns
            const responses = document.querySelectorAll('[class*="response"], [class*="assistant"]');
            if (responses.length > 0) {
                return responses[responses.length - 1].innerText;
            }
            // Strategy 3: Find the last message-like container
            const containers = document.querySelectorAll('[data-testid*="message"]');
            if (containers.length > 0) {
                return containers[containers.length - 1].innerText;
            }
            return '';
        }""")
        return text.strip() if text else ""

    async def _is_streaming(self) -> bool:
        """Check if Claude is still generating a response."""
        return await self.page.evaluate("""() => {
            // Check for streaming indicator
            const streaming = document.querySelector('[data-is-streaming="true"]');
            if (streaming) return true;
            // Check for stop button (visible during generation)
            const stopBtn = document.querySelector('button[aria-label="Stop"], button[aria-label="Stop generating"]');
            if (stopBtn && stopBtn.offsetParent !== null) return true;
            return false;
        }""")

    async def new_conversation(self):
        """Start a new conversation."""
        await self.page.goto(CLAUDE_URL, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(2)
        log.info("Started new conversation")

    async def disconnect(self):
        """Disconnect from Chrome (doesn't close Chrome)."""
        if self.browser:
            await self.browser.close()
            self.browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        log.info("Disconnected from Chrome")

    async def health_check(self) -> dict:
        """Check session health."""
        status = {
            "connected": self.browser is not None,
            "page_url": self.page.url if self.page else None,
            "logged_in": False,
        }
        if self.page:
            try:
                status["logged_in"] = await self.is_logged_in()
            except Exception:
                status["logged_in"] = False
        return status
