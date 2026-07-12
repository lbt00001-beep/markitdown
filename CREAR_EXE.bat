@echo off
setlocal EnableExtensions

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
cd /d "%ROOT%"

where python >nul 2>nul
if errorlevel 1 (
    echo No se encontro Python.
    pause
    exit /b 1
)

echo Instalando herramientas de construccion...
python -m pip install -r "%ROOT%\requirements-build.txt"
if errorlevel 1 goto :error

echo.
echo Creando la aplicacion para Windows...
python -m PyInstaller --noconfirm --clean "%ROOT%\MarkItDownDashboard.spec"
if errorlevel 1 goto :error

copy /Y "%ROOT%\LEEME-WINDOWS.txt" "%ROOT%\dist\MarkItDownDashboard\LEEME.txt" >nul

echo.
echo Comprimiendo la carpeta para compartirla...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$destination='%ROOT%\dist\MarkItDownDashboard-Windows.zip';" ^
  "if (Test-Path -LiteralPath $destination) { Remove-Item -LiteralPath $destination -Force };" ^
  "Compress-Archive -Path '%ROOT%\dist\MarkItDownDashboard\*' -DestinationPath $destination -CompressionLevel Optimal"
if errorlevel 1 goto :error

echo.
echo Construccion terminada:
echo %ROOT%\dist\MarkItDownDashboard\MarkItDownDashboard.exe
echo %ROOT%\dist\MarkItDownDashboard-Windows.zip
exit /b 0

:error
echo.
echo No se pudo crear la aplicacion. Revisa los mensajes anteriores.
pause
exit /b 1
