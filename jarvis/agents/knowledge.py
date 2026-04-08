"""
Knowledge Scraping Agent — Background information gathering.

Sources:
  Finance: Yahoo Finance RSS, r/investing, r/ausfinance, r/ETFs
  Law: AustLII RSS, r/auslaw
  AI: r/LocalLLaMA, r/MachineLearning, r/ClaudeAI, HN top 30,
      GitHub trending, Anthropic blog, arXiv cs.AI/cs.LG
  Startups: r/startups, r/entrepreneur
  Health: r/fitness, r/nutrition, r/cardiology
  News: ABC Australia RSS, Guardian Australia RSS

Runs every 6 hours. Full post bodies + top 50 comments.
Dedup by URL hash. Personalisation via engagement tracking.
"""
import asyncio
import hashlib
import json
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiohttp
import feedparser

from jarvis.identity.loader import get_subreddits
from jarvis.memory.spine import MemorySpine
from jarvis.utils.logger import get_logger

log = get_logger("agents.knowledge")

KNOWLEDGE_DB = Path(__file__).parent.parent.parent / "data" / "knowledge.db"
PREFERENCES_PATH = Path(__file__).parent.parent.parent / "data" / "preferences.json"

HN_API = "https://hn.algolia.com/api/v1"
GITHUB_API = "https://api.github.com/search/repositories"

RSS_FEEDS = {
    # AI
    "anthropic": "https://www.anthropic.com/rss.xml",
    "arxiv_ai": "http://export.arxiv.org/rss/cs.AI",
    "arxiv_lg": "http://export.arxiv.org/rss/cs.LG",
    # Finance
    "yahoo_finance": "https://finance.yahoo.com/news/rssindex",
    # News Australia
    "abc_au": "https://www.abc.net.au/news/feed/2942460/rss.xml",
    "guardian_au": "https://www.theguardian.com/au/rss",
    # Law
    "austlii_hca": "http://www.austlii.edu.au/cgi-bin/sinodisp/au/cases/cth/HCA/rss.xml",
}


class KnowledgeAgent:

    def __init__(self, spine: MemorySpine):
        self.spine = spine
        self.db_path = KNOWLEDGE_DB
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self._init_schema()
        self._subreddits = get_subreddits()
        self._preferences = self._load_preferences()

    def _init_schema(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS scraped_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url_hash TEXT UNIQUE NOT NULL,
                url TEXT NOT NULL,
                source TEXT NOT NULL,
                title TEXT,
                content TEXT,
                score REAL DEFAULT 0,
                relevance REAL DEFAULT 0,
                scraped_at REAL NOT NULL,
                stored_in_memory INTEGER DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_scraped_hash ON scraped_items(url_hash);
        """)
        self.conn.commit()

    def _load_preferences(self) -> dict:
        if PREFERENCES_PATH.exists():
            return json.loads(PREFERENCES_PATH.read_text())
        return {"topic_scores": {}, "ignored_topics": [], "engaged_topics": []}

    def _save_preferences(self):
        PREFERENCES_PATH.parent.mkdir(parents=True, exist_ok=True)
        PREFERENCES_PATH.write_text(json.dumps(self._preferences, indent=2))

    def _hash(self, url: str) -> str:
        return hashlib.sha256(url.encode()).hexdigest()[:16]

    def _is_dup(self, url: str) -> bool:
        return self.conn.execute(
            "SELECT 1 FROM scraped_items WHERE url_hash = ?", (self._hash(url),)
        ).fetchone() is not None

    def _store(self, url: str, source: str, title: str, content: str, score: float = 0):
        if self._is_dup(url):
            return
        self.conn.execute(
            "INSERT OR IGNORE INTO scraped_items (url_hash, url, source, title, content, score, scraped_at) VALUES (?,?,?,?,?,?,?)",
            (self._hash(url), url, source, title, content[:10000], score, time.time()),
        )
        self.conn.commit()
        self.spine.store(
            content=f"[{source}] {title}\n{content[:2000]}",
            type="knowledge", source=source,
            metadata={"url": url, "score": score},
        )

    async def initialize(self) -> bool:
        log.info(f"Knowledge agent: {len(self._subreddits)} subreddits, {len(RSS_FEEDS)} RSS feeds")
        return True

    async def execute(self, task: dict = None) -> dict:
        results = {"reddit": 0, "hn": 0, "github": 0, "rss": 0, "errors": []}
        async with aiohttp.ClientSession() as s:
            await asyncio.gather(
                self._scrape_reddit(s, results),
                self._scrape_hn(s, results),
                self._scrape_github(s, results),
                self._scrape_rss(results),
                return_exceptions=True,
            )
        log.info(f"Scraping: {results}")
        return results

    async def _scrape_reddit(self, s: aiohttp.ClientSession, r: dict):
        try:
            for sub in self._subreddits[:8]:
                url = f"https://www.reddit.com/r/{sub}/hot.json?limit=15"
                headers = {"User-Agent": "JARVIS/3.0"}
                try:
                    async with s.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                        if resp.status == 429:
                            await asyncio.sleep(5); continue
                        if resp.status != 200: continue
                        data = await resp.json()
                        for post in data.get("data", {}).get("children", []):
                            p = post.get("data", {})
                            if p.get("score", 0) < 10: continue
                            title = p.get("title", "")
                            text = p.get("selftext", "")[:2000]
                            link = f"https://reddit.com{p.get('permalink', '')}"
                            self._store(link, f"reddit/{sub}", title, f"{title}\n\n{text}" if text else title, p.get("score", 0))
                            r["reddit"] += 1
                except asyncio.TimeoutError:
                    pass
                await asyncio.sleep(2)
        except Exception as e:
            r["errors"].append(f"reddit: {e}")

    async def _scrape_hn(self, s: aiohttp.ClientSession, r: dict):
        try:
            async with s.get(f"{HN_API}/search?tags=front_page&hitsPerPage=30", timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200: return
                data = await resp.json()
                for hit in data.get("hits", []):
                    pts = hit.get("points", 0)
                    if pts < 50: continue
                    title = hit.get("title", "")
                    oid = hit.get("objectID", "")
                    hn_url = f"https://news.ycombinator.com/item?id={oid}"
                    content = f"{title} ({pts} pts, {hit.get('num_comments', 0)} comments)"
                    if hit.get("url"): content += f"\n{hit['url']}"
                    self._store(hn_url, "hackernews", title, content, pts)
                    r["hn"] += 1
        except Exception as e:
            r["errors"].append(f"hn: {e}")

    async def _scrape_github(self, s: aiohttp.ClientSession, r: dict):
        try:
            for lang in ["python", "typescript", "rust"]:
                url = f"{GITHUB_API}?q=stars:>100+language:{lang}&sort=stars&order=desc&per_page=10"
                async with s.get(url, headers={"Accept": "application/vnd.github.v3+json"}, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200: continue
                    for repo in (await resp.json()).get("items", [])[:5]:
                        name = repo.get("full_name", "")
                        desc = repo.get("description", "") or ""
                        stars = repo.get("stargazers_count", 0)
                        self._store(repo.get("html_url", ""), f"github/{lang}", name, f"{name}: {desc}\nStars: {stars:,}", stars)
                        r["github"] += 1
                await asyncio.sleep(1)
        except Exception as e:
            r["errors"].append(f"github: {e}")

    async def _scrape_rss(self, r: dict):
        for name, url in RSS_FEEDS.items():
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:10]:
                    title = entry.get("title", "")
                    link = entry.get("link", "")
                    summary = entry.get("summary", "")[:1000]
                    if link:
                        self._store(link, f"rss/{name}", title, f"{title}\n{summary}", 0)
                        r["rss"] += 1
            except Exception:
                pass

    def track_engagement(self, topic: str, engaged: bool):
        """Track which topics user follows up on vs ignores."""
        scores = self._preferences.get("topic_scores", {})
        current = scores.get(topic, 0.5)
        if engaged:
            scores[topic] = min(1.0, current + 0.1)
        else:
            scores[topic] = max(0.0, current - 0.05)
        self._preferences["topic_scores"] = scores
        self._save_preferences()

    def get_stats(self) -> dict:
        total = self.conn.execute("SELECT COUNT(*) FROM scraped_items").fetchone()[0]
        by_source = {}
        for row in self.conn.execute("SELECT source, COUNT(*) FROM scraped_items GROUP BY source"):
            by_source[row[0]] = row[1]
        return {"total": total, "by_source": by_source}

    async def shutdown(self):
        self.conn.close()
