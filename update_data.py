import requests
import sqlite3
from datetime import datetime, timedelta
import time
import re
import json
import urllib3
import sys
import os

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DB_FILE = "lottery_data.db"
TABLE_NAME = "history3d"

API_SOURCES = [
    {
        "name": "福彩官方API",
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
        "name": "中彩网API",
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
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": "http://kaijiang.zhcw.com/zhcw/html/3d/",
            "X-Requested-With": "XMLHttpRequest",
        },
        "type": "cwl",
    },
]

TIMEOUT = 15
MAX_RETRIES = 3


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
            resp = session.get(url, params=params, timeout=TIMEOUT, verify=False)
            last_status = resp.status_code
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    return data, None
                except (json.JSONDecodeError, ValueError) as e:
                    last_error = f"JSON解析失败: {str(e)}"
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
            last_error = str(e)
            if attempt < max_retries:
                time.sleep(min(attempt * 3, 15))
    return None, last_error


def fetch_html_with_retry(session, url, params=None, max_retries=MAX_RETRIES):
    last_status = None
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = session.get(url, params=params, timeout=TIMEOUT, verify=False)
            last_status = resp.status_code
            resp.encoding = "utf-8"
            if resp.status_code == 200:
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
            last_error = str(e)
            if attempt < max_retries:
                time.sleep(min(attempt * 3, 15))
    return None, last_error


def parse_cwl_data(data):
    results = []
    try:
        rows = data.get("result", [])
        if not rows:
            return results
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
    except Exception as e:
        print(f"  解析福彩API数据异常: {e}")
    return results


def parse_sporttery_data(data):
    results = []
    try:
        columns = data.get("columns", "")
        rows_str = data.get("rows", "")
        if not rows_str:
            return results
        col_list = columns.split(",")
        rows = rows_str.split(";")
        for row_str in rows:
            if not row_str.strip():
                continue
            vals = row_str.split(",")
            row_dict = dict(zip(col_list, vals))
            period = row_dict.get("issue", "")
            if not re.match(r"^\d{5,}$", period):
                continue
            nums = row_dict.get("lotteryDrawResult", "")
            digits = nums.split()
            if len(digits) < 3:
                digits = list(nums)
            if len(digits) < 3:
                continue
            n1, n2, n3 = int(digits[0]), int(digits[1]), int(digits[2])
            date_str = row_dict.get("lotteryDrawTime", "")
            draw_date = normalize_date(date_str) if date_str else ""
            pattern = determine_pattern(n1, n2, n3)
            results.append({
                "period": period,
                "num1": n1,
                "num2": n2,
                "num3": n3,
                "pattern": pattern,
                "draw_date": draw_date,
            })
    except Exception as e:
        print(f"  解析体彩API数据异常: {e}")
    return results


def parse_500_data(html):
    from bs4 import BeautifulSoup
    results = []
    try:
        soup = BeautifulSoup(html, "html.parser")
        table = soup.find("table", id="tablelist")
        if not table:
            table = soup.find("table")
        if not table:
            return results
        for row in table.find_all("tr"):
            tds = row.find_all("td")
            if len(tds) < 3:
                continue
            try:
                period = tds[0].get_text(strip=True)
                if not re.match(r"^\d{5,}$", period):
                    continue
                digits = []
                for td in tds[1:4]:
                    d = td.get_text(strip=True)
                    if d.isdigit() and len(d) == 1:
                        digits.append(int(d))
                if len(digits) < 3:
                    all_text = "".join(td.get_text(strip=True) for td in tds)
                    found = re.findall(r"\d", all_text)
                    if len(found) >= 3:
                        digits = [int(found[i]) for i in range(3)]
                if len(digits) < 3:
                    continue
                n1, n2, n3 = digits[0], digits[1], digits[2]
                date_td = tds[-1] if len(tds) > 4 else None
                date_str = date_td.get_text(strip=True) if date_td else ""
                draw_date = normalize_date(date_str) if date_str else ""
                pattern = determine_pattern(n1, n2, n3)
                results.append({
                    "period": period,
                    "num1": n1,
                    "num2": n2,
                    "num3": n3,
                    "pattern": pattern,
                    "draw_date": draw_date,
                })
            except (ValueError, IndexError):
                continue
    except Exception as e:
        print(f"  解析500彩票数据异常: {e}")
    return results


def fetch_from_source(source_idx=0, max_pages=50, cutoff=None):
    if cutoff is None:
        cutoff = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")

    source = API_SOURCES[source_idx]
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
            break

        for rec in records:
            if rec["draw_date"] and rec["draw_date"] < cutoff:
                return all_records, None
            all_records.append(rec)

        time.sleep(0.3)

    return all_records, errors if errors else None


def fetch_with_fallback():
    all_records = []
    used_source = None
    for idx, source in enumerate(API_SOURCES):
        print(f"尝试数据源: {source['name']}...")
        records, errors = fetch_from_source(source_idx=idx)
        if records:
            print(f"成功从 {source['name']} 抓取 {len(records)} 条数据")
            all_records = records
            used_source = source["name"]
            break
        print(f"  {source['name']} 失败: {errors}")

    return all_records, used_source


def incremental_update():
    conn = init_db()
    cursor = conn.cursor()

    latest_period = get_latest_period(cursor)
    is_empty = latest_period is None
    if is_empty:
        print("数据库为空，执行全量导入...")
    else:
        print(f"数据库最新期号: {latest_period}")

    records, used_source = fetch_with_fallback()
    if not records:
        print("所有数据源均失败，无法更新")
        conn.close()
        return False

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
    conn.close()

    if inserted > 0:
        print(f"成功更新 {inserted} 期数据 (跳过 {skipped} 期) [来源: {used_source}]")
        return True
    else:
        print(f"无新数据需要更新 (跳过 {skipped} 期)")
        return False


if __name__ == "__main__":
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始更新数据...")
    has_update = incremental_update()
    if has_update:
        print("数据库已更新，需要提交到仓库")
    else:
        print("数据库无变化，无需提交")
    print("更新流程结束")