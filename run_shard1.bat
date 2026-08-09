@echo off
REM Shard 1 — first half of config.SYMBOLS, broker account A, http://127.0.0.1:8000
cd /d "%~dp0"
set SHARD=1
py main.py
pause
