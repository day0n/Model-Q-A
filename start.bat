@echo off
echo 正在启动服务器...

REM 检查虚拟环境
if not exist "venv" (
    echo 创建虚拟环境...
    python -m venv venv
)

REM 激活虚拟环境并安装依赖
echo 激活虚拟环境...
call venv\Scripts\activate.bat

echo 安装依赖...
pip install flask flask-cors requests

echo 启动Flask服务器...
echo 服务器将在 http://localhost:5001 运行
echo 按 Ctrl+C 停止服务器
python app.py

pause