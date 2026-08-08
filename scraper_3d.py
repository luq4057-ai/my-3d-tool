import requests
from bs4 import BeautifulSoup
import sqlite3
from datetime import datetime, timedelta
import time
import re
import urllib3
import schedule
import sys

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "http://kaijiang.zhcw.com/zhcw/inc/3d/3d_wqhg.jsp?pageNum={}"
DB_FILE = "lottery_data.db"
TABLE_NAME = "history3d"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def create_session():
    session = requests.Session()
    session.trust_env = False
    session.headers.update(HEADERS)
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


def fetch_page(session, page_num, max_retries=3):
    url = BASE_URL.format(page_num)
    for attempt in range(1, max_retries + 1):
        try:
            resp = session.get(url, timeout=30, verify=False)
            resp.encoding = "utf-8"
            if resp.status_code == 200:
                return resp.text
            print(f"  HTTP {resp.status_code}")
            return None
        except requests.RequestException as e:
            if attempt < max_retries:
                wait = attempt * 3
                print(f"  第{attempt}次失败，{wait}秒后重试...", end=" ")
                time.sleep(wait)
            else:
                print(f"  请求异常(已重试{max_retries}次): {e}")
                return None


def normalize_date(raw):
    raw = raw.strip()
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


def parse_page(html):
    soup = BeautifulSoup(html, "html.parser")
    results = []

    table = soup.find("table", class_="wqhgt")
    if not table:
        table = soup.find("table")
    if not table:
        return results

    all_rows = table.find_all("tr")
    data_rows = all_rows[2:-1]

    for row in data_rows:
        tds = row.find_all("td")
        if len(tds) < 3:
            continue

        try:
            raw_date = tds[0].get_text(strip=True)
            if not re.search(r"\d{4}", raw_date):
                continue

            period = tds[1].get_text(strip=True)
            if not re.match(r"^\d{5,}$", period):
                continue

            em_tags = tds[2].find_all("em")
            if em_tags:
                digits = [em.get_text(strip=True) for em in em_tags]
            else:
                digits = re.findall(r"\d", tds[2].get_text(strip=True))

            if len(digits) < 3:
                continue

            n1, n2, n3 = int(digits[0]), int(digits[1]), int(digits[2])
            draw_date = normalize_date(raw_date)
            results.append((period, n1, n2, n3, draw_date))
        except (ValueError, IndexError):
            continue

    return results


def get_latest_period(cursor):
    cursor.execute(f"SELECT MAX(period) FROM {TABLE_NAME}")
    row = cursor.fetchone()
    return row[0] if row and row[0] else None


def incremental_update():
    conn = init_db()
    cursor = conn.cursor()
    session = create_session()

    latest_period = get_latest_period(cursor)
    if latest_period:
        print(f"数据库最新期号: {latest_period}")
    else:
        print("数据库为空，请先运行全量爬取（python scraper_3d.py --full）")
        conn.close()
        return

    print("正在获取官网最新数据 ...", end=" ")
    html = fetch_page(session, 1)
    if html is None:
        print("获取失败")
        conn.close()
        return

    records = parse_page(html)
    if not records:
        print("无有效数据")
        conn.close()
        return

    inserted = 0
    for period, n1, n2, n3, draw_date in records:
        if period <= latest_period:
            break
        pattern = determine_pattern(n1, n2, n3)
        try:
            cursor.execute(
                f"""
                INSERT INTO {TABLE_NAME}
                    (period, num1, num2, num3, pattern, draw_date)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (period, n1, n2, n3, pattern, draw_date),
            )
            inserted += 1
            print(f"\n  新增: 期号={period} 号码={n1}{n2}{n3} 形态={pattern} 日期={draw_date}", end="")
        except sqlite3.IntegrityError:
            pass

    conn.commit()
    conn.close()
    print(f"\n成功更新 {inserted} 期数据")


def run_scheduled():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 定时任务已启动，每天 22:00 执行增量更新")
    schedule.every().day.at("22:00").do(incremental_update)
    while True:
        schedule.run_pending()
        time.sleep(30)


def main():
    conn = init_db()
    cursor = conn.cursor()
    session = create_session()

    cutoff = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
    print(f"目标日期范围: {cutoff} ~ 至今")

    page = 1
    total_inserted = 0
    total_skipped = 0
    should_continue = True

    while should_continue:
        print(f"正在爬取第 {page} 页 ...", end=" ")
        html = fetch_page(session, page)
        if html is None:
            print("获取失败，停止")
            break

        records = parse_page(html)
        if not records:
            print("无有效数据，停止")
            break

        page_inserted = 0
        for period, n1, n2, n3, draw_date in records:
            if draw_date < cutoff:
                should_continue = False
                break

            if period_exists(cursor, period):
                total_skipped += 1
                continue

            pattern = determine_pattern(n1, n2, n3)
            try:
                cursor.execute(
                    f"""
                    INSERT INTO {TABLE_NAME}
                        (period, num1, num2, num3, pattern, draw_date)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (period, n1, n2, n3, pattern, draw_date),
                )
                total_inserted += 1
                page_inserted += 1
            except sqlite3.IntegrityError:
                total_skipped += 1

        conn.commit()
        print(f"新增 {page_inserted} 条")
        page += 1
        time.sleep(1)

    conn.close()
    print(f"\n完成！新增: {total_inserted} 条 | 跳过(已存在): {total_skipped} 条")
    print(f"数据库: {DB_FILE}  表: {TABLE_NAME}")


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
            print("  python scraper_3d.py --schedule   启动定时任务(每天22:00增量更新)")
    else:
        print("用法:")
        print("  python scraper_3d.py --full       全量爬取近一年数据")
        print("  python scraper_3d.py --update     增量更新最新数据")
        print("  python scraper_3d.py --schedule   启动定时任务(每天22:00增量更新)")
        print()
        print("Windows 任务计划(Cron 替代方案):")
        print('  schtasks /create /tn "福彩3D增量更新" /tr "python F:\\lq-lh\\3d\\scraper_3d.py --update" /sc daily /st 22:00')
        print("  删除任务:  schtasks /delete /tn \"福彩3D增量更新\" /f")
        print("  查看任务:  schtasks /query /tn \"福彩3D增量更新\"")