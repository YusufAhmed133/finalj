"""
Vector Search — Semantic similarity search using sqlite-vec + Ollama embeddings.

Uses Ollama's nomic-embed-text model for local embedding generation.
Stores vectors in sqlite-vec for efficient similarity search.
"""
import sqlite3
import json
import struct
from pathlib import Path
from typing import Optional

import httpx
import sqlite_vec

from jarvis.utils.logger import get_logger

log = get_logger("memory.vectors")

VECTORS_DB_PATH = Path(__file__).parent.parent.parent / "data" / "vectors.db"
OLLAMA_URL = "http://localhost:11434"
EMBED_MODEL = "nomic-embed-text"
EMBED_DIMENSIONS = 768


def _serialize_f32(vec: list[float]) -> bytes:
    """Serialize a list of floats to bytes for sqlite-vec."""
    return struct.pack(f"{len(vec)}f", *vec)


class VectorStore:
    """Vector similarity search backed by sqlite-vec."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or VECTORS_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # Use sqlite_vec's own connection factory if system Python lacks enable_load_extension
        try:
            self.conn = sqlite3.connect(str(self.db_path))
            self.conn.enable_load_extension(True)
            sqlite_vec.load(self.conn)
            self.conn.enable_load_extension(False)
        except AttributeError:
            # System Python compiled without loadable extensions — use sqlite-vec's bundled sqlite
            import sqlite_vec as _sv
            db = _sv.connect(str(self.db_path)) if hasattr(_sv, "connect") else None
            if db is None:
                # Fallback: use apsw or skip vectors
                log.warning("sqlite-vec: enable_load_extension unavailable. Vector search disabled.")
                log.warning("Fix: brew install python3 or use pyenv to get a Python with extension support.")
                self.conn = sqlite3.connect(str(self.db_path))
                self._disabled = True
                return
            self.conn = db
        self._disabled = False
        self._init_schema()
        log.info(f"Vector store initialized at {self.db_path}")

    def _init_schema(self):
        """Create the virtual table for vector search."""
        self.conn.execute(f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS memory_vectors USING vec0(
                memory_id INTEGER PRIMARY KEY,
                embedding float[{EMBED_DIMENSIONS}]
            )
        """)
        self.conn.commit()

    async def get_embedding(self, text: str) -> list[float]:
        """Get embedding from Ollama."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{OLLAMA_URL}/api/embed",
                json={"model": EMBED_MODEL, "input": text},
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["embeddings"][0]

    def get_embedding_sync(self, text: str) -> list[float]:
        """Get embedding from Ollama (synchronous)."""
        resp = httpx.post(
            f"{OLLAMA_URL}/api/embed",
            json={"model": EMBED_MODEL, "input": text},
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["embeddings"][0]

    @property
    def available(self) -> bool:
        return not getattr(self, "_disabled", False)

    def store(self, memory_id: int, embedding: list[float]):
        """Store a vector for a memory."""
        self.conn.execute(
            "INSERT OR REPLACE INTO memory_vectors (memory_id, embedding) VALUES (?, ?)",
            (memory_id, _serialize_f32(embedding)),
        )
        self.conn.commit()

    def search(self, query_embedding: list[float], limit: int = 10) -> list[dict]:
        """Find most similar memories by vector distance."""
        rows = self.conn.execute(
            """SELECT memory_id, distance
               FROM memory_vectors
               WHERE embedding MATCH ?
               ORDER BY distance
               LIMIT ?""",
            (_serialize_f32(query_embedding), limit),
        ).fetchall()
        return [{"memory_id": r[0], "distance": r[1]} for r in rows]

    async def store_with_embedding(self, memory_id: int, text: str):
        """Generate embedding and store in one step."""
        embedding = await self.get_embedding(text)
        self.store(memory_id, embedding)
        log.debug(f"Stored vector for memory #{memory_id}")

    async def search_similar(self, query: str, limit: int = 10) -> list[dict]:
        """Search by text query — generates embedding then searches."""
        query_embedding = await self.get_embedding(query)
        return self.search(query_embedding, limit)

    def count(self) -> int:
        """Count stored vectors."""
        row = self.conn.execute("SELECT COUNT(*) FROM memory_vectors").fetchone()
        return row[0]

    def delete(self, memory_id: int):
        """Delete a vector."""
        self.conn.execute("DELETE FROM memory_vectors WHERE memory_id = ?", (memory_id,))
        self.conn.commit()

    def close(self):
        self.conn.close()
        log.info("Vector store closed")
