"""Tests for JARVIS data importers."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from jarvis.memory.spine import MemorySpine
from jarvis.importers.claude_export import import_claude_export
from jarvis.importers.google_calendar import import_ics
from jarvis.importers.generic import import_file, import_directory, _chunk_text

TEST_DB = Path("/tmp/jarvis_test_importers.db")
TEST_DIR = Path("/tmp/jarvis_test_imports")

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


def cleanup():
    for p in [TEST_DB]:
        if p.exists():
            p.unlink()
        for suffix in ["-wal", "-shm"]:
            wal = Path(str(p) + suffix)
            if wal.exists():
                wal.unlink()
    if TEST_DIR.exists():
        import shutil
        shutil.rmtree(TEST_DIR)


def setup_test_files():
    """Create sample test files."""
    TEST_DIR.mkdir(parents=True, exist_ok=True)

    # Claude export
    claude_data = [
        {
            "uuid": "conv-1",
            "name": "Discussion about IVV investing strategy",
            "created_at": "2026-01-15T10:30:00Z",
            "chat_messages": [
                {"sender": "human", "text": "What's the best DCA strategy for IVV?", "created_at": "2026-01-15T10:30:00Z"},
                {"sender": "assistant", "text": "For IVV DCA, fortnightly contributions work well because they smooth out volatility better than monthly.", "created_at": "2026-01-15T10:30:05Z"},
                {"sender": "human", "text": "How much should I invest per fortnight to reach $1M by 30?", "created_at": "2026-01-15T10:31:00Z"},
                {"sender": "assistant", "text": "Assuming 10% geometric mean return, you'd need roughly $1,200 per fortnight starting now.", "created_at": "2026-01-15T10:31:05Z"},
            ]
        },
        {
            "uuid": "conv-2",
            "name": "UNSW Contract Law exam prep",
            "created_at": "2026-02-20T14:00:00Z",
            "chat_messages": [
                {"sender": "human", "text": "Explain consideration in Australian contract law", "created_at": "2026-02-20T14:00:00Z"},
                {"sender": "assistant", "text": "Consideration must be sufficient but need not be adequate. Key case: Chappell & Co v Nestle.", "created_at": "2026-02-20T14:00:05Z"},
            ]
        },
        {
            "uuid": "conv-3",
            "name": "Empty conversation",
            "created_at": "2026-03-01T09:00:00Z",
            "chat_messages": []
        }
    ]
    (TEST_DIR / "conversations.json").write_text(json.dumps(claude_data))

    # ICS calendar
    ics_content = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Google Inc//Google Calendar 70.9054//EN
BEGIN:VEVENT
DTSTART:20260415T090000Z
DTEND:20260415T100000Z
SUMMARY:Contract Law Tutorial
LOCATION:UNSW Law Building Room 203
DESCRIPTION:Week 7 tutorial - consideration and estoppel
ATTENDEE;CN=Prof. Smith:mailto:smith@unsw.edu.au
ATTENDEE;CN=Yusuf Ahmed:mailto:yusuf@student.unsw.edu.au
END:VEVENT
BEGIN:VEVENT
DTSTART:20260416T140000Z
DTEND:20260416T150000Z
SUMMARY:Mending Broken Hearts Meeting
LOCATION:UNSW Engineering Lab
DESCRIPTION:TAH prototype review
END:VEVENT
BEGIN:VEVENT
DTSTART:20260420
SUMMARY:IVV DCA Day
DESCRIPTION:Fortnightly investment
END:VEVENT
END:VCALENDAR"""
    (TEST_DIR / "calendar.ics").write_bytes(ics_content.encode())

    # Text file
    (TEST_DIR / "notes.txt").write_text(
        "Study notes for Contract Law\n\n"
        "Key cases:\n"
        "1. Carlill v Carbolic Smoke Ball Co [1893]\n"
        "2. Chappell & Co v Nestle [1960]\n"
        "3. Australian Woollen Mills v Commonwealth (1954)\n\n"
        "Important: Consideration must move from the promisee."
    )

    # CSV file
    (TEST_DIR / "investments.csv").write_text(
        "date,asset,units,price,total\n"
        "2026-01-15,IVV,2.5,680.50,1701.25\n"
        "2026-01-29,IVV,2.3,695.20,1598.96\n"
        "2026-02-12,IVV,2.4,687.30,1649.52\n"
    )

    # Markdown file
    (TEST_DIR / "goals.md").write_text(
        "# 2026 Goals\n\n"
        "## Academic\n"
        "- WAM target: 85\n"
        "- Focus subjects: Contract Law, Corporate Finance\n\n"
        "## Financial\n"
        "- $50,000 invested in IVV by December\n"
        "- Start tracking expenses\n\n"
        "## Health\n"
        "- Cardiac checkup in March\n"
        "- Gym 4x per week\n"
    )

    # JSON file
    (TEST_DIR / "config.json").write_text(json.dumps({
        "project": "JARVIS",
        "version": "3.0",
        "features": ["memory", "telegram", "computer_use"]
    }))


def test_claude_import():
    print("\n=== Claude Export Importer Tests ===")
    cleanup()
    setup_test_files()
    spine = MemorySpine(db_path=TEST_DB)

    stats = import_claude_export(TEST_DIR / "conversations.json", spine)
    report("Import runs without error", True)
    report("Conversations imported", stats["conversations"] == 2, f"expected 2, got {stats['conversations']}")
    report("Empty conversation skipped", stats["conversations"] == 2)
    report("Messages counted", stats["messages"] == 6, f"expected 6, got {stats['messages']}")

    # Verify searchable
    results = spine.search_text("IVV DCA strategy")
    report("FTS search finds imported conversation", len(results) >= 1)

    results = spine.search_text("consideration contract law")
    report("FTS search finds law conversation", len(results) >= 1)

    # Verify metadata
    recent = spine.get_recent(hours=1, type="import_claude")
    report("Type tagged correctly", len(recent) == 2)
    report("Metadata preserved", recent[0]["metadata"] is not None)

    spine.close()


def test_calendar_import():
    print("\n=== Calendar Importer Tests ===")
    cleanup()
    setup_test_files()
    spine = MemorySpine(db_path=TEST_DB)

    stats = import_ics(TEST_DIR / "calendar.ics", spine)
    report("Import runs without error", True)
    report("Events imported", stats["events"] == 3, f"expected 3, got {stats['events']}")

    # Verify searchable
    results = spine.search_text("Contract Law Tutorial")
    report("FTS finds event by name", len(results) >= 1)

    results = spine.search_text("Prof Smith")
    report("FTS finds event by attendee", len(results) >= 1)

    # Verify all-day event works
    results = spine.search_text("IVV DCA Day")
    report("All-day event imported", len(results) >= 1)

    spine.close()


def test_generic_importers():
    print("\n=== Generic Importer Tests ===")
    cleanup()
    setup_test_files()
    spine = MemorySpine(db_path=TEST_DB)

    # Text file
    stats = import_file(TEST_DIR / "notes.txt", spine)
    report("Text import", stats["memories_created"] >= 1)

    # CSV file
    stats = import_file(TEST_DIR / "investments.csv", spine)
    report("CSV import", stats["memories_created"] >= 1)

    # Markdown file
    stats = import_file(TEST_DIR / "goals.md", spine)
    report("Markdown import", stats["memories_created"] >= 1)

    # JSON file
    stats = import_file(TEST_DIR / "config.json", spine)
    report("JSON import", stats["memories_created"] >= 1)

    # Search across all imports
    results = spine.search_text("Carlill Carbolic")
    report("Cross-import FTS (text)", len(results) >= 1)

    results = spine.search_text("IVV investment")
    report("Cross-import FTS (csv)", len(results) >= 1)

    results = spine.search_text("WAM target 85")
    report("Cross-import FTS (markdown)", len(results) >= 1)

    spine.close()


def test_directory_import():
    print("\n=== Directory Import Tests ===")
    cleanup()
    setup_test_files()
    spine = MemorySpine(db_path=TEST_DB)

    stats = import_directory(TEST_DIR, spine)
    report("Directory import runs", stats["files"] >= 4, f"imported {stats['files']} files")
    report("No errors", len(stats["errors"]) == 0, f"errors: {stats['errors']}")
    report("Memories created", stats["memories_created"] >= 4)

    total = spine.count()
    report("Total memories in DB", total >= 4, f"got {total}")

    spine.close()


def test_chunking():
    print("\n=== Text Chunking Tests ===")

    # Short text — no chunking
    chunks = _chunk_text("Hello world", chunk_size=100)
    report("Short text no chunking", len(chunks) == 1)

    # Long text — chunked at paragraph
    long_text = "First paragraph about IVV investing.\n\nSecond paragraph about law studies.\n\nThird paragraph about health."
    chunks = _chunk_text(long_text, chunk_size=60)
    report("Paragraph-boundary chunking", len(chunks) >= 2)

    # Very long text
    very_long = "Word " * 1000
    chunks = _chunk_text(very_long, chunk_size=100)
    report("Very long text chunked", len(chunks) > 10)
    report("All chunks under limit", all(len(c) <= 105 for c in chunks))  # slight tolerance


if __name__ == "__main__":
    print("=" * 60)
    print("JARVIS Importer Tests")
    print("=" * 60)

    test_chunking()
    test_claude_import()
    test_calendar_import()
    test_generic_importers()
    test_directory_import()

    print("\n" + "=" * 60)
    print(f"Results: {PASSED} passed, {FAILED} failed, {PASSED + FAILED} total")
    print("=" * 60)

    cleanup()
    sys.exit(0 if FAILED == 0 else 1)
