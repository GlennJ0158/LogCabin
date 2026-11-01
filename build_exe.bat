@echo off
REM Build QuiltBack.exe (single file, no console window) with PyInstaller.
REM Run from the repository folder on Windows with Python installed.

python -m pip install --upgrade pyinstaller || goto :error

python -m PyInstaller --onefile --windowed --name QuiltBack app.py || goto :error

echo.
echo Build complete: dist\QuiltBack.exe
goto :eof

:error
echo.
echo Build failed.
exit /b 1
