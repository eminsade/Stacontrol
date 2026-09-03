@echo off
rem ===========================================================
rem  STACONTROL - TEK TIKLA BASLAT (kendi bilgisayarinda)
rem
rem  Bu dosyaya cift tiklayin. Uc sey birden baslar:
rem    1. Kopru servisi   (arka planda)
rem    2. ETABS ajani     (kod gosteren siyah pencere)
rem    3. Web arayuzu     (tarayicida acilir)
rem
rem  ETABS'in acik ve analizin calistirilmis olmasi yeterlidir.
rem  Hicbir sifre veya ayar girmeniz gerekmez.
rem ===========================================================
chcp 65001 >nul 2>&1
title Stacontrol
cd /d "%~dp0"

rem --- Yerel calisma icin gereken degerler (uretim sunucusunda
rem     bunlar kurulum betigi tarafindan otomatik uretilir) ---
set STACONTROL_DEV=1
set BRIDGE_DEV_MODE=1
set BRIDGE_INTERNAL_KEY=yerel-calisma-anahtari
set BRIDGE_URL=http://127.0.0.1:8500
set STACONTROL_BRIDGE_URL=http://127.0.0.1:8500
set BRIDGE_DB=%~dp0bridge_state.db
set STACONTROL_DB=%~dp0hesaplama_sonuc.db
set PYTHONPATH=%~dp0etabs_bridge

echo.
echo  [1/3] Kopru servisi baslatiliyor...
start "Stacontrol Kopru" /min cmd /c "python -m uvicorn etabs_bridge.server.app:app --host 127.0.0.1 --port 8500"

rem Koprunun ayaga kalkmasini bekle
timeout /t 4 /nobreak >nul

echo  [2/3] ETABS ajani baslatiliyor...
echo        (acilan pencerede 6 haneli kod gorunecek - KAPATMAYIN)
start "Stacontrol ETABS Ajani" cmd /k "python ""%~dp0etabs_bridge\agent\agent.py"""

timeout /t 2 /nobreak >nul

echo  [3/3] Web arayuzu aciliyor...
echo.
echo  ---------------------------------------------------------
echo   Tarayici acilinca:
echo     1. Kayit olun (kullanici adi + en az 8 karakter sifre)
echo     2. "ETABS Baglantisi" sayfasina gidin
echo     3. Ajan penceresindeki 6 haneli kodu girin
echo     4. Hesap sayfalarini kullanin
echo  ---------------------------------------------------------
echo.

streamlit run anasayfa.py

echo.
echo  Web arayuzu kapandi. Diger pencereleri de kapatabilirsiniz.
pause
