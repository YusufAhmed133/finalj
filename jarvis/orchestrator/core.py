"""
JARVIS Orchestrator — Main event loop, message routing, state management.

The orchestrator is the central coordinator:
- Receives messages from Telegram
- Scores priority
- Searches memory for relevant context
- Routes to intelligence layer
- Dispatches actions (computer use, email, calendar, etc.)
- Stores interactions in memory
- Manages JARVIS modes (active, focus, sleep)
"""
import asyncio
import json
import time
from datetime import datetime
from typing import Optional
from enum import Enum

from jarvis.memory.spine import MemorySpine
from jarvis.memory.graph import EntityGraph
from jarvis.brain.intelligence import Intelligence
from jarvis.orchestrator.priority import score_priority, is_stop_command, is_cardiac_alert
from jarvis.orchestrator.briefing import BriefingGenerator
from jarvis.memory.patterns import PatternLearner
from jarvis.utils.logger import get_logger

log = get_logger("orchestrator.core")


class Mode(Enum):
    ACTIVE = "active"       # Normal operation, responds to everything
    FOCUS = "focus"         # Only high-priority messages get through
    SLEEP = "sleep"         # Only cardiac alerts and emergencies
    MAINTENANCE = "maintenance"  # System maintenance, limited responses


FOCUS_THRESHOLD = 70  # Minimum priority to break through focus mode
SLEEP_THRESHOLD = 90  # Minimum priority to break through sleep mode


class Orchestrator:
    """Central coordinator for JARVIS."""

    def __init__(self):
        self.spine = MemorySpine()
        self.graph = EntityGraph()
        self.intelligence = Intelligence()
        self.briefing = BriefingGenerator(self.spine, self.intelligence)
        self.patterns = PatternLearner(self.spine)

        self.mode = Mode.ACTIVE
        self.running = False
        self._action_in_progress = False
        self._stop_event = asyncio.Event()

        self.send_message_callback = None
        self.send_approval_callback = None

    async def initialize(self) -> bool:
        log.info("Initializing JARVIS orchestrator...")

        intel_ok = await self.intelligence.initialize()
        if not intel_ok:
            log.warning("Intelligence layer not ready. Operating in limited mode.")

        self.running = True
        log.info(f"JARVIS orchestrator initialized. Mode: {self.mode.value}")
        return True

    async def handle_message(self, message: str, source: str = "telegram", metadata: Optional[dict] = None) -> str:
        """Handle an incoming message. Main entry point.

        Args:
            message: The message text
            source: Where it came from (telegram, cli, system)
            metadata: Additional info (chat_id, is_voice, etc.)

        Returns:
            Response text to send back
        """
        timestamp = datetime.now().isoformat()
        priority = score_priority(message, metadata)

        log.info(f"Message received: priority={priority} source={source} mode={self.mode.value}")

        # STOP command — always handled immediately
        if is_stop_command(message):
            return await self._handle_stop()

        # Mode filtering
        if self.mode == Mode.SLEEP and priority < SLEEP_THRESHOLD:
            log.info("Message suppressed (sleep mode)")
            return ""  # Silent suppress
        if self.mode == Mode.FOCUS and priority < FOCUS_THRESHOLD:
            return "In focus mode. Only urgent messages get through. Send /active to switch back."

        # Cardiac alert — always process immediately
        if is_cardiac_alert(message):
            log.warning(f"CARDIAC ALERT: {message[:100]}")

        # Track patterns
        self.patterns.record_interaction(message)

        # Store incoming message in memory
        mem_id = self.spine.store(
            content=f"{source}: {message}",
            type="interaction",
            source=source,
            metadata={"priority": priority, "timestamp": timestamp, **(metadata or {})},
        )

        # Handle special commands
        if message.startswith("/"):
            return await self._handle_command(message)

        # Check if this is a computer task
        computer_keywords = ["open ", "launch ", "go to ", "navigate to ", "click ",
                           "close ", "screenshot", "play ", "search for ", "type in ",
                           "fill ", "send email", "check my calendar"]
        is_computer_task = any(message.lower().startswith(kw) or message.lower().startswith("jarvis " + kw)
                              for kw in computer_keywords)

        if is_computer_task and hasattr(self, 'computer') and self.computer:
            try:
                # Route to computer agent
                task_msg = message.lower().replace("jarvis ", "", 1).strip()
                result = await self.computer.execute(task_msg)
                self.spine.store(content=f"JARVIS (action): {result}", type="interaction",
                               source="jarvis", metadata={"in_reply_to": mem_id})
                return result
            except Exception as e:
                log.error(f"Computer use error: {e}")
                return f"Tried to execute but hit an error: {str(e)[:200]}"

        # Search memory for relevant context
        memory_context = self._get_relevant_context(message)

        # Route to intelligence — response comes back as plain text
        try:
            response = await self.intelligence.think(
                message=message,
                memory_context=memory_context,
            )

            self.spine.store(content=f"JARVIS: {response}", type="interaction",
                           source="jarvis", metadata={"in_reply_to": mem_id})
            return response

        except Exception as e:
            log.error(f"Intelligence error: {e}")
            return f"Sorry, hit an error: {str(e)[:200]}"

    async def _handle_stop(self) -> str:
        """Handle STOP/KILL command — halt everything immediately."""
        log.warning("STOP command received — halting all actions")
        self._stop_event.set()
        self._action_in_progress = False

        # Brief pause then clear
        await asyncio.sleep(0.5)
        self._stop_event.clear()

        return "All actions halted. What's happening?"

    async def _handle_command(self, message: str) -> str:
        """Handle slash commands."""
        cmd = message.strip().lower().split()[0]
        args = message.strip()[len(cmd):].strip()

        commands = {
            "/active": lambda: self._set_mode(Mode.ACTIVE),
            "/focus": lambda: self._set_mode(Mode.FOCUS),
            "/sleep": lambda: self._set_mode(Mode.SLEEP),
            "/status": self._get_status,
            "/memory": lambda: self._search_memory(args),
            "/briefing": self._morning_briefing_job,
            "/review": self._evening_review_job,
            "/stats": self._get_stats,
        }

        handler = commands.get(cmd)
        if handler:
            result = handler()
            if asyncio.iscoroutine(result):
                return await result
            return result

        return f"Unknown command: {cmd}. Available: {', '.join(commands.keys())}"

    def _set_mode(self, mode: Mode) -> str:
        """Switch JARVIS mode."""
        old_mode = self.mode
        self.mode = mode
        log.info(f"Mode changed: {old_mode.value} → {mode.value}")
        return f"Mode: {mode.value}"

    def _get_status(self) -> str:
        """Get current JARVIS status."""
        stats = self.spine.stats()
        return (
            f"Mode: {self.mode.value}\n"
            f"Memories: {stats['total']} (hot: {stats['by_tier'].get('hot', 0)}, "
            f"warm: {stats['by_tier'].get('warm', 0)})\n"
            f"Entities: {self.graph.stats()['total_entities']}\n"
            f"Action in progress: {self._action_in_progress}"
        )

    def _search_memory(self, query: str) -> str:
        """Search memory and return results."""
        if not query:
            return "Usage: /memory <search query>"
        results = self.spine.search_text(query, limit=5)
        if not results:
            return f"No memories found for: {query}"
        lines = [f"Found {len(results)} memories:"]
        for r in results:
            content = r.get("content", "")[:150]
            tier = r.get("tier", "?")
            lines.append(f"[{tier}] {content}")
        return "\n".join(lines)

    async def _get_stats(self) -> str:
        """Get detailed stats."""
        mem_stats = self.spine.stats()
        graph_stats = self.graph.stats()
        health = await self.intelligence.health_check()
        return (
            f"Memory: {mem_stats}\n"
            f"Graph: {graph_stats}\n"
            f"Intelligence: {health}"
        )

    def _get_relevant_context(self, message: str, limit: int = 5) -> str:
        """Search memory for context relevant to the current message."""
        results = self.spine.search_text(message, limit=limit)
        if not results:
            return ""

        lines = []
        for r in results:
            tier = r.get("tier", "")
            content = r.get("summary") or r.get("content", "")
            lines.append(f"[{tier}] {content[:200]}")
        return "\n".join(lines)

    def _get_state_context(self) -> str:
        """Get current state as context string."""
        now = datetime.now()
        return (
            f"Time: {now.strftime('%Y-%m-%d %H:%M')} AEST ({now.strftime('%A')})\n"
            f"Mode: {self.mode.value}\n"
            f"Action in progress: {self._action_in_progress}"
        )

    def _parse_response(self, raw: str) -> dict:
        """Parse Claude's structured JSON response.

        Falls back gracefully if response isn't valid JSON.
        """
        # Try to extract JSON from the response
        try:
            # Direct JSON parse
            return json.loads(raw)
        except json.JSONDecodeError:
            pass

        # Try to find JSON block in the response
        try:
            start = raw.index("{")
            end = raw.rindex("}") + 1
            return json.loads(raw[start:end])
        except (ValueError, json.JSONDecodeError):
            pass

        # Fallback: treat entire response as the reply
        return {
            "reply": raw,
            "action": None,
            "remember": None,
            "mood": "unknown",
        }

    async def _handle_action(self, action: dict):
        """Dispatch an action to the appropriate handler."""
        action_type = action.get("type", "")
        details = action.get("details", "")
        log.info(f"Action requested: {action_type} — {details[:100]}")

        # Store action in memory
        self.spine.store(
            content=f"Action: {action_type} — {details}",
            type="action",
            source="orchestrator",
            metadata=action,
        )

        # TODO: Route to computer use agent, email handler, etc.
        # This will be implemented in Phase 6 (Computer Use Agent)

    async def _morning_briefing_job(self) -> str:
        """Morning briefing scheduled job."""
        log.info("Generating morning briefing...")
        briefing = await self.briefing.morning_briefing()

        # Store in memory
        self.spine.store(content=briefing, type="briefing", source="system")

        # Send via callback if registered
        if self.send_message_callback:
            await self.send_message_callback(briefing)

        return briefing

    async def _evening_review_job(self) -> str:
        """Evening review scheduled job."""
        log.info("Generating evening review...")
        review = await self.briefing.evening_review()

        self.spine.store(content=review, type="briefing", source="system")

        if self.send_message_callback:
            await self.send_message_callback(review)

        return review

    async def shutdown(self):
        """Clean shutdown."""
        log.info("Shutting down orchestrator...")
        self.running = False
        await self.intelligence.shutdown()
        self.spine.close()
        log.info("Orchestrator shut down")
