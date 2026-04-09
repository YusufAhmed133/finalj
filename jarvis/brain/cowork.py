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
        """Type prompt into side panel, click send, wait for and return response."""
        sp_url = _find_sidepanel()
        if not sp_url:
            return "Cowork side panel not found. Open the Claude extension in Chrome."

        # Step 1: Type and send
        try:
            async with websockets.connect(sp_url) as ws:
                # Escape the prompt for JS
                safe_prompt = json.dumps(prompt)

                await ws.send(json.dumps({
                    "id": 1,
                    "method": "Runtime.evaluate",
                    "params": {
                        "expression": f"""
                        (() => {{
                            const editor = document.querySelector('.ProseMirror')
                                || document.querySelector('[contenteditable="true"]');
                            if (!editor) return 'no editor';
                            editor.focus();
                            editor.innerHTML = '<p>' + {safe_prompt} + '</p>';
                            editor.dispatchEvent(new Event('input', {{bubbles: true}}));
                            setTimeout(() => {{
                                const btn = document.querySelector('[aria-label="Send message"]')
                                    || document.querySelector('button[type="submit"]')
                                    || [...document.querySelectorAll('button')].find(b =>
                                        b.querySelector('svg') && b.offsetParent !== null &&
                                        b.closest('[class*="input"], [class*="composer"], fieldset'));
                                if (btn) btn.click();
                            }}, 300);
                            return 'sent';
                        }})()
                        """,
                        "returnByValue": True
                    }
                }))
                result = await asyncio.wait_for(ws.recv(), timeout=5)
                data = json.loads(result)
                status = data.get("result", {}).get("result", {}).get("value", "")
                log.info(f"Cowork send: {status}")

                if status == "no editor":
                    return "Could not find input in Cowork side panel."

        except Exception as e:
            log.error(f"Cowork send error: {e}")
            return f"Cowork error: {str(e)[:100]}"

        # Step 2: Wait for response
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
                                // Get last response from side panel
                                const msgs = document.querySelectorAll('.font-claude-response');
                                if (msgs.length > 0) {
                                    let text = msgs[msgs.length - 1].innerText;
                                    // Strip thinking artifacts
                                    text = text.replace(/Thought for \\d+s?/gi, '');
                                    text = text.replace(/Thinking about[^\\n]*/gi, '');
                                    text = text.replace(/Connector search[^\\n]*/gi, '');
                                    return text.trim();
                                }
                                // Fallback
                                const all = document.querySelectorAll('[data-message-author-role="assistant"]');
                                if (all.length > 0) return all[all.length - 1].innerText.trim();
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
