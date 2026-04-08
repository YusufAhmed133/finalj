"""
Briefing Generator — Morning 7am, Evening 9pm.

Morning: schedule, weather (Open-Meteo API), overnight AI/market news, pending items.
Evening: what got done, what's pending, tomorrow preview.
"""
import asyncio
from datetime import datetime
from typing import Optional

import httpx

from jarvis.identity.loader import get_user_first_name, get_identity
from jarvis.memory.spine import MemorySpine
from jarvis.utils.logger import get_logger

log = get_logger("orchestrator.briefing")


async def _get_weather() -> str:
    """Get Sydney weather via Open-Meteo (free, no API key)."""
    try:
        url = "https://api.open-meteo.com/v1/forecast?latitude=-33.87&longitude=151.21&current=temperature_2m,weathercode&timezone=Australia/Sydney"
        async with httpx.AsyncClient() as client:
            r = await client.get(url, timeout=10)
            data = r.json()
            current = data.get("current", {})
            temp = current.get("temperature_2m", "?")
            code = current.get("weathercode", 0)
            # Simple weather code mapping
            conditions = {0: "Clear", 1: "Mainly clear", 2: "Partly cloudy",
                         3: "Overcast", 45: "Foggy", 51: "Light drizzle",
                         61: "Light rain", 63: "Rain", 65: "Heavy rain",
                         80: "Showers", 95: "Thunderstorm"}
            condition = conditions.get(code, f"Code {code}")
            return f"{temp}°C, {condition}"
    except Exception as e:
        log.warning(f"Weather fetch failed: {e}")
        return "Weather unavailable"


class BriefingGenerator:

    def __init__(self, spine: MemorySpine, intelligence=None):
        self.spine = spine
        self.intelligence = intelligence

    async def morning_briefing(self) -> str:
        name = get_user_first_name()
        now = datetime.now()
        day = now.strftime("%A")
        date = now.strftime("%d %B %Y")

        weather = await _get_weather()

        sections = [f"Good morning {name}. {day}, {date}.\nWeather: {weather}"]

        # Schedule from memory
        schedule = self._get_schedule()
        if schedule:
            sections.append(f"Today:\n{schedule}")

        # Overnight knowledge highlights
        knowledge = self._get_knowledge_highlights()
        if knowledge:
            sections.append(f"Overnight:\n{knowledge}")

        # Pending
        pending = self._get_pending()
        if pending:
            sections.append(f"Pending:\n{pending}")

        raw = "\n\n".join(sections)

        # Polish with Claude if available
        if self.intelligence:
            try:
                polished = await self.intelligence.think(
                    f"Polish this morning briefing. Keep it concise and direct. Don't add fluff:\n\n{raw}"
                )
                return polished
            except Exception as e:
                log.warning(f"Intelligence unavailable for briefing: {e}")

        return raw

    async def evening_review(self) -> str:
        name = get_user_first_name()
        now = datetime.now()
        date = now.strftime("%d %B %Y")

        sections = [f"Evening review — {date}"]

        today = self.spine.get_recent(hours=14, type="interaction")
        if today:
            sections.append(f"Conversations: {len(today)} today")

        actions = self.spine.get_recent(hours=14, type="action")
        if actions:
            sections.append(f"Actions: {len(actions)}")

        knowledge = self.spine.get_recent(hours=14, type="knowledge")
        if knowledge:
            sections.append(f"Knowledge items scraped: {len(knowledge)}")

        raw = "\n\n".join(sections)

        if self.intelligence:
            try:
                return await self.intelligence.think(
                    f"Polish this evening review. Brief and direct:\n\n{raw}"
                )
            except Exception:
                pass

        return raw

    def _get_schedule(self) -> str:
        today = datetime.now().strftime("%Y-%m-%d")
        results = self.spine.search_text(today, limit=5)
        cal = [r for r in results if r.get("type") in ("import_calendar", "calendar")]
        if cal:
            return "\n".join(f"- {r['content'].split(chr(10))[0][:100]}" for r in cal[:5])
        return ""

    def _get_knowledge_highlights(self) -> str:
        items = self.spine.get_recent(hours=12, type="knowledge")
        if not items:
            return ""
        # Top 5 by score (from metadata)
        scored = []
        for item in items:
            try:
                meta = item.get("metadata")
                if meta and isinstance(meta, str):
                    import json
                    meta = json.loads(meta)
                score = meta.get("score", 0) if meta else 0
                scored.append((score, item))
            except Exception:
                scored.append((0, item))
        scored.sort(key=lambda x: x[0], reverse=True)
        lines = []
        for _, item in scored[:5]:
            content = item.get("content", "")[:120]
            lines.append(f"- {content}")
        return "\n".join(lines)

    def _get_pending(self) -> str:
        results = self.spine.search_text("reminder pending todo", limit=3)
        if results:
            return "\n".join(f"- {r['content'][:100]}" for r in results[:3])
        return ""
