@echo off
title STACONT Bridge Agent
color 0A
echo ==========================================================
echo           STACONT YEREL KOPRU (BRIDGE) BASLATILIYOR
echo ==========================================================
echo.
echo ETABS ile Web Sitesi arasindaki baglanti kuruluyor...
echo Port: 8765
echo.
echo IPUCU: Web sitesinde analiz yaparken bu pencereyi acik tutun.
echo ==========================================================
echo.

python bridge_agent.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [HATA] Python veya comtypes bulunamadi!
    echo Lutfen 'pip install comtypes pandas' komutunu calistirin.
    echo.
    pause
)
