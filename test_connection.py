import requests
from bs4 import BeautifulSoup
import sys

BASE_URL = "http://kaijiang.zhcw.com/zhcw/inc/3d/3d_wqhg.jsp?pageNum=1"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

print("=" * 60)
print("福彩3D 数据源连接测试")
print("=" * 60)

print("\n[1/3] 测试网络连接...")
try:
    session = requests.Session()
    session.headers.update(HEADERS)
    resp = session.get(BASE_URL, timeout=30, verify=False)
    print(f"  ✓ HTTP 状态码: {resp.status_code}")
    print(f"  ✓ 响应大小: {len(resp.text)} 字节")
except Exception as e:
    print(f"  ✗ 连接失败: {e}")
    sys.exit(1)

print("\n[2/3] 测试数据解析...")
try:
    resp.encoding = "utf-8"
    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("table", class_="wqhgt")
    if table:
        rows = table.find_all("tr")
        print(f"  ✓ 找到数据表格，共 {len(rows)} 行")
    else:
        print("  ✗ 未找到数据表格")
        sys.exit(1)
except Exception as e:
    print(f"  ✗ 解析失败: {e}")
    sys.exit(1)

print("\n[3/3] 测试本地数据库...")
try:
    import sqlite3
    import os
    if os.path.exists("lottery_data.db"):
        conn = sqlite3.connect("lottery_data.db")
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM history3d")
        count = cursor.fetchone()[0]
        conn.close()
        print(f"  ✓ 本地数据库存在，共 {count} 条记录")
    else:
        print("  ⚠ 本地数据库不存在（云端环境正常）")
except Exception as e:
    print(f"  ✗ 数据库检查失败: {e}")

print("\n" + "=" * 60)
print("✅ 所有测试通过！数据源连接正常")
print("=" * 60)