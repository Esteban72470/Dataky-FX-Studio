@echo off
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
where py >nul 2>nul
if not errorlevel 1 (
    py -3 "%~dp0tool\fx_mcp.py" --install-claude-desktop
    goto :finished
)
where python >nul 2>nul
if not errorlevel 1 (
    python "%~dp0tool\fx_mcp.py" --install-claude-desktop
    goto :finished
)
echo Python 3 est introuvable.
:finished
pause
