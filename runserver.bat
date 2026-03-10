@echo off
cd /d "%~dp0project"
"%~dp0venv\Scripts\python.exe" manage.py runserver
pause
