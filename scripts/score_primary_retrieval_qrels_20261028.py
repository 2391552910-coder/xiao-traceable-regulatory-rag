"""Score the 60-question pooled retrieval review after independent human labels.

The candidate pool is the union of the two frozen Top-10 rankings. Recall is
therefore pool recall, not full-corpus recall. This script never invents labels.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import statistics
import sys
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
PACKET_DIR = ROOT / "outputs/8b416292-1179-49db-9a72-b105f57908c2"
EXPECTED_KEY_SHA256 = "0618d357437b57b01acba8e9da902453fa69a21a06ccc8cb3a4045e0a01bbfd8"
QUESTIONS_PATH = ROOT / "results/runs/paper_eval60_minimal_windows_20261020_02/评测集60题/questions.jsonl"
EXPECTED_QUESTIONS_SHA256 = "968cd746d0034f56d9c64b4cca24cbd802984f18a01a5110953ca628f14daf34"
NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "officeRel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "packageRel": "http://schemas.openxmlformats.org/package/2006/relationships",
}
REVIEW_HEADERS = {
    "盲审题码", "盲审条目码", "问题", "来源类型", "来源文档", "来源定位",
    "候选证据原文", "相关性等级（0–3）", "不确定（是/否）", "理由/备注",
}
KEY_HEADERS = {
    "评审者", "盲审题码", "盲审条目码", "实际题目ID", "片段ID",
    "合并检索名次", "双源检索名次", "合并来源类型", "双源来源类型",
    "文档ID", "文档标题", "来源SHA-256", "片段文本SHA-256",
}
K_VALUES = (1, 3, 5, 10)
BOOTSTRAP_SEED = 20261028
BOOTSTRAP_DRAWS = 20_000
RELEVANT_THRESHOLD = 2


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _column_index(cell_ref: str) -> int:
    letters = "".join(ch for ch in cell_ref if ch.isalpha())
    value = 0
    for char in letters.upper():
        value = value * 26 + ord(char) - ord("A") + 1
    return value - 1


def _numeric_or_text(value: str | None):
    if value is None:
        return ""
    try:
        number = float(value)
    except ValueError:
        return value
    return int(number) if number.is_integer() else number


def read_xlsx_sheet(path: Path, sheet_name: str) -> list[dict]:
    """Read a value-only XLSX sheet with the Python standard library."""
    with zipfile.ZipFile(path) as archive:
        damaged = archive.testzip()
        if damaged:
            raise ValueError(f"损坏的 XLSX ZIP 成员: {damaged}")
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        relation_targets = {r.attrib["Id"]: r.attrib["Target"] for r in rels}
        sheet_target = None
        for sheet in workbook.find("main:sheets", NS):
            if sheet.attrib.get("name") == sheet_name:
                relation_id = sheet.attrib[f"{{{NS['officeRel']}}}id"]
                sheet_target = relation_targets[relation_id]
                break
        if sheet_target is None:
            raise ValueError(f"缺少工作表 {sheet_name}: {path.name}")
        target = PurePosixPath(sheet_target.lstrip("/"))
        if target.parts[0] != "xl":
            target = PurePosixPath("xl") / target

        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            shared_strings = [
                "".join(t.text or "" for t in item.findall(".//main:t", NS))
                for item in root.findall("main:si", NS)
            ]

        sheet_root = ET.fromstring(archive.read(str(target)))
        raw_rows: list[dict[int, object]] = []
        for row in sheet_root.findall(".//main:sheetData/main:row", NS):
            values: dict[int, object] = {}
            for cell in row.findall("main:c", NS):
                if cell.find("main:f", NS) is not None:
                    raise ValueError(f"评审输入不允许公式单元格: {path.name}/{cell.attrib.get('r')}")
                col = _column_index(cell.attrib["r"])
                cell_type = cell.attrib.get("t")
                if cell_type == "inlineStr":
                    value = "".join(t.text or "" for t in cell.findall(".//main:t", NS))
                else:
                    v = cell.find("main:v", NS)
                    raw = None if v is None else v.text
                    if cell_type == "s" and raw is not None:
                        value = shared_strings[int(raw)]
                    elif cell_type == "b" and raw is not None:
                        value = raw == "1"
                    elif cell_type in {"str", "e"}:
                        value = raw or ""
                    else:
                        value = _numeric_or_text(raw)
                values[col] = value
            raw_rows.append(values)

    if not raw_rows:
        raise ValueError(f"工作表为空: {path.name}/{sheet_name}")
    header_row = raw_rows[0]
    last_col = max(header_row, default=-1)
    headers = [str(header_row.get(i, "")).strip() for i in range(last_col + 1)]
    if not headers or any(not h for h in headers) or len(headers) != len(set(headers)):
        raise ValueError(f"表头为空或重复: {path.name}/{sheet_name}")
    records = []
    for row in raw_rows[1:]:
        record = {headers[i]: row.get(i, "") for i in range(len(headers))}
        if any(v not in ("", None) for v in record.values()):
            records.append(record)
    return records


def _grade(value, label: str, allow_blank: bool = True):
    if value in ("", None):
        if allow_blank:
            return None
        raise ValueError(f"{label} 不能为空")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or int(value) != value:
        raise ValueError(f"{label} 必须是0–3整数")
    value = int(value)
    if value not in {0, 1, 2, 3}:
        raise ValueError(f"{label} 必须是0–3整数")
    return value


def _rank(value, label: str):
    if value in ("", None):
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or int(value) != value:
        raise ValueError(f"{label} 不是整数名次")
    value = int(value)
    if not 1 <= value <= 10:
        raise ValueError(f"{label} 超出1–10名次")
    return value


def _write_csv(path: Path, rows: list[dict], headers: list[str] | None = None,
               delimiter: str = ","):
    if headers is None:
        headers = list(rows[0]) if rows else []
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers, extrasaction="raise", delimiter=delimiter)
        writer.writeheader()
        writer.writerows(rows)


def _percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * p
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[low]
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _agreement(pairs: list[tuple[int, int]]) -> dict:
    n = len(pairs)
    if not n:
        return {"n_paired_items": 0, "exact_agreement": None,
                "cohen_kappa": None, "quadratic_weighted_kappa": None}
    labels = (0, 1, 2, 3)
    a_counts, b_counts = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    exact = sum(a == b for a, b in pairs) / n
    expected = sum(a_counts[g] * b_counts[g] for g in labels) / (n * n)
    kappa = (exact - expected) / (1 - expected) if expected < 1 else None
    denom = (len(labels) - 1) ** 2
    observed_disagreement = sum(((a - b) ** 2) / denom for a, b in pairs) / n
    expected_disagreement = sum(
        a_counts[a] * b_counts[b] * ((a - b) ** 2) / denom
        for a in labels for b in labels
    ) / (n * n)
    weighted = (1 - observed_disagreement / expected_disagreement
                if expected_disagreement > 0 else None)
    return {"n_paired_items": n, "exact_agreement": exact,
            "cohen_kappa": kappa,
            "quadratic_weighted_kappa": weighted}


def _metric(ordered_grades: list[int], pool_grades: list[int], k: int) -> dict:
    relevant_pool = sum(g >= RELEVANT_THRESHOLD for g in pool_grades)
    selected = ordered_grades[:k]
    p_at_k = sum(g >= RELEVANT_THRESHOLD for g in selected) / k
    recall = (sum(g >= RELEVANT_THRESHOLD for g in selected) / relevant_pool
              if relevant_pool else None)
    gain = lambda grade: (2 ** grade) - 1
    dcg = sum(gain(g) / math.log2(rank + 1)
              for rank, g in enumerate(selected, start=1))
    ideal = sorted(pool_grades, reverse=True)[:k]
    idcg = sum(gain(g) / math.log2(rank + 1)
               for rank, g in enumerate(ideal, start=1))
    ndcg = dcg / idcg if idcg else None
    return {"precision_at_k": p_at_k, "pool_recall_at_k": recall,
            "graded_ndcg_at_k": ndcg,
            "relevant_candidates_in_pool": relevant_pool}


def _cluster_intervals(per_query: dict, company_by_qid: dict,
                       draws: int = BOOTSTRAP_DRAWS) -> list[dict]:
    companies = sorted(set(company_by_qid.values()))
    grouped = defaultdict(list)
    for qid, methods in per_query.items():
        grouped[company_by_qid[qid]].append((qid, methods))
    metrics = sorted({metric for methods in per_query.values()
                      for method_by_k in methods.values()
                      for metrics_at_k in method_by_k.values()
                      for metric in metrics_at_k})
    output = []
    rng = random.Random(BOOTSTRAP_SEED)
    for k in K_VALUES:
        for metric in metrics:
            company_values = {}
            deltas = {}
            eligible = []
            for company in companies:
                rows = grouped[company]
                merged_values = [r[1]["merged"][k][metric] for r in rows
                                 if r[1]["merged"][k][metric] is not None]
                dual_values = [r[1]["dual"][k][metric] for r in rows
                               if r[1]["dual"][k][metric] is not None]
                paired = [(r[1]["merged"][k][metric], r[1]["dual"][k][metric])
                          for r in rows if r[1]["merged"][k][metric] is not None
                          and r[1]["dual"][k][metric] is not None]
                if merged_values:
                    company_values.setdefault("merged", {})[company] = statistics.mean(merged_values)
                if dual_values:
                    company_values.setdefault("dual", {})[company] = statistics.mean(dual_values)
                if paired:
                    eligible.append(company)
                    deltas[company] = statistics.mean(d - m for m, d in paired)
            record = {"k": k, "metric": metric, "bootstrap_unit": "company",
                      "seed": BOOTSTRAP_SEED, "draws": draws,
                      "companies_total": len(companies), "paired_companies": len(eligible)}
            for method in ("merged", "dual"):
                vals_by_company = company_values.get(method, {})
                selected = [c for c in companies if c in vals_by_company]
                samples = []
                if selected:
                    base = statistics.mean(vals_by_company.values())
                    for _ in range(draws):
                        samples.append(statistics.mean(
                            vals_by_company[rng.choice(selected)] for _ in selected))
                    record[f"{method}_company_macro_mean"] = base
                    record[f"{method}_ci95_low"] = _percentile(samples, .025)
                    record[f"{method}_ci95_high"] = _percentile(samples, .975)
                else:
                    record[f"{method}_company_macro_mean"] = None
                    record[f"{method}_ci95_low"] = None
                    record[f"{method}_ci95_high"] = None
            if eligible:
                base_delta = statistics.mean(deltas[c] for c in eligible)
                delta_samples = [statistics.mean(
                    deltas[rng.choice(eligible)] for _ in eligible)
                    for _ in range(draws)]
                record["dual_minus_merged_company_macro"] = base_delta
                record["delta_ci95_low"] = _percentile(delta_samples, .025)
                record["delta_ci95_high"] = _percentile(delta_samples, .975)
            else:
                record["dual_minus_merged_company_macro"] = None
                record["delta_ci95_low"] = None
                record["delta_ci95_high"] = None
            output.append(record)
    return output


def score(args) -> dict:
    reviewer_paths = {"A": Path(args.reviewer_a), "B": Path(args.reviewer_b)}
    key_path = Path(args.coordinator_key)
    for label, path in {**reviewer_paths, "key": key_path}.items():
        if not path.is_file():
            raise ValueError(f"找不到{label}输入文件: {path}")
    if sha256_file(key_path) != EXPECTED_KEY_SHA256:
        raise ValueError("协调密钥文件SHA-256变化。请使用原始未编辑的密钥文件。")
    if sha256_file(QUESTIONS_PATH) != EXPECTED_QUESTIONS_SHA256:
        raise ValueError("冻结问题集SHA-256变化，拒绝按未知题集计算。")

    key_rows = read_xlsx_sheet(key_path, "协调密钥")
    if len(key_rows) != 1666 or not KEY_HEADERS <= set(key_rows[0]):
        raise ValueError("协调密钥的行数或列结构不符")
    key_by_reviewer_item = {}
    key_by_qid_chunk = {}
    rank_sets = {"merged": defaultdict(set), "dual": defaultdict(set)}
    for row in key_rows:
        reviewer = str(row["评审者"])
        item = str(row["盲审条目码"])
        qid, chunk_id = str(row["实际题目ID"]), str(row["片段ID"])
        key = (reviewer, item)
        if reviewer not in reviewer_paths or key in key_by_reviewer_item:
            raise ValueError("协调密钥包含未知评审者或重复盲审条目码")
        rec = dict(row)
        rec["_qid"] = qid
        rec["_chunk_id"] = chunk_id
        rec["_pair"] = (qid, chunk_id)
        for method, col in (("merged", "合并检索名次"), ("dual", "双源检索名次")):
            rank = _rank(row[col], f"{qid}/{method}")
            rec[f"_{method}_rank"] = rank
            role_col = "合并来源类型" if method == "merged" else "双源来源类型"
            role = str(row[role_col] or "")
            if (rank is None) != (not role):
                raise ValueError(f"{qid}/{chunk_id}: 名次与来源类型不一致")
            if rank is not None:
                rank_sets[method][qid].add(rank)
        key_by_reviewer_item[key] = rec
        if reviewer == "A":
            if (qid, chunk_id) in key_by_qid_chunk:
                raise ValueError("协调密钥含重复问题—片段映射")
            key_by_qid_chunk[(qid, chunk_id)] = rec
    if {r for r, _ in key_by_reviewer_item} != {"A", "B"}:
        raise ValueError("协调密钥缺少A或B评审者")
    qids = {qid for qid, _ in key_by_qid_chunk}
    if len(qids) != 60 or len(key_by_qid_chunk) != 833:
        raise ValueError("协调密钥不是冻结的60题/833项候选池")
    for method in ("merged", "dual"):
        if set(rank_sets[method]) != qids or any(ranks != set(range(1, 11))
                                                  for ranks in rank_sets[method].values()):
            raise ValueError(f"{method}每题必须恰有连续Top-10名次")

    questions = {}
    for line in QUESTIONS_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip():
            obj = json.loads(line)
            questions[obj["question_id"]] = obj
    if set(questions) != qids:
        raise ValueError("冻结问题集ID与协调密钥不一致")
    company_by_qid = {qid: str(questions[qid]["stock_code"]).upper() for qid in qids}
    if len(set(company_by_qid.values())) != 20:
        raise ValueError("冻结问题集公司数不符")

    reviews = {}
    incomplete = []
    for reviewer, path in reviewer_paths.items():
        rows = read_xlsx_sheet(path, "评审")
        if len(rows) != 833 or not REVIEW_HEADERS <= set(rows[0]):
            raise ValueError(f"评审者{reviewer}的行数或列结构不符")
        indexed = {}
        for row in rows:
            item = str(row["盲审条目码"])
            map_key = (reviewer, item)
            if item in indexed or map_key not in key_by_reviewer_item:
                raise ValueError(f"评审者{reviewer}有重复或未知条目码: {item}")
            key = key_by_reviewer_item[map_key]
            qid, chunk_id = key["_qid"], key["_chunk_id"]
            pair = (qid, chunk_id)
            role = "年报" if str(key["合并来源类型"] or key["双源来源类型"]) == "annual_report" else "法规"
            expected = {
                "盲审题码": str(key["盲审题码"]),
                "问题": questions[qid]["query"],
                "来源类型": role,
                "来源文档": str(key["文档标题"]),
            }
            for field, expected_value in expected.items():
                if str(row[field]) != expected_value:
                    raise ValueError(f"评审者{reviewer}/{item}的{field}被改动")
            text = str(row["候选证据原文"])
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
            if digest != str(key["片段文本SHA-256"]):
                raise ValueError(f"评审者{reviewer}/{item}候选原文哈希不符")
            if item != str(key["盲审条目码"]) or pair not in key_by_qid_chunk:
                raise ValueError("盲审映射异常")
            grade = _grade(row["相关性等级（0–3）"], f"{reviewer}/{item}")
            uncertain = str(row["不确定（是/否）"] or "")
            if uncertain not in {"", "是", "否"}:
                raise ValueError(f"{reviewer}/{item}的不确定字段只能是是/否")
            comment = str(row["理由/备注"] or "").strip()
            if grade is None or uncertain == "" or (uncertain == "是" and not comment):
                incomplete.append({"reviewer": reviewer, "question_id": qid,
                                   "chunk_id": chunk_id, "item_id": item,
                                   "grade_missing": grade is None,
                                   "uncertainty_missing": uncertain == "",
                                   "uncertain_without_comment": uncertain == "是" and not comment})
            indexed[item] = {"pair": pair, "grade": grade, "uncertain": uncertain,
                             "comment": comment, "location": str(row["来源定位"] or "")}
        expected_items = {item for r, item in key_by_reviewer_item if r == reviewer}
        if set(indexed) != expected_items:
            raise ValueError(f"评审者{reviewer}的条目集合不完整")
        reviews[reviewer] = indexed

    paired = []
    conflicts = []
    for pair, key in key_by_qid_chunk.items():
        item_a, item_b = str(key_by_reviewer_item[("A", _find_item(key_rows, "A", pair))]["盲审条目码"]), \
                         str(key_by_reviewer_item[("B", _find_item(key_rows, "B", pair))]["盲审条目码"])
        a, b = reviews["A"][item_a], reviews["B"][item_b]
        if a["grade"] is not None and b["grade"] is not None:
            paired.append((a["grade"], b["grade"]))
        if a["grade"] is not None and b["grade"] is not None and \
                (a["grade"] != b["grade"] or a["uncertain"] == "是" or b["uncertain"] == "是"):
            conflicts.append({"question_id": pair[0], "chunk_id": pair[1],
                              "blind_item_a": item_a, "grade_a": a["grade"],
                              "uncertain_a": a["uncertain"], "comment_a": a["comment"],
                              "blind_item_b": item_b, "grade_b": b["grade"],
                              "uncertain_b": b["uncertain"], "comment_b": b["comment"],
                              "adjudicated_grade": "", "adjudication_rationale": ""})

    out_dir = Path(args.output_dir)
    if out_dir.exists() and any(out_dir.iterdir()):
        raise ValueError(f"输出目录非空，为避免覆盖请另选目录: {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)
    agreement = _agreement(paired)
    report = {
        "schema_version": 1,
        "review_status": "awaiting_reviews" if len(incomplete) == 1666 else "incomplete_reviews",
        "n_questions": 60, "n_companies": 20,
        "n_pooled_query_chunk_pairs": 833, "n_distinct_chunks": 460,
        "n_rows_reviewer_a": len(reviews["A"]), "n_rows_reviewer_b": len(reviews["B"]),
        "n_incomplete_reviewer_rows": len(incomplete),
        "n_paired_grades_available": len(paired),
        "n_adjudication_required": len(conflicts),
        "agreement": agreement,
        "relevance_threshold": RELEVANT_THRESHOLD,
        "recall_scope": "judged union of the frozen merged and dual Top-10 pools; not full-corpus recall",
        "retrieval_metrics_computed": False,
        "reason": "Both independent reviews must be complete; disagreements or uncertain grades require coordinator adjudication.",
        "input_sha256": {"reviewer_a": sha256_file(reviewer_paths["A"]),
                         "reviewer_b": sha256_file(reviewer_paths["B"]),
                         "coordinator_key": sha256_file(key_path),
                         "questions": sha256_file(QUESTIONS_PATH)},
    }
    if incomplete:
        report["review_status"] = "awaiting_reviews" if len(paired) == 0 else "incomplete_reviews"
        _write_csv(out_dir / "incomplete_items.csv", incomplete)
        (out_dir / "review_status.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return report

    _write_csv(out_dir / "adjudication.csv", conflicts,
               ["question_id", "chunk_id", "blind_item_a", "grade_a", "uncertain_a", "comment_a",
                "blind_item_b", "grade_b", "uncertain_b", "comment_b", "adjudicated_grade", "adjudication_rationale"])
    adjudication_path = Path(args.adjudication) if args.adjudication else None
    consensus = {}
    for pair, key in key_by_qid_chunk.items():
        ida = _find_item(key_rows, "A", pair)
        idb = _find_item(key_rows, "B", pair)
        a, b = reviews["A"][ida], reviews["B"][idb]
        consensus[pair] = a["grade"] if a["grade"] == b["grade"] else None

    if conflicts:
        if adjudication_path is None or not adjudication_path.is_file():
            report["review_status"] = "needs_adjudication"
            report["reason"] = "All 833 pairs are rated, but the disagreement/uncertainty list must be completed by the coordinator."
            (out_dir / "review_status.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            return report
        adjudicated_rows = []
        with adjudication_path.open(encoding="utf-8-sig", newline="") as f:
            adjudicated_rows = list(csv.DictReader(f))
        conflict_pairs = {(x["question_id"], x["chunk_id"]) for x in conflicts}
        supplied = {}
        for row in adjudicated_rows:
            pair = (row.get("question_id", ""), row.get("chunk_id", ""))
            if pair not in conflict_pairs or pair in supplied:
                raise ValueError("仲裁文件包含非争议项或重复项")
            grade = _grade(_numeric_or_text(row.get("adjudicated_grade")), f"仲裁 {pair}", allow_blank=False)
            rationale = (row.get("adjudication_rationale") or "").strip()
            if not rationale:
                raise ValueError(f"仲裁理由不能为空: {pair}")
            supplied[pair] = grade
        if supplied.keys() != conflict_pairs:
            report["review_status"] = "needs_adjudication"
            report["n_unresolved_adjudications"] = len(conflict_pairs - supplied.keys())
            report["reason"] = "仲裁表未填写全部分歧/不确定项。"
            (out_dir / "review_status.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            return report
        consensus.update(supplied)
    elif adjudication_path is not None:
        with adjudication_path.open(encoding="utf-8-sig", newline="") as f:
            extra = list(csv.DictReader(f))
        if extra:
            raise ValueError("没有待仲裁项，仲裁表却包含记录")

    if any(v is None for v in consensus.values()) or len(consensus) != 833:
        raise ValueError("一致/仲裁标签不完整，拒绝计算检索指标")

    ranked = {qid: {"merged": {}, "dual": {}} for qid in qids}
    pool = defaultdict(list)
    for (qid, chunk_id), grade in consensus.items():
        key = key_by_qid_chunk[(qid, chunk_id)]
        pool[qid].append(grade)
        if key["_merged_rank"] is not None:
            ranked[qid]["merged"][key["_merged_rank"]] = grade
        if key["_dual_rank"] is not None:
            ranked[qid]["dual"][key["_dual_rank"]] = grade

    per_query = {}
    details = []
    for qid in sorted(qids):
        per_query[qid] = {"merged": {}, "dual": {}}
        for method in ("merged", "dual"):
            grades = [ranked[qid][method][rank] for rank in range(1, 11)]
            for k in K_VALUES:
                metrics = _metric(grades, pool[qid], k)
                per_query[qid][method][k] = metrics
                details.append({"question_id": qid, "company": company_by_qid[qid],
                                "method": method, "k": k, **metrics})

    summaries = []
    for method in ("merged", "dual"):
        for k in K_VALUES:
            for metric in ("precision_at_k", "pool_recall_at_k", "graded_ndcg_at_k"):
                values = [per_query[qid][method][k][metric] for qid in qids
                          if per_query[qid][method][k][metric] is not None]
                summaries.append({"method": method, "k": k, "metric": metric,
                                  "macro_mean": statistics.mean(values) if values else None,
                                  "n_queries_defined": len(values), "n_queries_total": len(qids)})

    bootstrap = _cluster_intervals(per_query, company_by_qid)
    qrels_rows = [{"query_id": qid, "iteration": 0, "chunk_id": cid, "grade": grade}
                  for (qid, cid), grade in sorted(consensus.items())]
    _write_csv(out_dir / "per_question_metrics.csv", details)
    _write_csv(out_dir / "metric_summary.csv", summaries)
    _write_csv(out_dir / "company_cluster_bootstrap.csv", bootstrap)
    _write_csv(out_dir / "adjudicated_pool_qrels.tsv", qrels_rows,
               ["query_id", "iteration", "chunk_id", "grade"], delimiter="\t")
    report.update({"review_status": "scored", "retrieval_metrics_computed": True,
                   "n_adjudicated_pool_labels": len(consensus),
                   "binary_relevance_rule": "grade >= 2",
                   "graded_ndcg_gain": "2^grade - 1; grade is 0–3",
                   "macro_aggregation": "question-macro; pool recall and nDCG omit queries with no positive judged gain and report their denominators",
                   "uncertainty": "20,000 paired company-cluster bootstrap replicates; seed 20261028",
                   "metric_files": ["per_question_metrics.csv", "metric_summary.csv",
                                    "company_cluster_bootstrap.csv", "adjudicated_pool_qrels.tsv"]})
    report["reason"] = "Metrics cover the union of the frozen two Top-10 lists only; they do not estimate full-corpus recall."
    (out_dir / "review_status.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def _find_item(key_rows: list[dict], reviewer: str, pair: tuple[str, str]) -> str:
    matches = [str(r["盲审条目码"]) for r in key_rows
               if str(r["评审者"]) == reviewer and
               (str(r["实际题目ID"]), str(r["片段ID"])) == pair]
    if len(matches) != 1:
        raise ValueError(f"协调密钥问题—片段映射不是唯一项: {reviewer}/{pair}")
    return matches[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reviewer-a", default=str(PACKET_DIR / "检索相关性盲审_A_主实验60题.xlsx"))
    parser.add_argument("--reviewer-b", default=str(PACKET_DIR / "检索相关性盲审_B_主实验60题.xlsx"))
    parser.add_argument("--coordinator-key", default=str(PACKET_DIR / "检索相关性盲审_协调者密钥_勿发评审者.xlsx"))
    parser.add_argument("--adjudication", help="协调者完成的CSV，列为question_id,chunk_id,adjudicated_grade,adjudication_rationale")
    parser.add_argument("--output-dir", required=True, help="必须是空目录；已有文件不会覆盖")
    args = parser.parse_args()
    try:
        report = score(args)
    except (OSError, ValueError, KeyError, ET.ParseError, zipfile.BadZipFile) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

