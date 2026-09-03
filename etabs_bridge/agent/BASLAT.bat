@echo off
rem ===========================================================
rem  Stacontrol ETABS Ajani - baslatici
rem  Bu dosyaya cift tiklayin. Kurulum gerekmez.
rem ===========================================================
chcp 65001 >nul 2>&1
title Stacontrol ETABS Ajani
cd /d "%~dp0"

if exist "python\python.exe" (
    "python\python.exe" "agent.py"
    goto :son
)

rem Gomulu Python yoksa sistemdeki Python denenir.
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 "agent.py"
    goto :son
)

where python >nul 2>nul
if %errorlevel%==0 (
    python "agent.py"
    goto :son
)

echo.
echo  [HATA] Python bulunamadi.
echo.
echo  Tam paketi (icinde Python gomulu olan) indirdiginizden emin olun:
echo  bu klasorde "python" adinda bir alt klasor olmali.
echo.

:son
echo.
pause
