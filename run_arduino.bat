@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
set PY=python
where python >nul 2>nul || set PY=py
echo Installing the needed libraries (first time only, needs internet)...
%PY% -m pip install --quiet pyserial requests numpy scipy
echo.
%PY% serial_bridge.py
echo.
echo ---- The program has stopped. Read the messages above. ----
pause
