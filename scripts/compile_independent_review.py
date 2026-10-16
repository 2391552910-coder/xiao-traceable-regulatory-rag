"""校验、汇总已逐条写入的独立复核判断；不生成或推断相关性标签。"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data.benchmark import annotation_hash, corpus_hash, read_rounds, sha256_file
from src.data.clause_splitter import split_document
from src.data.knowledge_loader import load_documents

REVIEW = ROOT / "data/annotation/reviews/independent_20261013"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(name, rows, fields):
    with (REVIEW / name).open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_json(name, value):
    (REVIEW / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8")


def check_artifacts():
    """只读验证交付产物，避免通过重新汇总掩盖文件被改动。"""
    artifact = json.loads((REVIEW / "artifact_manifest.json").read_text())
    require(sha256_file(Path(__file__)) == artifact["compiler_sha256"], "汇总脚本已变化")
    for name, expected in artifact["files"].items():
        require(sha256_file(REVIEW / name) == expected, f"产物已变化: {name}")
    manifest = json.loads((REVIEW / "review_manifest.json").read_text())
    require(sha256_file(ROOT / manifest["source_path"]) == artifact["source_sha256"], "原候选表已变化")
    baseline = artifact["baseline_hashes"]
    require(corpus_hash(ROOT / "data/knowledge_base") == baseline["corpus_sha256"], "语料已变化")
    require(sha256_file(ROOT / "src/data/clause_splitter.py") == baseline["splitter_sha256"], "切分器已变化")
    require(sha256_file(ROOT / "data/annotation/retrieval_queries_gold.csv") == baseline["queries_sha256"], "原 gold 已变化")
    require(annotation_hash(ROOT / "data/annotation") == baseline["annotation_sha256"], "原标注已变化")
    print(f'通过：{len(artifact["files"])} 个冻结产物、原候选表、原 gold、原标注、语料与切分器哈希一致。')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="只读校验已生成产物的哈希，不改写文件")
    args = parser.parse_args()
    if args.check:
        check_artifacts()
        return
    manifest = json.loads((REVIEW / "review_manifest.json").read_text())
    frozen = json.loads((ROOT / "data/annotation/benchmark_manifest.json").read_text())
    source = ROOT / manifest["source_path"]
    require(sha256_file(source) == sha256_file(REVIEW / "input_blind.csv")
            == manifest["source_sha256"], "原始盲审输入已变化")
    require(sha256_file(REVIEW / "initial_decisions.json")
            == manifest["initial_decisions_sha256"], "首轮冻结判断已变化")
    kb = ROOT / "data/knowledge_base"
    hashes = {
        "corpus_sha256": corpus_hash(kb),
        "splitter_sha256": sha256_file(ROOT / "src/data/clause_splitter.py"),
        "queries_sha256": sha256_file(ROOT / "data/annotation/retrieval_queries_gold.csv"),
        "annotation_sha256": annotation_hash(ROOT / "data/annotation"),
    }
    require(hashes == frozen["hashes"], "原基准、语料或切分器与冻结版本不一致")
    docs = {d["doc_id"]: d for d in load_documents(kb)}
    chunks = {c.chunk_id: c for d in docs.values() for c in split_document(d)}
    rows = read_csv(REVIEW / "input_blind.csv")
    pairs = {(r["query_id"], r["chunk_id"]) for r in rows}
    require(len(pairs) == len(rows) == manifest["n_candidates"], "候选重复或数量不符")
    query_ids = sorted({q for q, _ in pairs})
    require(len(query_ids) == 40, "查询数不符")
    require({p.stem for p in REVIEW.glob("Q*.json")} == set(query_ids), "判断文件与查询不符")
    decisions = {}
    for qid in query_ids:
        d = json.loads((REVIEW / f"{qid}.json").read_text())
        require(set(d) == {cid for q, cid in pairs if q == qid}, f"{qid}: 判断缺漏")
        for cid, value in d.items():
            require(isinstance(value, list) and len(value) == 3
                    and type(value[0]) is int and value[0] in {-1, 0, 1, 2}
                    and value[1] in {"high", "medium", "low"}
                    and isinstance(value[2], str) and value[2].strip(), f"{qid}/{cid}: 格式错误")
            decisions[f"{qid}/{cid}"] = value
    initial = json.loads((REVIEW / "initial_decisions.json").read_text())
    require(initial.keys() == decisions.keys(), "首轮记录覆盖不符")

    # 只在加载完整冻结判断后读取历史标签。历史未标候选不能记为负例。
    old_gold = {r["query_id"]: r for r in read_csv(ROOT / "data/annotation/retrieval_queries_gold.csv")}
    require(set(old_gold) == set(query_ids), "历史查询集合不符")
    old_pools, old_positive = {}, {}
    for qid in query_ids:
        a = read_rounds(ROOT / "data/annotation/rounds", f"passA_{qid}*.csv")
        b = read_rounds(ROOT / "data/annotation/rounds", f"passB_{qid}*.csv")
        require(a.keys() == b.keys(), f"{qid}: 历史双轮候选不一致")
        old_pools[qid] = set(a)
        old_positive[qid] = set(old_gold[qid]["relevant_chunk_ids"].split(";"))
        require(old_positive[qid] <= old_pools[qid] <= {c for q, c in pairs if q == qid},
                f"{qid}: 历史候选或正例不在本轮候选池内")

    reviewed, comparison, differences, revisions, issues = [], [], [], [], []
    original_fields = [f for f in rows[0] if f not in {"human_label", "annotator", "comment"}]
    for r in rows:
        qid, cid = r["query_id"], r["chunk_id"]
        require((r["query"], r["dimension"]) == (old_gold[qid]["query"], old_gold[qid]["dimension"]),
                f"{qid}: 查询文本或维度改变")
        require(cid in chunks and chunks[cid].text == r["text"], f"{cid}: 文本与冻结语料不符")
        require(hashlib.sha256(r["text"].encode()).hexdigest() == r["text_sha256"], f"{cid}: 文本哈希不符")
        c = chunks[cid]
        require(r["doc_title"] == c.doc_title and r["doc_date"] == docs[c.doc_id]["date"]
                and r["source"] == c.source, f"{cid}: 文献元数据不符")
        for f in ("is_clause_heading", "truncated", "owner_clause_no"):
            require(r[f] == str(c.meta[f] if c.meta[f] is not None else ""), f"{cid}: {f} 不符")
        require(r["stored_clause_no"] == (c.clause_no or ""), f"{cid}: 条款编号不符")
        grade, confidence, reason = decisions[f"{qid}/{cid}"]
        binary = "" if grade == -1 else int(grade >= 1)
        direct = "" if grade == -1 else int(grade == 2)
        flags = []
        if r["truncated"] == "True":
            flags.append("truncated_at_length_limit")
        if r["stored_clause_no"] and r["is_clause_heading"] == "False":
            flags.append("inline_reference_split")
        if confidence != "high":
            flags.append("confidence_" + confidence)
        reviewed.append({**{f: r[f] for f in original_fields}, "doc_type": c.doc_type,
                         "review_grade": grade, "review_label": binary, "direct_label": direct,
                         "review_confidence": confidence, "review_reason": reason,
                         "quality_flags": ";".join(flags)})
        for flag in flags:
            issues.append({"query_id": qid, "chunk_id": cid, "review_grade": grade,
                           "issue": flag, "stored_clause_no": r["stored_clause_no"],
                           "owner_clause_no": r["owner_clause_no"], "review_reason": reason})
        judged = cid in old_pools[qid]
        prior = int(cid in old_positive[qid]) if judged else ""
        status = ("unresolved" if grade == -1 else
                  "new_relevant_candidate" if not judged and binary else
                  "new_irrelevant_candidate" if not judged else
                  "prior_positive_rejected" if prior and not binary else
                  "prior_negative_promoted" if not prior and binary else
                  "retained_positive" if prior else "retained_negative")
        item = {"query_id": qid, "chunk_id": cid, "previously_judged": judged,
                "previous_label": prior, "review_grade": grade, "review_label": binary,
                "comparison_status": status, "review_reason": reason}
        comparison.append(item)
        if status in {"prior_positive_rejected", "prior_negative_promoted", "new_relevant_candidate", "unresolved"}:
            differences.append(item)
        first = initial[f"{qid}/{cid}"]
        if first != [grade, confidence, reason]:
            revisions.append({"query_id": qid, "chunk_id": cid, "initial_grade": first[0],
                              "final_grade": grade, "initial_confidence": first[1],
                              "final_confidence": confidence, "initial_reason": first[2],
                              "final_reason": reason})
    write_csv("reviewed_candidates.csv", reviewed, list(reviewed[0]))
    write_csv("comparison_all_candidates.csv", comparison, list(comparison[0]))
    write_csv("differences_from_previous.csv", differences, list(comparison[0]))
    write_csv("review_revisions.csv", revisions,
              ["query_id", "chunk_id", "initial_grade", "final_grade", "initial_confidence",
               "final_confidence", "initial_reason", "final_reason"])
    write_csv("quality_issues.csv", issues,
              ["query_id", "chunk_id", "review_grade", "issue", "stored_clause_no", "owner_clause_no", "review_reason"])
    query_summary, broad, strict = [], [], []
    for qid in query_ids:
        rr = [r for r in reviewed if r["query_id"] == qid]
        counts = Counter(r["review_grade"] for r in rr)
        query_summary.append({"query_id": qid, "dimension": rr[0]["dimension"], "query": rr[0]["query"],
                              "n_candidates": len(rr), "n_direct": counts[2], "n_partial": counts[1],
                              "n_irrelevant": counts[0], "n_unresolved": counts[-1],
                              "n_previous_positive": len(old_positive[qid])})
        for target, threshold in ((broad, 1), (strict, 2)):
            ids = sorted(r["chunk_id"] for r in rr if r["review_grade"] >= threshold)
            require(bool(ids), f"{qid}: 导出的正例集合为空")
            target.append({"query_id": qid, "dimension": rr[0]["dimension"], "query": rr[0]["query"],
                           "relevant_chunk_ids": ";".join(ids), "n_relevant": len(ids),
                           "label_source": "independent_review"})
    write_csv("query_summary.csv", query_summary, list(query_summary[0]))
    write_csv("retrieval_queries_reviewed.csv", broad, list(broad[0]))
    write_csv("retrieval_queries_direct.csv", strict, list(strict[0]))
    (REVIEW / "qrels.tsv").write_text("".join(
        f'{r["query_id"]}\t0\t{r["chunk_id"]}\t{r["review_grade"]}\n'
        for r in reviewed if r["review_grade"] >= 0), encoding="utf-8")

    supplements = json.loads((REVIEW / "supplemental_decisions.json").read_text())
    extra = []
    for key, (grade, reason) in supplements.items():
        qid, cid = key.split("/")
        require(qid in query_ids and cid in chunks and (qid, cid) not in pairs,
                f"{key}: 补充证据必须在语料内、原候选池外")
        require(grade in {1, 2} and reason.strip(), f"{key}: 补充判断不完整")
        c = chunks[cid]
        extra.append({"query_id": qid, "query": old_gold[qid]["query"], "chunk_id": cid,
                      "doc_title": c.doc_title, "doc_date": docs[c.doc_id]["date"],
                      "source": c.source, "text": c.text,
                      "text_sha256": hashlib.sha256(c.text.encode()).hexdigest(),
                      "suggested_grade": grade, "reason": reason,
                      "included_in_main_review": False})
    write_csv("supplemental_candidates.csv", extra, list(extra[0]))
    summary = {"review_name": manifest["review_name"], "n_queries": len(query_ids),
               "n_candidates": len(reviewed), "grade_counts": dict(Counter(r["review_grade"] for r in reviewed)),
               "confidence_counts": dict(Counter(r["review_confidence"] for r in reviewed)),
               "n_broad_positive": sum(r["review_grade"] >= 1 for r in reviewed),
               "n_direct_positive": sum(r["review_grade"] == 2 for r in reviewed),
               "comparison_counts": dict(Counter(r["comparison_status"] for r in comparison)),
               "n_previous_judged": sum(len(v) for v in old_pools.values()),
               "n_previous_positive": sum(len(v) for v in old_positive.values()),
               "n_initial_to_final_revisions": len(revisions),
               "quality_flag_counts": dict(Counter(r["issue"] for r in issues)),
               "n_pairs_with_quality_flags": len({(r["query_id"], r["chunk_id"]) for r in issues}),
               "n_supplemental_candidates_not_in_main_review": len(extra),
               "status": "provisional", "usage": "development_only",
               "scope": "1049 supplied query-candidate pairs; supplements are separate and not exhaustive"}
    write_json("review_summary.json", summary)
    # 单独冻结本轮标签及产物；不覆盖旧 gold 或旧基准清单。
    tracked = sorted(p for p in REVIEW.iterdir() if p.is_file() and p.name != "artifact_manifest.json")
    write_json("artifact_manifest.json", {
        "review_name": manifest["review_name"], "schema_version": 1,
        "source_sha256": manifest["source_sha256"], "baseline_hashes": hashes,
        "compiler_sha256": sha256_file(Path(__file__)),
        "files": {p.name: sha256_file(p) for p in tracked},
    })
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
