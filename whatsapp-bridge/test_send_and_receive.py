"""Test: connect, send a message TO the owner, then listen for replies."""
import asyncio
import json
import os
import sys

BRIDGE_DIR = os.path.dirname(os.path.abspath(__file__))
BRIDGE_SCRIPT = os.path.join(BRIDGE_DIR, "bridge.js")

# Your JID from the session file
OWNER_JID = "61470665141@s.whatsapp.net"


async def main():
    print("Starting bridge...", flush=True)
    proc = await asyncio.create_subprocess_exec(
        "node", BRIDGE_SCRIPT,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        cwd=BRIDGE_DIR,
    )

    print("Waiting for connection...", flush=True)

    buffer = ""
    connected = False

    while True:
        chunk = await proc.stdout.read(4096)
        if not chunk:
            break
        buffer += chunk.decode()
        lines = buffer.split('\n')
        buffer = lines.pop()

        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
                t = event.get("type")

                if t == "connection" and event.get("status") == "open":
                    print("[CONNECTED]", flush=True)
                    connected = True

                    # Send a test message to self
                    print(f"\nSending test message to {OWNER_JID}...", flush=True)
                    cmd = json.dumps({
                        "action": "send_text",
                        "to": OWNER_JID,
                        "text": "JARVIS is online. Reply to this message to test."
                    }) + '\n'
                    proc.stdin.write(cmd.encode())
                    await proc.stdin.drain()
                    print("[SENT] Test message sent to your WhatsApp!", flush=True)
                    print("Now reply to that message on WhatsApp...\n", flush=True)

                elif t == "message":
                    text = event.get("text", "")
                    sender = event.get("pushName", "?")
                    jid = event.get("from", "")
                    print(f"[MESSAGE RECEIVED]", flush=True)
                    print(f"  From: {sender} ({jid})", flush=True)
                    print(f"  Text: {text}", flush=True)

                    if text:
                        reply = json.dumps({
                            "action": "send_text",
                            "to": jid,
                            "text": f"JARVIS echo: {text}"
                        }) + '\n'
                        proc.stdin.write(reply.encode())
                        await proc.stdin.drain()
                        print(f"  [REPLIED] JARVIS echo: {text}", flush=True)
                        print("\n[SUCCESS] Full round-trip working! Ctrl+C to stop.", flush=True)

                elif t == "sent":
                    print(f"  [DELIVERED] to {event.get('to')}", flush=True)

                elif t == "error":
                    print(f"[ERROR] {event.get('error')}", flush=True)

                elif t == "bridge_ready":
                    print("[BRIDGE READY]", flush=True)

            except json.JSONDecodeError:
                pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped.", flush=True)
