"""
Instant Mac Control — No LLM needed. Sub-second execution.

Pattern-matches natural language to direct macOS commands.
Falls through to Claude only if no pattern matches.
"""
import re
import subprocess
import urllib.parse
from jarvis.utils.logger import get_logger

log = get_logger("agents.mac_control")


def _run(cmd: list, timeout: int = 5) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip() or r.stderr.strip() or "Done"
    except subprocess.TimeoutExpired:
        return "Timed out"
    except Exception as e:
        return str(e)


def _osascript(script: str) -> str:
    return _run(["osascript", "-e", script])


def try_instant_command(message: str):
    """Try to match message to an instant Mac command.
    Returns response string if handled, None if should go to Claude.
    """
    msg = message.lower().strip()
    # Strip "jarvis" prefix
    for prefix in ["jarvis ", "hey jarvis ", "j.a.r.v.i.s ", "jarvis, "]:
        if msg.startswith(prefix):
            msg = msg[len(prefix):]

    # ─── Open App ────────────────────────────────────
    m = re.match(r"(?:open|launch|start|run)\s+(.+?)(?:\s+app)?$", msg)
    if m:
        app = m.group(1).strip()
        # Common app name mapping
        app_map = {
            "spotify": "Spotify", "chrome": "Google Chrome", "safari": "Safari",
            "finder": "Finder", "terminal": "Terminal", "notes": "Notes",
            "messages": "Messages", "mail": "Mail", "calendar": "Calendar",
            "photos": "Photos", "music": "Music", "maps": "Maps",
            "settings": "System Preferences", "system preferences": "System Preferences",
            "system settings": "System Settings", "vscode": "Visual Studio Code",
            "vs code": "Visual Studio Code", "code": "Visual Studio Code",
            "slack": "Slack", "discord": "Discord", "zoom": "Zoom",
            "notion": "Notion", "word": "Microsoft Word", "excel": "Microsoft Excel",
            "pages": "Pages", "numbers": "Numbers", "keynote": "Keynote",
            "preview": "Preview", "activity monitor": "Activity Monitor",
            "whatsapp": "WhatsApp", "telegram": "Telegram",
        }
        app_name = app_map.get(app, app.title())
        result = _run(["open", "-a", app_name])
        if "unable to find" in result.lower():
            return f"Couldn't find {app_name} on this Mac, sir."
        log.info(f"Opened: {app_name}")
        return f"{app_name} is open, sir."

    # ─── Open URL / Go To ────────────────────────────
    m = re.match(r"(?:go to|open|navigate to|visit)\s+(https?://\S+)", msg)
    if m:
        url = m.group(1)
        _run(["open", url])
        log.info(f"Opened URL: {url}")
        return f"Opening {url}."

    m = re.match(r"(?:go to|open|navigate to|visit)\s+(\S+\.\S+)", msg)
    if m:
        domain = m.group(1)
        if not domain.startswith("http"):
            domain = "https://" + domain
        _run(["open", domain])
        log.info(f"Opened: {domain}")
        return f"Opening {domain}."

    # ─── Search ──────────────────────────────────────
    m = re.match(r"(?:search for|search|google|look up)\s+(.+)", msg)
    if m:
        query = urllib.parse.quote_plus(m.group(1))
        _run(["open", f"https://www.google.com/search?q={query}"])
        log.info(f"Searching: {m.group(1)}")
        return f"Searching for {m.group(1)}, sir."

    # ─── Music Control ───────────────────────────────
    if msg in ("play", "play music", "resume", "resume music"):
        _osascript('tell application "Spotify" to play')
        return "Playing, sir."

    if msg in ("pause", "pause music", "stop music", "stop"):
        _osascript('tell application "Spotify" to pause')
        return "Paused."

    if msg in ("next", "next song", "skip", "next track"):
        _osascript('tell application "Spotify" to next track')
        return "Skipping to next track."

    if msg in ("previous", "previous song", "prev", "previous track", "go back"):
        _osascript('tell application "Spotify" to previous track')
        return "Going back."

    m = re.match(r"play\s+(.+?)(?:\s+on spotify)?$", msg)
    if m and "music" not in m.group(1):
        query = m.group(1)
        # Open Spotify search
        _run(["open", f"spotify:search:{urllib.parse.quote(query)}"])
        return f"Searching Spotify for {query}."

    # ─── Volume ──────────────────────────────────────
    if msg in ("volume up", "louder", "turn it up"):
        _osascript("set volume output volume ((output volume of (get volume settings)) + 15)")
        return "Volume up."

    if msg in ("volume down", "quieter", "turn it down"):
        _osascript("set volume output volume ((output volume of (get volume settings)) - 15)")
        return "Volume down."

    if msg in ("mute", "mute volume", "silence"):
        _osascript("set volume output muted true")
        return "Muted."

    if msg in ("unmute", "unmute volume"):
        _osascript("set volume output muted false")
        return "Unmuted."

    m = re.match(r"(?:set )?volume (?:to )?(\d+)", msg)
    if m:
        level = min(100, max(0, int(m.group(1))))
        _osascript(f"set volume output volume {level}")
        return f"Volume set to {level}."

    # ─── Close App ───────────────────────────────────
    m = re.match(r"(?:close|quit|exit|kill)\s+(.+)", msg)
    if m:
        app = m.group(1).strip().title()
        _osascript(f'tell application "{app}" to quit')
        return f"Closed {app}."

    # ─── Screenshot ──────────────────────────────────
    if "screenshot" in msg or "screen capture" in msg:
        from datetime import datetime
        path = f"/tmp/screenshot_{datetime.now().strftime('%H%M%S')}.png"
        _run(["screencapture", "-x", path])
        return f"Screenshot saved to {path}."

    # ─── System Info ─────────────────────────────────
    if msg in ("what time is it", "time", "what's the time"):
        from datetime import datetime
        return datetime.now().strftime("It's %I:%M %p, sir.")

    if msg in ("what's the date", "date", "what date is it", "what's the date today"):
        from datetime import datetime
        return datetime.now().strftime("It's %A, %d %B %Y.")

    # ─── Dark Mode ───────────────────────────────────
    if "dark mode" in msg:
        _osascript('tell application "System Events" to tell appearance preferences to set dark mode to true')
        return "Dark mode enabled."

    if "light mode" in msg:
        _osascript('tell application "System Events" to tell appearance preferences to set dark mode to false')
        return "Light mode enabled."

    # ─── Sleep/Lock ──────────────────────────────────
    if msg in ("lock", "lock screen", "lock the screen"):
        _run(["pmset", "displaysleepnow"])
        return "Locking screen."

    # No pattern matched — return None to fall through to Claude
    return None
