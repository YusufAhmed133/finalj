"""
JARVIS Voice Interface — Arc Reactor UI at localhost:7777.

Uses browser-native Web Speech API for instant transcription (no Whisper delay).
edge-tts en-GB-RyanNeural for JARVIS voice.
Admin dashboard at /admin.
"""
import asyncio
import json
import uuid
from pathlib import Path
from typing import Optional, Callable

import edge_tts
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse

from jarvis.utils.logger import get_logger

log = get_logger("voice.server")

app = FastAPI(title="JARVIS")

_message_handler: Optional[Callable] = None
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


@app.post("/api/tts")
async def tts_endpoint(request: Request):
    body = await request.json()
    text = body.get("text", "").strip()
    if not text:
        return JSONResponse({"error": "no text"}, 400)
    # Clean response — remove thinking/meta artifacts
    for prefix in ["Thinking", "Processing", "Let me", "Hmm,"]:
        if text.startswith(prefix) and "..." in text[:50]:
            text = text[text.index("...") + 3:].strip()
    filename = TTS_DIR / f"j_{uuid.uuid4().hex[:8]}.mp3"
    communicate = edge_tts.Communicate(text[:800], voice=JARVIS_VOICE, rate="+5%", pitch="-2Hz")
    await communicate.save(str(filename))
    return FileResponse(str(filename), media_type="audio/mpeg")


@app.on_event("startup")
async def startup_event():
    """Pre-generate ack audio on startup if missing."""
    ack_dir = TTS_DIR / "ack"
    ack_dir.mkdir(exist_ok=True)
    acks = {
        "ack1.mp3": "Yes sir.", "ack2.mp3": "Right away.",
        "ack3.mp3": "On it.", "ack4.mp3": "One moment.",
        "ack5.mp3": "Understood.",
        "ack6.mp3": "Still working on that, one moment please.",
    }
    for fname, text in acks.items():
        path = ack_dir / fname
        if not path.exists():
            try:
                c = edge_tts.Communicate(text, voice=JARVIS_VOICE, rate="+5%", pitch="-2Hz")
                await c.save(str(path))
                log.info(f"Pre-cached {fname}")
            except Exception:
                pass


@app.get("/api/ack")
async def ack_endpoint():
    """Return a random pre-cached acknowledgment audio instantly."""
    import random
    ack_dir = Path("/tmp/jarvis_tts/ack")
    files = list(ack_dir.glob("ack[1-5].mp3"))  # ack6 is the longer one for 6s+ waits
    if files:
        return FileResponse(str(random.choice(files)), media_type="audio/mpeg")
    return JSONResponse({"error": "no ack files"}, 404)


@app.get("/api/ack/long")
async def ack_long_endpoint():
    """Return the longer acknowledgment for 6s+ waits."""
    path = Path("/tmp/jarvis_tts/ack/ack6.mp3")
    if path.exists():
        return FileResponse(str(path), media_type="audio/mpeg")
    return JSONResponse({"error": "no ack file"}, 404)


@app.post("/api/chat")
async def chat_endpoint(request: Request):
    body = await request.json()
    text = body.get("text", "").strip()
    if not text or not _message_handler:
        return JSONResponse({"response": "Not connected."})

    # Fast path: instant Mac commands bypass LLM entirely (<100ms)
    from jarvis.agents.instant_mac import try_instant_command
    log.info(f"Voice chat: '{text}'")
    instant = try_instant_command(text)
    if instant:
        log.info(f"Instant command: {instant}")
        return JSONResponse({"response": instant, "instant": True})
    log.info("Not instant, routing to Claude...")

    try:
        response = await _message_handler(message=text, source="voice", metadata={"is_voice": True})
        # Clean any thinking artifacts from response
        if response:
            for noise in ["Thinking...", "Processing...", "Let me think..."]:
                response = response.replace(noise, "").strip()
    except Exception as e:
        response = f"Error: {str(e)[:200]}"
    return JSONResponse({"response": response or "No response."})


@app.get("/", response_class=HTMLResponse)
async def index():
    return ARC_REACTOR_HTML


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
h1{{color:#00d4ff}}h2{{color:#4fc3f7;border-bottom:1px solid #1a2030;padding-bottom:5px}}
table{{width:100%;border-collapse:collapse;font-size:0.85em}}
th,td{{text-align:left;padding:6px 10px;border-bottom:1px solid #1a2030}}th{{color:#556}}
.stat{{font-size:2.5em;color:#00d4ff;font-weight:bold}}
a{{color:#00d4ff;text-decoration:none}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:20px}}
.card{{background:#0d1117;border:1px solid #1a2030;border-radius:8px;padding:15px}}</style></head><body>
<h1><a href="/">← J.A.R.V.I.S.</a> // ADMIN</h1>
<div class="grid">
<div class="card"><h2>MEMORY</h2><div class="stat">{mem['total']}</div>
<p>Hot:{mem['by_tier'].get('hot',0)} Warm:{mem['by_tier'].get('warm',0)} Cold:{mem['by_tier'].get('cold',0)} Archive:{mem['by_tier'].get('archive',0)}</p></div>
<div class="card"><h2>ENTITIES</h2><div class="stat">{gs['total_entities']}</div><p>{gs['total_relations']} relations</p></div></div>
<h2>RECENT</h2><table><tr><th>Tier</th><th>Type</th><th>Content</th></tr>{rows}</table>
<h2>SEARCH</h2><form action="/admin/search"><input name="q" placeholder="Search..." style="padding:8px;width:300px;background:#0d1117;border:1px solid #1a2030;color:#e0e0e0;border-radius:4px;font-family:monospace">
<button style="padding:8px 16px;background:#00d4ff;color:#000;border:none;border-radius:4px">SEARCH</button></form></body></html>"""

@app.get("/admin/search", response_class=HTMLResponse)
async def admin_search(q: str = ""):
    from html import escape
    from jarvis.memory.spine import MemorySpine
    spine = _spine_ref or MemorySpine()
    safe_q = escape(q)
    results = spine.search_text(q, limit=20) if q else []
    rows = "".join(f'<tr><td>{r.get("tier","?")}</td><td>{escape((r.get("content") or "")[:200])}</td></tr>' for r in results)
    return f"""<!DOCTYPE html><html><head><title>Search: {safe_q}</title>
<style>body{{background:#0a0e17;color:#e0e0e0;font-family:monospace;padding:20px}}
h1{{color:#00d4ff}}table{{width:100%;border-collapse:collapse}}
th,td{{text-align:left;padding:6px;border-bottom:1px solid #1a2030}}a{{color:#00d4ff}}</style></head><body>
<h1><a href="/admin">←</a> SEARCH: {q}</h1><p>{len(results)} results</p>
<table><tr><th>Tier</th><th>Content</th></tr>{rows}</table></body></html>"""

@app.get("/health")
async def health():
    return {"status": "ok", "version": "3.0"}


# ─── Arc Reactor UI ──────────────────────────────────────────────

ARC_REACTOR_HTML = r"""<!DOCTYPE html>
<html>
<head>
<title>J.A.R.V.I.S.</title>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body {
    background: #070b14; overflow: hidden;
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    height: 100vh; font-family: 'Courier New', monospace;
    color: #00d4ff;
}

/* Arc reactor container */
.reactor {
    position: relative; width: 400px; height: 400px;
    display: flex; align-items: center; justify-content: center;
}

/* Concentric rings */
.ring {
    position: absolute; border-radius: 50%;
    border: 1px solid rgba(0,180,255,0.2);
}
.ring-1 { width: 380px; height: 380px; border-width: 2px; border-color: rgba(0,180,255,0.15); animation: spin 20s linear infinite; }
.ring-2 { width: 320px; height: 320px; border-width: 2px; border-style: dashed; border-color: rgba(0,180,255,0.25); animation: spin 15s linear infinite reverse; }
.ring-3 { width: 260px; height: 260px; border-width: 3px; border-color: rgba(0,200,255,0.3); animation: spin 10s linear infinite; }
.ring-4 { width: 200px; height: 200px; border-width: 2px; border-style: dotted; border-color: rgba(0,212,255,0.35); animation: spin 8s linear infinite reverse; }
.ring-5 { width: 150px; height: 150px; border-width: 3px; border-color: rgba(0,220,255,0.5); animation: spin 5s linear infinite; }

/* Tick marks on rings */
.ring-1::before, .ring-3::before {
    content: ''; position: absolute; top: -1px; left: 50%;
    width: 2px; height: 12px; background: rgba(0,212,255,0.5);
    transform: translateX(-50%);
}
.ring-1::after, .ring-3::after {
    content: ''; position: absolute; bottom: -1px; left: 50%;
    width: 2px; height: 12px; background: rgba(0,212,255,0.5);
    transform: translateX(-50%);
}

/* Data segments on outer ring */
.data-seg {
    position: absolute; font-size: 7px; letter-spacing: 2px;
    color: rgba(0,180,255,0.4);
}
.data-seg.top { top: 5px; }
.data-seg.bottom { bottom: 5px; }
.data-seg.left { left: -10px; top: 50%; transform: rotate(-90deg); }
.data-seg.right { right: -10px; top: 50%; transform: rotate(90deg); }

/* Core glow */
.core {
    width: 100px; height: 100px; border-radius: 50%;
    background: radial-gradient(circle, rgba(0,220,255,0.6) 0%, rgba(0,150,255,0.2) 50%, transparent 70%);
    box-shadow: 0 0 40px rgba(0,200,255,0.3), 0 0 80px rgba(0,180,255,0.15);
    display: flex; align-items: center; justify-content: center;
    z-index: 10; position: relative;
    transition: all 0.4s ease;
}
.core-text {
    font-size: 11px; letter-spacing: 5px; font-weight: bold;
    color: rgba(0,220,255,0.9); text-shadow: 0 0 10px rgba(0,200,255,0.5);
}

/* Waveform bars around core */
.wave-container {
    position: absolute; width: 130px; height: 130px;
    display: flex; align-items: center; justify-content: center;
    z-index: 5;
}
.wave-bar {
    position: absolute; width: 2px; background: rgba(0,200,255,0.4);
    transform-origin: center 65px; border-radius: 1px;
    transition: height 0.1s ease, background 0.3s ease;
}

/* States */
.reactor.listening .core {
    box-shadow: 0 0 60px rgba(0,200,255,0.5), 0 0 120px rgba(0,180,255,0.25);
}
.reactor.listening .wave-bar { background: rgba(0,200,255,0.7); }
.reactor.listening .ring { border-color: rgba(0,200,255,0.4); }

.reactor.thinking .core {
    background: radial-gradient(circle, rgba(255,180,50,0.6) 0%, rgba(255,120,0,0.2) 50%, transparent 70%);
    box-shadow: 0 0 60px rgba(255,150,0,0.4), 0 0 100px rgba(255,120,0,0.2);
}
.reactor.thinking .wave-bar { background: rgba(255,180,50,0.6); }
.reactor.thinking .ring { border-color: rgba(255,180,50,0.3); }
.reactor.thinking .core-text { color: rgba(255,200,100,0.9); }

.reactor.speaking .core {
    background: radial-gradient(circle, rgba(0,255,180,0.6) 0%, rgba(0,200,150,0.2) 50%, transparent 70%);
    box-shadow: 0 0 60px rgba(0,255,180,0.4), 0 0 100px rgba(0,220,150,0.2);
}
.reactor.speaking .wave-bar { background: rgba(0,255,180,0.7); }
.reactor.speaking .ring { border-color: rgba(0,255,180,0.3); }
.reactor.speaking .core-text { color: rgba(0,255,180,0.9); }

@keyframes spin { to { transform: rotate(360deg); } }

/* Status + text */
#status {
    margin-top: 25px; font-size: 10px; letter-spacing: 5px;
    text-transform: uppercase; opacity: 0.5;
}
#transcript {
    position: fixed; bottom: 120px; left: 50%; transform: translateX(-50%);
    max-width: 600px; text-align: center; font-size: 13px;
    color: rgba(0,180,255,0.5); opacity: 0.7;
}
#response {
    position: fixed; bottom: 65px; left: 50%; transform: translateX(-50%);
    max-width: 700px; text-align: center; font-size: 15px;
    color: #00d4ff; line-height: 1.4;
}
/* Controls bar */
#controls {
    position: fixed; bottom: 15px; left: 50%; transform: translateX(-50%);
    display: flex; gap: 8px; align-items: center;
}
#textInput {
    width: 350px; padding: 8px 14px;
    background: rgba(0,180,255,0.08); border: 1px solid rgba(0,180,255,0.25);
    border-radius: 20px; color: #00d4ff; font-family: 'Courier New', monospace;
    font-size: 13px; outline: none;
}
#textInput::placeholder { color: rgba(0,180,255,0.3); }
#textInput:focus { border-color: rgba(0,180,255,0.5); background: rgba(0,180,255,0.12); }
.ctrl-btn {
    padding: 8px 14px; border: 1px solid rgba(0,180,255,0.25);
    background: rgba(0,180,255,0.08); color: rgba(0,180,255,0.6);
    border-radius: 20px; font-family: 'Courier New', monospace;
    font-size: 11px; letter-spacing: 2px; cursor: pointer;
    text-transform: uppercase; transition: all 0.2s;
}
.ctrl-btn:hover { background: rgba(0,180,255,0.15); color: #00d4ff; border-color: rgba(0,180,255,0.5); }
.ctrl-btn.active { background: rgba(255,80,80,0.15); border-color: rgba(255,80,80,0.4); color: rgba(255,80,80,0.7); }
#nav { position: fixed; top: 12px; right: 18px; font-size: 10px; letter-spacing: 3px; }
#nav a { color: rgba(0,180,255,0.3); text-decoration: none; }
#nav a:hover { color: #00d4ff; }

/* Scan lines */
body::after {
    content: ''; position: fixed; inset: 0;
    background: repeating-linear-gradient(0deg, transparent, transparent 3px, rgba(0,180,255,0.015) 3px, rgba(0,180,255,0.015) 6px);
    pointer-events: none; z-index: 100;
}
</style>
</head>
<body>
<div id="nav"><a href="/admin">ADMIN</a></div>

<div class="reactor" id="reactor">
    <div class="ring ring-1">
        <span class="data-seg top">0010110100</span>
        <span class="data-seg bottom">1101001011</span>
    </div>
    <div class="ring ring-2"></div>
    <div class="ring ring-3">
        <span class="data-seg left">SYSTEMS</span>
        <span class="data-seg right">ONLINE</span>
    </div>
    <div class="ring ring-4"></div>
    <div class="ring ring-5"></div>
    <div class="wave-container" id="waveContainer"></div>
    <div class="core"><span class="core-text">J.A.R.V.I.S</span></div>
</div>
<div id="status">STANDBY</div>
<div id="transcript"></div>
<div id="response"></div>
<div id="controls">
    <input type="text" id="textInput" placeholder="Type a command..." autocomplete="off">
    <button class="ctrl-btn" id="muteBtn" onclick="toggleMute()">MIC ON</button>
</div>

<script>
const reactor = document.getElementById('reactor');
const statusEl = document.getElementById('status');
const transcriptEl = document.getElementById('transcript');
const responseEl = document.getElementById('response');
const waveContainer = document.getElementById('waveContainer');

// Create waveform bars around the core
const NUM_BARS = 36;
const bars = [];
for (let i = 0; i < NUM_BARS; i++) {
    const bar = document.createElement('div');
    bar.className = 'wave-bar';
    bar.style.transform = `rotate(${i * (360/NUM_BARS)}deg)`;
    bar.style.height = '3px';
    bar.style.top = '0px';
    waveContainer.appendChild(bar);
    bars.push(bar);
}

let audioContext, analyser, micStream;
let isProcessing = false;
let recognition;

function setState(state) {
    reactor.className = 'reactor ' + state;
    statusEl.textContent = state.toUpperCase() || 'STANDBY';
}

// Animate wave bars from mic input
function animateWaves() {
    if (!analyser) { requestAnimationFrame(animateWaves); return; }
    const data = new Uint8Array(analyser.frequencyBinCount);
    analyser.getByteFrequencyData(data);
    for (let i = 0; i < NUM_BARS; i++) {
        const idx = Math.floor(i * data.length / NUM_BARS);
        const val = data[idx] / 255;
        bars[i].style.height = (3 + val * 25) + 'px';
    }
    requestAnimationFrame(animateWaves);
}

// Use Web Speech API — instant, accurate, no server round-trip
function startListening() {
    if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
        statusEl.textContent = 'SPEECH API NOT SUPPORTED';
        return;
    }

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = 'en-AU';

    let finalTranscript = '';
    let silenceTimeout;

    recognition.onresult = (event) => {
        if (isProcessing) return;
        let interim = '';
        finalTranscript = '';
        for (let i = event.resultIndex; i < event.results.length; i++) {
            if (event.results[i].isFinal) {
                finalTranscript += event.results[i][0].transcript;
            } else {
                interim += event.results[i][0].transcript;
            }
        }

        if (interim) {
            setState('listening');
            transcriptEl.textContent = interim;
        }

        if (finalTranscript.trim()) {
            clearTimeout(silenceTimeout);
            silenceTimeout = setTimeout(() => {
                if (finalTranscript.trim().length > 1 && !isProcessing) {
                    processCommand(finalTranscript.trim());
                }
            }, 500);
        }
    };

    recognition.onend = () => {
        if (!isProcessing && micEnabled) {
            recognition.start(); // Auto-restart only if mic enabled
        }
    };

    recognition.onerror = (e) => {
        if (e.error !== 'no-speech' && e.error !== 'aborted') {
            console.error('Speech error:', e.error);
        }
    };

    recognition.start();
    setState('listening');
}

async function processCommand(text) {
    isProcessing = true;
    recognition.stop();

    transcriptEl.textContent = text;
    setState('thinking');

    // Check voice commands
    const lower = text.toLowerCase();
    if (lower.includes('jarvis mute') || lower === 'mute') {
        setState('standby');
        statusEl.textContent = 'MUTED';
        isProcessing = false;
        return;
    }

    try {
        responseEl.textContent = '...';

        // Play acknowledgment audio IMMEDIATELY while Claude thinks
        const ackPromise = fetch('/api/ack').then(r => r.blob()).then(b => {
            const ackAudio = new Audio(URL.createObjectURL(b));
            ackAudio.play();
        }).catch(() => {});

        // Fetch response from Claude IN PARALLEL with ack audio
        const chatPromise = fetch('/api/chat', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({text})
        }).then(r => r.json());

        // If chat takes > 6s, play longer ack
        const longAckTimer = setTimeout(async () => {
            try {
                const r = await fetch('/api/ack/long');
                const b = await r.blob();
                new Audio(URL.createObjectURL(b)).play();
            } catch(e) {}
        }, 6000);

        const chatData = await chatPromise;
        clearTimeout(longAckTimer);
        const response = chatData.response || 'No response.';

        responseEl.textContent = response.substring(0, 400);
        setState('speaking');

        // Generate and play TTS for the actual response
        const ttsRes = await fetch('/api/tts', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({text: response.substring(0, 500)})
        });
        const audioBlob = await ttsRes.blob();
        const audio = new Audio(URL.createObjectURL(audioBlob));
        audio.play();

        await new Promise(resolve => {
            audio.onended = resolve;
            audio.onerror = resolve;
        });

    } catch(e) {
        responseEl.textContent = 'Connection error.';
        console.error(e);
    }

    isProcessing = false;
    transcriptEl.textContent = '';
    setTimeout(() => { responseEl.textContent = ''; }, 5000);
    if (micEnabled) {
        setState('listening');
        recognition.start();
    } else {
        setState('');
        statusEl.textContent = 'MIC OFF';
    }
}

// Init mic for waveform visualization
async function initMic() {
    try {
        micStream = await navigator.mediaDevices.getUserMedia({audio: true});
        audioContext = new AudioContext();
        analyser = audioContext.createAnalyser();
        analyser.fftSize = 256;
        const source = audioContext.createMediaStreamSource(micStream);
        source.connect(analyser);
        animateWaves();
    } catch(e) {
        console.error('Mic error:', e);
    }
}

// Text input handler
const textInput = document.getElementById('textInput');
const muteBtn = document.getElementById('muteBtn');
let micEnabled = true;

textInput.addEventListener('keydown', async (e) => {
    if (e.key === 'Enter' && textInput.value.trim()) {
        const text = textInput.value.trim();
        textInput.value = '';
        transcriptEl.textContent = text;
        await processCommand(text);
    }
});

function toggleMute() {
    micEnabled = !micEnabled;
    if (micEnabled) {
        muteBtn.textContent = 'MIC ON';
        muteBtn.classList.remove('active');
        if (recognition) recognition.start();
        setState('listening');
    } else {
        muteBtn.textContent = 'MIC OFF';
        muteBtn.classList.add('active');
        if (recognition) recognition.stop();
        setState('');
        statusEl.textContent = 'MIC OFF';
    }
}

initMic();
if (micEnabled) startListening();
</script>
</body>
</html>"""
