"""
angel_feed.py — Angel One SmartAPI live price feed (multi-symbol NFO)
======================================================================
Subscribes to ALL symbols from config.SYMBOLS in one WebSocket session.
Stores per-symbol prices in a dict keyed by symbol name.

pip install smartapi-python pyotp
"""

import pyotp
import threading
from SmartApi import SmartConnect
from SmartApi.smartWebSocketV2 import SmartWebSocketV2

from config import SYMBOLS


class AngelOneFeed:
    def __init__(self, config: dict):
        self.config   = config
        self._prices  = {}          # name → {"buy": float, "sell": float}
        self._lock    = threading.Lock()
        self._api     = None
        self._ws      = None

        # Build token → name lookup from SYMBOLS list
        # Each symbol entry must have angel_token set in config.py
        self._token_to_name = {
            str(sym["angel_token"]): sym["name"]
            for sym in SYMBOLS
            if sym.get("angel_token") and sym["angel_token"] != "FILL_IN"
        }

    # ── Connect & authenticate ─────────────────────────────────────────────────
    def connect(self):
        cfg = self.config
        self._api = SmartConnect(api_key=cfg["api_key"])

        totp = pyotp.TOTP(cfg["totp_secret"]).now()
        data = self._api.generateSession(
            clientCode=cfg["client_id"],
            password=cfg["password"],
            totp=totp,
        )

        if data["status"] is False:
            raise ConnectionError(f"Angel One login failed: {data['message']}")

        auth_token  = data["data"]["jwtToken"]
        feed_token  = self._api.getfeedToken()
        client_code = cfg["client_id"]

        self._ws = SmartWebSocketV2(
            auth_token=auth_token,
            api_key=cfg["api_key"],
            client_code=client_code,
            feed_token=feed_token,
        )

        self._ws.on_open  = self._on_open
        self._ws.on_data  = self._on_data
        self._ws.on_error = self._on_error
        self._ws.on_close = self._on_close

        t = threading.Thread(target=self._ws.connect, daemon=True)
        t.start()
        print("  ✅ Angel One WebSocket connected.")

    def _on_open(self, ws):
        """Subscribe to ALL symbols from config at once (Mode 2 = Quote: bid+ask)."""
        tokens = [
            {"exchangeType": 2, "tokens": [str(sym["angel_token"])]}
            for sym in SYMBOLS
            if sym.get("angel_token") and sym["angel_token"] != "FILL_IN"
        ]
        if not tokens:
            print("  ⚠️  Angel One: no valid tokens found in config.SYMBOLS")
            return
        # exchangeType 2 = NFO
        self._ws.subscribe("angel_feed", 3, tokens)   # Mode 3 = Snap Quote (bid/ask/LTP)

    def _on_data(self, ws, message):
        """Parse incoming tick. Snap Quote includes best_5_buy_data / best_5_sell_data."""
        try:
            token = str(message.get("token", ""))
            name  = self._token_to_name.get(token)
            if not name:
                return

            # LTP (always present)
            ltp = message.get("last_traded_price", 0) / 100  # paise → ₹

            # Best bid/ask (present in Mode 3)
            buy_data  = message.get("best_5_buy_data",  [])
            sell_data = message.get("best_5_sell_data", [])

            best_bid = (buy_data[0].get("price",  0) / 100) if buy_data  else ltp
            best_ask = (sell_data[0].get("price", 0) / 100) if sell_data else ltp

            with self._lock:
                self._prices[name] = {"buy": best_bid, "sell": best_ask, "ltp": ltp}

        except Exception:
            pass

    def _on_error(self, ws, error):
        print(f"  ⚠️  Angel One WS error: {error}")

    def _on_close(self, ws, *args):
        print("  Angel One WS closed.")

    # ── Public API ─────────────────────────────────────────────────────────────
    def get_price(self, name: str) -> float | None:
        with self._lock:
            q = self._prices.get(name)
            return q["ltp"] if q else None

    def get_quote(self, name: str) -> dict | None:
        """Returns {buy, sell} or None."""
        with self._lock:
            return self._prices.get(name)

    def disconnect(self):
        try:
            if self._ws:
                self._ws.close_connection()
        except Exception:
            pass