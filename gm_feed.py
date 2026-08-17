"""
gm_feed.py — GM Global live price feed (multi-symbol NFO)
=========================================================
Replaces the old Angel One SmartAPI feed. Subscribes to ALL symbols from
config.SYMBOLS over one socket and stores per-symbol prices keyed by
symbol name — same interface as before (connect / get_price / get_quote /
disconnect), so main.py only had to swap the class name.

HOW THE SITE ACTUALLY WORKS
---------------------------
gmglobal.org is an AngularJS front end with two independent halves:

  1. PHP session APIs on https://www.gmglobal.org/ajaxfiles/*.php — login,
     watchlist management, order placement. Cookie-session based.
  2. A Socket.IO tick feed on https://giantdata.org:3003 — this is the
     only thing that carries live prices, and it is NOT tied to the PHP
     session. You join a "room" per instrument and it pushes quotes.

So the login below is used to validate the account (and is what the
lot-size refresh in fetch_gm_lots.py rides on); the prices themselves come
off the socket. A failed login is therefore a warning, not a fatal error —
the feed still delivers quotes.

PROTOCOL NOTE
-------------
The server is Socket.IO 2.x / Engine.IO 3 (see the socket.io.js the site
ships: "Socket.IO v2.2.0"). The modern python-socketio client only speaks
Engine.IO 4 and cannot talk to it, so the handful of frames we need are
implemented directly on websocket-client — which the project already
depends on for motilal_feed.py. The wire format is small:

    "0{...}"          server → client, Engine.IO handshake (ping interval)
    "40"              server → client, Socket.IO namespace connected
    "2" / "3"         client ping / server pong  (EIO3 has the CLIENT ping)
    "42[event, arg]"  either direction, an event

INSTRUMENT IDENTIFIERS
----------------------
The site keys instruments as "<SCRIPT>-<EXPIRY CODE>", e.g. "RELIANCE-I",
where I is the near month. config.SYMBOLS names are "<SCRIPT> <DD-MON-YYYY>",
so the identifier is the first word plus GM_EXPIRY_CODE. A symbol can
override this with an explicit "gm_symbol" key if it ever diverges.

pip install websocket-client requests
"""

import json
import threading
import time

import requests
import websocket

from config import SYMBOLS, GM_EXPIRY_CODE

# Engine.IO 3 handshake, websocket transport only (no long-poll upgrade
# dance — we know the server supports websocket, the browser client
# upgrades to it immediately).
_SOCKET_URL = "wss://giantdata.org:3003/socket.io/?EIO=3&transport=websocket"

# How long recv() blocks before we loop round to check the stop flag.
_RECV_TIMEOUT = 5.0

# Backoff between reconnect attempts, seconds.
_RECONNECT_DELAY = 3.0


def gm_identifier(sym: dict) -> str:
    """config.SYMBOLS entry → GM Global instrument identifier."""
    override = sym.get("gm_symbol")
    if override:
        return override
    return f"{sym['name'].split(' ')[0]}-{GM_EXPIRY_CODE}"


class GmGlobalFeed:
    def __init__(self, config: dict):
        self.config = config
        self._prices = {}                 # name → {"buy", "sell", "ltp"}
        self._lock = threading.Lock()
        self._send_lock = threading.Lock()
        self._ws = None
        self._stop = threading.Event()
        self._session = None

        # identifier → display name, and the subscription list in one pass.
        self._id_to_name = {gm_identifier(s): s["name"] for s in SYMBOLS}
        self._ids = list(self._id_to_name)

    # ── Connect & authenticate ─────────────────────────────────────────────────
    def connect(self):
        self._login()

        self._stop.clear()
        threading.Thread(target=self._run, daemon=True).start()
        print("  ✅ GM Global feed connected.")

    def _login(self):
        """PHP session login. Best effort — see module docstring."""
        cfg = self.config
        base = cfg.get("base_url", "https://www.gmglobal.org")

        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0",
            "Content-Type": "application/json;charset=UTF-8",
            "Referer": base + "/",
        })
        try:
            res = session.post(
                f"{base}/ajaxfiles/logincheck.php",
                json={"username": cfg["user_id"], "password": cfg["password"]},
                timeout=20,
            ).json()
        except Exception as e:
            print(f"  ⚠️  GM Global login request failed ({e}) — "
                  f"continuing on the tick feed, which needs no session.")
            return

        if res.get("status") != "ok":
            print(f"  ⚠️  GM Global login rejected: {res.get('message')} — "
                  f"continuing on the tick feed, which needs no session.")
            return

        self._session = session
        print(f"  GM Global logged in as {cfg['user_id']} "
              f"({res.get('user_fname', '')}).")

    # ── Socket loop ────────────────────────────────────────────────────────────
    def _run(self):
        while not self._stop.is_set():
            try:
                self._session_once()
            except Exception as e:
                if not self._stop.is_set():
                    print(f"  ⚠️  GM Global socket error: {e}")
            if self._stop.is_set():
                break
            # The site's own client retries indefinitely (reconnectionAttempts
            # 300); mirror that rather than dying on the first blip.
            time.sleep(_RECONNECT_DELAY)

    def _session_once(self):
        ws = websocket.WebSocket()
        ws.connect(_SOCKET_URL, timeout=20)
        self._ws = ws

        # Engine.IO handshake tells us how often to ping. In EIO3 it is the
        # client that pings; miss it and the server drops the socket after
        # pingTimeout with no error of its own.
        handshake = json.loads(ws.recv()[1:])
        ping_interval = handshake.get("pingInterval", 25000) / 1000.0

        self._subscribe()

        pinger = threading.Thread(
            target=self._ping_loop, args=(ping_interval,), daemon=True)
        pinger.start()

        ws.settimeout(_RECV_TIMEOUT)
        try:
            while not self._stop.is_set():
                try:
                    msg = ws.recv()
                except websocket.WebSocketTimeoutException:
                    continue
                if not msg:
                    break
                self._on_packet(msg)
        finally:
            try:
                ws.close()
            except Exception:
                pass
            if self._ws is ws:
                self._ws = None

    def _ping_loop(self, interval: float):
        ws = self._ws
        while not self._stop.is_set() and self._ws is ws:
            if self._stop.wait(interval):
                return
            if not self._send("2"):
                return

    def _send(self, raw: str) -> bool:
        ws = self._ws
        if ws is None:
            return False
        try:
            with self._send_lock:
                ws.send(raw)
            return True
        except Exception:
            return False

    def _emit(self, event: str, payload) -> bool:
        return self._send("42" + json.dumps([event, payload]))

    def _subscribe(self):
        """Join the tick room for every symbol in config.SYMBOLS."""
        if not self._ids:
            print("  ⚠️  GM Global: config.SYMBOLS is empty, nothing to subscribe to")
            return
        self._emit("connected1", {"ty": 1})
        self._emit("connectMarketWatch", {"scripts": self._ids, "openScript": ""})
        # connectMarketWatch alone is what the site sends on (re)connect, but
        # its watchlist page also emits addMarketWatch per instrument — send
        # both so a symbol that is not on the account's saved watchlist still
        # gets a room.
        for iden in self._ids:
            self._emit("addMarketWatch", {"product": iden})

    def _on_packet(self, msg):
        # Text frames only in practice, but a stray binary frame would
        # otherwise blow up the whole session and cost a reconnect.
        if isinstance(msg, (bytes, bytearray)):
            try:
                msg = msg.decode("utf-8")
            except UnicodeDecodeError:
                return

        # "3" = pong to our ping, "40" = namespace connect, "2" = a server
        # ping we should pong. Anything else that isn't an event we ignore.
        if msg == "2":
            self._send("3")
            return
        if not msg.startswith("42"):
            return

        try:
            event, arg = json.loads(msg[2:])
        except Exception:
            return

        if event == "connectionSuccess":
            # Server re-armed the rooms; the site re-sends its subscription
            # here and so do we, otherwise a mid-session server restart
            # leaves us connected but silent.
            self._subscribe()
            return

        if event != "marketWatch":
            return

        data = (arg or {}).get("data")
        if not data:
            return

        name = self._id_to_name.get(data.get("InstrumentIdentifier"))
        if not name:
            return

        # Prices arrive in rupees already — no paise conversion, unlike Angel.
        with self._lock:
            self._prices[name] = {
                "buy":  data.get("BuyPrice"),
                "sell": data.get("SellPrice"),
                "ltp":  data.get("LastTradePrice"),
            }

    # ── Public API ─────────────────────────────────────────────────────────────
    def get_price(self, name: str) -> float | None:
        with self._lock:
            q = self._prices.get(name)
            return q["ltp"] if q else None

    def get_quote(self, name: str) -> dict | None:
        """Returns {buy, sell, ltp} or None."""
        with self._lock:
            return self._prices.get(name)

    def disconnect(self):
        self._stop.set()
        try:
            if self._ws:
                self._ws.close()
        except Exception:
            pass
