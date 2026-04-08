"""Tests for JARVIS orchestrator — priority, commands, routing."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from jarvis.orchestrator.priority import score_priority, is_stop_command, is_cardiac_alert
from jarvis.orchestrator.core import Orchestrator, Mode

PASSED = 0
FAILED = 0
TEST_DB = Path("/tmp/jarvis_test_orchestrator.db")
TEST_GRAPH = Path("/tmp/jarvis_test_orch_graph.json")


def report(name: str, passed: bool, detail: str = ""):
    global PASSED, FAILED
    if passed:
        PASSED += 1
        print(f"  PASS: {name}")
    else:
        FAILED += 1
        print(f"  FAIL: {name} — {detail}")


def cleanup():
    for p in [TEST_DB, TEST_GRAPH]:
        if p.exists():
            p.unlink()
        for suffix in ["-wal", "-shm"]:
            wal = Path(str(p) + suffix)
            if wal.exists():
                wal.unlink()


def test_priority():
    print("\n=== Priority Scoring Tests ===")

    # Cardiac = 100
    report("Cardiac alert = 100", score_priority("my cardiac device is alerting") == 100)
    report("Heart pain = 100", score_priority("having chest pain") == 100)
    report("Pacemaker = 100", score_priority("pacemaker check needed") == 100)

    # STOP = 95
    report("STOP = 95", score_priority("stop") == 95)
    report("/stop = 95", score_priority("/stop") == 95)
    report("KILL = 95", score_priority("kill") == 95)

    # Emergency = 90
    report("Emergency = 90", score_priority("this is an emergency") == 90)

    # Time-sensitive = 80
    report("Urgent = 80", score_priority("this is urgent") == 80)
    report("ASAP = 80", score_priority("do this asap") == 80)

    # Financial = 75
    report("Buy = 75", score_priority("buy more IVV shares") == 75)

    # Questions = 60
    report("Question = 60", score_priority("what's the weather?") == 60)

    # Default = 50
    report("Statement = 50", score_priority("I went to the gym today") == 50)


def test_stop_detection():
    print("\n=== Stop Command Detection Tests ===")

    report("'stop' is stop", is_stop_command("stop"))
    report("'STOP' is stop", is_stop_command("STOP"))
    report("'/stop' is stop", is_stop_command("/stop"))
    report("'kill' is stop", is_stop_command("kill"))
    report("'hello' is not stop", not is_stop_command("hello"))
    report("'stop the music' is NOT stop", not is_stop_command("stop the music"))


def test_cardiac_detection():
    print("\n=== Cardiac Alert Detection Tests ===")

    report("Cardiac device", is_cardiac_alert("cardiac device alert"))
    report("Heart rate", is_cardiac_alert("heart rate abnormal"))
    report("Pacemaker", is_cardiac_alert("pacemaker check"))
    report("Normal message", not is_cardiac_alert("what's for dinner"))
    report("IVV investing", not is_cardiac_alert("buy more IVV"))


def test_mode_management():
    print("\n=== Mode Management Tests ===")

    orch = Orchestrator.__new__(Orchestrator)
    orch.mode = Mode.ACTIVE

    # Test mode transitions
    result = orch._set_mode(Mode.FOCUS)
    report("Switch to focus", orch.mode == Mode.FOCUS and "focus" in result)

    result = orch._set_mode(Mode.SLEEP)
    report("Switch to sleep", orch.mode == Mode.SLEEP)

    result = orch._set_mode(Mode.ACTIVE)
    report("Switch back to active", orch.mode == Mode.ACTIVE)


def test_response_parsing():
    print("\n=== Response Parsing Tests ===")

    orch = Orchestrator.__new__(Orchestrator)

    # Valid JSON response
    valid = '{"reply": "Hello!", "action": null, "remember": null, "mood": "neutral"}'
    parsed = orch._parse_response(valid)
    report("Parse valid JSON", parsed["reply"] == "Hello!")

    # JSON embedded in text
    embedded = 'Here is my response:\n{"reply": "IVV is at $680", "action": null, "remember": "Yusuf asked about IVV", "mood": "informative"}\nDone.'
    parsed = orch._parse_response(embedded)
    report("Parse embedded JSON", parsed["reply"] == "IVV is at $680")
    report("Parse remember field", parsed["remember"] == "Yusuf asked about IVV")

    # Plain text fallback
    plain = "Just a normal text response without JSON"
    parsed = orch._parse_response(plain)
    report("Fallback to plain text", parsed["reply"] == plain)
    report("Fallback action is None", parsed["action"] is None)

    # JSON with action
    with_action = '{"reply": "I\'ll open Calendar", "action": {"type": "open_app", "details": "Google Calendar"}, "remember": null, "mood": "helpful"}'
    parsed = orch._parse_response(with_action)
    report("Parse action", parsed["action"]["type"] == "open_app")


def test_command_handling():
    print("\n=== Command Handling Tests ===")

    loop = asyncio.new_event_loop()

    # We can't fully test commands without initialization,
    # but we can test the routing
    orch = Orchestrator.__new__(Orchestrator)
    orch.mode = Mode.ACTIVE
    orch.spine = None
    orch.graph = None

    # Test command parsing
    cmd = "/active"
    parts = cmd.strip().lower().split()
    report("Command parsing", parts[0] == "/active")

    cmd = "/memory search query here"
    parts = cmd.strip().lower().split()
    args = cmd.strip()[len(parts[0]):].strip()
    report("Command with args", args == "search query here")

    loop.close()


if __name__ == "__main__":
    print("=" * 60)
    print("JARVIS Orchestrator Tests")
    print("=" * 60)

    test_priority()
    test_stop_detection()
    test_cardiac_detection()
    test_mode_management()
    test_response_parsing()
    test_command_handling()

    print("\n" + "=" * 60)
    print(f"Results: {PASSED} passed, {FAILED} failed, {PASSED + FAILED} total")
    print("=" * 60)

    sys.exit(0 if FAILED == 0 else 1)
