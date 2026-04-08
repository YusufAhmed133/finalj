"""
Pattern Learning — Track user behavior and adapt.

Tracks:
- Topics asked about repeatedly → auto-include in briefings
- Time-of-day activity patterns → detect focus time
- Entities frequently mentioned → boost in memory search

Stores in data/preferences.json, applied dynamically.
"""
import json
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

from jarvis.memory.spine import MemorySpine
from jarvis.utils.logger import get_logger

log = get_logger("memory.patterns")

PREFERENCES_PATH = Path(__file__).parent.parent.parent / "data" / "preferences.json"


class PatternLearner:

    def __init__(self, spine: MemorySpine):
        self.spine = spine
        self.prefs = self._load()

    def _load(self) -> dict:
        if PREFERENCES_PATH.exists():
            try:
                return json.loads(PREFERENCES_PATH.read_text())
            except Exception:
                pass
        return {
            "topic_counts": {},      # topic -> count this week
            "topic_last_asked": {},  # topic -> timestamp
            "auto_briefing": [],     # topics to auto-include in briefing
            "quiet_hours": {},       # day_of_week -> [quiet_hour_ranges]
            "hourly_activity": {},   # hour -> message_count
        }

    def _save(self):
        PREFERENCES_PATH.parent.mkdir(parents=True, exist_ok=True)
        PREFERENCES_PATH.write_text(json.dumps(self.prefs, indent=2))

    def record_interaction(self, message: str):
        """Record an interaction for pattern analysis."""
        now = datetime.now()
        hour = str(now.hour)

        # Track hourly activity
        activity = self.prefs.get("hourly_activity", {})
        activity[hour] = activity.get(hour, 0) + 1
        self.prefs["hourly_activity"] = activity

        # Extract topics (simple keyword extraction)
        topics = self._extract_topics(message)
        counts = self.prefs.get("topic_counts", {})
        last_asked = self.prefs.get("topic_last_asked", {})

        for topic in topics:
            counts[topic] = counts.get(topic, 0) + 1
            last_asked[topic] = time.time()

            # Auto-include in briefing if asked 3+ times in a week
            if counts[topic] >= 3 and topic not in self.prefs.get("auto_briefing", []):
                self.prefs.setdefault("auto_briefing", []).append(topic)
                log.info(f"Auto-briefing: added '{topic}' (asked {counts[topic]} times)")

        self.prefs["topic_counts"] = counts
        self.prefs["topic_last_asked"] = last_asked
        self._save()

    def detect_quiet_hours(self):
        """Analyze hourly activity to find quiet periods (potential focus time)."""
        activity = self.prefs.get("hourly_activity", {})
        if not activity:
            return

        avg = sum(activity.values()) / max(len(activity), 1)
        quiet = [int(h) for h, count in activity.items() if count < avg * 0.3]

        # Group consecutive quiet hours
        now = datetime.now()
        day = now.strftime("%A")
        self.prefs.setdefault("quiet_hours", {})[day] = quiet
        self._save()

    def get_auto_briefing_topics(self) -> list:
        """Get topics that should be auto-included in briefings."""
        return self.prefs.get("auto_briefing", [])

    def get_quiet_hours(self) -> dict:
        return self.prefs.get("quiet_hours", {})

    def weekly_reset(self):
        """Reset weekly counters (call every Monday)."""
        self.prefs["topic_counts"] = {}
        self._save()

    def _extract_topics(self, message: str) -> list:
        """Simple topic extraction — financial instruments, proper nouns, key terms."""
        import re
        msg = message.lower()
        topics = []

        # Financial instruments
        instruments = ["ivv", "vgs", "vdhg", "aapl", "spy", "asx", "btc", "eth",
                      "ndq", "vas", "a200", "dhhf"]
        for inst in instruments:
            if inst in msg:
                topics.append(inst.upper())

        # Key domains
        domain_keywords = {
            "law": ["contract", "tort", "legal", "aglc", "case law", "statute", "auslaw"],
            "finance": ["invest", "stock", "market", "etf", "portfolio", "dca"],
            "health": ["cardiac", "heart", "gym", "workout", "fitness"],
            "ai": ["claude", "gpt", "llm", "model", "ai ", "machine learning"],
            "uni": ["wam", "unsw", "assignment", "exam", "lecture", "tutorial"],
        }
        for domain, keywords in domain_keywords.items():
            if any(kw in msg for kw in keywords):
                topics.append(domain)

        return list(set(topics))
