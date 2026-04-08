"""
Priority Scoring — Determines urgency of incoming messages.

Priority scale: 0-100
- 100: Cardiac alerts (always top, never suppressed)
- 90-99: Emergency / STOP / KILL commands
- 70-89: Time-sensitive (calendar, deadlines, financial alerts)
- 50-69: Normal conversation, requests
- 30-49: Background tasks, knowledge queries
- 0-29: Low priority (trivia, casual)
"""
import re
from typing import Optional

CARDIAC_KEYWORDS = [
    "cardiac", "heart", "pacemaker", "defibrillator", "icd", "arrhythmia",
    "chest pain", "palpitation", "syncope", "fainting", "device alert",
    "tachycardia", "bradycardia", "afib", "a-fib", "cardiac arrest",
]

EMERGENCY_COMMANDS = ["stop", "kill", "halt", "abort", "emergency"]

TIME_SENSITIVE_KEYWORDS = [
    "urgent", "asap", "now", "immediately", "deadline", "due today",
    "meeting in", "starts in", "running late", "overdue",
]

FINANCIAL_KEYWORDS = [
    "buy", "sell", "trade", "transfer", "payment", "invoice",
    "market crash", "flash crash", "margin call",
]


def score_priority(message: str, metadata: Optional[dict] = None) -> int:
    """Score the priority of an incoming message.

    Args:
        message: The message text
        metadata: Optional metadata (source, sender, etc.)

    Returns:
        Priority score 0-100
    """
    msg_lower = message.lower().strip()

    # Priority 100: Cardiac — ALWAYS top
    for keyword in CARDIAC_KEYWORDS:
        if keyword in msg_lower:
            return 100

    # Priority 95: STOP/KILL commands
    if msg_lower in EMERGENCY_COMMANDS or msg_lower.startswith(("stop", "kill", "/stop", "/kill")):
        return 95

    # Priority 90: Emergency
    if "emergency" in msg_lower or "911" in msg_lower or "000" in msg_lower:
        return 90

    # Priority 80: Time-sensitive
    for keyword in TIME_SENSITIVE_KEYWORDS:
        if keyword in msg_lower:
            return 80

    # Priority 75: Financial actions
    for keyword in FINANCIAL_KEYWORDS:
        if keyword in msg_lower:
            return 75

    # Priority 60: Questions / requests (default for most messages)
    if msg_lower.endswith("?") or any(w in msg_lower for w in ["can you", "please", "check", "find", "what", "when", "where", "how"]):
        return 60

    # Priority 50: Statements / information sharing
    return 50


def is_stop_command(message: str) -> bool:
    """Check if a message is a STOP/KILL command.

    Only exact matches or slash commands — 'stop the music' is NOT a stop command.
    """
    msg = message.lower().strip()
    return msg in EMERGENCY_COMMANDS or msg in ("/stop", "/kill")


def is_cardiac_alert(message: str) -> bool:
    """Check if a message involves cardiac health — always priority."""
    msg_lower = message.lower()
    return any(keyword in msg_lower for keyword in CARDIAC_KEYWORDS)
