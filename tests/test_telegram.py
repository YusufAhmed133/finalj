"""Tests for JARVIS Telegram bot — offline tests (no bot token needed)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from jarvis.agents.comms import TelegramBot

PASSED = 0
FAILED = 0


def report(name: str, passed: bool, detail: str = ""):
    global PASSED, FAILED
    if passed:
        PASSED += 1
        print(f"  PASS: {name}")
    else:
        FAILED += 1
        print(f"  FAIL: {name} — {detail}")


def test_import():
    print("\n=== Import Tests ===")
    try:
        from jarvis.agents.comms import TelegramBot
        report("Import TelegramBot", True)
    except Exception as e:
        report("Import TelegramBot", False, str(e))


def test_init():
    print("\n=== Initialization Tests ===")
    bot = TelegramBot()
    report("Bot created", bot is not None)
    report("No owner initially", bot.owner_chat_id is None)
    report("Empty context", len(bot._context_messages) == 0)
    report("No pending approvals", len(bot._pending_approvals) == 0)


def test_message_splitting():
    print("\n=== Message Splitting Tests ===")
    bot = TelegramBot()

    # Short message
    chunks = bot._split_message("Hello world")
    report("Short message = 1 chunk", len(chunks) == 1)

    # Exact limit
    msg = "x" * 4000
    chunks = bot._split_message(msg)
    report("At limit = 1 chunk", len(chunks) == 1)

    # Over limit
    msg = "x" * 8000
    chunks = bot._split_message(msg, max_len=4000)
    report("Over limit = 2 chunks", len(chunks) == 2)
    report("All chunks under limit", all(len(c) <= 4000 for c in chunks))

    # With newlines — should break at newline
    msg = "Line 1\n" * 600  # ~4200 chars
    chunks = bot._split_message(msg, max_len=4000)
    report("Breaks at newline", len(chunks) >= 2)
    report("Clean break", chunks[0].endswith("Line 1"))


def test_context_tracking():
    print("\n=== Context Tracking Tests ===")
    bot = TelegramBot()

    bot._add_context("Yusuf", "What's IVV at?")
    bot._add_context("JARVIS", "IVV is at $680")
    report("Context has 2 messages", len(bot._context_messages) == 2)

    context_str = bot.get_context()
    report("Context string contains both", "Yusuf" in context_str and "JARVIS" in context_str)

    # Test context window limit (20 messages)
    for i in range(25):
        bot._add_context("Yusuf", f"Message {i}")
    report("Context capped at 20", len(bot._context_messages) == 20)
    report("Oldest dropped", "Message 0" not in bot.get_context())


def test_owner_check():
    print("\n=== Owner Check Tests ===")
    bot = TelegramBot()

    # No owner set — should accept all
    report("No owner = accept all", bot.owner_chat_id is None)

    # Set owner
    bot.owner_chat_id = 12345
    report("Owner set", bot.owner_chat_id == 12345)


if __name__ == "__main__":
    print("=" * 60)
    print("JARVIS Telegram Bot Tests (offline)")
    print("=" * 60)

    test_import()
    test_init()
    test_message_splitting()
    test_context_tracking()
    test_owner_check()

    print("\n" + "=" * 60)
    print(f"Results: {PASSED} passed, {FAILED} failed, {PASSED + FAILED} total")
    print("=" * 60)

    sys.exit(0 if FAILED == 0 else 1)
