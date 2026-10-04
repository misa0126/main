@echo off
rem ダブルクリックで「ゆっくり素材集め」アプリを起動する(初回は準備に数分かかります)
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo 初回の準備をしています。数分かかります...
  py -3 -m venv .venv 2>nul || python -m venv .venv
  if not exist ".venv\Scripts\python.exe" (
    echo Python が見つかりません。https://www.python.org からインストールしてください。
    pause
    exit /b 1
  )
)
".venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
  echo 必要なライブラリのインストールに失敗しました。インターネット接続を確認してください。
  pause
  exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" app.py
