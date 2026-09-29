@echo off
rem Starts the API (port 8000) and the web app (port 3000) in two windows, then opens the browser.
cd /d "%~dp0"

where uv >nul 2>nul || (echo uv is not installed: https://docs.astral.sh/uv/ & pause & exit /b 1)
where pnpm >nul 2>nul || (echo pnpm is not installed: run "npm install -g pnpm" & pause & exit /b 1)

start "AutoEng API" cmd /k "cd /d "%~dp0backend" && uv sync --extra gpu && uv run python -m uvicorn autoeng.api.app:app --port 8000"
start "AutoEng Web" cmd /k "cd /d "%~dp0frontend" && pnpm install && pnpm dev"

echo Waiting for the servers to start...
timeout /t 15 /nobreak >nul
start "" http://localhost:3000
