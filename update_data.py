import requests
import sqlite3
from datetime import datetime, timedelta
import time
import re
import json
import urllib3
import sys
import os
import traceback

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DB_FILE = "lottery_data.db"
TABLE_NAME = "history3d"

API_SOURCES = [
    {
        "name": "福彩官方API(cwl.gov.cn)",
        "url": "https://www.cwl.gov.cn/cwl_admin/front/cwlkj/search/kjxx/findDrawNotice",
        "params": {
            "name": "3d",
            "issueCount": "",
            "issueStart": "",
            "issueEnd": "",
            "dayStart": "",
            "dayEnd": "",
            "pageNo": 1,
            "pageSize": 100,
            "systemType": "PC",
        },
        "headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": "https://www.cwl.gov.cn/ygkj/wqkj/sd/",
            "X-Requested-With": "XMLHttpRequest",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        },
        "type": "cwl",
    },
    {
        "name": "中彩网页面(zhcw.com)",
        "url": "http://kaijiang.zhcw.com/zhcw/inc/3d/3d_wqhg.jsp",
        "params": {},
        "headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": "http://kaijiang.zhcw.com/zhcw/html/3d/",
            "Connection": "keep-alive",
        },
        "type": "zhcw",
    },
]

TIMEOUT = 15
MAX_RETRIES = 3


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def determine_pattern(n1, n2, n3):
    if n1 == n2 == n3:
        return "豹子"
    if n1 == n2 or n2 == n3 or n1 == n3:
        return "组三"
    return "组六"


def normalize_date(raw):
    raw = str(raw).strip()
    m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", raw)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = re.match(r"(\d{4})/(\d{1,2})/(\d{1,2})", raw)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = re.match(r"(\d{4})年(\d{1,2})月(\d{1,2})日", raw)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return raw


def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
            period    TEXT PRIMARY KEY,
            num1      INTEGER NOT NULL,
            num2      INTEGER NOT NULL,
            num3      INTEGER NOT NULL,
            pattern   TEXT NOT NULL,
            draw_date TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def get_latest_period(cursor):
    cursor.execute(f"SELECT MAX(period) FROM {TABLE_NAME}")
    row = cursor.fetchone()
    return row[0] if row and row[0] else None


def period_exists(cursor, period):
    cursor.execute(f"SELECT 1 FROM {TABLE_NAME} WHERE period = ?", (period,))
    return cursor.fetchone() is not None


def fetch_json_with_retry(session, url, params=None, max_retries=MAX_RETRIES):
    last_status = None
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            log(f"    请求尝试 {attempt}/{max_retries}: {url[:60]}... page={params.get('pageNo', '?') if params else '?'}")
            resp = session.get(url, params=params, timeout=TIMEOUT, verify=False)
            last_status = resp.status_code
            log(f"    响应状态码: {resp.status_code}, 长度: {len(resp.text)} bytes")
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    result_count = len(data.get("result", []))
                    log(f"    JSON解析成功, result条数: {result_count}")
                    return data, None
                except (json.JSONDecodeError, ValueError) as e:
                    last_error = f"JSON解析失败: {str(e)}"
                    log(f"    JSON解析失败: {e}, 原始内容前200字: {resp.text[:200]}")
            elif resp.status_code == 403:
                last_error = "HTTP 403 Forbidden"
                log(f"    403被拒, 等待3秒后重试...")
                time.sleep(3)
            elif resp.status_code == 429:
                last_error = "HTTP 429 Too Many Requests"
                log(f"    429限流, 等待5秒后重试...")
                time.sleep(5)
            else:
                last_error = f"HTTP {resp.status_code}"
                log(f"    非200状态码: {resp.status_code}")
                time.sleep(2)
        except requests.exceptions.SSLError as e:
            last_error = f"SSL错误: {str(e)[:100]}"
            log(f"    SSL错误: {e}")
        except requests.exceptions.ConnectionError as e:
            last_error = f"连接错误: {str(e)[:100]}"
            log(f"    连接错误: {e}")
            if attempt < max_retries:
                wait = min(attempt * 5, 20)
                log(f"    等待{wait}秒后重试...")
                time.sleep(wait)
        except requests.exceptions.Timeout as e:
            last_error = f"超时({TIMEOUT}秒)"
            log(f"    请求超时")
        except requests.RequestException as e:
            last_error = f"请求异常: {str(e)[:100]}"
            log(f"    请求异常: {e}")
            if attempt < max_retries:
                time.sleep(min(attempt * 3, 15))
    return None, last_error


def fetch_html_with_retry(session, url, params=None, max_retries=MAX_RETRIES):
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            log(f"    请求尝试 {attempt}/{max_retries}: {url[:60]}...")
            resp = session.get(url, params=params, timeout=TIMEOUT, verify=False)
            log(f"    响应状态码: {resp.status_code}, 长度: {len(resp.text)} bytes")
            if resp.status_code == 200:
                resp.encoding = "utf-8"
                return resp.text, None
            elif resp.status_code == 403:
                last_error = "HTTP 403"
                time.sleep(3)
            elif resp.status_code == 429:
                last_error = "HTTP 429"
                time.sleep(5)
            else:
                last_error = f"HTTP {resp.status_code}"
                time.sleep(2)
        except requests.RequestException as e:
            last_error = str(e)[:100]
            log(f"    请求异常: {e}")
            if attempt < max_retries:
                time.sleep(min(attempt * 3, 15))
    return None, last_error


def parse_cwl_data(data):
    results = []
    try:
        rows = data.get("result", [])
        if not rows:
            log("    CWL API返回0条result")
            return results
        log(f"    开始解析 {len(rows)} 条CWL数据...")
        for item in rows:
            code = item.get("code", "")
            if not re.match(r"^\d{5,}$", code):
                continue
            red = item.get("red", "")
            digits = [d.strip() for d in red.split(",") if d.strip().isdigit()]
            if len(digits) < 3:
                digits = [d for d in red.split() if d.isdigit()]
            if len(digits) < 3:
                digits = [c for c in red if c.isdigit()]
            if len(digits) < 3:
                log(f"    跳过期号{code}: 无法解析号码 '{red}'")
                continue
            n1, n2, n3 = int(digits[0]), int(digits[1]), int(digits[2])
            date_str = item.get("date", "")
            draw_date = normalize_date(date_str) if date_str else ""
            pattern = determine_pattern(n1, n2, n3)
            results.append({
                "period": code,
                "num1": n1,
                "num2": n2,
                "num3": n3,
                "pattern": pattern,
                "draw_date": draw_date,
            })
        log(f"    CWL解析完成: {len(results)} 条有效数据")
    except Exception as e:
        log(f"    解析CWL数据异常: {e}")
        traceback.print_exc()
    return results


def parse_zhcw_data(html):
    from bs4 import BeautifulSoup
    results = []
    try:
        soup = BeautifulSoup(html, "html.parser")
        table = soup.find("table")
        if not table:
            log("    zhcw页面未找到table标签")
            return results
        trs = table.find_all("tr")
        log(f"    zhcw页面找到 {len(trs)} 行")
        for tr in trs:
            tds = tr.find_all("td")
            if len(tds) < 3:
                continue
            try:
                date_text = tds[0].get_text(strip=True)
                period_text = tds[1].get_text(strip=True)
                nums_text = tds[2].get_text(strip=True)
                if not re.match(r"^\d{5,}$", period_text):
                    continue
                if len(nums_text) < 3:
                    continue
                digits = [c for c in nums_text if c.isdigit()]
                if len(digits) < 3:
                    log(f"    zhcw跳过期号{period_text}: 号码解析失败 '{nums_text}'")
                    continue
                n1, n2, n3 = int(digits[0]), int(digits[1]), int(digits[2])
                draw_date = normalize_date(date_text) if date_text else ""
                pattern = determine_pattern(n1, n2, n3)
                results.append({
                    "period": period_text,
                    "num1": n1,
                    "num2": n2,
                    "num3": n3,
                    "pattern": pattern,
                    "draw_date": draw_date,
                })
            except (ValueError, IndexError) as e:
                continue
        log(f"    zhcw解析完成: {len(results)} 条有效数据")
    except Exception as e:
        log(f"    解析zhcw数据异常: {e}")
        traceback.print_exc()
    return results


def fetch_from_cwl(source, max_pages=50, cutoff=None):
    if cutoff is None:
        cutoff = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")

    session = requests.Session()
    session.trust_env = False
    session.headers.update(source["headers"])
    all_records = []
    errors = []

    for page in range(1, max_pages + 1):
        params = dict(source["params"])
        params["pageNo"] = page
        data, error = fetch_json_with_retry(session, source["url"], params=params)
        if data is None:
            errors.append(f"第{page}页: {error}")
            break

        records = parse_cwl_data(data)
        if not records:
            log(f"    第{page}页无数据，停止翻页")
            break

        for rec in records:
            if rec["draw_date"] and rec["draw_date"] < cutoff:
                log(f"    到达截止日期 {cutoff}，停止抓取")
                return all_records, None
            all_records.append(rec)

        time.sleep(0.5)

    return all_records, errors if errors else None


def fetch_from_zhcw(source, max_pages=20, cutoff=None):
    if cutoff is None:
        cutoff = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")

    session = requests.Session()
    session.trust_env = False
    session.headers.update(source["headers"])
    all_records = []
    errors = []

    for page in range(1, max_pages + 1):
        params = {"pageNum": page}
        html, error = fetch_html_with_retry(session, source["url"], params=params)
        if html is None:
            errors.append(f"第{page}页: {error}")
            break

        records = parse_zhcw_data(html)
        if not records:
            log(f"    zhcw第{page}页无数据，停止翻页")
            break

        for rec in records:
            if rec["draw_date"] and rec["draw_date"] < cutoff:
                log(f"    zhcw到达截止日期 {cutoff}，停止抓取")
                return all_records, None
            all_records.append(rec)

        time.sleep(0.5)

    return all_records, errors if errors else None


def fetch_with_fallback():
    all_records = []
    used_source = None

    for idx, source in enumerate(API_SOURCES):
        log(f"========== 尝试数据源 {idx+1}/{len(API_SOURCES)}: {source['name']} ==========")

        try:
            if source["type"] == "cwl":
                records, errors = fetch_from_cwl(source)
            elif source["type"] == "zhcw":
                records, errors = fetch_from_zhcw(source)
            else:
                log(f"  未知数据源类型: {source['type']}")
                continue

            if records:
                log(f"  ✅ 成功从 {source['name']} 抓取 {len(records)} 条数据")
                if records:
                    log(f"  最新一期: {records[-1]['period']} ({records[-1]['draw_date']}) 号码: {records[-1]['num1']}{records[-1]['num2']}{records[-1]['num3']}")
                all_records = records
                used_source = source["name"]
                break
            else:
                log(f"  ❌ {source['name']} 返回0条数据, 错误: {errors}")

        except Exception as e:
            log(f"  ❌ {source['name']} 发生异常: {e}")
            traceback.print_exc()

    return all_records, used_source


def incremental_update():
    log("========== 开始数据库更新 ==========")

    if not os.path.exists(DB_FILE):
        log(f"数据库文件 {DB_FILE} 不存在，将创建新数据库")
    else:
        db_size = os.path.getsize(DB_FILE)
        log(f"数据库文件存在，大小: {db_size} bytes")

    conn = init_db()
    cursor = conn.cursor()

    cursor.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}")
    total_count = cursor.fetchone()[0]
    log(f"数据库当前总记录数: {total_count}")

    latest_period = get_latest_period(cursor)
    is_empty = latest_period is None
    if is_empty:
        log("数据库为空，执行全量导入...")
    else:
        log(f"数据库最新期号: {latest_period}")

    records, used_source = fetch_with_fallback()
    if not records:
        log("❌ 所有数据源均失败，无法更新")
        conn.close()
        return False

    log(f"抓取到 {len(records)} 条数据，开始写入数据库...")
    inserted = 0
    skipped = 0
    for rec in records:
        if not is_empty and rec["period"] <= latest_period:
            skipped += 1
            continue
        if period_exists(cursor, rec["period"]):
            skipped += 1
            continue
        try:
            cursor.execute(
                f"""INSERT INTO {TABLE_NAME}
                    (period, num1, num2, num3, pattern, draw_date)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (rec["period"], rec["num1"], rec["num2"], rec["num3"],
                 rec["pattern"], rec["draw_date"]),
            )
            inserted += 1
        except sqlite3.IntegrityError:
            skipped += 1

    conn.commit()

    cursor.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}")
    new_total = cursor.fetchone()[0]
    conn.close()

    if inserted > 0:
        log(f"✅ 成功更新 {inserted} 期数据 (跳过 {skipped} 期) [来源: {used_source}]")
        log(f"数据库记录数: {total_count} → {new_total}")
        return True
    else:
        log(f"无新数据需要更新 (跳过 {skipped} 期)")
        return False


if __name__ == "__main__":
    log(f"========== 福彩3D数据更新脚本启动 ==========")
    log(f"运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log(f"Python版本: {sys.version}")
    log(f"工作目录: {os.getcwd()}")
    log(f"数据库文件: {os.path.abspath(DB_FILE)}")

    try:
        has_update = incremental_update()
    except Exception as e:
        log(f"❌ 更新过程发生未捕获异常: {e}")
        traceback.print_exc()
        has_update = False

    if has_update:
        log("✅ 数据库已更新，需要提交到仓库")
    else:
        log("ℹ️ 数据库无变化或更新失败")

    log("========== 更新流程结束 ==========")