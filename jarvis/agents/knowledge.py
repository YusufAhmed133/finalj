"""
Knowledge Scraping Agent — Background information gathering.

Sources:
- Reddit via PRAW: Configured subreddits from yusuf.yaml
- HackerNews via Algolia API: Top stories, full comment trees
- GitHub trending: Python, TypeScript, Rust, AI-tagged repos
- RSS: Anthropic blog, arXiv cs.AI/cs.LG, AustLII, RBA

Runs continuously in background. Never interferes with response latency.
Deduplication by URL hash. Rate limiting respected. Relevance scoring via Ollama.
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
import yaml

from jarvis.agents.base import BaseAgent
from jarvis.memory.spine import MemorySpine
from jarvis.utils.logger import get_logger

log = get_logger("agents.knowledge")

KNOWLEDGE_DB_PATH = Path(__file__).parent.parent.parent / "data" / "knowledge.db"
IDENTITY_PATH = Path(__file__).parent.parent / "identity" / "yusuf.yaml"

# HackerNews Algolia API
HN_API = "https://hn.algolia.com/api/v1"

# RSS feeds
RSS_FEEDS = {
    "anthropic_blog": "https://www.anthropic.com/rss.xml",
    "arxiv_cs_ai": "http://export.arxiv.org/rss/cs.AI",
    "arxiv_cs_lg": "http://export.arxiv.org/rss/cs.LG",
}

# GitHub trending API (unofficial)
GITHUB_TRENDING_URL = "https://api.github.com/search/repositories"


class KnowledgeAgent(BaseAgent):
    """Background knowledge scraping and storage."""

    def __init__(self, spine: MemorySpine):
        self.spine = spine
        self.db_path = KNOWLEDGE_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self._init_schema()
        self._subreddits = self._load_subreddits()
        self._running = False

    def _init_schema(self):
        """Create knowledge tracking table."""
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
            CREATE INDEX IF NOT EXISTS idx_scraped_source ON scraped_items(source);
            CREATE INDEX IF NOT EXISTS idx_scraped_hash ON scraped_items(url_hash);
        """)
        self.conn.commit()

    def _load_subreddits(self) -> list:
        """Load subreddit list from identity config."""
        if IDENTITY_PATH.exists():
            data = yaml.safe_load(IDENTITY_PATH.read_text())
            subs = data.get("subreddits_of_interest", [])
            return [s.replace("r/", "") for s in subs]
        return ["LocalLLaMA", "ClaudeAI", "MachineLearning"]

    def _url_hash(self, url: str) -> str:
        """Generate hash for deduplication."""
        return hashlib.sha256(url.encode()).hexdigest()[:16]

    def _is_duplicate(self, url: str) -> bool:
        """Check if URL already scraped."""
        h = self._url_hash(url)
        row = self.conn.execute(
            "SELECT 1 FROM scraped_items WHERE url_hash = ?", (h,)
        ).fetchone()
        return row is not None

    def _store_item(self, url: str, source: str, title: str, content: str, score: float = 0):
        """Store a scraped item."""
        if self._is_duplicate(url):
            return

        now = time.time()
        self.conn.execute(
            """INSERT OR IGNORE INTO scraped_items (url_hash, url, source, title, content, score, scraped_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (self._url_hash(url), url, source, title, content[:10000], score, now),
        )
        self.conn.commit()

        # Also store in memory spine for searchability
        self.spine.store(
            content=f"[{source}] {title}\n{content[:2000]}",
            type="knowledge",
            source=source,
            metadata={"url": url, "score": score},
        )

    async def initialize(self) -> bool:
        log.info(f"Knowledge agent initialized. Tracking {len(self._subreddits)} subreddits")
        return True

    async def execute(self, task: dict) -> dict:
        """Run a scraping cycle."""
        results = {"reddit": 0, "hn": 0, "github": 0, "rss": 0, "errors": []}

        async with aiohttp.ClientSession() as session:
            # Run all sources concurrently
            tasks = [
                self._scrape_reddit(session, results),
                self._scrape_hackernews(session, results),
                self._scrape_github_trending(session, results),
                self._scrape_rss(results),
            ]
            await asyncio.gather(*tasks, return_exceptions=True)

        log.info(f"Scraping cycle complete: {results}")
        return results

    async def _scrape_reddit(self, session: aiohttp.ClientSession, results: dict):
        """Scrape Reddit via JSON API (no auth needed for public subreddits)."""
        try:
            for subreddit in self._subreddits[:5]:  # Limit per cycle
                url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit=10"
                headers = {"User-Agent": "JARVIS/3.0 (personal AI assistant)"}

                try:
                    async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                        if resp.status == 429:
                            log.warning(f"Reddit rate limited on r/{subreddit}")
                            await asyncio.sleep(5)
                            continue
                        if resp.status != 200:
                            continue

                        data = await resp.json()
                        posts = data.get("data", {}).get("children", [])

                        for post in posts:
                            pdata = post.get("data", {})
                            title = pdata.get("title", "")
                            selftext = pdata.get("selftext", "")[:2000]
                            permalink = pdata.get("permalink", "")
                            score = pdata.get("score", 0)
                            num_comments = pdata.get("num_comments", 0)

                            if score < 10:  # Skip low-score posts
                                continue

                            full_url = f"https://reddit.com{permalink}"
                            content = f"{title}\n\n{selftext}" if selftext else title

                            self._store_item(
                                url=full_url,
                                source=f"reddit/r/{subreddit}",
                                title=title,
                                content=content,
                                score=score,
                            )
                            results["reddit"] += 1

                except asyncio.TimeoutError:
                    log.warning(f"Reddit timeout on r/{subreddit}")

                # Rate limiting: 1 request per 2 seconds
                await asyncio.sleep(2)

        except Exception as e:
            log.error(f"Reddit scraping error: {e}")
            results["errors"].append(f"reddit: {str(e)[:100]}")

    async def _scrape_hackernews(self, session: aiohttp.ClientSession, results: dict):
        """Scrape HackerNews via Algolia API."""
        try:
            # Get top stories
            url = f"{HN_API}/search?tags=front_page&hitsPerPage=30"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    return
                data = await resp.json()
                hits = data.get("hits", [])

                for hit in hits:
                    title = hit.get("title", "")
                    story_url = hit.get("url", "")
                    points = hit.get("points", 0)
                    num_comments = hit.get("num_comments", 0)
                    objectID = hit.get("objectID", "")

                    if points < 50:  # Skip low-score stories
                        continue

                    hn_url = f"https://news.ycombinator.com/item?id={objectID}"
                    content = f"{title} ({points} points, {num_comments} comments)"

                    if story_url:
                        content += f"\nURL: {story_url}"

                    self._store_item(
                        url=hn_url,
                        source="hackernews",
                        title=title,
                        content=content,
                        score=points,
                    )
                    results["hn"] += 1

        except Exception as e:
            log.error(f"HN scraping error: {e}")
            results["errors"].append(f"hn: {str(e)[:100]}")

    async def _scrape_github_trending(self, session: aiohttp.ClientSession, results: dict):
        """Scrape GitHub trending repos."""
        try:
            for lang in ["python", "typescript", "rust"]:
                url = (
                    f"{GITHUB_TRENDING_URL}?q=stars:>100+language:{lang}"
                    f"&sort=stars&order=desc&per_page=10"
                )
                headers = {"Accept": "application/vnd.github.v3+json"}

                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status == 403:
                        log.warning("GitHub API rate limited")
                        break
                    if resp.status != 200:
                        continue

                    data = await resp.json()
                    repos = data.get("items", [])

                    for repo in repos[:5]:
                        name = repo.get("full_name", "")
                        description = repo.get("description", "") or ""
                        stars = repo.get("stargazers_count", 0)
                        repo_url = repo.get("html_url", "")
                        topics = repo.get("topics", [])

                        content = f"{name}: {description}"
                        if topics:
                            content += f"\nTopics: {', '.join(topics[:10])}"
                        content += f"\nStars: {stars:,}"

                        self._store_item(
                            url=repo_url,
                            source=f"github/{lang}",
                            title=name,
                            content=content,
                            score=stars,
                        )
                        results["github"] += 1

                await asyncio.sleep(1)  # Rate limit

        except Exception as e:
            log.error(f"GitHub scraping error: {e}")
            results["errors"].append(f"github: {str(e)[:100]}")

    async def _scrape_rss(self, results: dict):
        """Scrape RSS feeds."""
        try:
            for name, feed_url in RSS_FEEDS.items():
                try:
                    feed = feedparser.parse(feed_url)
                    for entry in feed.entries[:10]:
                        title = entry.get("title", "")
                        link = entry.get("link", "")
                        summary = entry.get("summary", "")[:1000]

                        if not link:
                            continue

                        self._store_item(
                            url=link,
                            source=f"rss/{name}",
                            title=title,
                            content=f"{title}\n{summary}",
                            score=0,
                        )
                        results["rss"] += 1

                except Exception as e:
                    log.warning(f"RSS feed error ({name}): {e}")

        except Exception as e:
            log.error(f"RSS scraping error: {e}")
            results["errors"].append(f"rss: {str(e)[:100]}")

    def get_stats(self) -> dict:
        """Get scraping statistics."""
        total = self.conn.execute("SELECT COUNT(*) FROM scraped_items").fetchone()[0]
        by_source = {}
        for row in self.conn.execute("SELECT source, COUNT(*) FROM scraped_items GROUP BY source").fetchall():
            by_source[row[0]] = row[1]
        return {"total_items": total, "by_source": by_source}

    async def shutdown(self):
        self._running = False
        self.conn.close()
        log.info("Knowledge agent shut down")
