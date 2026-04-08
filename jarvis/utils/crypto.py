"""Fernet encryption for secrets at rest."""
from cryptography.fernet import Fernet
from pathlib import Path

SECRETS_PATH = Path(__file__).parent.parent.parent / "config" / "secrets.env"


def generate_key() -> bytes:
    return Fernet.generate_key()


def get_fernet(key: bytes) -> Fernet:
    return Fernet(key)


def encrypt(data: str, key: bytes) -> bytes:
    return get_fernet(key).encrypt(data.encode())


def decrypt(token: bytes, key: bytes) -> str:
    return get_fernet(key).decrypt(token).decode()


def load_secrets() -> dict:
    """Load secrets from config/secrets.env into a dict."""
    secrets = {}
    if not SECRETS_PATH.exists():
        return secrets
    for line in SECRETS_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            secrets[k.strip()] = v.strip()
    return secrets
