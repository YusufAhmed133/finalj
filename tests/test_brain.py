"""Tests for JARVIS brain — intelligence layer components."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

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


def test_imports():
    """Test that all brain modules import cleanly."""
    print("\n=== Import Tests ===")

    try:
        from jarvis.brain.claude_browser import ClaudeBrowserSession
        report("Import ClaudeBrowserSession", True)
    except Exception as e:
        report("Import ClaudeBrowserSession", False, str(e))

    try:
        from jarvis.brain.claude_api import ClaudeAPIClient
        report("Import ClaudeAPIClient", True)
    except Exception as e:
        report("Import ClaudeAPIClient", False, str(e))

    try:
        from jarvis.brain.intelligence import Intelligence, _load_identity
        report("Import Intelligence", True)
    except Exception as e:
        report("Import Intelligence", False, str(e))


def test_identity_loading():
    """Test identity YAML loads correctly."""
    print("\n=== Identity Tests ===")

    from jarvis.brain.intelligence import _load_identity
    identity = _load_identity()
    report("Identity loads", len(identity) > 0)
    report("Contains Yusuf", "Yusuf" in identity)
    report("Contains Sydney", "Sydney" in identity)
    report("Contains cardiac", "cardiac" in identity.lower() or "Cardiac" in identity)
    report("Contains UNSW", "UNSW" in identity)


def test_system_prompt():
    """Test system prompt construction."""
    print("\n=== System Prompt Tests ===")

    from jarvis.brain.intelligence import Intelligence
    intel = Intelligence()

    prompt = intel._system_prompt
    report("System prompt not empty", len(prompt) > 100)
    report("Contains JARVIS identity", "JARVIS" in prompt)
    report("Contains JSON format spec", "reply" in prompt and "action" in prompt)
    report("Contains Australian English", "Australian English" in prompt)
    report("Contains cardiac priority", "cardiac" in prompt.lower())
    report("Contains AGLC4", "AGLC4" in prompt)


def test_prompt_building():
    """Test full prompt construction with context and memory."""
    print("\n=== Prompt Building Tests ===")

    from jarvis.brain.intelligence import Intelligence
    intel = Intelligence()

    # Simple message
    prompt = intel._build_full_prompt("What's IVV at?", "", "")
    report("Simple prompt", "IVV" in prompt)

    # With context
    prompt = intel._build_full_prompt(
        "What's my schedule today?",
        "Time: 2026-04-08 09:00 AEST\nMode: active",
        "Memory: Contract Law tutorial at 2pm"
    )
    report("Prompt with context", "schedule" in prompt and "09:00" in prompt)
    report("Prompt includes memory", "Contract Law" in prompt)
    report("Sections separated", "---" in prompt)


def test_browser_session_init():
    """Test browser session initializes without connecting."""
    print("\n=== Browser Session Tests ===")

    from jarvis.brain.claude_browser import ClaudeBrowserSession
    session = ClaudeBrowserSession()
    report("Session created", session is not None)
    report("Not connected initially", session.browser is None)
    report("CDP URL set", session.cdp_url == "http://localhost:9222")


def test_api_client_init():
    """Test API client initialization (without actual API call)."""
    print("\n=== API Client Tests ===")

    from jarvis.brain.claude_api import ClaudeAPIClient
    # Use dummy key — won't make actual calls
    client = ClaudeAPIClient(api_key="sk-ant-test-dummy")
    report("Client created", client is not None)
    report("Model set", client.model == "claude-sonnet-4-5-20250514")
    report("Anthropic client exists", client.client is not None)


def test_tier_detection():
    """Test that Intelligence correctly reads tier from config."""
    print("\n=== Tier Detection Tests ===")

    from jarvis.brain.intelligence import Intelligence
    intel = Intelligence()

    # Default is Tier 1
    report("Default tier is 1", intel.tier == 1)

    # Health check without initialization
    loop = asyncio.new_event_loop()
    health = loop.run_until_complete(intel.health_check())
    report("Health check returns dict", isinstance(health, dict))
    report("Reports not connected", health.get("connected") == False or "error" in health)
    loop.close()


if __name__ == "__main__":
    print("=" * 60)
    print("JARVIS Brain Tests (offline — no Chrome or API required)")
    print("=" * 60)

    test_imports()
    test_identity_loading()
    test_system_prompt()
    test_prompt_building()
    test_browser_session_init()
    test_api_client_init()
    test_tier_detection()

    print("\n" + "=" * 60)
    print(f"Results: {PASSED} passed, {FAILED} failed, {PASSED + FAILED} total")
    print("=" * 60)

    sys.exit(0 if FAILED == 0 else 1)
