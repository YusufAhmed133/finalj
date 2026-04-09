"""
Instant Mac Control — Sub-second. No LLM.

Strips filler ("yo", "can you", "please") then pattern matches.
Falls through to Claude only if no pattern matches.
"""
import re
import subprocess
import urllib.parse
from pathlib import Path
from jarvis.utils.logger import get_logger

log = get_logger("agents.instant_mac")

FILLER = [
    r"^(?:yo|hey|hi|ok|okay|oi|ey|so|um|uh)\s+",
    r"^(?:jarvis|j\.a\.r\.v\.i\.s)\s*[,]?\s*",
    r"^(?:can you|could you|would you|will you|please|pls)\s+",
    r"^(?:i want you to|i need you to|go ahead and|i want to)\s+",
    r"^(?:can you please|could you please)\s+",
    r"\s+(?:please|pls|thanks|thank you|for me|now|right now)$",
]


def _strip(msg):
    msg = msg.lower().strip()
    changed = True
    while changed:
        changed = False
        for p in FILLER:
            new = re.sub(p, "", msg).strip()
            if new != msg:
                msg = new
                changed = True
    return msg


def _run(cmd, timeout=5):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout.strip() or "Done"
    except Exception as e:
        return str(e)


def _osa(script):
    return _run(["osascript", "-e", script])


APP_MAP = {
    "spotify": "Spotify", "chrome": "Google Chrome", "google chrome": "Google Chrome",
    "safari": "Safari", "finder": "Finder", "terminal": "Terminal",
    "notes": "Notes", "messages": "Messages", "mail": "Mail",
    "calendar": "Calendar", "photos": "Photos", "music": "Music",
    "maps": "Maps", "settings": "System Settings", "system settings": "System Settings",
    "vscode": "Visual Studio Code", "vs code": "Visual Studio Code",
    "code": "Visual Studio Code", "slack": "Slack", "discord": "Discord",
    "zoom": "Zoom", "notion": "Notion", "whatsapp": "WhatsApp",
    "telegram": "Telegram", "preview": "Preview", "calculator": "Calculator",
    "cursor": "Cursor", "word": "Microsoft Word", "excel": "Microsoft Excel",
}

WEB_FALLBACK = {
    "spotify": "https://open.spotify.com", "youtube": "https://youtube.com",
    "gmail": "https://mail.google.com", "google docs": "https://docs.google.com",
    "netflix": "https://netflix.com", "twitter": "https://x.com",
    "reddit": "https://reddit.com", "chatgpt": "https://chat.openai.com",
    "claude": "https://claude.ai", "instagram": "https://instagram.com",
    "facebook": "https://facebook.com", "linkedin": "https://linkedin.com",
    "whatsapp": "https://web.whatsapp.com", "telegram": "https://web.telegram.org",
}


def try_instant_command(message):
    msg = _strip(message)

    # ── Open App ──
    m = re.match(r"(?:open|launch|start|run|fire up|bring up|pull up)\s+(.+?)(?:\s+app)?$", msg)
    if m:
        app = re.sub(r"\s+(?:for me|please|now|up)$", "", m.group(1)).strip()
        app_name = APP_MAP.get(app, app.title())
        result = _run(["open", "-a", app_name])
        if "unable" in result.lower() or "can't" in result.lower() or "error" in result.lower():
            web = WEB_FALLBACK.get(app)
            if web:
                _run(["open", web])
                log.info(f"Web fallback: {web}")
                return f"Opening {app_name} in browser, sir."
            return f"Can't find {app_name}, sir."
        log.info(f"Opened: {app_name}")
        return f"{app_name} is open, sir."

    # ── URL ──
    m = re.match(r"(?:go to|open|navigate to|visit)\s+(https?://\S+)", msg)
    if m:
        _run(["open", m.group(1)]); return f"Opening {m.group(1)}."
    m = re.match(r"(?:go to|open|navigate to|visit)\s+(\S+\.\S+)", msg)
    if m:
        url = m.group(1) if m.group(1).startswith("http") else "https://" + m.group(1)
        _run(["open", url]); return f"Opening {url}."

    # ── Search ──
    m = re.match(r"(?:search for|search|google|look up)\s+(.+)", msg)
    if m:
        _run(["open", f"https://www.google.com/search?q={urllib.parse.quote_plus(m.group(1))}"])
        return f"Searching for {m.group(1)}, sir."

    # ── Music ──
    if msg in ("play", "play music", "resume", "play some music", "resume music"):
        _osa('tell application "Spotify" to play'); return "Playing, sir."
    if msg in ("pause", "pause music", "stop music", "stop playing", "stop"):
        _osa('tell application "Spotify" to pause'); return "Paused."
    if msg in ("next", "next song", "skip", "skip song", "next track"):
        _osa('tell application "Spotify" to next track'); return "Next track."
    if msg in ("previous", "previous song", "go back", "last song"):
        _osa('tell application "Spotify" to previous track'); return "Previous track."
    m = re.match(r"play\s+(.+?)(?:\s+on spotify)?$", msg)
    if m and msg not in ("play music", "play some music"):
        _run(["open", f"spotify:search:{urllib.parse.quote(m.group(1))}"])
        return f"Playing {m.group(1)}."

    # ── Volume ──
    if msg in ("volume up", "louder", "turn it up", "turn up the volume", "turn up volume"):
        _osa("set volume output volume ((output volume of (get volume settings)) + 15)"); return "Volume up."
    if msg in ("volume down", "quieter", "turn it down", "turn down the volume", "turn down volume"):
        _osa("set volume output volume ((output volume of (get volume settings)) - 15)"); return "Volume down."
    if msg in ("mute", "mute volume", "silence"):
        _osa("set volume output muted true"); return "Muted."
    if msg in ("unmute", "unmute volume"):
        _osa("set volume output muted false"); return "Unmuted."
    m = re.match(r"(?:set )?volume (?:to )?(\d+)", msg)
    if m:
        _osa(f"set volume output volume {min(100, max(0, int(m.group(1))))}"); return f"Volume {m.group(1)}."

    # ── Close ──
    m = re.match(r"(?:close|quit|exit|kill)\s+(.+)", msg)
    if m:
        _osa(f'tell application "{m.group(1).strip().title()}" to quit'); return f"Closed {m.group(1).title()}."

    # ── Screenshot ──
    if "screenshot" in msg:
        _run(["screencapture", "-x", "/tmp/screenshot.png"]); return "Screenshot taken."

    # ── Time/Date ──
    if any(x in msg for x in ["what time", "whats the time", "the time"]):
        from datetime import datetime; return datetime.now().strftime("It's %I:%M %p, sir.")
    if any(x in msg for x in ["what date", "whats the date", "the date", "what day"]):
        from datetime import datetime; return datetime.now().strftime("%A, %d %B %Y.")

    # ── Dark/Light ──
    if "dark mode" in msg:
        _osa('tell application "System Events" to tell appearance preferences to set dark mode to true'); return "Dark mode on."
    if "light mode" in msg:
        _osa('tell application "System Events" to tell appearance preferences to set dark mode to false'); return "Light mode on."

    # ── Lock ──
    if msg in ("lock", "lock screen", "lock the screen"):
        _run(["pmset", "displaysleepnow"]); return "Locking."

    # ── Folders ──
    if "downloads" in msg and ("open" in msg or "go to" in msg):
        _run(["open", str(Path.home() / "Downloads")]); return "Downloads open."
    if "desktop" in msg and ("open" in msg or "go to" in msg):
        _run(["open", str(Path.home() / "Desktop")]); return "Desktop open."
    if "documents" in msg and ("open" in msg or "go to" in msg):
        _run(["open", str(Path.home() / "Documents")]); return "Documents open."

    return None


def is_instant_command(message):
    msg = _strip(message)
    return any(re.match(p, msg) for p in [
        r"(?:open|launch|start|run|fire up|bring up|pull up)\s+",
        r"(?:go to|navigate to|visit)\s+", r"(?:search for|search|google|look up)\s+",
        r"(?:close|quit|exit|kill)\s+", r"(?:play|pause|next|skip|previous|stop|resume)",
        r"(?:volume|mute|unmute|louder|quieter)", r"screenshot",
        r"(?:what time|whats the time|what date|whats the date)",
        r"(?:dark mode|light mode|lock)",
    ])
