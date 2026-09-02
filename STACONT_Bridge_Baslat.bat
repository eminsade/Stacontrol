@echo off
title STACONT Bridge Agent
color 0A
echo ==========================================================
echo           STACONT YEREL KOPRU (BRIDGE) BASLATILIYOR
echo ==========================================================
echo.
echo ETABS ile Web Sitesi arasindaki baglanti kuruluyor...
echo.

python -c "import pycloudflared" 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [BILGI] Bulut erisimi icin pycloudflared yukleniyor...
    pip install pycloudflared
)

python bridge_agent.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [HATA] Python veya comtypes calistirilamadi!
    echo Lutfen 'pip install comtypes pandas pycloudflared' calistirin.
    echo.
    pause
)
