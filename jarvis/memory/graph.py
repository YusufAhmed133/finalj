"""
Entity Graph — Tracks relationships between entities in JARVIS's memory.

Stores entities (people, places, concepts, events) and their relationships.
JSON-based for simplicity at personal scale. Loaded into memory on startup.
"""
import json
import time
from pathlib import Path
from typing import Optional

from jarvis.utils.logger import get_logger

log = get_logger("memory.graph")

GRAPH_PATH = Path(__file__).parent.parent.parent / "data" / "graph.json"


class EntityGraph:
    """In-memory entity relationship graph with JSON persistence."""

    def __init__(self, path: Optional[Path] = None):
        self.path = path or GRAPH_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.entities: dict = {}     # name -> {type, attributes, first_seen, last_seen, mention_count}
        self.relations: list = []    # [{source, target, type, weight, timestamp}]
        self._load()

    def _load(self):
        """Load graph from disk."""
        if self.path.exists():
            data = json.loads(self.path.read_text())
            self.entities = data.get("entities", {})
            self.relations = data.get("relations", [])
            log.info(f"Loaded graph: {len(self.entities)} entities, {len(self.relations)} relations")
        else:
            log.info("No existing graph found, starting fresh")

    def _save(self):
        """Persist graph to disk."""
        data = {"entities": self.entities, "relations": self.relations}
        self.path.write_text(json.dumps(data, indent=2))

    def add_entity(self, name: str, entity_type: str = "unknown", attributes: Optional[dict] = None):
        """Add or update an entity."""
        now = time.time()
        name_key = name.lower().strip()

        if name_key in self.entities:
            self.entities[name_key]["last_seen"] = now
            self.entities[name_key]["mention_count"] += 1
            if attributes:
                self.entities[name_key]["attributes"].update(attributes)
        else:
            self.entities[name_key] = {
                "name": name,
                "type": entity_type,
                "attributes": attributes or {},
                "first_seen": now,
                "last_seen": now,
                "mention_count": 1,
            }
        self._save()

    def add_relation(self, source: str, target: str, relation_type: str, weight: float = 1.0):
        """Add a relationship between two entities."""
        source_key = source.lower().strip()
        target_key = target.lower().strip()

        # Ensure both entities exist
        if source_key not in self.entities:
            self.add_entity(source)
        if target_key not in self.entities:
            self.add_entity(target)

        # Check for existing relation
        for rel in self.relations:
            if rel["source"] == source_key and rel["target"] == target_key and rel["type"] == relation_type:
                rel["weight"] += weight
                rel["timestamp"] = time.time()
                self._save()
                return

        self.relations.append({
            "source": source_key,
            "target": target_key,
            "type": relation_type,
            "weight": weight,
            "timestamp": time.time(),
        })
        self._save()

    def get_entity(self, name: str) -> Optional[dict]:
        """Get an entity by name."""
        return self.entities.get(name.lower().strip())

    def get_relations(self, entity_name: str) -> list:
        """Get all relations involving an entity."""
        key = entity_name.lower().strip()
        return [r for r in self.relations if r["source"] == key or r["target"] == key]

    def get_connected_entities(self, entity_name: str, max_depth: int = 2) -> set:
        """BFS to find entities connected within N hops."""
        key = entity_name.lower().strip()
        visited = set()
        queue = [(key, 0)]

        while queue:
            current, depth = queue.pop(0)
            if current in visited or depth > max_depth:
                continue
            visited.add(current)

            for rel in self.relations:
                if rel["source"] == current and rel["target"] not in visited:
                    queue.append((rel["target"], depth + 1))
                elif rel["target"] == current and rel["source"] not in visited:
                    queue.append((rel["source"], depth + 1))

        visited.discard(key)
        return visited

    def search_entities(self, query: str, limit: int = 10) -> list:
        """Simple substring search on entity names."""
        query_lower = query.lower()
        results = []
        for key, entity in self.entities.items():
            if query_lower in key:
                results.append(entity)
        results.sort(key=lambda e: e["mention_count"], reverse=True)
        return results[:limit]

    def most_mentioned(self, limit: int = 20) -> list:
        """Get most frequently mentioned entities."""
        sorted_entities = sorted(
            self.entities.values(),
            key=lambda e: e["mention_count"],
            reverse=True,
        )
        return sorted_entities[:limit]

    def stats(self) -> dict:
        """Graph statistics."""
        type_counts = {}
        for entity in self.entities.values():
            t = entity["type"]
            type_counts[t] = type_counts.get(t, 0) + 1
        return {
            "total_entities": len(self.entities),
            "total_relations": len(self.relations),
            "entity_types": type_counts,
        }
