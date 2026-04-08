"""
Memory Compactor — Manages tier transitions and summarisation.

Runs daily at 3am AEST:
1. Hot (0-7d) → Warm (7-30d): Summarise full text to key points + entities
2. Warm (7-30d) → Cold (30-90d): Compress to single paragraph
3. Cold (30-90d) → Archive (90d+): Compress to one sentence

Summarisation uses the intelligence layer (Claude via browser or API).
When intelligence is unavailable, uses simple extractive summarisation.
"""
import re
from datetime import datetime
from typing import Optional

from jarvis.memory.spine import MemorySpine, TIER_HOT, TIER_WARM, TIER_COLD, TIER_ARCHIVE
from jarvis.utils.logger import get_logger

log = get_logger("memory.compactor")

# Transition map: current_tier -> next_tier
TIER_TRANSITIONS = {
    TIER_HOT: TIER_WARM,
    TIER_WARM: TIER_COLD,
    TIER_COLD: TIER_ARCHIVE,
}


def _extractive_summary(text: str, max_sentences: int = 3) -> str:
    """Simple extractive summary — first N sentences."""
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    selected = sentences[:max_sentences]
    return " ".join(selected)


def _one_sentence_summary(text: str) -> str:
    """Extract first sentence for archive tier."""
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    return sentences[0] if sentences else text[:200]


class MemoryCompactor:
    """Handles tier transitions and memory summarisation."""

    def __init__(self, spine: MemorySpine, summarise_fn=None):
        """
        Args:
            spine: The memory spine instance
            summarise_fn: Optional async function(text, target_length) -> summary
                         If None, uses extractive summarisation as fallback
        """
        self.spine = spine
        self.summarise_fn = summarise_fn

    async def compact_tier(self, tier: str) -> int:
        """Compact all memories in a tier that have aged past the threshold.

        Returns number of memories compacted.
        """
        next_tier = TIER_TRANSITIONS.get(tier)
        if not next_tier:
            return 0

        memories = self.spine.get_memories_for_compaction(tier)
        if not memories:
            log.info(f"No memories to compact from {tier}")
            return 0

        log.info(f"Compacting {len(memories)} memories from {tier} → {next_tier}")
        compacted = 0

        for mem in memories:
            content = mem["content"]
            existing_summary = mem.get("summary") or content

            if next_tier == TIER_WARM:
                # Hot → Warm: summarise to key points
                if self.summarise_fn:
                    summary = await self.summarise_fn(
                        content,
                        "Summarise this interaction into 2-3 key points. Include names, dates, and decisions."
                    )
                else:
                    summary = _extractive_summary(content, max_sentences=3)

            elif next_tier == TIER_COLD:
                # Warm → Cold: compress to single paragraph
                if self.summarise_fn:
                    summary = await self.summarise_fn(
                        existing_summary,
                        "Compress this to a single paragraph. Keep only the most important facts."
                    )
                else:
                    summary = _extractive_summary(existing_summary, max_sentences=2)

            elif next_tier == TIER_ARCHIVE:
                # Cold → Archive: one sentence
                if self.summarise_fn:
                    summary = await self.summarise_fn(
                        existing_summary,
                        "Compress this to exactly one sentence."
                    )
                else:
                    summary = _one_sentence_summary(existing_summary)

            else:
                continue

            self.spine.update_tier(mem["id"], next_tier, summary)
            compacted += 1

        log.info(f"Compacted {compacted} memories: {tier} → {next_tier}")
        return compacted

    async def run_full_compaction(self) -> dict:
        """Run compaction on all tiers. Called daily at 3am."""
        results = {}
        for tier in [TIER_HOT, TIER_WARM, TIER_COLD]:
            count = await self.compact_tier(tier)
            results[f"{tier}_to_{TIER_TRANSITIONS[tier]}"] = count

        stats = self.spine.stats()
        log.info(f"Full compaction complete. Memory stats: {stats}")
        return results
