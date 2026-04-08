"""
Briefing Generator — Morning and evening briefings.

Morning (7am AEST):
- Today's schedule (from Google Calendar)
- Weather
- Overnight AI/tech news (from scraped knowledge)
- Market summary (IVV, key indices)
- Any pending tasks or reminders

Evening (9pm AEST):
- What got done today
- What's pending
- Tomorrow's schedule preview
"""
from datetime import datetime
from typing import Optional

from jarvis.memory.spine import MemorySpine
from jarvis.utils.logger import get_logger

log = get_logger("orchestrator.briefing")


class BriefingGenerator:
    """Generates morning and evening briefings."""

    def __init__(self, spine: MemorySpine, intelligence=None):
        """
        Args:
            spine: Memory spine for retrieving context
            intelligence: Intelligence layer for generating summaries
        """
        self.spine = spine
        self.intelligence = intelligence

    async def morning_briefing(self) -> str:
        """Generate the morning briefing.

        If intelligence layer is available, uses Claude to synthesize.
        Otherwise, returns a structured raw briefing.
        """
        now = datetime.now()
        day_name = now.strftime("%A")
        date_str = now.strftime("%d %B %Y")

        sections = []
        from jarvis.identity.loader import get_user_first_name
        sections.append(f"Good morning {get_user_first_name()}. {day_name}, {date_str}.")

        # Schedule section — fetch from recent calendar imports or live
        schedule = self._get_todays_schedule()
        if schedule:
            sections.append(f"Schedule:\n{schedule}")
        else:
            sections.append("Schedule: Nothing found in memory. Use /calendar to sync.")

        # Overnight knowledge — recent scraped items
        knowledge = self._get_overnight_knowledge()
        if knowledge:
            sections.append(f"Overnight:\n{knowledge}")

        # Pending items
        pending = self._get_pending_items()
        if pending:
            sections.append(f"Pending:\n{pending}")

        raw_briefing = "\n\n".join(sections)

        # If intelligence available, have Claude polish it
        if self.intelligence:
            try:
                polished = await self.intelligence.think(
                    message=f"Polish this morning briefing into a concise, direct message. Keep all facts, remove fluff:\n\n{raw_briefing}",
                    context=f"Time: {now.strftime('%H:%M AEST')} on {date_str}",
                )
                return polished
            except Exception as e:
                log.warning(f"Intelligence unavailable for briefing polish: {e}")

        return raw_briefing

    async def evening_review(self) -> str:
        """Generate the evening review."""
        now = datetime.now()
        date_str = now.strftime("%d %B %Y")

        sections = []
        sections.append(f"Evening review — {date_str}")

        # Today's interactions
        today_memories = self.spine.get_recent(hours=14, type="interaction")
        if today_memories:
            topics = set()
            for mem in today_memories[:10]:
                content = mem.get("content", "")[:100]
                topics.add(content.split("\n")[0][:80])
            sections.append(f"Today's conversations ({len(today_memories)} total):\n" +
                          "\n".join(f"- {t}" for t in list(topics)[:5]))

        # Actions taken
        actions = self.spine.get_recent(hours=14, type="action")
        if actions:
            sections.append(f"Actions taken: {len(actions)}")

        # Tomorrow preview
        sections.append("Tomorrow: Check /calendar for schedule.")

        raw_review = "\n\n".join(sections)

        if self.intelligence:
            try:
                polished = await self.intelligence.think(
                    message=f"Polish this evening review into a concise summary:\n\n{raw_review}",
                    context=f"Time: {now.strftime('%H:%M AEST')} on {date_str}",
                )
                return polished
            except Exception as e:
                log.warning(f"Intelligence unavailable for review polish: {e}")

        return raw_review

    def _get_todays_schedule(self) -> str:
        """Get today's calendar events from memory."""
        today = datetime.now().strftime("%Y-%m-%d")
        results = self.spine.search_text(today, limit=10)
        calendar_results = [r for r in results if r.get("type") in ("import_calendar", "calendar")]
        if not calendar_results:
            # Try broader search
            day_name = datetime.now().strftime("%A")
            results = self.spine.search_text(day_name, limit=5)
            calendar_results = [r for r in results if r.get("type") in ("import_calendar", "calendar")]

        if calendar_results:
            lines = []
            for r in calendar_results[:5]:
                content = r.get("content", "")
                # Extract first line (event name)
                first_line = content.split("\n")[0]
                lines.append(f"- {first_line}")
            return "\n".join(lines)
        return ""

    def _get_overnight_knowledge(self) -> str:
        """Get scraped knowledge from overnight."""
        results = self.spine.get_recent(hours=12, type="knowledge")
        if results:
            lines = []
            for r in results[:5]:
                content = r.get("content", "")[:150]
                lines.append(f"- {content}")
            return "\n".join(lines)
        return ""

    def _get_pending_items(self) -> str:
        """Get pending reminders or tasks."""
        results = self.spine.search_text("reminder pending todo", limit=5)
        if results:
            lines = []
            for r in results[:3]:
                content = r.get("content", "")[:100]
                lines.append(f"- {content}")
            return "\n".join(lines)
        return ""
