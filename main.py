"""
main.py — Real-Time Arbitrage Dashboard
=======================================
Dual output: Google Sheets (every ~1.5s) + Live Excel (every tick ~100ms)
"""

import time
import datetime
import logging
import random
from typing import Dict

from config import (
    SYMBOLS, MARKET_OPEN, MARKET_CLOSE,
    REFRESH_INTERVAL, SHEET_WRITE_INTERVAL, DIFF_THRESHOLD,
    ANGEL_ONE_CONFIG, MOTILAL_CONFIG,
    GOOGLE_CREDENTIALS_FILE, SPREADSHEET_ID, WORKSHEET_NAME,
    EXCEL_WORKBOOK_NAME, EXCEL_SHEET_NAME,
    ENABLE_GOOGLE_SHEET, ENABLE_EXCEL, DEMO_MODE,
)
from angel_feed import AngelOneFeed
from motilal_feed import MotilalFeed
from comparison_engine import ComparisonEngine
from google_sheet_writer import GoogleSheetWriter
from excel_live_writer import ExcelLiveWriter

logging.basicConfig(
    level=logging.WARNING,          # suppress INFO noise from websocket libs
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[
        logging.FileHandler("arbitrage.log"),
        logging.StreamHandler(),
    ]
)
log = logging.getLogger(__name__)


def is_market_open() -> bool:
    now = datetime.datetime.now().time()
    return MARKET_OPEN <= now <= MARKET_CLOSE


def build_price_snapshot(feed, symbol_list) -> Dict[str, dict]:
    snapshot = {}
    for sym in symbol_list:
        name = sym["name"]
        if hasattr(feed, "get_quote"):
            quote = feed.get_quote(name)
            if quote:
                snapshot[name] = quote
                continue
        ltp = feed.get_price(name)
        if ltp is not None:
            snapshot[name] = {"buy": ltp, "sell": ltp}
    return snapshot


def make_demo_snapshot():
    """
    Fake prices for testing when brokers are offline / market is closed.
    Toggle with DEMO_MODE = True in config.py
    """
    base_prices = {
        "AUROPHARMA 28-JUL-2026": 1534.0,
        "BANDHANBNK 28-JUL-2026": 166.3,
        "BIOCON 28-JUL-2026":     433.4,
        "BHEL 28-JUL-2026":       417.5,
        "EXIDEIND 28-JUL-2026":   437.2,
    }
    snap = {}
    for sym in SYMBOLS:
        name  = sym["name"]
        base  = base_prices.get(name, 500.0)
        jitter = random.uniform(-0.5, 0.5)
        snap[name] = {
            "buy":  round(base + jitter - 0.1, 2),
            "sell": round(base + jitter + 0.1, 2),
            "ltp":  round(base + jitter, 2),
        }
    return snap


def snapshot_changed(prev: list, curr: list) -> bool:
    if len(prev) != len(curr):
        return True
    for a, b in zip(prev, curr):
        if (a["script_name"] != b["script_name"] or
                abs(a.get("angel_buy",   0) - b.get("angel_buy",   0)) > 0.001 or
                abs(a.get("angel_sell",  0) - b.get("angel_sell",  0)) > 0.001 or
                abs(a.get("motilal_buy", 0) - b.get("motilal_buy", 0)) > 0.001 or
                abs(a.get("motilal_sell",0) - b.get("motilal_sell",0)) > 0.001):
            return True
    return False


def main():
    print("=" * 65)
    print("  Real-Time Arbitrage Dashboard: Angel One vs Motilal Oswal")
    if DEMO_MODE:
        print("  ⚠️  DEMO MODE — using fake prices (set DEMO_MODE=False in config.py)")
    print(f"  Symbols: {len(SYMBOLS)}  |  Poll: {REFRESH_INTERVAL}s  |  Sheet: {SHEET_WRITE_INTERVAL}s")
    print("=" * 65)

    engine = ComparisonEngine(SYMBOLS)

    if not DEMO_MODE:
        angel   = AngelOneFeed(ANGEL_ONE_CONFIG)
        motilal = MotilalFeed(MOTILAL_CONFIG)

        print("\n[1/4] Connecting to Angel One ...")
        try:
            angel.connect()
        except Exception as e:
            log.error(f"Angel One connect failed: {e}")

        print("[2/4] Connecting to Motilal Oswal ...")
        try:
            motilal.connect()
        except Exception as e:
            log.error(f"Motilal connect failed: {e}")
    else:
        angel   = None
        motilal = None
        print("\n[1/4] DEMO: skipping Angel One connection")
        print("[2/4] DEMO: skipping Motilal connection")

    print("[3/4] Connecting to Google Sheets ...")
    gsheet = None
    if ENABLE_GOOGLE_SHEET:
        try:
            gsheet = GoogleSheetWriter(
                credentials_file=GOOGLE_CREDENTIALS_FILE,
                spreadsheet_id=SPREADSHEET_ID,
                worksheet_name=WORKSHEET_NAME,
                diff_threshold=DIFF_THRESHOLD,
                min_write_interval=SHEET_WRITE_INTERVAL,
            )
        except Exception as e:
            log.error(f"Google Sheets connect failed: {e}")
    else:
        print("  ⏭️  Google Sheets DISABLED (ENABLE_GOOGLE_SHEET=False in config.py)")

    print("[4/4] Connecting to Excel (live workbook) ...")
    excel = None
    if ENABLE_EXCEL:
        try:
            excel = ExcelLiveWriter(
                workbook_name=EXCEL_WORKBOOK_NAME,
                sheet_name=EXCEL_SHEET_NAME,
                diff_threshold=DIFF_THRESHOLD,
            )
        except Exception as e:
            log.error(f"Excel connect failed: {e}")
    else:
        print("  ⏭️  Excel DISABLED (ENABLE_EXCEL=False in config.py)")

    print(f"\nRunning:")
    print(f"  📊 Excel  → {'LIVE every tick' if excel  else 'DISABLED'}")
    print(f"  🌐 Sheets → {'every ~'+str(SHEET_WRITE_INTERVAL)+'s' if gsheet else 'DISABLED'}")
    print(f"  Press Ctrl+C to stop.\n")

    tick         = 0
    sheet_pushes = 0
    excel_writes = 0
    last_ranked  = []

    try:
        while True:
            if not is_market_open() and not DEMO_MODE:
                now = datetime.datetime.now().strftime("%H:%M:%S")
                print(f"\r[{now}] Market closed. Waiting ...", end="", flush=True)
                time.sleep(10)
                continue

            tick += 1
            t0 = time.time()

            # ── Get prices ─────────────────────────────────────────────────────
            if DEMO_MODE:
                angel_snap   = make_demo_snapshot()
                motilal_snap = make_demo_snapshot()
            else:
                angel_snap   = build_price_snapshot(angel,   SYMBOLS) if angel   else {}
                motilal_snap = build_price_snapshot(motilal, SYMBOLS) if motilal else {}

            # ── If one broker has no data yet, use LTP for both sides ──────────
            # This means Excel shows partial data rather than staying empty
            all_names = {s["name"] for s in SYMBOLS}
            for name in all_names:
                if name not in angel_snap and name in motilal_snap:
                    ltp = motilal_snap[name].get("ltp", 0)
                    angel_snap[name] = {"buy": ltp, "sell": ltp}
                if name not in motilal_snap and name in angel_snap:
                    ltp = angel_snap[name].get("ltp", 0)
                    motilal_snap[name] = {"buy": ltp, "sell": ltp}

            if not angel_snap and not motilal_snap:
                print(
                    f"\r  Waiting for data — angel:{len(angel_snap)}/{len(SYMBOLS)} "
                    f"motilal:{len(motilal_snap)}/{len(SYMBOLS)}",
                    end="", flush=True,
                )
                time.sleep(REFRESH_INTERVAL)
                continue

            ranked = engine.compute(angel_snap, motilal_snap)
            if not ranked:
                time.sleep(REFRESH_INTERVAL)
                continue

            changed = snapshot_changed(last_ranked, ranked)
            if not changed:
                time.sleep(REFRESH_INTERVAL)
                continue

            last_ranked = [dict(r) for r in ranked]

            # ── Google Sheets ──────────────────────────────────────────────────
            sheet_pushed = False
            if gsheet:
                try:
                    sheet_pushed = gsheet.update(ranked)
                    if sheet_pushed:
                        sheet_pushes += 1
                except Exception as e:
                    log.warning(f"Sheets error: {e}")

            # ── Excel (always, instant) ────────────────────────────────────────
            if excel:
                try:
                    excel.update(ranked)
                    excel_writes += 1
                except Exception as e:
                    log.warning(f"Excel error: {e}")

            # ── Status line ────────────────────────────────────────────────────
            elapsed = (time.time() - t0) * 1000
            top     = ranked[0]
            demo_tag = " [DEMO]" if DEMO_MODE else ""
            sheet_icon = "✅" if sheet_pushed else ("⏳" if gsheet else "❌")
            excel_icon = f"📊{excel_writes}" if excel else "❌"
            print(
                f"\r  #{tick:5d}  {datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]}"
                f"{demo_tag}"
                f"  {top['script_name'][:18]:<18}"
                f"  B2S:{top['buy_to_sell']:+6.2f}"
                f"  S2B:{top['sell_to_buy']:+6.2f}"
                f"  {sheet_icon}Sheet  {excel_icon}Excel"
                f"  [{elapsed:.0f}ms]        ",
                end="", flush=True,
            )

            sleep_for = max(0, REFRESH_INTERVAL - (time.time() - t0))
            time.sleep(sleep_for)

    except KeyboardInterrupt:
        print("\n\nStopped by user.")
    finally:
        log.info("Disconnecting ...")
        if angel:
            try: angel.disconnect()
            except Exception: pass
        if motilal:
            try: motilal.disconnect()
            except Exception: pass
        if excel:
            excel.disconnect()
        print("Done.")


if __name__ == "__main__":
    main()