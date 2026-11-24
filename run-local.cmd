@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv
  if errorlevel 1 exit /b 1
)
set "BP_PY=.venv\Scripts\python.exe"
"%BP_PY%" -m pip install -r requirements.txt || exit /b 1
if not exist ".env" (
  "%BP_PY%" -c "import secrets; from pathlib import Path; Path('.env').write_text('FLASK_SECRET_KEY='+secrets.token_hex(32)+'\nDATABASE_URL=sqlite:///budget_companion_dev.db\n', encoding='utf-8')" || exit /b 1
)
set "DATABASE_URL=sqlite:///budget_companion_dev.db"
"%BP_PY%" -m flask --app app db upgrade || exit /b 1
"%BP_PY%" -m flask --app app complete-schedules || exit /b 1
"%BP_PY%" -m flask --app app run
