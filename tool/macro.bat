@echo off
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
where py >nul 2>nul
if not errorlevel 1 (
    py -3 "%~dp0macro.py" %*
    goto :finished
)
where python >nul 2>nul
if not errorlevel 1 (
    python "%~dp0macro.py" %*
    goto :finished
)
echo ERREUR : Python est introuvable. Installez Python 3 avec requests et Pillow.
:finished
pause
