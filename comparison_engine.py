"""
comparison_engine.py — Price comparison and ranking engine
===========================================================
Matches symbols from GM Global and Motilal Oswal,
calculates Buy-to-Sell and Sell-to-Buy differences,
and returns rows sorted by best opportunity (highest absolute value).
"""

from typing import Dict, List, Optional
from config import DEFAULT_LOT_SIZE


class ComparisonEngine:
    def __init__(self, symbols: List[dict]):
        """
        symbols: list of dicts with keys:
            name        — display name  e.g. "AUROPHARMA 28-JUL-2026"
            code        — script code   e.g. 61113
            mo_scrip    — Motilal scrip code
        """
        self._symbols = symbols

    def compute(
        self,
        gm_prices:      Dict[str, dict],   # keyed by name → {buy, sell}
        motilal_prices: Dict[str, dict],   # keyed by name → {buy, sell}
    ) -> List[dict]:
        """
        Returns a sorted list of row dicts, highest opportunity first.

        Each row:
            script_name, script_code,
            motilal_buy, motilal_sell,
            gm_buy,      gm_sell,
            buy_to_sell  (motilal_buy - gm_sell),
            sell_to_buy  (gm_buy - motilal_sell),
            best_opp     (label string)
        """
        rows = []

        for sym in self._symbols:
            name = sym["name"]
            gp   = gm_prices.get(name)
            mp   = motilal_prices.get(name)

            if gp is None or mp is None:
                continue

            motilal_buy  = mp.get("buy")
            motilal_sell = mp.get("sell")
            gm_buy       = gp.get("buy")
            gm_sell      = gp.get("sell")

            # A price can legitimately be absent OR present-but-None — a GM
            # Global tick can arrive without every field, and Motilal returns
            # None until it has an ltp (its buy/sell are the ltp on both
            # sides — see motilal_feed.get_quote).
            #
            # Skip the symbol rather than defaulting to 0.0: a 0.0 stand-in
            # manufactures a spread the size of the whole contract (buy
            # 3000 - sell 0 = +3000), and because rows are ranked by that
            # number it would sort to the top and read as the single best
            # opportunity on screen. No data has to mean no row.
            if not all(isinstance(v, (int, float)) and not isinstance(v, bool)
                       for v in (motilal_buy, motilal_sell, gm_buy, gm_sell)):
                continue

            lot_size = sym.get("lot_size", DEFAULT_LOT_SIZE)

            try:
                lot_size = int(lot_size)
            except (TypeError, ValueError):
                lot_size = DEFAULT_LOT_SIZE

            

            # Buy on Motilal, sell on GM Global
            buy_to_sell = round(motilal_buy - gm_sell, 4)

            # Buy on GM Global, sell on Motilal
            sell_to_buy = round(gm_buy - motilal_sell, 4)
            buy_total = round(buy_to_sell * lot_size, 4)
            sell_total = round(sell_to_buy * lot_size, 4)

            best = max(buy_total, sell_total)

            if buy_total >= sell_total:
                best_opp = (
                    f"Buy Alpha→Sell Beta  {buy_to_sell:+.2f}  "
                    f"(lot: {buy_total:+.2f})"
                )
            else:
                best_opp = (
                    f"Buy Beta→Sell Alpha  {sell_to_buy:+.2f}  "
                    f"(lot: {sell_total:+.2f})"
                )

            rows.append({
                "script_name":  name,
                "script_code":  sym["code"],
                "motilal_buy":  motilal_buy,
                "motilal_sell": motilal_sell,
                "gm_buy":       gm_buy,
                "gm_sell":      gm_sell,
                "buy_to_sell": buy_to_sell,
                "buy_total": buy_total,
                "sell_to_buy": sell_to_buy,
                "sell_total": sell_total,
                "lot_size": lot_size,
                "best_opp":     best_opp,
                "_sort_key":    best,
            })

        # Sort: highest profitable opportunity first
        rows.sort(key=lambda r: r["_sort_key"], reverse=True)
        for r in rows:
            del r["_sort_key"]

        return rows