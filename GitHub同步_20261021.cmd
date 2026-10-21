@echo off
cd /d "%~dp0"
python github_sync_20261021.py sync
set "SYNC_EXIT=%ERRORLEVEL%"
pause
exit /b %SYNC_EXIT%
