"""
Cowork Bridge — Type directly into Claude Chrome extension side panel.

Uses CDP WebSocket to find the side panel page, inject text into the
ProseMirror editor, click send, and read the response.

This gives Claude full Cowork capabilities — computer use, connectors,
browser control — because it runs IN the extension with full permissions.
"""
import asyncio
import json
import time
import urllib.request

import websockets

from jarvis.utils.logger import get_logger

log = get_logger("brain.cowork")

CDP_URL = "http://localhost:9222"
EXT_ID = "fcoeoabgfenejglbffodgkkbkcdhcgfn"


def _get_targets():
    try:
        return json.loads(urllib.request.urlopen(f"{CDP_URL}/json", timeout=3).read())
    except Exception:
        return []


def _find_sidepanel():
    """Find the Claude extension side panel page."""
    for t in _get_targets():
        if t.get("type") == "page" and EXT_ID in t.get("url", "") and "sidepanel" in t.get("url", ""):
            return t.get("webSocketDebuggerUrl")
    return None


class CoworkBridge:
    """Type into Claude's side panel, read responses. Full Cowork permissions."""

    def __init__(self):
        self._ready = False

    async def initialize(self) -> bool:
        sp = _find_sidepanel()
        if sp:
            self._ready = True
            log.info("Cowork bridge: side panel found")
            return True
        log.warning("Cowork bridge: side panel not found. Open Claude extension in Chrome.")
        return False

    async def send_and_read(self, prompt: str, timeout: int = 60) -> str:
        """Type prompt into side panel via CDP keyboard events, click send, read response."""
        sp_url = _find_sidepanel()
        if not sp_url:
            return "Cowork side panel not found. Open the Claude extension in Chrome."

        try:
            async with websockets.connect(sp_url) as ws:
                # Step 1: Focus editor
                await ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate", "params": {
                    "expression": "document.querySelector('.ProseMirror')?.focus(); 'ok'",
                    "returnByValue": True
                }}))
                await asyncio.wait_for(ws.recv(), timeout=3)
                await asyncio.sleep(0.2)

                # Step 2: Clear any existing text (Cmd+A then Delete)
                for key_info in [
                    {"key": "a", "code": "KeyA", "modifiers": 4},  # Cmd+A
                    {"key": "Backspace", "code": "Backspace"},      # Delete
                ]:
                    mods = key_info.pop("modifiers", 0)
                    await ws.send(json.dumps({"id": 2, "method": "Input.dispatchKeyEvent",
                        "params": {"type": "keyDown", "modifiers": mods, **key_info}}))
                    await asyncio.wait_for(ws.recv(), timeout=2)
                    await ws.send(json.dumps({"id": 2, "method": "Input.dispatchKeyEvent",
                        "params": {"type": "keyUp", "modifiers": mods, **key_info}}))
                    await asyncio.wait_for(ws.recv(), timeout=2)

                await asyncio.sleep(0.1)

                # Step 3: Type prompt character by character via CDP keyboard events
                for char in prompt:
                    await ws.send(json.dumps({"id": 3, "method": "Input.dispatchKeyEvent",
                        "params": {"type": "char", "text": char}}))
                    await asyncio.wait_for(ws.recv(), timeout=2)

                await asyncio.sleep(0.3)

                # Step 4: Click send button
                await ws.send(json.dumps({"id": 4, "method": "Runtime.evaluate", "params": {
                    "expression": """
                    (() => {
                        const btn = document.querySelector('[aria-label="Send message"]');
                        if (btn && !btn.disabled) { btn.click(); return 'sent'; }
                        return 'send_disabled';
                    })()
                    """,
                    "returnByValue": True
                }}))
                result = await asyncio.wait_for(ws.recv(), timeout=3)
                status = json.loads(result).get("result", {}).get("result", {}).get("value", "")
                log.info(f"Cowork: {status}")

                if status != "sent":
                    return "Could not send to Cowork — send button disabled."

        except Exception as e:
            log.error(f"Cowork send error: {e}")
            return f"Cowork error: {str(e)[:100]}"

        # Step 5: Wait for response
        return await self._read_response(timeout)

    async def _read_response(self, timeout: int = 60) -> str:
        """Poll the side panel for Claude's response."""
        start = time.time()
        last_text = ""
        stable = 0

        await asyncio.sleep(2)  # Let Claude start responding

        while time.time() - start < timeout:
            sp_url = _find_sidepanel()
            if not sp_url:
                break

            try:
                async with websockets.connect(sp_url) as ws:
                    await ws.send(json.dumps({
                        "id": 1,
                        "method": "Runtime.evaluate",
                        "params": {
                            "expression": """
                            (() => {
                                // Side panel response — get full body text and extract last response
                                const body = document.body.innerText;
                                // Split by known markers
                                const parts = body.split(/Ask before acting|Optimistic|How can I help/);
                                // Get the last substantial chunk (Claude's response)
                                for (let i = parts.length - 1; i >= 0; i--) {
                                    const chunk = parts[i].trim();
                                    if (chunk.length > 5 && !chunk.includes('Sonnet') && !chunk.includes('quick mode')) {
                                        // Clean thinking artifacts
                                        let clean = chunk.replace(/Thought for \\d+s?/gi, '');
                                        clean = clean.replace(/Thinking about[^\\n]*/gi, '');
                                        clean = clean.replace(/Connector search[^\\n]*/gi, '');
                                        clean = clean.replace(/\\d+ connectors?[^\\n]*/gi, '');
                                        return clean.trim();
                                    }
                                }
                                return '';
                            })()
                            """,
                            "returnByValue": True
                        }
                    }))
                    result = await asyncio.wait_for(ws.recv(), timeout=5)
                    data = json.loads(result)
                    text = data.get("result", {}).get("result", {}).get("value", "").strip()

                    if text and text != last_text:
                        last_text = text
                        stable = 0
                    elif text:
                        stable += 1
                        if stable >= 3:  # 3 stable reads = done
                            log.info(f"Cowork response: {len(text)} chars")
                            return text

            except Exception:
                pass

            await asyncio.sleep(1)

        if last_text:
            return last_text
        return "Cowork didn't respond in time."
