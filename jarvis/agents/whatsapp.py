"""
WhatsApp Agent — Baileys Bridge Interface.

Spawns Node.js child process running bridge.js.
Communicates via newline-delimited JSON over stdin/stdout.
"""
import asyncio
import json
from pathlib import Path
from typing import Optional, Callable

from jarvis.utils.logger import get_logger

log = get_logger("agents.whatsapp")

BRIDGE_DIR = Path(__file__).parent.parent.parent / "whatsapp-bridge"
BRIDGE_SCRIPT = BRIDGE_DIR / "bridge.js"


class WhatsAppBridge:

    def __init__(self):
        self._process: Optional[asyncio.subprocess.Process] = None
        self._message_handler: Optional[Callable] = None
        self._read_task: Optional[asyncio.Task] = None
        self._running = False
        self._connected = False
        self._owner_jid: Optional[str] = None
        self._context_messages: list = []

    async def initialize(self, message_handler: Callable) -> bool:
        self._message_handler = message_handler

        from jarvis.utils.crypto import load_secrets
        secrets = load_secrets()
        self._owner_jid = secrets.get("WHATSAPP_OWNER_JID", "")

        if not BRIDGE_SCRIPT.exists():
            log.error(f"Bridge not found: {BRIDGE_SCRIPT}")
            return False

        if not (BRIDGE_DIR / "node_modules").exists():
            log.error("Run: cd whatsapp-bridge && npm install")
            return False

        log.info("WhatsApp bridge initialized")
        return True

    async def start(self):
        log.info("Starting WhatsApp bridge...")
        self._process = await asyncio.create_subprocess_exec(
            "node", str(BRIDGE_SCRIPT),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(BRIDGE_DIR),
        )
        self._running = True
        self._read_task = asyncio.create_task(self._read_loop())
        asyncio.create_task(self._stderr_loop())
        log.info(f"Bridge started (PID: {self._process.pid})")

    async def stop(self):
        self._running = False
        if self._process:
            self._process.stdin.close()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self._process.kill()
                await self._process.wait()
        if self._read_task:
            self._read_task.cancel()
        log.info("WhatsApp bridge stopped")

    async def _read_loop(self):
        buffer = ""
        while self._running:
            try:
                chunk = await self._process.stdout.read(8192)
                if not chunk:
                    log.warning("Bridge stdout closed")
                    break
                buffer += chunk.decode('utf-8')
                lines = buffer.split('\n')
                buffer = lines.pop()
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        await self._handle_event(json.loads(line))
                    except json.JSONDecodeError as e:
                        log.error(f"JSON parse error: {e}")
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"Read loop error: {e}")
                await asyncio.sleep(1)

    async def _stderr_loop(self):
        while self._running:
            try:
                line = await self._process.stderr.readline()
                if not line:
                    break
                text = line.decode().strip()
                if text:
                    # Print QR codes and important messages to console
                    print(text)
            except asyncio.CancelledError:
                break
            except Exception:
                break

    async def _handle_event(self, event: dict):
        t = event.get("type")

        if t == "bridge_ready":
            log.info("Bridge ready, connecting to WhatsApp...")

        elif t == "qr":
            log.info("QR code displayed in terminal. Scan with WhatsApp.")

        elif t == "connection":
            status = event.get("status")
            self._connected = status == "open"
            if status == "open":
                user = event.get("user", {})
                log.info(f"WhatsApp connected as {user.get('id', '?')}")
            elif status == "closed":
                log.warning(f"WhatsApp disconnected (code: {event.get('statusCode')})")
            elif status == "logged_out":
                log.error("Logged out. Delete whatsapp-bridge/auth_info/ and restart.")

        elif t == "message":
            await self._handle_message(event)

        elif t == "sent":
            log.debug(f"Sent: {event.get('action')} to {event.get('to')}")

        elif t == "error":
            log.error(f"Bridge: {event.get('error')} ({event.get('context', '')})")

    async def _handle_message(self, event: dict):
        from_jid = event.get("from", "")
        text = event.get("text", "")
        push_name = event.get("pushName", "")
        is_group = event.get("isGroup", False)

        # Owner filter
        if self._owner_jid and from_jid != self._owner_jid and not is_group:
            log.info(f"Ignoring non-owner: {from_jid}")
            return

        log.info(f"Message from {push_name}: {text[:80]}")

        # Voice note transcription
        if event.get("isVoiceNote") and event.get("mediaPath"):
            text = await self._transcribe(event["mediaPath"])
            if not text:
                await self.send_text(from_jid, "Couldn't transcribe that. Try again?")
                return

        if not text:
            return

        # Typing indicator
        await self._send_cmd({"action": "send_presence", "presence": "composing", "to": from_jid})

        self._context_messages.append({"sender": "user", "text": text[:500]})
        if len(self._context_messages) > 20:
            self._context_messages.pop(0)

        try:
            response = await self._message_handler(
                message=text,
                source="whatsapp",
                metadata={"jid": from_jid, "push_name": push_name, "is_group": is_group},
            )
            if response:
                self._context_messages.append({"sender": "JARVIS", "text": response[:500]})
                await self._send_cmd({"action": "send_presence", "presence": "paused", "to": from_jid})
                await self.send_text(from_jid, response)
        except Exception as e:
            log.error(f"Handler error: {e}")
            await self.send_text(from_jid, f"Error: {str(e)[:200]}")

    async def _transcribe(self, path: str) -> str:
        try:
            from faster_whisper import WhisperModel
            if not hasattr(self, '_whisper') or self._whisper is None:
                self._whisper = WhisperModel("tiny", device="cpu", compute_type="int8")
            segments, _ = self._whisper.transcribe(path, language="en", beam_size=5)
            return " ".join(s.text.strip() for s in segments).strip()
        except Exception as e:
            log.error(f"Transcription error: {e}")
            return ""

    async def send_text(self, to: str, text: str):
        for chunk in self._split(text):
            await self._send_cmd({"action": "send_text", "to": to, "text": chunk})

    async def send_to_owner(self, text: str):
        if self._owner_jid:
            await self.send_text(self._owner_jid, text)

    async def _send_cmd(self, cmd: dict):
        if not self._process or self._process.returncode is not None:
            return
        self._process.stdin.write((json.dumps(cmd) + '\n').encode())
        await self._process.stdin.drain()

    @staticmethod
    def _split(text: str, max_len: int = 4096) -> list:
        if len(text) <= max_len:
            return [text]
        chunks = []
        while text:
            if len(text) <= max_len:
                chunks.append(text)
                break
            b = text.rfind('\n', 0, max_len)
            if b == -1:
                b = max_len
            chunks.append(text[:b])
            text = text[b:].lstrip('\n')
        return chunks

    @property
    def is_connected(self):
        return self._connected
