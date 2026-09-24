@echo off
cd /d "%~dp0"
echo FAB-1 数字孪生：浏览器将打开 http://localhost:8765/index_local.html ，关闭此窗口即停止。
start "" http://localhost:8765/index_local.html
python -m http.server 8765 || py -m http.server 8765
pause
