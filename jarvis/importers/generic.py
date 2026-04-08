"""
Generic Document Importer.

Imports PDF, CSV, JSON, TXT, and MD files into memory.
Large documents are chunked into manageable pieces.
"""
import csv
import json
import io
from pathlib import Path
from typing import Optional

from jarvis.memory.spine import MemorySpine
from jarvis.utils.logger import get_logger

log = get_logger("importers.generic")

CHUNK_SIZE = 3000  # characters per memory chunk
SUPPORTED_EXTENSIONS = {".pdf", ".csv", ".json", ".txt", ".md", ".markdown"}


def import_file(
    file_path: Path,
    spine: MemorySpine,
) -> dict:
    """Import a generic document into memory.

    Args:
        file_path: Path to the document
        spine: Memory spine instance

    Returns:
        dict with import stats
    """
    ext = file_path.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {ext}. Supported: {SUPPORTED_EXTENSIONS}")

    log.info(f"Importing {ext} file: {file_path}")

    if ext == ".pdf":
        return _import_pdf(file_path, spine)
    elif ext == ".csv":
        return _import_csv(file_path, spine)
    elif ext == ".json":
        return _import_json(file_path, spine)
    else:
        return _import_text(file_path, spine)


def _chunk_text(text: str, chunk_size: int = CHUNK_SIZE) -> list:
    """Split text into chunks, trying to break at paragraph boundaries."""
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    while text:
        if len(text) <= chunk_size:
            chunks.append(text)
            break

        # Try to break at paragraph
        break_point = text.rfind("\n\n", 0, chunk_size)
        if break_point == -1:
            # Try to break at sentence
            break_point = text.rfind(". ", 0, chunk_size)
        if break_point == -1:
            # Try to break at word
            break_point = text.rfind(" ", 0, chunk_size)
        if break_point == -1:
            break_point = chunk_size

        chunks.append(text[:break_point + 1].strip())
        text = text[break_point + 1:].strip()

    return chunks


def _import_pdf(file_path: Path, spine: MemorySpine) -> dict:
    """Import a PDF file."""
    import pdfplumber

    stats = {"pages": 0, "memories_created": 0}
    text_parts = []

    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
                stats["pages"] += 1

    full_text = "\n\n".join(text_parts)
    chunks = _chunk_text(full_text)

    for i, chunk in enumerate(chunks):
        spine.store(
            content=chunk,
            type="import_document",
            source=f"pdf:{file_path.name}",
            metadata={
                "filename": file_path.name,
                "chunk": i + 1,
                "total_chunks": len(chunks),
                "total_pages": stats["pages"],
            },
        )
        stats["memories_created"] += 1

    log.info(f"PDF import complete: {stats}")
    return stats


def _import_csv(file_path: Path, spine: MemorySpine) -> dict:
    """Import a CSV file — each row or group of rows becomes a memory."""
    stats = {"rows": 0, "memories_created": 0}

    with open(file_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    stats["rows"] = len(rows)

    # Group rows into chunks
    chunk_size = 20  # rows per memory
    for i in range(0, len(rows), chunk_size):
        batch = rows[i:i + chunk_size]
        lines = []
        for row in batch:
            lines.append(" | ".join(f"{k}: {v}" for k, v in row.items() if v))
        content = f"Data from {file_path.name} (rows {i+1}-{i+len(batch)}):\n" + "\n".join(lines)

        spine.store(
            content=content[:5000],
            type="import_document",
            source=f"csv:{file_path.name}",
            metadata={
                "filename": file_path.name,
                "row_start": i + 1,
                "row_end": i + len(batch),
                "total_rows": len(rows),
            },
        )
        stats["memories_created"] += 1

    log.info(f"CSV import complete: {stats}")
    return stats


def _import_json(file_path: Path, spine: MemorySpine) -> dict:
    """Import a JSON file."""
    stats = {"memories_created": 0}

    data = json.loads(file_path.read_text())
    text = json.dumps(data, indent=2)
    chunks = _chunk_text(text)

    for i, chunk in enumerate(chunks):
        spine.store(
            content=chunk,
            type="import_document",
            source=f"json:{file_path.name}",
            metadata={
                "filename": file_path.name,
                "chunk": i + 1,
                "total_chunks": len(chunks),
            },
        )
        stats["memories_created"] += 1

    log.info(f"JSON import complete: {stats}")
    return stats


def _import_text(file_path: Path, spine: MemorySpine) -> dict:
    """Import a text or markdown file."""
    stats = {"memories_created": 0}

    text = file_path.read_text(encoding="utf-8")
    chunks = _chunk_text(text)

    for i, chunk in enumerate(chunks):
        spine.store(
            content=chunk,
            type="import_document",
            source=f"text:{file_path.name}",
            metadata={
                "filename": file_path.name,
                "chunk": i + 1,
                "total_chunks": len(chunks),
            },
        )
        stats["memories_created"] += 1

    log.info(f"Text import complete: {stats}")
    return stats


def import_directory(
    dir_path: Path,
    spine: MemorySpine,
) -> dict:
    """Import all supported files from a directory.

    Args:
        dir_path: Directory containing files to import
        spine: Memory spine instance

    Returns:
        Aggregate import stats
    """
    log.info(f"Importing all files from {dir_path}")
    total_stats = {"files": 0, "memories_created": 0, "errors": []}

    for file_path in sorted(dir_path.iterdir()):
        if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        try:
            stats = import_file(file_path, spine)
            total_stats["files"] += 1
            total_stats["memories_created"] += stats.get("memories_created", 0)
        except Exception as e:
            log.error(f"Failed to import {file_path}: {e}")
            total_stats["errors"].append({"file": str(file_path), "error": str(e)})

    log.info(f"Directory import complete: {total_stats}")
    return total_stats
