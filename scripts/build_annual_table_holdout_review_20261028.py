"""Build a source-bound human review packet for parser holdout runs.

This creates review material only. It does not calculate parser accuracy or
convert unreviewed predictions into labels.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
RUNS = ROOT / "results" / "runs"
DEV_STOCKS = {"000651", "000999", "600036", "603288"}
DEFAULT_HOLDOUT_RUNS = [
    "annual_table_holdout_vanke_2024_default_20261028_01",
    "annual_table_holdout_midea_2024_default_20261028_01",
    "annual_table_holdout_beijing_culture_2024_default_20261028_01",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def build(out: Path, holdout_runs: list[str], parser_version: str):
    if out.exists():
        raise FileExistsError(f"Choose a fresh output directory: {out}")
    from scripts._table_runtime import ensure_local_pdf_libraries
    ensure_local_pdf_libraries()
    import pypdfium2 as pdfium
    from PIL import ImageDraw

    out.mkdir(parents=True)
    previews = out / "previews"
    previews.mkdir()
    audit = {
        "status": "review_packet_built_pending_independent_human_labels",
        "created_utc_date": "2026-10-28",
        "parser_version": parser_version,
        "model_calls": 0,
        "parser_development_stock_codes_excluded": sorted(DEV_STOCKS),
        "selection_note": (
            "Four locally available 2023/2024 reports from two companies, chosen retrospectively "
            "for parser engineering diagnostics after parser v1.7 was fixed. This is not a random "
            "or preregistered sample; the reports appeared in earlier RAG experiments, so this is "
            "not a fully novel end-to-end or temporal-generalization test."
        ),
        "reports": [],
        "aggregate": {},
        "limitations": [
            "Counts describe parser outputs, not correctness.",
            "No independent human labels were created by this script.",
            "Precision, recall and F1 must not be reported until page/table and row labels are independently reviewed.",
            "PDF company/year identity is caller-supplied metadata and is not independently verified here.",
        ],
    }
    page_review_rows = []
    prediction_rows = []
    category_totals = Counter()
    totals = Counter()
    html_sections = []
    blind_sections = []

    for run_name in holdout_runs:
        run_dir = RUNS / run_name
        document = load(run_dir / "document.json")
        source = document["source"]
        stock = source["stock"]
        if stock in DEV_STOCKS:
            raise ValueError(f"Development stock leaked into holdout: {stock}")
        if document.get("parser_version") != audit["parser_version"]:
            raise ValueError(f"Unexpected parser version in {run_name}")
        if document.get("model_calls") != 0:
            raise ValueError(f"Unexpected model call in {run_name}")
        pdf_path = Path(source["url"])
        if not pdf_path.is_file():
            # Older extraction records store the original URL in ``source.url``.
            # For offline review, recover the local source path from the frozen
            # cross-year protocol using the source hash; never download here.
            protocol_path = run_dir.parent / "protocol.json"
            if protocol_path.is_file():
                protocol = load(protocol_path)
                protocol_report = next(
                    (item for item in protocol.get("reports", [])
                     if item.get("sha256") == source["sha256"]), None
                )
                if protocol_report:
                    pdf_path = ROOT / protocol_report["path"]
            if not pdf_path.is_file():
                raise FileNotFoundError(
                    f"Local source PDF unavailable for {run_name}; refusing network download: {source['url']}"
                )
        actual_hash = sha256(pdf_path)
        if actual_hash != source["sha256"] or actual_hash != document["source_pdf_sha256"]:
            raise ValueError(f"PDF SHA-256 mismatch in {run_name}")

        tables = document["tables"]
        chains = document["logical_tables"]
        parsed_pages = document["parsed_pages"]
        selected_pages = document["selection"]["selected_pages"]
        tables_by_page = defaultdict(list)
        chains_by_page = defaultdict(list)
        for table in tables:
            tables_by_page[table["page"]].append(table)
        for chain in chains:
            for page in chain["pages"]:
                chains_by_page[page].append(chain)

        pdf = pdfium.PdfDocument(str(pdf_path))
        try:
            for page_number in selected_pages:
                page = pdf[page_number - 1]
                try:
                    bitmap = page.render(scale=1.0)
                    try:
                        image = bitmap.to_pil().convert("RGB")
                    finally:
                        bitmap.close()
                finally:
                    page.close()
                blind_image = image.copy()
                blind_rel = Path("blind_previews") / stock / f"page_{page_number:04d}.png"
                blind_path = out / blind_rel
                blind_path.parent.mkdir(parents=True, exist_ok=True)
                blind_image.save(blind_path, optimize=True)
                draw = ImageDraw.Draw(image)
                for table in tables_by_page[page_number]:
                    sx = image.width / table["page_width"]
                    sy = image.height / table["page_height"]
                    x0, y0, x1, y1 = table["bbox"]
                    draw.rectangle((x0 * sx, y0 * sy, x1 * sx, y1 * sy), outline="#c62828", width=3)
                image_rel = Path("previews") / stock / f"page_{page_number:04d}.png"
                image_path = out / image_rel
                image_path.parent.mkdir(parents=True, exist_ok=True)
                image.save(image_path, optimize=True)
                page_tables = tables_by_page[page_number]
                page_chains = chains_by_page[page_number]
                page_review_rows.append({
                    "review_id": f"{stock}-{source['year']}-P{page_number:04d}",
                    "stock_code": stock,
                    "report_year": source["year"],
                    "source_pdf_sha256": actual_hash,
                    "physical_page": page_number,
                    "independent_reviewer": "",
                    "page_has_governance_table_gold": "",
                    "missed_table_count_gold": "",
                    "false_positive_table_ids": "",
                    "continuation_expected": "",
                    "continuation_correct": "",
                    "comments": "",
                })
                prediction_rows.append({
                    "review_id": f"{stock}-{source['year']}-P{page_number:04d}",
                    "stock_code": stock,
                    "report_year": source["year"],
                    "physical_page": page_number,
                    "selected_by_governance_rule": page_number in document["selection"]["seed_pages"],
                    "detected_table_ids": [t["table_id"] for t in page_tables],
                    "detected_table_categories": [t["category"] for t in page_tables],
                    "logical_chain_ids": sorted({c["chain_id"] for c in page_chains}),
                    "image": image_rel.as_posix(),
                    "blind_image": blind_rel.as_posix(),
                })
                blind_sections.append(
                    f"<section><h2>{html.escape(source['company'])} · {stock} · {source['year']} · 物理页 {page_number}</h2>"
                    f"<p>review_id={stock}-{source['year']}-P{page_number:04d}；请只依据原页图像记录盲审标签。</p>"
                    f"<img src='{blind_rel.as_posix()}' loading='lazy'></section>"
                )
                rows_html = []
                if page_tables:
                    for chain in page_chains:
                        summary_rows = chain.get("rows", [])[:8]
                        values = "<br>".join(
                            html.escape(" | ".join(str(v) for v in row.get("values", [])))
                            for row in summary_rows
                        )
                        if len(chain.get("rows", [])) > len(summary_rows):
                            values += f"<br>… 共 {len(chain['rows'])} 行"
                        rows_html.append(
                            "<details><summary>"
                            + html.escape(chain.get("category", ""))
                            + f" · 链页 {html.escape(','.join(map(str, chain.get('pages', []))))} · {len(chain.get('rows', []))} 行</summary>"
                            + "<p><b>表头：</b>" + html.escape(" | ".join(chain.get("headers", []))) + "</p>"
                            + "<p>" + values + "</p></details>"
                        )
                else:
                    rows_html.append("<p class='warn'>解析器本页未检出表格；请特别核查是否漏检。</p>")
                html_sections.append(
                    f"<section><h2>{html.escape(source['company'])} · {stock} · {source['year']} · 物理页 {page_number}</h2>"
                    f"<p>review_id={stock}-{source['year']}-P{page_number:04d}；候选表格数={len(page_tables)}；该页属于关键词种子页={page_number in document['selection']['seed_pages']}</p>"
                    f"<img src='{image_rel.as_posix()}' loading='lazy'>"
                    + "".join(rows_html)
                    + "</section>"
                )
        finally:
            pdf.close()

        categories = Counter(chain.get("category", "") for chain in chains)
        category_totals.update(categories)
        all_rows = [row for chain in chains for row in chain.get("rows", [])]
        indexed_rows = sum(bool(row.get("committee_labels")) for row in all_rows)
        review_queue = load(run_dir / "review_queue.json")
        report = {
            "run": run_name,
            "stock_code": stock,
            "company": source["company"],
            "report_year": source["year"],
            "source_file": source["file"],
            "source_pdf_sha256": actual_hash,
            "source_pages": source["pages"],
            "parser_scope": document["selection"]["scope"],
            "keyword_seed_pages": document["selection"]["seed_pages"],
            "selected_pages": selected_pages,
            "parsed_pages": len(parsed_pages),
            "selected_pages_with_detected_tables": sum(bool(record["tables"]) for record in parsed_pages),
            "selected_pages_without_detected_tables": sum(not record["tables"] for record in parsed_pages),
            "table_regions": len(tables),
            "logical_chains": len(chains),
            "logical_rows": len(all_rows),
            "rows_with_committee_labels": indexed_rows,
            "chain_categories": dict(categories),
            "review_queue_items": len(review_queue),
            "model_calls": document["model_calls"],
            "accuracy_status": "not_measured_pending_independent_review",
        }
        audit["reports"].append(report)
        for key in ("source_pages", "keyword_seed_pages", "selected_pages", "parsed_pages",
                    "selected_pages_with_detected_tables", "selected_pages_without_detected_tables",
                    "table_regions", "logical_chains", "logical_rows", "rows_with_committee_labels",
                    "review_queue_items"):
            totals[key] += len(report[key]) if isinstance(report[key], list) else report[key]

    audit["aggregate"] = {**dict(totals), "chain_categories": dict(category_totals)}
    audit["review_packet"] = {
        "page_review_template_csv": "page_review_template.csv",
        "page_predictions_jsonl": "page_predictions.jsonl",
        "blind_review_html": "blind_review.html",
        "review_html": "review.html",
        "selected_pages_in_packet": len(page_review_rows),
        "blind_previews_have_prediction_boxes": False,
        "comparison_previews_have_red_prediction_boxes": True,
        "warning": "Reviewer labels are blank; complete page_review_template.csv from blind_review.html before inspecting page_predictions.jsonl or review.html.",
    }
    (out / "holdout_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "page_predictions.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in prediction_rows), encoding="utf-8"
    )
    with (out / "page_review_template.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(page_review_rows[0]))
        writer.writeheader()
        writer.writerows(page_review_rows)
    html_doc = "<!doctype html><html lang='zh-CN'><meta charset='utf-8'><title>解析器留出复核</title>"
    html_doc += "<style>body{font:15px/1.55 system-ui;margin:24px;background:#f5f7fa;color:#172b42}section{background:white;padding:16px;margin:20px 0;border:1px solid #ccd5df;border-radius:8px}img{max-width:100%;height:auto;border:1px solid #aaa}details{margin:8px 0;padding:8px;background:#f1f5f9}.warn{color:#9b1c1c;font-weight:700}</style>"
    html_doc += "<h1>年报表格解析留出复核包</h1><p>红框为解析器预测边界，便于比较；此页面不是盲审。先填写 page_review_template.csv 并保留独立复核者身份，再对照预测。当前没有任何人工标签，不能计算准确率、精确率或召回率。</p>"
    html_doc += f"<p>报告数：{len(audit['reports'])}；关键词及邻页：{len(page_review_rows)} 页；模型调用：0。</p>"
    html_doc += "".join(html_sections) + "</html>"
    (out / "review.html").write_text(html_doc, encoding="utf-8")
    blind_doc = "<!doctype html><html lang='zh-CN'><meta charset='utf-8'><title>年报表格解析留出盲审页</title>"
    blind_doc += "<style>body{font:15px/1.55 system-ui;margin:24px;background:#f5f7fa;color:#172b42}section{background:white;padding:16px;margin:20px 0;border:1px solid #ccd5df;border-radius:8px}img{max-width:100%;height:auto;border:1px solid #aaa}</style>"
    blind_doc += "<h1>年报表格解析留出盲审页</h1><p>此页只展示原始PDF页面图，不展示解析器边框、表格或类别预测。请先填写同目录page_review_template.csv；完成并封存标签后，再查看review.html与page_predictions.jsonl。</p>"
    blind_doc += "".join(blind_sections) + "</html>"
    (out / "blind_review.html").write_text(blind_doc, encoding="utf-8")
    print(json.dumps({"status": audit["status"], "reports": len(audit["reports"]),
                      "review_pages": len(page_review_rows), "output": str(out)}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=RUNS / "annual_table_holdout_review_20261028_01")
    parser.add_argument("--parser-version", default="annual_governance_tables_v1_4")
    parser.add_argument("--runs", nargs="+", default=DEFAULT_HOLDOUT_RUNS)
    args = parser.parse_args()
    build(args.out.resolve(), args.runs, args.parser_version)


if __name__ == "__main__":
    main()

