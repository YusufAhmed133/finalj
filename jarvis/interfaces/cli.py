"""Debug CLI interface for JARVIS — testing only."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from jarvis.main import main

if __name__ == "__main__":
    sys.argv.append("--cli")
    main()
