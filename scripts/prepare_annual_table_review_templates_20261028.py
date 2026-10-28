"""Add table-level and page-boundary annotation sheets to an existing packet.

The script exports blank review templates only. It does not assign labels or
compute accuracy from parser predictions.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "results" / "runs"
DEFAULT_PACKET = RUNS / "annual_table_holdout_review_v17_20261028_02"


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite existing annotation file: {path}")
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def prepare(packet: Path) -> dict:
    audit_path = packet / "holdout_audit.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    table_rows: list[dict] = []
    continuation_rows: list[dict] = []
    page_rows: list[dict] = []

    for report in audit["reports"]:
        document = json.loads((RUNS / report["run"] / "document.json").read_text(encoding="utf-8"))
        source = document["source"]
        stock = source["stock"]
        pages = sorted(document["selection"]["selected_pages"])
        tables_by_page: dict[int, list[dict]] = {page: [] for page in pages}
        chains_by_table = {}
        for chain in document["logical_tables"]:
            for table_id in chain["table_ids"]:
                chains_by_table[table_id] = chain
        for table in document["tables"]:
            tables_by_page.setdefault(table["page"], []).append(table)
            chain = chains_by_table.get(table["table_id"], {})
            table_rows.append({
                "row_kind": "prediction",
                "stock_code": stock,
                "report_year": source["year"],
                "source_pdf_sha256": document["source_pdf_sha256"],
                "physical_page": table["page"],
                "prediction_table_id": table["table_id"],
                "predicted_category": table.get("category", ""),
                "predicted_chain_id": chain.get("chain_id", ""),
                "predicted_chain_pages": json.dumps(chain.get("pages", []), ensure_ascii=False),
                "bbox_page_coordinates": json.dumps(table.get("bbox", []), ensure_ascii=False),
                "gold_table_id": "",
                "gold_category": "",
                "match_status": "",
                "independent_reviewer": "",
                "comments": "",
            })

        # One blank slot per selected page lets a reviewer add each missed table
        # without requiring predictions to define the gold table inventory.
        for page in pages:
            page_rows.append({
                "stock_code": stock,
                "report_year": source["year"],
                "source_pdf_sha256": document["source_pdf_sha256"],
                "physical_page": page,
                "page_review_complete": "",
                "gold_table_id": "",
                "gold_category": "",
                "missed_by_parser": "",
                "independent_reviewer": "",
                "comments": "",
            })

        decisions = {
            (decision["left_table_id"], decision["right_table_id"]): decision
            for decision in document.get("continuation_decisions", [])
        }
        for left_page, right_page in zip(pages, pages[1:]):
            if right_page != left_page + 1:
                continue
            left_tables = tables_by_page.get(left_page, [])
            right_tables = tables_by_page.get(right_page, [])
            if not left_tables and not right_tables:
                continue
            pairs = [(left, right) for left in left_tables for right in right_tables]
            if not pairs:
                pairs = [(left, None) for left in left_tables] or [(None, right) for right in right_tables]
            for left, right in pairs:
                left_id = left["table_id"] if left else ""
                right_id = right["table_id"] if right else ""
                decision = decisions.get((left_id, right_id), {})
                continuation_rows.append({
                    "stock_code": stock,
                    "report_year": source["year"],
                    "source_pdf_sha256": document["source_pdf_sha256"],
                    "left_page": left_page,
                    "right_page": right_page,
                    "left_prediction_table_id": left_id,
                    "right_prediction_table_id": right_id,
                    "parser_link_attempted": "yes" if decision else "no",
                    "parser_link_accepted": str(decision.get("accepted", "")).lower(),
                    "parser_link_reasons": json.dumps(decision.get("reasons", []), ensure_ascii=False),
                    "gold_continuation": "",
                    "gold_left_table_id": "",
                    "gold_right_table_id": "",
                    "independent_reviewer": "",
                    "comments": "",
                })

    write_csv(packet / "table_review_template.csv", table_rows, list(table_rows[0]))
    write_csv(packet / "missed_table_template.csv", page_rows, list(page_rows[0]))
    write_csv(packet / "continuation_review_template.csv", continuation_rows, list(continuation_rows[0]))
    instructions = """# 留出复核标注说明

## 盲审顺序

1. 先只看 `blind_review.html` 的原始PDF页图，填写 `page_review_template.csv`，记录每页是否存在本项目范围内的治理表格及漏检数量。对有预测表格的页，`false_positive_table_ids` 必须明确填 `none` 或分号分隔的误检表格ID。
2. 用 `missed_table_template.csv` 为每页填写 `page_review_complete=yes`；每个漏检表格新增一行，填 `gold_table_id`（人工编号）、`gold_category`、`missed_by_parser=yes`、复核者和备注。确认本页没有漏检时，在原空白行填写 `missed_by_parser=no` 和复核者；不完整复核保持 `page_review_complete` 为空。
3. 再查看 `review.html` 和 `page_predictions.jsonl`。在 `table_review_template.csv` 中逐条预测填写 `match_status=matched` 或 `false_positive`；匹配项填 `gold_table_id` 和人工类别。分类只能按页面证据确定；证据不足填 `unclassified_table`，不要猜测。
4. 在 `continuation_review_template.csv` 中逐条填写 `gold_continuation=yes/no`。若为续表，补填人工确认的左右表编号。即使解析器没有接受连接，也要依据原页独立判断。
5. 每位复核者单独复制并填写整套模板；不要把多人意见先合并成一个标签。解决分歧后另存裁决版，保留原始复核表。

## 可计算范围

- 表格检测：逐表 TP/FP/FN、Precision、Recall、F1；页级有/无表格的 Precision、Recall、F1 另算。
- 类别：对匹配表格计算逐类 Precision、Recall、F1，并将漏检表计为对应类别 FN。
- 跨页连接：根据 `gold_continuation` 与解析器是否接受连接计算 TP/FP/FN、Precision、Recall、F1。
- 指标仅代表这三份事后选择的报告、治理关键词页及相邻页，不代表随机样本、全报告任意表格或端到端RAG效果。

`score_annual_table_review.py` 只在表级和边界级标签完整且包含复核者身份时计分。空白模板不是结果；模型或作者自检不能标记为独立人工复核。跨页指标限于模板枚举的相邻页预测区域组合。
"""
    instructions_path = packet / "review_instructions.md"
    if instructions_path.exists():
        raise FileExistsError(f"Refusing to overwrite existing instructions: {instructions_path}")
    instructions_path.write_text(instructions, encoding="utf-8")
    return {"status": "templates_created_blank", "predicted_tables": len(table_rows),
            "review_pages": len(page_rows), "adjacent_boundary_pairs": len(continuation_rows),
            "output": str(packet)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, default=DEFAULT_PACKET)
    args = parser.parse_args()
    print(json.dumps(prepare(args.packet.resolve()), ensure_ascii=False))


if __name__ == "__main__":
    main()

