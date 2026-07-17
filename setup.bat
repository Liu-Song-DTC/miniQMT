@echo off
chcp 65001 >nul
title miniQMT 环境安装脚本

echo ============================================================
echo   miniQMT 高抛低吸策略 - 一键环境配置
echo ============================================================
echo.

:: ========== 1. 检查 Python ==========
echo [1/5] 检查 Python 环境...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python，请先安装 Python 3.9
    echo   下载地址: https://www.python.org/downloads/
    echo   安装时勾选 "Add Python to PATH"
    pause
    exit /b 1
)
python --version
echo   Python OK
echo.

:: ========== 2. 安装核心依赖 ==========
echo [2/5] 安装核心依赖包...
pip install pandas==1.5.3 numpy==1.24.4 Flask==2.3.3 Flask-CORS==4.0.0 redis mootdx marshmallow requests colorama -q
if %errorlevel% neq 0 (
    echo [警告] 部分依赖安装失败，尝试宽松版本...
    pip install pandas numpy Flask Flask-CORS redis mootdx marshmallow requests colorama
)
echo   核心依赖 OK
echo.

:: ========== 3. 安装 TA-Lib（可选） ==========
echo [3/5] 安装 TA-Lib 技术分析库...
set PYTHON_VER=
for /f "tokens=2" %%i in ('python -c "import sys; print(f'cp{sys.version_info.major}{sys.version_info.minor}')" 2^>nul') do set PYTHON_VER=%%i

if exist "utils\TA_Lib-0.4.26-%PYTHON_VER%-win_amd64.whl" (
    pip install "utils\TA_Lib-0.4.26-%PYTHON_VER%-win_amd64.whl" -q
    echo   TA-Lib 已安装
) else (
    echo   [跳过] 未找到匹配的 whl 文件 (utils\TA_Lib-0.4.26-%PYTHON_VER%-win_amd64.whl)
    echo   不影响核心功能，可后续手动安装
)
echo.

:: ========== 4. 安装 xtquant（QMT API） ==========
echo [4/5] 安装 xtquant (QMT 交易接口)...
echo   正在搜索 QMT 安装目录...

set XTQUANT_FOUND=0

:: 常见 QMT 安装路径
for %%d in (
    "C:\国金证券QMT实盘"
    "C:\国金证券"
    "D:\国金证券QMT实盘"
    "D:\国金证券"
    "C:\Program Files\国金证券"
    "C:\QMT"
) do (
    if exist %%d\bin.x64\Lib\site-packages\xtquant\ (
        echo   找到 xtquant: %%d\bin.x64\Lib\site-packages\xtquant\
        pip install "%%d\bin.x64\Lib\site-packages\xtquant\" -q
        set XTQUANT_FOUND=1
        goto :xtquant_done
    )
)

:: 搜索 C 盘
echo   正在搜索 C 盘 QMT 安装目录（可能需要几秒）...
for /f "tokens=*" %%f in ('dir /s /b C:\userdata_mini 2^>nul') do (
    set QMT_DIR=%%~dpf
    set QMT_DIR=!QMT_DIR:~0,-1!
    if exist "!QMT_DIR!..\bin.x64\Lib\site-packages\xtquant\" (
        echo   找到 QMT: !QMT_DIR!..
        pip install "!QMT_DIR!..\bin.x64\Lib\site-packages\xtquant\" -q
        set XTQUANT_FOUND=1
        goto :xtquant_done
    )
)

:xtquant_done
if %XTQUANT_FOUND% equ 0 (
    echo.
    echo   [警告] 未自动找到 xtquant！
    echo   请手动安装：
    echo   1. 找到你 QMT 安装目录下的 bin.x64\Lib\site-packages\xtquant\
    echo   2. 运行: pip install "你的QMT路径\bin.x64\Lib\site-packages\xtquant\"
    echo.
    echo   常见路径：
    echo     C:\国金证券QMT实盘\bin.x64\Lib\site-packages\xtquant\
    echo     D:\国金证券QMT实盘\bin.x64\Lib\site-packages\xtquant\
) else (
    echo   xtquant OK
)
echo.

:: ========== 5. 验证环境 ==========
echo [5/5] 验证环境...
echo.

python -c "import pandas; print('  pandas:  OK')" 2>nul || echo "  pandas:  缺失"
python -c "import numpy; print('  numpy:   OK')" 2>nul || echo "  numpy:   缺失"
python -c "import flask; print('  flask:   OK')" 2>nul || echo "  flask:   缺失"
python -c "import xtquant; print('  xtquant: OK')" 2>nul || echo "  xtquant: 缺失 - QMT 交易功能不可用！"
python -c "from swing_trading_manager import SwingTradingManager; print('  swing:   OK - 高抛低吸策略已就绪')" 2>nul || echo "  swing:   缺失"

echo.
echo ============================================================
echo   安装完成！
echo ============================================================
echo.
echo   下一步:
echo   1. 创建 account_config.json 填入你的国金证券账号
echo   2. 打开 config.py 确认 ENABLE_SWING_TRADING=True
echo   3. 启动国金证券 QMT 客户端并登录
echo   4. 运行: python main.py
echo   5. 浏览器打开 http://localhost:5000
echo.
echo   建议先跑模拟模式: config.py 中 ENABLE_SIMULATION_MODE=True
echo ============================================================
pause
