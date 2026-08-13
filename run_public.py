"""
公网访问启动脚本 - 使用 Cloudflare Tunnel（免费、无需注册）
随时随地访问您的应用
"""
import subprocess
import sys
import os
import threading
import time
import re
from http.server import HTTPServer, SimpleHTTPRequestHandler

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(PROJECT_DIR, 'static')

class PWAStaticHandler(SimpleHTTPRequestHandler):
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
    server = HTTPServer(('0.0.0.0', port), PWAStaticHandler)
    print(f"📁 静态文件服务器: http://localhost:{port}")
    server.serve_forever()

def start_streamlit(port=8501):
    cmd = [
        sys.executable, "-m", "streamlit", "run", "app.py",
        "--server.port", str(port),
        "--server.headless", "true",
        "--browser.gatherUsageStats", "false",
        "--server.address", "0.0.0.0"
    ]
    subprocess.run(cmd, cwd=PROJECT_DIR)

def check_cloudflared():
    try:
        result = subprocess.run(["cloudflared", "--version"], capture_output=True, text=True)
        return result.returncode == 0
    except FileNotFoundError:
        return False

def install_cloudflared():
    print("\n📥 正在下载 Cloudflare Tunnel...")
    import urllib.request
    
    url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
    exe_path = os.path.join(PROJECT_DIR, "cloudflared.exe")
    
    try:
        urllib.request.urlretrieve(url, exe_path)
        print("✅ Cloudflare Tunnel 下载完成！")
        return True
    except Exception as e:
        print(f"❌ 下载失败: {e}")
        print("\n手动安装方法：")
        print("1. 访问 https://github.com/cloudflare/cloudflared/releases")
        print("2. 下载 cloudflared-windows-amd64.exe")
        print("3. 重命名为 cloudflared.exe 并放在项目根目录")
        return False

def start_cloudflared(port=8501):
    cmd = ["cloudflared", "tunnel", "--url", f"http://localhost:{port}"]
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW
    )
    
    print("\n⏳ 正在建立公网隧道...")
    
    for line in process.stdout:
        match = re.search(r'(https://[a-z0-9-]+\.trycloudflare\.com)', line)
        if match:
            public_url = match.group(1)
            print("\n" + "=" * 60)
            print("🎉 公网访问地址：")
            print(f"🌐 {public_url}")
            print("=" * 60)
            print("\n📱 使用方法：")
            print(f"1. 在手机浏览器打开: {public_url}")
            print("2. 添加到主屏幕（像普通App一样）")
            print("3. 随时随地都能访问！")
            print("\n⚠️ 注意：")
            print("- 此地址在每次重启后会变化")
            print("- 保持此窗口打开，关闭后无法访问")
            print("- 不要关闭此终端窗口")
            print("=" * 60)
            break
    
    process.wait()

if __name__ == "__main__":
    print("=" * 60)
    print("🌐 福彩3D 智能决策 - 公网版")
    print("=" * 60)
    
    static_thread = threading.Thread(target=start_static_server, args=(8080,), daemon=True)
    static_thread.start()
    
    time.sleep(1)
    print("\n🚀 正在启动 Streamlit 应用...")
    
    streamlit_thread = threading.Thread(target=start_streamlit, args=(8501,), daemon=True)
    streamlit_thread.start()
    
    time.sleep(3)
    
    if not check_cloudflared():
        print("\n⚠️ 未检测到 cloudflared")
        if install_cloudflared():
            print("\n✅ 自动安装完成，正在启动...")
        else:
            print("\n❌ 请先手动安装 cloudflared")
            sys.exit(1)
    
    print("\n🔗 正在建立公网隧道...")
    start_cloudflared(8501)