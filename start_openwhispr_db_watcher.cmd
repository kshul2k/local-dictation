@echo off
cd /d "%~dp0"
set "PYTHONPYCACHEPREFIX=%~dp0cache\pycache"

if "%~1"=="--no-paste" (
  start "" "%LocalAppData%\Programs\Python\Python312-arm64\pythonw.exe" "%~dp0src\run_openwhispr_db_watcher.py" --no-paste --replace-raw-paste
) else (
  start "" "%LocalAppData%\Programs\Python\Python312-arm64\pythonw.exe" "%~dp0src\run_openwhispr_db_watcher.py" --replace-raw-paste
)
echo OpenWhispr DB cleanup watcher launch requested.
