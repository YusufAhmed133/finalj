"""Test: start bridge, wait for a message, log it, reply with echo."""
import asyncio
import json
import subprocess
import os

BRIDGE_DIR = os.path.dirname(os.path.abspath(__file__))
BRIDGE_SCRIPT = os.path.join(BRIDGE_DIR, "bridge.js")


async def main():
    print("Starting bridge...")
    proc = await asyncio.create_subprocess_exec(
        "node", BRIDGE_SCRIPT,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        cwd=BRIDGE_DIR,
    )

    print("Waiting for connection and messages...")
    print("Send a WhatsApp message to this number now.\n")

    buffer = ""
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

                if t == "connection":
                    status = event.get("status")
                    if status == "open":
                        print(f"[CONNECTED] WhatsApp linked successfully!")
                    else:
                        print(f"[CONNECTION] {status}")

                elif t == "message":
                    text = event.get("text", "")
                    sender = event.get("pushName", "?")
                    jid = event.get("from", "")
                    print(f"\n[MESSAGE RECEIVED]")
                    print(f"  From: {sender} ({jid})")
                    print(f"  Text: {text}")
                    print(f"  Type: {event.get('contentType')}")

                    # Echo reply
                    if text:
                        reply = json.dumps({
                            "action": "send_text",
                            "to": jid,
                            "text": f"JARVIS received: {text}"
                        }) + '\n'
                        proc.stdin.write(reply.encode())
                        await proc.stdin.drain()
                        print(f"  [REPLIED] JARVIS received: {text}")

                elif t == "sent":
                    print(f"  [SENT OK] to {event.get('to')}")

                elif t == "error":
                    print(f"[ERROR] {event.get('error')}")

                elif t == "bridge_ready":
                    print("[BRIDGE READY]")

            except json.JSONDecodeError:
                pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped.")
