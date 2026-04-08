"""Central identity loader — single source of truth for user identity."""
import yaml
from pathlib import Path
from functools import lru_cache

IDENTITY_PATH = Path(__file__).parent / "user.yaml"

@lru_cache(maxsize=1)
def _load_raw() -> dict:
    if IDENTITY_PATH.exists():
        return yaml.safe_load(IDENTITY_PATH.read_text()) or {}
    return {}

def get_user_name() -> str:
    return _load_raw().get("name", "User")

def get_user_first_name() -> str:
    return get_user_name().split()[0]

def get_identity() -> dict:
    return _load_raw()

def get_identity_string() -> str:
    data = _load_raw()
    if not data:
        return "User identity not configured. Edit jarvis/identity/user.yaml."
    loc = data.get("location", {})
    edu = data.get("education", {})
    style = data.get("communication_style", {})
    lines = [
        f"User: {data.get('name', 'Unknown')}, {data.get('age', '?')} years old",
        f"Location: {loc.get('city', '?')}, {loc.get('country', '?')}",
        f"Timezone: {loc.get('timezone', 'UTC')}",
        f"Education: {edu.get('university', '?')} — {edu.get('degree', '?')}",
        f"Communication: {style.get('tone', 'Direct')}",
    ]
    if data.get("health", {}).get("cardiac_device"):
        lines.append("Health: Cardiac device implanted — cardiac alerts are ALWAYS priority, NEVER suppressed")
    return "\n".join(lines)

def get_subreddits() -> list:
    data = _load_raw()
    subs = data.get("subreddits_of_interest", [])
    return [s.replace("r/", "") for s in subs]

def reload():
    """Clear cache and reload from disk."""
    _load_raw.cache_clear()
