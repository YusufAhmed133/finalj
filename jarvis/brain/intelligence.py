"""
Intelligence Layer — Claude browser, single session, context once.
Instant commands bypass this entirely (handled by instant_mac.py).
"""
from jarvis.identity.loader import get_user_name, get_user_first_name, get_identity_string
from jarvis.utils.logger import get_logger

log = get_logger("brain.intelligence")


class Intelligence:

    def __init__(self):
        self._browser = None
        self._ready = False

    def _system_prompt(self):
        name = get_user_first_name()
        identity = get_identity_string()
        return (
            f"You are JARVIS — modelled after Alfred Pennyworth from Batman. "
            f"British, dry-witted, warmly sarcastic, loyal, competent. "
            f"Call the user 'sir' occasionally. 1-3 sentences max. "
            f"Never say anything about your thinking process. Just answer.\n\n"
            f"User:\n{identity}\n\n"
            f"If asked to do something on Mac, respond with:\n"
            f"DO: <applescript command>\nThen a brief confirmation.\n"
            f"Otherwise just respond naturally. No JSON. No markdown. No fluff."
        )

    async def initialize(self) -> bool:
        from jarvis.brain.claude_browser import ClaudeBrowser
        self._browser = ClaudeBrowser()
        ok = await self._browser.start()
        if not ok:
            log.error("Browser failed to start")
            return False

        # Single session — send personality ONCE
        log.info("Loading personality into session...")
        await self._browser.think(self._system_prompt())
        self._ready = True
        log.info("Intelligence: Claude browser (single session)")
        return True

    async def think(self, message: str, memory_context: str = "") -> str:
        if not self._ready:
            return "Not ready yet."

        prompt = message
        if memory_context:
            prompt = f"(Context: {memory_context[:300]})\n{message}"

        try:
            raw = await self._browser.think_in_conversation(prompt)
            return self._clean(raw)
        except Exception as e:
            log.error(f"Error: {e}")
            # Try reconnect
            try:
                await self._browser._reconnect()
                await self._browser.think(self._system_prompt())
                raw = await self._browser.think_in_conversation(prompt)
                return self._clean(raw)
            except Exception as e2:
                return f"Apologies sir, something went wrong: {str(e2)[:100]}"

    def _clean(self, text: str) -> str:
        noise = ["thinking about", "thought process", "concerns with",
                 "i need to be careful", "let me think", "i should be",
                 "user request", "this request", "allowed", "marshaled"]
        lines = []
        for line in text.split("\n"):
            if any(n in line.lower() for n in noise):
                continue
            lines.append(line)
        result = "\n".join(lines).strip()
        return result if result else text.strip()

    async def health_check(self) -> dict:
        return {"engine": "claude-browser", "ready": self._ready}

    async def shutdown(self):
        if self._browser:
            await self._browser.stop()
