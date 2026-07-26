# # """
# # google_sheet_writer.py — Real-time Google Sheets updater
# # =========================================================
# # Overwrites existing rows every second. Never appends.
# # Uses batch updates for performance.

# # pip install gspread google-auth
# # """

# # import datetime
# # import threading
# # from typing import List, Dict

# # try:
# #     import gspread
# #     from google.oauth2.service_account import Credentials
# # except ImportError:
# #     gspread = None

# # # ── Formatting constants ───────────────────────────────────────────────────────
# # SCOPES = [
# #     "https://www.googleapis.com/auth/spreadsheets",
# #     "https://www.googleapis.com/auth/drive",
# # ]

# # # Row indices (1-based)
# # HEADER_ROW_1   = 1   # merged: MOTILAL / ANGEL / DIFFERENCE
# # HEADER_ROW_2   = 2   # column labels
# # DATA_START_ROW = 3   # first data row

# # # Column positions (1-based)
# # COLS = {
# #     "script_name":   1,
# #     "script_code":   2,
# #     "motilal_buy":   3,
# #     "motilal_sell":  4,
# #     "angel_buy":     5,
# #     "angel_sell":    6,
# #     "buy_to_sell":   7,
# #     "sell_to_buy":   8,
# #     "best_opp":      9,
# # }

# # # Conditional format colors (Google Sheets RGB as dicts)
# # COLOR_GREEN  = {"red": 0.714, "green": 0.843, "blue": 0.659}  # positive profit
# # COLOR_RED    = {"red": 1.0,   "green": 0.784, "blue": 0.784}  # negative
# # COLOR_YELLOW = {"red": 1.0,   "green": 0.945, "blue": 0.612}  # threshold exceeded
# # COLOR_WHITE  = {"red": 1.0,   "green": 1.0,   "blue": 1.0}


# # class GoogleSheetWriter:
# #     def __init__(self, credentials_file: str, spreadsheet_id: str,
# #                  worksheet_name: str = "Sheet1", diff_threshold: float = 2.0):
# #         """
# #         credentials_file  : path to your service account JSON key file
# #         spreadsheet_id    : extracted from the Google Sheet URL
# #         worksheet_name    : tab name in the spreadsheet
# #         diff_threshold    : differences beyond ±this value get yellow highlight
# #         """
# #         if gspread is None:
# #             raise ImportError("Run: pip install gspread google-auth")

# #         self._spreadsheet_id  = spreadsheet_id
# #         self._worksheet_name  = worksheet_name
# #         self._diff_threshold  = diff_threshold
# #         self._lock            = threading.Lock()
# #         self._last_row_count  = 0

# #         creds = Credentials.from_service_account_file(credentials_file, scopes=SCOPES)
# #         self._client = gspread.authorize(creds)
# #         self._sh     = self._client.open_by_key(spreadsheet_id)
# #         self._ws     = self._sh.worksheet(worksheet_name)
# #         self._ws_id  = self._ws.id

# #         self._setup_headers()
# #         print("  ✅ Google Sheets connected.")

# #     # ── One-time header setup ──────────────────────────────────────────────────
# #     def _setup_headers(self):
# #         """Write merged header rows and freeze them. Safe to call multiple times."""
# #         requests_body = []

# #         # Freeze first 2 rows
# #         requests_body.append({
# #             "updateSheetProperties": {
# #                 "properties": {
# #                     "sheetId": self._ws_id,
# #                     "gridProperties": {"frozenRowCount": 2}
# #                 },
# #                 "fields": "gridProperties.frozenRowCount"
# #             }
# #         })

# #         # Set column widths (pixels)
# #         col_widths = [200, 110, 100, 100, 100, 100, 120, 120, 140]
# #         for i, px in enumerate(col_widths):
# #             requests_body.append({
# #                 "updateDimensionProperties": {
# #                     "range": {
# #                         "sheetId":    self._ws_id,
# #                         "dimension":  "COLUMNS",
# #                         "startIndex": i,
# #                         "endIndex":   i + 1,
# #                     },
# #                     "properties": {"pixelSize": px},
# #                     "fields": "pixelSize"
# #                 }
# #             })

# #         self._sh.batch_update({"requests": requests_body})

# #         # Write header text via values (simpler than batchUpdate for text)
# #         # Row 1: group labels
# #         self._ws.update(
# #             "A1:I1",
# #             [["SCRIPT NAME", "SCRIPT CODE", "MOTILAL", "", "ANGEL", "", "DIFFERENCE", "", ""]],
# #             value_input_option="RAW"
# #         )
# #         # Row 2: column labels
# #         self._ws.update(
# #             "A2:I2",
# #             [["", "", "BUY RATE", "SELL RATE", "BUY PRICE", "SELL PRICE",
# #               "BUY TO SELL", "SELL TO BUY", "BEST OPPORTUNITY"]],
# #             value_input_option="RAW"
# #         )

# #     # ── Main update called every second ───────────────────────────────────────
# #     def update(self, ranked_rows: List[Dict]):
# #         """
# #         ranked_rows: list of dicts (already sorted, highest opportunity first)
# #         Each dict keys: script_name, script_code, motilal_buy, motilal_sell,
# #                         angel_buy, angel_sell, buy_to_sell, sell_to_buy, best_opp
# #         """
# #         with self._lock:
# #             self._write_data(ranked_rows)

# #     def _write_data(self, rows: List[Dict]):
# #         n = len(rows)

# #         # Build value matrix
# #         values = []
# #         for r in rows:
# #             values.append([
# #                 r["script_name"],
# #                 r["script_code"],
# #                 r["motilal_buy"],
# #                 r["motilal_sell"],
# #                 r["angel_buy"],
# #                 r["angel_sell"],
# #                 round(r["buy_to_sell"], 4),
# #                 round(r["sell_to_buy"], 4),
# #                 r.get("best_opp", ""),
# #             ])

# #         # If fewer rows than before, pad with empty rows to clear old data
# #         prev = self._last_row_count
# #         if prev > n:
# #             for _ in range(prev - n):
# #                 values.append([""] * 9)

# #         end_row = DATA_START_ROW + max(n, prev) - 1
# #         range_str = f"A{DATA_START_ROW}:I{end_row}"

# #         self._ws.update(range_str, values, value_input_option="RAW")

# #         # Apply cell colors
# #         color_requests = []
# #         for i, r in enumerate(rows):
# #             row_idx = DATA_START_ROW + i  # 1-based

# #             # Color buy_to_sell cell (col G = index 6)
# #             color_requests.append(
# #                 self._cell_color_request(row_idx, 7, r["buy_to_sell"])
# #             )
# #             # Color sell_to_buy cell (col H = index 7)
# #             color_requests.append(
# #                 self._cell_color_request(row_idx, 8, r["sell_to_buy"])
# #             )

# #         if color_requests:
# #             self._sh.batch_update({"requests": color_requests})

# #         # Update timestamp in a side cell
# #         ts = datetime.datetime.now().strftime("Last updated: %H:%M:%S")
# #         self._ws.update(f"A{DATA_START_ROW + max(n, prev) + 1}", [[ts]])

# #         self._last_row_count = n

# #     def _cell_color_request(self, row_1based: int, col_1based: int, value: float) -> dict:
# #         """Return a batchUpdate request to color a single cell."""
# #         if value > 0:
# #             color = COLOR_GREEN
# #         elif value < -self._diff_threshold:
# #             color = COLOR_RED
# #         elif abs(value) >= self._diff_threshold:
# #             color = COLOR_YELLOW
# #         else:
# #             color = COLOR_WHITE

# #         return {
# #             "repeatCell": {
# #                 "range": {
# #                     "sheetId":          self._ws_id,
# #                     "startRowIndex":    row_1based - 1,
# #                     "endRowIndex":      row_1based,
# #                     "startColumnIndex": col_1based - 1,
# #                     "endColumnIndex":   col_1based,
# #                 },
# #                 "cell": {
# #                     "userEnteredFormat": {
# #                         "backgroundColor": color
# #                     }
# #                 },
# #                 "fields": "userEnteredFormat.backgroundColor"
# #             }
# #         }


# """
# google_sheet_writer.py — Real-time Google Sheets updater (fully formatted)
# ===========================================================================
# • Overwrites rows every second — never appends
# • Full row color highlighting (green / red / yellow)
# • Bold headers with merged group labels
# • Rank column with #1 #2 #3
# • Frozen header rows
# • Column widths set once on init

# pip install gspread google-auth
# """

# import datetime
# import threading
# from typing import List, Dict

# try:
#     import gspread
#     from google.oauth2.service_account import Credentials
# except ImportError:
#     gspread = None

# SCOPES = [
#     "https://www.googleapis.com/auth/spreadsheets",
#     "https://www.googleapis.com/auth/drive",
# ]

# # ── Row layout ─────────────────────────────────────────────────────────────────
# HEADER_GROUP_ROW = 1   # MOTILAL / ANGEL / DIFFERENCE group labels
# HEADER_COL_ROW   = 2   # BUY / SELL / BUY TO SELL etc
# DATA_START_ROW   = 3   # first live data row

# # Columns: A=Rank B=Script C=Code D=MoBuy E=MoSell F=AngBuy G=AngSell H=B2S I=S2B J=BestOpp
# # (10 columns total, 1-based)
# TOTAL_COLS = 10

# # ── Colors ─────────────────────────────────────────────────────────────────────
# def rgb(r, g, b):
#     return {"red": r/255, "green": g/255, "blue": b/255}

# # Row backgrounds
# ROW_GREEN  = rgb(198, 239, 206)   # profitable
# ROW_RED    = rgb(255, 199, 206)   # loss
# ROW_YELLOW = rgb(255, 235, 156)   # threshold hit
# ROW_WHITE  = rgb(255, 255, 255)

# # Header backgrounds
# HDR_DARK   = rgb(13,  51,  73)    # title row (very dark blue)
# HDR_MO     = rgb(17,  85, 204)    # Motilal group  (blue)
# HDR_ANG    = rgb(15, 157,  88)    # Angel group    (green)
# HDR_DIFF   = rgb(180,  95,   6)   # Difference     (orange)
# HDR_RANK   = rgb(60,  60,  60)    # Rank col       (dark grey)

# WHITE_TEXT = rgb(255, 255, 255)
# BLACK_TEXT = rgb(0,   0,   0)
# GOLD_TEXT  = rgb(255, 215,   0)
# SILVER_TEXT= rgb(192, 192, 192)
# BRONZE_TEXT= rgb(205, 127,  50)


# def _text_fmt(bold=False, color=None, size=10, halign="CENTER"):
#     fmt = {
#         "textFormat": {
#             "bold": bold,
#             "fontSize": size,
#         },
#         "horizontalAlignment": halign,
#     }
#     if color:
#         fmt["textFormat"]["foregroundColor"] = color
#     return fmt


# class GoogleSheetWriter:
#     def __init__(self, credentials_file: str, spreadsheet_id: str,
#                  worksheet_name: str = "Sheet1", diff_threshold: float = 2.0):
#         if gspread is None:
#             raise ImportError("Run: pip install gspread google-auth")

#         self._threshold      = diff_threshold
#         self._lock           = threading.Lock()
#         self._last_row_count = 0
#         self._headers_done   = False

#         creds = Credentials.from_service_account_file(credentials_file, scopes=SCOPES)
#         self._gc  = gspread.authorize(creds)
#         self._sh  = self._gc.open_by_key(spreadsheet_id)
#         self._ws  = self._sh.worksheet(worksheet_name)
#         self._sid = self._ws.id

#         self._setup_sheet()
#         print("  ✅ Google Sheets connected and formatted.")

#     # ── One-time sheet setup ───────────────────────────────────────────────────
#     def _setup_sheet(self):
#         reqs = []

#         # 1. Freeze 2 header rows
#         reqs.append({"updateSheetProperties": {
#             "properties": {"sheetId": self._sid,
#                            "gridProperties": {"frozenRowCount": 2}},
#             "fields": "gridProperties.frozenRowCount"
#         }})

#         # 2. Column widths (px): Rank, Script, Code, MoBuy, MoSell, AngBuy, AngSell, B2S, S2B, Best
#         widths = [50, 220, 90, 90, 90, 90, 90, 100, 100, 180]
#         for i, px in enumerate(widths):
#             reqs.append({"updateDimensionProperties": {
#                 "range": {"sheetId": self._sid, "dimension": "COLUMNS",
#                           "startIndex": i, "endIndex": i+1},
#                 "properties": {"pixelSize": px},
#                 "fields": "pixelSize"
#             }})

#         # 3. Row heights
#         for row_idx, px in [(0, 26), (1, 26)]:  # 0-based
#             reqs.append({"updateDimensionProperties": {
#                 "range": {"sheetId": self._sid, "dimension": "ROWS",
#                           "startIndex": row_idx, "endIndex": row_idx+1},
#                 "properties": {"pixelSize": px},
#                 "fields": "pixelSize"
#             }})

#         # 4. Merge group header cells
#         # Row 1 (0-based row 0):  Rank(A), Script+Code merged(B:C),
#         #   MO group (D:E), Angel group (F:G), Diff group (H:I), Best(J)
#         merges = [
#             (0, 0, 1, 2),   # B:C  → Script + Code
#             (0, 0, 3, 5),   # D:E  → MOTILAL
#             (0, 0, 5, 7),   # F:G  → ANGEL
#             (0, 0, 7, 9),   # H:I  → DIFFERENCE
#         ]
#         for r1, r2, c1, c2 in merges:
#             reqs.append({"mergeCells": {
#                 "range": {"sheetId": self._sid,
#                           "startRowIndex": r1, "endRowIndex": r1+1,
#                           "startColumnIndex": c1, "endColumnIndex": c2},
#                 "mergeType": "MERGE_ALL"
#             }})

#         self._sh.batch_update({"requests": reqs})

#         # 5. Write header text + colors in one values call
#         row1 = [["#", "SCRIPT NAME", "CODE",
#                  "MOTILAL OSWAL", "", "ANGEL ONE", "", "DIFFERENCE", "", "BEST OPPORTUNITY"]]
#         row2 = [["", "", "", "BUY RATE", "SELL RATE",
#                  "BUY PRICE", "SELL PRICE", "BUY→SELL", "SELL→BUY", ""]]

#         self._ws.update("A1:J1", row1, value_input_option="RAW")
#         self._ws.update("A2:J2", row2, value_input_option="RAW")

#         # 6. Format header rows
#         fmt_reqs = []

#         # Row 1 cell-by-cell background + bold white text
#         cell_colors_r1 = [
#             (0, HDR_RANK),   # A — Rank
#             (1, HDR_DARK),   # B — Script (merged B:C)
#             (2, HDR_DARK),   # C
#             (3, HDR_MO),     # D — Motilal (merged D:E)
#             (4, HDR_MO),     # E
#             (5, HDR_ANG),    # F — Angel (merged F:G)
#             (6, HDR_ANG),    # G
#             (7, HDR_DIFF),   # H — Diff (merged H:I)
#             (8, HDR_DIFF),   # I
#             (9, HDR_DARK),   # J — Best
#         ]
#         for col_i, bg in cell_colors_r1:
#             fmt_reqs.append({"repeatCell": {
#                 "range": {"sheetId": self._sid,
#                           "startRowIndex": 0, "endRowIndex": 1,
#                           "startColumnIndex": col_i, "endColumnIndex": col_i+1},
#                 "cell": {"userEnteredFormat": {
#                     "backgroundColor": bg,
#                     "textFormat": {"bold": True, "fontSize": 10,
#                                    "foregroundColor": WHITE_TEXT},
#                     "horizontalAlignment": "CENTER",
#                     "verticalAlignment": "MIDDLE",
#                 }},
#                 "fields": "userEnteredFormat"
#             }})

#         # Row 2 — lighter dark bg, bold white, smaller font
#         fmt_reqs.append({"repeatCell": {
#             "range": {"sheetId": self._sid,
#                       "startRowIndex": 1, "endRowIndex": 2,
#                       "startColumnIndex": 0, "endColumnIndex": TOTAL_COLS},
#             "cell": {"userEnteredFormat": {
#                 "backgroundColor": rgb(40, 40, 40),
#                 "textFormat": {"bold": True, "fontSize": 9,
#                                "foregroundColor": WHITE_TEXT},
#                 "horizontalAlignment": "CENTER",
#                 "verticalAlignment": "MIDDLE",
#             }},
#             "fields": "userEnteredFormat"
#         }})

#         self._sh.batch_update({"requests": fmt_reqs})
#         self._headers_done = True

#     # ── Called every second ────────────────────────────────────────────────────
#     def update(self, ranked_rows: List[Dict]):
#         with self._lock:
#             try:
#                 self._write_data(ranked_rows)
#             except Exception as e:
#                 print(f"  [Sheets] Write error: {e}")

#     def _write_data(self, rows: List[Dict]):
#         n    = len(rows)
#         prev = self._last_row_count

#         # ── 1. Build value matrix ──────────────────────────────────────────────
#         values = []
#         for i, r in enumerate(rows):
#             rank_label = ["#1", "#2", "#3"][i] if i < 3 else f"#{i+1}"
#             b2s = round(r["buy_to_sell"],  4)
#             s2b = round(r["sell_to_buy"],  4)
#             values.append([
#                 rank_label,
#                 r["script_name"],
#                 r["script_code"],
#                 r["motilal_buy"],
#                 r["motilal_sell"],
#                 r["angel_buy"],
#                 r["angel_sell"],
#                 b2s,
#                 s2b,
#                 r.get("best_opp", ""),
#             ])

#         # Pad to clear old rows
#         for _ in range(max(0, prev - n)):
#             values.append([""] * TOTAL_COLS)

#         total_rows = max(n, prev)
#         if total_rows == 0:
#             return

#         end_row   = DATA_START_ROW + total_rows - 1
#         range_str = f"A{DATA_START_ROW}:J{end_row}"
#         self._ws.update(range_str, values, value_input_option="RAW")

#         # ── 2. Format data rows ────────────────────────────────────────────────
#         fmt_reqs = []
#         for i, r in enumerate(rows):
#             row_0 = DATA_START_ROW - 1 + i   # 0-based

#             b2s = r["buy_to_sell"]
#             s2b = r["sell_to_buy"]
#             best_val = max(b2s, s2b)

#             # Choose row background
#             if best_val > 0:
#                 row_bg = ROW_GREEN
#             elif abs(best_val) >= self._threshold:
#                 row_bg = ROW_YELLOW
#             else:
#                 row_bg = ROW_RED

#             # Full row background + base text style
#             fmt_reqs.append({"repeatCell": {
#                 "range": {"sheetId": self._sid,
#                           "startRowIndex": row_0, "endRowIndex": row_0+1,
#                           "startColumnIndex": 0, "endColumnIndex": TOTAL_COLS},
#                 "cell": {"userEnteredFormat": {
#                     "backgroundColor": row_bg,
#                     "textFormat": {"bold": False, "fontSize": 10,
#                                    "foregroundColor": BLACK_TEXT},
#                     "horizontalAlignment": "CENTER",
#                     "verticalAlignment": "MIDDLE",
#                 }},
#                 "fields": "userEnteredFormat"
#             }})

#             # Rank cell — bold, special color for top 3
#             rank_colors = [GOLD_TEXT, SILVER_TEXT, BRONZE_TEXT]
#             rank_color  = rank_colors[i] if i < 3 else BLACK_TEXT
#             fmt_reqs.append({"repeatCell": {
#                 "range": {"sheetId": self._sid,
#                           "startRowIndex": row_0, "endRowIndex": row_0+1,
#                           "startColumnIndex": 0, "endColumnIndex": 1},
#                 "cell": {"userEnteredFormat": {
#                     "textFormat": {"bold": True, "fontSize": 11,
#                                    "foregroundColor": rank_color},
#                     "horizontalAlignment": "CENTER",
#                 }},
#                 "fields": "userEnteredFormat.textFormat,userEnteredFormat.horizontalAlignment"
#             }})

#             # Script name — left aligned, bold
#             fmt_reqs.append({"repeatCell": {
#                 "range": {"sheetId": self._sid,
#                           "startRowIndex": row_0, "endRowIndex": row_0+1,
#                           "startColumnIndex": 1, "endColumnIndex": 2},
#                 "cell": {"userEnteredFormat": {
#                     "textFormat": {"bold": True, "fontSize": 10},
#                     "horizontalAlignment": "LEFT",
#                 }},
#                 "fields": "userEnteredFormat.textFormat,userEnteredFormat.horizontalAlignment"
#             }})

#             # BUY→SELL cell (col H, index 7) — extra bold + own color
#             fmt_reqs.append({"repeatCell": {
#                 "range": {"sheetId": self._sid,
#                           "startRowIndex": row_0, "endRowIndex": row_0+1,
#                           "startColumnIndex": 7, "endColumnIndex": 8},
#                 "cell": {"userEnteredFormat": {
#                     "textFormat": {
#                         "bold": True, "fontSize": 10,
#                         "foregroundColor": rgb(0,128,0) if b2s > 0 else rgb(180,0,0)
#                     }
#                 }},
#                 "fields": "userEnteredFormat.textFormat"
#             }})

#             # SELL→BUY cell (col I, index 8)
#             fmt_reqs.append({"repeatCell": {
#                 "range": {"sheetId": self._sid,
#                           "startRowIndex": row_0, "endRowIndex": row_0+1,
#                           "startColumnIndex": 8, "endColumnIndex": 9},
#                 "cell": {"userEnteredFormat": {
#                     "textFormat": {
#                         "bold": True, "fontSize": 10,
#                         "foregroundColor": rgb(0,128,0) if s2b > 0 else rgb(180,0,0)
#                     }
#                 }},
#                 "fields": "userEnteredFormat.textFormat"
#             }})

#         # Clear formatting on rows that no longer have data
#         for i in range(n, prev):
#             row_0 = DATA_START_ROW - 1 + i
#             fmt_reqs.append({"repeatCell": {
#                 "range": {"sheetId": self._sid,
#                           "startRowIndex": row_0, "endRowIndex": row_0+1,
#                           "startColumnIndex": 0, "endColumnIndex": TOTAL_COLS},
#                 "cell": {"userEnteredFormat": {
#                     "backgroundColor": ROW_WHITE,
#                     "textFormat": {"bold": False, "foregroundColor": BLACK_TEXT},
#                 }},
#                 "fields": "userEnteredFormat"
#             }})

#         if fmt_reqs:
#             self._sh.batch_update({"requests": fmt_reqs})

#         # ── 3. Timestamp below table ───────────────────────────────────────────
#         ts_row = DATA_START_ROW + total_rows + 1
#         ts_str = datetime.datetime.now().strftime("⟳ Last updated: %d-%b-%Y  %H:%M:%S")
#         self._ws.update(f"A{ts_row}", [[ts_str]])

#         self._last_row_count = n

"""
google_sheet_writer.py — Real-time Google Sheets updater (quota-safe)
======================================================================
• Overwrites rows every push — never appends
• Full row color highlighting (green / red / yellow)
• Bold headers with merged group labels
• Rank column with #1 #2 #3
• Frozen header rows
• Column widths set once on init

WHY THIS VERSION IS DIFFERENT
------------------------------
Your original made 3 separate write API calls per update():
  1. self._ws.update(...)        -> values
  2. self._sh.batch_update(...)  -> row/rank/cell colors
  3. self._ws.update(...)        -> timestamp
At a 1s refresh loop that's ~180 write calls/minute against Google
Sheets' per-user write quota (commonly 60/min, sometimes up to
300/min) -> guaranteed 429 "Quota exceeded" errors, which is exactly
what you hit.

Two changes fix this:
  1. THROTTLE: actual sheet pushes are limited to at most once every
     `min_write_interval` seconds (default 2s), independent of how
     often your main loop polls prices. Change `min_write_interval`
     if you have a higher quota and want faster refresh.
  2. CONSOLIDATE: values + timestamp + all formatting are now sent in
     a single spreadsheets.batchUpdate call (updateCells requests)
     instead of 3 separate HTTP calls -> 1 write call per push instead
     of 3, tripling your effective headroom even before throttling.
  3. BACKOFF: a 429 no longer just logs and moves on forever — it
     backs off (skips pushes) for a few seconds so you don't keep
     hammering an already-throttled quota.

pip install gspread google-auth
"""

import datetime
import threading
import time
from typing import List, Dict

try:
    import gspread
    from google.oauth2.service_account import Credentials
except ImportError:
    gspread = None

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# ── Row layout ─────────────────────────────────────────────────────────────────
HEADER_GROUP_ROW = 1
HEADER_COL_ROW   = 2
DATA_START_ROW   = 3

TOTAL_COLS = 9  # A=Rank B=Script C=AngBuy D=AngSell E=MoBuy F=MoSell G=B2S H=S2B I=BestOpp

# ── Colors ─────────────────────────────────────────────────────────────────────
def rgb(r, g, b):
    return {"red": r/255, "green": g/255, "blue": b/255}

ROW_GREEN  = rgb(198, 239, 206)
ROW_RED    = rgb(255, 199, 206)
ROW_YELLOW = rgb(255, 235, 156)
ROW_WHITE  = rgb(255, 255, 255)

HDR_DARK   = rgb(13,  51,  73)
HDR_MO     = rgb(17,  85, 204)
HDR_ANG    = rgb(15, 157,  88)
HDR_DIFF   = rgb(180,  95,   6)
HDR_RANK   = rgb(60,  60,  60)

WHITE_TEXT  = rgb(255, 255, 255)
BLACK_TEXT  = rgb(0,   0,   0)
GOLD_TEXT   = rgb(255, 215,   0)
SILVER_TEXT = rgb(192, 192, 192)
BRONZE_TEXT = rgb(205, 127,  50)


def _num(v):
    """Wrap a python value into a Sheets ExtendedValue for updateCells."""
    if isinstance(v, (int, float)):
        return {"numberValue": v}
    return {"stringValue": "" if v is None else str(v)}


class GoogleSheetWriter:
    def __init__(self, credentials_file: str, spreadsheet_id: str,
                 worksheet_name: str = "Sheet1", diff_threshold: float = 2.0,
                 min_write_interval: float = 2.0):
        if gspread is None:
            raise ImportError("Run: pip install gspread google-auth")

        self._threshold          = diff_threshold
        self._lock               = threading.Lock()
        self._last_row_count     = 0
        self._headers_done       = False
        self._last_write_ts      = 0.0
        self._backoff_until      = 0.0
        # Throttle: actual sheet pushes happen at most this often,
        # regardless of how often update() is called. This is the main
        # fix for the 429 "Write requests per minute" quota error.
        self._min_write_interval = min_write_interval

        creds = Credentials.from_service_account_file(credentials_file, scopes=SCOPES)
        self._gc  = gspread.authorize(creds)
        self._sh  = self._gc.open_by_key(spreadsheet_id)
        self._ws  = self._sh.worksheet(worksheet_name)
        self._sid = self._ws.id

        self._setup_sheet()
        print("  ✅ Google Sheets connected and formatted.")

    # ── One-time sheet setup (unchanged structure, still its own calls —
    #    this only runs once at startup, not per-tick, so it doesn't
    #    contribute to the per-minute quota problem) ────────────────────────────
    def _setup_sheet(self):
        reqs = []

        reqs.append({"updateSheetProperties": {
            "properties": {"sheetId": self._sid,
                           "gridProperties": {"frozenRowCount": 2}},
            "fields": "gridProperties.frozenRowCount"
        }})

        widths = [50, 220, 90, 90, 90, 90, 100, 100, 180]
        for i, px in enumerate(widths):
            reqs.append({"updateDimensionProperties": {
                "range": {"sheetId": self._sid, "dimension": "COLUMNS",
                          "startIndex": i, "endIndex": i+1},
                "properties": {"pixelSize": px},
                "fields": "pixelSize"
            }})

        for row_idx, px in [(0, 26), (1, 26)]:
            reqs.append({"updateDimensionProperties": {
                "range": {"sheetId": self._sid, "dimension": "ROWS",
                          "startIndex": row_idx, "endIndex": row_idx+1},
                "properties": {"pixelSize": px},
                "fields": "pixelSize"
            }})

        # Unmerge the whole header row first. If the sheet still has merges
        # from a previous column layout (e.g. an old CODE column), the new
        # merge ranges below can partially overlap them, which Sheets
        # rejects with "You must select all cells in a merged range to
        # merge or unmerge them." Clearing first avoids that entirely.
        reqs.append({"unmergeCells": {
            "range": {"sheetId": self._sid,
                      "startRowIndex": 0, "endRowIndex": 1,
                      "startColumnIndex": 0, "endColumnIndex": max(TOTAL_COLS, 12)}
        }})

        # Column layout: 0=Rank 1=Script 2-3=Angel 4-5=Motilal 6-7=Diff 8=Best
        merges = [
            (0, 0, 2, 4),   # C:D -> ANGEL ONE
            (0, 0, 4, 6),   # E:F -> MOTILAL OSWAL
            (0, 0, 6, 8),   # G:H -> DIFFERENCE
        ]
        for r1, r2, c1, c2 in merges:
            reqs.append({"mergeCells": {
                "range": {"sheetId": self._sid,
                          "startRowIndex": r1, "endRowIndex": r1+1,
                          "startColumnIndex": c1, "endColumnIndex": c2},
                "mergeType": "MERGE_ALL"
            }})

        self._sh.batch_update({"requests": reqs})

        # Wipe any leftover columns from a previous, wider layout (e.g. the
        # old 10-column version had a column J that this layout no longer
        # uses — without this it keeps showing old, stale header/data).
        CLEAR_UPTO_COL = 14
        reqs.append({"updateCells": {
            "range": {"sheetId": self._sid,
                      "startRowIndex": 0, "endRowIndex": 2,
                      "startColumnIndex": TOTAL_COLS, "endColumnIndex": CLEAR_UPTO_COL},
            "fields": "userEnteredValue,userEnteredFormat"
        }})
        # Same cleanup for the data rows themselves — old layout's column J
        # data would otherwise sit there forever since new pushes never
        # touch that column again. Done once here at startup, not per-tick,
        # to avoid burning extra write quota.
        reqs.append({"updateCells": {
            "range": {"sheetId": self._sid,
                      "startRowIndex": DATA_START_ROW - 1, "endRowIndex": DATA_START_ROW + 100,
                      "startColumnIndex": TOTAL_COLS, "endColumnIndex": CLEAR_UPTO_COL},
            "fields": "userEnteredValue,userEnteredFormat"
        }})

        row1 = [["#", "SCRIPT NAME",
                 "ANGEL ONE", "", "MOTILAL OSWAL", "", "DIFFERENCE", "", "BEST OPPORTUNITY"]]
        row2 = [["", "",
                 "BUY PRICE", "SELL PRICE", "BUY RATE", "SELL RATE", "BUY→SELL", "SELL→BUY", ""]]

        self._ws.update("A1:I1", row1, value_input_option="RAW")
        self._ws.update("A2:I2", row2, value_input_option="RAW")

        fmt_reqs = []
        cell_colors_r1 = [
            (0, HDR_RANK), (1, HDR_DARK),
            (2, HDR_ANG), (3, HDR_ANG),
            (4, HDR_MO), (5, HDR_MO),
            (6, HDR_DIFF), (7, HDR_DIFF),
            (8, HDR_DARK),
        ]
        for col_i, bg in cell_colors_r1:
            fmt_reqs.append({"repeatCell": {
                "range": {"sheetId": self._sid,
                          "startRowIndex": 0, "endRowIndex": 1,
                          "startColumnIndex": col_i, "endColumnIndex": col_i+1},
                "cell": {"userEnteredFormat": {
                    "backgroundColor": bg,
                    "textFormat": {"bold": True, "fontSize": 10,
                                   "foregroundColor": WHITE_TEXT},
                    "horizontalAlignment": "CENTER",
                    "verticalAlignment": "MIDDLE",
                }},
                "fields": "userEnteredFormat"
            }})

        fmt_reqs.append({"repeatCell": {
            "range": {"sheetId": self._sid,
                      "startRowIndex": 1, "endRowIndex": 2,
                      "startColumnIndex": 0, "endColumnIndex": TOTAL_COLS},
            "cell": {"userEnteredFormat": {
                "backgroundColor": rgb(40, 40, 40),
                "textFormat": {"bold": True, "fontSize": 9,
                               "foregroundColor": WHITE_TEXT},
                "horizontalAlignment": "CENTER",
                "verticalAlignment": "MIDDLE",
            }},
            "fields": "userEnteredFormat"
        }})

        self._sh.batch_update({"requests": fmt_reqs})
        self._headers_done = True

    # ── Called every tick from main.py ─────────────────────────────────────────
    def update(self, ranked_rows: List[Dict]):
        now = time.time()

        if now < self._backoff_until:
            return  # still cooling off after a 429

        if now - self._last_write_ts < self._min_write_interval:
            return  # throttled — not time for the next push yet

        with self._lock:
            try:
                self._write_data(ranked_rows)
                self._last_write_ts = now
            except Exception as e:
                msg = str(e)
                if "429" in msg or "Quota exceeded" in msg:
                    # Back off harder than the normal throttle so we
                    # actually recover instead of hammering the quota.
                    self._backoff_until = now + 15.0
                    print(f"  [Sheets] 429 hit — backing off pushes for 15s")
                else:
                    print(f"  [Sheets] Write error: {e}")

    def _write_data(self, rows: List[Dict]):
        n    = len(rows)
        prev = self._last_row_count
        total_rows = max(n, prev)
        if total_rows == 0:
            return

        requests = []

        # ── Build one updateCells request per data row: values + format
        #    combined, so writing N rows is still ONE API call total. ───────────
        for i in range(total_rows):
            row_0 = DATA_START_ROW - 1 + i  # 0-based

            if i < n:
                r = rows[i]
                rank_label = f"#{i+1}"
                b2s = round(r["buy_to_sell"], 4)
                s2b = round(r["sell_to_buy"], 4)
                best_val = max(b2s, s2b)

                if best_val > 0:
                    row_bg = ROW_GREEN
                elif abs(best_val) >= self._threshold:
                    row_bg = ROW_YELLOW
                else:
                    row_bg = ROW_RED

                rank_colors = [GOLD_TEXT, SILVER_TEXT, BRONZE_TEXT]
                rank_color  = rank_colors[i] if i < 3 else BLACK_TEXT

                values = [
                    rank_label, r["script_name"],
                    r["angel_buy"], r["angel_sell"],
                    r["motilal_buy"], r["motilal_sell"],
                    b2s, s2b, r.get("best_opp", ""),
                ]

                row_cells = []
                for col_i, val in enumerate(values):
                    cell_fmt = {
                        "backgroundColor": row_bg,
                        "textFormat": {"bold": False, "fontSize": 10,
                                       "foregroundColor": BLACK_TEXT},
                        "horizontalAlignment": "CENTER",
                        "verticalAlignment": "MIDDLE",
                    }
                    if col_i == 0:  # rank
                        cell_fmt["textFormat"] = {"bold": True, "fontSize": 11,
                                                   "foregroundColor": rank_color}
                    elif col_i == 1:  # script name
                        cell_fmt["textFormat"] = {"bold": True, "fontSize": 10}
                        cell_fmt["horizontalAlignment"] = "LEFT"
                    elif col_i == 6:  # buy->sell
                        cell_fmt["textFormat"] = {
                            "bold": True, "fontSize": 10,
                            "foregroundColor": rgb(0, 128, 0) if b2s > 0 else rgb(180, 0, 0)
                        }
                    elif col_i == 7:  # sell->buy
                        cell_fmt["textFormat"] = {
                            "bold": True, "fontSize": 10,
                            "foregroundColor": rgb(0, 128, 0) if s2b > 0 else rgb(180, 0, 0)
                        }
                    row_cells.append({"userEnteredValue": _num(val),
                                       "userEnteredFormat": cell_fmt})
            else:
                # Clearing a row that no longer has data
                row_cells = [{"userEnteredValue": {"stringValue": ""},
                              "userEnteredFormat": {"backgroundColor": ROW_WHITE,
                                                     "textFormat": {"bold": False,
                                                                    "foregroundColor": BLACK_TEXT}}}
                             for _ in range(TOTAL_COLS)]

            requests.append({
                "updateCells": {
                    "rows": [{"values": row_cells}],
                    "fields": "userEnteredValue,userEnteredFormat",
                    "start": {"sheetId": self._sid, "rowIndex": row_0, "columnIndex": 0},
                }
            })

        # ── Timestamp row folded into the same batch ───────────────────────────
        ts_row_0 = DATA_START_ROW - 1 + total_rows + 1
        ts_str = datetime.datetime.now().strftime("⟳ Last updated: %d-%b-%Y  %H:%M:%S")
        requests.append({
            "updateCells": {
                "rows": [{"values": [{"userEnteredValue": {"stringValue": ts_str}}]}],
                "fields": "userEnteredValue",
                "start": {"sheetId": self._sid, "rowIndex": ts_row_0, "columnIndex": 0},
            }
        })

        # ONE API call for everything above.
        self._sh.batch_update({"requests": requests})

        self._last_row_count = n