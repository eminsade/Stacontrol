@echo off
rem ===========================================================
rem  Stacontrol - GELISTIRME ortaminda calistirir.
rem  Iki surec baslatir: kopru API'si (8500) ve Streamlit (8501).
rem  Uretim icin deploy/ klasorundeki systemd birimlerini kullanin.
rem ===========================================================
cd /d "%~dp0"

set STACONTROL_DEV=1
set BRIDGE_DEV_MODE=1
set BRIDGE_INTERNAL_KEY=gelistirme-anahtari-degistirmeyin-uretimde
set COOKIES_PASSWORD=gelistirme-cerez-anahtari
set BRIDGE_URL=http://127.0.0.1:8500
set BRIDGE_DB=%~dp0bridge_state.db
set STACONTROL_DB=%~dp0hesaplama_sonuc.db

echo Kopru sunucusu baslatiliyor (port 8500)...
start "Stacontrol Kopru" cmd /k python -m uvicorn etabs_bridge.server.app:app --host 127.0.0.1 --port 8500

echo Streamlit baslatiliyor (port 8501)...
timeout /t 2 >nul
streamlit run anasayfa.py

pause
