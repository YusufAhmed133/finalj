"""
JARVIS Orchestrator — Simplified. Two paths only.

Every message goes through ONE of two paths:
  1. Instant command (volume, time, open app) — sub-second, no LLM
  2. Claude via browser — everything else, no exceptions

No action detection. No caching. No complex routing.
Claude's Cowork handles questions AND Mac control.
"""
import asyncio
import json
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
    ACTIVE = "active"
    FOCUS = "focus"
    SLEEP = "sleep"


FOCUS_THRESHOLD = 70
SLEEP_THRESHOLD = 90


class Orchestrator:
    """Central coordinator for JARVIS. Two paths: instant || Claude."""

    def __init__(self):
        self.spine = MemorySpine()
        self.graph = EntityGraph()
        self.intelligence = Intelligence()
        self.patterns = PatternLearner(self.spine)
        self.briefing = BriefingGenerator(self.spine, self.intelligence, self.patterns)

        self.mode = Mode.ACTIVE
        self.running = False
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
        """Main entry point. Two paths: instant command or Claude."""
        timestamp = datetime.now().isoformat()
        priority = score_priority(message, metadata)

        log.info(f"Message received: priority={priority} source={source} mode={self.mode.value}")

        # ── Always handle: STOP ──
        if is_stop_command(message):
            return await self._handle_stop()

        # ── Mode gates ──
        if self.mode == Mode.SLEEP and priority < SLEEP_THRESHOLD:
            return ""
        if self.mode == Mode.FOCUS and priority < FOCUS_THRESHOLD:
            return "In focus mode. Only urgent messages get through. Send /active to switch back."

        # ── Cardiac alert — log it, then fall through to Claude ──
        if is_cardiac_alert(message):
            log.warning(f"CARDIAC ALERT: {message[:100]}")

        # ── Track patterns + extract entities into graph ──
        self.patterns.record_interaction(message)
        self._extract_and_store_entities(message)
        mem_id = self.spine.store_if_meaningful(
            content=f"{source}: {message}",
            type="interaction",
            source=source,
            metadata={"priority": priority, "timestamp": timestamp, **(metadata or {})},
        )
        if mem_id is None:
            # Trivial message — still needs a mem_id ref for reply tracking
            mem_id = -1

        # ── Slash commands ──
        if message.startswith("/"):
            return await self._handle_command(message)

        # ── PATH 1: Only volume/time/date handled instantly (everything else → Cowork) ──
        quick = self._try_quick(message)
        if quick:
            self.spine.store(content=f"JARVIS: {quick}", type="interaction",
                           source="jarvis", metadata={"in_reply_to": mem_id, "instant": True})
            return quick

        # ── PATH 2: EVERYTHING else → Claude/Cowork (full computer use) ──
        memory_context = self._get_relevant_context(message) if len(message.split()) > 1 else ""
        try:
            response = await self.intelligence.think(message=message, memory_context=memory_context)
            self.spine.store(content=f"JARVIS: {response}", type="interaction",
                           source="jarvis", metadata={"in_reply_to": mem_id})
            return response
        except Exception as e:
            log.error(f"Claude error: {e}")
            return f"Apologies sir, something went wrong: {str(e)[:150]}"

    # ── Internal ──

    def _try_quick(self, message: str):
        """ONLY volume and time. Everything else goes to Cowork."""
        import subprocess
        from datetime import datetime
        msg = message.lower().strip()
        for p in ["jarvis ", "hey ", "yo "]:
            if msg.startswith(p): msg = msg[len(p):]

        if msg in ("volume up", "louder"):
            subprocess.run(["osascript", "-e", "set volume output volume ((output volume of (get volume settings)) + 15)"], capture_output=True, timeout=5)
            return "Volume up."
        if msg in ("volume down", "quieter"):
            subprocess.run(["osascript", "-e", "set volume output volume ((output volume of (get volume settings)) - 15)"], capture_output=True, timeout=5)
            return "Volume down."
        if msg in ("mute",):
            subprocess.run(["osascript", "-e", "set volume output muted true"], capture_output=True, timeout=5)
            return "Muted."
        if msg in ("unmute",):
            subprocess.run(["osascript", "-e", "set volume output muted false"], capture_output=True, timeout=5)
            return "Unmuted."
        if any(x in msg for x in ["what time", "whats the time"]):
            return datetime.now().strftime("It's %I:%M %p, sir.")
        if any(x in msg for x in ["what date", "whats the date", "what day"]):
            return datetime.now().strftime("%A, %d %B %Y.")
        return None

    async def _handle_stop(self) -> str:
        log.warning("STOP command received — halting all actions")
        self._stop_event.set()
        await asyncio.sleep(0.5)
        self._stop_event.clear()
        return "All actions halted. What's happening?"

    async def _handle_command(self, message: str) -> str:
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
        old_mode = self.mode
        self.mode = mode
        log.info(f"Mode changed: {old_mode.value} → {mode.value}")
        return f"Mode: {mode.value}"

    def _get_status(self) -> str:
        stats = self.spine.stats()
        return (
            f"Mode: {self.mode.value}\n"
            f"Memories: {stats['total']} (hot: {stats['by_tier'].get('hot', 0)}, "
            f"warm: {stats['by_tier'].get('warm', 0)})\n"
            f"Entities: {self.graph.stats()['total_entities']}"
        )

    def _search_memory(self, query: str) -> str:
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
        mem_stats = self.spine.stats()
        graph_stats = self.graph.stats()
        health = await self.intelligence.health_check()
        return (
            f"Memory: {mem_stats}\n"
            f"Graph: {graph_stats}\n"
            f"Intelligence: {health}"
        )

    def _get_relevant_context(self, message: str, limit: int = 5) -> str:
        """Build memory context: FTS5 search + recent conversation + entity graph."""
        parts = []

        # 1) FTS5 search for topical relevance
        search_results = self.spine.search_text(message, limit=limit)
        search_ids = set()
        if search_results:
            for r in search_results:
                search_ids.add(r.get("id"))
                tier = r.get("tier", "")
                ts = r.get("timestamp", "")[:16]
                # Prefer summary for compacted tiers, full content for hot
                if tier in ("warm", "cold", "archive") and r.get("summary"):
                    text = r["summary"]
                else:
                    text = r.get("content", "")
                parts.append(f"[{ts} | {tier}] {text[:300]}")

        # 2) Last 3 messages for conversational continuity
        recent = self.spine.get_recent(hours=1, limit=3, type="interaction")
        for r in recent:
            if r.get("id") not in search_ids:
                text = r.get("content", "")[:200]
                parts.append(f"[recent] {text}")

        # 3) Entity graph enrichment (best-effort)
        try:
            topics = self.patterns._extract_topics(message)
            for topic in topics[:3]:
                connected = self.graph.get_connected_entities(topic, max_depth=1)
                if connected:
                    names = ", ".join(list(connected)[:5])
                    parts.append(f"[graph] {topic} relates to: {names}")
        except Exception:
            pass

        return "\n".join(parts) if parts else ""

    def _extract_and_store_entities(self, message: str):
        """Extract entities from message and update the entity graph.

        Uses the pattern learner's topic extraction + simple proper noun detection.
        """
        try:
            # Known topics (financial instruments, domains)
            topics = self.patterns._extract_topics(message)
            for topic in topics:
                entity_type = "topic"
                if topic.isupper() and len(topic) <= 5:
                    entity_type = "instrument"
                self.graph.add_entity(topic, entity_type=entity_type)

            # Co-occurrence: if multiple entities in one message, they're related
            if len(topics) > 1:
                for i in range(len(topics)):
                    for j in range(i + 1, len(topics)):
                        self.graph.add_relation(
                            topics[i], topics[j],
                            relation_type="co_mentioned",
                            weight=0.5,
                        )

            # Simple proper noun detection (capitalised words not at sentence start)
            import re
            words = message.split()
            for idx, word in enumerate(words):
                clean = re.sub(r'[^\w]', '', word)
                if (clean and clean[0].isupper() and len(clean) > 2
                        and idx > 0 and clean.lower() not in {"the", "and", "but", "for"}):
                    self.graph.add_entity(clean, entity_type="person_or_place")

        except Exception as e:
            log.debug(f"Entity extraction error (non-fatal): {e}")

    async def _morning_briefing_job(self) -> str:
        log.info("Generating morning briefing...")
        briefing = await self.briefing.morning_briefing()
        self.spine.store(content=briefing, type="briefing", source="system")
        if self.send_message_callback:
            await self.send_message_callback(briefing)
        return briefing

    async def _evening_review_job(self) -> str:
        log.info("Generating evening review...")
        review = await self.briefing.evening_review()
        self.spine.store(content=review, type="briefing", source="system")
        if self.send_message_callback:
            await self.send_message_callback(review)
        return review

    async def shutdown(self):
        log.info("Shutting down orchestrator...")
        self.running = False
        await self.intelligence.shutdown()
        self.spine.close()
        log.info("Orchestrator shut down")
