#!/bin/bash

echo "=== 正在启动服务器 ==="

# 检查虚拟环境是否存在
if [ ! -d "venv" ]; then
    echo "1. 创建虚拟环境..."
    python3 -m venv venv || { echo "错误: 无法创建虚拟环境"; exit 1; }
fi

# 激活虚拟环境
echo "2. 激活虚拟环境..."
source venv/bin/activate || { echo "错误: 无法激活虚拟环境"; exit 1; }

# 安装依赖
echo "3. 检查并安装依赖..."
pip3 install -q flask flask-cors requests || { echo "错误: 依赖安装失败"; exit 1; }

# 启动服务器
echo "4. 启动Flask服务器..."
echo "服务器将在以下地址运行:"
echo "  - http://localhost:5001"
echo "  - http://127.0.0.1:5001"
echo ""
echo "按 Ctrl+C 停止服务器"
echo "========================"
python3 app.py