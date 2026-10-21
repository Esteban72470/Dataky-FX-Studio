@echo off
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
title Dataky FX Studio
where py >nul 2>nul
if not errorlevel 1 (
    py -3 "%~dp0tool\fx_launch.py" %*
    goto :finished
)
where python >nul 2>nul
if not errorlevel 1 (
    python "%~dp0tool\fx_launch.py" %*
    goto :finished
)
echo Python 3 est introuvable. Installez Python 3 pour ouvrir Dataky FX Studio.
:finished
if errorlevel 1 pause
