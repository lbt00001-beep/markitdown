@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
set "APP_TITLE=MarkItDown Dashboard"
set "HOST=127.0.0.1"
set "PORT=8000"
set "URL=http://%HOST%:%PORT%"
set "RUN_DIR=%ROOT%\data\run"
set "SERVER_PID_FILE=%RUN_DIR%\server.pid"
set "SERVER_CHILD_PID_FILE=%RUN_DIR%\server-child.pid"
set "BROWSER_PID_FILE=%RUN_DIR%\browser.pid"
set "BROWSER_PROFILE=%RUN_DIR%\browser-profile"
set "LOG_FILE=%RUN_DIR%\server.log"
set "SERVER_CMD=%RUN_DIR%\server.cmd"
set "SERVER_WINDOW_TITLE=%APP_TITLE% - servidor"

cd /d "%ROOT%"

if not exist "%RUN_DIR%" mkdir "%RUN_DIR%" >nul 2>nul

call :cleanup_previous

where python >nul 2>nul
if errorlevel 1 (
    echo No se encontro Python en el PATH.
    echo Instala Python 3.10 o superior y vuelve a ejecutar este archivo.
    pause
    exit /b 1
)

python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if errorlevel 1 (
    echo Se necesita Python 3.10 o superior.
    pause
    exit /b 1
)

python -c "import fastapi, uvicorn, multipart, openai, imageio_ffmpeg, mammoth, olefile, openpyxl, pandas, pdfminer, pdfplumber, pydub, pptx, speech_recognition, xlrd, youtube_transcript_api; import azure.ai.documentintelligence, azure.ai.contentunderstanding, azure.identity; from markitdown.converters import ContentUnderstandingFileType" >nul 2>nul
if errorlevel 1 (
    echo Instalando dependencias necesarias...
    python -m pip install -r "%ROOT%\requirements.txt"
    if errorlevel 1 (
        echo.
        echo No se pudieron instalar las dependencias.
        pause
        exit /b 1
    )
)

echo Arrancando %APP_TITLE% en %URL% ...

(
    echo @echo off
    echo title %SERVER_WINDOW_TITLE%
    echo cd /d "%ROOT%"
    echo python -m uvicorn app.main:app --host %HOST% --port %PORT% --log-level info ^> "%LOG_FILE%" 2^>^&1
    echo echo.
    echo echo Servidor detenido. Revisa el log si necesitas detalles:
    echo echo "%LOG_FILE%"
    echo pause
) > "%SERVER_CMD%"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$root='%ROOT%'; $serverCmd='%SERVER_CMD%'; $pidFile='%SERVER_PID_FILE%';" ^
  "$p = Start-Process -FilePath $env:ComSpec -ArgumentList @('/k', ('""' + $serverCmd + '""')) -WorkingDirectory $root -PassThru;" ^
  "Set-Content -LiteralPath $pidFile -Value $p.Id -Encoding ASCII"

if errorlevel 1 (
    echo No se pudo iniciar la ventana del servidor.
    pause
    exit /b 1
)

echo Esperando a que el servidor responda...
set "READY="
for /L %%I in (1,1,30) do (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r = Invoke-WebRequest -UseBasicParsing '%URL%/api/health' -TimeoutSec 1; if ($r.StatusCode -ge 200) { exit 0 } } catch { exit 1 }" >nul 2>nul
    if not errorlevel 1 (
        set "READY=1"
        powershell -NoProfile -ExecutionPolicy Bypass -Command ^
          "$p = Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty OwningProcess;" ^
          "if ($p) { Set-Content -LiteralPath '%SERVER_CHILD_PID_FILE%' -Value $p -Encoding ASCII }" >nul 2>nul
        goto :open_browser
    )
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Sleep -Seconds 1" >nul 2>nul
)

echo.
echo El servidor no respondio a tiempo.
echo Revisa el log: "%LOG_FILE%"
call :cleanup_previous
pause
exit /b 1

:open_browser
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$candidates = @('%ProgramFiles%\Google\Chrome\Application\chrome.exe', '%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe', '%ProgramFiles%\Microsoft\Edge\Application\msedge.exe', '%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe');" ^
  "$browser = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1;" ^
  "if ($browser) { $args = @('--app=%URL%', ('--user-data-dir=' + [char]34 + '%BROWSER_PROFILE%' + [char]34), '--no-first-run'); $p = Start-Process -FilePath $browser -ArgumentList $args -PassThru } else { $p = Start-Process '%URL%' -PassThru };" ^
  "if ($p -and $p.Id) { Set-Content -LiteralPath '%BROWSER_PID_FILE%' -Value $p.Id -Encoding ASCII }"

echo.
echo %APP_TITLE% esta disponible en:
echo %URL%
echo.
echo Vuelve a ejecutar EJECUTAR.bat para cerrar la ejecucion anterior y arrancar una nueva.
echo Esta ventana se puede cerrar.
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Sleep -Seconds 5" >nul 2>nul
exit /b 0

:cleanup_previous
set "CLEANED="

if exist "%BROWSER_PID_FILE%" (
    set /p BROWSER_PID=<"%BROWSER_PID_FILE%"
    if defined BROWSER_PID (
        taskkill /PID !BROWSER_PID! /T /F >nul 2>nul
        set "CLEANED=1"
    )
    del "%BROWSER_PID_FILE%" >nul 2>nul
)

if exist "%SERVER_PID_FILE%" (
    set /p SERVER_PID=<"%SERVER_PID_FILE%"
    if defined SERVER_PID (
        taskkill /PID !SERVER_PID! /T /F >nul 2>nul
        set "CLEANED=1"
    )
    del "%SERVER_PID_FILE%" >nul 2>nul
)

if exist "%SERVER_CHILD_PID_FILE%" (
    set /p SERVER_CHILD_PID=<"%SERVER_CHILD_PID_FILE%"
    if defined SERVER_CHILD_PID (
        taskkill /PID !SERVER_CHILD_PID! /T /F >nul 2>nul
        set "CLEANED=1"
    )
    del "%SERVER_CHILD_PID_FILE%" >nul 2>nul
)

if exist "%SERVER_CMD%" del "%SERVER_CMD%" >nul 2>nul

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$title='%SERVER_WINDOW_TITLE%';" ^
  "Get-Process cmd -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -eq $title } | Stop-Process -Force -ErrorAction SilentlyContinue" >nul 2>nul

if defined CLEANED (
    echo Ejecucion anterior cerrada.
)

exit /b 0
