"""
comparison_engine.py — Price comparison and ranking engine
===========================================================
Matches symbols from Angel One and Motilal Oswal,
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
            angel_token — Angel One token
            mo_scrip    — Motilal scrip code
        """
        self._symbols = symbols

    def compute(
        self,
        angel_prices:   Dict[str, dict],   # keyed by name → {buy, sell}
        motilal_prices: Dict[str, dict],   # keyed by name → {buy, sell}
    ) -> List[dict]:
        """
        Returns a sorted list of row dicts, highest opportunity first.

        Each row:
            script_name, script_code,
            motilal_buy, motilal_sell,
            angel_buy,   angel_sell,
            buy_to_sell  (motilal_buy - angel_sell),
            sell_to_buy  (angel_buy - motilal_sell),
            best_opp     (label string)
        """
        rows = []

        for sym in self._symbols:
            name = sym["name"]
            ap   = angel_prices.get(name)
            mp   = motilal_prices.get(name)

            if ap is None or mp is None:
                continue

            motilal_buy  = mp.get("buy",  0.0)
            motilal_sell = mp.get("sell", 0.0)
            angel_buy    = ap.get("buy",  0.0)
            angel_sell   = ap.get("sell", 0.0)
            lot_size = sym.get("lot_size", DEFAULT_LOT_SIZE)

            try:
                lot_size = int(lot_size)
            except (TypeError, ValueError):
                lot_size = DEFAULT_LOT_SIZE

            

            # Buy on Motilal, sell on Angel
            buy_to_sell = round(motilal_buy - angel_sell, 4)

            # Buy on Angel, sell on Motilal
            sell_to_buy = round(angel_buy - motilal_sell, 4)
            buy_total = round(buy_to_sell * lot_size, 4)
            sell_total = round(sell_to_buy * lot_size, 4)

            best = max(buy_total, sell_total)

            if buy_total >= sell_total:
                best_opp = (
                    f"Buy Angel→Sell MO  {buy_to_sell:+.2f}  "
                    f"(lot: {buy_total:+.2f})"
                )
            else:
                best_opp = (
                    f"Buy MO→Sell Angel  {sell_to_buy:+.2f}  "
                    f"(lot: {sell_total:+.2f})"
                )

            rows.append({
                "script_name":  name,
                "script_code":  sym["code"],
                "motilal_buy":  motilal_buy,
                "motilal_sell": motilal_sell,
                "angel_buy":    angel_buy,
                "angel_sell":   angel_sell,
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