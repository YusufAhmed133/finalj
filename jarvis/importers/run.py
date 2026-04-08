"""CLI entry point for running imports."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from jarvis.memory.spine import MemorySpine
from jarvis.importers.claude_export import import_claude_export
from jarvis.importers.google_calendar import import_ics
from jarvis.importers.generic import import_file, import_directory
from jarvis.utils.logger import get_logger

log = get_logger("importers.run")


def main():
    if len(sys.argv) < 3:
        print("Usage: python -m jarvis.importers.run <type> <path>")
        print("Types: claude, calendar, file, directory")
        print("Examples:")
        print("  python -m jarvis.importers.run claude data/imports/raw/conversations.json")
        print("  python -m jarvis.importers.run calendar data/imports/raw/calendar.ics")
        print("  python -m jarvis.importers.run file data/imports/raw/document.pdf")
        print("  python -m jarvis.importers.run directory data/imports/raw/")
        sys.exit(1)

    import_type = sys.argv[1]
    path = Path(sys.argv[2])

    if not path.exists():
        print(f"Error: {path} does not exist")
        sys.exit(1)

    spine = MemorySpine()

    try:
        if import_type == "claude":
            stats = import_claude_export(path, spine)
        elif import_type == "calendar":
            stats = import_ics(path, spine)
        elif import_type == "file":
            stats = import_file(path, spine)
        elif import_type == "directory":
            stats = import_directory(path, spine)
        else:
            print(f"Unknown import type: {import_type}")
            sys.exit(1)

        print(f"Import complete: {stats}")
        print(f"Total memories in database: {spine.count()}")
    finally:
        spine.close()


if __name__ == "__main__":
    main()
