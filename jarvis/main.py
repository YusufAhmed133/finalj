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
from jarvis.agents.computer import ComputerAgent
from jarvis.utils.logger import get_logger

log = get_logger("main")


class JARVIS:
    """Main JARVIS application."""

    def __init__(self):
        self.orchestrator = Orchestrator()
        self.telegram = TelegramBot()
        self.knowledge = KnowledgeAgent(self.orchestrator.spine)
        self.computer = ComputerAgent(spine=self.orchestrator.spine)
        self._shutdown_event = None

    async def start(self, cli_mode: bool = False):
        self._shutdown_event = asyncio.Event()
        """Start JARVIS."""
        log.info("=" * 50)
        log.info("JARVIS v3.0 starting...")
        log.info("=" * 50)

        # 1. Initialize orchestrator (memory, intelligence, scheduler)
        await self.orchestrator.initialize()

        # 2. Mac control via instant commands + Claude DO: commands
        log.info("Mac control: instant commands + Claude")

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
                self.computer.send_message = self.telegram.send_message
                self.computer.request_approval = self.telegram.request_approval

                # Start Telegram bot
                await self.telegram.start()
                log.info("Telegram bot running")
            else:
                log.error("Telegram bot failed to start. Check TELEGRAM_BOT_TOKEN in secrets.env")
                log.info("Falling back to CLI mode")
                await self._run_cli()
                return

            # 5. Start background tasks
            asyncio.create_task(self._knowledge_loop())
            asyncio.create_task(self._briefing_loop())

            # 6. Start voice interface at localhost:7777
            asyncio.create_task(self._start_voice_server())

            # 7. Wait for shutdown
            log.info("JARVIS is online. Waiting for messages...")
            await self._shutdown_event.wait()

        await self.shutdown()

    async def _start_voice_server(self):
        """Start voice interface at localhost:8080."""
        try:
            import uvicorn
            from jarvis.voice.server import app as voice_app, set_handler, set_data
            set_handler(self.orchestrator.handle_message)
            set_data(self.orchestrator.spine, self.orchestrator.graph)
            config = uvicorn.Config(voice_app, host="0.0.0.0", port=7777, log_level="warning")
            server = uvicorn.Server(config)
            log.info("Voice interface at http://localhost:7777")
            await server.serve()
        except Exception as e:
            log.error(f"Voice server error: {e}")

    async def _knowledge_loop(self):
        """Run knowledge scraping on interval."""
        while not self._shutdown_event.is_set():
            try:
                await self.knowledge.execute({})
                log.info("Knowledge scraping cycle complete")
            except Exception as e:
                log.error(f"Knowledge scraping error: {e}")

            # Wait 6 hours between cycles
            try:
                await asyncio.wait_for(self._shutdown_event.wait(), timeout=21600)
                break
            except asyncio.TimeoutError:
                continue

    async def _briefing_loop(self):
        """Check every minute if it's time for morning or evening briefing."""
        from jarvis.orchestrator.briefing import BriefingGenerator
        briefer = BriefingGenerator(self.orchestrator.spine, self.orchestrator.intelligence)
        sent_today_morning = False
        sent_today_evening = False
        last_date = None

        while not self._shutdown_event.is_set():
            try:
                from datetime import datetime
                now = datetime.now()
                today = now.strftime("%Y-%m-%d")

                # Reset flags on new day
                if today != last_date:
                    sent_today_morning = False
                    sent_today_evening = False
                    last_date = today

                # Morning briefing at 7am
                if now.hour == 7 and now.minute < 5 and not sent_today_morning:
                    log.info("Generating morning briefing...")
                    text = await briefer.morning_briefing()
                    if self.telegram and text:
                        await self.telegram.send_message(text)
                    sent_today_morning = True

                # Evening review at 9pm
                if now.hour == 21 and now.minute < 5 and not sent_today_evening:
                    log.info("Generating evening review...")
                    text = await briefer.evening_review()
                    if self.telegram and text:
                        await self.telegram.send_message(text)
                    sent_today_evening = True

            except Exception as e:
                log.error(f"Briefing error: {e}")

            try:
                await asyncio.wait_for(self._shutdown_event.wait(), timeout=60)
                break
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
