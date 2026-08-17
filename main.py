"""
main.py — Real-Time Arbitrage Dashboard
=======================================
Live Excel output, updated every tick (~100ms).
"""

import time
import datetime
import logging
import random
from typing import Dict

from config import (
    SYMBOLS, MARKET_OPEN, MARKET_CLOSE,
    REFRESH_INTERVAL,
    GM_GLOBAL_CONFIG, MOTILAL_CONFIG,
    EXCEL_WORKBOOK_NAME, EXCEL_SHEET_NAME,
    ENABLE_EXCEL, DEMO_MODE,
    HIGHLIGHT_SYMBOLS,
    ENABLE_WEB_DASHBOARD, WEB_HOST, WEB_HTTP_PORT, WEB_WS_PORT, DIFF_THRESHOLD,
    SHARD, SHARD_COUNT, SHARD_LABEL,
)
from gm_feed import GmGlobalFeed
from motilal_feed import MotilalFeed
from comparison_engine import ComparisonEngine
from excel_live_writer import ExcelLiveWriter
from web_dashboard import WebDashboard

logging.basicConfig(
    level=logging.WARNING,          # suppress INFO noise from websocket libs
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[
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
        name  = sym["name"]
        quote = feed.get_quote(name)
        if quote:
            snapshot[name] = quote
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
                abs(a.get("gm_buy",      0) - b.get("gm_buy",      0)) > 0.001 or
                abs(a.get("gm_sell",     0) - b.get("gm_sell",     0)) > 0.001 or
                abs(a.get("motilal_buy", 0) - b.get("motilal_buy", 0)) > 0.001 or
                abs(a.get("motilal_sell",0) - b.get("motilal_sell",0)) > 0.001):
            return True
    return False


def main():
    print("=" * 65)
    print("  Real-Time Arbitrage Dashboard: GM Global vs Motilal Oswal")
    if DEMO_MODE:
        print("  ⚠️  DEMO MODE — using fake prices (set DEMO_MODE=False in config.py)")
    if SHARD:
        print(f"  🔀 SHARD {SHARD} of {SHARD_COUNT} — this process handles only its "
              f"own slice of symbols, on its own broker accounts.")
        print(f"     Range: {SYMBOLS[0]['name']}  →  {SYMBOLS[-1]['name']}")
    else:
        print("  ℹ️  Single-process mode (SHARD unset) — all symbols on one account.")
    print(f"  Symbols: {len(SYMBOLS)}  |  Poll: {REFRESH_INTERVAL}s")
    print("=" * 65)

    engine = ComparisonEngine(SYMBOLS)

    if not DEMO_MODE:
        gm      = GmGlobalFeed(GM_GLOBAL_CONFIG)
        motilal = MotilalFeed(MOTILAL_CONFIG)

        print("\n[1/3] Connecting to GM Global ...")
        try:
            gm.connect()
        except Exception as e:
            log.error(f"GM Global connect failed: {e}")

        print("[2/3] Connecting to Motilal Oswal ...")
        try:
            motilal.connect()
        except Exception as e:
            log.error(f"Motilal connect failed: {e}")
    else:
        gm      = None
        motilal = None
        print("\n[1/3] DEMO: skipping GM Global connection")
        print("[2/3] DEMO: skipping Motilal connection")

    print("[3/3] Connecting to Excel (live workbook) ...")
    excel = None
    if ENABLE_EXCEL:
        try:
            excel = ExcelLiveWriter(
                workbook_name=EXCEL_WORKBOOK_NAME,
                sheet_name=EXCEL_SHEET_NAME,
                highlight_names=HIGHLIGHT_SYMBOLS,
            )
        except Exception as e:
            log.error(f"Excel connect failed: {e}")
    else:
        print("  ⏭️  Excel DISABLED (ENABLE_EXCEL=False in config.py)")

    dashboard = None
    if ENABLE_WEB_DASHBOARD:
        try:
            dashboard = WebDashboard(
                host=WEB_HOST, http_port=WEB_HTTP_PORT, ws_port=WEB_WS_PORT,
                diff_threshold=DIFF_THRESHOLD, shard_label=SHARD_LABEL,
            )
        except Exception as e:
            log.error(f"Web dashboard start failed: {e}")
    else:
        print("  ⏭️  Web dashboard DISABLED (ENABLE_WEB_DASHBOARD=False in config.py)")

    print(f"\nRunning:")
    print(f"  📊 Excel  → {'LIVE every tick' if excel  else 'DISABLED'}")
    print(f"  🌐 Web    → {f'http://{WEB_HOST}:{WEB_HTTP_PORT}' if dashboard else 'DISABLED'}")
    print(f"  Press Ctrl+C to stop.\n")

    tick         = 0
    excel_writes = 0
    dash_writes  = 0
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
                gm_snap      = make_demo_snapshot()
                motilal_snap = make_demo_snapshot()
            else:
                gm_snap      = build_price_snapshot(gm,      SYMBOLS) if gm      else {}
                motilal_snap = build_price_snapshot(motilal, SYMBOLS) if motilal else {}

            if not gm_snap and not motilal_snap:
                print(
                    f"\r  Waiting for data — gm:{len(gm_snap)}/{len(SYMBOLS)} "
                    f"motilal:{len(motilal_snap)}/{len(SYMBOLS)}",
                    end="", flush=True,
                )
                time.sleep(REFRESH_INTERVAL)
                continue

            ranked = engine.compute(gm_snap, motilal_snap)
            if not ranked:
                time.sleep(REFRESH_INTERVAL)
                continue

            changed = snapshot_changed(last_ranked, ranked)
            if not changed:
                time.sleep(REFRESH_INTERVAL)
                continue

            last_ranked = [dict(r) for r in ranked]

            # ── Excel (always, instant) ────────────────────────────────────────
            if excel:
                try:
                    excel.update(ranked)
                    excel_writes += 1
                except Exception as e:
                    log.warning(f"Excel error: {e}")

            # ── Web dashboard (broadcast to every connected browser tab) ───────
            if dashboard:
                try:
                    dashboard.broadcast(
                        ranked, highlight_names=HIGHLIGHT_SYMBOLS,
                        ts=datetime.datetime.now().isoformat(),
                    )
                    dash_writes += 1
                except Exception as e:
                    log.warning(f"Web dashboard error: {e}")

            # ── Status line ────────────────────────────────────────────────────
            elapsed = (time.time() - t0) * 1000
            top     = ranked[0]
            demo_tag = " [DEMO]" if DEMO_MODE else ""
            excel_icon = f"📊{excel_writes}" if excel else "❌"
            dash_icon  = f"🌐{dash_writes}" if dashboard else "❌"
            print(
                f"\r  #{tick:5d}  {datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]}"
                f"{demo_tag}"
                f"  {top['script_name'][:18]:<18}"
                f"  B2S:{top['buy_to_sell']:+6.2f}"
                f"  S2B:{top['sell_to_buy']:+6.2f}"
                f"  {excel_icon}Excel"
                f"  {dash_icon}Web"
                f"  [{elapsed:.0f}ms]        ",
                end="", flush=True,
            )

            sleep_for = max(0, REFRESH_INTERVAL - (time.time() - t0))
            time.sleep(sleep_for)

    except KeyboardInterrupt:
        print("\n\nStopped by user.")
    finally:
        log.info("Disconnecting ...")
        if gm:
            try: gm.disconnect()
            except Exception: pass
        if motilal:
            try: motilal.disconnect()
            except Exception: pass
        if excel:
            excel.disconnect()
        if dashboard:
            dashboard.stop()
        print("Done.")


if __name__ == "__main__":
    main()