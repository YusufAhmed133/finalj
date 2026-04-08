"""Tests for JARVIS knowledge scraping agent — offline tests."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from jarvis.agents.knowledge import KnowledgeAgent
from jarvis.memory.spine import MemorySpine

PASSED = 0
FAILED = 0
TEST_DB = Path("/tmp/jarvis_test_knowledge.db")
TEST_SPINE_DB = Path("/tmp/jarvis_test_knowledge_spine.db")


def report(name: str, passed: bool, detail: str = ""):
    global PASSED, FAILED
    if passed:
        PASSED += 1
        print(f"  PASS: {name}")
    else:
        FAILED += 1
        print(f"  FAIL: {name} — {detail}")


def cleanup():
    for p in [TEST_DB, TEST_SPINE_DB]:
        if p.exists():
            p.unlink()
        for suffix in ["-wal", "-shm"]:
            wal = Path(str(p) + suffix)
            if wal.exists():
                wal.unlink()


def test_imports():
    print("\n=== Import Tests ===")
    try:
        from jarvis.agents.knowledge import KnowledgeAgent
        report("Import KnowledgeAgent", True)
    except Exception as e:
        report("Import KnowledgeAgent", False, str(e))


def test_init():
    print("\n=== Initialization Tests ===")
    cleanup()
    spine = MemorySpine(db_path=TEST_SPINE_DB)
    agent = KnowledgeAgent.__new__(KnowledgeAgent)
    agent.spine = spine
    agent.db_path = TEST_DB
    agent.db_path.parent.mkdir(parents=True, exist_ok=True)
    import sqlite3
    agent.conn = sqlite3.connect(str(TEST_DB))
    agent._init_schema()
    agent._subreddits = ["LocalLLaMA", "ClaudeAI"]
    agent._running = False

    report("Agent created", agent is not None)
    report("Subreddits loaded", len(agent._subreddits) == 2)
    report("Schema created", True)

    spine.close()
    agent.conn.close()


def test_deduplication():
    print("\n=== Deduplication Tests ===")
    cleanup()
    spine = MemorySpine(db_path=TEST_SPINE_DB)
    agent = KnowledgeAgent.__new__(KnowledgeAgent)
    agent.spine = spine
    agent.db_path = TEST_DB
    import sqlite3
    agent.conn = sqlite3.connect(str(TEST_DB))
    agent._init_schema()

    url = "https://reddit.com/r/ClaudeAI/test_post"

    # First check — not duplicate
    report("New URL not duplicate", not agent._is_duplicate(url))

    # Store item
    agent._store_item(url, "reddit", "Test Post", "Test content", 100)
    report("Item stored", True)

    # Now it should be duplicate
    report("Stored URL is duplicate", agent._is_duplicate(url))

    # Different URL not duplicate
    report("Different URL not duplicate", not agent._is_duplicate("https://reddit.com/other"))

    # URL hash is consistent
    h1 = agent._url_hash(url)
    h2 = agent._url_hash(url)
    report("Hash is deterministic", h1 == h2)
    report("Hash is 16 chars", len(h1) == 16)

    spine.close()
    agent.conn.close()


def test_stats():
    print("\n=== Stats Tests ===")
    cleanup()
    spine = MemorySpine(db_path=TEST_SPINE_DB)
    agent = KnowledgeAgent.__new__(KnowledgeAgent)
    agent.spine = spine
    agent.db_path = TEST_DB
    import sqlite3
    agent.conn = sqlite3.connect(str(TEST_DB))
    agent._init_schema()

    # Store some items
    agent._store_item("https://reddit.com/1", "reddit/r/ClaudeAI", "Post 1", "Content 1", 50)
    agent._store_item("https://reddit.com/2", "reddit/r/LocalLLaMA", "Post 2", "Content 2", 100)
    agent._store_item("https://hn.com/1", "hackernews", "HN Story", "HN Content", 200)

    stats = agent.get_stats()
    report("Total items = 3", stats["total_items"] == 3)
    report("By source correct", len(stats["by_source"]) == 3)

    # Memory spine should also have entries
    mem_count = spine.count()
    report("Memory spine has entries", mem_count == 3, f"expected 3, got {mem_count}")

    # Verify searchable in memory
    results = spine.search_text("ClaudeAI")
    report("Knowledge searchable in memory", len(results) >= 1)

    spine.close()
    agent.conn.close()


def test_subreddit_loading():
    print("\n=== Subreddit Loading Tests ===")

    # Test with actual identity file
    agent = KnowledgeAgent.__new__(KnowledgeAgent)
    subs = agent._load_subreddits()
    report("Subreddits loaded from yaml", len(subs) > 0)
    report("LocalLLaMA in list", "LocalLLaMA" in subs)
    report("ClaudeAI in list", "ClaudeAI" in subs)
    report("ausfinance in list", "ausfinance" in subs)
    report("No r/ prefix", all(not s.startswith("r/") for s in subs))


if __name__ == "__main__":
    print("=" * 60)
    print("JARVIS Knowledge Agent Tests (offline)")
    print("=" * 60)

    test_imports()
    test_init()
    test_deduplication()
    test_stats()
    test_subreddit_loading()

    print("\n" + "=" * 60)
    print(f"Results: {PASSED} passed, {FAILED} failed, {PASSED + FAILED} total")
    print("=" * 60)

    cleanup()
    sys.exit(0 if FAILED == 0 else 1)
