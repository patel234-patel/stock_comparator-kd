"""
web_dashboard.py — Real-time HTML dashboard over WebSocket
=============================================================
Replaces (or complements) the Excel live writer. Excel's ~100ms floor
comes from routing every tick through a single-threaded COM call into
another process; a browser tab has no such floor — it just applies
whatever JSON arrives over a WebSocket, so there is no per-tick write
latency to fight regardless of how many symbols (~208 here) are on
screen.

Two tiny servers run in daemon threads, started once at startup:
  - a plain HTTP server that serves web/dashboard.html (and nothing
    else — it's rooted at the isolated web/ folder, not the project
    root, so it can never serve config.py or other project files)
  - a WebSocket server that pushes the ranked comparison table to
    every connected browser tab as soon as it changes

pip install websockets
"""

import asyncio
import json
import logging
import threading
from html import escape
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterable, Optional

import websockets

log = logging.getLogger(__name__)

_WEB_DIR = Path(__file__).with_name("web")


class WebDashboard:
    def __init__(self, host: str = "127.0.0.1", http_port: int = 8000,
                 ws_port: int = 8765, diff_threshold: float = 50.0,
                 shard_label: str = ""):
        self._host = host
        self._http_port = http_port
        self._ws_port = ws_port
        self._diff_threshold = diff_threshold
        # Shown in the page title and header so two shards running side by
        # side are tellable apart at a glance — otherwise both browser tabs
        # look identical and it's easy to read the wrong half's prices.
        self._shard_label = shard_label

        self._clients = set()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._last_payload: Optional[str] = None

        self._http_server: Optional[ThreadingHTTPServer] = None
        self._ready = threading.Event()

        self._start_http()
        self._start_ws()
        if not self._ready.wait(timeout=5):
            log.warning("Web dashboard: WebSocket server did not confirm startup in time")

        print(f"  ✅ Web dashboard: http://{host}:{http_port}  (open this in a browser)")

    # ── HTTP: serves the single static dashboard.html ──────────────────────
    def _start_http(self):
        directory = str(_WEB_DIR)
        ws_port = self._ws_port
        shard_label = self._shard_label

        class Handler(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=directory, **kwargs)

            def log_message(self, fmt, *args):
                pass  # silence per-request access logging

            def do_GET(self):
                if self.path in ("", "/", "/dashboard.html"):
                    # Inject the WS port config.py actually bound, so the page
                    # never has a stale hardcoded value if WEB_WS_PORT changes.
                    html = (_WEB_DIR / "dashboard.html").read_text(encoding="utf-8")
                    html = html.replace("__WS_PORT__", str(ws_port))
                    html = html.replace("__SHARD_LABEL__", escape(shard_label))
                    body = html.encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                self.send_error(404)

        self._http_server = ThreadingHTTPServer((self._host, self._http_port), Handler)
        threading.Thread(target=self._http_server.serve_forever, daemon=True).start()

    # ── WebSocket: pushes ranked rows to every connected tab ───────────────
    def _start_ws(self):
        threading.Thread(target=self._run_ws_loop, daemon=True).start()

    def _run_ws_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._serve())
        except Exception as e:
            log.error(f"Web dashboard WS server crashed: {e}")

    async def _serve(self):
        async def handler(ws):
            self._clients.add(ws)
            try:
                if self._last_payload is not None:
                    await ws.send(self._last_payload)
                async for _ in ws:
                    pass  # dashboard is read-only; ignore anything a client sends
            finally:
                self._clients.discard(ws)

        async with websockets.serve(handler, self._host, self._ws_port, ping_interval=20):
            self._ready.set()
            await asyncio.Future()  # run until the process exits

    # ── Called from the main polling loop (sync context) ───────────────────
    def broadcast(self, ranked_rows: Iterable[dict], highlight_names: Iterable[str] = (),
                  ts: str = ""):
        if self._loop is None:
            return

        highlight_set = set(highlight_names)
        rows = []
        for r in ranked_rows:
            row = dict(r)
            row["highlighted"] = row.get("script_name") in highlight_set
            rows.append(row)

        message = json.dumps({
            "type": "update",
            "ts": ts,
            "diff_threshold": self._diff_threshold,
            "rows": rows,
        })
        self._last_payload = message
        asyncio.run_coroutine_threadsafe(self._broadcast_async(message), self._loop)

    async def _broadcast_async(self, message: str):
        if not self._clients:
            return
        dead = []
        for ws in list(self._clients):
            try:
                await ws.send(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._clients.discard(ws)

    def stop(self):
        try:
            if self._http_server:
                self._http_server.shutdown()
        except Exception:
            pass
        try:
            if self._loop:
                self._loop.call_soon_threadsafe(self._loop.stop)
        except Exception:
            pass
