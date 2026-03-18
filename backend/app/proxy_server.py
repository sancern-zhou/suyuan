#!/usr/bin/env python3
"""
本地千问3服务器代理
用于解决CORS问题和统一参数处理
"""

import http.server
import socketserver
import json
import urllib.request
import urllib.parse
from urllib.error import URLError
import structlog

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = structlog.get_logger()

# 实际的千问3 API 地址
API_BASE_URL = 'https://public-1960182902053687299-iaaa.ksai.scnet.cn:58043/v1/chat/completions'

class CORSProxyHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_POST(self):
        if self.path == '/api':
            self.proxy_request()
        else:
            super().do_POST()

    def do_GET(self):
        if self.path == '/health':
            self.send_health_response()
        else:
            super().do_GET()

    def send_health_response(self):
        """健康检查端点"""
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        response_data = json.dumps({
            'status': 'healthy',
            'proxy': 'running',
            'target': API_BASE_URL
        }).encode()
        self.wfile.write(response_data)

    def proxy_request(self):
        """代理请求到千问3服务器"""
        try:
            # 读取请求体
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            
            # 解析请求数据
            request_data = json.loads(post_data)
            
            logger.info("📥 收到代理请求")
            logger.debug(f"原始请求: {json.dumps(request_data, indent=2, ensure_ascii=False)}")
            
            # 🔧 强制设置千问3优化参数（匹配我们的配置）
            request_data.update({
                'temperature': request_data.get('temperature', 0.7),  # 使用传入的温度或默认值
                'top_p': request_data.get('top_p', 0.8),
                'top_k': request_data.get('top_k', 20),
                'min_p': request_data.get('min_p', 0),
                'enable_thinking': False  # 硬开关：强制禁用思考模式
            })
            
            # 🔧 确保消息中包含 /no_think 标记（软开关，双重保险）
            if 'messages' in request_data and request_data['messages']:
                for msg in request_data['messages']:
                    if msg['role'] == 'user' and not msg['content'].endswith(' /no_think'):
                        msg['content'] = msg['content'] + ' /no_think'
                        logger.debug("🔧 添加软开关标记: /no_think")
        
            logger.debug(f"处理后请求: {json.dumps(request_data, indent=2, ensure_ascii=False)}")
            
            # 转发到千问3 API
            req = urllib.request.Request(
                API_BASE_URL,
                data=json.dumps(request_data).encode('utf-8'),
                headers={'Content-Type': 'application/json'}
            )
            
            logger.info("📤 转发请求到千问3服务器...")
            
            with urllib.request.urlopen(req, timeout=300) as response:
                response_data = response.read()
                
            logger.info("📥 千问3服务器响应成功")
                
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(response_data)
            
        except URLError as e:
            logger.error(f"❌ 千问3 API调用失败: {e}")
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            error_msg = json.dumps({
                'error': f'千问3 API调用失败: {str(e)}',
                'type': 'proxy_error'
            }).encode()
            self.wfile.write(error_msg)
        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON解析失败: {e}")
            self.send_response(400)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            error_msg = json.dumps({
                'error': f'JSON解析失败: {str(e)}',
                'type': 'json_error'
            }).encode()
            self.wfile.write(error_msg)
        except Exception as e:
            logger.error(f"❌ 代理服务器内部错误: {e}")
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            error_msg = json.dumps({
                'error': f'代理服务器内部错误: {str(e)}',
                'type': 'internal_error'
            }).encode()
            self.wfile.write(error_msg)

if __name__ == '__main__':
    PORT = 8088  # 修改为8088端口避免冲突
    
    logger.info("="*60)
    logger.info("🚀 千问3代理服务器启动中...")
    logger.info("="*60)
    logger.info(f"🌐 代理服务器地址: http://localhost:{PORT}")
    logger.info(f"📡 API端点: http://localhost:{PORT}/api")
    logger.info(f"🔗 目标服务器: {API_BASE_URL}")
    logger.info(f"💊 健康检查: http://localhost:{PORT}/health")
    logger.info("🔧 已配置参数优化:")
    logger.info("   - enable_thinking: false (强制禁用思考模式)")
    logger.info("   - 自动添加 /no_think 软开关")
    logger.info("   - CORS头部支持")
    logger.info("="*60)
    
    try:
        with socketserver.TCPServer(("", PORT), CORSProxyHandler) as httpd:
            logger.info("✅ 代理服务器已启动，等待请求...")
            httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("⏹️  代理服务器已停止")
    except Exception as e:
        logger.error(f"❌ 代理服务器启动失败: {e}")