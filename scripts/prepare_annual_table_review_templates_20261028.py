"""Prepare a two-stage blind annotation packet for the table-parser holdout.

Gold tables and continuation links are annotated from original page images
before parser predictions are revealed. This script never creates labels.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "results" / "runs"
DEFAULT_PACKET = RUNS / "annual_table_holdout_review_v17_20261028_02"


def write_csv(path: Path, rows: list[dict], *, replace_existing: bool = False) -> None:
    if path.exists() and not replace_existing:
        raise FileExistsError(f"Choose a fresh packet or pass --replace-existing: {path}")
    if not rows:
        raise ValueError(f"Refusing to create empty annotation sheet: {path}")
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def prepare(packet: Path, *, replace_existing: bool = False) -> dict:
    audit = json.loads((packet / "holdout_audit.json").read_text(encoding="utf-8"))
    gold_tables: list[dict] = []
    predicted_tables: list[dict] = []
    gold_continuations: list[dict] = []
    accepted_continuations: list[dict] = []
    report_pages: dict[tuple[str, int], list[int]] = {}

    for report in audit["reports"]:
        document = json.loads((RUNS / report["run"] / "document.json").read_text(encoding="utf-8"))
        source = document["source"]
        stock = source["stock"]
        sha = document["source_pdf_sha256"]
        pages = sorted(document["selection"]["selected_pages"])
        report_pages[(stock, source["year"])] = pages

        # Blind gold inventory: one blank slot per page. Reviewers duplicate a
        # row for each additional table or mark gold_table_id=NONE explicitly.
        for page in pages:
            gold_tables.append({
                "stock_code": stock,
                "report_year": source["year"],
                "source_pdf_sha256": sha,
                "physical_page": page,
                "gold_table_id": "",
                "gold_category": "",
                "gold_bbox_normalized_xyxy": "",
                "review_complete": "",
                "independent_reviewer": "",
                "comments": "",
            })

        chains_by_table = {}
        for chain in document["logical_tables"]:
            for table_id in chain["table_ids"]:
                chains_by_table[table_id] = chain
        for table in document["tables"]:
            chain = chains_by_table.get(table["table_id"], {})
            x0, y0, x1, y1 = table["bbox"]
            width, height = table["page_width"], table["page_height"]
            normalized = [x0 / width, y0 / height, x1 / width, y1 / height]
            predicted_tables.append({
                "stock_code": stock,
                "report_year": source["year"],
                "source_pdf_sha256": sha,
                "physical_page": table["page"],
                "prediction_table_id": table["table_id"],
                "predicted_category": table.get("category", "unclassified_table"),
                "predicted_chain_id": chain.get("chain_id", ""),
                "predicted_chain_pages": json.dumps(chain.get("pages", []), ensure_ascii=False),
                "pred_bbox_normalized_xyxy": json.dumps(normalized),
                "gold_table_id": "",
                "match_status": "",
                "independent_reviewer": "",
                "comments": "",
            })

        # Blind gold continuation ledger: include every contiguous physical
        # boundary where both pages were in scope, even if neither had a table
        # prediction. Add rows for each true link, or a single NONE row.
        for left_page, right_page in zip(pages, pages[1:]):
            if right_page != left_page + 1:
                continue
            gold_continuations.append({
                "stock_code": stock,
                "report_year": source["year"],
                "source_pdf_sha256": sha,
                "left_page": left_page,
                "right_page": right_page,
                "gold_left_table_id": "",
                "gold_right_table_id": "",
                "gold_continuation": "",
                "review_complete": "",
                "independent_reviewer": "",
                "comments": "",
            })

        for decision in document.get("continuation_decisions", []):
            if decision.get("accepted"):
                accepted_continuations.append({
                    "stock_code": stock,
                    "report_year": source["year"],
                    "source_pdf_sha256": sha,
                    "left_page": decision["physical_pages"][0],
                    "right_page": decision["physical_pages"][1],
                    "left_prediction_table_id": decision["left_table_id"],
                    "right_prediction_table_id": decision["right_table_id"],
                    "accepted": True,
                })

    write_csv(packet / "gold_table_blind_template.csv", gold_tables, replace_existing=replace_existing)
    write_csv(packet / "prediction_gold_match_template.csv", predicted_tables, replace_existing=replace_existing)
    write_csv(packet / "gold_continuation_blind_template.csv", gold_continuations, replace_existing=replace_existing)
    manifest_path = packet / "accepted_continuation_predictions.jsonl"
    if manifest_path.exists() and not replace_existing:
        raise FileExistsError(f"Choose a fresh packet or pass --replace-existing: {manifest_path}")
    manifest_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in accepted_continuations), encoding="utf-8")

    instructions = """# 留出集双阶段盲审与计分说明

## 阶段一：只做盲标，不查看解析预测

只打开同目录 `blind_review.html`，不要打开 `review.html`、`page_predictions.jsonl`、`prediction_gold_match_template.csv` 或 `accepted_continuation_predictions.jsonl`。

1. 在 `gold_table_blind_template.csv` 为每页登记所有实际表格区域（包括治理关键词页邻页上出现的其他主题表格）。填写唯一人工 `gold_table_id`、人工类别及归一化框 `[x0,y0,x1,y1]`（范围0–1，按整页宽高归一化）。每页无表时将原行 `gold_table_id` 填 `NONE`、`review_complete=yes` 和复核者。若有表格，原行填写一个表格；每多一个表格复制一行并填写另一个ID。类别按可见表头/内容填写；无明确领域类别的真实表格标为 `other_table`，不要遗漏。
2. 在 `gold_continuation_blind_template.csv` 检查每个相邻物理页边界。无续表时填 `gold_continuation=no`；有一组续表时填 `yes` 并填写左右人工表格ID；同一边界有多组续表时复制行。每个边界必须有 `review_complete=yes` 和复核者。若某一页没有列入复核包，不能推断跨该页没有续表；本指标只覆盖模板中的相邻页边界。
3. 保存第一阶段副本并记录复核者、日期及文件哈希。第二位复核者应独立复制原始空模板完成同样工作。先合并/裁决盲标分歧，再查看预测。

## 阶段二：揭示预测并做一对一匹配

完成并封存阶段一后，才查看 `review.html` 和 `page_predictions.jsonl`。在 `prediction_gold_match_template.csv` 为每个预测表格填 `match_status=matched` 或 `false_positive`。匹配项填阶段一的 `gold_table_id`；误检不填金表ID。每个人工金表最多匹配一个预测表。类别使用阶段一封存的金表类别，不能因为解析器输出而改写。

## 计分与边界

`score_annual_table_review.py` 要求三张标签表完整、引用的金表ID有效且逐页误检/漏检清楚，然后计算页级和表级Precision、Recall、F1，逐类指标，以及跨页连接指标。跨页指标以预测器实际接受的边作为预测，和阶段一金续表边集合匹配；被漏检的表或边将计为FN。

每位复核者应在独立副本上分别计分并保留原表；分歧需另存裁决表。复核者字段只记录身份，不能由脚本证明其独立性。样本是事后选择的美的集团与科大讯飞2023/2024年报，共四份报告；仅覆盖治理关键词页及固定相邻页。它们曾用于先前RAG实验，因此不是全新独立时间迁移集，也不能代表随机样本、完整年报或端到端RAG效果。空白模板、作者/AI自查都不是独立人工指标。
"""
    instructions_path = packet / "review_instructions.md"
    if instructions_path.exists() and not replace_existing:
        raise FileExistsError(f"Choose a fresh packet or pass --replace-existing: {instructions_path}")
    instructions_path.write_text(instructions, encoding="utf-8")

    # The original page-level worksheet used post-unblinding fields. Replace it
    # with a lightweight page inventory index to avoid mixed blind/unblind use.
    page_index = []
    for (stock, year), pages in report_pages.items():
        report = next(r for r in audit["reports"] if r["stock_code"] == stock and r["report_year"] == year)
        for page in pages:
            page_index.append({"stock_code": stock, "report_year": report["report_year"],
                               "source_pdf_sha256": report["source_pdf_sha256"],
                               "physical_page": page,
                               "gold_table_present": "",
                               "review_complete": "",
                               "independent_reviewer": "",
                               "comments": ""})
    write_csv(packet / "page_review_template.csv", page_index, replace_existing=replace_existing)

    audit["review_packet"] = {
        "blind_review_html": "blind_review.html",
        "prediction_comparison_html": "review.html",
        "page_review_template_csv": "page_review_template.csv",
        "gold_table_blind_template_csv": "gold_table_blind_template.csv",
        "prediction_gold_match_template_csv": "prediction_gold_match_template.csv",
        "gold_continuation_blind_template_csv": "gold_continuation_blind_template.csv",
        "accepted_continuation_predictions_jsonl": "accepted_continuation_predictions.jsonl",
        "review_instructions": "review_instructions.md",
        "scope": "all visible table regions on the selected governance-keyword pages and fixed neighbors; blind gold inventory first",
        "pages": len(page_index),
        "predicted_table_regions": len(predicted_tables),
        "contiguous_physical_page_boundaries": len(gold_continuations),
        "accepted_parser_links": len(accepted_continuations),
        "labels_created": False,
        "accuracy_status": "not_measured_pending_independent_human_labels",
    }
    (packet / "holdout_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return {"status": "two_stage_blind_templates_created_blank",
            "reports": len(audit["reports"]), "pages": len(page_index),
            "predicted_tables": len(predicted_tables),
            "contiguous_page_boundaries": len(gold_continuations),
            "accepted_parser_links": len(accepted_continuations),
            "output": str(packet)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, default=DEFAULT_PACKET)
    parser.add_argument("--replace-existing", action="store_true",
                        help="Replace only the annotation files generated by this script")
    args = parser.parse_args()
    print(json.dumps(prepare(args.packet.resolve(), replace_existing=args.replace_existing), ensure_ascii=False))


if __name__ == "__main__":
    main()

