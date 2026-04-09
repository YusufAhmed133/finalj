"""
Intelligence Layer — Gemini 2.0 Flash (free, fast, vision).

No more browser automation. Direct API calls. ~1-2s responses.
Vision capable for screen reading.
"""
import base64
import subprocess
from pathlib import Path

import google.generativeai as genai

from jarvis.identity.loader import get_user_name, get_user_first_name, get_identity_string
from jarvis.utils.logger import get_logger
from jarvis.utils.crypto import load_secrets

log = get_logger("brain.intelligence")


class Intelligence:

    def __init__(self):
        self._model = None
        self._chat = None
        self._browser = None
        self._use_browser = False
        self._ready = False

    def _system_prompt(self):
        name = get_user_first_name()
        identity = get_identity_string()
        return (
            f"You are JARVIS — a personal AI assistant modelled after Alfred Pennyworth "
            f"from Batman. British, dry-witted, warmly sarcastic, fiercely loyal, "
            f"supremely competent. You call the user 'sir' occasionally but not every message. "
            f"Concise — 1-3 sentences max unless asked for detail. "
            f"Never say meta-commentary about your thinking process. Just answer.\n\n"
            f"The person you serve:\n{identity}\n\n"
            f"If {name} asks you to do something on the Mac (open app, play music, "
            f"go to website, control volume, etc), respond with EXACTLY this format "
            f"on its own line:\nDO: <applescript or shell command>\n"
            f"Then add a brief confirmation after.\n\n"
            f"For everything else, just respond naturally. No JSON. No markdown headers. No fluff."
        )

    async def initialize(self) -> bool:
        secrets = load_secrets()

        # Try Gemini first (fast, free)
        gemini_key = secrets.get("GEMINI_API_KEY", "")
        if gemini_key:
            try:
                genai.configure(api_key=gemini_key)
                self._model = genai.GenerativeModel(
                    "gemini-2.0-flash",
                    system_instruction=self._system_prompt(),
                )
                # Test with a quick call
                self._chat = self._model.start_chat()
                test = self._chat.send_message("Say 'ready' and nothing else.")
                if test.text:
                    self._ready = True
                    log.info("Intelligence: Gemini 2.0 Flash")
                    return True
            except Exception as e:
                log.warning(f"Gemini failed: {e}")
                log.info("Falling back to Claude browser...")

        # Fallback: Claude browser (slow but works)
        try:
            from jarvis.brain.claude_browser import ClaudeBrowser
            self._browser = ClaudeBrowser()
            ok = await self._browser.start()
            if ok:
                self._use_browser = True
                self._ready = True
                # Send personality prompt
                await self._browser.think(self._system_prompt())
                log.info("Intelligence: Claude browser (fallback)")
                return True
        except Exception as e:
            log.error(f"Claude browser also failed: {e}")

        return False

    async def think(self, message: str, memory_context: str = "") -> str:
        """Send message, get response."""
        if not self._ready:
            return "Intelligence not ready."

        prompt = message
        if memory_context:
            prompt = f"(Context: {memory_context[:300]})\n{message}"

        # Gemini path
        if self._model and not getattr(self, '_use_browser', False):
            try:
                response = self._chat.send_message(prompt)
                return self._clean(response.text.strip())
            except Exception as e:
                log.error(f"Gemini error: {e}")
                try:
                    self._chat = self._model.start_chat()
                    response = self._chat.send_message(prompt)
                    return self._clean(response.text.strip())
                except Exception as e2:
                    return f"Apologies sir, something went wrong: {str(e2)[:150]}"

        # Claude browser path
        if getattr(self, '_use_browser', False) and getattr(self, '_browser', None):
            try:
                raw = await self._browser.think_in_conversation(prompt)
                return self._clean(raw)
            except Exception as e:
                return f"Apologies sir, something went wrong: {str(e)[:150]}"

        return "No intelligence engine available."

    async def think_with_screenshot(self, message: str) -> str:
        """Send message + screenshot of current screen. For visual tasks."""
        if not self._ready:
            return "Intelligence not ready."

        # Take screenshot
        path = "/tmp/jarvis_screen.png"
        subprocess.run(["screencapture", "-x", path], timeout=5, capture_output=True)

        try:
            import PIL.Image
            img = PIL.Image.open(path)
            response = self._model.generate_content([message, img])
            return self._clean(response.text.strip())
        except Exception as e:
            log.error(f"Vision error: {e}")
            return await self.think(message)

    def _clean(self, text: str) -> str:
        """Strip thinking artifacts."""
        noise = ["thinking about", "thought process", "concerns with",
                 "i need to be careful", "let me think", "i should be",
                 "user request", "this request", "allowed"]
        lines = []
        for line in text.split("\n"):
            if any(n in line.lower() for n in noise):
                continue
            lines.append(line)
        result = "\n".join(lines).strip()
        return result if result else text.strip()

    async def health_check(self) -> dict:
        return {"engine": "gemini-2.0-flash", "ready": self._ready}

    async def shutdown(self):
        log.info("Intelligence shut down")
