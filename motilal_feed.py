# """
# motilal_feed.py — Motilal Oswal OpenAPI live price feed (multi-symbol NFO)
# ===========================================================================
# Subscribes to ALL symbols from config.SYMBOLS.
# Stores per-symbol prices keyed by symbol name.

# WHY THIS VERSION IS DIFFERENT FROM YOUR ORIGINAL
# -------------------------------------------------
# Your logs showed: login OK, access token OK, WS "connected" ... but
# 0/5 symbols ever went live, and the socket eventually died with
# WinError 10054 / read timeouts. That pattern (auth fine, but zero data,
# then the server drops you) means the *subscribe* message was being
# rejected silently. Two confirmed bugs caused that:

#   1. WS "Register" message used "Exchange": "NFO" and "ExchangeType": "D".
#      Motilal's own docs state the WebSocket Broadcast API only accepts:
#          Exchange     = "BSE" or "NSE"
#          Exchange Type = "CASH" or "DERIVATIVES"
#      ("NFO" / "D" are not valid values for this websocket call at all —
#      they silently get ignored, so you get a "connected" socket that
#      never emits a single tick.)

#   2. REST LTP fallback used "exchange": "NFO". Motilal's documented
#      exchange enum is: NSE, BSE, NSEFO, NSECD, MCX, BSEFO — there is no
#      "NFO" in their system, only "NSEFO".

# IMPORTANT CAVEAT
# ----------------
# Motilal's public API docs show WebSocket scrip registration only as SDK
# pseudocode (Mofsl.Register("BSE","CASH",532543)), not as a raw JSON
# wire message — unlike the Trade WebSocket, which IS documented as raw
# JSON. The {"action":"Register", "Exchange":..., "ExchangeType":...,
# "ScripCode":...} message below is my best-effort reconstruction of that
# wire format based on the documented parameter names and the pattern used
# elsewhere in their API (Trade WebSocket auth uses the same clientid/
# apikey/authtoken shape). It is NOT guaranteed to be byte-for-byte what
# their server expects.

# Because of that uncertainty, this version treats WS as "best effort" and
# adds a REST polling loop as the *guaranteed* data source — the REST
# getltpdata endpoint IS fully documented and is what actually worked in
# your logs before the exchange-value bug. get_price()/get_quote() always
# return the freshest value between WS and REST, so if the WS format
# guess above is wrong, you still get live prices (just via REST on the
# poll interval instead of true tick-by-tick).

# If you want guaranteed tick-by-tick, the safest long-term route is to
# `pip install` Motilal's official SDK (github.com/motradingapi/PythonSDK)
# and call `Mofsl.Register("NSE", "DERIVATIVES", scripcode)` directly from
# their library instead of hand-rolling the socket JSON — that removes the
# guesswork entirely.

# pip install websocket-client pyotp requests
# """

# import hashlib
# import json
# import threading
# import time
# import socket

# import requests

# try:
#     import websocket
# except ImportError:
#     websocket = None

# try:
#     import pyotp
# except ImportError:
#     pyotp = None

# from config import SYMBOLS

# BASE_URL = "https://openapi.motilaloswal.com"
# WS_URL   = "wss://openapi.motilaloswal.com/ws"

# # How often the REST poller refreshes each symbol (seconds).
# # Keep this >= 1s per symbol-ish to stay well clear of rate limits.
# REST_POLL_INTERVAL = 1.5

# # If WS hasn't updated a symbol in this many seconds, treat WS data as
# # stale and prefer REST for that symbol.
# WS_STALE_AFTER = 5.0


# def _sha256(text: str) -> str:
#     return hashlib.sha256(text.encode()).hexdigest()


# def _get_local_ip() -> str:
#     try:
#         return socket.gethostbyname(socket.gethostname())
#     except Exception:
#         return "127.0.0.1"


# class MotilalFeed:
#     def __init__(self, config: dict):
#         self.config        = config
#         self._ws_prices    = {}      # name -> {"buy","sell","ltp","ts"}
#         self._rest_prices  = {}      # name -> {"buy","sell","ltp","ts"}
#         self._lock         = threading.Lock()
#         self._auth_token   = None
#         self._access_token = None
#         self._ws_app       = None
#         self._stop_poll    = threading.Event()
#         self._poll_thread  = None

#         # Build scrip -> name lookup from SYMBOLS
#         self._scrip_to_name = {
#             sym["mo_scrip"]: sym["name"]
#             for sym in SYMBOLS
#             if sym.get("mo_scrip")
#         }

#     # ── Step 1: Login → AuthToken ──────────────────────────────────────────────
#     def _login(self) -> str:
#         cfg = self.config

#         raw_password = cfg["password"]
#         api_key      = cfg["market_api_key"]
#         hashed_pw    = _sha256(raw_password + api_key)

#         totp_code = cfg.get("totp_code")
#         if not totp_code:
#             if pyotp is None:
#                 raise ImportError("Run: pip install pyotp")
#             totp_code = pyotp.TOTP(cfg["totp_secret"]).now()

#         payload = {
#             "userid":   cfg["client_code"],
#             "password": hashed_pw,
#             "2FA":      cfg["two_fa"],
#             "totp":     totp_code,
#         }
#         headers = self._common_headers(auth_token=None, access_token=None)

#         resp = requests.post(
#             f"{BASE_URL}/rest/login/v7/authdirectapi",
#             json=payload, headers=headers, timeout=10
#         )
#         print("  [MO] Login status:", resp.status_code)
#         print("  [MO] Login raw body:", repr(resp.text))
#         resp.raise_for_status()

#         decoder = json.JSONDecoder()
#         data, _ = decoder.raw_decode(resp.text.strip())

#         if data.get("status") != "SUCCESS":
#             raise ConnectionError(f"Motilal login failed: {data}")

#         return data["AuthToken"]

#     # ── Step 2: Generate AccessToken ──────────────────────────────────────────
#     def _get_access_token(self) -> str:
#         headers = self._common_headers(auth_token=self._auth_token, access_token=None)
#         resp = requests.post(
#             f"{BASE_URL}/rest/login/v1/getaccesstoken",
#             headers=headers, timeout=10
#         )
#         print("  [MO] AccessToken status:", resp.status_code)
#         print("  [MO] AccessToken raw body:", repr(resp.text))
#         resp.raise_for_status()

#         decoder = json.JSONDecoder()
#         data, _ = decoder.raw_decode(resp.text.strip())

#         if data.get("status") != "SUCCESS":
#             raise ConnectionError(f"Motilal getaccesstoken failed: {data}")

#         return data["accesstoken"]

#     # ── Common headers ─────────────────────────────────────────────────────────
#     def _common_headers(self, auth_token, access_token) -> dict:
#         cfg      = self.config
#         local_ip = _get_local_ip()
#         headers  = {
#             "Accept":           "application/json",
#             "User-Agent":       "MOSL/V.1.1.0",
#             "ApiKey":           cfg["market_api_key"],
#             "apisecretkey":     cfg["api_secret_key"],
#             "ClientLocalIp":    local_ip,
#             "ClientPublicIp":   local_ip,
#             "MacAddress":       "00:00:00:00:00:00",
#             "SourceId":         "WEB",
#             "vendorinfo":       cfg["client_code"],
#             "osname":           "Windows 10",
#             "osversion":        "10.0",
#             "devicemodel":      "PC",
#             "manufacturer":     "DELL",
#             "productname":      "StockComparator",
#             "productversion":   "1.0",
#             "browsername":      "Chrome",
#             "browserversion":   "125.0",
#         }
#         if auth_token:
#             headers["Authorization"] = auth_token
#         if access_token:
#             headers["accesstoken"] = access_token
#         return headers

#     # ── Public connect ─────────────────────────────────────────────────────────
#     def connect(self):
#         print("  [MO] Step 1 — Login ...")
#         self._auth_token = self._login()

#         print("  [MO] Step 2 — Get access token ...")
#         self._access_token = self._get_access_token()

#         print("  [MO] Step 3 — Connect WebSocket (best-effort) ...")
#         try:
#             self._start_ws()
#         except Exception as e:
#             print(f"  ⚠️  Motilal WS setup failed, continuing on REST polling only: {e}")

#         print("  [MO] Step 4 — Start REST polling loop (guaranteed data source) ...")
#         self._start_rest_poller()

#         print("  ✅ Motilal Oswal feed ready (WS best-effort + REST polling).")

#     # ── WebSocket (best-effort — see module docstring caveat) ─────────────────
#     def _start_ws(self):
#         auth_token   = self._auth_token
#         access_token = self._access_token
#         cfg          = self.config

#         def on_open(ws):
#             # Authorize (this shape IS documented — matches Trade WebSocket auth)
#             ws.send(json.dumps({
#                 "clientid":  cfg["client_code"],
#                 "authtoken": auth_token,
#                 "apikey":    cfg["market_api_key"],
#             }))
#             time.sleep(0.5)

#             # Subscribe to all NFO symbols.
#             # Exchange must be "NSE"/"BSE" and ExchangeType must be
#             # "CASH"/"DERIVATIVES" per Motilal's docs — NOT "NFO"/"D".
#             for sym in SYMBOLS:
#                 scrip = sym.get("mo_scrip")
#                 if scrip:
#                     ws.send(json.dumps({
#                         "clientid":     cfg["client_code"],
#                         "action":       "Register",
#                         "Exchange":     "NSE",
#                         "ExchangeType": "DERIVATIVES",
#                         "ScripCode":    scrip,
#                     }))

#         def on_message(ws, message):
#             try:
#                 msg = json.loads(message)

#                 scrip_code = (
#                     msg.get("Scrip Code")
#                     or msg.get("ScripCode")
#                     or msg.get("scripcode")
#                 )
#                 if scrip_code is None:
#                     return

#                 name = self._scrip_to_name.get(int(scrip_code))
#                 if not name:
#                     return

#                 # Different quote packet types carry different fields
#                 # (LTP packet vs MarketDepth packet — see Motilal docs).
#                 ltp = msg.get("LTP_Rate")
#                 bid = msg.get("BidRate")
#                 ask = msg.get("OfferRate")

#                 with self._lock:
#                     existing = self._ws_prices.get(name, {})
#                     if ltp is not None:
#                         existing["ltp"] = float(ltp)
#                     if bid is not None:
#                         existing["buy"] = float(bid)
#                     if ask is not None:
#                         existing["sell"] = float(ask)
#                     existing["ts"] = time.time()
#                     self._ws_prices[name] = existing
#             except Exception:
#                 pass

#         def on_error(ws, error):
#             print(f"  ⚠️  Motilal WS error: {error}")

#         def on_close(ws, *args):
#             print("  Motilal WS closed.")

#         if websocket is None:
#             raise ImportError("Run: pip install websocket-client")

#         self._ws_app = websocket.WebSocketApp(
#             WS_URL,
#             on_open=on_open,
#             on_message=on_message,
#             on_error=on_error,
#             on_close=on_close,
#         )

#         t = threading.Thread(
#             target=self._ws_app.run_forever,
#             kwargs={"ping_interval": 30},
#             daemon=True,
#         )
#         t.start()
#         time.sleep(1)

#     # ── REST polling (guaranteed — fully documented endpoint) ─────────────────
#     def _start_rest_poller(self):
#         t = threading.Thread(target=self._rest_poll_loop, daemon=True)
#         t.start()
#         self._poll_thread = t

#     def _rest_poll_loop(self):
#         while not self._stop_poll.is_set():
#             for sym in SYMBOLS:
#                 if self._stop_poll.is_set():
#                     break
#                 name = sym["name"]
#                 quote = self._fetch_quote_rest(name)
#                 if quote:
#                     with self._lock:
#                         quote["ts"] = time.time()
#                         self._rest_prices[name] = quote
#                 time.sleep(REST_POLL_INTERVAL / max(len(SYMBOLS), 1))

#     def _fetch_quote_rest(self, name: str) -> dict | None:
#         """REST getltpdata — exchange must be 'NSEFO' for F&O scrips
#         (Motilal's enum is NSE/BSE/NSEFO/NSECD/MCX/BSEFO — there is no
#         'NFO')."""
#         sym = next((s for s in SYMBOLS if s["name"] == name), None)
#         if not sym:
#             return None

#         headers = self._common_headers(self._auth_token, self._access_token)
#         payload = {
#             "exchange":  "NSEFO",   # was "NFO" — invalid, always errored/timed out
#             "scripcode": sym["mo_scrip"],
#         }
#         try:
#             resp = requests.post(
#                 f"{BASE_URL}/rest/report/v3/getltpdata",
#                 json=payload, headers=headers, timeout=5
#             )
#             data = resp.json()
#             if data.get("status") == "SUCCESS":
#                 d = data["data"]
#                 # Confirmed: Motilal's NSEFO getltpdata response is in
#                 # paisa (e.g. 153230 -> ₹1532.30), same as their cash LTP
#                 # endpoint. Divide by 100 to match Angel One's rupee units.
#                 bid = float(d.get("bid", d.get("ltp", 0))) / 100
#                 ask = float(d.get("ask", d.get("ltp", 0))) / 100
#                 ltp = float(d.get("ltp", 0)) / 100
#                 return {"buy": bid, "sell": ask, "ltp": ltp}
#             else:
#                 print(f"  [MO] REST LTP error ({name}): {data.get('message')}")
#         except Exception as e:
#             print(f"  [MO] REST LTP error ({name}): {e}")
#         return None

#     # ── Public API ─────────────────────────────────────────────────────────────
#     def get_price(self, name: str) -> float | None:
#         quote = self.get_quote(name)
#         return quote["ltp"] if quote else None

#     def get_quote(self, name: str) -> dict | None:
#         """Returns {buy, sell, ltp} using whichever source (WS or REST)
#         is freshest for this symbol."""
#         with self._lock:
#             ws_q   = self._ws_prices.get(name)
#             rest_q = self._rest_prices.get(name)

#         now = time.time()
#         ws_fresh   = ws_q and (now - ws_q.get("ts", 0)) < WS_STALE_AFTER
#         rest_fresh = rest_q is not None

#         if ws_fresh and (not rest_fresh or ws_q["ts"] >= rest_q["ts"]):
#             return {"buy": ws_q.get("buy", ws_q.get("ltp")),
#                     "sell": ws_q.get("sell", ws_q.get("ltp")),
#                     "ltp": ws_q.get("ltp")}
#         if rest_fresh:
#             return {"buy": rest_q["buy"], "sell": rest_q["sell"], "ltp": rest_q["ltp"]}
#         return None

#     def disconnect(self):
#         self._stop_poll.set()
#         try:
#             if self._ws_app:
#                 self._ws_app.close()
#         except Exception:
#             pass
"""
motilal_feed.py — Motilal Oswal feed (WS best-effort + throttled REST fallback)
"""

import hashlib
import json
import threading
import time
import socket

import requests

try:
    import websocket
except ImportError:
    websocket = None

try:
    import pyotp
except ImportError:
    pyotp = None

from config import SYMBOLS

BASE_URL = "https://openapi.motilaloswal.com"
WS_URL   = "wss://openapi.motilaloswal.com/ws"

REST_POLL_INTERVAL = 3.0   # seconds between REST polls per symbol (was 1.5 — too fast)
WS_STALE_AFTER     = 5.0


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _get_local_ip() -> str:
    try:
        return socket.gethostbyname(socket.gethostname())
    except Exception:
        return "127.0.0.1"


class MotilalFeed:
    def __init__(self, config: dict):
        self.config        = config
        self._ws_prices    = {}
        self._rest_prices  = {}
        self._lock         = threading.Lock()
        self._auth_token   = None
        self._access_token = None
        self._ws_app       = None
        self._stop_poll    = threading.Event()

        # REST error throttle — only print an error once per symbol per N seconds
        self._last_rest_error_ts = {}   # name → timestamp of last printed error
        self._REST_ERR_QUIET = 30.0    # seconds between repeated error prints

        self._scrip_to_name = {
            sym["mo_scrip"]: sym["name"]
            for sym in SYMBOLS if sym.get("mo_scrip")
        }

    # ── Auth helpers ───────────────────────────────────────────────────────────
    def _common_headers(self, auth_token=None, access_token=None) -> dict:
        cfg = self.config
        local_ip = _get_local_ip()
        h = {
            "Accept": "application/json", "User-Agent": "MOSL/V.1.1.0",
            "ApiKey": cfg["market_api_key"], "apisecretkey": cfg["api_secret_key"],
            "ClientLocalIp": local_ip, "ClientPublicIp": local_ip,
            "MacAddress": "00:00:00:00:00:00", "SourceId": "WEB",
            "vendorinfo": cfg["client_code"], "osname": "Windows 10",
            "osversion": "10.0", "devicemodel": "PC", "manufacturer": "DELL",
            "productname": "StockComparator", "productversion": "1.0",
            "browsername": "Chrome", "browserversion": "125.0",
        }
        if auth_token:   h["Authorization"] = auth_token
        if access_token: h["accesstoken"]   = access_token
        return h

    def _login(self) -> str:
        cfg       = self.config
        hashed_pw = _sha256(cfg["password"] + cfg["market_api_key"])
        totp_code = cfg.get("totp_code") or pyotp.TOTP(cfg["totp_secret"]).now()
        payload   = {"userid": cfg["client_code"], "password": hashed_pw,
                     "2FA": cfg["two_fa"], "totp": totp_code}
        resp = requests.post(f"{BASE_URL}/rest/login/v7/authdirectapi",
                             json=payload, headers=self._common_headers(), timeout=10)
        print("  [MO] Login status:", resp.status_code)
        print("  [MO] Login raw body:", repr(resp.text))
        resp.raise_for_status()
        data = json.loads(resp.text.strip())
        if data.get("status") != "SUCCESS":
            raise ConnectionError(f"Motilal login failed: {data}")
        return data["AuthToken"]

    def _get_access_token(self) -> str:
        resp = requests.post(f"{BASE_URL}/rest/login/v1/getaccesstoken",
                             headers=self._common_headers(self._auth_token), timeout=10)
        print("  [MO] AccessToken status:", resp.status_code)
        resp.raise_for_status()
        data = json.loads(resp.text.strip())
        if data.get("status") != "SUCCESS":
            raise ConnectionError(f"Motilal getaccesstoken failed: {data}")
        return data["accesstoken"]

    # ── Connect ────────────────────────────────────────────────────────────────
    def connect(self):
        print("  [MO] Step 1 — Login ...")
        self._auth_token = self._login()
        print("  [MO] Step 2 — Get access token ...")
        self._access_token = self._get_access_token()
        print("  [MO] Step 3 — Connect WebSocket (best-effort) ...")
        try:
            self._start_ws()
        except Exception as e:
            print(f"  ⚠️  Motilal WS failed, using REST only: {e}")
        print("  [MO] Step 4 — Start REST polling loop ...")
        self._start_rest_poller()
        print("  ✅ Motilal Oswal feed ready.")

    # ── WebSocket ──────────────────────────────────────────────────────────────
    def _start_ws(self):
        auth_token = self._auth_token
        cfg        = self.config

        def on_open(ws):
            ws.send(json.dumps({"clientid": cfg["client_code"],
                                "authtoken": auth_token,
                                "apikey":    cfg["market_api_key"]}))
            time.sleep(0.5)
            for sym in SYMBOLS:
                scrip = sym.get("mo_scrip")
                if scrip:
                    ws.send(json.dumps({"clientid":     cfg["client_code"],
                                        "action":       "Register",
                                        "Exchange":     "NSE",
                                        "ExchangeType": "DERIVATIVES",
                                        "ScripCode":    scrip}))

        def on_message(ws, message):
            try:
                msg        = json.loads(message)
                scrip_code = msg.get("Scrip Code") or msg.get("ScripCode") or msg.get("scripcode")
                if scrip_code is None:
                    return
                name = self._scrip_to_name.get(int(scrip_code))
                if not name:
                    return
                ltp = msg.get("LTP_Rate")
                bid = msg.get("BidRate")
                ask = msg.get("OfferRate")
                with self._lock:
                    e = self._ws_prices.get(name, {})
                    if ltp is not None: e["ltp"]  = float(ltp)
                    if bid is not None: e["buy"]  = float(bid)
                    if ask is not None: e["sell"] = float(ask)
                    e["ts"] = time.time()
                    self._ws_prices[name] = e
            except Exception:
                pass

        def on_error(ws, error):
            print(f"  ⚠️  Motilal WS error: {error}")

        def on_close(ws, *args):
            print("  Motilal WS closed.")

        if websocket is None:
            raise ImportError("pip install websocket-client")

        self._ws_app = websocket.WebSocketApp(
            WS_URL, on_open=on_open, on_message=on_message,
            on_error=on_error, on_close=on_close)
        threading.Thread(target=self._ws_app.run_forever,
                         kwargs={"ping_interval": 30}, daemon=True).start()
        time.sleep(1)

    # ── REST polling (throttled, quiet on repeated errors) ────────────────────
    def _start_rest_poller(self):
        threading.Thread(target=self._rest_poll_loop, daemon=True).start()

    def _rest_poll_loop(self):
        while not self._stop_poll.is_set():
            for sym in SYMBOLS:
                if self._stop_poll.is_set():
                    break
                name  = sym["name"]
                quote = self._fetch_quote_rest(name)
                if quote:
                    with self._lock:
                        quote["ts"] = time.time()
                        self._rest_prices[name] = quote
                # Space out requests: total cycle = REST_POLL_INTERVAL per symbol
                time.sleep(REST_POLL_INTERVAL / max(len(SYMBOLS), 1))

    def _fetch_quote_rest(self, name: str) -> dict | None:
        sym = next((s for s in SYMBOLS if s["name"] == name), None)
        if not sym:
            return None
        headers = self._common_headers(self._auth_token, self._access_token)
        payload = {"exchange": "NSEFO", "scripcode": sym["mo_scrip"]}
        try:
            resp = requests.post(f"{BASE_URL}/rest/report/v3/getltpdata",
                                 json=payload, headers=headers, timeout=5)
            data = resp.json()
            if data.get("status") == "SUCCESS":
                d   = data["data"]
                ltp = float(d.get("ltp", 0)) / 100
                bid = float(d.get("bid", d.get("ltp", 0))) / 100
                ask = float(d.get("ask", d.get("ltp", 0))) / 100
                # Clear any stale error record on success
                self._last_rest_error_ts.pop(name, None)
                return {"buy": bid, "sell": ask, "ltp": ltp}
            else:
                self._maybe_print_error(name, f"REST status not SUCCESS: {data.get('message')}")
        except Exception as e:
            self._maybe_print_error(name, str(e))
        return None

    def _maybe_print_error(self, name: str, msg: str):
        """Print REST errors at most once per _REST_ERR_QUIET seconds per symbol."""
        now  = time.time()
        last = self._last_rest_error_ts.get(name, 0)
        if now - last >= self._REST_ERR_QUIET:
            # Shorten the error message — no need for the full stack
            short = msg.split("\n")[0][:120]
            print(f"  [MO] REST error ({name}): {short}")
            self._last_rest_error_ts[name] = now

    # ── Public API ─────────────────────────────────────────────────────────────
    def get_price(self, name: str) -> float | None:
        q = self.get_quote(name)
        return q["ltp"] if q else None

    def get_quote(self, name: str) -> dict | None:
        with self._lock:
            ws_q   = self._ws_prices.get(name)
            rest_q = self._rest_prices.get(name)
        now        = time.time()
        ws_fresh   = ws_q and (now - ws_q.get("ts", 0)) < WS_STALE_AFTER
        rest_fresh = rest_q is not None
        if ws_fresh and (not rest_fresh or ws_q["ts"] >= rest_q["ts"]):
            return {"buy": ws_q.get("buy", ws_q.get("ltp")),
                    "sell": ws_q.get("sell", ws_q.get("ltp")),
                    "ltp": ws_q.get("ltp")}
        if rest_fresh:
            return {"buy": rest_q["buy"], "sell": rest_q["sell"], "ltp": rest_q["ltp"]}
        return None

    def disconnect(self):
        self._stop_poll.set()
        try:
            if self._ws_app:
                self._ws_app.close()
        except Exception:
            pass