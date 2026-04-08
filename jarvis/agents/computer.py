"""
Computer Use Agent — Mac control WITHOUT API key.

Flow: screenshot → send to Claude browser → Claude describes action → execute via osascript.
Loop until task complete or max iterations.

No API key needed. Uses the same Playwright→claude.ai session as intelligence.
"""
import asyncio
import base64
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable

from jarvis.memory.spine import MemorySpine
from jarvis.utils.logger import get_logger

log = get_logger("agents.computer")

SCREENSHOTS_DIR = Path(__file__).parent.parent.parent / "data" / "logs" / "computer_actions"
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

PERMISSION_LOW = {"open_app", "navigate_url", "read_screen", "search_web",
                  "play_music", "adjust_volume", "take_screenshot", "read_file"}
PERMISSION_HIGH = {"send_email", "submit_form", "financial_transaction",
                   "delete_file", "post_publicly"}


class ComputerAgent:

    def __init__(self, spine: MemorySpine):
        self.spine = spine
        self._stop = asyncio.Event()
        self._running = False
        self.send_message: Optional[Callable] = None
        self.request_approval: Optional[Callable] = None
        self._brain = None  # Set to ClaudeBrowser instance

    async def initialize(self, brain=None) -> bool:
        """Initialize with the browser brain (no API key needed)."""
        self._brain = brain
        if brain:
            log.info("Computer use agent ready (browser-powered)")
            return True
        log.warning("Computer use agent: no brain provided")
        return False

    async def execute(self, task: str, action_type: str = "general") -> str:
        """Execute a task on the Mac using screenshot→Claude→osascript loop."""
        if not self._brain:
            return "Computer use unavailable — brain not connected."

        # Permission check
        if action_type in PERMISSION_HIGH:
            approved = await self._ask_approval(f"CRITICAL: {task}")
            if not approved:
                return "Action denied."
        elif action_type not in PERMISSION_LOW:
            approved = await self._ask_approval(f"Action: {task}")
            if not approved:
                return "Action denied."

        log.info(f"Computer task: {task[:80]}")
        before = await self._screenshot("before")

        self._running = True
        try:
            result = await self._vision_action_loop(task)
        except Exception as e:
            result = f"Error: {e}"
        finally:
            self._running = False

        after = await self._screenshot("after")

        self.spine.log_action(
            action_type=action_type,
            description=task,
            screenshot_before=str(before) if before else None,
            screenshot_after=str(after) if after else None,
            outcome=result[:500],
        )

        return result

    async def _vision_action_loop(self, task: str, max_steps: int = 8) -> str:
        """Screenshot → describe to Claude → execute action → repeat."""

        for step in range(max_steps):
            if self._stop.is_set():
                self._stop.clear()
                return "Stopped by user."

            # Take screenshot
            screenshot_path = await self._screenshot(f"step{step}")
            if not screenshot_path:
                return "Could not take screenshot."

            # Convert to base64 for describing to Claude
            # We can't send images to claude.ai browser directly via text,
            # so we describe the task and let Claude give us the action
            prompt = self._build_vision_prompt(task, step)

            # Ask Claude browser what to do
            response = await self._brain.think_in_conversation(prompt)
            log.info(f"Step {step}: Claude says: {response[:150]}")

            # Parse Claude's response for action
            action = self._parse_action(response)

            if action["type"] == "done":
                return action.get("message", "Task complete.")
            elif action["type"] == "click":
                await self._applescript(f'tell application "System Events" to click at {{{action["x"]}, {action["y"]}}}')
                await asyncio.sleep(1)
            elif action["type"] == "type":
                text = action.get("text", "")
                escaped = text.replace("\\", "\\\\").replace('"', '\\"')
                await self._applescript(f'tell application "System Events" to keystroke "{escaped}"')
                await asyncio.sleep(0.5)
            elif action["type"] == "key":
                await self._applescript(f'tell application "System Events" to key code {action.get("code", 0)}')
                await asyncio.sleep(0.5)
            elif action["type"] == "open_app":
                app_name = action.get("app", "")
                await self._applescript(f'tell application "{app_name}" to activate')
                await asyncio.sleep(2)
            elif action["type"] == "osascript":
                script = action.get("script", "")
                result = await self._applescript(script)
                log.info(f"Script result: {result[:100]}")
                await asyncio.sleep(1)
            elif action["type"] == "url":
                url = action.get("url", "")
                subprocess.run(["open", url], timeout=5, capture_output=True)
                await asyncio.sleep(2)
            else:
                log.warning(f"Unknown action type: {action['type']}")
                await asyncio.sleep(1)

        return "Task attempted (max steps reached)."

    def _build_vision_prompt(self, task: str, step: int) -> str:
        """Build prompt telling Claude what we're trying to do."""
        if step == 0:
            return (
                f"I need to do this on my Mac: {task}\n\n"
                f"Tell me the EXACT action to take. Respond in this format:\n"
                f"ACTION: open_app Spotify\n"
                f"or ACTION: click 720 450\n"
                f"or ACTION: type some text here\n"
                f"or ACTION: key 36 (for Return)\n"
                f"or ACTION: url https://google.com\n"
                f"or ACTION: osascript tell application \"Finder\" to open folder \"Downloads\"\n"
                f"or ACTION: done Task completed successfully\n\n"
                f"Just give me ONE action, nothing else."
            )
        else:
            return (
                f"Continuing task: {task}\n"
                f"Step {step + 1}. What's the next action? Same format:\n"
                f"ACTION: open_app/click/type/key/url/osascript/done ..."
            )

    def _parse_action(self, response: str) -> dict:
        """Parse Claude's action response."""
        # Look for ACTION: line
        for line in response.split("\n"):
            line = line.strip()
            if line.upper().startswith("ACTION:"):
                parts = line[7:].strip().split(None, 1)
                if not parts:
                    continue
                cmd = parts[0].lower()
                arg = parts[1] if len(parts) > 1 else ""

                if cmd == "done":
                    return {"type": "done", "message": arg or "Task complete."}
                elif cmd == "click":
                    try:
                        coords = arg.split()
                        return {"type": "click", "x": int(coords[0]), "y": int(coords[1])}
                    except (ValueError, IndexError):
                        return {"type": "done", "message": f"Invalid click coords: {arg}"}
                elif cmd == "type":
                    return {"type": "type", "text": arg}
                elif cmd == "key":
                    try:
                        return {"type": "key", "code": int(arg.split()[0])}
                    except ValueError:
                        return {"type": "done", "message": f"Invalid key code: {arg}"}
                elif cmd == "open_app":
                    return {"type": "open_app", "app": arg}
                elif cmd == "url":
                    return {"type": "url", "url": arg}
                elif cmd == "osascript":
                    return {"type": "osascript", "script": arg}

        # If no ACTION: found, check if response implies done
        lower = response.lower()
        if any(w in lower for w in ["done", "complete", "finished", "already open"]):
            return {"type": "done", "message": response[:200]}

        # Default: try to extract app name for open
        return {"type": "done", "message": f"Could not parse action from: {response[:200]}"}

    async def _applescript(self, script: str) -> str:
        try:
            r = subprocess.run(["osascript", "-e", script],
                             capture_output=True, text=True, timeout=10)
            return r.stdout.strip() or r.stderr.strip() or "Done"
        except subprocess.TimeoutExpired:
            return "Timed out"
        except Exception as e:
            return str(e)

    async def _screenshot(self, label: str) -> Optional[Path]:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = SCREENSHOTS_DIR / f"{ts}_{label}.png"
        try:
            subprocess.run(["screencapture", "-x", str(path)], timeout=5, capture_output=True)
            return path if path.exists() else None
        except Exception:
            return None

    async def _ask_approval(self, description: str) -> bool:
        if not self.request_approval:
            return True
        result = asyncio.Event()
        approved = [False]
        async def cb(is_approved):
            approved[0] = is_approved
            result.set()
        await self.request_approval(description, f"action_{int(time.time())}", cb)
        try:
            await asyncio.wait_for(result.wait(), timeout=120)
            return approved[0]
        except asyncio.TimeoutError:
            return False

    def force_stop(self):
        self._stop.set()
        self._running = False
        log.warning("FORCE STOP")

    async def shutdown(self):
        self.force_stop()
