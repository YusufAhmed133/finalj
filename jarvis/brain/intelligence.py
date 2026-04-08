"""
Unified Intelligence Interface.

Switches between Tier 1 (browser) and Tier 2 (API) based on config.
Provides a single interface for the rest of JARVIS to use.
"""
import asyncio
import yaml
from pathlib import Path
from typing import Optional

from jarvis.utils.logger import get_logger
from jarvis.utils.crypto import load_secrets

log = get_logger("brain.intelligence")

CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "agents.yaml"
IDENTITY_PATH = Path(__file__).parent.parent / "identity" / "yusuf.yaml"


def _load_identity() -> str:
    """Load Yusuf's identity as context string."""
    if IDENTITY_PATH.exists():
        data = yaml.safe_load(IDENTITY_PATH.read_text())
        lines = [
            f"User: {data.get('name', 'Yusuf Ahmed')}, {data.get('age', 18)} years old",
            f"Location: {data.get('location', {}).get('city', 'Sydney')}, {data.get('location', {}).get('country', 'Australia')}",
            f"Timezone: {data.get('location', {}).get('timezone', 'Australia/Sydney')}",
            f"Education: {data.get('education', {}).get('university', 'UNSW')} — {data.get('education', {}).get('degree', '')}",
            f"Communication: {data.get('communication_style', {}).get('tone', 'Direct, informal')}",
            f"Health: Cardiac device implanted — cardiac alerts are ALWAYS priority, NEVER suppressed",
        ]
        return "\n".join(lines)
    return "User: Yusuf Ahmed, Sydney, Australia"


class Intelligence:
    """Unified intelligence interface — routes to Tier 1 or Tier 2."""

    def __init__(self):
        self.tier = 1
        self._browser_session = None
        self._api_client = None
        self._identity = _load_identity()
        self._system_prompt = self._build_system_prompt()

    def _build_system_prompt(self) -> str:
        """Build the system prompt sent with every query."""
        return f"""You are JARVIS, a personal AI assistant for Yusuf Ahmed.

{self._identity}

You respond in a structured format. Every response MUST be valid JSON with these fields:
{{
    "reply": "The message to send back to Yusuf via Telegram",
    "action": null or {{
        "type": "action_type",
        "details": "what to do"
    }},
    "remember": null or "what to store in memory for future reference",
    "mood": "brief assessment of urgency/tone"
}}

Rules:
- Be direct, informal, zero fluff — match Yusuf's communication style
- Australian English (colour, organisation, defence)
- AUD for money, AEST/AEDT for times
- AGLC4 for legal citations
- Cardiac health alerts are ALWAYS top priority
- Never validate uncritically — push back when something is wrong
- If an action is needed on the Mac, specify it clearly in the action field"""

    async def initialize(self) -> bool:
        """Initialize the appropriate intelligence tier."""
        secrets = load_secrets()
        tier_str = secrets.get("INTELLIGENCE_TIER", "1")
        self.tier = int(tier_str) if tier_str.isdigit() else 1

        if self.tier == 2:
            api_key = secrets.get("ANTHROPIC_API_KEY", "")
            if not api_key:
                log.warning("Tier 2 selected but no API key found. Falling back to Tier 1.")
                self.tier = 1
            else:
                from jarvis.brain.claude_api import ClaudeAPIClient
                self._api_client = ClaudeAPIClient(api_key)
                log.info("Intelligence layer: Tier 2 (API)")
                return True

        if self.tier == 1:
            from jarvis.brain.claude_browser import ClaudeBrowserSession
            self._browser_session = ClaudeBrowserSession()
            chrome_ok = await self._browser_session.ensure_chrome_running()
            if not chrome_ok:
                log.error("Failed to start Chrome. Intelligence layer unavailable.")
                return False
            connected = await self._browser_session.connect()
            if not connected:
                log.error("Failed to connect to Chrome. Intelligence layer unavailable.")
                return False
            logged_in = await self._browser_session.is_logged_in()
            if not logged_in:
                log.warning("Not logged into claude.ai. Please log in manually.")
                return False
            log.info("Intelligence layer: Tier 1 (Browser)")
            return True

        return False

    async def think(
        self,
        message: str,
        context: str = "",
        memory_context: str = "",
    ) -> str:
        """Send a message to Claude and get a response.

        Args:
            message: Yusuf's message or the orchestrator's query
            context: Current state context (time, mode, etc.)
            memory_context: Relevant memories from the spine

        Returns:
            Claude's response (raw text — caller parses JSON)
        """
        full_prompt = self._build_full_prompt(message, context, memory_context)

        if self.tier == 2 and self._api_client:
            return await self._api_client.send_prompt(full_prompt, system=self._system_prompt)
        elif self.tier == 1 and self._browser_session:
            # For browser, system prompt is included in the message itself
            browser_prompt = f"{self._system_prompt}\n\n---\n\n{full_prompt}"
            return await self._browser_session.send_prompt(browser_prompt)
        else:
            raise RuntimeError("Intelligence layer not initialized")

    def _build_full_prompt(self, message: str, context: str, memory_context: str) -> str:
        """Build the full prompt with all context."""
        parts = []

        if context:
            parts.append(f"Current state:\n{context}")

        if memory_context:
            parts.append(f"Relevant memories:\n{memory_context}")

        parts.append(f"Yusuf's message:\n{message}")

        return "\n\n---\n\n".join(parts)

    async def health_check(self) -> dict:
        """Check intelligence layer health."""
        if self.tier == 2 and self._api_client:
            return {"tier": 2, **self._api_client.health_check()}
        elif self.tier == 1 and self._browser_session:
            return {"tier": 1, **(await self._browser_session.health_check())}
        return {"tier": self.tier, "connected": False, "error": "Not initialized"}

    async def shutdown(self):
        """Clean shutdown."""
        if self._browser_session:
            await self._browser_session.disconnect()
        log.info("Intelligence layer shut down")
