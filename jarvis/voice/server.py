"""
JARVIS Voice Interface — Iron Man orb UI at localhost:8080.

Black screen with animated orb. Listens via microphone, transcribes with
faster-whisper, routes through orchestrator, speaks response via macOS TTS.

WebSocket for real-time audio/status. FastAPI serves the page.
"""
import asyncio
import json
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Optional, Callable

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from jarvis.utils.logger import get_logger

log = get_logger("voice.server")

app = FastAPI(title="JARVIS Voice")

_message_handler: Optional[Callable] = None
_whisper_model = None
_muted = False
_deafened = False


def set_handler(handler: Callable):
    global _message_handler
    _message_handler = handler


def _get_whisper():
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        _whisper_model = WhisperModel("tiny", device="cpu", compute_type="int8")
        log.info("Whisper loaded for voice UI")
    return _whisper_model


def _speak(text: str):
    """Speak text via macOS TTS."""
    if _deafened:
        return
    # Use macOS 'say' command with a good voice
    subprocess.Popen(["say", "-v", "Daniel", text],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


ORB_HTML = """<!DOCTYPE html>
<html>
<head>
<title>JARVIS</title>
<meta charset="utf-8">
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    background: #000; overflow: hidden;
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    height: 100vh; font-family: -apple-system, sans-serif;
    color: #4fc3f7;
}
#orb-container {
    position: relative; width: 200px; height: 200px;
    display: flex; align-items: center; justify-content: center;
}
#orb {
    width: 120px; height: 120px; border-radius: 50%;
    background: radial-gradient(circle at 40% 40%, #4fc3f7, #0288d1, #01579b);
    box-shadow: 0 0 60px rgba(79, 195, 247, 0.4), 0 0 120px rgba(79, 195, 247, 0.2);
    transition: all 0.3s ease;
}
#orb.listening {
    animation: pulse 1.5s ease-in-out infinite;
    box-shadow: 0 0 80px rgba(79, 195, 247, 0.6), 0 0 160px rgba(79, 195, 247, 0.3);
}
#orb.thinking {
    animation: spin 2s linear infinite;
    background: radial-gradient(circle at 40% 40%, #ffb74d, #f57c00, #e65100);
    box-shadow: 0 0 80px rgba(255, 183, 77, 0.6), 0 0 160px rgba(255, 183, 77, 0.3);
}
#orb.speaking {
    animation: breathe 0.8s ease-in-out infinite;
    background: radial-gradient(circle at 40% 40%, #81c784, #388e3c, #1b5e20);
    box-shadow: 0 0 80px rgba(129, 199, 132, 0.6), 0 0 160px rgba(129, 199, 132, 0.3);
}
#orb.muted {
    background: radial-gradient(circle at 40% 40%, #666, #444, #222);
    box-shadow: 0 0 30px rgba(100, 100, 100, 0.3);
    animation: none;
}
@keyframes pulse {
    0%, 100% { transform: scale(1); }
    50% { transform: scale(1.08); }
}
@keyframes spin {
    0% { transform: rotate(0deg) scale(1.05); }
    100% { transform: rotate(360deg) scale(1.05); }
}
@keyframes breathe {
    0%, 100% { transform: scale(1); }
    50% { transform: scale(1.12); }
}
#status {
    margin-top: 30px; font-size: 14px; color: #666;
    text-transform: uppercase; letter-spacing: 3px;
}
#transcript {
    position: fixed; bottom: 40px; left: 50%;
    transform: translateX(-50%); max-width: 600px;
    text-align: center; font-size: 16px; color: #aaa;
    opacity: 0.8;
}
#response {
    position: fixed; bottom: 80px; left: 50%;
    transform: translateX(-50%); max-width: 600px;
    text-align: center; font-size: 18px; color: #4fc3f7;
}
.ring {
    position: absolute; border-radius: 50%;
    border: 1px solid rgba(79, 195, 247, 0.15);
    animation: ring-expand 3s ease-out infinite;
}
.ring:nth-child(2) { animation-delay: 1s; }
.ring:nth-child(3) { animation-delay: 2s; }
@keyframes ring-expand {
    0% { width: 120px; height: 120px; opacity: 0.5; }
    100% { width: 300px; height: 300px; opacity: 0; }
}
</style>
</head>
<body>
<div id="orb-container">
    <div class="ring"></div>
    <div class="ring"></div>
    <div class="ring"></div>
    <div id="orb" class="listening"></div>
</div>
<div id="status">listening</div>
<div id="response"></div>
<div id="transcript"></div>

<script>
const orb = document.getElementById('orb');
const status = document.getElementById('status');
const transcript = document.getElementById('transcript');
const responseDiv = document.getElementById('response');

let ws;
let mediaRecorder;
let audioChunks = [];
let isRecording = false;
let silenceTimer;
let audioContext;
let analyser;

function connect() {
    ws = new WebSocket(`ws://${location.host}/ws`);
    ws.onopen = () => { console.log('Connected'); startListening(); };
    ws.onmessage = (e) => {
        const data = JSON.parse(e.data);
        if (data.type === 'status') {
            setOrb(data.state);
            status.textContent = data.state;
        } else if (data.type === 'transcript') {
            transcript.textContent = data.text;
        } else if (data.type === 'response') {
            responseDiv.textContent = data.text;
            transcript.textContent = '';
            setTimeout(() => { responseDiv.textContent = ''; }, 8000);
        } else if (data.type === 'muted') {
            setOrb('muted');
            status.textContent = 'muted';
        }
    };
    ws.onclose = () => setTimeout(connect, 2000);
}

function setOrb(state) {
    orb.className = state;
}

async function startListening() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        audioContext = new AudioContext();
        const source = audioContext.createMediaStreamSource(stream);
        analyser = audioContext.createAnalyser();
        analyser.fftSize = 512;
        source.connect(analyser);

        mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm;codecs=opus' });
        mediaRecorder.ondataavailable = (e) => { if (e.data.size > 0) audioChunks.push(e.data); };
        mediaRecorder.onstop = sendAudio;

        detectSpeech();
    } catch(e) {
        status.textContent = 'microphone denied';
        console.error(e);
    }
}

function detectSpeech() {
    const data = new Uint8Array(analyser.frequencyBinCount);
    let speaking = false;

    function check() {
        analyser.getByteFrequencyData(data);
        const avg = data.reduce((a,b) => a+b, 0) / data.length;

        if (avg > 15 && !isRecording) {
            isRecording = true;
            audioChunks = [];
            mediaRecorder.start();
            clearTimeout(silenceTimer);
        }

        if (avg < 8 && isRecording) {
            clearTimeout(silenceTimer);
            silenceTimer = setTimeout(() => {
                if (isRecording) {
                    isRecording = false;
                    mediaRecorder.stop();
                }
            }, 1200);
        }

        requestAnimationFrame(check);
    }
    check();
}

async function sendAudio() {
    if (audioChunks.length === 0) return;
    const blob = new Blob(audioChunks, { type: 'audio/webm' });
    if (blob.size < 1000) return; // Too short

    const reader = new FileReader();
    reader.onload = () => {
        const base64 = reader.result.split(',')[1];
        ws.send(JSON.stringify({ type: 'audio', data: base64 }));
    };
    reader.readAsDataURL(blob);
    audioChunks = [];
}

connect();
</script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
async def index():
    return ORB_HTML


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    global _muted, _deafened
    await websocket.accept()
    log.info("Voice client connected")

    await websocket.send_json({"type": "status", "state": "listening"})

    try:
        while True:
            msg = await websocket.receive_text()
            data = json.loads(msg)

            if data["type"] == "audio":
                await websocket.send_json({"type": "status", "state": "thinking"})

                # Decode audio
                import base64
                audio_bytes = base64.b64decode(data["data"])

                # Save to temp file
                tmp = tempfile.NamedTemporaryFile(suffix=".webm", delete=False)
                tmp.write(audio_bytes)
                tmp.close()

                # Convert webm to wav using ffmpeg
                wav_path = tmp.name.replace(".webm", ".wav")
                subprocess.run(
                    ["ffmpeg", "-y", "-i", tmp.name, "-ar", "16000", "-ac", "1", wav_path],
                    capture_output=True, timeout=10
                )

                # Transcribe
                try:
                    model = _get_whisper()
                    segments, _ = model.transcribe(wav_path, language="en", beam_size=5)
                    text = " ".join(s.text.strip() for s in segments).strip()
                except Exception as e:
                    log.error(f"Transcription error: {e}")
                    text = ""

                # Cleanup
                Path(tmp.name).unlink(missing_ok=True)
                Path(wav_path).unlink(missing_ok=True)

                if not text:
                    await websocket.send_json({"type": "status", "state": "listening"})
                    continue

                # Check voice commands
                lower = text.lower().strip()
                if "jarvis mute" in lower or "mute" == lower:
                    _muted = True
                    await websocket.send_json({"type": "muted"})
                    continue
                elif "jarvis unmute" in lower or "unmute" == lower:
                    _muted = False
                    await websocket.send_json({"type": "status", "state": "listening"})
                    continue
                elif "jarvis deafen" in lower:
                    _deafened = True
                    await websocket.send_json({"type": "status", "state": "listening"})
                    continue
                elif "jarvis undeafen" in lower:
                    _deafened = False
                    await websocket.send_json({"type": "status", "state": "listening"})
                    continue

                if _muted:
                    continue

                await websocket.send_json({"type": "transcript", "text": text})

                # Route through orchestrator
                if _message_handler:
                    try:
                        response = await _message_handler(
                            message=text, source="voice", metadata={"is_voice": True}
                        )
                    except Exception as e:
                        response = f"Error: {str(e)[:200]}"
                else:
                    response = "Orchestrator not connected."

                await websocket.send_json({"type": "response", "text": response[:300]})
                await websocket.send_json({"type": "status", "state": "speaking"})

                # Speak the response
                _speak(response[:500])

                # Wait for TTS to finish (rough estimate)
                await asyncio.sleep(max(2, len(response) / 20))
                await websocket.send_json({"type": "status", "state": "listening"})

    except WebSocketDisconnect:
        log.info("Voice client disconnected")


def run_voice_server(handler: Callable = None, port: int = 8080):
    import uvicorn
    if handler:
        set_handler(handler)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
