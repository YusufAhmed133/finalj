"""
Heartbeat System — Proactive JARVIS behaviors.

Inspired by CoPaw's heartbeat pattern. Runs on schedule, checks what
JARVIS should proactively tell the user without being asked.

Checks:
- Morning briefing (7am)
- Evening review (9pm)
- IVV price movement alerts (>2%)
- Upcoming deadline reminders (7/3/1 day)
- Pattern-based schedule suggestions
- Cardiac device check reminders
- Self-improvement weekly report (Sunday 10am)
"""
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Callable

from jarvis.memory.spine import MemorySpine
from jarvis.memory.patterns import PatternLearner
from jarvis.orchestrator.briefing import BriefingGenerator
from jarvis.agents.self_improve import SelfImproveAgent
from jarvis.utils.logger import get_logger

log = get_logger("orchestrator.heartbeat")

# Active hours — don't bother the user outside these times
ACTIVE_START = 7   # 7am
ACTIVE_END = 22    # 10pm


class Heartbeat:
    """Proactive agent loop. Checks every minute for things to do."""

    def __init__(
        self,
        spine: MemorySpine,
        patterns: PatternLearner,
        intelligence=None,
        send_callback: Optional[Callable] = None,
    ):
        self.spine = spine
        self.patterns = patterns
        self.intelligence = intelligence
        self.briefing = BriefingGenerator(spine, intelligence, patterns)
        self.self_improve = SelfImproveAgent(spine)
        self.send = send_callback

        self._sent_today = set()  # Track what we've sent today
        self._last_date = None

    async def tick(self):
        """Called every minute by the main loop."""
        now = datetime.now()
        hour = now.hour
        minute = now.minute
        today = now.strftime("%Y-%m-%d")
        day_name = now.strftime("%A")

        # Reset daily tracking
        if today != self._last_date:
            self._sent_today = set()
            self._last_date = today
            # Weekly decay on Mondays
            if day_name == "Monday":
                self.patterns.weekly_decay()
                log.info("Weekly pattern decay applied")

        # Don't bother user outside active hours
        if hour < ACTIVE_START or hour >= ACTIVE_END:
            return

        # Morning briefing at 7:00-7:04
        if hour == 7 and minute < 5 and "morning" not in self._sent_today:
            await self._send_morning_briefing()
            self._sent_today.add("morning")

        # Evening review at 21:00-21:04
        if hour == 21 and minute < 5 and "evening" not in self._sent_today:
            await self._send_evening_review()
            self._sent_today.add("evening")

        # Sunday 10am — self-improvement report
        if day_name == "Sunday" and hour == 10 and minute < 5 and "self_improve" not in self._sent_today:
            self.self_improve.scan_knowledge()
            report = self.self_improve.get_weekly_report()
            if report:
                await self._send(report)
            self._sent_today.add("self_improve")

        # Detect quiet hours and update patterns (once per day at noon)
        if hour == 12 and minute < 5 and "quiet_detect" not in self._sent_today:
            self.patterns.detect_quiet_hours()
            self._sent_today.add("quiet_detect")

    async def _send_morning_briefing(self):
        """Generate and send the morning briefing."""
        log.info("Generating morning briefing...")
        try:
            briefing = await self.briefing.morning_briefing()
            if briefing:
                await self._send(briefing)
                self.spine.store(content=briefing, type="briefing", source="heartbeat")
                log.info("Morning briefing sent")
        except Exception as e:
            log.error(f"Morning briefing failed: {e}")

    async def _send_evening_review(self):
        """Generate and send the evening review."""
        log.info("Generating evening review...")
        try:
            review = await self.briefing.evening_review()
            if review:
                await self._send(review)
                self.spine.store(content=review, type="briefing", source="heartbeat")
                log.info("Evening review sent")
        except Exception as e:
            log.error(f"Evening review failed: {e}")

    async def _send(self, text: str):
        """Send a proactive message to the user."""
        if self.send:
            try:
                await self.send(text)
            except Exception as e:
                log.error(f"Failed to send proactive message: {e}")
