@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PY=C:\Users\PC\Anaconda3\envs\python39\python.exe

if not exist "%PY%" (
    echo [start_docs] 未找到 Python: %PY%
    echo [start_docs] 请检查 Anaconda3\envs\python39 环境是否存在。
    pause
    exit /b 1
)

echo [start_docs] 检查文档依赖...
"%PY%" -m pip install -q -r utils\requirements-docs.txt
if errorlevel 1 (
    echo [start_docs] 依赖安装失败，退出。
    pause
    exit /b 1
)

echo [start_docs] 启动浏览器...
start "" http://127.0.0.1:8000

echo [start_docs] 启动 MkDocs 热重载服务（Ctrl+C 退出）...
"%PY%" -m mkdocs serve -a 127.0.0.1:8000
