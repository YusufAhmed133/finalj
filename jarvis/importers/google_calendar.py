"""
Google Calendar .ics Importer.

Imports events from Google Calendar export (.ics files).
Each event becomes a memory entry with date, location, and attendee entities.
"""
from pathlib import Path
from datetime import datetime
from typing import Optional

from icalendar import Calendar
from jarvis.memory.spine import MemorySpine
from jarvis.utils.logger import get_logger

log = get_logger("importers.gcal")


def import_ics(
    file_path: Path,
    spine: MemorySpine,
    max_events: Optional[int] = None,
) -> dict:
    """Import Google Calendar .ics file into memory.

    Args:
        file_path: Path to .ics file
        spine: Memory spine instance
        max_events: Limit number of events (None = all)

    Returns:
        dict with import stats
    """
    log.info(f"Importing calendar from {file_path}")

    cal = Calendar.from_ical(file_path.read_bytes())
    stats = {"events": 0, "memories_created": 0}

    events = []
    for component in cal.walk():
        if component.name == "VEVENT":
            events.append(component)

    if max_events:
        events = events[:max_events]

    for event in events:
        summary = str(event.get("SUMMARY", "Untitled Event"))
        dtstart = event.get("DTSTART")
        dtend = event.get("DTEND")
        location = str(event.get("LOCATION", ""))
        description = str(event.get("DESCRIPTION", ""))

        # Parse dates
        start_str = ""
        if dtstart:
            dt = dtstart.dt
            if isinstance(dt, datetime):
                start_str = dt.strftime("%Y-%m-%d %H:%M")
            else:
                start_str = str(dt)

        end_str = ""
        if dtend:
            dt = dtend.dt
            if isinstance(dt, datetime):
                end_str = dt.strftime("%Y-%m-%d %H:%M")
            else:
                end_str = str(dt)

        # Extract attendees
        attendees = []
        attendee_list = event.get("ATTENDEE")
        if attendee_list:
            if not isinstance(attendee_list, list):
                attendee_list = [attendee_list]
            for attendee in attendee_list:
                name = attendee.params.get("CN", str(attendee).replace("mailto:", ""))
                attendees.append(str(name))

        # Build content
        parts = [f"Event: {summary}"]
        if start_str:
            parts.append(f"When: {start_str}" + (f" to {end_str}" if end_str else ""))
        if location:
            parts.append(f"Where: {location}")
        if attendees:
            parts.append(f"With: {', '.join(attendees[:10])}")
        if description:
            parts.append(f"Details: {description[:500]}")

        content = "\n".join(parts)

        entities = [summary]
        if attendees:
            entities.extend(attendees[:5])
        if location:
            entities.append(location)

        spine.store(
            content=content,
            type="import_calendar",
            source="google_calendar",
            entities=entities,
            metadata={
                "event_name": summary,
                "start": start_str,
                "end": end_str,
                "location": location,
                "attendee_count": len(attendees),
            },
        )
        stats["events"] += 1
        stats["memories_created"] += 1

    log.info(f"Calendar import complete: {stats}")
    return stats
