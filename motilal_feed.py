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
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

try:
    import pyotp
except ImportError:
    pyotp = None

# Motilal's real Broadcast WS is a raw binary-struct protocol at
# wss://ws1feed.motilaloswal.com/jwebsocket/jwebsocket — NOT JSON at
# openapi.motilaloswal.com/ws (confirmed by reading the official
# motradingapi/PythonSDK source directly). That's why REST-only ever
# gives you buy=sell=ltp: getltpdata has no bid/ask fields at all — real
# bid/ask only exists in the WS MarketDepth broadcast. We vendor and drive
# the real SDK (MOFSLOPENAPI.py, next to this file) for the WS layer only;
# REST polling below is untouched from the original.
try:
    from MOFSLOPENAPI import MOFSLOPENAPI

    class _MotilalBroadcastClient(MOFSLOPENAPI):
        """MOFSLOPENAPI has no callback/queue mechanism of its own — per its
        source, _Broadcast_on_open/_Broadcast_on_message are no-op stubs
        meant to be filled in by subclassing. These hooks are it."""

        def __init__(self, *args, on_ready=None, on_tick=None, on_raw_message=None, **kwargs):
            super().__init__(*args, **kwargs)
            self._on_ready = on_ready
            self._on_tick  = on_tick
            self._on_raw_message = on_raw_message

        def Packet_Parsing(self, message):
            # Fires for EVERY incoming frame, including server heartbeats,
            # which never reach _Broadcast_on_message — the only reliable
            # "is the socket actually alive" signal independent of trades.
            if self._on_raw_message:
                try:
                    self._on_raw_message()
                except Exception:
                    pass
            super().Packet_Parsing(message)

        def _Broadcast_on_open(self, ws1):
            if self._on_ready:
                try:
                    self._on_ready()
                except Exception:
                    pass

        def _Broadcast_on_message(self, ws1, message_type, message):
            if self._on_tick:
                try:
                    self._on_tick(message_type, message)
                except Exception:
                    pass
except ImportError:
    MOFSLOPENAPI = None
    _MotilalBroadcastClient = None

from config import SYMBOLS

BASE_URL = "https://openapi.motilaloswal.com"

REST_POLL_INTERVAL = 3.0   # seconds between REST polls per symbol (was 1.5 — too fast)
REST_POLL_WORKERS  = 15    # concurrent REST requests in flight — keeps a full poll
# cycle roughly flat as symbol count grows, instead of scaling linearly with N
# (serial polling of 200 symbols could take 60-90s per cycle).
WS_STALE_AFTER     = 600.0  # was 5.0, then 60.0 — still too short: outside
# market hours the SDK's internal watchdog only reconnects (and re-sends a
# per-symbol snapshot) roughly every ~6.5 minutes when there's no organic
# tick activity, observed directly in price_updates.log. A 60s window meant
# real WS bid/ask was "stale" and fell back to REST's fake buy=sell=ltp for
# most of that ~6.5min gap. 600s comfortably covers that reconnect cadence;
# during live market hours, genuine ticks arrive far more often than this
# anyway, so it won't mask an actual mid-day WS failure in practice.


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
        self._mo_sdk       = None   # official SDK instance driving the WS layer
        self._rest_executor = None  # created in _start_rest_poller
        self._stop_poll    = threading.Event()
        self._ws_msg_count = 0
        self._ws_first_msg_seen = False

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

    # ── WebSocket (real binary Broadcast protocol, via vendored SDK) ──────────
    def _start_ws(self):
        if _MotilalBroadcastClient is None:
            raise ImportError(
                "Motilal WS needs MOFSLOPENAPI.py's deps: pip install websocket-client geocoder"
            )

        cfg = self.config
        totp_code = cfg.get("totp_code") or pyotp.TOTP(cfg["totp_secret"]).now()

        self._mo_sdk = _MotilalBroadcastClient(
            f_apikey=cfg["market_api_key"],
            f_Base_Url=BASE_URL,
            f_clientcode=cfg["client_code"],
            f_strSourceID="WEB",
            f_browsername="Chrome",
            f_browserversion="125.0",
            f_apisecretkey=cfg["api_secret_key"],
            on_ready=self._on_ws_ready,
            on_tick=self._on_ws_tick,
            on_raw_message=self._on_ws_raw_message,
        )

        login_resp = self._mo_sdk.login(
            cfg["client_code"], cfg["password"], cfg["two_fa"], totp_code,
            f_vendorinfo=cfg["client_code"],  # SDK defaults this to None -> MO2012
            # "Vendor Info Tag is Invalid" if omitted; our own working REST
            # login (_common_headers) already sends vendorinfo=client_code.
        )
        if login_resp.get("status") != "SUCCESS":
            raise ConnectionError(f"Motilal WS login failed: {login_resp}")

        # MOFSLOPENAPI.Register() only enforces a real per-account broadcast
        # cap if m_MaxBroadcastLimit was set from this call — otherwise it
        # silently falls back to a hardcoded 200. If the account's real limit
        # is lower, symbols past it get dropped from WS with just a console
        # print and permanently depend on REST polling. Query it up front so
        # Register() enforces the true cap and we know at startup, not later,
        # how many of our symbols can actually be live.
        try:
            limit_resp = self._mo_sdk.getbroadcastmaxlimit(cfg["client_code"])
            if limit_resp.get("status") == "SUCCESS":
                real_limit = limit_resp.get("data", {}).get("MaxBroadcastLimit")
                if real_limit:
                    self._mo_sdk.m_MaxBroadcastLimit = int(real_limit)
                    if len(SYMBOLS) > real_limit:
                        print(f"  ⚠️  {len(SYMBOLS)} symbols configured but your "
                              f"account's real WS broadcast limit is {real_limit}. "
                              f"The extra {len(SYMBOLS) - real_limit} will never "
                              f"get live WS ticks and will depend on REST polling.")
            else:
                print(f"  ⚠️  Couldn't fetch real broadcast limit "
                      f"({limit_resp.get('message')}); SDK will default to 200.")
        except Exception as e:
            print(f"  ⚠️  getbroadcastmaxlimit check failed, SDK will default to 200: {e}")

        self._mo_sdk.Broadcast_connect()
        time.sleep(1)

    def _on_ws_ready(self):
        """Fires from the SDK's on_open hook once the Broadcast socket is up.
        NSE/DERIVATIVES matches Motilal's documented WS enum for F&O scrips
        (Exchange must be NSE/BSE, ExchangeType must be CASH/DERIVATIVES)."""
        print("  [MO] WS connected — registering symbols ...")
        for sym in SYMBOLS:
            scrip = sym.get("mo_scrip")
            if scrip:
                self._mo_sdk.Register("NSE", "DERIVATIVES", int(scrip))

    def _on_ws_raw_message(self):
        """Fires for every raw frame the server sends (heartbeats included) —
        the only way to tell "socket alive, just quiet" apart from "silently
        dead" when no LTP/MarketDepth ticks are arriving."""
        self._ws_msg_count += 1
        if not self._ws_first_msg_seen:
            self._ws_first_msg_seen = True
            print("  [MO] WS: first frame received from server — socket confirmed alive.")

    def _on_ws_tick(self, message_type, message):
        """message_type is 'LTP' or 'MarketDepth', message is the SDK's
        already-decoded dict — field names like 'Scrip Code' (with a space)
        and 'LTP_Rate'/'BidRate'/'OfferRate' come straight from the SDK
        source, not guessed. This is the only real source of Motilal
        bid/ask — REST's getltpdata has no such fields at all."""
        scrip_code = message.get("Scrip Code")
        if scrip_code is None:
            return
        name = self._scrip_to_name.get(int(scrip_code))
        if not name:
            return

        with self._lock:
            e = self._ws_prices.get(name, {})
            if message_type == "LTP":
                ltp = message.get("LTP_Rate")
                if ltp is not None:
                    e["ltp"] = float(ltp)
            elif message_type == "MarketDepth" and message.get("Level") == 1:
                # Level 1 = best bid/ask; ignore deeper depth levels 2-5,
                # which would otherwise overwrite the top-of-book price.
                bid = message.get("BidRate")
                ask = message.get("OfferRate")
                if bid is not None: e["buy"]  = float(bid)
                if ask is not None: e["sell"] = float(ask)
            else:
                return
            e["ts"] = time.time()
            self._ws_prices[name] = e

    # ── REST polling (throttled, quiet on repeated errors) ────────────────────
    def _start_rest_poller(self):
        self._rest_executor = ThreadPoolExecutor(
            max_workers=REST_POLL_WORKERS, thread_name_prefix="mo-rest"
        )
        threading.Thread(target=self._rest_poll_loop, daemon=True).start()

    def _rest_poll_loop(self):
        # Fetch all symbols concurrently instead of serially — serial polling
        # scales cycle time linearly with len(SYMBOLS) (dominated by network
        # round-trip, not the old per-symbol sleep), which is what made large
        # symbol lists (e.g. 200) update far slower than small ones (e.g. 59).
        while not self._stop_poll.is_set():
            cycle_start = time.time()
            futures = {
                self._rest_executor.submit(self._fetch_quote_rest, sym["name"]): sym["name"]
                for sym in SYMBOLS
            }
            for future in as_completed(futures):
                if self._stop_poll.is_set():
                    break
                name  = futures[future]
                quote = future.result()
                if quote:
                    with self._lock:
                        quote["ts"] = time.time()
                        self._rest_prices[name] = quote
            # Cap the whole cycle at REST_POLL_INTERVAL rather than sleeping
            # per symbol, so refresh speed stays roughly flat as N grows.
            elapsed = time.time() - cycle_start
            if elapsed < REST_POLL_INTERVAL:
                time.sleep(REST_POLL_INTERVAL - elapsed)

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
        # Prefer WS whenever it's fresh, full stop — WS carries a real
        # bid/ask spread; REST is always a synthetic buy=sell=ltp duplicate
        # (getltpdata has no bid/ask fields). REST polls continuously, so
        # it almost always has a newer timestamp than WS — the old
        # `ws_q["ts"] >= rest_q["ts"]` tie-breaker meant REST's fake data
        # won out over WS's real data the moment REST refreshed, discarding
        # a real spread in favor of a fake one within seconds of receiving it.
        if ws_fresh:
            return {"buy": ws_q.get("buy", ws_q.get("ltp")),
                    "sell": ws_q.get("sell", ws_q.get("ltp")),
                    "ltp": ws_q.get("ltp")}
        if rest_fresh:
            return {"buy": rest_q["buy"], "sell": rest_q["sell"], "ltp": rest_q["ltp"]}
        return None

    def disconnect(self):
        self._stop_poll.set()
        if self._rest_executor:
            self._rest_executor.shutdown(wait=False)
        try:
            if self._mo_sdk and self._mo_sdk.ws1:
                self._mo_sdk.ws1.close()
        except Exception:
            pass