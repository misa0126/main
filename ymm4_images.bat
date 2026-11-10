@echo off
rem YMM4で保存したプロジェクト(.ymmp)をこのファイルにドラッグ&ドロップすると、
rem 区切り表どおりに画像を並べた「(元の名前)_画像入り.ymmp」を作る
cd /d "%~dp0"
if "%~1"=="" (
  echo YMM4で保存したプロジェクト^(.ymmp^)を、このファイルの上にドラッグ^&ドロップしてください。
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  echo 準備ができていません。先に start_app.bat を一度ダブルクリックして、アプリが開いたら閉じてください。
  echo そのあと、もう一度プロジェクトをこのファイルにドラッグ^&ドロップしてください。
  pause
  exit /b 1
)
set PYTHONUTF8=1
".venv\Scripts\python.exe" -m material_collector.ymmp_images "%~1" --ask
echo.
pause
