@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   集保籌碼瀏覽器 啟動中...
echo   稍候會自動打開瀏覽器;關閉本視窗即停止。
echo ============================================
where py >nul 2>nul && (py chips_server.py) || (python chips_server.py)
pause
