@echo off
rem ダブルクリックで「ゆっくり素材集め」アプリを起動する(初回は準備に数分かかります)
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto install

echo 初回の準備をしています。数分かかります。この画面は閉じずにお待ちください...
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && python -c "import sys" >nul 2>nul && set "PY=python"
if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PY="%LOCALAPPDATA%\Programs\Python\Python312\python.exe""
if not defined PY (
  echo Python をインストールしています...
  winget install --id Python.Python.3.12 -e --scope user --silent --accept-package-agreements --accept-source-agreements
  if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PY="%LOCALAPPDATA%\Programs\Python\Python312\python.exe""
)
if not defined PY (
  echo Python を自動でインストールできませんでした。
  echo https://www.python.org からインストールしてから、もう一度このファイルをダブルクリックしてください。
  pause
  exit /b 1
)
%PY% -m venv .venv
if not exist ".venv\Scripts\python.exe" (
  echo 準備に失敗しました。この画面を Claude に見せてください。
  pause
  exit /b 1
)

:install
".venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
  echo 必要なライブラリのインストールに失敗しました。インターネット接続を確認してください。
  pause
  exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" app.py
