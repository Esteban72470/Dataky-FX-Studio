@echo off
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
echo Reconstruction du catalogue depuis les captures source existantes.
echo Les apercus valides sont reutilises; les apercus manquants sont retentes.
where py >nul 2>nul
if not errorlevel 1 (
    set "ZV_PYTHON=py -3"
    py -3 "%~dp0tool\catalog.py" %*
    goto :finished
)
where python >nul 2>nul
if not errorlevel 1 (
    set "ZV_PYTHON=python"
    python "%~dp0tool\catalog.py" %*
    goto :finished
)
echo ERREUR : Python est introuvable. Installez Python 3 avec requests et Pillow.
pause
exit /b 1

:finished
if errorlevel 1 (
    echo.
    echo La mise a jour a echoue. Consultez le message ci-dessus.
    echo Les captures source et les exports deja enregistres sont conserves.
    pause
    exit /b 1
)
if exist "%~dp0beams\source\All.json" if exist "%~dp0meshes\source\All.json" (
    %ZV_PYTHON% "%~dp0tool\asset_catalog.py" --collections beams meshes --workers 12
    if errorlevel 1 (
        echo La mise a jour Beams ou Meshes a echoue. Consultez le message ci-dessus.
        pause
        exit /b 1
    )
)
if exist "%~dp0catalogue.html" start "" "%~dp0catalogue.html"
exit /b 0
