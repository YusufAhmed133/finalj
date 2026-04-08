"""
JARVIS Dashboard — FastAPI admin panel at localhost:7000.

Shows:
- Live status (mode, uptime, intelligence tier)
- Memory search interface
- Memory statistics
- Knowledge scraping stats
- Action log
- Entity graph stats
"""
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

from jarvis.memory.spine import MemorySpine
from jarvis.memory.graph import EntityGraph
from jarvis.utils.logger import get_logger

log = get_logger("dashboard")

app = FastAPI(title="JARVIS Dashboard", version="3.0")

# Global references — set by main.py or standalone
_spine: MemorySpine = None
_graph: EntityGraph = None
_start_time: float = time.time()


def set_spine(spine: MemorySpine):
    global _spine
    _spine = spine


def set_graph(graph: EntityGraph):
    global _graph
    _graph = graph


@app.get("/", response_class=HTMLResponse)
async def index():
    """Main dashboard page."""
    spine = _spine or MemorySpine()
    graph = _graph or EntityGraph()

    mem_stats = spine.stats()
    graph_stats = graph.stats()
    uptime = int(time.time() - _start_time)
    uptime_str = f"{uptime // 3600}h {(uptime % 3600) // 60}m {uptime % 60}s"

    recent = spine.get_recent(hours=24, limit=10)
    recent_html = ""
    for mem in recent:
        content = (mem.get("content") or "")[:150].replace("<", "&lt;")
        tier = mem.get("tier", "?")
        mtype = mem.get("type", "?")
        recent_html += f'<tr><td>{tier}</td><td>{mtype}</td><td>{content}</td></tr>'

    top_entities = graph.most_mentioned(limit=10)
    entities_html = ""
    for entity in top_entities:
        entities_html += f'<tr><td>{entity["name"]}</td><td>{entity["type"]}</td><td>{entity["mention_count"]}</td></tr>'

    return f"""<!DOCTYPE html>
<html>
<head>
    <title>JARVIS Dashboard</title>
    <meta charset="utf-8">
    <meta http-equiv="refresh" content="30">
    <style>
        body {{ font-family: -apple-system, system-ui, sans-serif; margin: 0; padding: 20px; background: #0a0a0a; color: #e0e0e0; }}
        h1 {{ color: #4fc3f7; margin-bottom: 5px; }}
        h2 {{ color: #81c784; border-bottom: 1px solid #333; padding-bottom: 5px; }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; }}
        .card {{ background: #1a1a1a; border: 1px solid #333; border-radius: 8px; padding: 15px; }}
        .stat {{ font-size: 2em; font-weight: bold; color: #4fc3f7; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 0.9em; }}
        th, td {{ text-align: left; padding: 6px 10px; border-bottom: 1px solid #222; }}
        th {{ color: #aaa; }}
        .search {{ margin: 20px 0; }}
        .search input {{ padding: 8px 12px; width: 300px; background: #222; border: 1px solid #444; color: #fff; border-radius: 4px; }}
        .search button {{ padding: 8px 16px; background: #4fc3f7; color: #000; border: none; border-radius: 4px; cursor: pointer; }}
        a {{ color: #4fc3f7; text-decoration: none; }}
    </style>
</head>
<body>
    <h1>JARVIS v3.0</h1>
    <p>Uptime: {uptime_str} | Auto-refreshes every 30s</p>

    <div class="grid">
        <div class="card">
            <h2>Memory</h2>
            <div class="stat">{mem_stats['total']}</div>
            <p>total memories</p>
            <table>
                <tr><th>Tier</th><th>Count</th></tr>
                <tr><td>Hot (0-7d)</td><td>{mem_stats['by_tier'].get('hot', 0)}</td></tr>
                <tr><td>Warm (7-30d)</td><td>{mem_stats['by_tier'].get('warm', 0)}</td></tr>
                <tr><td>Cold (30-90d)</td><td>{mem_stats['by_tier'].get('cold', 0)}</td></tr>
                <tr><td>Archive (90d+)</td><td>{mem_stats['by_tier'].get('archive', 0)}</td></tr>
            </table>
        </div>

        <div class="card">
            <h2>Entity Graph</h2>
            <div class="stat">{graph_stats['total_entities']}</div>
            <p>entities, {graph_stats['total_relations']} relations</p>
            <table>
                <tr><th>Name</th><th>Type</th><th>Mentions</th></tr>
                {entities_html}
            </table>
        </div>

        <div class="card">
            <h2>Memory Types</h2>
            <table>
                <tr><th>Type</th><th>Count</th></tr>
                {''.join(f'<tr><td>{t}</td><td>{c}</td></tr>' for t, c in mem_stats.get('by_type', {}).items())}
            </table>
        </div>
    </div>

    <div class="search">
        <h2>Memory Search</h2>
        <form action="/search" method="get">
            <input type="text" name="q" placeholder="Search memories..." autofocus>
            <button type="submit">Search</button>
        </form>
    </div>

    <h2>Recent Memories (24h)</h2>
    <table>
        <tr><th>Tier</th><th>Type</th><th>Content</th></tr>
        {recent_html}
    </table>

    <p style="margin-top: 30px; color: #666;">
        <a href="/api/stats">API: /api/stats</a> |
        <a href="/api/search?q=test">API: /api/search?q=...</a> |
        <a href="/health">Health check</a>
    </p>
</body>
</html>"""


@app.get("/search", response_class=HTMLResponse)
async def search(q: str = ""):
    """Search memories."""
    spine = _spine or MemorySpine()
    results = spine.search_text(q, limit=20) if q else []

    results_html = ""
    for r in results:
        content = (r.get("content") or "")[:300].replace("<", "&lt;")
        tier = r.get("tier", "?")
        mtype = r.get("type", "?")
        ts = r.get("timestamp", "?")
        results_html += f'<tr><td>{tier}</td><td>{mtype}</td><td>{ts[:16]}</td><td>{content}</td></tr>'

    return f"""<!DOCTYPE html>
<html>
<head>
    <title>JARVIS Search: {q}</title>
    <style>
        body {{ font-family: -apple-system, system-ui, sans-serif; margin: 0; padding: 20px; background: #0a0a0a; color: #e0e0e0; }}
        h1 {{ color: #4fc3f7; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ text-align: left; padding: 6px 10px; border-bottom: 1px solid #222; }}
        th {{ color: #aaa; }}
        a {{ color: #4fc3f7; }}
        input {{ padding: 8px 12px; width: 300px; background: #222; border: 1px solid #444; color: #fff; border-radius: 4px; }}
        button {{ padding: 8px 16px; background: #4fc3f7; color: #000; border: none; border-radius: 4px; cursor: pointer; }}
    </style>
</head>
<body>
    <h1><a href="/">JARVIS</a> — Search</h1>
    <form action="/search" method="get">
        <input type="text" name="q" value="{q}" autofocus>
        <button type="submit">Search</button>
    </form>
    <p>{len(results)} results for "{q}"</p>
    <table>
        <tr><th>Tier</th><th>Type</th><th>Time</th><th>Content</th></tr>
        {results_html}
    </table>
</body>
</html>"""


@app.get("/api/stats")
async def api_stats():
    """API: Memory statistics."""
    spine = _spine or MemorySpine()
    graph = _graph or EntityGraph()
    return {
        "memory": spine.stats(),
        "graph": graph.stats(),
        "uptime_seconds": int(time.time() - _start_time),
    }


@app.get("/api/search")
async def api_search(q: str = "", limit: int = 10):
    """API: Search memories."""
    spine = _spine or MemorySpine()
    results = spine.search_text(q, limit=limit) if q else []
    return {"query": q, "count": len(results), "results": results}


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "version": "3.0"}


def run_dashboard(spine: MemorySpine = None, graph: EntityGraph = None, port: int = 7000):
    """Run the dashboard as a standalone server."""
    import uvicorn
    if spine:
        set_spine(spine)
    if graph:
        set_graph(graph)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
