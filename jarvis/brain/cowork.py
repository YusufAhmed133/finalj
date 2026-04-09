"""
Cowork Bridge — Send tasks to Claude's Chrome extension with full computer use.

Uses CDP WebSocket to communicate with the extension's service worker.
EXECUTE_SCHEDULED_TASK creates a Cowork window with skipPermissions=true.
POPULATE_INPUT_TEXT fills the existing side panel input.

This gives Claude full computer use — open apps, click, type, browse, anything.
"""
import asyncio
import json
import time
import urllib.request
from typing import Optional

import websockets

from jarvis.utils.logger import get_logger

log = get_logger("brain.cowork")

CDP_URL = "http://localhost:9222"
EXT_ID = "fcoeoabgfenejglbffodgkkbkcdhcgfn"


def _get_targets():
    """Get all Chrome CDP targets."""
    try:
        data = urllib.request.urlopen(f"{CDP_URL}/json", timeout=3).read()
        return json.loads(data)
    except Exception:
        return []


def _find_service_worker():
    """Find the Claude extension's service worker WebSocket URL."""
    for t in _get_targets():
        if t.get("type") == "service_worker" and EXT_ID in t.get("url", ""):
            return t.get("webSocketDebuggerUrl")
    return None


def _find_sidepanel():
    """Find the Claude side panel page WebSocket URL."""
    for t in _get_targets():
        if t.get("type") == "page" and EXT_ID in t.get("url", "") and "sidepanel" in t.get("url", ""):
            return t.get("webSocketDebuggerUrl")
    return None


class CoworkBridge:
    """Send tasks to Claude Cowork with full computer use permissions."""

    def __init__(self):
        self._ready = False

    async def initialize(self) -> bool:
        sw = _find_service_worker()
        if sw:
            self._ready = True
            log.info("Cowork bridge: service worker found")
            return True
        log.warning("Cowork bridge: extension service worker not found")
        return False

    async def execute_task(self, prompt: str, target_url: str = "about:blank") -> str:
        """Send a task to Cowork via EXECUTE_SCHEDULED_TASK.

        Creates a new window with full computer use permissions.
        Returns confirmation or error.
        """
        sw_url = _find_service_worker()
        if not sw_url:
            return "Cowork not available — extension service worker not found."

        task_id = f"jarvis_{int(time.time())}"

        js = f"""
        (async () => {{
            const task = {{
                id: '{task_id}',
                name: 'JARVIS Task',
                prompt: {json.dumps(prompt)},
                url: '{target_url}',
                enabled: true,
                skipPermissions: true,
                repeatType: 'none'
            }};

            // Send to service worker to execute
            return new Promise((resolve) => {{
                chrome.runtime.sendMessage({{
                    type: 'EXECUTE_SCHEDULED_TASK',
                    task: task,
                    isManual: true
                }}, (response) => {{
                    resolve(JSON.stringify({{
                        sent: true,
                        error: chrome.runtime.lastError?.message || null,
                        response: response
                    }}));
                }});
            }});
        }})()
        """

        try:
            async with websockets.connect(sw_url) as ws:
                await ws.send(json.dumps({
                    "id": 1,
                    "method": "Runtime.evaluate",
                    "params": {
                        "expression": js,
                        "returnByValue": True,
                        "awaitPromise": True,
                    }
                }))
                result = await asyncio.wait_for(ws.recv(), timeout=10)
                data = json.loads(result)
                value = data.get("result", {}).get("result", {}).get("value", "")
                log.info(f"Cowork task sent: {value}")
                return f"Task dispatched to Cowork, sir."
        except Exception as e:
            log.error(f"Cowork error: {e}")
            return f"Cowork error: {str(e)[:100]}"

    async def send_to_sidepanel(self, prompt: str) -> str:
        """Send a prompt to the existing side panel (for questions)."""
        sw_url = _find_service_worker()
        if not sw_url:
            return None

        js = f"""
        (async () => {{
            return new Promise((resolve) => {{
                chrome.runtime.sendMessage({{
                    type: 'POPULATE_INPUT_TEXT',
                    prompt: {json.dumps(prompt)},
                    permissionMode: 'optimistic'
                }}, (response) => {{
                    resolve(JSON.stringify({{sent: true, error: chrome.runtime.lastError?.message}}));
                }});
            }});
        }})()
        """

        try:
            async with websockets.connect(sw_url) as ws:
                await ws.send(json.dumps({
                    "id": 1,
                    "method": "Runtime.evaluate",
                    "params": {
                        "expression": js,
                        "returnByValue": True,
                        "awaitPromise": True,
                    }
                }))
                result = await asyncio.wait_for(ws.recv(), timeout=10)
                log.info(f"Sent to side panel: {prompt[:50]}")
                return "Sent to Cowork."
        except Exception as e:
            log.error(f"Side panel error: {e}")
            return None

    async def read_sidepanel_response(self, timeout: int = 60) -> str:
        """Read the latest response from the side panel DOM."""
        sp_url = _find_sidepanel()
        if not sp_url:
            return ""

        start = time.time()
        last_text = ""
        stable = 0

        while time.time() - start < timeout:
            try:
                async with websockets.connect(sp_url) as ws:
                    await ws.send(json.dumps({
                        "id": 1,
                        "method": "Runtime.evaluate",
                        "params": {
                            "expression": """
                            (() => {
                                const msgs = document.querySelectorAll('.font-claude-response');
                                if (msgs.length > 0) return msgs[msgs.length - 1].innerText;
                                const all = document.querySelectorAll('[class*="message"]');
                                if (all.length > 0) return all[all.length - 1].innerText;
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
                        if stable >= 2:
                            return text
            except Exception:
                pass

            await asyncio.sleep(1)

        return last_text
