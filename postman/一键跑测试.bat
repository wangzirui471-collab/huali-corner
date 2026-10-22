@echo off
REM ============================================================
REM  Huali-Corner - one-click API tests (Postman + Newman)
REM
REM  Double-click this file. It starts a throwaway backend + AI
REM  service, runs all three Postman collections, writes a report,
REM  then shuts both services down again.
REM
REM  This .bat is deliberately ASCII-only: cmd.exe mangles
REM  multi-byte characters in batch files (especially next to the
REM  "^" line-continuation), so all the real logic lives in
REM  run_all.py next to this file.
REM ============================================================
chcp 65001 >nul
cd /d "%~dp0"

REM Prefer the project venv: it has Pillow, which the backend needs.
if exist "%~dp0..\.venv-trial\Scripts\python.exe" (
  "%~dp0..\.venv-trial\Scripts\python.exe" run_all.py %*
) else (
  python run_all.py %*
)

echo.
pause
