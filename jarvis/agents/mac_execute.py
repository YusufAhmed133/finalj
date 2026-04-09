"""
Mac Execute — Real browser + OS control via CDP and AppleScript.

Single entry point: execute(command) takes natural language, makes it happen.

Approach:
- URL/website tasks: open in Chrome, use CDP for in-page interaction
- App tasks: open -a for installed apps, web fallback for others
- Music: Spotify Web Player via CDP (click play/pause/skip)
- Browser interaction: CDP websocket for clicking, typing, JS evaluation
"""
import asyncio
import json
import re
import subprocess
import urllib.parse
import urllib.request
from typing import Optional

CDP_URL = "http://localhost:9222"


# ── Shell helpers ──────────────────────────────────────────────

def _run(cmd: list, timeout: int = 5) -> tuple:
    """Run command, return (output, success)."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        out = (r.stdout.strip() + " " + r.stderr.strip()).strip()
        return out, r.returncode == 0
    except Exception as e:
        return str(e), False


def _osa(script: str) -> str:
    out, _ = _run(["osascript", "-e", script])
    return out


# ── CDP helpers ────────────────────────────────────────────────

def _cdp_available() -> bool:
    try:
        urllib.request.urlopen(f"{CDP_URL}/json/version", timeout=2)
        return True
    except Exception:
        return False


def _get_tabs() -> list:
    try:
        data = urllib.request.urlopen(f"{CDP_URL}/json/list", timeout=3).read()
        return [t for t in json.loads(data) if t.get("type") == "page"]
    except Exception:
        return []


def _find_tab(url_pattern: str) -> Optional[dict]:
    for tab in _get_tabs():
        if url_pattern.lower() in tab.get("url", "").lower():
            return tab
    return None


def _activate_tab(tab_id: str):
    try:
        urllib.request.urlopen(f"{CDP_URL}/json/activate/{tab_id}", timeout=2)
    except Exception:
        pass


def _cdp_eval(tab: dict, js_expression: str, timeout: int = 8) -> Optional[str]:
    """Execute JavaScript in a Chrome tab via CDP websocket. Returns result string."""
    try:
        import websocket
        ws = websocket.create_connection(tab["webSocketDebuggerUrl"], timeout=timeout)
        cmd = {
            "id": 1,
            "method": "Runtime.evaluate",
            "params": {"expression": js_expression, "returnByValue": True}
        }
        ws.send(json.dumps(cmd))
        resp = json.loads(ws.recv())
        ws.close()
        return resp.get("result", {}).get("result", {}).get("value")
    except Exception as e:
        return f"CDP error: {e}"


def _open_in_chrome(url: str) -> dict:
    """Open URL in Chrome and return the tab info once loaded."""
    import time
    _osa(f'tell application "Google Chrome" to open location "{url}"')
    # Wait for tab to appear
    for _ in range(10):
        time.sleep(0.5)
        # Match by a distinctive part of the URL
        domain = urllib.parse.urlparse(url).netloc or url
        tab = _find_tab(domain)
        if tab:
            _activate_tab(tab["id"])
            return tab
    return {}


# ── App mapping ────────────────────────────────────────────────

APP_MAP = {
    "spotify": "Spotify", "chrome": "Google Chrome", "google chrome": "Google Chrome",
    "safari": "Safari", "finder": "Finder", "terminal": "Terminal",
    "notes": "Notes", "messages": "Messages", "mail": "Mail",
    "calendar": "Calendar", "photos": "Photos", "music": "Music",
    "maps": "Maps", "settings": "System Settings", "system settings": "System Settings",
    "vscode": "Visual Studio Code", "vs code": "Visual Studio Code",
    "code": "Visual Studio Code", "slack": "Slack", "discord": "Discord",
    "zoom": "Zoom", "notion": "Notion", "whatsapp": "WhatsApp",
    "telegram": "Telegram", "cursor": "Cursor", "arc": "Arc",
    "warp": "Warp", "iterm": "iTerm",
}

WEB_FALLBACK = {
    "spotify": "https://open.spotify.com",
    "youtube": "https://youtube.com",
    "gmail": "https://mail.google.com",
    "google docs": "https://docs.google.com",
    "netflix": "https://netflix.com",
    "twitter": "https://x.com",
    "reddit": "https://reddit.com",
    "chatgpt": "https://chat.openai.com",
    "claude": "https://claude.ai",
    "instagram": "https://instagram.com",
    "facebook": "https://facebook.com",
    "linkedin": "https://linkedin.com",
    "whatsapp web": "https://web.whatsapp.com",
}


# ── Filler stripping ──────────────────────────────────────────

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
]


def _strip(msg: str) -> str:
    msg = msg.lower().strip()
    changed = True
    while changed:
        changed = False
        for p in FILLER_PRE:
            new = re.sub(p, "", msg).strip()
            if new != msg:
                msg = new
                changed = True
    for p in FILLER_POST:
        msg = re.sub(p, "", msg).strip()
    return msg


# ── Spotify Web Player controls ───────────────────────────────

def _spotify_ensure_open() -> Optional[dict]:
    """Ensure Spotify web is open, return its tab."""
    tab = _find_tab("open.spotify.com")
    if tab:
        _activate_tab(tab["id"])
        return tab
    return _open_in_chrome("https://open.spotify.com")


def _spotify_play_pause() -> str:
    tab = _spotify_ensure_open()
    if not tab:
        return "Could not open Spotify Web Player."
    result = _cdp_eval(tab, """
    (function() {
        var btn = document.querySelector('button[data-testid="control-button-playpause"]');
        if (btn) {
            var was = btn.getAttribute('aria-label');
            btn.click();
            return 'Was ' + was + ', now toggled.';
        }
        return 'Play/pause button not found on page.';
    })()
    """)
    return result or "Toggled play/pause."


def _spotify_play() -> str:
    tab = _spotify_ensure_open()
    if not tab:
        return "Could not open Spotify Web Player."
    result = _cdp_eval(tab, """
    (function() {
        var btn = document.querySelector('button[data-testid="control-button-playpause"]');
        if (!btn) return 'Play button not found.';
        if (btn.getAttribute('aria-label') === 'Play') {
            btn.click();
            return 'Playing now.';
        }
        return 'Already playing.';
    })()
    """)
    return result or "Playing."


def _spotify_pause() -> str:
    tab = _spotify_ensure_open()
    if not tab:
        return "Could not open Spotify Web Player."
    result = _cdp_eval(tab, """
    (function() {
        var btn = document.querySelector('button[data-testid="control-button-playpause"]');
        if (!btn) return 'Pause button not found.';
        if (btn.getAttribute('aria-label') === 'Pause') {
            btn.click();
            return 'Paused.';
        }
        return 'Already paused.';
    })()
    """)
    return result or "Paused."


def _spotify_next() -> str:
    tab = _spotify_ensure_open()
    if not tab:
        return "Could not open Spotify."
    _cdp_eval(tab, """
    document.querySelector('button[data-testid="control-button-skip-forward"]').click();
    """)
    return "Skipped to next track."


def _spotify_previous() -> str:
    tab = _spotify_ensure_open()
    if not tab:
        return "Could not open Spotify."
    _cdp_eval(tab, """
    document.querySelector('button[data-testid="control-button-skip-back"]').click();
    """)
    return "Previous track."


def _spotify_search_and_play(query: str) -> str:
    """Search Spotify and play the first result."""
    tab = _spotify_ensure_open()
    if not tab:
        return "Could not open Spotify."
    # Navigate to search
    encoded = urllib.parse.quote(query)
    _cdp_eval(tab, f'window.location.href = "https://open.spotify.com/search/{encoded}";')
    import time
    time.sleep(2)
    # Re-find the tab (URL changed)
    tab = _find_tab("open.spotify.com/search")
    if not tab:
        return f"Navigated to search for '{query}' but lost the tab."
    # Click the first play button in search results
    result = _cdp_eval(tab, """
    (function() {
        // Wait a moment, then find the first play button in results
        var btns = document.querySelectorAll('button[data-testid="play-button"]');
        if (btns.length > 0) {
            btns[0].click();
            return 'Playing: ' + (btns[0].getAttribute('aria-label') || 'first result');
        }
        return 'No play buttons found in search results yet.';
    })()
    """, timeout=10)
    return result or f"Searching for '{query}' on Spotify."


def _spotify_get_current() -> str:
    """Get what's currently playing."""
    tab = _find_tab("open.spotify.com")
    if not tab:
        return "Spotify not open."
    result = _cdp_eval(tab, """
    (function() {
        var track = document.querySelector('[data-testid="now-playing-widget"] a');
        var artist = document.querySelectorAll('[data-testid="now-playing-widget"] a');
        if (track) {
            var parts = [];
            artist.forEach(function(a) { parts.push(a.textContent); });
            return parts.join(' - ') || track.textContent;
        }
        var npv = document.querySelector('[data-testid="context-item-info-title"]');
        if (npv) return npv.textContent;
        return 'Nothing playing or cannot detect.';
    })()
    """)
    return result or "Cannot detect current track."


# ── YouTube controls ───────────────────────────────────────────

def _youtube_open_channel(channel: str) -> str:
    """Open a YouTube channel page."""
    # Clean up channel name
    channel = channel.strip().replace(" ", "")
    if not channel.startswith("@"):
        channel = "@" + channel
    url = f"https://www.youtube.com/{channel}"
    tab = _open_in_chrome(url)
    if tab:
        return f"Opened YouTube channel: {url}"
    return f"Opening {url} in browser."


def _youtube_search(query: str) -> str:
    """Search YouTube."""
    encoded = urllib.parse.quote_plus(query)
    url = f"https://www.youtube.com/results?search_query={encoded}"
    tab = _open_in_chrome(url)
    if tab:
        return f"Searching YouTube for: {query}"
    return f"Opening YouTube search for: {query}"


def _youtube_play_pause() -> str:
    """Toggle play/pause on currently open YouTube video."""
    tab = _find_tab("youtube.com/watch")
    if not tab:
        return "No YouTube video tab found."
    _activate_tab(tab["id"])
    result = _cdp_eval(tab, """
    (function() {
        var video = document.querySelector('video');
        if (video) {
            if (video.paused) { video.play(); return 'Playing.'; }
            else { video.pause(); return 'Paused.'; }
        }
        return 'No video element found.';
    })()
    """)
    return result or "Toggled YouTube playback."


# ── Generic browser interaction ────────────────────────────────

def _browser_click(selector: str, tab_pattern: str = "") -> str:
    """Click an element in the current or specified tab."""
    if tab_pattern:
        tab = _find_tab(tab_pattern)
    else:
        tabs = _get_tabs()
        tab = tabs[0] if tabs else None
    if not tab:
        return "No matching tab found."
    _activate_tab(tab["id"])
    result = _cdp_eval(tab, f"""
    (function() {{
        var el = document.querySelector('{selector}');
        if (el) {{ el.click(); return 'Clicked: ' + (el.textContent || el.tagName).substring(0, 50); }}
        return 'Element not found: {selector}';
    }})()
    """)
    return result or "Click attempted."


def _browser_type(text: str, selector: str = "", tab_pattern: str = "") -> str:
    """Type text into the active element or a specific selector."""
    if tab_pattern:
        tab = _find_tab(tab_pattern)
    else:
        tabs = _get_tabs()
        tab = tabs[0] if tabs else None
    if not tab:
        return "No matching tab found."
    _activate_tab(tab["id"])
    escaped = text.replace("'", "\\'").replace("\n", "\\n")
    if selector:
        js = f"""
        (function() {{
            var el = document.querySelector('{selector}');
            if (el) {{ el.focus(); el.value = '{escaped}'; el.dispatchEvent(new Event('input', {{bubbles:true}})); return 'Typed into ' + el.tagName; }}
            return 'Element not found';
        }})()
        """
    else:
        js = f"""
        (function() {{
            var el = document.activeElement;
            if (el) {{ el.value = '{escaped}'; el.dispatchEvent(new Event('input', {{bubbles:true}})); return 'Typed into ' + el.tagName; }}
            return 'No active element';
        }})()
        """
    return _cdp_eval(tab, js) or "Typed."


def _take_screenshot(path: str = "/tmp/screenshot.png") -> str:
    _run(["screencapture", "-x", path])
    return f"Screenshot saved to {path}."


# ── Command parser + executor ──────────────────────────────────

async def execute(command: str) -> str:
    """
    Execute a natural language Mac command. Returns status string.

    Examples:
        "open Spotify and play" -> opens Spotify web, clicks play
        "go to KSI's YouTube" -> opens youtube.com/@KSI
        "pause" -> pauses Spotify
        "next song" -> skips track
        "search YouTube for funny cats" -> opens YouTube search
        "open google docs" -> opens docs.google.com
        "take a screenshot" -> screencapture
    """
    msg = _strip(command)

    # ── Spotify: play/pause/next/previous ──
    if msg in ("play", "play music", "resume", "resume music", "play some music",
               "press play", "hit play"):
        return _spotify_play()

    if msg in ("pause", "pause music", "stop music", "stop", "press pause", "hit pause"):
        return _spotify_pause()

    if msg in ("next", "next song", "skip", "skip song", "next track", "skip track"):
        return _spotify_next()

    if msg in ("previous", "previous song", "go back", "last song", "previous track"):
        return _spotify_previous()

    if msg in ("whats playing", "what's playing", "current song", "what song",
               "what is playing", "now playing"):
        return _spotify_get_current()

    # ── Spotify: "open spotify and play" / "open spotify" ──
    m = re.match(r"open spotify(?:\s+and\s+(?:play|press play|hit play))?", msg)
    if m:
        tab = _spotify_ensure_open()
        if "and" in msg and "play" in msg:
            import time
            time.sleep(1)
            return _spotify_play()
        return "Spotify Web Player is open." if tab else "Could not open Spotify."

    # ── Spotify: "play X on spotify" / "play X" ──
    m = re.match(r"play\s+(.+?)(?:\s+on\s+spotify)?$", msg)
    if m and msg not in ("play music", "play some music"):
        query = m.group(1).strip()
        # Check if it's a playlist name from sidebar
        return _spotify_search_and_play(query)

    # ── YouTube: "go to X youtube" / "open X youtube channel" ──
    m = re.match(r"(?:go to|open|visit)\s+(.+?)(?:'s)?\s+youtube(?:\s+channel)?", msg)
    if m:
        return _youtube_open_channel(m.group(1).strip())

    # ── YouTube: "go to youtube.com/@X" ──
    m = re.match(r"(?:go to|open|visit)\s+youtube\.com/(@?\w+)", msg)
    if m:
        return _youtube_open_channel(m.group(1))

    # ── YouTube: "search youtube for X" ──
    m = re.match(r"(?:search youtube for|youtube search)\s+(.+)", msg)
    if m:
        return _youtube_search(m.group(1).strip())

    # ── YouTube play/pause ──
    if "youtube" in msg and any(w in msg for w in ["play", "pause"]):
        return _youtube_play_pause()

    # ── Open URL ──
    m = re.match(r"(?:go to|open|navigate to|visit)\s+(https?://\S+)", msg)
    if m:
        url = m.group(1)
        _open_in_chrome(url)
        return f"Opened {url}."

    m = re.match(r"(?:go to|navigate to|visit)\s+(\S+\.\S+)", msg)
    if m:
        url = m.group(1) if m.group(1).startswith("http") else "https://" + m.group(1)
        _open_in_chrome(url)
        return f"Opened {url}."

    # ── Search Google ──
    m = re.match(r"(?:search for|search|google|look up)\s+(.+)", msg)
    if m:
        query = urllib.parse.quote_plus(m.group(1))
        _open_in_chrome(f"https://www.google.com/search?q={query}")
        return f"Searching for: {m.group(1)}."

    # ── Open app (installed or web fallback) ──
    m = re.match(r"(?:open|launch|start|run|fire up|bring up|pull up)\s+(.+)", msg)
    if m:
        raw = m.group(1).strip()
        app_key = raw.lower().split()[0]  # First word as app key
        # Try multi-word matches
        for key in sorted(WEB_FALLBACK.keys(), key=len, reverse=True):
            if raw.lower().startswith(key):
                app_key = key
                break
        for key in sorted(APP_MAP.keys(), key=len, reverse=True):
            if raw.lower().startswith(key):
                app_key = key
                break

        # Try native app first
        app_name = APP_MAP.get(app_key)
        if app_name:
            out, ok = _run(["osascript", "-e", f'tell application "{app_name}" to activate'])
            if ok:
                return f"{app_name} is open."

        # Try open -a
        app_title = app_name or raw.title()
        out, ok = _run(["open", "-a", app_title])
        if ok:
            return f"{app_title} is open."

        # Web fallback
        web_url = WEB_FALLBACK.get(app_key)
        if web_url:
            _open_in_chrome(web_url)
            return f"Opened {app_key} in browser."

        return f"Could not find app: {raw}."

    # ── Close app ──
    m = re.match(r"(?:close|quit|exit|kill)\s+(.+)", msg)
    if m:
        app_key = m.group(1).strip().lower()
        app_name = APP_MAP.get(app_key, app_key.title())
        _osa(f'tell application "{app_name}" to quit')
        return f"Closed {app_name}."

    # ── Screenshot ──
    if "screenshot" in msg:
        return _take_screenshot()

    # ── Volume ──
    if msg in ("volume up", "louder", "turn it up", "turn up volume"):
        _osa("set volume output volume ((output volume of (get volume settings)) + 15)")
        return "Volume up."
    if msg in ("volume down", "quieter", "turn it down", "turn down volume"):
        _osa("set volume output volume ((output volume of (get volume settings)) - 15)")
        return "Volume down."
    if msg in ("mute", "mute volume", "silence"):
        _osa("set volume output muted true")
        return "Muted."
    if msg in ("unmute", "unmute volume"):
        _osa("set volume output muted false")
        return "Unmuted."
    m = re.match(r"(?:set )?volume (?:to )?(\d+)", msg)
    if m:
        _osa(f"set volume output volume {min(100, max(0, int(m.group(1))))}")
        return f"Volume set to {m.group(1)}."

    # ── Keyboard shortcuts ──
    shortcuts = {
        "copy": ("c", "command down"),
        "paste": ("v", "command down"),
        "cut": ("x", "command down"),
        "undo": ("z", "command down"),
        "save": ("s", "command down"),
        "select all": ("a", "command down"),
        "refresh": ("r", "command down"),
        "new tab": ("t", "command down"),
        "close tab": ("w", "command down"),
        "minimize": ("m", "command down"),
    }
    for name, (key, mod) in shortcuts.items():
        if msg == name:
            _osa(f'tell application "System Events" to keystroke "{key}" using {mod}')
            return f"Done ({name})."

    # ── Time/Date ──
    if any(x in msg for x in ["what time", "whats the time", "the time"]):
        from datetime import datetime
        return datetime.now().strftime("It's %I:%M %p.")
    if any(x in msg for x in ["what date", "whats the date", "the date", "what day"]):
        from datetime import datetime
        return datetime.now().strftime("%A, %d %B %Y.")

    # ── Dark/Light mode ──
    if "dark mode" in msg:
        _osa('tell application "System Events" to tell appearance preferences to set dark mode to true')
        return "Dark mode on."
    if "light mode" in msg:
        _osa('tell application "System Events" to tell appearance preferences to set dark mode to false')
        return "Light mode on."

    # ── Lock ──
    if msg in ("lock", "lock screen"):
        _run(["pmset", "displaysleepnow"])
        return "Locking screen."

    # ── Fallback: unrecognized command ──
    return f"Not sure how to handle: '{command}'. Try being more specific."


# ── Sync wrapper for non-async callers ─────────────────────────

def execute_sync(command: str) -> str:
    """Synchronous wrapper around execute()."""
    return asyncio.run(execute(command))


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        cmd = " ".join(sys.argv[1:])
        print(f"Executing: {cmd}")
        print(execute_sync(cmd))
    else:
        print("Usage: python mac_execute.py <command>")
        print("Examples:")
        print("  python mac_execute.py open spotify and play")
        print("  python mac_execute.py go to KSI youtube channel")
        print("  python mac_execute.py pause")
        print("  python mac_execute.py play drake on spotify")
