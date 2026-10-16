"""评测可信度回归：无效标注、版本漂移、跨切分匹配与重复证据。"""
import csv
import hashlib
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import load_config
from src.data.benchmark import export_review, load_benchmark
from src.data.clause_splitter import Chunk, split_document
from src.metrics.benchmark_eval import (
    bootstrap_intervals, ensure_new_output, sanitized, score_evidence,
)


def fixture_benchmark(tmp_path, **row_overrides):
    kb = tmp_path / "kb"
    kb.mkdir()
    (kb / "doc.txt").write_text(
        "@DOC_ID: DOC001\n@TITLE: 规则\n@TYPE: regulation\n@SOURCE: 测试\n---\n第一条 年报须披露。\n第二条 不得造假。", encoding="utf-8")
    query_file = tmp_path / "queries.csv"
    row = {"query_id": "Q01", "dimension": "D1", "query": "年报披露",
           "relevant_chunk_ids": "DOC001-C001", "n_relevant": "1",
           "label_source": "ai_dual_pass_adjudicated", **row_overrides}
    with query_file.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)
    cfg = {"knowledge_base": {"path": str(kb)}, "evaluation": {
        "queries_path": str(query_file), "manifest_path": str(tmp_path / "manifest.json")}}
    return cfg


@pytest.mark.parametrize("overrides", [
    {"relevant_chunk_ids": "DOC999-C001"}, {"relevant_chunk_ids": ""},
    {"relevant_chunk_ids": "DOC001-C001;DOC001-C001"}, {"n_relevant": "2"},
    {"dimension": "unknown"}, {"query_id": ""}, {"query": " "},
])
def test_invalid_labels_fail_before_evaluation(tmp_path, overrides):
    cfg = fixture_benchmark(tmp_path, **overrides)
    with pytest.raises(ValueError):
        load_benchmark(cfg, verify_manifest=False)


def test_frozen_corpus_detects_silent_edits(tmp_path):
    cfg = fixture_benchmark(tmp_path)
    benchmark = load_benchmark(cfg, verify_manifest=False)
    manifest = {"schema_version": 1, "benchmark_id": "fixture-v1", "hashes": benchmark.hashes}
    Path(cfg["evaluation"]["manifest_path"]).write_text(json.dumps(manifest))
    assert load_benchmark(cfg).manifest["benchmark_id"] == "fixture-v1"
    doc = Path(cfg["knowledge_base"]["path"]) / "doc.txt"
    doc.write_text(doc.read_text() + "\n新增条文")
    with pytest.raises(ValueError, match="冻结版本"):
        load_benchmark(cfg)


def test_duplicate_queries_rejected(tmp_path):
    cfg = fixture_benchmark(tmp_path)
    path = Path(cfg["evaluation"]["queries_path"])
    lines = path.read_text().splitlines()
    path.write_text("\n".join(lines + [lines[1]]) + "\n")
    with pytest.raises(ValueError, match="重复 query_id"):
        load_benchmark(cfg, verify_manifest=False)


def make_chunk(cid, start, end, doc_id="DOC001"):
    return Chunk(cid, doc_id, "规则", "regulation", "测试", None, "证据",
                 meta={"source_start": start, "source_end": end})


def test_window_hits_same_evidence_despite_different_id():
    gold = make_chunk("DOC001-C001", 0, 100)
    window = make_chunk("DOC001-W001", 0, 60)
    score = score_evidence([(window, 1)], {gold.chunk_id}, {gold.chunk_id: gold}, 5)
    assert score["recall@5"] == score["mrr"] == score["ndcg@5"] == 1


def test_overlap_not_double_counted_and_coverage_is_accumulated():
    gold = make_chunk("DOC001-C001", 0, 100)
    w1 = make_chunk("DOC001-W001", 0, 30)
    repeated = make_chunk("DOC001-W002", 0, 30)
    w2 = make_chunk("DOC001-W003", 30, 60)
    kwargs = ({gold.chunk_id}, {gold.chunk_id: gold}, 5)
    assert score_evidence([(w1, 1), (repeated, 1)], *kwargs)["recall@5"] == 0
    score = score_evidence([(w1, 1), (w2, 1)], *kwargs)
    assert score["recall@5"] == 1
    assert score["mrr"] == .5


def test_window_cannot_match_a_different_document():
    gold = make_chunk("DOC001-C001", 0, 100)
    other = make_chunk("DOC002-W001", 0, 100, "DOC002")
    assert score_evidence([(other, 1)], {gold.chunk_id}, {gold.chunk_id: gold}, 5)["recall@5"] == 0


def test_duplicate_evidence_does_not_inflate_ndcg():
    gold = make_chunk("DOC001-C001", 0, 100)
    hits = [(make_chunk("DOC001-W001", 0, 100), 1),
            (make_chunk("DOC001-W002", 0, 100), 1)]
    assert score_evidence(hits, {gold.chunk_id}, {gold.chunk_id: gold}, 5)["ndcg@5"] == 1


def test_inline_reference_audited_without_reindexing():
    doc = {"doc_id": "DOC001", "title": "规则", "doc_type": "regulation", "source": "测试",
           "text": "第一条 依照第二条办理。\n第二条 禁止造假。"}
    chunks = split_document(doc)
    assert [(c.chunk_id, c.clause_no, c.text) for c in chunks] == [
        ("DOC001-C001", "第一条", "第一条依照"),
        ("DOC001-C002", "第二条", "第二条办理。"),
        ("DOC001-C003", "第二条", "第二条禁止造假。")]
    assert not chunks[1].meta["is_clause_heading"]
    assert chunks[1].meta["owner_clause_no"] == "第一条"
    assert doc["text"][chunks[1].meta["source_start"]:chunks[1].meta["source_end"]] == "第二条办理。"


def test_span_tracks_only_visible_truncated_text():
    doc = {"doc_id": "DOC001", "title": "规则", "doc_type": "regulation", "source": "测试",
           "text": "第一条 " + "甲" * 3000}
    chunk = split_document(doc)[0]
    assert len(chunk.text) == 2000
    assert chunk.meta["truncated"]
    assert chunk.meta["source_end"] < chunk.meta["raw_end"]
    assert chunk.meta["source_end"] == 2001  # 源文本包括存储文本省略的一个空格


def test_paired_bootstrap_aligns_queries_and_is_deterministic():
    rows = [{"config": name, "query_id": qid, "recall@5": score, "mrr": score,
             "ndcg@5": score, "hit@5": score}
            for name, values in [("base", [("Q2", 0), ("Q1", 1)]),
                                 ("same", [("Q1", 1), ("Q2", 0)])] for qid, score in values]
    result = bootstrap_intervals(rows, 5, samples=100)
    assert result == bootstrap_intervals(rows, 5, samples=100)
    assert all(r["delta_ci95_low"] == r["delta_ci95_high"] == 0 for r in result)


def test_existing_outputs_not_overwritten(tmp_path):
    output = tmp_path / "eval.csv"
    output.with_name("eval_detail.csv").write_text("existing")
    with pytest.raises(ValueError, match="输出已存在"):
        ensure_new_output(output)


def test_run_config_redacts_nested_credentials():
    assert sanitized({"retrieval": {"embedding_api_key": "secret", "model": "test"}}) == {
        "retrieval": {"embedding_api_key": "[REDACTED]", "model": "test"}}


def test_repository_gold_audit_and_blind_review(tmp_path):
    benchmark = load_benchmark(load_config())
    audit = benchmark.audit()
    assert audit["n_queries"] == 40 and audit["n_positive_pairs"] == 226
    assert audit["status"] == "provisional" and audit["frozen"]
    assert any("inline_reference_used_as_heading" in issue["flags"] for issue in audit["structural_issues"])
    consistency = audit["annotation_consistency"]
    assert consistency["n_undefined_kappa"] == 2
    assert all(r["gold_matches_rounds"] and not r["unresolved_disputes"] for r in consistency["per_query"])
    path = tmp_path / "review.csv"
    assert export_review(benchmark, path) >= 226
    rows = list(csv.DictReader(path.open(encoding="utf-8-sig")))
    assert all(r["human_label"] == r["annotator"] == "" for r in rows)
    assert "label_source" not in rows[0] and "gold_label" not in rows[0]
    assert all(r["text_sha256"] == hashlib.sha256(r["text"].encode()).hexdigest() for r in rows)


def test_single_class_agreement_is_not_certified_as_kappa_one(tmp_path):
    cfg = fixture_benchmark(tmp_path)
    rounds = tmp_path / "rounds"
    rounds.mkdir()
    for tag in ("A", "B"):
        (rounds / f"pass{tag}_Q01.csv").write_text("DOC001-C001,1\n")
    audit = load_benchmark(cfg, verify_manifest=False).audit()["annotation_consistency"]
    assert audit["per_query"][0]["agreement"] == 1
    assert audit["per_query"][0]["kappa"] is None
    assert audit["mean_defined_kappa"] is None


def test_frozen_annotation_rounds_detect_silent_edits(tmp_path):
    cfg = fixture_benchmark(tmp_path)
    benchmark = load_benchmark(cfg, verify_manifest=False)
    manifest = {"schema_version": 1, "benchmark_id": "fixture-v1", "hashes": benchmark.hashes}
    Path(cfg["evaluation"]["manifest_path"]).write_text(json.dumps(manifest))
    rounds = tmp_path / "rounds"
    rounds.mkdir()
    (rounds / "passA_Q01.csv").write_text("DOC001-C001,0\n")
    with pytest.raises(ValueError, match="冻结版本"):
        load_benchmark(cfg)
