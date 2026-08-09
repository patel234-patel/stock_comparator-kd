@echo off
REM Shard 2 — second half of config.SYMBOLS, broker account B, http://127.0.0.1:8001
cd /d "%~dp0"
set SHARD=2
py main.py
pause
