"""
Claude API Client — Tier 2 Intelligence Layer.

Direct API calls using the anthropic Python SDK.
Faster, more reliable, but requires ANTHROPIC_API_KEY.
"""
from typing import Optional

import anthropic

from jarvis.utils.logger import get_logger

log = get_logger("brain.claude_api")

DEFAULT_MODEL = "claude-sonnet-4-5-20250514"
MAX_TOKENS = 8192


class ClaudeAPIClient:
    """Direct API client for Claude — Tier 2 intelligence."""

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        log.info(f"Claude API client initialized (model={model})")

    async def send_prompt(self, prompt: str, system: str = "", timeout: int = 120) -> str:
        """Send a prompt and get a response.

        Args:
            prompt: User message
            system: System prompt
            timeout: Max seconds (not directly used — API has its own timeout)

        Returns:
            Claude's response text
        """
        messages = [{"role": "user", "content": prompt}]

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=MAX_TOKENS,
                system=system if system else anthropic.NOT_GIVEN,
                messages=messages,
            )
            text = ""
            for block in response.content:
                if block.type == "text":
                    text += block.text

            log.info(f"API response: {len(text)} chars, {response.usage.input_tokens}+{response.usage.output_tokens} tokens")
            return text

        except anthropic.APIError as e:
            log.error(f"Claude API error: {e}")
            raise

    def health_check(self) -> dict:
        """Check API connectivity."""
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=10,
                messages=[{"role": "user", "content": "ping"}],
            )
            return {"connected": True, "model": self.model}
        except Exception as e:
            return {"connected": False, "error": str(e)}
