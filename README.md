# Stock Price Comparator — Angel One vs Motilal Oswal

Captures live prices every second, saves to Excel, shows a live dashboard.
**Both APIs are FREE** — no monthly charges.

---

## 📁 Files

```
stock_comparator/
├── main.py          ← Run this
├── config.py        ← Fill YOUR credentials here
├── angel_feed.py    ← Angel One WebSocket handler
├── motilal_feed.py  ← Motilal Oswal XTS WebSocket handler
├── excel_writer.py  ← Saves data to Excel every second
├── dashboard.py     ← Live terminal dashboard
├── requirements.txt ← Python dependencies
└── output/          ← Excel files saved here (auto-created)
```

---

## ⚙️ Setup (One-Time)

### Step 1 — Angel One API (FREE)
1. Go to: https://smartapi.angelbroking.com/
2. Create account → Generate API Key
3. Enable TOTP (use Google Authenticator → save the base32 secret key)
4. Fill in `ANGEL_ONE_CONFIG` in `config.py`

### Step 2 — Motilal Oswal API (FREE)
1. Have a Motilal Oswal demat account
2. Email: **rms.trading@motilaloswal.com**
   - Subject: "XTS API activation request"
   - Body: Your Client ID + request for Market Data API access
3. You'll receive credentials from: it.operations@motilaloswal.com
4. Go to: https://invest.motilaloswal.com/moAPI/
5. Create an API app → get Market API Key + Secret
6. Fill in `MOTILAL_CONFIG` in `config.py`

### Step 3 — Install Python packages
```bash
pip install -r requirements.txt
```

---

## ▶️ Run

```bash
python main.py
```

- Dashboard updates every second in the terminal
- Excel file saved to `output/TATAMOTORS_prices_YYYY-MM-DD.xlsx`
- Auto-saves every 60 rows (configurable in config.py)
- Press **Ctrl+C** to stop and do a final save

---

## 📊 Excel Output

| Column | Description |
|--------|-------------|
| Timestamp | HH:MM:SS of the tick |
| Angel One Price | Live LTP from Angel One |
| Motilal Price | Live LTP from Motilal Oswal |
| Difference | Angel − Motilal (green = Angel higher, red = Motilal higher) |
| Diff % | Percentage difference |

---

## 🔧 Change Stock Symbol

In `config.py`:
```python
SYMBOL = "RELIANCE"   # or INFY, TCS, HDFCBANK, SBIN, etc.
```

Available pre-mapped symbols: TATAMOTORS, RELIANCE, INFY, TCS, HDFCBANK,
ICICIBANK, SBIN, WIPRO, AXISBANK, LT

For other symbols, add their token/instrument ID to the maps in
`angel_feed.py` and `motilal_feed.py`.

---

## ❓ Common Issues

| Problem | Fix |
|---------|-----|
| Angel login fails | Check TOTP secret — must be the base32 key, not the QR image |
| Motilal login fails | XTS may not be activated yet — wait for their email |
| Price shows None | Market may be closed, or WebSocket hasn't received first tick yet |
| Excel not updating | Check `output/` folder; it auto-saves every 60 rows |
