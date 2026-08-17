"""
fetch_gm_lots.py — refresh SYMBOLS lot sizes from GM Global
===========================================================
Replaces the old fetch_angel_tokens.py. GM Global identifiers need no
token lookup (gm_feed builds them from the script name), so the only
thing left to resolve is lot_size — and GM Global publishes it in the
same script master the site's own watchlist filter uses.

Run after every expiry rollover:

    py fetch_gm_lots.py            → report only, changes nothing
    py fetch_gm_lots.py --write    → rewrite lot_size in config.py

Reports three things you want to see before a session:
  * lot sizes that disagree with config (and fixes them with --write)
  * config symbols GM Global does not list at all — those will never
    produce a row, since gm_feed can't get a quote for them
  * whether GM Global's expiry for these scripts still matches the date
    in your SYMBOLS names
"""

import json
import re
import sys

import requests

from config import SYMBOLS, GM_GLOBAL_CONFIG

NSEFUT_MARKET_TYPE_ID = "2"

CONFIG_PATH = "config.py"


def fetch_master(cfg: dict) -> dict:
    """Log in and pull GM Global's NSEFUT script + expiry master."""
    base = cfg.get("base_url", "https://www.gmglobal.org")
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Content-Type": "application/json;charset=UTF-8",
        "Referer": base + "/",
    })

    res = s.post(f"{base}/ajaxfiles/logincheck.php",
                 json={"username": cfg["user_id"], "password": cfg["password"]},
                 timeout=20).json()
    if res.get("status") != "ok":
        raise SystemExit(f"GM Global login failed: {res.get('message')}")
    print(f"Logged in as {cfg['user_id']} ({res.get('user_fname', '')}).")

    data = s.post(f"{base}/ajaxfiles/get_market_watch_filter2.php",
                  json={"type": ""}, timeout=20).json()

    scripts = data["script_list"][NSEFUT_MARKET_TYPE_ID]
    expiries = data["script_expiry_list"]

    # script name → the near-month expiry row, which is what "-I" resolves
    # to on the tick feed. Scripts with no expiry row aren't tradable.
    master = {}
    for sc in scripts:
        rows = expiries.get(sc["script_id"]) or []
        if rows:
            master[sc["script_name"]] = rows[0]
    return master


def main():
    write = "--write" in sys.argv
    master = fetch_master(GM_GLOBAL_CONFIG)
    print(f"GM Global NSEFUT scripts with a live expiry: {len(master)}\n")

    missing, mismatched, expiry_mismatch = [], [], set()

    for sym in SYMBOLS:
        base_name, _, expiry = sym["name"].partition(" ")
        row = master.get(base_name)
        if row is None:
            missing.append(sym["name"])
            continue

        # "25AUG2026" vs config's "25-AUG-2026"
        if row["expiry_date_orginal"] != expiry.replace("-", ""):
            expiry_mismatch.add((expiry, row["expiry_date_orginal"]))

        gm_lot = int(row["script_lot_qty"])
        if gm_lot != int(sym.get("lot_size") or 0):
            mismatched.append((sym["name"], sym.get("lot_size"), gm_lot))

    if missing:
        print(f"NOT LISTED on GM Global ({len(missing)}) — these can never "
              f"produce a row:")
        for name in missing:
            print(f"  {name}")
        print()

    if expiry_mismatch:
        print("EXPIRY MISMATCH — your SYMBOLS names disagree with GM Global's "
              "near month, so '-I' is pointing at a different contract:")
        for want, got in sorted(expiry_mismatch):
            print(f"  config says {want}, GM Global says {got}")
        print()

    if not mismatched:
        print("All lot sizes already match GM Global. Nothing to write.")
        return

    print(f"LOT SIZE differences ({len(mismatched)}):")
    for name, old, new in mismatched:
        print(f"  {name:<28} {old} -> {new}")

    if not write:
        print("\nRun with --write to apply these to config.py.")
        return

    src = open(CONFIG_PATH, encoding="utf-8").read()
    fixed = 0
    for name, _old, new in mismatched:
        # Rewrite lot_size only on that symbol's own line, so nothing else
        # in config.py can be touched by a stray match.
        pattern = re.compile(
            r'(\{"name": ' + re.escape(json.dumps(name)) + r'.*?"lot_size": )\d+')
        src, n = pattern.subn(lambda m: m.group(1) + str(new), src, count=1)
        fixed += n

    open(CONFIG_PATH, "w", encoding="utf-8", newline="").write(src)
    print(f"\nUpdated {fixed} lot sizes in {CONFIG_PATH}.")
    if fixed != len(mismatched):
        print(f"  !!  {len(mismatched) - fixed} could not be matched by name — "
              f"check those rows by hand.")


if __name__ == "__main__":
    main()
