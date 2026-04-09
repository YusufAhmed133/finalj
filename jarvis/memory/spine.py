"""
Memory Spine — Core read/write/search for JARVIS memory.

Architecture:
- SQLite database with FTS5 for full-text search
- sqlite-vec for vector similarity search
- Tiered storage: hot (0-7d), warm (7-30d), cold (30-90d), archive (90d+)
- Every interaction stored with timestamp, type, content, entities, embedding
"""
import sqlite3
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from jarvis.utils.logger import get_logger

log = get_logger("memory.spine")

DB_PATH = Path(__file__).parent.parent.parent / "data" / "context.db"

# Memory tiers
TIER_HOT = "hot"        # 0-7 days, full text
TIER_WARM = "warm"      # 7-30 days, summarised
TIER_COLD = "cold"      # 30-90 days, paragraph summary
TIER_ARCHIVE = "archive" # 90+ days, one sentence

TIER_THRESHOLDS = {
    TIER_HOT: 7,
    TIER_WARM: 30,
    TIER_COLD: 90,
}


class MemorySpine:
    """Core memory system for JARVIS."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()
        log.info(f"Memory spine initialized at {self.db_path}")

    def _init_schema(self):
        """Create tables and FTS5 virtual table."""
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                type TEXT NOT NULL,
                tier TEXT NOT NULL DEFAULT 'hot',
                source TEXT,
                content TEXT NOT NULL,
                summary TEXT,
                entities TEXT,
                metadata TEXT,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_memories_timestamp ON memories(timestamp);
            CREATE INDEX IF NOT EXISTS idx_memories_tier ON memories(tier);
            CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(type);
            CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at);
        """)

        # FTS5 virtual table for full-text search
        self.conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
                content,
                summary,
                entities,
                content='memories',
                content_rowid='id',
                tokenize='porter unicode61'
            )
        """)

        # Triggers to keep FTS in sync
        self.conn.executescript("""
            CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
                INSERT INTO memories_fts(rowid, content, summary, entities)
                VALUES (new.id, new.content, new.summary, new.entities);
            END;

            CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
                INSERT INTO memories_fts(memories_fts, rowid, content, summary, entities)
                VALUES ('delete', old.id, old.content, old.summary, old.entities);
            END;

            CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
                INSERT INTO memories_fts(memories_fts, rowid, content, summary, entities)
                VALUES ('delete', old.id, old.content, old.summary, old.entities);
                INSERT INTO memories_fts(rowid, content, summary, entities)
                VALUES (new.id, new.content, new.summary, new.entities);
            END;
        """)

        # Action log for computer use
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS action_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                action_type TEXT NOT NULL,
                description TEXT NOT NULL,
                screenshot_before TEXT,
                screenshot_after TEXT,
                outcome TEXT,
                created_at REAL NOT NULL
            )
        """)

        self.conn.commit()

    def store(
        self,
        content: str,
        type: str = "interaction",
        source: str = "telegram",
        entities: Optional[list] = None,
        metadata: Optional[dict] = None,
        summary: Optional[str] = None,
    ) -> int:
        """Store a new memory. Returns the memory ID."""
        now = time.time()
        ts = datetime.now().isoformat()
        entities_json = json.dumps(entities) if entities else None
        metadata_json = json.dumps(metadata) if metadata else None

        cursor = self.conn.execute(
            """INSERT INTO memories (timestamp, type, tier, source, content, summary, entities, metadata, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (ts, type, TIER_HOT, source, content, summary, entities_json, metadata_json, now, now),
        )
        self.conn.commit()
        mem_id = cursor.lastrowid
        log.debug(f"Stored memory #{mem_id} type={type} source={source}")
        return mem_id

    def search_text(self, query: str, limit: int = 10, tier: Optional[str] = None) -> list:
        """Full-text search using FTS5 with BM25 ranking + recency boost.

        Extracts keywords, uses OR matching (more recall), then re-ranks
        with a combined score of BM25 relevance + recency.
        """
        keywords = self._extract_search_keywords(query)
        if not keywords:
            return []

        # Use OR for broader recall — AND is too strict for natural language
        fts_query = " OR ".join(keywords)

        # Fetch more candidates than needed so we can re-rank
        fetch_limit = limit * 3
        now = time.time()

        if tier:
            rows = self.conn.execute(
                """SELECT m.*, rank
                   FROM memories_fts fts
                   JOIN memories m ON m.id = fts.rowid
                   WHERE memories_fts MATCH ? AND m.tier = ?
                   ORDER BY rank
                   LIMIT ?""",
                (fts_query, tier, fetch_limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """SELECT m.*, rank
                   FROM memories_fts fts
                   JOIN memories m ON m.id = fts.rowid
                   WHERE memories_fts MATCH ?
                   ORDER BY rank
                   LIMIT ?""",
                (fts_query, fetch_limit),
            ).fetchall()

        # Re-rank: combine BM25 (negative, lower=better) with recency boost
        results = []
        for r in rows:
            d = dict(r)
            age_days = (now - d.get("created_at", now)) / 86400
            # BM25 rank is negative (closer to 0 = better); normalise to positive relevance
            bm25_score = -d.get("rank", 0)
            # Recency: exponential decay, half-life of 7 days
            recency_boost = 2.0 ** (-age_days / 7.0)
            d["_combined_score"] = bm25_score * 0.6 + recency_boost * 0.4
            results.append(d)

        results.sort(key=lambda r: r["_combined_score"], reverse=True)
        return results[:limit]

    @staticmethod
    def _extract_search_keywords(text: str) -> list[str]:
        """Extract meaningful keywords from natural language for FTS5 query."""
        import re
        # Strip punctuation
        text = re.sub(r'[^\w\s]', ' ', text).strip().lower()
        if not text:
            return []

        # Stop words — common words that add noise to FTS5 queries
        stop_words = {
            "i", "me", "my", "we", "you", "your", "he", "she", "it", "they",
            "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
            "have", "has", "had", "do", "does", "did", "will", "would", "could",
            "should", "can", "may", "might", "shall", "must",
            "what", "when", "where", "which", "who", "whom", "how", "why",
            "that", "this", "these", "those", "there", "here",
            "and", "or", "but", "if", "then", "so", "because", "while",
            "of", "in", "on", "at", "to", "for", "with", "from", "by", "about",
            "into", "through", "during", "before", "after", "above", "below",
            "not", "no", "nor", "very", "just", "also", "than", "too",
            "said", "say", "tell", "told", "know", "think", "want", "need",
            "like", "get", "got", "go", "went", "come", "make", "made",
            "last", "did", "about", "something", "anything",
        }

        words = text.split()
        keywords = [w for w in words if w not in stop_words and len(w) > 1]

        # Deduplicate while preserving order
        seen = set()
        unique = []
        for kw in keywords:
            if kw not in seen:
                seen.add(kw)
                unique.append(kw)

        return unique[:8]  # Cap at 8 keywords to avoid FTS5 query explosion

    def get_recent(self, hours: int = 24, limit: int = 50, type: Optional[str] = None) -> list:
        """Get recent memories within the last N hours."""
        cutoff = time.time() - (hours * 3600)
        if type:
            rows = self.conn.execute(
                """SELECT * FROM memories
                   WHERE created_at > ? AND type = ?
                   ORDER BY created_at DESC LIMIT ?""",
                (cutoff, type, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """SELECT * FROM memories
                   WHERE created_at > ?
                   ORDER BY created_at DESC LIMIT ?""",
                (cutoff, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_by_id(self, mem_id: int) -> Optional[dict]:
        """Get a single memory by ID."""
        row = self.conn.execute("SELECT * FROM memories WHERE id = ?", (mem_id,)).fetchone()
        return dict(row) if row else None

    def update_tier(self, mem_id: int, new_tier: str, summary: Optional[str] = None):
        """Move a memory to a different tier, optionally updating summary."""
        now = time.time()
        if summary:
            self.conn.execute(
                "UPDATE memories SET tier = ?, summary = ?, updated_at = ? WHERE id = ?",
                (new_tier, summary, now, mem_id),
            )
        else:
            self.conn.execute(
                "UPDATE memories SET tier = ?, updated_at = ? WHERE id = ?",
                (new_tier, now, mem_id),
            )
        self.conn.commit()

    def get_memories_for_compaction(self, tier: str) -> list:
        """Get memories that should be compacted to the next tier."""
        threshold_days = TIER_THRESHOLDS.get(tier)
        if threshold_days is None:
            return []
        cutoff = time.time() - (threshold_days * 86400)
        rows = self.conn.execute(
            """SELECT * FROM memories
               WHERE tier = ? AND created_at < ?
               ORDER BY created_at ASC""",
            (tier, cutoff),
        ).fetchall()
        return [dict(r) for r in rows]

    def log_action(
        self,
        action_type: str,
        description: str,
        screenshot_before: Optional[str] = None,
        screenshot_after: Optional[str] = None,
        outcome: Optional[str] = None,
    ) -> int:
        """Log a computer use action."""
        now = time.time()
        ts = datetime.now().isoformat()
        cursor = self.conn.execute(
            """INSERT INTO action_log (timestamp, action_type, description, screenshot_before, screenshot_after, outcome, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (ts, action_type, description, screenshot_before, screenshot_after, outcome, now),
        )
        self.conn.commit()
        return cursor.lastrowid

    def store_if_meaningful(
        self,
        content: str,
        type: str = "interaction",
        source: str = "telegram",
        entities: Optional[list] = None,
        metadata: Optional[dict] = None,
        summary: Optional[str] = None,
    ) -> Optional[int]:
        """Store a memory only if it carries meaningful information.

        Skips trivial messages (acknowledgements, single-word reactions, etc.)
        to keep the memory database high-signal.
        Returns memory ID or None if skipped.
        """
        # Extract the actual message (strip "source: " prefix if present)
        text = content
        if ": " in content:
            text = content.split(": ", 1)[1]
        text = text.strip().lower()

        # Skip trivial messages
        trivial_patterns = {
            "ok", "okay", "sure", "thanks", "thank you", "thx", "ty",
            "yes", "no", "yep", "nope", "yea", "yeah", "nah",
            "lol", "haha", "lmao", "nice", "cool", "great", "good",
            "k", "kk", "hmm", "hm", "ah", "oh", "right",
            "got it", "sounds good", "will do", "perfect",
        }
        if text in trivial_patterns or len(text) < 3:
            return None

        return self.store(content, type, source, entities, metadata, summary)

    def count(self, tier: Optional[str] = None) -> int:
        """Count memories, optionally filtered by tier."""
        if tier:
            row = self.conn.execute("SELECT COUNT(*) FROM memories WHERE tier = ?", (tier,)).fetchone()
        else:
            row = self.conn.execute("SELECT COUNT(*) FROM memories").fetchone()
        return row[0]

    def stats(self) -> dict:
        """Get memory statistics."""
        total = self.count()
        by_tier = {}
        for tier in [TIER_HOT, TIER_WARM, TIER_COLD, TIER_ARCHIVE]:
            by_tier[tier] = self.count(tier)
        by_type = {}
        for row in self.conn.execute("SELECT type, COUNT(*) as cnt FROM memories GROUP BY type").fetchall():
            by_type[row["type"]] = row["cnt"]
        return {"total": total, "by_tier": by_tier, "by_type": by_type}

    def close(self):
        self.conn.close()
        log.info("Memory spine closed")
