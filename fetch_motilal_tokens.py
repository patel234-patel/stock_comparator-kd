"""
fetch_motilal_tokens.py — Resolve Motilal Oswal scrip codes for NFO stock
futures and patch them into config.py automatically.

Unlike Angel One, Motilal has no public unauthenticated master file — you
must be logged in to call the Scrip/Instrument master API. This script
reuses the exact login flow already implemented in motilal_feed.py
(_login -> _get_access_token -> _common_headers), then calls:

    POST https://openapi.motilaloswal.com/rest/report/v3/getscripsbyexchangename
    body: {"exchangename": "NSEFO"}

...and matches each entry in config.SYMBOLS against the returned rows by
scripshortname (base name) + expirydate (unix epoch -> IST date).

Run from your project folder:
    py fetch_motilal_tokens.py
"""

import re
import shutil
import time
import csv
import io
import datetime as dt
import requests

from config import SYMBOLS
import config as config_module
from motilal_feed import MotilalFeed, BASE_URL

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def find_motilal_config() -> dict:
    """Locate the credentials dict in config.py without assuming its name.

    Looks for any dict attribute containing the keys MotilalFeed needs.
    """
    required = {"password", "market_api_key", "api_secret_key", "client_code"}
    for attr_name in dir(config_module):
        val = getattr(config_module, attr_name)
        if isinstance(val, dict) and required.issubset(val.keys()):
            return val
    raise RuntimeError(
        "Couldn't find your Motilal credentials dict in config.py "
        "(expected keys: password, market_api_key, api_secret_key, client_code, "
        "totp_secret/totp_code, two_fa). Edit find_motilal_config() to point at it."
    )


def split_name_and_expiry(display_name: str):
    """'AUROPHARMA 28-JUL-2026' -> ('AUROPHARMA', datetime.date(2026,7,28))"""
    base, date_part = display_name.rsplit(" ", 1)
    expiry_date = dt.datetime.strptime(date_part, "%d-%b-%Y").date()
    return base.strip(), expiry_date


def main():
    cfg = find_motilal_config()
    feed = MotilalFeed(cfg)

    print("  [MO] Logging in ...")
    auth_token = feed._login()
    feed._auth_token = auth_token

    print("  [MO] Waiting 3s for session to propagate ...")
    time.sleep(3)

    access_token = None
    last_error = None
    for attempt in range(1, 4):
        try:
            access_token = feed._get_access_token()
            break
        except ConnectionError as e:
            last_error = e
            print(f"  [MO] Attempt {attempt}/3 failed: {e}")
            if attempt < 3:
                print("  [MO] Retrying in 3s ...")
                time.sleep(3)
    if access_token is None:
        raise SystemExit(
            f"\nCould not get an access token after 3 attempts.\n"
            f"Last error: {last_error}\n\n"
            f"Make sure no other script/main.py is currently logged in with this "
            f"client code, then try again."
        )
    headers = feed._common_headers(auth_token, access_token)

    print("  [MO] Fetching NSEFO scrip master (CSV, this can take ~30-60s) ...")
    csv_url = f"{BASE_URL}/getscripmastercsv?name=NSEFO"
    resp = requests.get(csv_url, headers=headers, timeout=120, stream=True)
    resp.raise_for_status()

    chunks = []
    downloaded = 0
    for chunk in resp.iter_content(chunk_size=262144):
        if chunk:
            chunks.append(chunk)
            downloaded += len(chunk)
            print(f"  ... {downloaded / 1024:.0f} KB downloaded", end="\r")
    print()

    raw_text = b"".join(chunks).decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(raw_text))
    rows = list(reader)
    print(f"  -> {len(rows)} NSEFO instruments loaded\n")

    if rows and "scripcode" not in rows[0]:
        print("  ⚠️  Unexpected CSV columns:", list(rows[0].keys()))
        raise RuntimeError("CSV format didn't match what we expected — see columns above.")

    # NOTE: Motilal's 'expirydate' epoch field in this CSV is unreliable — it's
    # consistently offset from the real date (e.g. scripname says '28-Jul-2026'
    # but the epoch decodes to 2016-07-28 under standard Unix epoch). So we
    # match on the human-readable scripname text instead, which is correct.
    fut_index = {}
    for row in rows:
        if row.get("instrumentname") not in ("FUTSTK", "FUTIDX"):
            continue
        shortname = str(row.get("scripshortname", "")).strip().upper()
        scripname = str(row.get("scripname", "")).strip().upper()
        fut_index.setdefault(shortname, []).append((scripname, row))

    resolved = {}
    missing = []

    for sym in SYMBOLS:
        base, expiry_date = split_name_and_expiry(sym["name"])
        target_date_str = expiry_date.strftime("%d-%b-%Y").upper()  # '28-JUL-2026'
        candidates = fut_index.get(base.upper(), [])

        match = None
        for scripname, row in candidates:
            if target_date_str in scripname:
                match = row
                break

        if match:
            scripcode = int(match["scripcode"])
            resolved[sym["name"]] = scripcode
            print(f"  ✅ {sym['name']:<28} -> scripcode {scripcode}  ({match.get('scripname')})")
        else:
            missing.append(sym["name"])
            print(f"  ❌ {sym['name']:<28} -> NOT FOUND (base='{base}', looking for '{target_date_str}')")
            if candidates:
                print(f"      Available FUTSTK/FUTIDX scripnames for '{base}':")
                for scripname, row in candidates[:10]:
                    print(f"        {row.get('scripname')!r}")
            else:
                print(f"      No FUTSTK/FUTIDX rows at all for scripshortname='{base}'")

    if missing:
        print(
            "\nSome symbols weren't found — see the 'Available FUTSTK/FUTIDX scripnames' "
            "lines above for each one. Common causes:\n"
            "  - That expiry hasn't been listed yet, or already expired/delisted\n"
            "  - The date format in scripname differs slightly from what we searched for\n"
        )

    if not resolved:
        print("Nothing resolved — config.py left untouched.")
        return

    shutil.copyfile("config.py", "config.py.bak2")
    with open("config.py", "r", encoding="utf-8") as f:
        text = f.read()

    for name, scripcode in resolved.items():
        pattern = re.compile(
            r'("name":\s*"' + re.escape(name) + r'".*?"mo_scrip":\s*)\d+',
            re.DOTALL,
        )
        text, n = pattern.subn(r"\g<1>" + str(scripcode), text, count=1)
        if n == 0:
            print(f"  ⚠️  Could not patch config.py for '{name}' (pattern not found)")

    with open("config.py", "w", encoding="utf-8") as f:
        f.write(text)

    print(f"\n✅ config.py updated ({len(resolved)}/{len(SYMBOLS)} scrip codes refreshed).")
    print("   Previous version saved as config.py.bak2.")


if __name__ == "__main__":
    main()