"""Tiny HTTP server that shows the WhatsApp QR code in a browser.
Starts bridge.js, captures QR data, serves it as a web page at localhost:7777.
"""
import asyncio
import json
import subprocess
import sys
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import qrcode
import qrcode.image.svg
import io
import base64

# State
latest_qr_data = None
connection_status = "waiting"
bridge_process = None

BRIDGE_DIR = os.path.dirname(os.path.abspath(__file__))
BRIDGE_SCRIPT = os.path.join(BRIDGE_DIR, "bridge.js")

HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
    <title>JARVIS - WhatsApp QR</title>
    <meta http-equiv="refresh" content="3">
    <style>
        body {{
            background: #0a0a0a; color: #e0e0e0;
            font-family: -apple-system, system-ui, sans-serif;
            display: flex; flex-direction: column;
            align-items: center; justify-content: center;
            min-height: 100vh; margin: 0;
        }}
        h1 {{ color: #4fc3f7; }}
        .status {{ color: #81c784; font-size: 1.2em; margin: 10px 0; }}
        .qr {{ background: white; padding: 20px; border-radius: 12px; margin: 20px; }}
        .qr img {{ width: 350px; height: 350px; }}
        .connected {{ color: #4caf50; font-size: 2em; }}
        .instructions {{ color: #aaa; max-width: 400px; text-align: center; }}
    </style>
</head>
<body>
    <h1>JARVIS - WhatsApp Setup</h1>
    {content}
</body>
</html>"""


class QRHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()

        if connection_status == "open":
            content = '<div class="connected">Connected to WhatsApp!</div><p>You can close this page.</p>'
        elif latest_qr_data:
            # Generate QR code as PNG base64
            qr = qrcode.QRCode(version=1, box_size=10, border=4)
            qr.add_data(latest_qr_data)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            b64 = base64.b64encode(buf.getvalue()).decode()

            content = f"""
            <div class="qr"><img src="data:image/png;base64,{b64}" alt="QR Code"></div>
            <div class="instructions">
                <p><strong>Scan this with WhatsApp:</strong></p>
                <p>Open WhatsApp → Settings → Linked Devices → Link a Device</p>
                <p style="color: #666;">Page refreshes every 3 seconds</p>
            </div>
            """
        else:
            content = '<div class="status">Starting WhatsApp bridge... waiting for QR code</div>'

        html = HTML_TEMPLATE.format(content=content)
        self.wfile.write(html.encode())

    def log_message(self, format, *args):
        pass  # Suppress request logs


def read_bridge_output(proc):
    global latest_qr_data, connection_status
    for line in proc.stdout:
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
            if event.get("type") == "qr":
                latest_qr_data = event["data"]
                print(f"[QR] New QR code received")
            elif event.get("type") == "connection":
                status = event.get("status")
                connection_status = status
                print(f"[Connection] {status}")
                if status == "open":
                    user = event.get("user", {})
                    print(f"[Connected] as {user}")
            elif event.get("type") == "message":
                text = event.get("text", "")
                sender = event.get("pushName", event.get("from", "?"))
                print(f"[Message] {sender}: {text[:100]}")
            elif event.get("type") == "error":
                print(f"[Error] {event.get('error')}")
        except json.JSONDecodeError:
            pass


def main():
    global bridge_process

    print("Starting WhatsApp bridge...")
    bridge_process = subprocess.Popen(
        ["node", BRIDGE_SCRIPT],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        cwd=BRIDGE_DIR,
        text=True,
        bufsize=1,
    )

    # Read bridge output in background thread
    reader = threading.Thread(target=read_bridge_output, args=(bridge_process,), daemon=True)
    reader.start()

    # Start HTTP server
    port = 7777
    server = HTTPServer(("0.0.0.0", port), QRHandler)
    print(f"\nOpen http://localhost:{port} in your browser to scan the QR code\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        bridge_process.terminate()
        server.shutdown()


if __name__ == "__main__":
    main()
