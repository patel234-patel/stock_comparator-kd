"""
price_log.py — shared per-symbol update trail for both feeds.

Every time Angel One or Motilal updates a symbol's price (via WS or REST),
one CSV line is appended: timestamp,broker,source,symbol,buy,sell,ltp.

This exists to let you *measure* lag objectively instead of eyeballing the
console: filter price_updates.log by symbol, compare ANGEL vs MOTILAL row
timestamps, and see exactly how many seconds behind (or how stale) Motilal
actually is per symbol, rather than guessing from a scrolling status line.
"""

import logging
from logging.handlers import RotatingFileHandler

_logger = logging.getLogger("price_trail")
_logger.setLevel(logging.INFO)
_logger.propagate = False  # keep separate from main.py's arbitrage.log

if not _logger.handlers:
    _handler = RotatingFileHandler(
        "price_updates.log", maxBytes=20_000_000, backupCount=3, encoding="utf-8"
    )
    _handler.setFormatter(logging.Formatter(
        "%(asctime)s.%(msecs)03d,%(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    ))
    _logger.addHandler(_handler)


def log_update(broker: str, source: str, name: str, buy, sell, ltp) -> None:
    """Append one row: timestamp,broker,source,symbol,buy,sell,ltp"""
    _logger.info(f"{broker},{source},{name},{buy},{sell},{ltp}")
