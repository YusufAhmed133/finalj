"""
Intelligence Layer — Routes through Claude Cowork (Chrome extension).

Actions → EXECUTE_SCHEDULED_TASK (full computer use, skipPermissions)
Questions → Side panel or Claude browser fallback
"""
from jarvis.identity.loader import get_user_first_name, get_identity_string
from jarvis.utils.logger import get_logger

log = get_logger("brain.intelligence")


class Intelligence:

    def __init__(self):
        self._cowork = None
        self._browser = None
        self._ready = False

    def _system_context(self):
        from jarvis.identity.system_prompt import build_system_prompt
        return build_system_prompt()

    async def initialize(self) -> bool:
        # Try Cowork bridge first (best — full computer use)
        from jarvis.brain.cowork import CoworkBridge
        self._cowork = CoworkBridge()
        cowork_ok = await self._cowork.initialize()

        if cowork_ok:
            log.info("Intelligence: Cowork bridge (full computer use)")
            self._ready = True
            return True

        # Fallback to Claude browser
        log.info("Cowork not available, falling back to Claude browser")
        from jarvis.brain.claude_browser import ClaudeBrowser
        self._browser = ClaudeBrowser()
        ok = await self._browser.start()
        if ok:
            await self._browser.think(self._system_context())
            self._ready = True
            log.info("Intelligence: Claude browser (fallback)")
            return True

        log.error("No intelligence backend available")
        return False

    async def think(self, message: str, memory_context: str = "") -> str:
        if not self._ready:
            return "Not ready yet."

        prompt = message
        if memory_context:
            prompt = f"(Context: {memory_context[:1500]})\n{message}"

        # Everything goes to Cowork side panel — no action detection needed
        if self._cowork and self._cowork._ready:
            response = await self._cowork.send_and_read(prompt, timeout=45)
            if response:
                return self._clean(response)

        # Browser fallback
        if self._browser:
            try:
                raw = await self._browser.think_in_conversation(prompt)
                return self._clean(raw)
            except Exception as e:
                return f"Apologies sir: {str(e)[:100]}"

        return "No intelligence available."

    def _clean(self, text):
        noise = ["thinking about", "thought process", "thought for",
                 "concerns with", "connector search", "i need to be careful"]
        lines = [l for l in text.split("\n") if not any(n in l.lower() for n in noise)]
        return "\n".join(lines).strip() or text.strip()

    async def health_check(self):
        return {"cowork": self._cowork._ready if self._cowork else False, "ready": self._ready}

    async def shutdown(self):
        if self._browser:
            await self._browser.stop()
