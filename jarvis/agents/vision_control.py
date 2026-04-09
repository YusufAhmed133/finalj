"""
Vision-Powered Mac Control — Screenshots + Ollama Vision + AppleScript.

Flow:
1. Take screenshot of current screen
2. Send to Ollama vision model with task description
3. Model returns what to do (click coordinates, type text, etc.)
4. Execute via AppleScript/pyautogui
5. Repeat until task complete

Uses gemma3:4b (local, free, fast on M2).
"""
import asyncio
import base64
import io
import json
import re
import subprocess
import time
from pathlib import Path

import httpx

from jarvis.utils.logger import get_logger

log = get_logger("agents.vision_control")

OLLAMA_URL = "http://localhost:11434"
VISION_MODEL = "gemma3:4b"
MAX_STEPS = 8


async def _screenshot_b64() -> str:
    """Take screenshot, return base64."""
    path = "/tmp/jarvis_vision_screen.png"
    subprocess.run(["screencapture", "-x", path], timeout=5, capture_output=True)
    if Path(path).exists():
        data = Path(path).read_bytes()
        return base64.b64encode(data).decode()
    return ""


async def _ask_vision(image_b64: str, prompt: str) -> str:
    """Send screenshot + prompt to Ollama vision model."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(f"{OLLAMA_URL}/api/chat", json={
                "model": VISION_MODEL,
                "messages": [{
                    "role": "user",
                    "content": prompt,
                    "images": [image_b64],
                }],
                "stream": False,
            })
            data = resp.json()
            return data.get("message", {}).get("content", "")
    except Exception as e:
        log.error(f"Vision error: {e}")
        return ""


def _click(x: int, y: int):
    """Click at screen coordinates using cliclick or AppleScript."""
    # Try cliclick first (more reliable)
    result = subprocess.run(["which", "cliclick"], capture_output=True)
    if result.returncode == 0:
        subprocess.run(["cliclick", f"c:{x},{y}"], timeout=3, capture_output=True)
    else:
        # AppleScript fallback using Python + Quartz
        subprocess.run(["python3", "-c", f"""
import Quartz
point = Quartz.CGPointMake({x}, {y})
down = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseDown, point, Quartz.kCGMouseButtonLeft)
up = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseUp, point, Quartz.kCGMouseButtonLeft)
Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
import time; time.sleep(0.05)
Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)
"""], timeout=3, capture_output=True)


def _type_text(text: str):
    """Type text using AppleScript."""
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    subprocess.run(["osascript", "-e",
        f'tell application "System Events" to keystroke "{escaped}"'],
        timeout=5, capture_output=True)


def _press_key(key: str):
    """Press a key."""
    subprocess.run(["osascript", "-e",
        f'tell application "System Events" to keystroke return'],
        timeout=3, capture_output=True)


async def vision_execute(task: str) -> str:
    """Execute a task using vision. Takes screenshots, asks vision model what to do, acts."""
    log.info(f"Vision task: {task}")

    for step in range(MAX_STEPS):
        # Take screenshot
        img_b64 = await _screenshot_b64()
        if not img_b64:
            return "Could not take screenshot."

        # Ask vision model
        prompt = (
            f"You are controlling a Mac computer. The user wants to: {task}\n\n"
            f"Look at this screenshot. What is the SINGLE next action to take?\n"
            f"Respond in EXACTLY one of these formats:\n"
            f"CLICK x y - click at pixel coordinates (x,y)\n"
            f"TYPE text - type this text\n"
            f"KEY enter/tab/escape - press a key\n"
            f"OPEN url - open a URL in browser\n"
            f"APP appname - open an application\n"
            f"DONE message - task is complete\n"
            f"FAIL reason - task cannot be completed\n\n"
            f"Step {step + 1}/{MAX_STEPS}. Give ONE action only."
        )

        response = await _ask_vision(img_b64, prompt)
        log.info(f"Vision step {step}: {response[:100]}")

        if not response:
            return "Vision model didn't respond."

        # Parse action
        action = _parse_vision_action(response)

        if action["type"] == "DONE":
            return action.get("msg", "Done, sir.")
        elif action["type"] == "FAIL":
            return action.get("msg", "Couldn't complete that, sir.")
        elif action["type"] == "CLICK":
            _click(action["x"], action["y"])
            await asyncio.sleep(1)
        elif action["type"] == "TYPE":
            _type_text(action["text"])
            await asyncio.sleep(0.5)
        elif action["type"] == "KEY":
            _press_key(action["key"])
            await asyncio.sleep(0.5)
        elif action["type"] == "OPEN":
            subprocess.run(["open", action["url"]], timeout=5, capture_output=True)
            await asyncio.sleep(2)
        elif action["type"] == "APP":
            subprocess.run(["open", "-a", action["app"]], timeout=5, capture_output=True)
            await asyncio.sleep(2)
        else:
            log.warning(f"Unknown action: {action}")
            await asyncio.sleep(1)

    return "Task attempted, sir."


def _parse_vision_action(response: str) -> dict:
    """Parse vision model's action response."""
    # Clean up response
    text = response.strip()
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue

        # CLICK x y
        m = re.match(r"CLICK\s+(\d+)\s+(\d+)", line, re.IGNORECASE)
        if m:
            return {"type": "CLICK", "x": int(m.group(1)), "y": int(m.group(2))}

        # TYPE text
        m = re.match(r"TYPE\s+(.+)", line, re.IGNORECASE)
        if m:
            return {"type": "TYPE", "text": m.group(1).strip()}

        # KEY keyname
        m = re.match(r"KEY\s+(\w+)", line, re.IGNORECASE)
        if m:
            return {"type": "KEY", "key": m.group(1)}

        # OPEN url
        m = re.match(r"OPEN\s+(https?://\S+)", line, re.IGNORECASE)
        if m:
            return {"type": "OPEN", "url": m.group(1)}

        # APP name
        m = re.match(r"APP\s+(.+)", line, re.IGNORECASE)
        if m:
            return {"type": "APP", "app": m.group(1).strip()}

        # DONE
        m = re.match(r"DONE\s*(.*)", line, re.IGNORECASE)
        if m:
            return {"type": "DONE", "msg": m.group(1).strip() or "Done, sir."}

        # FAIL
        m = re.match(r"FAIL\s*(.*)", line, re.IGNORECASE)
        if m:
            return {"type": "FAIL", "msg": m.group(1).strip() or "Couldn't do that."}

    # Default: couldn't parse
    return {"type": "DONE", "msg": text[:200]}
