@echo off
rem Ajani YEREL kopruye baglayarak calistirir (gelistirme testi icin).
cd /d "%~dp0etabs_bridge\agent"
set STACONTROL_BRIDGE_URL=http://127.0.0.1:8500
set PYTHONPATH=%~dp0etabs_bridge
python agent.py
pause
