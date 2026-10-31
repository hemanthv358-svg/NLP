@echo off
setlocal
set "PROJECT_ROOT=%~dp0.."
set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"

if exist "%PYTHON_EXE%" (
  "%PYTHON_EXE%" "%PROJECT_ROOT%\bot.py"
) else (
  python "%PROJECT_ROOT%\bot.py"
)
