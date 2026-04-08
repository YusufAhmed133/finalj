"""
Claude.ai Conversation Export Importer.

Imports conversations from Claude's export JSON format.
Each conversation becomes a memory entry with entities extracted from participants.

Export format (conversations.json):
[
  {
    "uuid": "...",
    "name": "conversation title",
    "created_at": "2024-01-15T10:30:00Z",
    "updated_at": "...",
    "chat_messages": [
      {
        "uuid": "...",
        "sender": "human" | "assistant",
        "text": "message content",
        "created_at": "..."
      }
    ]
  }
]
"""
import json
from pathlib import Path
from datetime import datetime
from typing import Optional

from jarvis.memory.spine import MemorySpine
from jarvis.utils.logger import get_logger

log = get_logger("importers.claude")


def import_claude_export(
    file_path: Path,
    spine: MemorySpine,
    max_conversations: Optional[int] = None,
) -> dict:
    """Import Claude.ai conversation export into memory.

    Args:
        file_path: Path to conversations.json
        spine: Memory spine instance
        max_conversations: Limit number of conversations (None = all)

    Returns:
        dict with import stats
    """
    log.info(f"Importing Claude export from {file_path}")

    data = json.loads(file_path.read_text())

    # Handle both array format and object-with-array format
    if isinstance(data, dict):
        conversations = data.get("conversations", data.get("chat_conversations", []))
    elif isinstance(data, list):
        conversations = data
    else:
        raise ValueError(f"Unexpected format: {type(data)}")

    if max_conversations:
        conversations = conversations[:max_conversations]

    stats = {"conversations": 0, "messages": 0, "memories_created": 0}

    for conv in conversations:
        title = conv.get("name", conv.get("title", "Untitled"))
        created = conv.get("created_at", "")
        messages = conv.get("chat_messages", conv.get("messages", []))

        if not messages:
            continue

        # Build conversation text
        lines = [f"Conversation: {title}"]
        for msg in messages:
            sender = msg.get("sender", msg.get("role", "unknown"))
            text = msg.get("text", msg.get("content", ""))
            if isinstance(text, list):
                # Handle content blocks format
                text = " ".join(
                    block.get("text", "") for block in text
                    if isinstance(block, dict) and block.get("type") == "text"
                )
            if text:
                lines.append(f"{sender}: {text[:500]}")  # Truncate long messages
                stats["messages"] += 1

        content = "\n".join(lines)

        # Don't store empty conversations
        if len(lines) <= 1:
            continue

        # Store as a memory
        spine.store(
            content=content[:5000],  # Cap total size
            type="import_claude",
            source="claude_export",
            entities=_extract_entities(content),
            metadata={
                "conversation_id": conv.get("uuid", ""),
                "title": title,
                "original_date": created,
                "message_count": len(messages),
            },
        )
        stats["conversations"] += 1
        stats["memories_created"] += 1

    log.info(f"Claude import complete: {stats}")
    return stats


def _extract_entities(text: str) -> list:
    """Simple entity extraction — proper nouns and capitalized words."""
    import re
    # Find capitalized words that aren't at start of sentences
    words = re.findall(r'(?<!\. )(?<!\n)[A-Z][a-z]+(?:\s[A-Z][a-z]+)*', text)
    # Deduplicate and filter common words
    common = {"The", "This", "That", "These", "Those", "What", "When", "Where",
              "How", "Why", "Which", "Who", "And", "But", "Yes", "No", "Not",
              "Can", "Could", "Would", "Should", "Will", "Shall", "May", "Might",
              "Here", "There", "Now", "Then", "Also", "Just", "Let", "Sure",
              "Conversation", "Human", "Assistant"}
    entities = list(dict.fromkeys(w for w in words if w not in common))
    return entities[:20]  # Cap at 20 entities per memory
