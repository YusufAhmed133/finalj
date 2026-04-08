"""
Unified Intelligence Interface.

Tier 1: ClaudeBrowser (Playwright → claude.ai, free with Max subscription)
Tier 2: Claude API (anthropic SDK, paid, faster)

Config switch via INTELLIGENCE_TIER in secrets.env.
"""
import json
from typing import Optional

from jarvis.identity.loader import get_user_name, get_user_first_name, get_identity_string, get_identity
from jarvis.utils.logger import get_logger
from jarvis.utils.crypto import load_secrets

log = get_logger("brain.intelligence")


class Intelligence:

    def __init__(self):
        self.tier = 1
        self._browser = None
        self._api_client = None
        self._user_name = get_user_name()
        self._identity = get_identity_string()

    def _build_system_prompt(self) -> str:
        user = get_identity()
        style = user.get("communication_style", {})
        return f"""You are JARVIS, a personal AI assistant for {self._user_name}.

{self._identity}

Rules:
- Be direct, informal, zero fluff
- Respond naturally as a helpful AI assistant
- If an action is needed on the Mac, say so clearly
- Cardiac health alerts are ALWAYS top priority
- Never validate uncritically — push back when something is wrong
- {style.get('language', 'English')}"""

    async def initialize(self) -> bool:
        secrets = load_secrets()
        tier_str = secrets.get("INTELLIGENCE_TIER", "1")
        self.tier = int(tier_str) if tier_str.isdigit() else 1

        if self.tier == 2:
            api_key = secrets.get("ANTHROPIC_API_KEY", "")
            if api_key:
                from jarvis.brain.claude_api import ClaudeAPIClient
                self._api_client = ClaudeAPIClient(api_key)
                log.info("Intelligence: Tier 2 (API)")
                return True
            log.warning("No API key, falling back to Tier 1")
            self.tier = 1

        if self.tier == 1:
            from jarvis.brain.claude_browser import ClaudeBrowser
            self._browser = ClaudeBrowser()
            ok = await self._browser.start()
            if ok:
                log.info("Intelligence: Tier 1 (Browser)")
                return True
            log.error("Browser failed to start")
            return False

        return False

    async def think(self, message: str, context: str = "", memory_context: str = "") -> str:
        """Send a message to Claude, return the response."""
        system = self._build_system_prompt()
        parts = [system, "---"]

        if context:
            parts.append(f"Current state:\n{context}")
        if memory_context:
            parts.append(f"Relevant memories:\n{memory_context}")

        parts.append(f"{get_user_first_name()}: {message}")

        full_prompt = "\n\n".join(parts)

        if self.tier == 2 and self._api_client:
            return await self._api_client.send_prompt(message, system=system)
        elif self.tier == 1 and self._browser:
            return await self._browser.think(full_prompt)
        else:
            raise RuntimeError("Intelligence not initialized")

    async def health_check(self) -> dict:
        if self.tier == 2 and self._api_client:
            return {"tier": 2, **self._api_client.health_check()}
        return {"tier": self.tier, "browser_started": bool(self._browser and self._browser._started)}

    async def shutdown(self):
        if self._browser:
            await self._browser.stop()
        log.info("Intelligence shut down")
