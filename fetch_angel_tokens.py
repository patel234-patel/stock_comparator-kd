"""
fetch_angel_tokens.py — Resolve Angel One instrument tokens for NFO stock
futures and patch them into config.py automatically.

Run this from your stock_comparator project folder (same folder as config.py):

    pip install requests
    py fetch_angel_tokens.py

It will:
  1. Download the public Angel One instrument master (OpenAPIScripMaster.json)
  2. Match each entry in config.SYMBOLS by base name + expiry date
     (only FUTSTK/FUTIDX on exch_seg == NFO are considered)
  3. Back up config.py -> config.py.bak
  4. Replace every "FILL_IN" angel_token with the real token
  5. Print a summary table so you can sanity-check before running main.py
"""

import re
import shutil
import datetime as dt
import requests

MASTER_URL = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"

from config import SYMBOLS  # noqa: E402


def split_name_and_expiry(display_name: str):
    """'AUROPHARMA 28-JUL-2026' -> ('AUROPHARMA', datetime.date(2026,7,28))"""
    base, date_part = display_name.rsplit(" ", 1)
    expiry_date = dt.datetime.strptime(date_part, "%d-%b-%Y").date()
    return base.strip(), expiry_date


def expiry_to_master_format(expiry_date: dt.date) -> str:
    """datetime.date -> '28JUL2026' (matches the master's expiry field format)"""
    return expiry_date.strftime("%d%b%Y").upper()


def main():
    print("Downloading Angel One instrument master ...")
    resp = requests.get(MASTER_URL, timeout=30)
    resp.raise_for_status()
    master = resp.json()
    print(f"  -> {len(master)} instruments loaded\n")

    # Index NFO stock/index futures by (name, expiry) for fast lookup
    fut_index = {}
    for row in master:
        if row.get("exch_seg") == "NFO" and row.get("instrumenttype") in ("FUTSTK", "FUTIDX"):
            key = (row["name"].upper(), row["expiry"].upper())
            fut_index[key] = row

    resolved = {}   # display_name -> token
    missing = []

    for sym in SYMBOLS:
        base, expiry_date = split_name_and_expiry(sym["name"])
        master_expiry = expiry_to_master_format(expiry_date)
        row = fut_index.get((base.upper(), master_expiry))
        if row:
            resolved[sym["name"]] = row["token"]
            print(f"  ✅ {sym['name']:<28} -> token {row['token']}  (symbol: {row['symbol']})")
        else:
            missing.append(sym["name"])
            print(f"  ❌ {sym['name']:<28} -> NOT FOUND (base='{base}', expiry='{master_expiry}')")

    if missing:
        print(
            "\nSome symbols weren't found. Common causes:\n"
            "  - Expiry hasn't been listed yet for that month\n"
            "  - Base name in config.py doesn't match Angel One's 'name' field exactly\n"
            "    (check spelling/case against the master, e.g. via the printed 'symbol' column)\n"
        )

    if not resolved:
        print("Nothing resolved — config.py left untouched.")
        return

    # Patch config.py: back it up, then replace FILL_IN per matching symbol block
    shutil.copyfile("config.py", "config.py.bak")
    with open("config.py", "r", encoding="utf-8") as f:
        text = f.read()

    for name, token in resolved.items():
        pattern = re.compile(
            r'("name":\s*"' + re.escape(name) + r'".*?"angel_token":\s*")FILL_IN(")',
            re.DOTALL,
        )
        text, n = pattern.subn(r"\g<1>" + token + r"\2", text, count=1)
        if n == 0:
            print(f"  ⚠️  Could not patch config.py for '{name}' (pattern not found)")

    with open("config.py", "w", encoding="utf-8") as f:
        f.write(text)

    print(f"\n✅ config.py updated ({len(resolved)}/{len(SYMBOLS)} tokens filled in).")
    print("   Original saved as config.py.bak — re-run main.py now.")


if __name__ == "__main__":
    main()