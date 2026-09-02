@echo off
echo ===================================================
echo   STACONT Bridge - Tek Tikla .EXE Uretici
echo ===================================================
echo.

pip install pyinstaller pandas comtypes

echo.
echo [1/2] STACONT-Bridge.exe derleniyor...
pyinstaller --onefile --name "STACONT-Bridge" bridge_agent.py

echo.
echo ===================================================
echo [2/2] Derleme Tamamlandi!
echo Uretilen dosya: dist\STACONT-Bridge.exe
echo ===================================================
pause
