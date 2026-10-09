"""
从巨潮资讯网（cninfo）批量下载 A 股上市公司年报 PDF。

用法：
  python scripts/fetch_annual_reports.py                  # 下载抽样框全部公司
  python scripts/fetch_annual_reports.py --code 600519.SH 000002.SZ  # 只下指定公司
  python scripts/fetch_annual_reports.py --year 2023      # 指定年报年度（默认2024）

产出：
  data/companies/annual_reports/<code>_<name>_<year>.pdf
  data/companies/download_report.csv                      # 下载结果清单（含失败原因）

说明：
- 年报原文 PDF 只存本地，不提交 GitHub；抽取后的事实样本以 data/companies/*.json 入库。
- 巨潮接口为公开数据接口，调用间隔 1 秒，请控制频率。
"""
import argparse
import csv
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRAME = ROOT / "data" / "companies" / "sampling_frame.csv"
OUT_DIR = ROOT / "data" / "companies" / "annual_reports"
RESULT_CSV = ROOT / "data" / "companies" / "download_report.csv"
STOCK_LIST_URL = "http://www.cninfo.com.cn/new/data/szse_stock.json"
QUERY_URL = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
STATIC_URL = "http://static.cninfo.com.cn/"

HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "http://www.cninfo.com.cn"}


def http_get(url: str) -> bytes:
    req = urllib.request.Request(url, headers=HEADERS)
    return urllib.request.urlopen(req, timeout=30).read()


def http_post(url: str, data: dict) -> bytes:
    req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode(),
                                 headers=HEADERS)
    return urllib.request.urlopen(req, timeout=30).read()


def load_org_ids() -> dict:
    d = json.loads(http_get(STOCK_LIST_URL))
    return {s["code"]: s["orgId"] for s in d["stockList"]}


def find_annual_report(code: str, org_id: str, name: str, year: int) -> tuple[str, str] | None:
    """返回 (公告标题, adjunctUrl)；精确匹配《<name><year>年年度报告》，排除摘要/英文版/取消。"""
    column = "sse" if code.startswith("6") else "szse"
    data = {
        "pageNum": "1", "pageSize": "30", "column": column, "tabName": "fulltext",
        "stock": f"{code},{org_id}", "category": "category_ndbg_szsh",
        "seDate": f"{year + 1}-01-01~{year + 1}-12-31", "isHLtitle": "true",
    }
    resp = json.loads(http_post(QUERY_URL, data))
    bad = ("摘要", "英文", "取消", "已更正", "补充")
    cands = []
    for a in resp.get("announcements") or []:
        title = re.sub(r"<[^>]+>", "", a["announcementTitle"])
        if any(b in title for b in bad):
            continue
        # 标题后缀为 "<year>年年度报告" 或 "<year>年度报告" 均可（公司名前缀不统一，如
        # "招商银行股份有限公司2024年度报告"、部分公司干脆不带公司名）
        if title.endswith(f"{year}年年度报告") or title.endswith(f"{year}年度报告"):
            cands.append((title, a["adjunctUrl"]))
    if not cands:
        return None
    # 优先带公司名前缀的精确匹配
    for t, u in cands:
        if t.startswith(name):
            return t, u
    return cands[0]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--code", nargs="*", help="限定股票代码（如 600519.SH）")
    ap.add_argument("--year", type=int, default=2024, help="年报年度，默认 2024")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(FRAME, newline="", encoding="utf-8") as f:
        frame = list(csv.DictReader(f))
    if args.code:
        frame = [r for r in frame if r["stock_code"] in args.code]

    print("加载巨潮股票列表...", flush=True)
    org_ids = load_org_ids()

    results = []
    for r in frame:
        code6 = r["stock_code"].split(".")[0]
        row = {"stock_code": r["stock_code"], "name": r["name"], "year": args.year,
               "status": "failed", "file": "", "note": ""}
        try:
            hit = find_annual_report(code6, org_ids[code6], r["name"], args.year)
            if not hit:
                row["note"] = f"未找到 {r['name']}{args.year}年年度报告"
            else:
                title, adjunct = hit
                fname = f"{r['stock_code']}_{r['name']}_{args.year}.pdf"
                fpath = OUT_DIR / fname
                if not fpath.exists() or fpath.stat().st_size < 100_000:
                    pdf = http_get(STATIC_URL + adjunct)
                    fpath.write_bytes(pdf)
                row.update(status="ok", file=str(fpath.relative_to(ROOT)),
                           note=f"{fpath.stat().st_size // 1024}KB")
                print(f"  ✓ {r['name']} {args.year} 年报 ({fpath.stat().st_size // 1024}KB)", flush=True)
        except Exception as e:  # noqa: BLE001
            row["note"] = f"{type(e).__name__}: {e}"
        results.append(row)
        time.sleep(1)

    with open(RESULT_CSV, newline="", encoding="utf-8") as f:
        prev = {r["stock_code"]: r for r in csv.DictReader(f)} if RESULT_CSV.exists() else {}
    prev.update({r["stock_code"]: r for r in results})  # 新结果覆盖旧记录（重试语义）
    merged = list(prev.values())
    with open(RESULT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        w.writeheader(); w.writerows(merged)
    ok = sum(1 for r in merged if r["status"] == "ok")
    print(f"\n累计: {ok}/{len(merged)} 成功，结果见 {RESULT_CSV.relative_to(ROOT)}")
    sys.exit(0 if all(r["status"] == "ok" for r in merged) else 1)


if __name__ == "__main__":
    main()
