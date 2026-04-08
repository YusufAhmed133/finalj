"""
Self-Learning Pipeline.

Every 6 hours: scrape for techniques that would improve JARVIS itself.
Score each item: does this improve JARVIS specifically?
Items scoring 7+ stored in data/self_improvement.json.
Every Sunday 10am: send top 3 improvements to user on Telegram.
"""
import json
import time
from datetime import datetime
from pathlib import Path

from jarvis.memory.spine import MemorySpine
from jarvis.utils.logger import get_logger

log = get_logger("agents.self_improve")

IMPROVEMENTS_PATH = Path(__file__).parent.parent.parent / "data" / "self_improvement.json"


class SelfImproveAgent:

    def __init__(self, spine: MemorySpine):
        self.spine = spine
        self.improvements = self._load()

    def _load(self) -> list:
        if IMPROVEMENTS_PATH.exists():
            return json.loads(IMPROVEMENTS_PATH.read_text())
        return []

    def _save(self):
        IMPROVEMENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        IMPROVEMENTS_PATH.write_text(json.dumps(self.improvements, indent=2))

    def scan_knowledge(self):
        """Scan recent knowledge items for JARVIS-relevant improvements."""
        items = self.spine.get_recent(hours=24, type="knowledge")
        keywords = [
            "ai assistant", "automation", "browser automation", "playwright",
            "whisper", "voice", "memory", "vector search", "embedding",
            "telegram bot", "whatsapp", "computer use", "claude api",
            "personal ai", "jarvis", "agent", "mcp", "tool use",
        ]

        candidates = []
        for item in items:
            content = (item.get("content") or "").lower()
            score = sum(1 for kw in keywords if kw in content)
            if score >= 2:  # At least 2 keyword matches
                candidates.append({
                    "content": item.get("content", "")[:500],
                    "score": score,
                    "source": item.get("source", ""),
                    "found_at": datetime.now().isoformat(),
                })

        # Store high-scoring items
        for c in candidates:
            if c["score"] >= 3 and not any(
                e.get("content", "")[:100] == c["content"][:100]
                for e in self.improvements
            ):
                self.improvements.append(c)
                log.info(f"Self-improvement item found (score={c['score']}): {c['content'][:80]}")

        # Keep only top 50
        self.improvements.sort(key=lambda x: x.get("score", 0), reverse=True)
        self.improvements = self.improvements[:50]
        self._save()

        return len(candidates)

    def get_weekly_report(self, top_n: int = 3) -> str:
        """Generate the Sunday 10am improvement report."""
        if not self.improvements:
            return ""

        # Get top items from this week
        week_ago = time.time() - (7 * 86400)
        recent = [i for i in self.improvements
                  if i.get("found_at", "") > datetime.fromtimestamp(week_ago).isoformat()]

        if not recent:
            recent = self.improvements[:top_n]

        recent.sort(key=lambda x: x.get("score", 0), reverse=True)
        top = recent[:top_n]

        if not top:
            return ""

        lines = ["Here are 3 things I found this week that could make me better:\n"]
        for i, item in enumerate(top, 1):
            content = item.get("content", "")[:200]
            source = item.get("source", "")
            lines.append(f"{i}. [{source}] {content}\n")

        lines.append("Want me to implement any of them? Reply with the number.")
        return "\n".join(lines)
