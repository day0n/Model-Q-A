from flask import Flask, render_template, request, Response, jsonify, send_file
from flask_cors import CORS
import requests
import json
import re
import logging
from datetime import datetime
import os
import uuid
from werkzeug.utils import secure_filename

app = Flask(__name__)
CORS(app)

# 配置文件上传
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf', 'docx', 'txt', 'md', 'json', 'csv'}

# 确保上传目录存在
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('dify_debug.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Dify API配置
DIFY_API_URL = "http://10.0.100.98/v1/chat-messages"
DIFY_API_KEY = "app-B0VIK9h34x1cynWeX8z3qKKF"

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/upload', methods=['POST'])
def upload_files():
    try:
        if 'files' not in request.files:
            return jsonify({'error': '没有文件'}), 400
        
        files = request.files.getlist('files')
        uploaded_urls = []
        
        for file in files:
            if file and allowed_file(file.filename):
                # 生成安全的文件名
                filename = secure_filename(file.filename)
                # 生成唯一文件名避免冲突
                unique_filename = f"{uuid.uuid4()}_{filename}"
                file_path = os.path.join(UPLOAD_FOLDER, unique_filename)
                
                # 保存文件
                file.save(file_path)
                
                # 生成文件的访问URL（使用内网可访问的URL）
                import socket
                hostname = socket.gethostname()
                local_ip = socket.gethostbyname(hostname)
                file_url = f"http://{local_ip}:5001/files/{unique_filename}"
                uploaded_urls.append(file_url)
        
        return jsonify({'urls': uploaded_urls})
    
    except Exception as e:
        logger.error(f"文件上传失败: {e}")
        return jsonify({'error': '文件上传失败'}), 500

@app.route('/download/<filename>')
def download_file(filename):
    try:
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        if os.path.exists(file_path):
            return send_file(file_path, as_attachment=True)
        else:
            return jsonify({'error': '文件不存在'}), 404
    except Exception as e:
        logger.error(f"文件下载失败: {e}")
        return jsonify({'error': '文件下载失败'}), 500

@app.route('/files/<filename>')
def serve_file(filename):
    """提供文件访问服务，供内网访问"""
    try:
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        if os.path.exists(file_path):
            return send_file(file_path)
        else:
            return jsonify({'error': '文件不存在'}), 404
    except Exception as e:
        logger.error(f"文件访问失败: {e}")
        return jsonify({'error': '文件访问失败'}), 500

@app.route('/')
def index():
    return render_template('index.html')

def generate_stream(response, user_message):
    """生成流式响应 - 实现思考内容的实时流式输出"""
    accumulated_content = ""
    thinking_sent = False
    thinking_buffer = ""
    is_collecting_thinking = False
    
    for line in response.iter_lines():
        if line:
            line = line.decode('utf-8')
            logger.debug(f"Received line: {line}")
            
            if line.startswith('data: '):
                data = line[6:]
                if data == '[DONE]':
                    yield "data: [DONE]\n\n"
                    break
                    
                try:
                    parsed_data = json.loads(data)
                    
                    # 只处理包含答案的事件
                    if parsed_data.get('event') in ['node_started', 'node_finished', 'workflow_started', 'workflow_finished', 'ping']:
                        continue
                    
                    answer = parsed_data.get('answer', '')
                    if not answer:
                        continue
                    
                    accumulated_content += answer
                    
                    # 实时处理思考内容 - 使用状态机方式处理
                    think_start_tag = '<think>'
                    think_end_tag = '</think>'
                    
                    # 检查是否在思考标签内
                    if think_start_tag in answer or think_end_tag in answer or is_collecting_thinking:
                        # 分割答案块以处理思考标签
                        while answer:
                            if is_collecting_thinking:
                                # 正在收集思考内容，寻找结束标签
                                if think_end_tag in answer:
                                    # 找到结束标签
                                    end_index = answer.find(think_end_tag)
                                    thinking_chunk = answer[:end_index]
                                    thinking_buffer += thinking_chunk
                                    
                                    # 发送思考内容的最后一块
                                    if thinking_buffer.strip():
                                        yield f"data: {json.dumps({
                                            'type': 'thinking_stream',
                                            'thinking': thinking_buffer,
                                            'is_complete': True,
                                            'chunk_index': 0,
                                            'total_chunks': 1
                                        }, ensure_ascii=False)}\n\n"
                                        thinking_sent = True
                                        logger.debug(f"Sent final thinking chunk: {thinking_buffer[:50]}...")
                                    
                                    # 重置状态
                                    thinking_buffer = ""
                                    is_collecting_thinking = False
                                    
                                    # 处理结束标签后的内容
                                    remaining_content = answer[end_index + len(think_end_tag):]
                                    if remaining_content.strip():
                                        # 发送思考标签后的正式内容
                                        yield f"data: {json.dumps({
                                            'type': 'message',
                                            'answer': remaining_content
                                        }, ensure_ascii=False)}\n\n"
                                    
                                    answer = ""
                                else:
                                    # 没有找到结束标签，整个块都是思考内容
                                    thinking_buffer += answer
                                    answer = ""
                            else:
                                # 不在思考标签内，寻找开始标签
                                if think_start_tag in answer:
                                    # 找到开始标签
                                    start_index = answer.find(think_start_tag)
                                    
                                    # 发送开始标签前的正式内容
                                    before_content = answer[:start_index]
                                    if before_content.strip():
                                        yield f"data: {json.dumps({
                                            'type': 'message',
                                            'answer': before_content
                                        }, ensure_ascii=False)}\n\n"
                                    
                                    # 开始收集思考内容
                                    is_collecting_thinking = True
                                    answer = answer[start_index + len(think_start_tag):]
                                    
                                    # 如果这个块里还有结束标签，下一轮循环会处理
                                else:
                                    # 没有思考标签，直接发送正式内容
                                    yield f"data: {json.dumps({
                                        'type': 'message',
                                        'answer': answer
                                    }, ensure_ascii=False)}\n\n"
                                    answer = ""
                    else:
                        # 没有思考标签，直接发送正式内容
                        yield f"data: {json.dumps({
                            'type': 'message',
                            'answer': answer
                        }, ensure_ascii=False)}\n\n"
                        
                except json.JSONDecodeError as e:
                    logger.error(f"JSON decode error: {e}")
                    continue

@app.route('/chat', methods=['POST'])
def chat():
    try:
        data = request.json
        user_message = data.get('query', '')
        user_id = data.get('user', 'abc-123')
        mode = data.get('inputs', {}).get('classification', '1')
        file_urls = data.get('urls', []) or ([data.get('inputs', {}).get('url')] if data.get('inputs', {}).get('url') else [])
        
        # 添加调试日志
        logger.debug(f"收到请求: {data}")
        logger.debug(f"解析后的file_urls: {file_urls}")
        
        # 调用Dify API
        headers = {
            'Authorization': f'Bearer {DIFY_API_KEY}',
            'Content-Type': 'application/json'
        }
        
        payload = {
            "inputs": {
                "classification": mode
            },
            "query": user_message,
            "response_mode": "streaming",
            "user": user_id
        }
        
        if mode == "1":
            payload["inputs"]["url"] = "https://httpbin.org/get"
        elif mode == "2" and file_urls:
            payload["inputs"]["url"] = file_urls[0]
        elif mode == "3" and file_urls:
            payload["inputs"]["url"] = file_urls[0]
        elif mode == "3":
            # 如果没有上传文件，使用默认测试URL
            payload["inputs"]["url"] = "https://httpbin.org/get"
        
        # 添加调试日志显示最终payload
        logger.debug(f"发送给Dify的payload: {payload}")
        
        response = requests.post(DIFY_API_URL, headers=headers, json=payload, stream=True)
            
        return Response(
            generate_stream(response, user_message),
            mimetype='text/event-stream'
        )
        
    except Exception as e:
        def generate_error():
            yield f"data: {json.dumps({
                'type': 'error',
                'answer': f'错误：{str(e)}'
            }, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        
        return Response(
            generate_error(),
            mimetype='text/event-stream'
        )

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)