"""
excel_live_writer.py — Live Excel updater using xlwings
========================================================
Updates an OPEN Excel workbook in real time (milliseconds).
No file save/reload needed — xlwings talks directly to the
running Excel process via COM (Windows) / AppleScript (Mac).

pip install xlwings

IMPORTANT: Excel must be OPEN with the workbook before running main.py.
Run: py setup_excel.py   ← creates and opens the workbook once
Then: py main.py          ← updates it live every tick
"""

import datetime
import threading
from typing import List, Dict

try:
    import xlwings as xw
except ImportError:
    xw = None

# ── Layout (same as Google Sheet) ─────────────────────────────────────────────
DATA_START_ROW = 3   # 1-based; rows 1+2 are headers

# ── Colors (Excel uses BGR hex strings or RGB tuples) ─────────────────────────
def rgb(r, g, b):
    return (r, g, b)

ROW_GREEN  = rgb(198, 239, 206)
ROW_RED    = rgb(255, 199, 206)
ROW_YELLOW = rgb(255, 235, 156)
ROW_WHITE  = rgb(255, 255, 255)

HDR_DARK  = rgb(13,  51,  73)
HDR_MO    = rgb(17,  85, 204)
HDR_ANG   = rgb(15, 157,  88)
HDR_DIFF  = rgb(180, 95,   6)
HDR_RANK  = rgb(60,  60,  60)

WHITE = rgb(255, 255, 255)
BLACK = rgb(0,   0,   0)
GOLD  = rgb(255, 215,   0)
SILVER= rgb(150, 150, 150)
BRONZE= rgb(205, 127,  50)
DKGRN = rgb(0,  128,   0)
DKRED = rgb(180,  0,   0)

TOTAL_COLS = 9   # A=Rank B=Script C=AngBuy D=AngSell E=MoBuy F=MoSell G=B2S H=S2B I=BestOpp


class ExcelLiveWriter:
    def __init__(self, workbook_name: str = "Arbitrage_Dashboard.xlsx",
                 sheet_name: str = "Dashboard", diff_threshold: float = 2.0):
        if xw is None:
            raise ImportError("Run: pip install xlwings")

        self._wb_name    = workbook_name
        self._sh_name    = sheet_name
        self._threshold  = diff_threshold
        self._lock       = threading.Lock()
        self._last_rows  = 0
        self._wb         = None
        self._sh         = None

        self._connect()

    def _connect(self):
        """Attach to an already-open Excel workbook, or create+open one."""
        try:
            self._wb = xw.Book(self._wb_name)
            print(f"  ✅ Excel: attached to open workbook '{self._wb_name}'")
        except Exception:
            # Workbook not open — create it
            self._wb = xw.Book()
            self._wb.save(self._wb_name)
            print(f"  ✅ Excel: created new workbook '{self._wb_name}'")

        # Get or create sheet
        if self._sh_name in [s.name for s in self._wb.sheets]:
            self._sh = self._wb.sheets[self._sh_name]
        else:
            self._sh = self._wb.sheets.add(self._sh_name)

        self._setup_headers()

    def _setup_headers(self):
        sh = self._sh

        # ── Row 1: Group labels ────────────────────────────────────────────────
        headers_r1 = ["#", "SCRIPT NAME", "ANGEL ONE", "", "MOTILAL OSWAL", "",
                       "DIFFERENCE", "", "BEST OPPORTUNITY"]
        sh["A1"].value = headers_r1

        # Merge group cells
        sh["C1:D1"].merge()   # ANGEL ONE
        sh["E1:F1"].merge()   # MOTILAL OSWAL
        sh["G1:H1"].merge()   # DIFFERENCE

        # Color row 1 cell by cell
        r1_colors = [HDR_RANK, HDR_DARK, HDR_ANG, HDR_ANG,
                     HDR_MO, HDR_MO, HDR_DIFF, HDR_DIFF, HDR_DARK]
        for i, color in enumerate(r1_colors):
            cell = sh[0, i]   # 0-based in xlwings
            cell.color = color
            cell.font.bold  = True
            cell.font.size  = 10
            cell.font.color = WHITE
            cell.api.HorizontalAlignment = -4108   # xlCenter

        sh.range("A1:I1").row_height = 24

        # ── Row 2: Column labels ───────────────────────────────────────────────
        headers_r2 = ["", "", "BUY PRICE", "SELL PRICE",
                       "BUY RATE", "SELL RATE", "BUY→SELL", "SELL→BUY", ""]
        sh["A2"].value = headers_r2

        for i in range(TOTAL_COLS):
            cell = sh[1, i]
            cell.color = (40, 40, 40)
            cell.font.bold  = True
            cell.font.size  = 9
            cell.font.color = WHITE
            cell.api.HorizontalAlignment = -4108

        sh.range("A2:I2").row_height = 22

        # ── Column widths ──────────────────────────────────────────────────────
        col_widths = [5, 26, 11, 11, 11, 11, 12, 12, 22]
        for i, w in enumerate(col_widths):
            sh.range(1, i+1).column_width = w

        # Freeze top 2 rows
        sh.api.Application.ActiveWindow.FreezePanes = False
        sh.activate()
        sh["A3"].select()
        sh.api.Application.ActiveWindow.FreezePanes = True

    # ── Called every tick where Google Sheet push returned False ───────────────
    def update(self, ranked_rows: List[Dict]):
        with self._lock:
            try:
                self._write_data(ranked_rows)
            except Exception as e:
                print(f"  [Excel] Write error: {e}")

    def _write_data(self, rows: List[Dict]):
        sh = self._sh
        n  = len(rows)

        # Build value grid for batch write (much faster than cell-by-cell)
        values = []
        for i, r in enumerate(rows):
            rank_label = ["#1", "#2", "#3"][i] if i < 3 else f"#{i+1}"
            b2s = round(r["buy_to_sell"], 4)
            s2b = round(r["sell_to_buy"], 4)
            values.append([
                rank_label,
                r["script_name"],
                r["angel_buy"],
                r["angel_sell"],
                r["motilal_buy"],
                r["motilal_sell"],
                b2s,
                s2b,
                r.get("best_opp", ""),
            ])

        # Clear extra rows from last update
        if self._last_rows > n:
            clear_start = DATA_START_ROW + n
            clear_end   = DATA_START_ROW + self._last_rows - 1
            sh.range(f"A{clear_start}:I{clear_end}").clear_contents()
            sh.range(f"A{clear_start}:I{clear_end}").color = ROW_WHITE

        # Batch write all values in ONE call (fast)
        end_row = DATA_START_ROW + n - 1
        sh.range(f"A{DATA_START_ROW}:I{end_row}").value = values

        # Apply formatting row by row (colours + font)
        for i, r in enumerate(rows):
            row_num = DATA_START_ROW + i   # 1-based Excel row

            b2s = r["buy_to_sell"]
            s2b = r["sell_to_buy"]
            best_val = max(b2s, s2b)

            row_color = (ROW_GREEN  if best_val > 0
                         else ROW_YELLOW if abs(best_val) >= self._threshold
                         else ROW_RED)

            row_range = sh.range(f"A{row_num}:I{row_num}")
            row_range.color     = row_color
            row_range.font.size = 10
            row_range.font.bold = False
            row_range.font.color= BLACK
            row_range.api.HorizontalAlignment = -4108   # xlCenter

            # Rank cell: bold + medal color
            rank_colors = [GOLD, SILVER, BRONZE]
            sh[row_num-1, 0].font.bold  = True
            sh[row_num-1, 0].font.color = rank_colors[i] if i < 3 else BLACK
            sh[row_num-1, 0].font.size  = 11

            # Script name: left align + bold
            sh[row_num-1, 1].api.HorizontalAlignment = -4131  # xlLeft
            sh[row_num-1, 1].font.bold = True

            # BUY→SELL: green/red text
            sh[row_num-1, 6].font.bold  = True
            sh[row_num-1, 6].font.color = DKGRN if b2s > 0 else DKRED

            # SELL→BUY: green/red text
            sh[row_num-1, 7].font.bold  = True
            sh[row_num-1, 7].font.color = DKGRN if s2b > 0 else DKRED

        # Timestamp
        ts_row = DATA_START_ROW + n + 1
        ts_str = datetime.datetime.now().strftime("⟳ Last updated: %d-%b-%Y  %H:%M:%S.%f")[:-3]
        sh[f"A{ts_row}"].value      = ts_str
        sh[f"A{ts_row}"].font.color = (100, 100, 100)
        sh[f"A{ts_row}"].font.size  = 9

        self._last_rows = n

    def disconnect(self):
        """Save workbook on exit."""
        try:
            if self._wb:
                self._wb.save()
                print(f"  Excel workbook saved: {self._wb_name}")
        except Exception as e:
            print(f"  [Excel] Save error: {e}")