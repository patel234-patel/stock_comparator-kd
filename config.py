"""
config.py
"""
import datetime
import os

MARKET_OPEN  = datetime.time(0, 0)
MARKET_CLOSE = datetime.time(23, 59)

# ══════════════════════════════════════════════════════════════════
#  ON / OFF SWITCHES — change True/False only
# ══════════════════════════════════════════════════════════════════
ENABLE_EXCEL        = False    # True  = update open Excel file every tick
ENABLE_WEB_DASHBOARD = True   # True  = serve a live HTML dashboard over WebSocket
                              # (no COM round-trip, so no ~100ms Excel write lag)
DEMO_MODE           = False    # True  = use fake prices (no broker needed)
                              # ← set False when market is open + brokers connected
# ══════════════════════════════════════════════════════════════════

# ── Speed controls ──────────────────────────────────────────────────────────────
REFRESH_INTERVAL     = 0.3   # poll prices every 0.1s (10x per second)

# Diff magnitude (₹, per-lot total) below which an unprofitable row shows
# yellow instead of red on the web dashboard.
DIFF_THRESHOLD = 500.0

# ── Web dashboard (HTML + WebSocket, see web_dashboard.py) ───────────────────
WEB_HOST      = "127.0.0.1"   # bind address; use "0.0.0.0" to view from other devices on your LAN

# Base ports for shard 1. Every further shard is offset by +1, so shard 2
# serves on 8001/8766 — see the SHARD SPLIT block at the bottom of this
# file, which is what actually sets WEB_HTTP_PORT / WEB_WS_PORT.
WEB_HTTP_PORT_BASE = 8000
WEB_WS_PORT_BASE   = 8765

# Fallback lot size used ONLY if a symbol's lot_size couldn't be resolved
# (e.g. fetch_gm_lots.py hasn't been run yet, or the field is still
# "FILL_IN"). Set to 1 so totals just equal the per-unit diff until you
# run the fetch script.
DEFAULT_LOT_SIZE = 1

# ── Symbols ──────────────────────────────────────────────────────────────────
# name:
#   "<SCRIPT> <DD-MON-YYYY>". The first word is also what gm_feed.py turns
#   into a GM Global instrument identifier ("RELIANCE" → "RELIANCE-I"), so
#   it has to match GM Global's script name. Add a "gm_symbol" key to a row
#   to override that if one ever diverges.
# lot_size:
#   Run `py fetch_gm_lots.py` to refresh these from GM Global's own script
#   master (script_lot_qty) — worth doing after every expiry rollover.


SYMBOLS = [
    {"name": "360ONE 25-AUG-2026", "code": 58074, "mo_scrip": 58074, "lot_size": 500},
    {"name": "ABB 25-AUG-2026", "code": 58075, "mo_scrip": 58075, "lot_size": 125},
    {"name": "ABCAPITAL 25-AUG-2026", "code": 58086, "mo_scrip": 58086, "lot_size": 3100},
    {"name": "ADANIENSOL 25-AUG-2026", "code": 58087, "mo_scrip": 58087, "lot_size": 675},
    {"name": "ADANIENT 25-AUG-2026", "code": 58088, "mo_scrip": 58088, "lot_size": 309},
    {"name": "ADANIGREEN 25-AUG-2026", "code": 58089, "mo_scrip": 58089, "lot_size": 600},
    {"name": "ADANIPORTS 25-AUG-2026", "code": 58090, "mo_scrip": 58090, "lot_size": 475},
    {"name": "ADANIPOWER 25-AUG-2026", "code": 58091, "mo_scrip": 58091, "lot_size": 3550},
    {"name": "ALKEM 25-AUG-2026", "code": 58100, "mo_scrip": 58100, "lot_size": 125},
    {"name": "AMBER 25-AUG-2026", "code": 58101, "mo_scrip": 58101, "lot_size": 100},
    {"name": "AMBUJACEM 25-AUG-2026", "code": 58102, "mo_scrip": 58102, "lot_size": 1200},
    {"name": "ANGELONE 25-AUG-2026", "code": 58103, "mo_scrip": 58103, "lot_size": 2500},
    {"name": "APLAPOLLO 25-AUG-2026", "code": 58104, "mo_scrip": 58104, "lot_size": 350},
    {"name": "APOLLOHOSP 25-AUG-2026", "code": 58105, "mo_scrip": 58105, "lot_size": 125},
    {"name": "ASHOKLEY 25-AUG-2026", "code": 58106, "mo_scrip": 58106, "lot_size": 5000},
    {"name": "ASIANPAINT 25-AUG-2026", "code": 58107, "mo_scrip": 58107, "lot_size": 250},
    {"name": "ASTRAL 25-AUG-2026", "code": 58108, "mo_scrip": 58108, "lot_size": 425},
    {"name": "AUBANK 25-AUG-2026", "code": 58109, "mo_scrip": 58109, "lot_size": 1000},
    {"name": "AUROPHARMA 25-AUG-2026", "code": 58116, "mo_scrip": 58116, "lot_size": 550},
    {"name": "AXISBANK 25-AUG-2026", "code": 58117, "mo_scrip": 58117, "lot_size": 625},
    {"name": "BAJAJ-AUTO 25-AUG-2026", "code": 58118, "mo_scrip": 58118, "lot_size": 75},
    {"name": "BAJAJFINSV 25-AUG-2026", "code": 58119, "mo_scrip": 58119, "lot_size": 300},
    {"name": "BAJAJHLDNG 25-AUG-2026", "code": 58120, "mo_scrip": 58120, "lot_size": 75},
    {"name": "BAJFINANCE 25-AUG-2026", "code": 58121, "mo_scrip": 58121, "lot_size": 750},
    {"name": "BANDHANBNK 25-AUG-2026", "code": 58122, "mo_scrip": 58122, "lot_size": 3600},
    {"name": "BANKBARODA 25-AUG-2026", "code": 58123, "mo_scrip": 58123, "lot_size": 2925},
    {"name": "BANKINDIA 25-AUG-2026", "code": 58125, "mo_scrip": 58125, "lot_size": 5200},
    {"name": "BDL 25-AUG-2026", "code": 58126, "mo_scrip": 58126, "lot_size": 425},
    {"name": "BEL 25-AUG-2026", "code": 58130, "mo_scrip": 58130, "lot_size": 1425},
    {"name": "BHARATFORG 25-AUG-2026", "code": 58131, "mo_scrip": 58131, "lot_size": 500},
    {"name": "BHARTIARTL 25-AUG-2026", "code": 58132, "mo_scrip": 58132, "lot_size": 475},
    {"name": "BHEL 25-AUG-2026", "code": 58133, "mo_scrip": 58133, "lot_size": 2625},
    {"name": "BIOCON 25-AUG-2026", "code": 58134, "mo_scrip": 58134, "lot_size": 2500},
    {"name": "BLUESTARCO 25-AUG-2026", "code": 58135, "mo_scrip": 58135, "lot_size": 325},
    {"name": "BOSCHLTD 25-AUG-2026", "code": 58136, "mo_scrip": 58136, "lot_size": 25},
    {"name": "BPCL 25-AUG-2026", "code": 58138, "mo_scrip": 58138, "lot_size": 1975},
    {"name": "BRITANNIA 25-AUG-2026", "code": 58140, "mo_scrip": 58140, "lot_size": 125},
    {"name": "BSE 25-AUG-2026", "code": 58141, "mo_scrip": 58141, "lot_size": 200},
    {"name": "CAMS 25-AUG-2026", "code": 58142, "mo_scrip": 58142, "lot_size": 825},
    {"name": "CANBK 25-AUG-2026", "code": 58143, "mo_scrip": 58143, "lot_size": 6750},
    {"name": "CDSL 25-AUG-2026", "code": 58144, "mo_scrip": 58144, "lot_size": 475},
    {"name": "CGPOWER 25-AUG-2026", "code": 58145, "mo_scrip": 58145, "lot_size": 850},
    {"name": "CHOLAFIN 25-AUG-2026", "code": 58146, "mo_scrip": 58146, "lot_size": 625},
    {"name": "CIPLA 25-AUG-2026", "code": 58147, "mo_scrip": 58147, "lot_size": 425},
    {"name": "COALINDIA 25-AUG-2026", "code": 58148, "mo_scrip": 58148, "lot_size": 1350},
    {"name": "COCHINSHIP 25-AUG-2026", "code": 58149, "mo_scrip": 58149, "lot_size": 400},
    {"name": "COFORGE 25-AUG-2026", "code": 58152, "mo_scrip": 58152, "lot_size": 475},
    {"name": "COLPAL 25-AUG-2026", "code": 58153, "mo_scrip": 58153, "lot_size": 275},
    {"name": "CONCOR 25-AUG-2026", "code": 58154, "mo_scrip": 58154, "lot_size": 1250},
    {"name": "CROMPTON 25-AUG-2026", "code": 58155, "mo_scrip": 58155, "lot_size": 2150},
    {"name": "CUMMINSIND 25-AUG-2026", "code": 58156, "mo_scrip": 58156, "lot_size": 200},
    {"name": "DABUR 25-AUG-2026", "code": 58157, "mo_scrip": 58157, "lot_size": 1250},
    {"name": "DALBHARAT 25-AUG-2026", "code": 58158, "mo_scrip": 58158, "lot_size": 325},
    {"name": "DELHIVERY 25-AUG-2026", "code": 58159, "mo_scrip": 58159, "lot_size": 2075},
    {"name": "DIVISLAB 25-AUG-2026", "code": 58160, "mo_scrip": 58160, "lot_size": 100},
    {"name": "DIXON 25-AUG-2026", "code": 58161, "mo_scrip": 58161, "lot_size": 50},
    {"name": "DLF 25-AUG-2026", "code": 58162, "mo_scrip": 58162, "lot_size": 950},
    {"name": "DMART 25-AUG-2026", "code": 58163, "mo_scrip": 58163, "lot_size": 150},
    {"name": "DRREDDY 25-AUG-2026", "code": 58170, "mo_scrip": 58170, "lot_size": 625},
    {"name": "EICHERMOT 25-AUG-2026", "code": 58181, "mo_scrip": 58181, "lot_size": 100},
    {"name": "ETERNAL 25-AUG-2026", "code": 58182, "mo_scrip": 58182, "lot_size": 2425},
    {"name": "FEDERALBNK 25-AUG-2026", "code": 58183, "mo_scrip": 58183, "lot_size": 2500},
    {"name": "FORCEMOT 25-AUG-2026", "code": 58184, "mo_scrip": 58184, "lot_size": 25},
    {"name": "FORTIS 25-AUG-2026", "code": 58188, "mo_scrip": 58188, "lot_size": 775},
    {"name": "GAIL 25-AUG-2026", "code": 58189, "mo_scrip": 58189, "lot_size": 3550},
    {"name": "GLENMARK 25-AUG-2026", "code": 58198, "mo_scrip": 58198, "lot_size": 375},
    {"name": "GMRAIRPORT 25-AUG-2026", "code": 58199, "mo_scrip": 58199, "lot_size": 6975},
    {"name": "GODFRYPHLP 25-AUG-2026", "code": 58200, "mo_scrip": 58200, "lot_size": 275},
    {"name": "GODREJCP 25-AUG-2026", "code": 58201, "mo_scrip": 58201, "lot_size": 500},
    {"name": "GODREJPROP 25-AUG-2026", "code": 58207, "mo_scrip": 58207, "lot_size": 325},
    {"name": "GRASIM 25-AUG-2026", "code": 58208, "mo_scrip": 58208, "lot_size": 250},
    {"name": "GVT&D 25-AUG-2026", "code": 58211, "mo_scrip": 58211, "lot_size": 125},
    {"name": "HAL 25-AUG-2026", "code": 58212, "mo_scrip": 58212, "lot_size": 150},
    {"name": "HAVELLS 25-AUG-2026", "code": 58213, "mo_scrip": 58213, "lot_size": 500},
    {"name": "HCLTECH 25-AUG-2026", "code": 58214, "mo_scrip": 58214, "lot_size": 400},
    {"name": "HDFCAMC 25-AUG-2026", "code": 58215, "mo_scrip": 58215, "lot_size": 300},
    {"name": "HDFCBANK 25-AUG-2026", "code": 58216, "mo_scrip": 58216, "lot_size": 650},
    {"name": "HDFCLIFE 25-AUG-2026", "code": 58217, "mo_scrip": 58217, "lot_size": 1100},
    {"name": "HEROMOTOCO 25-AUG-2026", "code": 58218, "mo_scrip": 58218, "lot_size": 150},
    {"name": "HINDALCO 25-AUG-2026", "code": 58225, "mo_scrip": 58225, "lot_size": 700},
    {"name": "HINDPETRO 25-AUG-2026", "code": 58226, "mo_scrip": 58226, "lot_size": 2025},
    {"name": "HINDUNILVR 25-AUG-2026", "code": 58227, "mo_scrip": 58227, "lot_size": 300},
    {"name": "HINDZINC 25-AUG-2026", "code": 58228, "mo_scrip": 58228, "lot_size": 1225},
    {"name": "HYUNDAI 25-AUG-2026", "code": 58229, "mo_scrip": 58229, "lot_size": 275},
    {"name": "ICICIBANK 25-AUG-2026", "code": 58232, "mo_scrip": 58232, "lot_size": 700},
    {"name": "ICICIGI 25-AUG-2026", "code": 58233, "mo_scrip": 58233, "lot_size": 325},
    {"name": "ICICIPRULI 25-AUG-2026", "code": 58234, "mo_scrip": 58234, "lot_size": 925},
    {"name": "IDEA 25-AUG-2026", "code": 58235, "mo_scrip": 58235, "lot_size": 71475},
    {"name": "IDFCFIRSTB 25-AUG-2026", "code": 58236, "mo_scrip": 58236, "lot_size": 9275},
    {"name": "IEX 25-AUG-2026", "code": 58237, "mo_scrip": 58237, "lot_size": 4350},
    {"name": "INDHOTEL 25-AUG-2026", "code": 58240, "mo_scrip": 58240, "lot_size": 1000},
    {"name": "INDIANB 25-AUG-2026", "code": 58241, "mo_scrip": 58241, "lot_size": 1000},
    {"name": "INDIGO 25-AUG-2026", "code": 58242, "mo_scrip": 58242, "lot_size": 150},
    {"name": "INDUSINDBK 25-AUG-2026", "code": 58243, "mo_scrip": 58243, "lot_size": 700},
    {"name": "INDUSTOWER 25-AUG-2026", "code": 58244, "mo_scrip": 58244, "lot_size": 1700},
    {"name": "INFY 25-AUG-2026", "code": 58245, "mo_scrip": 58245, "lot_size": 400},
    {"name": "INOXWIND 25-AUG-2026", "code": 58246, "mo_scrip": 58246, "lot_size": 6400},
    {"name": "IOC 25-AUG-2026", "code": 58247, "mo_scrip": 58247, "lot_size": 4875},
    {"name": "IREDA 25-AUG-2026", "code": 58248, "mo_scrip": 58248, "lot_size": 4525},
    {"name": "IRFC 25-AUG-2026", "code": 58249, "mo_scrip": 58249, "lot_size": 5425},
    {"name": "ITC 25-AUG-2026", "code": 58250, "mo_scrip": 58250, "lot_size": 1725},
    {"name": "JINDALSTEL 25-AUG-2026", "code": 58251, "mo_scrip": 58251, "lot_size": 625},
    {"name": "JIOFIN 25-AUG-2026", "code": 58256, "mo_scrip": 58256, "lot_size": 2350},
    {"name": "JSWENERGY 25-AUG-2026", "code": 58257, "mo_scrip": 58257, "lot_size": 1075},
    {"name": "JSWSTEEL 25-AUG-2026", "code": 58258, "mo_scrip": 58258, "lot_size": 675},
    {"name": "JUBLFOOD 25-AUG-2026", "code": 58260, "mo_scrip": 58260, "lot_size": 1250},
    {"name": "KALYANKJIL 25-AUG-2026", "code": 58261, "mo_scrip": 58261, "lot_size": 1350},
    {"name": "KAYNES 25-AUG-2026", "code": 58274, "mo_scrip": 58274, "lot_size": 150},
    {"name": "KEI 25-AUG-2026", "code": 58275, "mo_scrip": 58275, "lot_size": 175},
    {"name": "KFINTECH 25-AUG-2026", "code": 58276, "mo_scrip": 58276, "lot_size": 575},
    {"name": "KOTAKBANK 25-AUG-2026", "code": 58277, "mo_scrip": 58277, "lot_size": 2000},
    {"name": "KPITTECH 25-AUG-2026", "code": 58278, "mo_scrip": 58278, "lot_size": 775},
    {"name": "LAURUSLABS 25-AUG-2026", "code": 58279, "mo_scrip": 58279, "lot_size": 850},
    {"name": "LICHSGFIN 25-AUG-2026", "code": 58289, "mo_scrip": 58289, "lot_size": 1000},
    {"name": "LICI 25-AUG-2026", "code": 58290, "mo_scrip": 58290, "lot_size": 1400},
    {"name": "LODHA 25-AUG-2026", "code": 58291, "mo_scrip": 58291, "lot_size": 625},
    {"name": "LT 25-AUG-2026", "code": 58292, "mo_scrip": 58292, "lot_size": 175},
    {"name": "LTF 25-AUG-2026", "code": 58297, "mo_scrip": 58297, "lot_size": 2250},
    {"name": "LTM 25-AUG-2026", "code": 58298, "mo_scrip": 58298, "lot_size": 150},
    {"name": "LUPIN 25-AUG-2026", "code": 58301, "mo_scrip": 58301, "lot_size": 425},
    {"name": "M&M 25-AUG-2026", "code": 58302, "mo_scrip": 58302, "lot_size": 200},
    {"name": "MANAPPURAM 25-AUG-2026", "code": 58303, "mo_scrip": 58303, "lot_size": 3000},
    {"name": "MANKIND 25-AUG-2026", "code": 58304, "mo_scrip": 58304, "lot_size": 250},
    {"name": "MARICO 25-AUG-2026", "code": 58305, "mo_scrip": 58305, "lot_size": 1200},
    {"name": "MARUTI 25-AUG-2026", "code": 58306, "mo_scrip": 58306, "lot_size": 50},
    {"name": "MAXHEALTH 25-AUG-2026", "code": 58307, "mo_scrip": 58307, "lot_size": 525},
    {"name": "MAZDOCK 25-AUG-2026", "code": 58310, "mo_scrip": 58310, "lot_size": 225},
    {"name": "MCX 25-AUG-2026", "code": 58316, "mo_scrip": 58316, "lot_size": 225},
    {"name": "MFSL 25-AUG-2026", "code": 58317, "mo_scrip": 58317, "lot_size": 400},
    {"name": "MOTHERSON 25-AUG-2026", "code": 58319, "mo_scrip": 58319, "lot_size": 6150},
    {"name": "MOTILALOFS 25-AUG-2026", "code": 58320, "mo_scrip": 58320, "lot_size": 775},
    {"name": "MPHASIS 25-AUG-2026", "code": 58321, "mo_scrip": 58321, "lot_size": 275},
    {"name": "MUTHOOTFIN 25-AUG-2026", "code": 58322, "mo_scrip": 58322, "lot_size": 275},
    {"name": "NAM-INDIA 25-AUG-2026", "code": 58326, "mo_scrip": 58326, "lot_size": 625},
    {"name": "NATIONALUM 25-AUG-2026", "code": 58327, "mo_scrip": 58327, "lot_size": 1875},
    {"name": "NAUKRI 25-AUG-2026", "code": 58328, "mo_scrip": 58328, "lot_size": 550},
    {"name": "NBCC 25-AUG-2026", "code": 58329, "mo_scrip": 58329, "lot_size": 6500},
    {"name": "NESTLEIND 25-AUG-2026", "code": 58330, "mo_scrip": 58330, "lot_size": 500},
    {"name": "NHPC 25-AUG-2026", "code": 58331, "mo_scrip": 58331, "lot_size": 6950},
    {"name": "NMDC 25-AUG-2026", "code": 58332, "mo_scrip": 58332, "lot_size": 6750},
    {"name": "NTPC 25-AUG-2026", "code": 58333, "mo_scrip": 58333, "lot_size": 1500},
    {"name": "NYKAA 25-AUG-2026", "code": 58334, "mo_scrip": 58334, "lot_size": 3125},
    {"name": "OBEROIRLTY 25-AUG-2026", "code": 58335, "mo_scrip": 58335, "lot_size": 350},
    {"name": "OFSS 25-AUG-2026", "code": 58337, "mo_scrip": 58337, "lot_size": 100},
    {"name": "OIL 25-AUG-2026", "code": 58338, "mo_scrip": 58338, "lot_size": 1400},
    {"name": "ONGC 25-AUG-2026", "code": 58339, "mo_scrip": 58339, "lot_size": 2250},
    {"name": "PAGEIND 25-AUG-2026", "code": 58340, "mo_scrip": 58340, "lot_size": 1075},
    {"name": "PATANJALI 25-AUG-2026", "code": 58341, "mo_scrip": 58341, "lot_size": 1075},
    {"name": "PAYTM 25-AUG-2026", "code": 58342, "mo_scrip": 58342, "lot_size": 725},
    {"name": "PERSISTENT 25-AUG-2026", "code": 58343, "mo_scrip": 58343, "lot_size": 125},
    {"name": "PETRONET 25-AUG-2026", "code": 58344, "mo_scrip": 58344, "lot_size": 1900},
    {"name": "PFC 25-AUG-2026", "code": 58345, "mo_scrip": 58345, "lot_size": 1300},
    {"name": "PGEL 25-AUG-2026", "code": 58346, "mo_scrip": 58346, "lot_size": 950},
    {"name": "PHOENIXLTD 25-AUG-2026", "code": 58347, "mo_scrip": 58347, "lot_size": 350},
    {"name": "PIDILITIND 25-AUG-2026", "code": 58348, "mo_scrip": 58348, "lot_size": 500},
    {"name": "PIIND 25-AUG-2026", "code": 58349, "mo_scrip": 58349, "lot_size": 175},
    {"name": "PNB 25-AUG-2026", "code": 58350, "mo_scrip": 58350, "lot_size": 8000},
    {"name": "PNBHOUSING 25-AUG-2026", "code": 58351, "mo_scrip": 58351, "lot_size": 650},
    {"name": "POLICYBZR 25-AUG-2026", "code": 58355, "mo_scrip": 58355, "lot_size": 350},
    {"name": "POLYCAB 25-AUG-2026", "code": 58356, "mo_scrip": 58356, "lot_size": 125},
    {"name": "POWERGRID 25-AUG-2026", "code": 58357, "mo_scrip": 58357, "lot_size": 1900},
    {"name": "POWERINDIA 25-AUG-2026", "code": 58358, "mo_scrip": 58358, "lot_size": 25},
    {"name": "PREMIERENE 25-AUG-2026", "code": 58359, "mo_scrip": 58359, "lot_size": 650},
    {"name": "PRESTIGE 25-AUG-2026", "code": 58360, "mo_scrip": 58360, "lot_size": 450},
    {"name": "RADICO 25-AUG-2026", "code": 58367, "mo_scrip": 58367, "lot_size": 150},
    {"name": "RBLBANK 25-AUG-2026", "code": 58368, "mo_scrip": 58368, "lot_size": 3175},
    {"name": "RECLTD 25-AUG-2026", "code": 58369, "mo_scrip": 58369, "lot_size": 1575},
    {"name": "RELIANCE 25-AUG-2026", "code": 58371, "mo_scrip": 58371, "lot_size": 500},
    {"name": "RVNL 25-AUG-2026", "code": 58374, "mo_scrip": 58374, "lot_size": 1925},
    {"name": "SAIL 25-AUG-2026", "code": 58375, "mo_scrip": 58375, "lot_size": 4700},
    {"name": "SBICARD 25-AUG-2026", "code": 58376, "mo_scrip": 58376, "lot_size": 800},
    {"name": "SBILIFE 25-AUG-2026", "code": 58377, "mo_scrip": 58377, "lot_size": 375},
    {"name": "SBIN 25-AUG-2026", "code": 58382, "mo_scrip": 58382, "lot_size": 750},
    {"name": "SHREECEM 25-AUG-2026", "code": 58383, "mo_scrip": 58383, "lot_size": 25},
    {"name": "SHRIRAMFIN 25-AUG-2026", "code": 58386, "mo_scrip": 58386, "lot_size": 825},
    {"name": "SIEMENS 25-AUG-2026", "code": 58387, "mo_scrip": 58387, "lot_size": 175},
    {"name": "SOLARINDS 25-AUG-2026", "code": 58388, "mo_scrip": 58388, "lot_size": 50},
    {"name": "SONACOMS 25-AUG-2026", "code": 58389, "mo_scrip": 58389, "lot_size": 1225},
    {"name": "SRF 25-AUG-2026", "code": 58390, "mo_scrip": 58390, "lot_size": 200},
    {"name": "SUNPHARMA 25-AUG-2026", "code": 58391, "mo_scrip": 58391, "lot_size": 350},
    {"name": "SUPREMEIND 25-AUG-2026", "code": 58392, "mo_scrip": 58392, "lot_size": 175},
    {"name": "SUZLON 25-AUG-2026", "code": 58393, "mo_scrip": 58393, "lot_size": 12700},
    {"name": "SWIGGY 25-AUG-2026", "code": 58394, "mo_scrip": 58394, "lot_size": 1825},
    {"name": "TATACONSUM 25-AUG-2026", "code": 58395, "mo_scrip": 58395, "lot_size": 550},
    {"name": "TATAELXSI 25-AUG-2026", "code": 58396, "mo_scrip": 58396, "lot_size": 125},
    {"name": "TATAPOWER 25-AUG-2026", "code": 58397, "mo_scrip": 58397, "lot_size": 1450},
    {"name": "TATASTEEL 25-AUG-2026", "code": 58398, "mo_scrip": 58398, "lot_size": 2750},
    {"name": "TCS 25-AUG-2026", "code": 58399, "mo_scrip": 58399, "lot_size": 225},
    {"name": "TECHM 25-AUG-2026", "code": 58400, "mo_scrip": 58400, "lot_size": 600},
    {"name": "TIINDIA 25-AUG-2026", "code": 58401, "mo_scrip": 58401, "lot_size": 200},
    {"name": "TITAN 25-AUG-2026", "code": 58402, "mo_scrip": 58402, "lot_size": 175},
    {"name": "TMPV 25-AUG-2026", "code": 58403, "mo_scrip": 58403, "lot_size": 1600},
    {"name": "TORNTPHARM 25-AUG-2026", "code": 58404, "mo_scrip": 58404, "lot_size": 125},
    {"name": "TRENT 25-AUG-2026", "code": 58405, "mo_scrip": 58405, "lot_size": 225},
    {"name": "TVSMOTOR 25-AUG-2026", "code": 58406, "mo_scrip": 58406, "lot_size": 175},
    {"name": "ULTRACEMCO 25-AUG-2026", "code": 58407, "mo_scrip": 58407, "lot_size": 50},
    {"name": "UNIONBANK 25-AUG-2026", "code": 58408, "mo_scrip": 58408, "lot_size": 4425},
    {"name": "UNITDSPR 25-AUG-2026", "code": 58409, "mo_scrip": 58409, "lot_size": 400},
    {"name": "UNOMINDA 25-AUG-2026", "code": 58412, "mo_scrip": 58412, "lot_size": 550},
    {"name": "UPL 25-AUG-2026", "code": 58413, "mo_scrip": 58413, "lot_size": 1355},
    {"name": "VBL 25-AUG-2026", "code": 58414, "mo_scrip": 58414, "lot_size": 1275},
    {"name": "VEDL 25-AUG-2026", "code": 58415, "mo_scrip": 58415, "lot_size": 1150},
    {"name": "VMM 25-AUG-2026", "code": 58416, "mo_scrip": 58416, "lot_size": 4850},
    {"name": "VOLTAS 25-AUG-2026", "code": 58417, "mo_scrip": 58417, "lot_size": 375},
    {"name": "WAAREEENER 25-AUG-2026", "code": 58418, "mo_scrip": 58418, "lot_size": 175},
    {"name": "WIPRO 25-AUG-2026", "code": 58419, "mo_scrip": 58419, "lot_size": 3000},
    {"name": "YESBANK 25-AUG-2026", "code": 58420, "mo_scrip": 58420, "lot_size": 31100},
    {"name": "ZYDUSLIFE 25-AUG-2026", "code": 58421, "mo_scrip": 58421, "lot_size": 900},
]

# Symbol names to highlight (bright yellow row) in the Excel sheet,
# regardless of rank/sort position. Must match SYMBOLS[i]["name"] exactly.
HIGHLIGHT_SYMBOLS = [
    "TVSMOTOR 25-AUG-2026","BAJAJ-AUTO 25-AUG-2026"
]

# ── GM Global ────────────────────────────────────────────────────────────────
# One account, shared by every shard. Unlike the broker APIs there is no
# per-account rate limit to spread out: GM Global's price ticks come off an
# open Socket.IO feed (giantdata.org:3003) that isn't tied to the PHP login
# session at all, so a second account would buy nothing. The login is still
# performed — it validates the account and is what fetch_gm_lots.py uses.
GM_GLOBAL_CONFIG = {
    "user_id":  "287174",
    "password": "zxcvbnm1234",
    "base_url": "https://www.gmglobal.org",
}

# Expiry code appended to the script name to form a GM Global instrument
# identifier: "RELIANCE" + "-" + "I" → "RELIANCE-I". I is the near month,
# II the next one out. The SYMBOLS list above is near-month, so "I" is
# correct; bump this if you ever point SYMBOLS at a further expiry.
GM_EXPIRY_CODE = "I"

# ── Broker accounts, one entry per shard ─────────────────────────────────────
# Index 0 = shard 1's account, index 1 = shard 2's account, and so on.
# The SHARD SPLIT block below picks one out of this list and exposes it as
# MOTILAL_CONFIG, which is all the feed ever sees.
MOTILAL_ACCOUNTS = [
    {   # account A — shard 1
        "market_api_key": "Lv5ALt875Fs4PF7z",
        "api_secret_key": "8485fb96-b8bc-4612-8d68-d57c8c2d2106",
        "client_code":    "VD208",
        "password":       "Ipo@12",
        "two_fa":         "AOYPV8973K",
        "totp_secret":    "5L3X7OCMNXH2YTRFQGOK74L2MZLTAUC7",
        "base_url":       "https://openapi.motilaloswal.com",
    },
    {   # account B — shard 2
        "market_api_key": "l1Cutp1IEyUVlUuC",
        "api_secret_key": "58dc61a7-f5fe-4a00-85c0-c693c666543f",
        "client_code":    "VD210",
        "password":       "Ipo#1234",
        "two_fa":         "AQKPH7787D",
        "totp_secret":    "ZKMW3EMKDKKYCLFYF5RH3RIAAW3PEKLP",
        "base_url":       "https://openapi.motilaloswal.com",
    },
]

EXCEL_WORKBOOK_NAME = "Karmit.xlsx"
EXCEL_SHEET_NAME    = "Karmit"

OUTPUT_DIR = "output"
SAVE_EVERY = 60


# ══════════════════════════════════════════════════════════════════════════
#  SHARD SPLIT — run the 200+ symbols as 2 independent processes
# ══════════════════════════════════════════════════════════════════════════
# Why: one Motilal account polling 200+ scrips is the bottleneck. Its WS
# broadcast cap (see the getbroadcastmaxlimit check in motilal_feed.py)
# means symbols past the limit never get live ticks and fall back to REST,
# and one REST cycle has to cover all 200 before any symbol refreshes
# again. Splitting across two accounts halves both: ~100 scrips per
# account fits under the WS cap, and each REST cycle is half the work.
#
# Nothing else in the codebase needs to change. gm_feed.py and
# motilal_feed.py both do `from config import SYMBOLS` at import time, so
# rebinding SYMBOLS here is enough — each process only ever knows about
# its own half.
#
# Only Motilal is split across accounts. GM Global uses the one
# GM_GLOBAL_CONFIG in every shard — its feed has no per-account cap to
# work around (see the note on GM_GLOBAL_CONFIG above).
#
# Usage (PowerShell):
#     $env:SHARD=1; py main.py     → symbols 1-100,   MO account A, :8000
#     $env:SHARD=2; py main.py     → symbols 101-200, MO account B, :8001
# Or just double-click run_shard1.bat / run_shard2.bat.
#
# SHARD unset (or 0) keeps the original single-process behaviour: all
# symbols, MO account A, port 8000.

SHARD_COUNT = 2          # how many processes to split across
SHARD = int(os.environ.get("SHARD", "0") or "0")

if SHARD:
    if not 1 <= SHARD <= SHARD_COUNT:
        raise ValueError(
            f"SHARD={SHARD} is out of range — must be 1..{SHARD_COUNT} "
            f"(or unset for the original all-symbols single-process mode)."
        )

    _idx = SHARD - 1

    # Contiguous, even split — the last shard absorbs any remainder, so no
    # symbol is ever dropped when len(SYMBOLS) doesn't divide evenly.
    _per_shard = -(-len(SYMBOLS) // SHARD_COUNT)   # ceiling division
    _start     = _idx * _per_shard
    _end       = len(SYMBOLS) if SHARD == SHARD_COUNT else _start + _per_shard
    SYMBOLS    = SYMBOLS[_start:_end]

    MOTILAL_CONFIG = MOTILAL_ACCOUNTS[_idx]

    # Fail loudly at startup rather than letting a placeholder reach the
    # broker and come back as a confusing auth error mid-run.
    _missing = [k for k, v in MOTILAL_CONFIG.items() if v == "FILL_IN"]
    if _missing:
        raise ValueError(
            f"SHARD={SHARD} uses MOTILAL_ACCOUNTS[{_idx}], but these fields "
            f"are still placeholders in config.py: {', '.join(_missing)}"
        )

    # Each shard gets its own ports so both can run side by side.
    WEB_HTTP_PORT = WEB_HTTP_PORT_BASE + _idx
    WEB_WS_PORT   = WEB_WS_PORT_BASE   + _idx

    # Two processes must never drive the same workbook — they'd overwrite
    # each other's rows every tick. (Only matters if ENABLE_EXCEL is on.)
    EXCEL_WORKBOOK_NAME = f"Karmit_shard{SHARD}.xlsx"

    SHARD_LABEL = f"Shard {SHARD}/{SHARD_COUNT} · {len(SYMBOLS)} symbols"
else:
    MOTILAL_CONFIG = MOTILAL_ACCOUNTS[0]
    WEB_HTTP_PORT  = WEB_HTTP_PORT_BASE
    WEB_WS_PORT    = WEB_WS_PORT_BASE
    SHARD_LABEL    = ""