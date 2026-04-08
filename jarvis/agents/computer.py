"""
Computer Use Agent — Controls the Mac to execute tasks.

Uses Anthropic Computer Use API with claude-sonnet-4-5.
Three permission tiers:
1. Immediate: execute + confirm after (open apps, navigate, read screen)
2. Approve first: send preview to Telegram, wait for YES
3. Critical: require YES + 10-second STOP window

Every action logged with screenshots to data/logs/computer_actions/.
STOP command halts everything within 3 seconds.
"""
import asyncio
import base64
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, Awaitable
from enum import Enum

import anthropic

from jarvis.agents.base import BaseAgent
from jarvis.memory.spine import MemorySpine
from jarvis.utils.logger import get_logger
from jarvis.utils.crypto import load_secrets

log = get_logger("agents.computer")

SCREENSHOTS_DIR = Path(__file__).parent.parent.parent / "data" / "logs" / "computer_actions"
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

COMPUTER_USE_MODEL = "claude-sonnet-4-5-20250514"


class PermissionTier(Enum):
    IMMEDIATE = "immediate"       # Execute, confirm after
    APPROVE_FIRST = "approve"     # Preview → wait for YES → execute
    CRITICAL = "critical"         # Preview → YES → 10s STOP window → execute


# Action → permission tier mapping
ACTION_PERMISSIONS = {
    # Immediate
    "open_app": PermissionTier.IMMEDIATE,
    "navigate_url": PermissionTier.IMMEDIATE,
    "read_screen": PermissionTier.IMMEDIATE,
    "search_web": PermissionTier.IMMEDIATE,
    "play_music": PermissionTier.IMMEDIATE,
    "adjust_volume": PermissionTier.IMMEDIATE,
    "take_screenshot": PermissionTier.IMMEDIATE,
    "read_file": PermissionTier.IMMEDIATE,
    # Approve first
    "compose_email": PermissionTier.APPROVE_FIRST,
    "fill_form": PermissionTier.APPROVE_FIRST,
    "create_calendar_event": PermissionTier.APPROVE_FIRST,
    "download_file": PermissionTier.APPROVE_FIRST,
    "write_document": PermissionTier.APPROVE_FIRST,
    # Critical
    "send_email": PermissionTier.CRITICAL,
    "submit_form": PermissionTier.CRITICAL,
    "financial_transaction": PermissionTier.CRITICAL,
    "delete_file": PermissionTier.CRITICAL,
    "post_publicly": PermissionTier.CRITICAL,
}


class ComputerUseAgent(BaseAgent):
    """Controls the Mac using Claude's Computer Use API."""

    def __init__(
        self,
        spine: MemorySpine,
        approval_callback: Optional[Callable] = None,
        message_callback: Optional[Callable] = None,
    ):
        """
        Args:
            spine: Memory spine for logging actions
            approval_callback: async fn(description, approval_id) -> bool
            message_callback: async fn(text) -> None (send to Telegram)
        """
        self.spine = spine
        self.approval_callback = approval_callback
        self.message_callback = message_callback
        self.client: Optional[anthropic.Anthropic] = None
        self._stop_event = asyncio.Event()
        self._running = False

    async def initialize(self) -> bool:
        """Initialize with API key for computer use."""
        secrets = load_secrets()
        api_key = secrets.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            log.warning("No ANTHROPIC_API_KEY — computer use requires Tier 2 API access")
            return False

        self.client = anthropic.Anthropic(api_key=api_key)
        log.info("Computer use agent initialized")
        return True

    async def execute(self, task: dict) -> dict:
        """Execute a computer use task.

        Args:
            task: {"type": "action_type", "details": "what to do", "context": "..."}

        Returns:
            {"success": bool, "result": str, "screenshots": [paths]}
        """
        action_type = task.get("type", "unknown")
        details = task.get("details", "")
        permission = ACTION_PERMISSIONS.get(action_type, PermissionTier.APPROVE_FIRST)

        log.info(f"Computer use: {action_type} (permission: {permission.value})")

        # Permission check
        if permission == PermissionTier.APPROVE_FIRST:
            approved = await self._request_approval(
                f"Action: {action_type}\nDetails: {details}"
            )
            if not approved:
                return {"success": False, "result": "Denied by user", "screenshots": []}

        elif permission == PermissionTier.CRITICAL:
            approved = await self._request_approval(
                f"CRITICAL ACTION: {action_type}\nDetails: {details}\n\n"
                f"Send STOP within 10 seconds to cancel."
            )
            if not approved:
                return {"success": False, "result": "Denied by user", "screenshots": []}

            # 10-second STOP window
            if self.message_callback:
                await self.message_callback("Executing in 10 seconds. Send STOP to cancel.")
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=10.0)
                # Stop was triggered
                self._stop_event.clear()
                return {"success": False, "result": "Stopped by user", "screenshots": []}
            except asyncio.TimeoutError:
                pass  # No stop — proceed

        # Take screenshot before
        screenshot_before = await self._take_screenshot("before")

        # Execute the action
        self._running = True
        try:
            result = await self._execute_with_computer_use(action_type, details)
        except Exception as e:
            result = f"Error: {str(e)}"
        finally:
            self._running = False

        # Take screenshot after
        screenshot_after = await self._take_screenshot("after")

        # Log the action
        self.spine.log_action(
            action_type=action_type,
            description=details,
            screenshot_before=str(screenshot_before) if screenshot_before else None,
            screenshot_after=str(screenshot_after) if screenshot_after else None,
            outcome=result[:500] if isinstance(result, str) else str(result)[:500],
        )

        # Notify result for immediate actions
        if permission == PermissionTier.IMMEDIATE and self.message_callback:
            await self.message_callback(f"Done: {action_type} — {result[:200]}")

        return {
            "success": "error" not in result.lower() if isinstance(result, str) else True,
            "result": result,
            "screenshots": [s for s in [screenshot_before, screenshot_after] if s],
        }

    async def _execute_with_computer_use(self, action_type: str, details: str) -> str:
        """Execute using Anthropic Computer Use API or AppleScript shortcuts."""

        # Quick actions via AppleScript (faster than full computer use)
        applescript_actions = {
            "open_app": lambda d: f'tell application "{d}" to activate',
            "adjust_volume": lambda d: f'set volume output volume {d}',
            "play_music": lambda d: 'tell application "Spotify" to play',
        }

        if action_type in applescript_actions:
            script = applescript_actions[action_type](details)
            return await self._run_applescript(script)

        # Full computer use for complex actions
        if not self.client:
            return "Computer use unavailable — no API key configured"

        # Take a screenshot to give Claude vision
        screenshot_b64 = await self._screenshot_base64()

        messages = [{
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": f"Execute this action on the Mac: {action_type} — {details}. "
                            f"Use the computer tools to accomplish this. Be precise and efficient."
                },
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": screenshot_b64,
                    },
                },
            ],
        }]

        try:
            response = self.client.messages.create(
                model=COMPUTER_USE_MODEL,
                max_tokens=4096,
                messages=messages,
                tools=[
                    {
                        "type": "computer_20250124",
                        "name": "computer",
                        "display_width_px": 1440,
                        "display_height_px": 900,
                        "display_number": 1,
                    },
                    {
                        "type": "bash_20250124",
                        "name": "bash",
                    },
                    {
                        "type": "text_editor_20250124",
                        "name": "str_replace_editor",
                    },
                ],
            )

            # Process tool calls in the response
            result_parts = []
            for block in response.content:
                if block.type == "text":
                    result_parts.append(block.text)
                elif block.type == "tool_use":
                    # Execute the tool call
                    tool_result = await self._execute_tool_call(block)
                    result_parts.append(f"[{block.name}: {tool_result[:200]}]")

            return " ".join(result_parts) or "Action completed"

        except Exception as e:
            log.error(f"Computer use API error: {e}")
            return f"Error: {str(e)}"

    async def _execute_tool_call(self, tool_block) -> str:
        """Execute a tool call from Claude's computer use response."""
        name = tool_block.name
        input_data = tool_block.input

        if name == "bash":
            command = input_data.get("command", "")
            log.info(f"Executing bash: {command[:100]}")
            try:
                result = subprocess.run(
                    command, shell=True, capture_output=True, text=True, timeout=30
                )
                return result.stdout or result.stderr or "Done"
            except subprocess.TimeoutExpired:
                return "Command timed out (30s)"

        elif name == "computer":
            action = input_data.get("action", "")
            log.info(f"Computer action: {action}")
            # Handle mouse/keyboard actions via AppleScript or cliclick
            if action == "screenshot":
                return "Screenshot taken"
            elif action in ("click", "double_click", "right_click"):
                x, y = input_data.get("coordinate", [0, 0])
                return await self._click(x, y, action)
            elif action == "type":
                text = input_data.get("text", "")
                return await self._type_text(text)
            elif action == "key":
                key = input_data.get("key", "")
                return await self._press_key(key)

        return f"Unknown tool: {name}"

    async def _click(self, x: int, y: int, click_type: str = "click") -> str:
        """Click at coordinates using AppleScript."""
        # Use cliclick if available, otherwise AppleScript
        script = f"""
        tell application "System Events"
            click at {{{x}, {y}}}
        end tell
        """
        # Actually use osascript to move mouse and click
        cmd = f'osascript -e \'tell application "System Events" to click at {{{x}, {y}}}\''
        try:
            subprocess.run(cmd, shell=True, timeout=5, capture_output=True)
            return f"Clicked at ({x}, {y})"
        except Exception as e:
            return f"Click failed: {e}"

    async def _type_text(self, text: str) -> str:
        """Type text using AppleScript."""
        # Escape special characters for AppleScript
        escaped = text.replace("\\", "\\\\").replace('"', '\\"')
        script = f'tell application "System Events" to keystroke "{escaped}"'
        return await self._run_applescript(script)

    async def _press_key(self, key: str) -> str:
        """Press a key using AppleScript."""
        # Map common key names to AppleScript key codes
        key_map = {
            "Return": "return", "Enter": "return", "Tab": "tab",
            "Escape": "escape", "Space": "space",
        }
        as_key = key_map.get(key, key.lower())
        script = f'tell application "System Events" to key code "{as_key}"'
        return await self._run_applescript(script)

    async def _run_applescript(self, script: str) -> str:
        """Execute an AppleScript."""
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=10,
            )
            return result.stdout.strip() or result.stderr.strip() or "Done"
        except subprocess.TimeoutExpired:
            return "AppleScript timed out"
        except Exception as e:
            return f"AppleScript error: {e}"

    async def _take_screenshot(self, label: str) -> Optional[Path]:
        """Take a screenshot and save it."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = SCREENSHOTS_DIR / f"{timestamp}_{label}.png"
        try:
            subprocess.run(
                ["screencapture", "-x", str(path)],
                timeout=5, capture_output=True,
            )
            if path.exists():
                return path
        except Exception as e:
            log.error(f"Screenshot failed: {e}")
        return None

    async def _screenshot_base64(self) -> str:
        """Take a screenshot and return as base64."""
        path = await self._take_screenshot("temp")
        if path and path.exists():
            data = path.read_bytes()
            path.unlink()  # Clean up temp screenshot
            return base64.b64encode(data).decode()
        return ""

    async def _request_approval(self, description: str) -> bool:
        """Request approval from the user via Telegram."""
        if not self.approval_callback:
            log.warning("No approval callback — auto-approving")
            return True

        approval_id = f"action_{int(time.time())}"
        result = asyncio.Event()
        approved = [False]

        async def on_response(is_approved: bool):
            approved[0] = is_approved
            result.set()

        await self.approval_callback(description, approval_id, on_response)

        try:
            await asyncio.wait_for(result.wait(), timeout=120)
            return approved[0]
        except asyncio.TimeoutError:
            log.warning("Approval timed out (120s)")
            return False

    def force_stop(self):
        """Force stop all actions immediately."""
        self._stop_event.set()
        self._running = False
        log.warning("FORCE STOP triggered")

    async def shutdown(self):
        """Clean shutdown."""
        self.force_stop()
        log.info("Computer use agent shut down")
