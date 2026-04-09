"""
Unified Intelligence Interface.
One persistent conversation on claude.ai. Context sent once. Alfred tone.
"""
from jarvis.identity.loader import get_user_name, get_user_first_name, get_identity_string
from jarvis.utils.logger import get_logger
from jarvis.utils.crypto import load_secrets

log = get_logger("brain.intelligence")


class Intelligence:

    def __init__(self):
        self.tier = 1
        self._browser = None
        self._api_client = None
        self._ready = False

    def _identity_prompt(self) -> str:
        name = get_user_first_name()
        identity = get_identity_string()
        return (
            f"You are JARVIS — a personal AI assistant modelled after Alfred Pennyworth "
            f"from Batman. You are British, dry-witted, warmly sarcastic, fiercely loyal, "
            f"and supremely competent. You call the user 'sir' occasionally but not every message. "
            f"You are concise — never more than 2-3 sentences unless asked for detail. "
            f"Never say 'Thinking about concerns' or any meta-commentary about your process. "
            f"Just answer directly.\n\n"
            f"The person you serve:\n{identity}\n\n"
            f"If {name} asks you to do something on the Mac (open an app, go to a website, "
            f"play music, etc), respond with EXACTLY this format on its own line:\n"
            f"DO: <applescript or shell command>\n"
            f"Then add a brief confirmation message after.\n"
            f"Example: if asked to open Spotify:\n"
            f"DO: tell application \"Spotify\" to activate\n"
            f"Spotify is on its way, sir.\n\n"
            f"For everything else, just respond naturally. No JSON. No markdown. No fluff. Go."
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
                self._ready = True
                return True
            self.tier = 1

        if self.tier == 1:
            from jarvis.brain.claude_browser import ClaudeBrowser
            self._browser = ClaudeBrowser()
            ok = await self._browser.start()
            if not ok:
                log.error("Browser failed to start")
                return False

            # Send identity prompt ONCE in a new conversation
            log.info("Loading JARVIS personality into conversation...")
            await self._browser.think(self._identity_prompt())
            log.info("Personality loaded. JARVIS ready.")
            self._ready = True
            return True

        return False

    async def think(self, message: str, memory_context: str = "") -> str:
        """Send message in the EXISTING conversation. No new conversation. No context dump."""
        if not self._ready:
            return "Not ready yet."

        # Simple prompt — just the message. Context is already in the conversation.
        prompt = message
        if memory_context:
            prompt = f"(Context: {memory_context[:300]})\n{message}"

        if self.tier == 2 and self._api_client:
            return await self._api_client.send_prompt(prompt, system=self._identity_prompt())
        elif self.tier == 1 and self._browser:
            raw = await self._browser.think_in_conversation(prompt)
            return self._clean(raw)

        return "Intelligence offline."

    def _clean(self, text: str) -> str:
        """Strip Claude's thinking artifacts."""
        lines = []
        for line in text.split("\n"):
            # Skip thinking/safety text
            if any(noise in line for noise in [
                "Thinking about", "thinking about",
                "concerns with this request",
                "I need to be careful",
                "Let me think about",
            ]):
                continue
            lines.append(line)
        return "\n".join(lines).strip()

    async def health_check(self) -> dict:
        return {"tier": self.tier, "ready": self._ready}

    async def shutdown(self):
        if self._browser:
            await self._browser.stop()
