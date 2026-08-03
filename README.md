# Arbitrage Dashboard — Angel One vs Motilal Oswal

Compares live NFO futures prices between Angel One and Motilal Oswal for a
list of symbols, ranks them by best arbitrage opportunity (buy on one
broker, sell on the other), and writes the ranked table straight into an
open Excel workbook roughly every 100ms. Both broker APIs are free.

---

## 📁 Files

```
stock_comparator-kd/
├── main.py                 ← Run this — the real-time loop
├── config.py                ← Broker credentials + SYMBOLS list (gitignored, not committed)
├── angel_feed.py             ← Angel One WebSocket price feed (smartapi-python)
├── motilal_feed.py           ← Motilal Oswal feed: WS broadcast (best-effort) + REST poll fallback
├── MOFSLOPENAPI.py            ← Motilal's official SDK, vendored (drives the WS layer for motilal_feed.py)
├── comparison_engine.py       ← Ranks symbols by buy→sell / sell→buy arbitrage diff
├── excel_live_writer.py       ← Writes into an already-open Excel workbook via xlwings/COM
├── fetch_angel_tokens.py      ← One-off: resolves Angel One instrument tokens into config.py
├── fetch_motilal_tokens.py    ← One-off: resolves Motilal Oswal scrip codes into config.py
└── requirements.txt
```

---

## ⚙️ How it works

Every `REFRESH_INTERVAL` seconds (0.1s by default), `main.py`:

1. Reads the latest cached price for every symbol in `config.SYMBOLS` from
   both feeds. Angel One's price comes from an in-memory dict kept fresh by
   a WebSocket thread; Motilal's comes from whichever of its WS broadcast
   or REST poller has the freshest quote for that symbol.
2. Passes both snapshots to `ComparisonEngine`, which computes
   `buy_to_sell` (buy on Motilal, sell on Angel) and `sell_to_buy` (buy on
   Angel, sell on Motilal) per symbol — multiplied by each symbol's
   `lot_size` for a total — and sorts by the best opportunity.
3. If anything changed since the last tick, batch-writes the whole ranked
   table into the Excel workbook in a **single COM call** (screen updating
   and calculation are turned off for the duration of the write). Row
   colors (green/yellow/red) and font colors are native Excel conditional
   formatting rules set up once at startup — not written per cell per
   tick — which is what keeps this fast even with 100+ symbols.

If Excel isn't already open with the target workbook, `ExcelLiveWriter`
opens/creates it itself via xlwings — you don't need a separate setup
script.

---

## ⚙️ Setup (one-time)

### Step 1 — Install Python packages
```bash
pip install -r requirements.txt
```
Requires Windows + a real Excel install (`xlwings` drives Excel over COM).

### Step 2 — Angel One API (free)
1. Go to https://smartapi.angelbroking.com/, create an account, generate an API key.
2. Enable TOTP (use an authenticator app → save the base32 secret).
3. Fill in `ANGEL_ONE_CONFIG` in `config.py` (`api_key`, `client_id`, `password`, `totp_secret`).

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
    {"name": "RELIANCE 25-AUG-2026", "code": 58371, "angel_token": "FILL_IN", "mo_scrip": None, "lot_size": 500},
]
```
Then resolve the `FILL_IN` / missing fields automatically:
```bash
py fetch_angel_tokens.py     # resolves angel_token, backs up config.py -> config.py.bak first
py fetch_motilal_tokens.py   # resolves mo_scrip
```

### Step 5 — Run
```bash
py main.py
```
- Connects to Angel One (WebSocket) and Motilal Oswal (WS best-effort + REST fallback), then opens/attaches to the Excel workbook.
- Updates the workbook live, roughly every `REFRESH_INTERVAL` seconds.
- Press **Ctrl+C** to stop — the workbook is saved on exit.

No brokers or market hours needed to try it out — set `DEMO_MODE = True`
in `config.py` to drive the Excel sheet with fake, jittered prices instead.

---

## 🔧 Key config.py knobs

| Setting | Purpose |
|---|---|
| `ENABLE_EXCEL` | Turn the live Excel writer on/off |
| `DEMO_MODE` | Use fake prices instead of connecting to real brokers |
| `REFRESH_INTERVAL` | Seconds between ticks (default `0.1`) |
| `DIFF_THRESHOLD` | Diff magnitude (₹) above which a losing row is highlighted yellow instead of red |
| `DEFAULT_LOT_SIZE` | Fallback lot size for a symbol until its real `lot_size` is filled in |
| `MARKET_OPEN` / `MARKET_CLOSE` | Outside this window (and outside DEMO_MODE) the loop idles instead of polling |
| `EXCEL_WORKBOOK_NAME` / `EXCEL_SHEET_NAME` | Target workbook/sheet for the live writer |

---

## 📊 Excel Output

Columns: `# | Script Name | Angel Buy | Angel Sell | Motilal Buy | Motilal Sell | Buy→Sell | Buy Total | Sell→Buy | Sell Total | Best Opportunity`

Row color is driven by Excel conditional formatting, not Python:
- **Green** — best opportunity (buy→sell or sell→buy) is profitable.
- **Yellow** — unprofitable but within `DIFF_THRESHOLD`.
- **Red** — unprofitable beyond the threshold.

Rank #1–#3 get gold/silver/bronze text; positive/negative diff columns get
green/red font automatically.

---

## ❓ Common Issues

| Problem | Fix |
|---|---|
| Angel login fails | Check the TOTP secret is the base32 key, not the QR image |
| Motilal WS shows 0 ticks | Its real broadcast protocol is binary and best-effort (see `motilal_feed.py` docstring) — REST polling is always running as a guaranteed fallback, so prices should still update, just possibly slower |
| Prices show 0 / blank | Waiting for the first tick from either broker, or market is closed and `DEMO_MODE` is off |
| Excel not updating | Check `ENABLE_EXCEL=True`; make sure Excel/xlwings was able to open or attach to the workbook (see console output on startup) |
| High symbol counts feel laggy | Reduce logging/side work in the feed threads before adding more symbols — the Excel write itself is a single batched COM call regardless of row count |

---

## 🔒 Security notes

- `config.py` holds real broker credentials in plaintext and is
  **gitignored** — never commit it, and delete any stray `config.py.bak*`
  files that `fetch_angel_tokens.py`/`fetch_motilal_tokens.py` create
  before handing the project folder to anyone else.
- Avoid printing raw HTTP response bodies from login calls — they can
  contain live auth tokens.
