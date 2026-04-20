"""
大乐透历史开奖抓取器

主数据源：500 彩票网 (datachart.500.com) · HTML 表格一次性返回全部期数
备用数据源：中国体育彩票官方 API (webapi.sporttery.cn) · JSON
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional

import requests
from tenacity import retry, stop_after_attempt, wait_exponential
from tqdm import tqdm

from ..db import get_conn, init_db
from ..utils.numbers import encode

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

FIVEHUNDRED_URL = (
    "https://datachart.500.com/dlt/history/newinc/history.php?start={start}&end={end}"
)
SPORTTERY_URL = (
    "https://webapi.sporttery.cn/gateway/lottery/getHistoryPageListV1.qry"
    "?gameNo=85&provinceId=0&pageSize=100&isVerify=1&pageNo={page}"
)

ROW_RE = re.compile(
    r'<tr class="t_tr1">'
    r'(?:<!--.*?-->)?\s*'
    r'<td class="t_tr1">(\d+)</td>'
    r'<td class="cfont2">(\d+)</td><td class="cfont2">(\d+)</td>'
    r'<td class="cfont2">(\d+)</td><td class="cfont2">(\d+)</td>'
    r'<td class="cfont2">(\d+)</td>'
    r'<td class="cfont4">(\d+)</td><td class="cfont4">(\d+)</td>'
    r'<td class="t_tr1">([\d,]+)</td>'
    r'.*?'
    r'<td class="t_tr1">([\d,]+)</td>'
    r'<td class="t_tr1">(\d{4}-\d{2}-\d{2})</td>',
    re.DOTALL,
)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _fetch_500(start: str = "07001", end: str = "99999") -> str:
    """
    从 500 彩票网获取历史开奖 HTML

    @param start 起始期号
    @param end 结束期号（给足大的值即可返回全部）
    @returns HTML 内容
    """
    url = FIVEHUNDRED_URL.format(start=start, end=end)
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or "gb2312"
    return resp.text


def _parse_500_html(html: str) -> List[Dict]:
    """
    解析 500 彩票网的 HTML 行

    @param html 网页原文
    @returns 规范化记录列表
    """
    records: List[Dict] = []
    for m in ROW_RE.finditer(html):
        try:
            issue = m.group(1)
            front = [int(m.group(i)) for i in range(2, 7)]
            back = [int(m.group(i)) for i in range(7, 9)]
            sales = int(m.group(9).replace(",", ""))
            pool = int(m.group(10).replace(",", ""))
            date = m.group(11)
            records.append(
                {
                    "issue": issue,
                    "draw_date": date,
                    "front": encode(front),
                    "back": encode(back),
                    "sales": sales,
                    "pool": pool,
                }
            )
        except (ValueError, AttributeError):
            continue
    return records


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _fetch_sporttery_page(page: int) -> dict:
    """
    从官方 API 获取单页数据
    """
    resp = requests.get(
        SPORTTERY_URL.format(page=page),
        headers={**HEADERS, "Referer": "https://www.sporttery.cn/"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def _parse_sporttery_record(item: Dict) -> Optional[Dict]:
    """
    解析官方 API 单条记录
    """
    try:
        result = item["lotteryDrawResult"].split()
        return {
            "issue": str(item["lotteryDrawNum"]),
            "draw_date": item["lotteryDrawTime"],
            "front": encode([int(x) for x in result[:5]]),
            "back": encode([int(x) for x in result[5:7]]),
            "sales": int(str(item.get("totalSaleAmount", "0")).replace(",", "") or 0),
            "pool": int(str(item.get("poolBalanceAfterdraw", "0")).replace(",", "") or 0),
        }
    except (KeyError, ValueError, AttributeError):
        return None


def fetch_from_sporttery(max_pages: int = 200) -> List[Dict]:
    """
    从官方 API 翻页抓取
    """
    records: List[Dict] = []
    first = _fetch_sporttery_page(1)
    total_pages = min(int(first.get("value", {}).get("pages", 1)), max_pages)
    for page in tqdm(range(1, total_pages + 1), desc="Sporttery API"):
        data = first if page == 1 else _fetch_sporttery_page(page)
        for it in data.get("value", {}).get("list", []):
            rec = _parse_sporttery_record(it)
            if rec:
                records.append(rec)
    return records


def fetch_all(start: str = "07001") -> List[Dict]:
    """
    抓取开奖数据。先尝试 500 彩票网（快、全），网络失败才降级到官方 API

    @param start 起始期号（增量抓取时只需给数据库最新期号 +1）
    """
    try:
        print(f"从 500 彩票网抓取（start={start}）…")
        html = _fetch_500(start=start)
        records = _parse_500_html(html)
        records.sort(key=lambda r: r["issue"])
        if records:
            print(f"500 彩票网返回 {len(records)} 条（最新 {records[-1]['issue']}）")
        else:
            print("500 彩票网返回 0 条（无新开奖）")
        return records
    except Exception as e:
        print(f"500 彩票网访问失败：{e}，降级到官方 API")

    records = fetch_from_sporttery()
    records.sort(key=lambda r: r["issue"])
    return records


def _latest_issue_in_db() -> Optional[str]:
    """
    查询数据库最新期号，用于增量抓取
    """
    init_db()
    with get_conn() as conn:
        row = conn.execute("SELECT issue FROM draws ORDER BY issue DESC LIMIT 1").fetchone()
    return row["issue"] if row else None


def save_to_db(records: List[Dict]) -> int:
    """
    入库（按期号 upsert）

    @returns 处理的记录数
    """
    init_db()
    n = 0
    with get_conn() as conn:
        for r in records:
            conn.execute(
                """
                INSERT INTO draws (issue, draw_date, front, back, sales, pool)
                VALUES (:issue, :draw_date, :front, :back, :sales, :pool)
                ON CONFLICT(issue) DO UPDATE SET
                    draw_date = excluded.draw_date,
                    front     = excluded.front,
                    back      = excluded.back,
                    sales     = excluded.sales,
                    pool      = excluded.pool
                """,
                r,
            )
            n += 1
        conn.commit()
    return n


def run(full: bool = False) -> None:
    """
    抓取入口：默认增量（只抓数据库最新期号之后的新数据），可指定 full=True 全量重抓

    @param full 是否强制全量抓取
    """
    latest = None if full else _latest_issue_in_db()
    if latest:
        try:
            start = f"{int(latest) + 1:05d}"
        except ValueError:
            start = latest
        print(f"数据库最新期号 {latest}，增量抓取从 {start} 开始")
        records = fetch_all(start=start)
        if not records:
            print("没有新开奖，无需更新")
            return
    else:
        print("数据库为空或强制全量，抓取全部历史")
        records = fetch_all(start="07001")

    n = save_to_db(records)
    print(f"成功入库/更新 {n} 条开奖记录")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="抓取大乐透开奖数据")
    parser.add_argument("--full", action="store_true", help="强制全量抓取（默认增量）")
    args = parser.parse_args()
    run(full=args.full)
