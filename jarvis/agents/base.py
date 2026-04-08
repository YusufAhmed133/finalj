"""Abstract base class for JARVIS agents."""
from abc import ABC, abstractmethod


class BaseAgent(ABC):
    """Base class all JARVIS agents must inherit from."""

    @abstractmethod
    async def initialize(self) -> bool:
        """Initialize the agent. Returns True if successful."""
        ...

    @abstractmethod
    async def execute(self, task: dict) -> dict:
        """Execute a task. Returns result dict."""
        ...

    @abstractmethod
    async def shutdown(self):
        """Clean shutdown."""
        ...
