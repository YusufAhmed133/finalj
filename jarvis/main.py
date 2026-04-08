"""
JARVIS — Main Entry Point.

Starts all subsystems:
1. Memory spine
2. Intelligence layer (Tier 1 or Tier 2)
3. Telegram bot
4. Computer use agent
5. Knowledge scraping agent
6. Scheduled briefings
7. Dashboard (FastAPI)

Usage:
    python -m jarvis.main
    python -m jarvis.main --cli   (debug CLI mode, no Telegram)
"""
import asyncio
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from jarvis.orchestrator.core import Orchestrator
from jarvis.agents.comms import TelegramBot
from jarvis.agents.knowledge import KnowledgeAgent
from jarvis.agents.computer import ComputerUseAgent
from jarvis.utils.logger import get_logger

log = get_logger("main")


class JARVIS:
    """Main JARVIS application."""

    def __init__(self):
        self.orchestrator = Orchestrator()
        self.telegram = TelegramBot()
        self.knowledge = KnowledgeAgent(self.orchestrator.spine)
        self.computer = ComputerUseAgent(
            spine=self.orchestrator.spine,
            message_callback=None,  # Set after telegram init
            approval_callback=None,
        )
        self._shutdown_event = None

    async def start(self, cli_mode: bool = False):
        self._shutdown_event = asyncio.Event()
        """Start JARVIS."""
        log.info("=" * 50)
        log.info("JARVIS v3.0 starting...")
        log.info("=" * 50)

        # 1. Initialize orchestrator (memory, intelligence, scheduler)
        await self.orchestrator.initialize()

        # 2. Initialize computer use agent
        computer_ok = await self.computer.initialize()
        if computer_ok:
            log.info("Computer use agent ready")
        else:
            log.warning("Computer use agent unavailable (no API key)")

        # 3. Initialize knowledge agent
        await self.knowledge.initialize()

        if cli_mode:
            # Debug CLI mode — no Telegram
            log.info("Running in CLI mode (no Telegram)")
            await self._run_cli()
        else:
            # 4. Initialize Telegram bot
            telegram_ok = await self.telegram.initialize(
                message_handler=self.orchestrator.handle_message,
            )
            if telegram_ok:
                # Wire up callbacks
                self.orchestrator.send_message_callback = self.telegram.send_message
                self.computer.message_callback = self.telegram.send_message
                self.computer.approval_callback = self.telegram.request_approval

                # Start Telegram bot
                await self.telegram.start()
                log.info("Telegram bot running")
            else:
                log.error("Telegram bot failed to start. Check TELEGRAM_BOT_TOKEN in secrets.env")
                log.info("Falling back to CLI mode")
                await self._run_cli()
                return

            # 5. Start background knowledge scraping
            asyncio.create_task(self._knowledge_loop())

            # 6. Wait for shutdown
            log.info("JARVIS is online. Waiting for messages...")
            await self._shutdown_event.wait()

        await self.shutdown()

    async def _knowledge_loop(self):
        """Run knowledge scraping on interval."""
        while not self._shutdown_event.is_set():
            try:
                await self.knowledge.execute({})
                log.info("Knowledge scraping cycle complete")
            except Exception as e:
                log.error(f"Knowledge scraping error: {e}")

            # Wait 30 minutes between cycles
            try:
                await asyncio.wait_for(self._shutdown_event.wait(), timeout=1800)
                break  # Shutdown requested
            except asyncio.TimeoutError:
                continue

    async def _run_cli(self):
        """Debug CLI interface."""
        print("\nJARVIS CLI Mode (type 'quit' to exit)")
        print("-" * 40)

        while True:
            try:
                user_input = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: input("\n> ")
                )
            except (EOFError, KeyboardInterrupt):
                break

            if user_input.lower() in ("quit", "exit", "q"):
                break

            response = await self.orchestrator.handle_message(
                message=user_input,
                source="cli",
            )
            print(f"\nJARVIS> {response}")

    async def shutdown(self):
        """Clean shutdown of all subsystems."""
        log.info("Shutting down JARVIS...")

        await self.telegram.stop()
        await self.computer.shutdown()
        await self.knowledge.shutdown()
        await self.orchestrator.shutdown()

        log.info("JARVIS shut down complete.")

    def request_shutdown(self):
        """Signal shutdown from signal handler."""
        self._shutdown_event.set()


def main():
    cli_mode = "--cli" in sys.argv
    jarvis = JARVIS()

    async def run():
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, jarvis.request_shutdown)
        await jarvis.start(cli_mode=cli_mode)

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        log.info("Keyboard interrupt")


if __name__ == "__main__":
    main()
