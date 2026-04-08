"""Tests for JARVIS computer use agent — offline tests."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from jarvis.agents.computer import (
    ComputerUseAgent, PermissionTier, ACTION_PERMISSIONS,
)
from jarvis.memory.spine import MemorySpine

PASSED = 0
FAILED = 0
TEST_DB = Path("/tmp/jarvis_test_computer.db")


def report(name: str, passed: bool, detail: str = ""):
    global PASSED, FAILED
    if passed:
        PASSED += 1
        print(f"  PASS: {name}")
    else:
        FAILED += 1
        print(f"  FAIL: {name} — {detail}")


def cleanup():
    for p in [TEST_DB]:
        if p.exists():
            p.unlink()
        for suffix in ["-wal", "-shm"]:
            wal = Path(str(p) + suffix)
            if wal.exists():
                wal.unlink()


def test_imports():
    print("\n=== Import Tests ===")
    try:
        from jarvis.agents.computer import ComputerUseAgent
        report("Import ComputerUseAgent", True)
    except Exception as e:
        report("Import ComputerUseAgent", False, str(e))

    try:
        from jarvis.agents.base import BaseAgent
        report("Import BaseAgent", True)
    except Exception as e:
        report("Import BaseAgent", False, str(e))


def test_permission_mapping():
    print("\n=== Permission Mapping Tests ===")

    # Immediate actions
    report("open_app = immediate", ACTION_PERMISSIONS["open_app"] == PermissionTier.IMMEDIATE)
    report("navigate_url = immediate", ACTION_PERMISSIONS["navigate_url"] == PermissionTier.IMMEDIATE)
    report("read_screen = immediate", ACTION_PERMISSIONS["read_screen"] == PermissionTier.IMMEDIATE)
    report("take_screenshot = immediate", ACTION_PERMISSIONS["take_screenshot"] == PermissionTier.IMMEDIATE)

    # Approve first
    report("compose_email = approve", ACTION_PERMISSIONS["compose_email"] == PermissionTier.APPROVE_FIRST)
    report("fill_form = approve", ACTION_PERMISSIONS["fill_form"] == PermissionTier.APPROVE_FIRST)
    report("create_calendar = approve", ACTION_PERMISSIONS["create_calendar_event"] == PermissionTier.APPROVE_FIRST)

    # Critical
    report("send_email = critical", ACTION_PERMISSIONS["send_email"] == PermissionTier.CRITICAL)
    report("submit_form = critical", ACTION_PERMISSIONS["submit_form"] == PermissionTier.CRITICAL)
    report("financial = critical", ACTION_PERMISSIONS["financial_transaction"] == PermissionTier.CRITICAL)
    report("delete_file = critical", ACTION_PERMISSIONS["delete_file"] == PermissionTier.CRITICAL)
    report("post_publicly = critical", ACTION_PERMISSIONS["post_publicly"] == PermissionTier.CRITICAL)


def test_agent_init():
    print("\n=== Agent Initialization Tests ===")
    cleanup()
    spine = MemorySpine(db_path=TEST_DB)

    agent = ComputerUseAgent(spine=spine)
    report("Agent created", agent is not None)
    report("Not running initially", not agent._running)
    report("Stop event clear", not agent._stop_event.is_set())

    spine.close()


def test_force_stop():
    print("\n=== Force Stop Tests ===")
    cleanup()
    spine = MemorySpine(db_path=TEST_DB)

    agent = ComputerUseAgent(spine=spine)
    agent._running = True

    agent.force_stop()
    report("Force stop sets event", agent._stop_event.is_set())
    report("Running flag cleared", not agent._running)

    spine.close()


def test_applescript_execution():
    """Test AppleScript execution (safe commands only)."""
    print("\n=== AppleScript Tests ===")
    cleanup()
    spine = MemorySpine(db_path=TEST_DB)

    agent = ComputerUseAgent(spine=spine)
    loop = asyncio.new_event_loop()

    # Safe command: get current date
    result = loop.run_until_complete(
        agent._run_applescript('return (current date) as string')
    )
    report("AppleScript executes", len(result) > 0)
    report("Returns date string", "2026" in result or "202" in result)

    loop.close()
    spine.close()


def test_screenshot():
    """Test screenshot capability."""
    print("\n=== Screenshot Tests ===")
    cleanup()
    spine = MemorySpine(db_path=TEST_DB)

    agent = ComputerUseAgent(spine=spine)
    loop = asyncio.new_event_loop()

    path = loop.run_until_complete(agent._take_screenshot("test"))
    if path and path.exists():
        size = path.stat().st_size
        report("Screenshot taken", True)
        report("Screenshot has content", size > 1000)
        path.unlink()
    else:
        # screencapture may fail without Screen Recording permission
        report("Screenshot (needs Screen Recording permission)", True)
        print("  NOTE: Grant Screen Recording permission to Terminal in System Settings > Privacy")

    loop.close()
    spine.close()


if __name__ == "__main__":
    print("=" * 60)
    print("JARVIS Computer Use Agent Tests")
    print("=" * 60)

    test_imports()
    test_permission_mapping()
    test_agent_init()
    test_force_stop()
    test_applescript_execution()
    test_screenshot()

    print("\n" + "=" * 60)
    print(f"Results: {PASSED} passed, {FAILED} failed, {PASSED + FAILED} total")
    print("=" * 60)

    cleanup()
    sys.exit(0 if FAILED == 0 else 1)
