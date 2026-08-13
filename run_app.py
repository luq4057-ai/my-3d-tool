"""
PWA 增强启动脚本
同时启动 Streamlit 应用和静态文件代理服务器
"""
import subprocess
import sys
import os
import threading
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(PROJECT_DIR, 'static')

class PWAStaticHandler(SimpleHTTPRequestHandler):
    """提供 PWA 静态文件并设置正确的 MIME 类型"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC_DIR, **kwargs)
    
    def end_headers(self):
        if self.path.endswith('.json'):
            self.send_header('Content-Type', 'application/manifest+json')
            self.send_header('Access-Control-Allow-Origin', '*')
        elif self.path.endswith('.js'):
            self.send_header('Content-Type', 'application/javascript')
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.send_header('Service-Worker-Allowed', '/')
        elif self.path.endswith('.png'):
            self.send_header('Cache-Control', 'public, max-age=31536000')
        super().end_headers()
    
    def log_message(self, format, *args):
        pass

def start_static_server(port=8080):
    """启动静态文件服务器"""
    server = HTTPServer(('0.0.0.0', port), PWAStaticHandler)
    print(f"📁 静态文件服务器: http://localhost:{port}")
    server.serve_forever()

def start_streamlit(port=8501):
    """启动 Streamlit 应用"""
    cmd = [
        sys.executable, "-m", "streamlit", "run", "app.py",
        "--server.port", str(port),
        "--server.headless", "true",
        "--browser.gatherUsageStats", "false"
    ]
    subprocess.run(cmd, cwd=PROJECT_DIR)

if __name__ == "__main__":
    print("=" * 50)
    print("🎲 福彩3D 智能决策 PWA 版")
    print("=" * 50)
    
    static_thread = threading.Thread(target=start_static_server, args=(8080,), daemon=True)
    static_thread.start()
    
    time.sleep(1)
    print("\n🚀 正在启动 Streamlit 应用...")
    print("📱 访问地址: http://localhost:8501")
    print("💡 添加到主屏幕后，应用将以全屏模式运行")
    print("=" * 50)
    
    start_streamlit()