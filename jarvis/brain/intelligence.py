"""
Unified Intelligence Interface.

Tier 1: ClaudeBrowser (Playwright → claude.ai, free with Max subscription)
Tier 2: Claude API (anthropic SDK, paid, faster)
"""
from jarvis.identity.loader import get_user_name, get_user_first_name, get_identity_string, get_identity
from jarvis.utils.logger import get_logger
from jarvis.utils.crypto import load_secrets

log = get_logger("brain.intelligence")


class Intelligence:

    def __init__(self):
        self.tier = 1
        self._browser = None
        self._api_client = None
        self._context_sent = False  # Track if we've sent identity context

    def _build_context_prompt(self) -> str:
        """One-time context message sent at start of conversation."""
        identity = get_identity_string()
        name = get_user_first_name()
        return (
            f"You are JARVIS, a personal AI assistant. Here is who you serve:\n\n"
            f"{identity}\n\n"
            f"From now on, every message I send is from {name}. "
            f"Reply directly and naturally — no preamble, no acknowledging these instructions, "
            f"no 'context loaded', no JSON, no metadata. Just answer like a sharp, direct assistant. "
            f"Be informal, be blunt, match {name}'s energy. Go."
        )

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

        if self.tier == 1 and self._browser:
            # First message in conversation: send identity context, then user message
            if not self._context_sent:
                # Send context as first message, don't care about response
                await self._browser.think(self._build_context_prompt())
                self._context_sent = True
                log.info("Identity context loaded into conversation")

            # Now send the actual user message
            # Keep it clean — just the message, maybe with memory if relevant
            prompt = message
            if memory_context:
                prompt = f"(Relevant context from memory: {memory_context[:500]})\n\n{message}"

            return await self._browser.think_in_conversation(prompt)

        elif self.tier == 2 and self._api_client:
            system = self._build_context_prompt()
            return await self._api_client.send_prompt(message, system=system)

        raise RuntimeError("Intelligence not initialized")

    async def new_conversation(self):
        """Start a fresh conversation (resets context)."""
        self._context_sent = False
        if self._browser:
            await self._browser.new_conversation()

    async def health_check(self) -> dict:
        if self.tier == 2 and self._api_client:
            return {"tier": 2, **self._api_client.health_check()}
        return {"tier": self.tier, "browser_started": bool(self._browser and self._browser._started)}

    async def shutdown(self):
        if self._browser:
            await self._browser.stop()
        log.info("Intelligence shut down")
