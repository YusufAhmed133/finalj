"""Quick live test: Telegram bot echoes messages and shows chat_id."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from jarvis.agents.comms import TelegramBot
from jarvis.identity.loader import get_user_first_name


async def echo_handler(message: str, source: str, metadata: dict) -> str:
    """Simple echo handler until intelligence layer is connected."""
    name = get_user_first_name()

    if message.startswith("/"):
        if message.startswith("/start"):
            chat_id = metadata.get("chat_id", "?")
            return (
                f"JARVIS online. Hello {name}.\n\n"
                f"Your chat_id: {chat_id}\n"
                f"Save this in config/secrets.env as TELEGRAM_OWNER_CHAT_ID={chat_id}\n\n"
                f"Intelligence layer not connected yet — I'll echo for now."
            )
        elif message.startswith("/status"):
            return "JARVIS v3.0 — Telegram connected. Intelligence: offline (echo mode)."
        return f"Unknown command: {message}"

    return f"[Echo] {message}\n\n(Intelligence layer not connected yet — this is a test.)"


async def main():
    bot = TelegramBot()
    ok = await bot.initialize(message_handler=echo_handler)
    if not ok:
        print("Failed to initialize. Check TELEGRAM_BOT_TOKEN in config/secrets.env")
        return

    print("Starting Telegram bot...")
    await bot.start()
    print("Bot is running! Send /start to your bot on Telegram.")
    print("Press Ctrl+C to stop.\n")

    try:
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        pass
    finally:
        await bot.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped.")
