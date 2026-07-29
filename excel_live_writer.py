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

WHAT CHANGED vs the original version
-------------------------------------
1. Every tick used to do ~10 separate COM calls PER ROW (color, bold,
   font size, font color, alignment...) with screen updating left ON.
   Excel repaints after each COM write, so rows visibly lit up one at a
   time. Now:
     - screen_updating is turned OFF and calculation set to 'manual'
       for the duration of each update, then flipped back ON at the
       end. Excel buffers every change and shows them all in a single
       repaint -> all rows appear to update simultaneously.
     - Per-row color/bold/alignment is no longer written from Python at
       all. It's expressed once, at setup time, as native Excel
       Conditional Formatting rules (formula-driven), so Excel itself
       recolors rows the instant values.change — zero extra COM calls
       per tick.
2. _write_data is now effectively ONE COM call (the batch values
   write) instead of ~1 + 10*n. This is almost always the actual
   bottleneck behind your "how low can REFRESH_INTERVAL go" question —
   dropping the Python poll interval below this floor achieves nothing
   until the COM-call count per tick comes down, which is what this
   rewrite does.
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

# Upper bound on rows we pre-format with conditional formatting rules.
# Safe to raise if you expect more symbols than this; costs nothing extra
# per tick either way since CF is evaluated by Excel, not written by us.
MAX_DATA_ROWS = 250

# ── Colors (RGB tuples — converted to Excel's native BGR int where needed) ───
def rgb(r, g, b):
    return (r, g, b)

def _bgr(rgb_tuple):
    """Excel's COM Interior.Color / Font.Color want a single BGR integer,
    not an (r,g,b) tuple. xlwings' high-level .color= setter accepts
    tuples, but the low-level FormatConditions API (used for conditional
    formatting) needs this raw integer form."""
    r, g, b = rgb_tuple
    return r + (g << 8) + (b << 16)

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

TOTAL_COLS = 11   # A=Rank B=Script C=AngBuy D=AngSell E=MoBuy F=MoSell G=B2S H=BuyTotal I=S2B J=SellTotal K=BestOpp

# Excel COM constants (avoids needing win32com.client.constants)
XL_EXPRESSION  = 2     # xlExpression
XL_CENTER      = -4108  # xlCenter
XL_LEFT        = -4131  # xlLeft
FORMAT_CONDITION_TEXT_TYPE = 2  # xlCellValue (used for exact-text rank rules)


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
            self._wb = xw.Book()
            self._wb.save(self._wb_name)
            print(f"  ✅ Excel: created new workbook '{self._wb_name}'")

        if self._sh_name in [s.name for s in self._wb.sheets]:
            self._sh = self._wb.sheets[self._sh_name]
        else:
            self._sh = self._wb.sheets.add(self._sh_name)

        app = self._wb.app
        prev_su = app.screen_updating
        try:
            app.screen_updating = False
            self._setup_headers()
            self._setup_conditional_formatting()
        finally:
            app.screen_updating = prev_su

    def _setup_headers(self):
        sh = self._sh

        # ── Row 1: Group labels ────────────────────────────────────────────────
        headers_r1 = [
            "#", "SCRIPT NAME", "ANGEL ONE", "", "MOTILAL OSWAL", "",
            "DIFFERENCE", "", "DIFFERENCE", "", "BEST OPPORTUNITY",
        ]
        sh["A1"].value = headers_r1

        sh["C1:D1"].merge()
        sh["E1:F1"].merge()
        sh["G1:H1"].merge()
        sh["I1:J1"].merge()

        r1_colors = [HDR_RANK, HDR_DARK, HDR_ANG, HDR_ANG, HDR_MO, HDR_MO,
                     HDR_DIFF, HDR_DIFF, HDR_DIFF, HDR_DIFF, HDR_DARK]
        for i, color in enumerate(r1_colors):
            cell = sh[0, i]
            cell.color = color
            cell.font.bold  = True
            cell.font.size  = 10
            cell.font.color = WHITE
            cell.api.HorizontalAlignment = XL_CENTER

        sh.range("A1:K1").row_height = 24

        # ── Row 2: Column labels ───────────────────────────────────────────────
        headers_r2 = ["", "", "BUY PRICE", "SELL PRICE", "BUY RATE", "SELL RATE",
                      "BUY→SELL", "BUY TOTAL", "SELL→BUY", "SELL TOTAL", ""]
        sh["A2"].value = headers_r2

        for i in range(TOTAL_COLS):
            cell = sh[1, i]
            cell.color = (40, 40, 40)
            cell.font.bold  = True
            cell.font.size  = 9
            cell.font.color = WHITE
            cell.api.HorizontalAlignment = XL_CENTER

        sh.range("A2:K2").row_height = 22

        col_widths = [5, 26, 11, 11, 11, 11, 12, 12, 12, 12, 35]
        for i, w in enumerate(col_widths):
            sh.range(1, i + 1).column_width = w

        sh.api.Application.ActiveWindow.FreezePanes = False
        sh.activate()
        sh["A3"].select()
        sh.api.Application.ActiveWindow.FreezePanes = True

        # ── One-time STATIC formatting across the whole data range ─────────────
        # (bold/alignment that never changes per tick — no reason to re-set it
        # every update, unlike the old per-tick loop.)
        last_row = DATA_START_ROW + MAX_DATA_ROWS - 1
        full_range = sh.range(f"A{DATA_START_ROW}:K{last_row}")
        full_range.font.size = 10
        full_range.api.HorizontalAlignment = XL_CENTER

        rank_col   = sh.range(f"A{DATA_START_ROW}:A{last_row}")
        rank_col.font.bold = True
        rank_col.font.size = 11

        script_col = sh.range(f"B{DATA_START_ROW}:B{last_row}")
        script_col.font.bold = True
        script_col.api.HorizontalAlignment = XL_LEFT

        for col in ("G", "H", "I", "J"):
            sh.range(f"{col}{DATA_START_ROW}:{col}{last_row}").font.bold = True

    def _setup_conditional_formatting(self):
        """Replaces the old per-row Python color/font loop. Set once;
        Excel re-evaluates these formulas itself on every recalculation —
        no COM round-trip from Python needed per tick."""
        sh = self._sh
        last_row = DATA_START_ROW + MAX_DATA_ROWS - 1
        row0 = DATA_START_ROW  # anchor row for relative formulas

        row_range = sh.range(f"A{DATA_START_ROW}:K{last_row}")
        try:
            row_range.api.FormatConditions.Delete()
        except Exception:
            pass

        # Row fill: green if best per-unit diff > 0, yellow if within
        # threshold (magnitude), else red. Mirrors the original logic:
        #   best_val = max(buy_to_sell, sell_to_buy)   (columns G, I)
        rules = [
            (f"=MAX($G{row0},$I{row0})>0", ROW_GREEN),
            (f"=AND(MAX($G{row0},$I{row0})<=0,ABS(MAX($G{row0},$I{row0}))>={self._threshold})", ROW_YELLOW),
        ]
        for formula, color in rules:
            fc = row_range.api.FormatConditions.Add(Type=XL_EXPRESSION, Formula1=formula)
            fc.Interior.Color = _bgr(color)
            fc.StopIfTrue = False
        # Fallback / default fill = red, applied as a plain (non-conditional)
        # background so rows with no other rule matching still read as red.
        row_range.color = ROW_RED

        # Rank column medal colors — rank text is static ("#1","#2","#3")
        # so an exact-text CF rule is cheap and correct.
        rank_range = sh.range(f"A{DATA_START_ROW}:A{last_row}")
        for rank_num, color in ((1, GOLD), (2, SILVER), (3, BRONZE)):
            formula = f'=$A{row0}="#{rank_num}"'
            fc = rank_range.api.FormatConditions.Add(Type=XL_EXPRESSION, Formula1=formula)
            fc.Font.Color = _bgr(color)
            fc.StopIfTrue = False

        # Font color per value column: green if positive, red otherwise.
        for col in ("G", "H", "I", "J"):
            col_range = sh.range(f"{col}{DATA_START_ROW}:{col}{last_row}")
            fc_pos = col_range.api.FormatConditions.Add(Type=XL_EXPRESSION, Formula1=f"=${col}{row0}>0")
            fc_pos.Font.Color = _bgr(DKGRN)
            fc_pos.StopIfTrue = False
            fc_neg = col_range.api.FormatConditions.Add(Type=XL_EXPRESSION, Formula1=f"=${col}{row0}<=0")
            fc_neg.Font.Color = _bgr(DKRED)
            fc_neg.StopIfTrue = False

    # ── Called every tick ────────────────────────────────────────────────────
    def update(self, ranked_rows: List[Dict]):
        with self._lock:
            app = self._wb.app
            prev_su    = app.screen_updating
            prev_calc  = app.calculation
            try:
                app.screen_updating = False
                app.calculation = 'manual'
                self._write_data(ranked_rows)
            except Exception as e:
                print(f"  [Excel] Write error: {e}")
            finally:
                app.calculation = prev_calc
                app.screen_updating = prev_su   # single repaint happens here

    def _write_data(self, rows: List[Dict]):
        sh = self._sh
        n  = len(rows)

        if n > MAX_DATA_ROWS:
            # Pre-formatted range isn't big enough — extend on the fly
            # (rare; only matters if you add many more symbols than
            # MAX_DATA_ROWS). Raise MAX_DATA_ROWS instead if this fires
            # often, since re-running CF setup mid-flight costs a repaint.
            print(f"  [Excel] Warning: {n} rows exceeds MAX_DATA_ROWS={MAX_DATA_ROWS}; truncating.")
            rows = rows[:MAX_DATA_ROWS]
            n = MAX_DATA_ROWS

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
                r["buy_total"],
                s2b,
                r["sell_total"],
                r.get("best_opp", ""),
            ])

        # Clear extra rows left over from a previous tick with more rows.
        # Conditional formatting stays in place (it's on the whole range,
        # set up once) — clearing contents just blanks the cells so old
        # values/colors don't linger.
        if self._last_rows > n:
            clear_start = DATA_START_ROW + n
            clear_end   = DATA_START_ROW + self._last_rows - 1
            sh.range(f"A{clear_start}:K{clear_end}").clear_contents()

        # Single batch write — this is now the ONLY per-tick COM call that
        # touches the data range. All coloring/bolding is handled by the
        # conditional formatting rules set up once in _setup_conditional_formatting.
        end_row = DATA_START_ROW + n - 1
        sh.range(f"A{DATA_START_ROW}:K{end_row}").value = values

        # Timestamp (one more small, cheap write)
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