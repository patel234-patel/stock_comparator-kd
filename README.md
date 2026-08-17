# Arbitrage Dashboard — GM Global vs Motilal Oswal

Compares live NFO futures prices between GM Global (gmglobal.org) and
Motilal Oswal for a list of symbols, ranks them by best arbitrage
opportunity (buy on one venue, sell on the other), and pushes the ranked
table out roughly every 100ms — to an open Excel workbook, and/or to a
live HTML dashboard served over WebSocket.

---

## 📁 Files

```
stock_comparator-kd/
├── main.py                 ← Run this — the real-time loop
├── config.py                ← Broker credentials + SYMBOLS list (gitignored, not committed)
├── gm_feed.py                ← GM Global price feed (Socket.IO 2.x over websocket-client)
├── motilal_feed.py           ← Motilal Oswal feed: WS broadcast (best-effort) + REST poll fallback
├── MOFSLOPENAPI.py            ← Motilal's official SDK, vendored (drives the WS layer for motilal_feed.py)
├── comparison_engine.py       ← Ranks symbols by buy→sell / sell→buy arbitrage diff
├── excel_live_writer.py       ← Writes into an already-open Excel workbook via xlwings/COM
├── web_dashboard.py           ← Live HTML dashboard: HTTP + WebSocket servers (no COM lag)
├── web/dashboard.html         ← The dashboard page itself (self-contained, no external deps)
├── run_shard1.bat            ← Starts the first half of the symbols on broker account A (port 8000)
├── run_shard2.bat            ← Starts the second half on broker account B (port 8001)
├── fetch_gm_lots.py           ← Refreshes lot_size from GM Global's script master (run after each rollover)
├── fetch_motilal_tokens.py    ← One-off: resolves Motilal Oswal scrip codes into config.py
└── requirements.txt
```

---

## ⚙️ How it works

Every `REFRESH_INTERVAL` seconds (0.1s by default), `main.py`:

1. Reads the latest cached price for every symbol in `config.SYMBOLS` from
   both feeds. GM Global's price comes from an in-memory dict kept fresh by
   a socket thread; Motilal's comes from whichever of its WS broadcast
   or REST poller has the freshest quote for that symbol.
2. Passes both snapshots to `ComparisonEngine`, which computes
   `buy_to_sell` (buy on Motilal, sell on GM Global) and `sell_to_buy` (buy
   on GM Global, sell on Motilal) per symbol — multiplied by each symbol's
   `lot_size` for a total — and sorts by the best opportunity.
3. If anything changed since the last tick, it pushes the whole ranked
   table out to whichever outputs are enabled:
   - **Excel** — a batch-writes the whole ranked table into the Excel
     workbook in a **single COM call** (screen updating and calculation
     are turned off for the duration of the write). Row colors
     (green/yellow/red) and font colors are native Excel conditional
     formatting rules set up once at startup — not written per cell per
     tick — which is what keeps this fast even with 100+ symbols. In
     practice this still has a floor: every write is a round-trip into
     another process over COM, and Excel's own repaint can lag behind it,
     especially at ~200 symbols.
   - **Web dashboard** — the same ranked rows, JSON-encoded, pushed over
     a WebSocket to every connected browser tab in one message. There's
     no COM/process boundary and no repaint scheduler to wait on, so this
     has no comparable lag floor — a browser tab just applies whatever
     arrives.

If Excel isn't already open with the target workbook, `ExcelLiveWriter`
opens/creates it itself via xlwings — you don't need a separate setup
script. The web dashboard's HTTP + WebSocket servers are started the same
way, from inside `main.py` — nothing else to run.

---

## ⚙️ Setup (one-time)

### Step 1 — Install Python packages
```bash
pip install -r requirements.txt
```
Requires Windows + a real Excel install (`xlwings` drives Excel over COM).

### Step 2 — GM Global
Fill in `GM_GLOBAL_CONFIG` in `config.py` (`user_id`, `password`) with your
gmglobal.org login. No API key, no TOTP, no SDK.

GM Global is two independent halves, and it's worth knowing which does what:

- **PHP session APIs** at `https://www.gmglobal.org/ajaxfiles/*.php` —
  login, watchlist, orders. Cookie-session based. `gm_feed.py` logs in here
  and `fetch_gm_lots.py` reads the script master through it.
- **A Socket.IO tick feed** at `giantdata.org:3003` — the only thing that
  carries live prices, and it is *not* tied to the PHP session. `gm_feed.py`
  joins one room per instrument and quotes stream back.

Because prices ride the second half, a failed login is a warning rather
than a fatal error — the feed still delivers.

Their server is Socket.IO 2.x / Engine.IO 3. The modern `python-socketio`
client only speaks Engine.IO 4 and cannot talk to it, so `gm_feed.py`
implements the handful of frames needed directly on `websocket-client`
(already a dependency for Motilal). See the `gm_feed.py` docstring for the
wire format.

**Instrument identifiers.** GM Global keys instruments as
`<SCRIPT>-<EXPIRY CODE>`, e.g. `RELIANCE-I`, where `I` is the near month.
`gm_feed.py` builds that from the first word of each `SYMBOLS` name plus
`GM_EXPIRY_CODE`. A symbol can override it with an explicit `gm_symbol`
key if one ever diverges.

### Step 3 — Motilal Oswal API (free)
1. Have a Motilal Oswal demat account.
2. Email **rms.trading@motilaloswal.com** — subject "XTS API activation
   request", body with your Client ID requesting Market Data API access.
3. Credentials arrive from **it.operations@motilaloswal.com**.
4. Go to https://invest.motilaloswal.com/moAPI/, create an API app, get the
   Market API Key + Secret.
5. Fill in `MOTILAL_CONFIG` in `config.py`.

### Step 4 — Add symbols
In `config.py`, add entries to `SYMBOLS`:
```python
SYMBOLS = [
    {"name": "RELIANCE 25-AUG-2026", "code": 58371, "mo_scrip": None, "lot_size": 500},
]
```
The name's first word is what becomes the GM Global identifier, so it has
to match GM Global's script name. Then resolve the remaining fields:
```bash
py fetch_motilal_tokens.py   # resolves mo_scrip
py fetch_gm_lots.py          # report: lot sizes, unlisted symbols, expiry drift
py fetch_gm_lots.py --write  # apply the lot_size fixes to config.py
```

### Step 5 — Run
```bash
py main.py
```
- Connects to GM Global (socket feed) and Motilal Oswal (WS best-effort + REST fallback), then opens/attaches to the Excel workbook and starts the web dashboard servers.
- Updates both live, roughly every `REFRESH_INTERVAL` seconds.
- Open **http://127.0.0.1:8000** (or whatever `WEB_HOST`/`WEB_HTTP_PORT` are set to) in a browser for the live HTML dashboard.
- Press **Ctrl+C** to stop — the workbook is saved on exit.

No accounts or market hours needed to try it out — set `DEMO_MODE = True`
in `config.py` to drive both outputs with fake, jittered prices instead.

---

## 🔀 Splitting across two broker accounts

One Motilal account covering 200+ scrips is the update-speed bottleneck,
for two compounding reasons:

- **The WS broadcast cap.** Motilal enforces a per-account limit on how
  many scrips a broadcast socket may subscribe to (queried at startup by
  the `getbroadcastmaxlimit` call in `motilal_feed.py`). Symbols past that
  cap never receive live WS ticks at all — they silently fall back to REST
  polling.
- **REST cycle length.** Every REST cycle has to work through the whole
  symbol list before any given symbol refreshes again, so buy/sell prices
  go stale in proportion to how many symbols are configured.

Running two accounts, each handling half the list, halves both: ~100
scrips fits under the WS cap, and each REST cycle is half the work.

**How to use it.** Fill in your second Motilal account as index `1` of
`MOTILAL_ACCOUNTS` in `config.py` (index `0` is the account you already
have), then start both halves. Only Motilal is split — GM Global uses the
one `GM_GLOBAL_CONFIG` in every shard, since its tick feed has no
per-account cap to work around:

```bash
run_shard1.bat      # symbols 1-104,   account A  ->  http://127.0.0.1:8000
run_shard2.bat      # symbols 105-208, account B  ->  http://127.0.0.1:8001
```

Or set the `SHARD` environment variable yourself:

```powershell
$env:SHARD=1; py main.py
$env:SHARD=2; py main.py
```

Each process is fully independent — its own logins, its own feeds,
its own dashboard. If one broker session drops, the other half keeps
running. Open both URLs in two browser tabs; each page shows a gold
**"Shard 1/2"** pill in its header and in the tab title so the two are
never mistaken for each other.

The split itself needs no code changes anywhere else: `gm_feed.py` and
`motilal_feed.py` both read `SYMBOLS` from `config` at import time, so the
`SHARD` block at the bottom of `config.py` rebinding `SYMBOLS` to one half
is enough — each process only ever knows about its own symbols. The split
is contiguous and remainder-safe (the last shard absorbs any odd symbol),
so no symbol is ever dropped or handled twice.

Leaving `SHARD` unset keeps the original behaviour exactly: all symbols,
account A, port 8000, `Karmit.xlsx`. When sharding *is* active each
process also targets its own workbook (`Karmit_shard1.xlsx`,
`Karmit_shard2.xlsx`) so two processes can never fight over one file.

> Both processes still run from one machine, so this helps with per-account
> limits, not per-IP ones. If Motilal is throttling by IP rather than by
> account, splitting will reduce the gain.

---

## 🔧 Key config.py knobs

| Setting | Purpose |
|---|---|
| `ENABLE_EXCEL` | Turn the live Excel writer on/off |
| `ENABLE_WEB_DASHBOARD` | Turn the live HTML dashboard on/off |
| `WEB_HOST` / `WEB_HTTP_PORT_BASE` / `WEB_WS_PORT_BASE` | Where the dashboard is served (`WEB_HOST="0.0.0.0"` to view from another device on your LAN). Each shard is offset `+1` from the base ports |
| `SHARD_COUNT` | How many processes to split the symbol list across (see *Splitting across two broker accounts*) |
| `GM_GLOBAL_CONFIG` | gmglobal.org `user_id` / `password` — one account, shared by every shard |
| `GM_EXPIRY_CODE` | Expiry code appended to the script name to build a GM Global identifier (`I` = near month) |
| `MOTILAL_ACCOUNTS` | One credentials entry per shard — index 0 for shard 1, index 1 for shard 2 |
| `DEMO_MODE` | Use fake prices instead of connecting to real brokers |
| `REFRESH_INTERVAL` | Seconds between ticks (default `0.1`) |
| `DIFF_THRESHOLD` | Diff magnitude (₹, per-lot total) below which an unprofitable row shows yellow instead of red on the web dashboard |
| `DEFAULT_LOT_SIZE` | Fallback lot size for a symbol until its real `lot_size` is filled in |
| `MARKET_OPEN` / `MARKET_CLOSE` | Outside this window (and outside DEMO_MODE) the loop idles instead of polling |
| `EXCEL_WORKBOOK_NAME` / `EXCEL_SHEET_NAME` | Target workbook/sheet for the live writer |

---

## 🌐 Live HTML Dashboard

The fix for Excel's write lag: `web_dashboard.py` starts two daemon threads
from inside `main.py` —

- a plain HTTP server (`WEB_HTTP_PORT`, default `8000`) that serves
  `web/dashboard.html`. It's rooted at the isolated `web/` folder, not the
  project root, so it can never accidentally serve `config.py` or anything
  else in the project.
- a WebSocket server (`WEB_WS_PORT`, default `8765`) that pushes the
  ranked comparison table, as one JSON message, to every connected browser
  tab whenever it changes.

Open **http://127.0.0.1:8000** while `main.py` is running. The page
auto-reconnects if the WebSocket drops, shows a live/stale connection
indicator, and has a symbol filter box — no build step, no dependencies,
just the one HTML file. Row coloring matches the Excel version (green =
profitable, yellow = unprofitable within `DIFF_THRESHOLD`, red = beyond
it, gold border = watchlisted), computed client-side per tick so there's
nothing extra for Python to compute or write.

By default `WEB_HOST` is `127.0.0.1` (this machine only). Set it to
`0.0.0.0` to view the dashboard from another device on the same network —
note this is plain, unauthenticated HTTP/WS, so only do that on a network
you trust.

---

## 📊 Excel & Dashboard Output

Columns: `# | Script Name | GM Buy | GM Sell | Motilal Buy | Motilal Sell | Buy→Sell | Buy Total | Sell→Buy | Sell Total | Best Opportunity`

In Excel, row color is driven by native conditional formatting, not
Python. On the web dashboard, the same rule is computed in the browser
from the JSON payload:
- **Green** — best opportunity (buy→sell or sell→buy) is profitable.
- **Yellow** — unprofitable but within `DIFF_THRESHOLD`.
- **Red** — unprofitable beyond the threshold.

Rank #1–#3 get gold/silver/bronze text; positive/negative diff columns get
green/red font automatically.

---

## ❓ Common Issues

| Problem | Fix |
|---|---|
| GM Global login is rejected | Check `user_id`/`password` in `GM_GLOBAL_CONFIG`. Prices keep flowing regardless — the tick feed needs no session — but `fetch_gm_lots.py` will refuse to run |
| One symbol never produces a row | GM Global may not list it. Run `py fetch_gm_lots.py` — it reports every config symbol GM Global has no live contract for |
| Every symbol's buy == sell | Normal outside market hours: GM Global reports bid, ask and LTP as the same number when nothing is trading |
| Motilal WS shows 0 ticks | Its real broadcast protocol is binary and best-effort (see `motilal_feed.py` docstring) — REST polling is always running as a guaranteed fallback, so prices should still update, just possibly slower |
| Prices show 0 / blank | Waiting for the first tick from either broker, or market is closed and `DEMO_MODE` is off |
| Excel not updating | Check `ENABLE_EXCEL=True`; make sure Excel/xlwings was able to open or attach to the workbook (see console output on startup) |
| Dashboard page shows "Connecting…" forever | Check `ENABLE_WEB_DASHBOARD=True`, that `main.py` is still running, and that nothing else on this machine is already using `WEB_HTTP_PORT`/`WEB_WS_PORT` |
| Dashboard loads but stays "Disconnected" | A firewall may be blocking the WebSocket port (`WEB_WS_PORT`) even though the HTTP page loaded fine — allow it, or keep `WEB_HOST=127.0.0.1` if you're only viewing locally |
| `SHARD=2 uses MOTILAL_ACCOUNTS[1], but these fields are still placeholders` | Shard 2 needs a second Motilal account — replace the `FILL_IN` values at index `1` of `MOTILAL_ACCOUNTS` in `config.py` |
| Shard 2 won't start: "address already in use" | Shard 1 is already on `8000`/`8765` and shard 2 wants `8001`/`8766` — make sure you launched it with `SHARD=2` (or via `run_shard2.bat`), not `SHARD=1` twice |
| Both tabs show the same symbols | Both processes were started with the same `SHARD` value; check the shard pill in each page header and the `🔀 SHARD n of 2` line in each console |
| High symbol counts feel laggy | Reduce logging/side work in the feed threads before adding more symbols — the Excel write is a single batched COM call regardless of row count, and the web dashboard push is a single WebSocket message regardless of row count |

---

## 🔒 Security notes

- `config.py` holds real GM Global and broker credentials in plaintext and
  is **gitignored** — never commit it, and delete any stray `config.py.bak*`
  files that `fetch_motilal_tokens.py` creates before handing the project
  folder to anyone else.
- Avoid printing raw HTTP response bodies from login calls — they can
  contain live auth tokens.
