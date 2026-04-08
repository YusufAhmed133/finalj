"""Tests for JARVIS memory spine, vector store, entity graph, and compactor."""
import asyncio
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from jarvis.memory.spine import MemorySpine, TIER_HOT, TIER_WARM, TIER_COLD, TIER_ARCHIVE
from jarvis.memory.graph import EntityGraph
from jarvis.memory.compactor import MemoryCompactor

# Use temp paths for testing
TEST_DB = Path("/tmp/jarvis_test_context.db")
TEST_GRAPH = Path("/tmp/jarvis_test_graph.json")
TEST_VECTORS_DB = Path("/tmp/jarvis_test_vectors.db")

PASSED = 0
FAILED = 0


def report(name: str, passed: bool, detail: str = ""):
    global PASSED, FAILED
    if passed:
        PASSED += 1
        print(f"  PASS: {name}")
    else:
        FAILED += 1
        print(f"  FAIL: {name} — {detail}")


def cleanup():
    for p in [TEST_DB, TEST_GRAPH, TEST_VECTORS_DB]:
        if p.exists():
            p.unlink()
        # WAL and SHM files
        for suffix in ["-wal", "-shm"]:
            wal = Path(str(p) + suffix)
            if wal.exists():
                wal.unlink()


def test_spine():
    print("\n=== Memory Spine Tests ===")
    cleanup()
    spine = MemorySpine(db_path=TEST_DB)

    # Test 1: Store a memory
    mid = spine.store(
        content="Yusuf asked about IVV performance this quarter",
        type="interaction",
        source="telegram",
        entities=["Yusuf", "IVV"],
        metadata={"sentiment": "neutral"},
    )
    report("Store memory", mid == 1)

    # Test 2: Store multiple memories
    mid2 = spine.store(content="Morning briefing: AAPL up 2%, IVV flat", type="briefing", source="system")
    mid3 = spine.store(content="Yusuf scheduled a meeting with Prof. Smith for Thursday", type="interaction", entities=["Yusuf", "Prof. Smith"])
    mid4 = spine.store(content="Cardiac device check reminder sent", type="alert", source="system", entities=["Yusuf"])
    report("Store multiple memories", mid4 == 4)

    # Test 3: Count
    count = spine.count()
    report("Count all memories", count == 4, f"expected 4, got {count}")

    # Test 4: Count by tier
    hot_count = spine.count(TIER_HOT)
    report("All memories start as hot", hot_count == 4, f"expected 4 hot, got {hot_count}")

    # Test 5: Full-text search
    results = spine.search_text("IVV")
    report("FTS search 'IVV'", len(results) == 2, f"expected 2, got {len(results)}")

    # Test 6: FTS search with ranking
    results = spine.search_text("Yusuf meeting Thursday")
    report("FTS search multi-term", len(results) >= 1, f"expected >=1, got {len(results)}")

    # Test 7: Get recent
    recent = spine.get_recent(hours=1)
    report("Get recent (1h)", len(recent) == 4, f"expected 4, got {len(recent)}")

    # Test 8: Get recent by type
    alerts = spine.get_recent(hours=1, type="alert")
    report("Get recent by type", len(alerts) == 1, f"expected 1 alert, got {len(alerts)}")

    # Test 9: Get by ID
    mem = spine.get_by_id(1)
    report("Get by ID", mem is not None and "IVV" in mem["content"])

    # Test 10: Update tier
    spine.update_tier(1, TIER_WARM, summary="Yusuf asked about IVV quarterly performance")
    mem = spine.get_by_id(1)
    report("Update tier to warm", mem["tier"] == TIER_WARM and mem["summary"] is not None)

    # Test 11: Stats
    stats = spine.stats()
    report("Stats", stats["total"] == 4 and stats["by_tier"]["warm"] == 1)

    # Test 12: Action log
    action_id = spine.log_action(
        action_type="open_app",
        description="Opened Google Calendar",
        outcome="success",
    )
    report("Log action", action_id == 1)

    # Test 13: FTS search after tier update still works
    results = spine.search_text("IVV performance")
    report("FTS after tier update", len(results) >= 1)

    # Test 14: Search with tier filter
    hot_results = spine.search_text("Yusuf", tier=TIER_HOT)
    report("FTS with tier filter", all(r["tier"] == TIER_HOT for r in hot_results))

    spine.close()


def test_graph():
    print("\n=== Entity Graph Tests ===")
    cleanup()
    graph = EntityGraph(path=TEST_GRAPH)

    # Test 1: Add entity
    graph.add_entity("Yusuf Ahmed", "person", {"role": "owner", "age": 18})
    report("Add entity", "yusuf ahmed" in graph.entities)

    # Test 2: Add more entities
    graph.add_entity("IVV", "etf", {"market": "US"})
    graph.add_entity("UNSW", "university", {"location": "Sydney"})
    graph.add_entity("Prof. Smith", "person", {"department": "Law"})
    report("Multiple entities", len(graph.entities) == 4)

    # Test 3: Add relation
    graph.add_relation("Yusuf Ahmed", "UNSW", "attends")
    graph.add_relation("Yusuf Ahmed", "IVV", "invests_in")
    graph.add_relation("Prof. Smith", "UNSW", "works_at")
    report("Add relations", len(graph.relations) == 3)

    # Test 4: Get entity
    entity = graph.get_entity("Yusuf Ahmed")
    report("Get entity", entity is not None and entity["type"] == "person")

    # Test 5: Get relations
    rels = graph.get_relations("Yusuf Ahmed")
    report("Get relations", len(rels) == 2)

    # Test 6: Connected entities
    connected = graph.get_connected_entities("Yusuf Ahmed", max_depth=2)
    report("Connected entities (depth 2)", "unsw" in connected and "prof. smith" in connected,
           f"got {connected}")

    # Test 7: Mention count increments
    graph.add_entity("Yusuf Ahmed")
    entity = graph.get_entity("Yusuf Ahmed")
    report("Mention count", entity["mention_count"] == 2)

    # Test 8: Search entities
    results = graph.search_entities("yusuf")
    report("Search entities", len(results) == 1 and results[0]["name"] == "Yusuf Ahmed")

    # Test 9: Most mentioned
    for _ in range(5):
        graph.add_entity("IVV")
    top = graph.most_mentioned(limit=1)
    report("Most mentioned", top[0]["name"] == "IVV")

    # Test 10: Relation weight increments
    graph.add_relation("Yusuf Ahmed", "IVV", "invests_in")
    rels = graph.get_relations("IVV")
    invest_rel = [r for r in rels if r["type"] == "invests_in"][0]
    report("Relation weight increments", invest_rel["weight"] == 2.0)

    # Test 11: Persistence
    graph2 = EntityGraph(path=TEST_GRAPH)
    report("Persistence", len(graph2.entities) == 4 and len(graph2.relations) == 3)

    # Test 12: Stats
    stats = graph.stats()
    report("Stats", stats["total_entities"] == 4 and stats["total_relations"] == 3)


def test_compactor():
    print("\n=== Compactor Tests ===")
    cleanup()
    spine = MemorySpine(db_path=TEST_DB)

    # Store memories with artificially old timestamps
    now = time.time()
    eight_days_ago = now - (8 * 86400)
    thirty_five_days_ago = now - (35 * 86400)
    ninety_five_days_ago = now - (95 * 86400)

    # Insert directly with old timestamps
    spine.conn.execute(
        """INSERT INTO memories (timestamp, type, tier, source, content, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        ("2026-03-31", "interaction", TIER_HOT, "telegram", "Old hot memory about studying contracts law for exam", eight_days_ago, eight_days_ago),
    )
    spine.conn.execute(
        """INSERT INTO memories (timestamp, type, tier, source, content, summary, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        ("2026-03-04", "interaction", TIER_WARM, "telegram", "Original content about IVV purchase",
         "Yusuf bought more IVV shares. DCA strategy on track.", thirty_five_days_ago, thirty_five_days_ago),
    )
    spine.conn.execute(
        """INSERT INTO memories (timestamp, type, tier, source, content, summary, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        ("2026-01-03", "interaction", TIER_COLD, "telegram", "Original content about new year goals",
         "Set goals for 2026: WAM 85, $50K invested, secure internship.", ninety_five_days_ago, ninety_five_days_ago),
    )
    # Also need FTS entries for the manually inserted rows
    spine.conn.execute(
        "INSERT INTO memories_fts(rowid, content, summary, entities) VALUES (1, ?, NULL, NULL)",
        ("Old hot memory about studying contracts law for exam",))
    spine.conn.execute(
        "INSERT INTO memories_fts(rowid, content, summary, entities) VALUES (2, ?, ?, NULL)",
        ("Original content about IVV purchase", "Yusuf bought more IVV shares. DCA strategy on track."))
    spine.conn.execute(
        "INSERT INTO memories_fts(rowid, content, summary, entities) VALUES (3, ?, ?, NULL)",
        ("Original content about new year goals", "Set goals for 2026: WAM 85, $50K invested, secure internship."))
    spine.conn.commit()

    # Test compaction without AI summariser (uses extractive fallback)
    compactor = MemoryCompactor(spine)

    # Test 1: Hot → Warm
    loop = asyncio.new_event_loop()
    count = loop.run_until_complete(compactor.compact_tier(TIER_HOT))
    report("Hot → Warm compaction", count == 1, f"expected 1, got {count}")

    mem = spine.get_by_id(1)
    report("Tier updated to warm", mem["tier"] == TIER_WARM)
    report("Summary generated", mem["summary"] is not None and len(mem["summary"]) > 0)

    # Test 2: Warm → Cold
    count = loop.run_until_complete(compactor.compact_tier(TIER_WARM))
    report("Warm → Cold compaction", count == 1, f"expected 1, got {count}")

    mem = spine.get_by_id(2)
    report("Tier updated to cold", mem["tier"] == TIER_COLD)

    # Test 3: Cold → Archive
    count = loop.run_until_complete(compactor.compact_tier(TIER_COLD))
    report("Cold → Archive compaction", count == 1, f"expected 1, got {count}")

    mem = spine.get_by_id(3)
    report("Tier updated to archive", mem["tier"] == TIER_ARCHIVE)

    # Test 4: Full compaction
    # Add more old memories
    spine.conn.execute(
        """INSERT INTO memories (timestamp, type, tier, source, content, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        ("2026-03-30", "interaction", TIER_HOT, "telegram", "Another old hot memory", eight_days_ago, eight_days_ago),
    )
    spine.conn.execute(
        "INSERT INTO memories_fts(rowid, content, summary, entities) VALUES (4, ?, NULL, NULL)",
        ("Another old hot memory",))
    spine.conn.commit()

    results = loop.run_until_complete(compactor.run_full_compaction())
    report("Full compaction runs", "hot_to_warm" in results)

    # Test 5: Stats after compaction
    stats = spine.stats()
    report("Post-compaction stats", stats["by_tier"]["archive"] == 1)

    loop.close()
    spine.close()


def test_vectors_basic():
    """Test vector store without Ollama (just schema and serialization)."""
    print("\n=== Vector Store Basic Tests ===")
    cleanup()

    try:
        from jarvis.memory.vectors import VectorStore, _serialize_f32
    except Exception as e:
        report("Import vector store", False, str(e))
        return

    # Test serialization
    vec = [0.1, 0.2, 0.3, 0.4, 0.5]
    serialized = _serialize_f32(vec)
    report("Serialize float vector", len(serialized) == 20)  # 5 floats * 4 bytes

    # Test store initialization
    vs = VectorStore(db_path=TEST_VECTORS_DB)
    if not vs.available:
        report("Vector store init (disabled — system Python lacks extension support)", True)
        print("  NOTE: Vector search disabled. Install Python with extension support to enable.")
        print("        Run: brew install python3  OR  pyenv install 3.12")
        vs.close()
        return
    report("Vector store init", vs.count() == 0)

    # Test store and search with dummy vectors
    dummy_vec = [0.0] * 768
    dummy_vec[0] = 1.0
    vs.store(1, dummy_vec)
    report("Store vector", vs.count() == 1)

    # Store another vector
    dummy_vec2 = [0.0] * 768
    dummy_vec2[1] = 1.0
    vs.store(2, dummy_vec2)
    report("Store second vector", vs.count() == 2)

    # Search with query similar to first
    query = [0.0] * 768
    query[0] = 0.9
    query[1] = 0.1
    results = vs.search(query, limit=2)
    report("Vector search returns results", len(results) == 2)
    report("Nearest neighbor correct", results[0]["memory_id"] == 1,
           f"expected memory_id=1, got {results[0]['memory_id']}")

    # Delete
    vs.delete(1)
    report("Delete vector", vs.count() == 1)

    vs.close()


if __name__ == "__main__":
    print("=" * 60)
    print("JARVIS Memory System Tests")
    print("=" * 60)

    test_spine()
    test_graph()
    test_compactor()
    test_vectors_basic()

    print("\n" + "=" * 60)
    print(f"Results: {PASSED} passed, {FAILED} failed, {PASSED + FAILED} total")
    print("=" * 60)

    cleanup()
    sys.exit(0 if FAILED == 0 else 1)
