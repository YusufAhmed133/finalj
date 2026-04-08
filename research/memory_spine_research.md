# Memory Spine Research & Architecture Debate

## Use Case
JARVIS personal AI operating system needs a persistent memory system ("memory spine") with four temperature tiers:
- **Hot** (0-7 days): Full text, fully searchable, instant recall
- **Warm** (7-30 days): Summarised, key entities extracted, semantic search
- **Cold** (30-90 days): Single paragraph summary per memory
- **Archive** (90+ days): One sentence, permanently kept

Must run entirely local on macOS Apple Silicon. No cloud dependencies.

---

## Systems Researched

### 1. mem0 (mem0ai/mem0)

**What it is**: The most widely adopted standalone memory layer for AI agents (~48K GitHub stars). Provides a universal memory API for AI apps with `add()`, `search()`, `get()`, `update()`, `delete()` methods.

**Architecture**: Triple-storage backend:
- **Vector store**: 24+ providers (Qdrant, Pinecone, Chroma, PGVector) for embedding persistence and similarity search
- **Graph store** (optional): Neo4j, Memgraph, Kuzu, Neptune for entity relationships
- **History database**: SQLiteManager tracks all modifications with timestamps

**How add() works**: Validates session IDs (requires user_id/agent_id/run_id) -> parses messages -> extracts facts via LLM -> generates embeddings -> searches for existing similar memories -> LLM determines ADD/UPDATE/DELETE actions -> executes vector + graph operations in parallel -> logs to history DB.

**How search() works**: Validates filters -> embeds query -> vector similarity search -> optional reranking -> retrieves related graph entities if enabled.

**Memory deduplication**: Uses LLM to determine if new facts semantically overlap with existing memories. The LLM decides whether to ADD new, UPDATE existing, or DELETE obsolete memories. This is intelligent but expensive (requires LLM call per add).

**Factory pattern**: Each component type (LLMs, vector stores, embedders, graph stores, rerankers) uses `create()`, `register_provider()`, `get_supported_providers()`. Lazy-loading via importlib means only needed providers are imported.

**Current version**: v1.0.0 (pip install mem0ai). Python >=3.9, <4.0.

**Relevance to JARVIS**: mem0's architecture is over-engineered for our use case. It's designed for multi-tenant SaaS (user_id/agent_id/run_id), requires LLM calls for every add operation (expensive for local-first), and its graph memory requires Neo4j/Memgraph (heavy external services). However, the triple-storage concept (vector + graph + history) is the right pattern. We should replicate this architecture with lighter components: sqlite-vec instead of Qdrant, SQLite relations table instead of Neo4j, SQLite FTS5 instead of a separate history DB.

---

### 2. MemGPT / Letta

**What it is**: Agent architecture inspired by OS virtual memory. The LLM manages its own memory through tool calls. Now part of Letta (the company/framework).

**Memory tiers** (three-level model):
- **Core Memory** (always in-context, like RAM): Fixed-size, writeable via tool calls. Stores key facts about user and agent persona. Always included in every prompt. Two default blocks: `human` (user info) and `persona` (agent character).
- **Recall Memory** (conversation history, like page file): Full conversation logs stored in external DB. Searchable via `conversation_search` tool. No data is ever lost.
- **Archival Memory** (long-term, like disk): Vector DB (LanceDB default) for semantic search. Agent writes here via `archival_memory_insert`, reads via `archival_memory_search`.

**Self-directed memory editing tools**:
- `core_memory_append`: Add new info to core memory blocks
- `core_memory_replace`: Update existing core memories
- `archival_memory_insert`: Write facts to archival storage
- `archival_memory_search`: Semantic search over archival memory
- `conversation_search`: Case-insensitive search of conversation history
- `send_message`: Send visible responses to user

**Context window management**: Uses FIFO queue for conversation history. When context approaches capacity, older messages are evicted. The first index in the queue is a system message containing a **recursive summary** of previously evicted messages. The LLM generates this summary, and when the summary itself gets evicted, the new summary incorporates the old one (recursive compaction).

**Compaction mechanism**: When context fills -> LLM summarises oldest messages -> summary replaces them at queue head -> evicted messages preserved in recall memory. The summary is recursive: each new summary incorporates the previous summary. This means information is never truly lost, just increasingly compressed.

**Agent initialization example**:
```python
agent_state = client.agents.create(
    model="openai/gpt-4o-mini-2024-07-18",
    embedding="openai/text-embedding-3-small",
    memory_blocks=[
        CreateBlock(label="human", value="My name is Sarah."),
        CreateBlock(label="persona", value="You are a helpful assistant.")
    ]
)
```

**Token budget tracking**: System tracks tokens across categories: system prompt (1,076), core memory (86), external memory summary (107), messages (179). This enables transparent context budgeting.

**Relevance to JARVIS**: The recursive summary mechanism is exactly what we need for the warm->cold->archive compaction pipeline. The self-directed memory editing pattern (agent writes its own memory) is powerful but overkill for JARVIS's initial implementation — we should start with automated tier transitions on time-based schedules, then add agent-directed editing later. The core memory concept (always-in-context working memory) maps directly to our "hot" tier.

---

### 3. SQLite FTS5 (Full-Text Search)

**What it is**: SQLite's built-in full-text search extension. Ships with Python's sqlite3 module. Zero additional dependencies.

**Table creation**:
```sql
CREATE VIRTUAL TABLE memories_fts USING fts5(
    title,
    content,
    entities,
    tokenize='porter unicode61',
    content='memories',
    content_rowid='id'
);
```
Using `content='memories'` makes this an **external content table** — the FTS index points back to a regular table, avoiding data duplication.

**Query syntax**:
```sql
-- Basic search
SELECT * FROM memories_fts WHERE memories_fts MATCH 'machine learning';

-- Phrase search
SELECT * FROM memories_fts WHERE memories_fts MATCH '"neural network"';

-- Boolean operators
SELECT * FROM memories_fts WHERE memories_fts MATCH 'python AND (async OR threading)';

-- Prefix search
SELECT * FROM memories_fts WHERE memories_fts MATCH 'mach*';

-- Column-specific search
SELECT * FROM memories_fts WHERE memories_fts MATCH 'entities : "John Smith"';

-- NEAR proximity
SELECT * FROM memories_fts WHERE memories_fts MATCH 'NEAR(memory search, 5)';
```

**BM25 ranking** (lower = more relevant, scores are negative):
```sql
-- Basic ranking
SELECT rowid, rank FROM memories_fts WHERE memories_fts MATCH 'search query' ORDER BY rank;

-- Column-weighted ranking (title 10x, content 1x, entities 5x)
SELECT rowid, bm25(memories_fts, 10.0, 1.0, 5.0) as score
FROM memories_fts
WHERE memories_fts MATCH 'search query'
ORDER BY score;
```

**BM25 formula**: `Score = -1 + SUM(IDF(qi) * f(qi,D) * (k1+1) / (f(qi,D) + k1*(1-b+b*|D|/avgdl)))` where k1=1.2, b=0.75 (hardcoded).

**Highlight and snippet functions**:
```sql
-- Highlight matches
SELECT highlight(memories_fts, 1, '<b>', '</b>') FROM memories_fts WHERE memories_fts MATCH 'query';

-- Extract snippet with context
SELECT snippet(memories_fts, 1, '<b>', '</b>', '...', 20) FROM memories_fts WHERE memories_fts MATCH 'query';
```

**Tokenizers**:
- `unicode61` (default): Best for general multilingual text. Supports `remove_diacritics`, custom `tokenchars`/`separators`
- `porter`: Wraps another tokenizer (default unicode61) with Porter stemming. "running" matches "run"
- `ascii`: ASCII-only, fastest, limited charset
- Best combo for JARVIS: `tokenize='porter unicode61'` — gives stemming + Unicode support

**Sync with external content table** (required triggers):
```sql
CREATE TRIGGER memories_ai AFTER INSERT ON memories BEGIN
  INSERT INTO memories_fts(rowid, title, content, entities)
  VALUES (new.id, new.title, new.content, new.entities);
END;

CREATE TRIGGER memories_ad AFTER DELETE ON memories BEGIN
  INSERT INTO memories_fts(memories_fts, rowid, title, content, entities)
  VALUES('delete', old.id, old.title, old.content, old.entities);
END;

CREATE TRIGGER memories_au AFTER UPDATE ON memories BEGIN
  INSERT INTO memories_fts(memories_fts, rowid, title, content, entities)
  VALUES('delete', old.id, old.title, old.content, old.entities);
  INSERT INTO memories_fts(rowid, title, content, entities)
  VALUES (new.id, new.title, new.content, new.entities);
END;
```

**Relevance to JARVIS**: FTS5 is the primary search mechanism for the hot tier. It's built into Python, zero dependencies, instant keyword search with relevance ranking. For the hot tier (0-7 days, full text), FTS5 MATCH queries with BM25 ranking are faster and more predictable than vector search for exact keyword lookups. Vector search complements FTS5 for semantic/fuzzy queries.

---

### 4. sqlite-vec

**What it is**: SQLite extension for vector similarity search. Written in pure C, no dependencies, runs everywhere SQLite runs. Successor to sqlite-vss. Current version: v0.1.9 (March 2026). Pre-v1, expect breaking changes.

**Installation**: `pip install sqlite-vec`

**Distance functions**:
- **L2 (Euclidean)**: Default. `vec_distance_L2(a, b)`
- **Cosine**: `vec_distance_cosine(a, b)`. Specify `distance_metric=cosine` on table.
- **L1 (Manhattan)**: `vec_distance_L1(a, b)`

**Vector types**: `float[N]` (float32), `int8[N]` (quantized), `bit[N]` (binary/hamming)

**Table creation and KNN query**:
```sql
-- Create vector table
CREATE VIRTUAL TABLE vec_memories USING vec0(
    memory_id INTEGER PRIMARY KEY,
    embedding float[384],
    +tier TEXT,
    +created_at TEXT
);

-- Insert vector
INSERT INTO vec_memories(memory_id, embedding, tier, created_at)
VALUES (1, :embedding_blob, 'hot', '2026-04-08');

-- KNN search (find 10 nearest neighbors)
SELECT memory_id, distance
FROM vec_memories
WHERE embedding MATCH :query_vector
  AND k = 10;

-- KNN with cosine distance
CREATE VIRTUAL TABLE vec_memories USING vec0(
    memory_id INTEGER PRIMARY KEY,
    embedding float[384],
    distance_metric=cosine
);
```

**Python integration pattern**:
```python
import sqlite3
import sqlite_vec
import struct

def serialize_float32(vector: list[float]) -> bytes:
    """Convert list of floats to binary blob for sqlite-vec."""
    return struct.pack(f"{len(vector)}f", *vector)

db = sqlite3.connect("jarvis_memory.db")
db.enable_load_extension(True)
sqlite_vec.load(db)
db.enable_load_extension(False)

# Create table
db.execute("""
    CREATE VIRTUAL TABLE IF NOT EXISTS vec_memories USING vec0(
        memory_id INTEGER PRIMARY KEY,
        embedding float[384],
        distance_metric=cosine
    )
""")

# Insert
embedding = serialize_float32(embedding_list)
db.execute(
    "INSERT INTO vec_memories(memory_id, embedding) VALUES (?, ?)",
    (memory_id, embedding)
)

# Query
query_blob = serialize_float32(query_embedding)
results = db.execute(
    "SELECT memory_id, distance FROM vec_memories WHERE embedding MATCH ? AND k = ?",
    (query_blob, 10)
).fetchall()
```

**Metadata columns**: Prefixed with `+` in table definition (e.g., `+tier TEXT`). These are stored alongside vectors and can be used for filtering, though filtering is applied post-KNN in current versions.

**Relevance to JARVIS**: sqlite-vec is the right choice for our vector store. It lives inside the same SQLite database as everything else — no external services, no network calls, single file backup. The 384-dimensional float32 vectors from all-MiniLM-L6-v2 are natively supported. Performance is "fast enough" for our scale (personal memory, not millions of documents).

---

### 5. ChromaDB vs sqlite-vec Debate

**ChromaDB overview**: Open-source embedding database. Runs in-process (embedded) or client-server. Uses SQLite underneath for metadata, with its own vector index. Got a Rust rewrite in 2025 delivering 4x faster writes/queries.

**Comparison table**:

| Aspect | sqlite-vec | ChromaDB |
|--------|-----------|----------|
| Architecture | SQLite extension (single DB file) | Separate process/embedded (multiple files) |
| Dependencies | Zero (pure C) | Heavy (many Python deps) |
| Storage | Inside existing SQLite DB | Its own directory structure |
| Distance functions | L2, cosine, L1, hamming | L2, cosine, IP |
| Max vectors | Limited by SQLite (practical: ~1M) | Designed for millions |
| Backup | Copy one .db file | Copy entire directory |
| Concurrency | SQLite locking (limited writes) | Better concurrent access |
| Python API | Raw SQL via sqlite3 | High-level Pythonic API |
| Metadata filtering | Post-KNN (limited) | Pre-filter + post-filter |
| Size on disk | Minimal overhead | Larger footprint |
| Maturity | Pre-v1 (v0.1.9) | v0.6+ stable |

**Verdict for JARVIS**: **sqlite-vec wins**. Reasons:
1. **Single database file**: JARVIS memory is one file. FTS5 index, vector index, relations table, metadata — all in `jarvis_memory.db`. Backup = copy one file. Migration = copy one file.
2. **Zero dependencies**: No separate service to start, no port conflicts, no process management.
3. **Scale is right**: JARVIS is a personal assistant. Even with years of daily use, we're talking tens of thousands of memories, not millions. sqlite-vec handles this easily.
4. **Unified queries**: Can JOIN vector results with FTS5 results and metadata tables in a single SQL query. ChromaDB would require fetching IDs then querying SQLite separately.
5. **ChromaDB is overkill**: Its advantages (concurrent writes, pre-filtering, scale) don't matter for a single-user local system.

**When ChromaDB would win**: Multi-user system, >1M vectors, need pre-filter on metadata before KNN, need client-server architecture. None of these apply to JARVIS.

---

### 6. Embedding Generation: sentence-transformers vs Ollama

#### sentence-transformers (all-MiniLM-L6-v2)

**Specs**:
- Dimensions: 384
- Max sequence length: 256 word pieces (trained on 128 tokens)
- Model size: 22.7M parameters, ~80MB on disk
- Speed: ~14K sentences/sec on CPU
- Similarity metric: Cosine
- Training data: 1.17B sentence pairs from 21+ datasets

**Code**:
```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("all-MiniLM-L6-v2")
embeddings = model.encode(["Remember to buy groceries", "Meeting with John at 3pm"])
# embeddings.shape = (2, 384)
```

**Pros**: Fastest option, runs entirely in-process (no HTTP calls), tiny model, well-tested, huge community (195M+ monthly downloads).
**Cons**: Adds PyTorch as dependency (~2GB), loads model into memory (~300MB with PyTorch runtime).

#### Ollama nomic-embed-text

**Specs**:
- Dimensions: 768 (supports Matryoshka: 64, 128, 256, 512, 768)
- Context length: 2,048 tokens (8x longer than MiniLM)
- Model size: 274MB
- Performance: Surpasses OpenAI text-embedding-ada-002 and text-embedding-3-small
- Requires: Ollama running locally (likely already running for JARVIS LLM)

**Code**:
```python
import httpx

def get_embedding(text: str, model: str = "nomic-embed-text") -> list[float]:
    response = httpx.post(
        "http://localhost:11434/api/embeddings",
        json={"model": model, "prompt": text}
    )
    return response.json()["embedding"]  # 768 floats

# Or via ollama Python package:
import ollama
result = ollama.embed(model="nomic-embed-text", input="Remember to buy groceries")
# result["embeddings"][0] -> list of 768 floats
```

**Pros**: Better quality embeddings, longer context window (2K vs 256 tokens), Ollama is likely already running for JARVIS, Matryoshka allows dimension reduction.
**Cons**: Requires HTTP call to Ollama (latency ~10-50ms per call), Ollama must be running.

#### Verdict for JARVIS: **Ollama nomic-embed-text wins**, with sentence-transformers as fallback.

Reasons:
1. **Ollama is already running**: JARVIS uses Ollama for LLM inference. The embedding server is free.
2. **Better quality**: nomic-embed-text outperforms MiniLM on benchmarks, especially for longer text.
3. **Longer context**: 2,048 tokens vs 256. Memory entries can be paragraphs, not just sentences.
4. **Dimension flexibility**: Use 768 for hot/warm (best quality), 384 for cold/archive (save space), via Matryoshka.
5. **No PyTorch dependency**: Avoids the 2GB PyTorch install.

**Fallback strategy**: If Ollama is unavailable (crashed, not started), fall back to sentence-transformers with a cached model. This gives resilience without Ollama as a hard dependency.

**Dimension choice**: Use **384 dimensions** with nomic-embed-text (Matryoshka truncation) for best balance of quality and storage. This matches MiniLM-L6-v2 dimensions, making the fallback strategy seamless. If quality testing shows 384 is insufficient, bump to 512.

```python
import numpy as np

def get_embedding(text: str, dimensions: int = 384) -> list[float]:
    """Get embedding from Ollama, truncated to target dimensions via Matryoshka."""
    try:
        response = httpx.post(
            "http://localhost:11434/api/embeddings",
            json={"model": "nomic-embed-text", "prompt": text},
            timeout=10.0
        )
        full_embedding = response.json()["embedding"]  # 768d
        truncated = full_embedding[:dimensions]  # Matryoshka truncation
        # L2 normalize after truncation
        norm = np.linalg.norm(truncated)
        return (np.array(truncated) / norm).tolist()
    except Exception:
        # Fallback to sentence-transformers
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer("all-MiniLM-L6-v2")
        return model.encode(text).tolist()  # Already 384d
```

---

### 7. FTS5 vs Vector Search: When to Use Which

| Query Type | Use FTS5 | Use Vector Search |
|-----------|----------|------------------|
| Exact keyword: "John Smith" | YES | No |
| Entity lookup: "meeting with Sarah" | YES (entity column) | Backup |
| Fuzzy/semantic: "that conversation about food" | No | YES |
| Temporal: "what happened yesterday" | YES (date filter + FTS) | No |
| Related concepts: "similar to my cooking notes" | No | YES |
| Boolean: "python AND NOT javascript" | YES | No |
| Typo-tolerant: "reciepe" (meant recipe) | No | YES (embeddings handle typos) |
| Prefix: "mach*" (machine, machining...) | YES | No |

**Hybrid search strategy for JARVIS**:
```python
def search_memories(query: str, limit: int = 10) -> list[Memory]:
    """Hybrid search: FTS5 for keywords, vector for semantics, merge results."""
    # 1. FTS5 keyword search
    fts_results = db.execute("""
        SELECT m.id, m.content, bm25(memories_fts, 10.0, 1.0, 5.0) as fts_score
        FROM memories_fts
        JOIN memories m ON m.id = memories_fts.rowid
        WHERE memories_fts MATCH ?
        ORDER BY fts_score
        LIMIT ?
    """, (query, limit)).fetchall()

    # 2. Vector semantic search
    query_embedding = get_embedding(query)
    vec_results = db.execute("""
        SELECT memory_id, distance
        FROM vec_memories
        WHERE embedding MATCH ? AND k = ?
    """, (serialize_float32(query_embedding), limit)).fetchall()

    # 3. Reciprocal Rank Fusion (RRF) to merge
    scores = {}
    k = 60  # RRF constant
    for rank, (id, content, _) in enumerate(fts_results):
        scores[id] = scores.get(id, 0) + 1 / (k + rank + 1)
    for rank, (id, _) in enumerate(vec_results):
        scores[id] = scores.get(id, 0) + 1 / (k + rank + 1)

    # Return merged, sorted by combined score
    top_ids = sorted(scores, key=scores.get, reverse=True)[:limit]
    return [get_memory(id) for id in top_ids]
```

---

### 8. Entity Graph: networkx vs Custom JSON vs SQLite Relations Table

#### Option A: networkx
- **What it is**: Python graph library, in-memory, full graph algorithms (shortest path, centrality, clustering)
- **Pros**: Rich API, graph algorithms for "find most connected entities", visualization, serialization to/from JSON
- **Cons**: In-memory only (must serialize to disk), separate from SQLite, adds ~10MB dependency, not queryable via SQL
- **Pattern**: Load graph on startup, query in memory, persist to JSON file on changes

#### Option B: Custom JSON
- **Pros**: Zero dependencies, human-readable, easy to inspect/debug
- **Cons**: No query capability (must load entire graph to search), O(n) for any lookup, no integrity constraints, concurrent access issues
- **Verdict**: REJECTED. Too primitive for a memory system.

#### Option C: SQLite Relations Table
```sql
CREATE TABLE entities (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    entity_type TEXT NOT NULL,  -- person, place, project, concept
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    mention_count INTEGER DEFAULT 1
);

CREATE TABLE entity_relations (
    id INTEGER PRIMARY KEY,
    source_id INTEGER REFERENCES entities(id),
    target_id INTEGER REFERENCES entities(id),
    relation_type TEXT NOT NULL,  -- works_with, located_at, part_of, discussed_in
    weight REAL DEFAULT 1.0,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    UNIQUE(source_id, target_id, relation_type)
);

CREATE TABLE memory_entities (
    memory_id INTEGER REFERENCES memories(id),
    entity_id INTEGER REFERENCES entities(id),
    PRIMARY KEY (memory_id, entity_id)
);

-- Indexes for fast lookups
CREATE INDEX idx_entities_name ON entities(name);
CREATE INDEX idx_entity_relations_source ON entity_relations(source_id);
CREATE INDEX idx_entity_relations_target ON entity_relations(target_id);
CREATE INDEX idx_memory_entities_entity ON memory_entities(entity_id);
```

**Query examples**:
```sql
-- Find all memories mentioning a person
SELECT m.* FROM memories m
JOIN memory_entities me ON m.id = me.memory_id
JOIN entities e ON e.id = me.entity_id
WHERE e.name = 'John Smith';

-- Find entities most associated with another entity (1-hop graph traversal)
SELECT e2.name, er.relation_type, er.weight
FROM entities e1
JOIN entity_relations er ON e1.id = er.source_id
JOIN entities e2 ON e2.id = er.target_id
WHERE e1.name = 'Project Alpha'
ORDER BY er.weight DESC;

-- Find most mentioned entities in the last 7 days
SELECT e.name, e.entity_type, COUNT(*) as recent_mentions
FROM entities e
JOIN memory_entities me ON e.id = me.entity_id
JOIN memories m ON m.id = me.memory_id
WHERE m.created_at > datetime('now', '-7 days')
GROUP BY e.id
ORDER BY recent_mentions DESC
LIMIT 20;
```

#### Verdict: **SQLite Relations Table wins**, with optional networkx for advanced analysis.

Reasons:
1. **Same database**: Entities, relations, and memories all in `jarvis_memory.db`. One file, one backup, one transaction scope.
2. **SQL queryable**: JOINs across entities, memories, and relations in single queries. FTS5 can index entity names.
3. **Durable**: Survives crashes. No in-memory state to lose.
4. **Concurrent-safe**: SQLite handles locking.
5. **Scales fine**: Graph traversals via SQL are O(edges) per hop, which is fine for personal entity counts (hundreds to low thousands).

**When to add networkx**: If JARVIS needs multi-hop graph analysis (e.g., "find the shortest path between two people through shared projects"), load the relations table into networkx on-demand:
```python
import networkx as nx

def build_entity_graph() -> nx.DiGraph:
    G = nx.DiGraph()
    for row in db.execute("SELECT source_id, target_id, relation_type, weight FROM entity_relations"):
        G.add_edge(row[0], row[1], relation=row[2], weight=row[3])
    return G
```

---

## Memory Compaction/Summarization Pipeline

Drawing from both mem0 and MemGPT patterns, here is the recommended compaction pipeline:

### Tier Transitions

```
HOT (0-7 days)                    WARM (7-30 days)
Full text + embeddings     ->     LLM summary + entities + embedding
FTS5 indexed                      FTS5 on summary + entity names
Vector searchable                 Vector searchable (re-embedded on summary)

WARM (7-30 days)                  COLD (30-90 days)
Summary + entities         ->     Single paragraph (recursive summary)
                                  Entity links preserved
                                  Vector searchable

COLD (30-90 days)                 ARCHIVE (90+ days)
Single paragraph           ->     One sentence
                                  Entity links preserved
                                  Permanently kept, never deleted
```

### Compaction Implementation

```python
async def compact_hot_to_warm(memory_id: int):
    """Transition a memory from hot to warm tier."""
    memory = get_memory(memory_id)

    # 1. LLM generates summary + extracts entities
    prompt = f"""Summarise this memory in 2-3 sentences. Extract all named entities
    (people, places, projects, dates, concepts).

    Memory: {memory.content}

    Respond as JSON:
    {{"summary": "...", "entities": [{{"name": "...", "type": "person|place|project|concept"}}]}}"""

    result = await llm_call(prompt)

    # 2. Generate new embedding from summary
    new_embedding = get_embedding(result["summary"])

    # 3. Update memory record
    db.execute("""
        UPDATE memories SET
            content = ?,
            tier = 'warm',
            original_content = content,
            embedding = ?,
            compacted_at = datetime('now')
        WHERE id = ?
    """, (result["summary"], serialize_float32(new_embedding), memory_id))

    # 4. Update entity graph
    for entity in result["entities"]:
        upsert_entity(entity["name"], entity["type"], memory_id)

    # 5. Update FTS5 index (via trigger)

async def compact_warm_to_cold(memory_ids: list[int]):
    """Compact multiple warm memories into a single cold memory (recursive summary)."""
    memories = [get_memory(mid) for mid in memory_ids]
    combined = "\n".join(m.content for m in memories)

    prompt = f"""Condense these related memories into a single paragraph:

    {combined}

    Write one clear paragraph capturing the key information."""

    paragraph = await llm_call(prompt)
    new_embedding = get_embedding(paragraph)

    # Create cold memory, archive warm ones
    cold_id = create_memory(paragraph, tier="cold", embedding=new_embedding)

    # Preserve entity links
    for mid in memory_ids:
        db.execute("""
            INSERT OR IGNORE INTO memory_entities (memory_id, entity_id)
            SELECT ?, entity_id FROM memory_entities WHERE memory_id = ?
        """, (cold_id, mid))
        db.execute("UPDATE memories SET tier = 'archived_warm', replaced_by = ? WHERE id = ?",
                   (cold_id, mid))

async def compact_cold_to_archive(memory_id: int):
    """Compress cold memory to one sentence for permanent archive."""
    memory = get_memory(memory_id)

    prompt = f"Summarise in exactly one sentence: {memory.content}"
    sentence = await llm_call(prompt)

    db.execute("""
        UPDATE memories SET
            content = ?,
            tier = 'archive',
            compacted_at = datetime('now')
        WHERE id = ?
    """, (sentence, memory_id))
```

### Scheduled Compaction (Cron Pattern)

```python
async def run_compaction():
    """Run daily at 3 AM local time."""
    # Hot -> Warm: memories older than 7 days
    hot_memories = db.execute("""
        SELECT id FROM memories
        WHERE tier = 'hot'
        AND created_at < datetime('now', '-7 days')
    """).fetchall()
    for (mid,) in hot_memories:
        await compact_hot_to_warm(mid)

    # Warm -> Cold: memories older than 30 days, grouped by week
    warm_memories = db.execute("""
        SELECT id, strftime('%Y-%W', created_at) as week
        FROM memories
        WHERE tier = 'warm'
        AND created_at < datetime('now', '-30 days')
        ORDER BY created_at
    """).fetchall()
    # Group by week, compact each group
    from itertools import groupby
    for week, group in groupby(warm_memories, key=lambda r: r[1]):
        ids = [r[0] for r in group]
        await compact_warm_to_cold(ids)

    # Cold -> Archive: memories older than 90 days
    cold_memories = db.execute("""
        SELECT id FROM memories
        WHERE tier = 'cold'
        AND created_at < datetime('now', '-90 days')
    """).fetchall()
    for (mid,) in cold_memories:
        await compact_cold_to_archive(mid)
```

---

## Recommended Full Schema

```sql
-- Core memories table
CREATE TABLE memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT NOT NULL,
    original_content TEXT,          -- preserved when compacted
    tier TEXT NOT NULL DEFAULT 'hot' CHECK(tier IN ('hot', 'warm', 'cold', 'archive')),
    source TEXT,                     -- 'conversation', 'observation', 'user_input', 'system'
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    compacted_at TEXT,
    replaced_by INTEGER REFERENCES memories(id),
    metadata JSON                   -- flexible extra data
);

-- FTS5 index (external content, synced via triggers)
CREATE VIRTUAL TABLE memories_fts USING fts5(
    content,
    tokenize='porter unicode61',
    content='memories',
    content_rowid='id'
);

-- Vector index
CREATE VIRTUAL TABLE vec_memories USING vec0(
    memory_id INTEGER PRIMARY KEY,
    embedding float[384],
    distance_metric=cosine
);

-- Entity graph
CREATE TABLE entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    entity_type TEXT NOT NULL,
    first_seen TEXT NOT NULL DEFAULT (datetime('now')),
    last_seen TEXT NOT NULL DEFAULT (datetime('now')),
    mention_count INTEGER DEFAULT 1
);

CREATE TABLE entity_relations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER REFERENCES entities(id),
    target_id INTEGER REFERENCES entities(id),
    relation_type TEXT NOT NULL,
    weight REAL DEFAULT 1.0,
    first_seen TEXT NOT NULL DEFAULT (datetime('now')),
    last_seen TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(source_id, target_id, relation_type)
);

CREATE TABLE memory_entities (
    memory_id INTEGER REFERENCES memories(id),
    entity_id INTEGER REFERENCES entities(id),
    PRIMARY KEY (memory_id, entity_id)
);

-- Indexes
CREATE INDEX idx_memories_tier ON memories(tier);
CREATE INDEX idx_memories_created ON memories(created_at);
CREATE INDEX idx_memories_tier_created ON memories(tier, created_at);
CREATE INDEX idx_entities_name ON entities(name);
CREATE INDEX idx_entities_type ON entities(entity_type);
CREATE INDEX idx_entity_relations_source ON entity_relations(source_id);
CREATE INDEX idx_entity_relations_target ON entity_relations(target_id);

-- FTS5 sync triggers
CREATE TRIGGER memories_fts_insert AFTER INSERT ON memories BEGIN
    INSERT INTO memories_fts(rowid, content) VALUES (new.id, new.content);
END;

CREATE TRIGGER memories_fts_delete AFTER DELETE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content) VALUES('delete', old.id, old.content);
END;

CREATE TRIGGER memories_fts_update AFTER UPDATE OF content ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content) VALUES('delete', old.id, old.content);
    INSERT INTO memories_fts(rowid, content) VALUES (new.id, new.content);
END;
```

---

## Library Versions & Dependencies

| Library | Version | Purpose | Install |
|---------|---------|---------|---------|
| sqlite-vec | v0.1.9 | Vector search in SQLite | `pip install sqlite-vec` |
| sentence-transformers | 4.x | Fallback embeddings | `pip install sentence-transformers` |
| ollama (Python) | 0.4.x | Primary embeddings via Ollama API | `pip install ollama` |
| httpx | 0.28.x | HTTP client for Ollama API | `pip install httpx` |
| networkx | 3.4.x | Optional graph analysis | `pip install networkx` |
| numpy | 2.x | Vector operations | `pip install numpy` |

**Not needed**:
- ChromaDB: sqlite-vec covers our vector search needs
- Neo4j/Memgraph: SQLite relations table covers entity graph
- mem0ai: We're building our own lighter version of this pattern
- Letta: We're borrowing the recursive summary concept, not the framework

---

## Architecture Summary

```
jarvis_memory.db (single SQLite file)
├── memories table          -- all tiers, all content
├── memories_fts (FTS5)     -- full-text search index
├── vec_memories (vec0)     -- vector similarity index
├── entities table          -- entity graph nodes
├── entity_relations table  -- entity graph edges
└── memory_entities table   -- memory <-> entity links

Embedding pipeline:
    Ollama nomic-embed-text (primary, 768d -> truncated to 384d)
    └── fallback: sentence-transformers all-MiniLM-L6-v2 (384d native)

Search pipeline:
    Query -> [FTS5 keyword search] + [Vector semantic search] -> RRF merge -> ranked results

Compaction pipeline (daily cron):
    Hot (full text, 0-7d) -> Warm (LLM summary + entities, 7-30d)
    -> Cold (single paragraph, 30-90d) -> Archive (one sentence, 90d+, permanent)
```

Sources:
- [mem0 GitHub](https://github.com/mem0ai/mem0)
- [mem0 Core Architecture (DeepWiki)](https://deepwiki.com/mem0ai/mem0/2-core-architecture)
- [MemGPT Paper](https://arxiv.org/abs/2310.08560)
- [Letta Memory Management Docs](https://docs.letta.com/advanced/memory-management/)
- [MemGPT Virtual Context (Leonie Monigatti)](https://www.leoniemonigatti.com/blog/memgpt.html)
- [SQLite FTS5 Extension](https://www.sqlite.org/fts5.html)
- [sqlite-vec GitHub](https://github.com/asg017/sqlite-vec)
- [sqlite-vec KNN Queries](https://alexgarcia.xyz/sqlite-vec/features/knn.html)
- [SQLite vs Chroma Comparison](https://dev.to/stephenc222/sqlite-vs-chroma-a-comparative-analysis-for-managing-vector-embeddings-4i76)
- [ChromaDB vs Qdrant vs pgvector Comparison 2026](https://4xxi.com/articles/vector-database-comparison/)
- [all-MiniLM-L6-v2 on HuggingFace](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2)
- [nomic-embed-text on Ollama](https://ollama.com/library/nomic-embed-text)
- [nomic-embed-text-v1.5 on HuggingFace](https://huggingface.co/nomic-ai/nomic-embed-text-v1.5)
- [Ollama Embedding Models Guide 2025](https://collabnix.com/ollama-embedded-models-the-complete-technical-guide-to-local-ai-embeddings-in-2025/)
- [State of AI Agent Memory 2026 (mem0 blog)](https://mem0.ai/blog/state-of-ai-agent-memory-2026)
- [Top 6 AI Agent Memory Frameworks 2026](https://dev.to/nebulagg/top-6-ai-agent-memory-frameworks-for-devs-2026-1fef)
