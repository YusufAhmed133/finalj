"""
JARVIS Voice Interface — Iron Man orb at localhost:7777.

Architecture:
  Browser: Silero VAD (neural speech detection) → sends audio on speech end
  Server: Whisper transcribes → orchestrator routes → edge-tts generates audio
  Browser: plays audio, pauses VAD during playback to prevent echo loop

Admin dashboard at /admin.
"""
import asyncio
import base64
import json
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Optional, Callable

import edge_tts
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse

from jarvis.utils.logger import get_logger

log = get_logger("voice.server")

app = FastAPI(title="JARVIS")

_message_handler: Optional[Callable] = None
_whisper_model = None
_spine_ref = None
_graph_ref = None

TTS_DIR = Path("/tmp/jarvis_tts")
TTS_DIR.mkdir(exist_ok=True)

JARVIS_VOICE = "en-GB-RyanNeural"


def set_handler(handler: Callable):
    global _message_handler
    _message_handler = handler

def set_data(spine, graph):
    global _spine_ref, _graph_ref
    _spine_ref = spine
    _graph_ref = graph

def _get_whisper():
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        _whisper_model = WhisperModel("tiny", device="cpu", compute_type="int8")
        log.info("Whisper loaded")
    return _whisper_model


# ─── TTS endpoint ────────────────────────────────────────────────

@app.post("/api/tts")
async def tts_endpoint(request: Request):
    """Generate JARVIS speech audio. Returns audio/mpeg file."""
    body = await request.json()
    text = body.get("text", "")
    if not text:
        return JSONResponse({"error": "no text"}, 400)

    filename = TTS_DIR / f"jarvis_{uuid.uuid4().hex[:8]}.mp3"
    communicate = edge_tts.Communicate(text, voice=JARVIS_VOICE, rate="+5%", pitch="-2Hz")
    await communicate.save(str(filename))
    return FileResponse(str(filename), media_type="audio/mpeg")


# ─── Transcription endpoint ─────────────────────────────────────

@app.post("/api/transcribe")
async def transcribe_endpoint(request: Request):
    """Transcribe audio. Accepts base64 WAV in JSON body."""
    body = await request.json()
    audio_b64 = body.get("audio", "")
    if not audio_b64:
        return JSONResponse({"text": ""})

    audio_bytes = base64.b64decode(audio_b64)
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.write(audio_bytes)
    tmp.close()

    try:
        model = _get_whisper()
        segments, _ = model.transcribe(tmp.name, language="en", beam_size=5)
        text = " ".join(s.text.strip() for s in segments).strip()
    except Exception as e:
        log.error(f"Transcription error: {e}")
        text = ""
    finally:
        Path(tmp.name).unlink(missing_ok=True)

    return JSONResponse({"text": text})


# ─── Chat endpoint ──────────────────────────────────────────────

@app.post("/api/chat")
async def chat_endpoint(request: Request):
    """Send message through orchestrator."""
    body = await request.json()
    text = body.get("text", "")
    if not text or not _message_handler:
        return JSONResponse({"response": "Not connected."})

    try:
        response = await _message_handler(message=text, source="voice", metadata={"is_voice": True})
    except Exception as e:
        response = f"Error: {str(e)[:200]}"

    return JSONResponse({"response": response})


# ─── Main page: JARVIS Orb ──────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    return """<!DOCTYPE html>
<html>
<head>
<title>J.A.R.V.I.S.</title>
<meta charset="utf-8">
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
:root {
    --jarvis: #00d4ff;
    --glow: rgba(0, 212, 255, 0.4);
    --bg: #0a0e17;
}
body {
    background: var(--bg); overflow: hidden;
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    height: 100vh; font-family: 'Courier New', monospace;
    color: var(--jarvis); user-select: none;
}

/* Orb container */
.jarvis-container {
    position: relative; width: 220px; height: 220px;
}

/* Rotating rings */
.ring {
    position: absolute; inset: 0;
    border: 2px solid rgba(0, 212, 255, 0.15);
    border-top: 2px solid var(--jarvis);
    border-radius: 50%;
    animation: ring-spin 4s linear infinite;
}
.ring:nth-child(2) { inset: 18px; animation-duration: 6s; animation-direction: reverse; border-top-color: rgba(0,212,255,0.6); }
.ring:nth-child(3) { inset: 36px; animation-duration: 3s; border-top-color: rgba(0,212,255,0.4); }

/* Core orb */
.orb {
    position: absolute; inset: 55px; border-radius: 50%;
    background: radial-gradient(circle at 40% 40%, rgba(0,212,255,0.8), rgba(0,100,200,0.4) 50%, rgba(0,50,100,0.1) 70%, transparent);
    box-shadow: 0 0 30px var(--glow), 0 0 60px rgba(0,212,255,0.2), inset 0 0 30px rgba(0,212,255,0.1);
    animation: orb-idle 3s ease-in-out infinite;
    transition: all 0.3s ease;
}

/* States */
.orb.listening {
    animation: orb-listen 0.8s ease-in-out infinite;
    box-shadow: 0 0 50px rgba(0,212,255,0.6), 0 0 100px rgba(0,212,255,0.3), inset 0 0 40px rgba(0,212,255,0.2);
}
.orb.thinking {
    animation: orb-think 1.5s ease-in-out infinite;
    background: radial-gradient(circle at 40% 40%, rgba(255,183,77,0.9), rgba(245,124,0,0.5) 50%, transparent);
    box-shadow: 0 0 50px rgba(255,183,77,0.5), 0 0 100px rgba(255,183,77,0.2);
}
.orb.speaking {
    animation: orb-speak 0.15s ease-in-out infinite alternate;
    background: radial-gradient(circle at 40% 40%, rgba(0,255,200,0.9), rgba(0,200,255,0.5) 50%, transparent);
    box-shadow: 0 0 60px rgba(0,255,200,0.5), 0 0 120px rgba(0,212,255,0.3);
}
.orb.muted {
    background: radial-gradient(circle at 40% 40%, #444, #222, #111);
    box-shadow: 0 0 20px rgba(100,100,100,0.2);
    animation: none;
}

@keyframes ring-spin { to { transform: rotate(360deg); } }
@keyframes orb-idle { 0%,100% { transform: scale(1); opacity: 0.8; } 50% { transform: scale(1.04); opacity: 1; } }
@keyframes orb-listen { 0%,100% { transform: scale(1); } 50% { transform: scale(1.12); } }
@keyframes orb-think { 0%,100% { transform: scale(1) rotate(0deg); } 50% { transform: scale(1.06) rotate(180deg); } }
@keyframes orb-speak { from { transform: scale(1); } to { transform: scale(1.06); } }

/* Scan lines */
.jarvis-container::after {
    content: ''; position: absolute; inset: -50px;
    background: repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0,212,255,0.02) 2px, rgba(0,212,255,0.02) 4px);
    pointer-events: none; border-radius: 50%;
}

#status {
    margin-top: 30px; font-size: 11px; letter-spacing: 4px;
    text-transform: uppercase; opacity: 0.6;
}
#transcript {
    position: fixed; bottom: 80px; left: 50%; transform: translateX(-50%);
    max-width: 600px; text-align: center; font-size: 14px; color: #556; opacity: 0.8;
}
#response {
    position: fixed; bottom: 30px; left: 50%; transform: translateX(-50%);
    max-width: 700px; text-align: center; font-size: 16px; color: var(--jarvis);
    line-height: 1.4;
}
#nav { position: fixed; top: 15px; right: 20px; font-size: 11px; }
#nav a { color: rgba(0,212,255,0.4); text-decoration: none; letter-spacing: 2px; }
#nav a:hover { color: var(--jarvis); }
</style>
</head>
<body>
<div id="nav"><a href="/admin">ADMIN</a></div>

<div class="jarvis-container">
    <div class="ring"></div>
    <div class="ring"></div>
    <div class="ring"></div>
    <div class="orb" id="orb"></div>
</div>
<div id="status">INITIALIZING</div>
<div id="transcript"></div>
<div id="response"></div>

<!-- Silero VAD for neural speech detection -->
<script src="https://cdn.jsdelivr.net/npm/onnxruntime-web@1.14.0/dist/ort.js"></script>
<script src="https://cdn.jsdelivr.net/npm/@ricky0123/vad-web@0.0.19/dist/bundle.min.js"></script>

<script>
const orb = document.getElementById('orb');
const statusEl = document.getElementById('status');
const transcriptEl = document.getElementById('transcript');
const responseEl = document.getElementById('response');

let currentAudio = null;
let vadInstance = null;
let isMuted = false;

function setState(state) {
    orb.className = 'orb ' + state;
    statusEl.textContent = state.toUpperCase() || 'STANDBY';
}

// Convert Float32Array (16kHz mono) to WAV blob
function float32ToWav(samples, sr) {
    const buf = new ArrayBuffer(44 + samples.length * 2);
    const v = new DataView(buf);
    const ws = (o, s) => { for(let i=0;i<s.length;i++) v.setUint8(o+i, s.charCodeAt(i)); };
    ws(0,'RIFF'); v.setUint32(4, 36+samples.length*2, true);
    ws(8,'WAVE'); ws(12,'fmt '); v.setUint32(16,16,true);
    v.setUint16(20,1,true); v.setUint16(22,1,true);
    v.setUint32(24,sr,true); v.setUint32(28,sr*2,true);
    v.setUint16(32,2,true); v.setUint16(34,16,true);
    ws(36,'data'); v.setUint32(40,samples.length*2,true);
    for(let i=0;i<samples.length;i++) {
        const s = Math.max(-1, Math.min(1, samples[i]));
        v.setInt16(44+i*2, s<0?s*0x8000:s*0x7FFF, true);
    }
    return new Blob([buf], {type:'audio/wav'});
}

async function handleSpeech(audio) {
    // audio = Float32Array from Silero VAD at 16kHz
    setState('thinking');
    transcriptEl.textContent = 'Processing...';

    // Convert to WAV and base64
    const wavBlob = float32ToWav(audio, 16000);
    const reader = new FileReader();
    const b64 = await new Promise(resolve => {
        reader.onload = () => resolve(reader.result.split(',')[1]);
        reader.readAsDataURL(wavBlob);
    });

    // Transcribe
    let text = '';
    try {
        const res = await fetch('/api/transcribe', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({audio: b64})
        });
        const data = await res.json();
        text = data.text || '';
    } catch(e) {
        console.error('Transcribe error:', e);
        setState('listening');
        return;
    }

    if (!text || text.trim().length < 2) {
        setState('listening');
        transcriptEl.textContent = '';
        return;
    }

    // Check voice commands
    const lower = text.toLowerCase().trim();
    if (lower.includes('jarvis mute') || lower === 'mute') {
        isMuted = true;
        setState('muted');
        transcriptEl.textContent = '';
        return;
    }
    if (lower.includes('jarvis unmute') || lower === 'unmute') {
        isMuted = false;
        setState('listening');
        transcriptEl.textContent = '';
        return;
    }

    transcriptEl.textContent = text;

    // Get response from JARVIS
    let response = '';
    try {
        const res = await fetch('/api/chat', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({text})
        });
        const data = await res.json();
        response = data.response || 'No response.';
    } catch(e) {
        response = 'Connection error.';
    }

    responseEl.textContent = response.substring(0, 400);

    // Speak the response — PAUSE VAD first to prevent echo
    if (vadInstance) vadInstance.pause();
    setState('speaking');

    try {
        const ttsRes = await fetch('/api/tts', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({text: response.substring(0, 500)})
        });
        const audioBlob = await ttsRes.blob();
        const audioUrl = URL.createObjectURL(audioBlob);
        currentAudio = new Audio(audioUrl);
        currentAudio.play();

        await new Promise(resolve => {
            currentAudio.addEventListener('ended', resolve);
            currentAudio.addEventListener('error', resolve);
        });
    } catch(e) {
        console.error('TTS error:', e);
    }

    // Resume VAD after TTS + buffer
    await new Promise(r => setTimeout(r, 600));
    if (vadInstance && !isMuted) vadInstance.start();
    setState('listening');
    setTimeout(() => { responseEl.textContent = ''; transcriptEl.textContent = ''; }, 5000);
}

async function init() {
    setState('initializing');
    try {
        vadInstance = await vad.MicVAD.new({
            positiveSpeechThreshold: 0.85,
            negativeSpeechThreshold: 0.35,
            minSpeechFrames: 5,
            preSpeechPadFrames: 10,
            redemptionFrames: 8,
            onSpeechStart: () => {
                if (!isMuted) setState('listening');
            },
            onSpeechEnd: (audio) => {
                if (!isMuted) handleSpeech(audio);
            },
        });
        vadInstance.start();
        setState('listening');
    } catch(e) {
        console.error('VAD init error:', e);
        statusEl.textContent = 'MIC ACCESS REQUIRED';
    }
}

init();
</script>
</body>
</html>"""


# ─── Admin Dashboard ─────────────────────────────────────────────

@app.get("/admin", response_class=HTMLResponse)
async def admin():
    from jarvis.memory.spine import MemorySpine
    from jarvis.memory.graph import EntityGraph
    spine = _spine_ref or MemorySpine()
    graph = _graph_ref or EntityGraph()
    mem = spine.stats()
    gs = graph.stats()
    recent = spine.get_recent(hours=24, limit=15)
    rows = ""
    for m in recent:
        c = (m.get("content") or "")[:150].replace("<", "&lt;")
        rows += f'<tr><td>{m.get("tier","?")}</td><td>{m.get("type","?")}</td><td>{c}</td></tr>'
    return f"""<!DOCTYPE html><html><head><title>JARVIS Admin</title>
<style>body{{background:#0a0e17;color:#e0e0e0;font-family:'Courier New',monospace;padding:20px}}
h1{{color:#00d4ff}}h2{{color:#81c784;border-bottom:1px solid #1a2030;padding-bottom:5px}}
table{{width:100%;border-collapse:collapse;font-size:0.85em}}
th,td{{text-align:left;padding:6px 10px;border-bottom:1px solid #1a2030}}th{{color:#556}}
.stat{{font-size:2.5em;color:#00d4ff;font-weight:bold}}
a{{color:#00d4ff;text-decoration:none}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:20px}}
.card{{background:#0d1117;border:1px solid #1a2030;border-radius:8px;padding:15px}}</style></head><body>
<h1><a href="/">← J.A.R.V.I.S.</a> // ADMIN</h1>
<div class="grid">
<div class="card"><h2>MEMORY</h2><div class="stat">{mem['total']}</div>
<p>Hot: {mem['by_tier'].get('hot',0)} | Warm: {mem['by_tier'].get('warm',0)} | Cold: {mem['by_tier'].get('cold',0)} | Archive: {mem['by_tier'].get('archive',0)}</p></div>
<div class="card"><h2>ENTITIES</h2><div class="stat">{gs['total_entities']}</div><p>{gs['total_relations']} relations</p></div></div>
<h2>RECENT ACTIVITY</h2><table><tr><th>Tier</th><th>Type</th><th>Content</th></tr>{rows}</table>
<h2>SEARCH</h2><form action="/admin/search"><input name="q" placeholder="Search memories..." style="padding:8px;width:300px;background:#0d1117;border:1px solid #1a2030;color:#e0e0e0;border-radius:4px;font-family:monospace">
<button style="padding:8px 16px;background:#00d4ff;color:#000;border:none;border-radius:4px;cursor:pointer;font-family:monospace">SEARCH</button></form></body></html>"""

@app.get("/admin/search", response_class=HTMLResponse)
async def admin_search(q: str = ""):
    from jarvis.memory.spine import MemorySpine
    spine = _spine_ref or MemorySpine()
    results = spine.search_text(q, limit=20) if q else []
    rows = "".join(f'<tr><td>{r.get("tier","?")}</td><td>{(r.get("content") or "")[:200]}</td></tr>' for r in results)
    return f"""<!DOCTYPE html><html><head><title>Search: {q}</title>
<style>body{{background:#0a0e17;color:#e0e0e0;font-family:monospace;padding:20px}}
h1{{color:#00d4ff}}table{{width:100%;border-collapse:collapse}}
th,td{{text-align:left;padding:6px;border-bottom:1px solid #1a2030}}a{{color:#00d4ff}}</style></head><body>
<h1><a href="/admin">← ADMIN</a> // SEARCH: {q}</h1><p>{len(results)} results</p>
<table><tr><th>Tier</th><th>Content</th></tr>{rows}</table></body></html>"""

@app.get("/health")
async def health():
    return {"status": "ok", "version": "3.0"}
