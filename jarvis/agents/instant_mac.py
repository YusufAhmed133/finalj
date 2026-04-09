"""
Instant Mac Control — Sub-second. No LLM.

1. Strip filler ("yo", "can you", "please", "so it is in front of me")
2. Extract clean app name / command
3. Execute via osascript (activate = bring to front)
4. Verify it worked
"""
import re
import subprocess
import urllib.parse
from pathlib import Path
from jarvis.utils.logger import get_logger

log = get_logger("agents.instant_mac")

# ── Filler stripping ──
FILLER_PRE = [
    r"^(?:yo|hey|hi|ok|okay|oi|ey|so|um|uh|right)\s+",
    r"^(?:jarvis|j\.a\.r\.v\.i\.s)\s*[,]?\s*",
    r"^(?:can you|could you|would you|will you|please|pls)\s+",
    r"^(?:i want you to|i need you to|go ahead and|i want to)\s+",
    r"^(?:can you please|could you please)\s+",
]
FILLER_POST = [
    r"\s+(?:please|pls|thanks|thank you|for me|now|right now)$",
    r"\s+(?:so it is|so it's|and put it|and bring it|and have it).*$",
    r"\s+(?:on my desktop|on my screen|in front of me|on the screen).*$",
    r"\s+(?:and make it|so i can see it|so i can use it).*$",
]


def _strip(msg):
    msg = msg.lower().strip()
    # Pre-filler
    changed = True
    while changed:
        changed = False
        for p in FILLER_PRE:
            new = re.sub(p, "", msg).strip()
            if new != msg: msg = new; changed = True
    # Post-filler
    for p in FILLER_POST:
        msg = re.sub(p, "", msg).strip()
    return msg


def _run(cmd, timeout=5):
    """Run command, return (stdout+stderr, success)."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        output = (r.stdout.strip() + " " + r.stderr.strip()).strip()
        return output, r.returncode == 0
    except Exception as e:
        return str(e), False


def _osa(script):
    out, ok = _run(["osascript", "-e", script])
    return out


# ── App name mapping ──
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
    "arc": "Arc", "brave": "Brave Browser", "firefox": "Firefox",
    "iterm": "iTerm", "warp": "Warp",
}

WEB_FALLBACK = {
    "spotify": "https://open.spotify.com", "youtube": "https://youtube.com",
    "gmail": "https://mail.google.com", "google docs": "https://docs.google.com",
    "netflix": "https://netflix.com", "twitter": "https://x.com",
    "reddit": "https://reddit.com", "chatgpt": "https://chat.openai.com",
    "claude": "https://claude.ai", "instagram": "https://instagram.com",
    "facebook": "https://facebook.com", "linkedin": "https://linkedin.com",
    "whatsapp web": "https://web.whatsapp.com",
}


def _find_installed_app(name):
    """Try to find an installed app by fuzzy matching against mdfind."""
    try:
        out, ok = _run(["mdfind", 'kMDItemKind == "Application"'], timeout=5)
        if not ok:
            return None
        import os, difflib
        apps = {}
        for path in out.split('\n'):
            app = os.path.basename(path).replace('.app', '')
            apps[app.lower()] = app
        # Exact match first
        if name in apps:
            return apps[name]
        # Fuzzy match
        matches = difflib.get_close_matches(name, apps.keys(), n=1, cutoff=0.85)
        if matches:
            return apps[matches[0]]
    except Exception:
        pass
    return None


def _open_app(app_key):
    """Open app and bring to foreground. Returns (message, success)."""
    # Check known map first, then mdfind, then .title() fallback
    app_name = APP_MAP.get(app_key)
    if not app_name:
        app_name = _find_installed_app(app_key)
    if not app_name:
        app_name = app_key.title()

    # Use AppleScript to open AND activate (bring to front)
    script = f'''
    tell application "{app_name}"
        activate
    end tell
    '''
    out, ok = _run(["osascript", "-e", script])

    if ok:
        log.info(f"Opened and activated: {app_name}")
        return f"Done, sir. {app_name} is up.", True

    # App not found by AppleScript — try `open -a` as fallback
    out2, ok2 = _run(["open", "-a", app_name])
    if ok2:
        # Also activate to bring to front
        _run(["osascript", "-e", f'tell application "{app_name}" to activate'])
        log.info(f"Opened via open -a: {app_name}")
        return f"Done, sir. {app_name} is up.", True

    # Try web fallback
    web = WEB_FALLBACK.get(app_key)
    if web:
        _run(["open", web])
        log.info(f"Web fallback: {web}")
        return f"Opening {app_name} in browser, sir.", True

    return f"Can't find {app_name} on this Mac, sir.", False


def _extract_app_name(text):
    """Extract just the app name from natural language.
    'spotify so it is in front of me on my desktop' → 'spotify'
    """
    # Known app names — check longest first
    text_lower = text.lower().strip()
    for key in sorted(APP_MAP.keys(), key=len, reverse=True):
        if text_lower.startswith(key):
            return key
    for key in sorted(WEB_FALLBACK.keys(), key=len, reverse=True):
        if text_lower.startswith(key):
            return key
    # Strip articles
    text_lower = re.sub(r"^(?:the|a|an|my)\s+", "", text_lower)
    # Take first word(s) before common stop words
    stop = ["so", "and", "on", "in", "for", "to", "that", "which", "then"]
    words = text_lower.split()
    name_words = []
    for w in words:
        if w in stop:
            break
        name_words.append(w)
    return " ".join(name_words) if name_words else text_lower


def try_instant_command(message):
    """Match message to instant Mac command. Returns response or None."""
    msg = _strip(message)

    # ── Open App ──
    m = re.match(r"(?:open|launch|start|run|fire up|bring up|pull up)\s+(.+)", msg)
    if m:
        raw_app = m.group(1).strip()
        app_key = _extract_app_name(raw_app)
        reply, ok = _open_app(app_key)
        return reply

    # ── URL ──
    m = re.match(r"(?:go to|open|navigate to|visit)\s+(https?://\S+)", msg)
    if m:
        _run(["open", m.group(1)]); return f"Opening {m.group(1)}."
    m = re.match(r"(?:go to|navigate to|visit)\s+(\S+\.\S+)", msg)
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
        app_key = _extract_app_name(m.group(1))
        app_name = APP_MAP.get(app_key, app_key.title())
        _osa(f'tell application "{app_name}" to quit'); return f"Closed {app_name}."

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
    for folder in ["downloads", "desktop", "documents"]:
        if folder in msg and any(x in msg for x in ["open", "go to", "show"]):
            _run(["open", str(Path.home() / folder.title())]); return f"{folder.title()} open."

    return None


def is_instant_command(message):
    msg = _strip(message)
    return any(re.match(p, msg) for p in [
        r"(?:open|launch|start|run|fire up|bring up|pull up)\s+",
        r"(?:go to|navigate to|visit)\s+", r"(?:search for|search|google|look up)\s+",
        r"(?:close|quit|exit|kill)\s+", r"(?:play|pause|next|skip|previous|stop|resume)",
        r"(?:volume|mute|unmute|louder|quieter)", r"screenshot",
        r"(?:what time|whats the time|what date|whats the date|what day)",
        r"(?:dark mode|light mode|lock)",
    ])
