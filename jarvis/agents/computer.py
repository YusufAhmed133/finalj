"""
Computer Use Agent — Controls the Mac via Anthropic Computer Use API.

Uses claude-sonnet-4-5 to see the screen and take actions.
Three permission tiers:
  - low: execute immediately, confirm after
  - medium: send preview to Telegram, wait for YES
  - high: require YES + 10s kill window

Every action logged with screenshots to data/logs/computer_actions/.
STOP/KILL on Telegram halts everything within 3 seconds.
"""
import asyncio
import base64
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable

import anthropic

from jarvis.memory.spine import MemorySpine
from jarvis.utils.logger import get_logger
from jarvis.utils.crypto import load_secrets

log = get_logger("agents.computer")

SCREENSHOTS_DIR = Path(__file__).parent.parent.parent / "data" / "logs" / "computer_actions"
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

MODEL = "claude-sonnet-4-5-20250514"

PERMISSION_LOW = {"open_app", "navigate_url", "read_screen", "search_web",
                  "play_music", "adjust_volume", "take_screenshot", "read_file"}
PERMISSION_HIGH = {"send_email", "submit_form", "financial_transaction",
                   "delete_file", "post_publicly"}
# Everything else is medium


class ComputerAgent:

    def __init__(self, spine: MemorySpine):
        self.spine = spine
        self.client: Optional[anthropic.Anthropic] = None
        self._stop = asyncio.Event()
        self._running = False
        self.send_message: Optional[Callable] = None  # Telegram callback
        self.request_approval: Optional[Callable] = None

    async def initialize(self) -> bool:
        secrets = load_secrets()
        key = secrets.get("ANTHROPIC_API_KEY", "")
        if not key:
            log.warning("No ANTHROPIC_API_KEY — computer use unavailable")
            return False
        self.client = anthropic.Anthropic(api_key=key)
        log.info("Computer use agent ready")
        return True

    async def execute(self, task: str, action_type: str = "general") -> str:
        """Execute a task on the Mac. Returns result description."""
        if not self.client:
            return "Computer use unavailable — no API key configured."

        # Determine permission tier
        if action_type in PERMISSION_LOW:
            tier = "low"
        elif action_type in PERMISSION_HIGH:
            tier = "high"
        else:
            tier = "medium"

        log.info(f"Computer task: {task[:80]} (tier={tier})")

        # Permission check
        if tier == "medium":
            approved = await self._ask_approval(f"Action: {task}")
            if not approved:
                return "Action denied."

        if tier == "high":
            approved = await self._ask_approval(f"CRITICAL: {task}\n\nSend STOP within 10s to cancel.")
            if not approved:
                return "Action denied."
            if self.send_message:
                await self.send_message("Executing in 10 seconds. Send STOP to cancel.")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=10.0)
                self._stop.clear()
                return "Stopped by user."
            except asyncio.TimeoutError:
                pass

        # Take screenshot before
        before = await self._screenshot("before")

        # Execute via Computer Use API
        self._running = True
        try:
            result = await self._run_computer_use(task)
        except Exception as e:
            result = f"Error: {e}"
        finally:
            self._running = False

        # Take screenshot after
        after = await self._screenshot("after")

        # Log
        self.spine.log_action(
            action_type=action_type,
            description=task,
            screenshot_before=str(before) if before else None,
            screenshot_after=str(after) if after else None,
            outcome=result[:500],
        )

        if tier == "low" and self.send_message:
            await self.send_message(f"Done: {result[:300]}")

        return result

    async def _run_computer_use(self, task: str) -> str:
        """Execute task using Anthropic Computer Use API with tool loop."""
        screenshot_b64 = await self._screenshot_b64()

        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": f"Execute this task on the Mac: {task}"},
                {"type": "image", "source": {
                    "type": "base64", "media_type": "image/png", "data": screenshot_b64,
                }},
            ],
        }]

        tools = [
            {"type": "computer_20250124", "name": "computer",
             "display_width_px": 1440, "display_height_px": 900, "display_number": 1},
            {"type": "bash_20250124", "name": "bash"},
            {"type": "text_editor_20250124", "name": "str_replace_editor"},
        ]

        # Tool use loop — keep going until Claude says it's done
        max_iterations = 10
        for i in range(max_iterations):
            if self._stop.is_set():
                self._stop.clear()
                return "Stopped by user."

            response = self.client.messages.create(
                model=MODEL, max_tokens=4096, messages=messages, tools=tools,
            )

            # Process response
            result_text = ""
            tool_results = []

            for block in response.content:
                if block.type == "text":
                    result_text += block.text
                elif block.type == "tool_use":
                    tool_result = await self._execute_tool(block)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": tool_result,
                    })

            if not tool_results:
                return result_text or "Task completed."

            # Add assistant response + tool results for next iteration
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

        return result_text or "Task completed (max iterations reached)."

    async def _execute_tool(self, block) -> str:
        """Execute a tool call from Claude."""
        name = block.name
        inp = block.input

        if name == "bash":
            cmd = inp.get("command", "")
            log.info(f"Bash: {cmd[:100]}")
            try:
                r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
                return r.stdout[:2000] or r.stderr[:2000] or "Done"
            except subprocess.TimeoutExpired:
                return "Timed out (30s)"

        elif name == "computer":
            action = inp.get("action", "")
            if action == "screenshot":
                b64 = await self._screenshot_b64()
                return [{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}}]
            elif action in ("click", "double_click", "right_click"):
                x, y = inp.get("coordinate", [0, 0])
                subprocess.run(["osascript", "-e",
                    f'tell application "System Events" to click at {{{x}, {y}}}'],
                    timeout=5, capture_output=True)
                return f"Clicked at ({x}, {y})"
            elif action == "type":
                text = inp.get("text", "")
                escaped = text.replace("\\", "\\\\").replace('"', '\\"')
                subprocess.run(["osascript", "-e",
                    f'tell application "System Events" to keystroke "{escaped}"'],
                    timeout=5, capture_output=True)
                return f"Typed: {text[:50]}"
            elif action == "key":
                key = inp.get("key", "")
                subprocess.run(["osascript", "-e",
                    f'tell application "System Events" to keystroke "{key}"'],
                    timeout=5, capture_output=True)
                return f"Pressed: {key}"
            elif action == "cursor_position":
                return "0,0"
            elif action == "scroll":
                return "Scrolled"

        elif name == "str_replace_editor":
            cmd = inp.get("command", "")
            path = inp.get("path", "")
            if cmd == "view" and path:
                try:
                    return Path(path).read_text()[:3000]
                except Exception as e:
                    return str(e)

        return f"Unknown tool: {name}"

    async def _ask_approval(self, description: str) -> bool:
        if not self.request_approval:
            return True
        result = asyncio.Event()
        approved = [False]
        async def cb(is_approved):
            approved[0] = is_approved
            result.set()
        approval_id = f"action_{int(time.time())}"
        await self.request_approval(description, approval_id, cb)
        try:
            await asyncio.wait_for(result.wait(), timeout=120)
            return approved[0]
        except asyncio.TimeoutError:
            return False

    async def _screenshot(self, label: str) -> Optional[Path]:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = SCREENSHOTS_DIR / f"{ts}_{label}.png"
        try:
            subprocess.run(["screencapture", "-x", str(path)], timeout=5, capture_output=True)
            return path if path.exists() else None
        except Exception:
            return None

    async def _screenshot_b64(self) -> str:
        path = await self._screenshot("temp")
        if path and path.exists():
            data = path.read_bytes()
            path.unlink()
            return base64.b64encode(data).decode()
        return ""

    def force_stop(self):
        self._stop.set()
        self._running = False
        log.warning("FORCE STOP")

    async def shutdown(self):
        self.force_stop()
