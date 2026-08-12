import requests
import sqlite3
from datetime import datetime, timedelta
import time
import re
import json
import urllib3
import schedule
import sys
import pandas as pd

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
        "name": "体彩API",
        "url": "https://webapi.sporttery.cn/gateway/lottery/getHistoryPageListV1.qry",
        "params": {
            "gameNo": "3d",
            "provinceId": "0",
            "pageSize": "100",
            "is498": "true",
            "pageNo": 1,
        },
        "headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": "https://www.sporttery.cn/jc/jsq/dlt/",
            "Connection": "keep-alive",
        },
        "type": "sporttery",
    },
]

TIMEOUT = 10
MAX_RETRIES = 3


def create_session(source_idx=0):
    session = requests.Session()
    session.trust_env = False
    session.headers.update(API_SOURCES[source_idx]["headers"])
    return session


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


def determine_pattern(n1, n2, n3):
    if n1 == n2 == n3:
        return "豹子"
    if n1 == n2 or n2 == n3 or n1 == n3:
        return "组三"
    return "组六"


def period_exists(cursor, period):
    cursor.execute(
        f"SELECT 1 FROM {TABLE_NAME} WHERE period = ?", (period,)
    )
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
            digits = red.split()
            if len(digits) < 3:
                digits = list(red)
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
    except Exception:
        pass
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
    except Exception:
        pass
    return results


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


def fetch_from_source(source_idx=0, max_pages=50, cutoff=None):
    if cutoff is None:
        cutoff = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")

    source = API_SOURCES[source_idx]
    session = create_session(source_idx)
    all_records = []
    errors = []
    status_codes = []

    if source["type"] == "cwl":
        parse_func = parse_cwl_data
    elif source["type"] == "sporttery":
        parse_func = parse_sporttery_data
    else:
        return pd.DataFrame(), ["未知数据源类型"], status_codes

    for page in range(1, max_pages + 1):
        params = dict(source["params"])
        params["pageNo"] = page
        data, error = fetch_json_with_retry(session, source["url"], params=params)

        if data is None:
            errors.append(f"第{page}页: {error}")
            if error:
                status_codes.append(f"{source['name']}: {error}")
            break

        records = parse_func(data)
        if not records:
            break

        for rec in records:
            if rec["draw_date"] and rec["draw_date"] < cutoff:
                return pd.DataFrame(all_records), None, status_codes
            all_records.append(rec)

        time.sleep(0.3)

    if not all_records:
        return pd.DataFrame(), errors if errors else ["无有效数据"], status_codes

    df = pd.DataFrame(all_records)
    df = df.drop_duplicates(subset=["period"], keep="first")
    df = df.sort_values("period", ascending=True).reset_index(drop=True)
    return df, None, status_codes


def fetch_with_fallback():
    """带备用源的抓取：主站失败自动切备用站"""
    all_status_codes = []
    for idx, source in enumerate(API_SOURCES):
        print(f"尝试数据源: {source['name']}...")
        df, errors, status_codes = fetch_from_source(source_idx=idx)
        all_status_codes.extend(status_codes)
        if not df.empty:
            print(f"成功从 {source['name']} 抓取 {len(df)} 条数据")
            return df, None, all_status_codes
        print(f"  {source['name']} 失败: {errors}")

    return pd.DataFrame(), ["所有数据源均失败"], all_status_codes


def incremental_update():
    conn = init_db()
    cursor = conn.cursor()

    latest_period = get_latest_period(cursor)
    if not latest_period:
        print("数据库为空，请先运行全量爬取")
        conn.close()
        return

    print(f"数据库最新期号: {latest_period}")

    df, errors, status_codes = fetch_with_fallback()
    if df.empty:
        print(f"抓取失败: {errors}")
        if status_codes:
            print(f"HTTP状态码: {status_codes}")
        conn.close()
        return

    inserted = 0
    for _, row in df.iterrows():
        if row["period"] <= latest_period:
            continue
        try:
            cursor.execute(
                f"""INSERT INTO {TABLE_NAME}
                    (period, num1, num2, num3, pattern, draw_date)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (row["period"], row["num1"], row["num2"], row["num3"],
                 row["pattern"], row["draw_date"]),
            )
            inserted += 1
        except sqlite3.IntegrityError:
            pass

    conn.commit()
    conn.close()
    print(f"成功更新 {inserted} 期数据")


def get_latest_period(cursor):
    cursor.execute(f"SELECT MAX(period) FROM {TABLE_NAME}")
    row = cursor.fetchone()
    return row[0] if row and row[0] else None


def run_scheduled():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 定时任务已启动")
    schedule.every().day.at("22:00").do(incremental_update)
    while True:
        schedule.run_pending()
        time.sleep(30)


def main():
    conn = init_db()
    cursor = conn.cursor()

    cutoff = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
    print(f"目标日期范围: {cutoff} ~ 至今")

    df, errors, status_codes = fetch_with_fallback()
    if df.empty:
        print(f"抓取失败: {errors}")
        if status_codes:
            print(f"HTTP状态码: {status_codes}")
        conn.close()
        return

    inserted = 0
    skipped = 0
    for _, row in df.iterrows():
        if row["draw_date"] < cutoff:
            break
        if period_exists(cursor, row["period"]):
            skipped += 1
            continue
        try:
            cursor.execute(
                f"""INSERT INTO {TABLE_NAME}
                    (period, num1, num2, num3, pattern, draw_date)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (row["period"], row["num1"], row["num2"], row["num3"],
                 row["pattern"], row["draw_date"]),
            )
            inserted += 1
        except sqlite3.IntegrityError:
            skipped += 1

    conn.commit()
    conn.close()
    print(f"完成！新增: {inserted} 条 | 跳过: {skipped} 条")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        mode = sys.argv[1]
        if mode == "--full":
            main()
        elif mode == "--update":
            incremental_update()
        elif mode == "--schedule":
            run_scheduled()
        else:
            print("用法:")
            print("  python scraper_3d.py --full       全量爬取近一年数据")
            print("  python scraper_3d.py --update     增量更新最新数据")
            print("  python scraper_3d.py --schedule   启动定时任务")
    else:
        print("用法:")
        print("  python scraper_3d.py --full       全量爬取近一年数据")
        print("  python scraper_3d.py --update     增量更新最新数据")
        print("  python scraper_3d.py --schedule   启动定时任务")