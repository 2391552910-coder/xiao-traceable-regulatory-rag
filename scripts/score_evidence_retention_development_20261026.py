"""Offline scoring of saved development answers, with explicit publication gates.

No generation or network access occurs. Incomplete conditions and batches with
no valid model answer have null quality metrics, never an inferred zero score.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.score_heldout_validation_20261023 import names, dates, setscore
from src.generation.annual_audit_development import valid_answer
from src.generation.request_journal import atomic_write_json

SOURCE = ROOT / "results/paper/heldout_validation_20261023_01"
DEFAULT_RUN = ROOT / "results/runs/evidence_retention_development_20261026_03"
MODES = ("k3_single_dev", "k3_fixed_preserve", "k3_refine3_dev", "k3_agent_preserve")
METRICS = ("members_precision", "members_recall", "members_f1", "count_accuracy",
           "dates_precision", "dates_recall", "dates_f1", "three_field_exact")
TERMINAL = {"completed", "failed", "not_dispatched", "remote_unknown", "http_failed",
            "output_exhausted", "empty_answer", "parse_failed"}


def _key(value):
    return (value.get("question_id", value.get("question", {}).get("question_id")), value.get("mode"))


def _scores(answer, reference):
    member = setscore(names(answer.get("members")), names(reference["members"]))
    date = setscore(dates(answer.get("meeting_dates")), dates(reference["meeting_dates"]))
    count = type(answer.get("meeting_count")) is int and answer["meeting_count"] == reference["meeting_count"]
    return {**{"members_" + k: member[k] for k in ("precision", "recall", "f1")},
            **{"dates_" + k: date[k] for k in ("precision", "recall", "f1")},
            "count_accuracy": float(count), "three_field_exact": float(member["exact"] and date["exact"] and count)}


def summarize(results, reference_by_qid, schedule):
    """Pure calculation over a fixed schedule; no file reads or mutation.

    Results are a sequence of saved result dictionaries. Failed units count as
    zero only when their entire condition is terminal and at least one valid,
    nonempty completed answer exists. Otherwise all quality fields stay null.
    """
    expected = [_key(s) for s in schedule]
    if not expected or len(set(expected)) != len(expected) or any(not all(k) for k in expected):
        raise ValueError("Schedule must contain unique question and mode pairs")
    by_key = {}
    for result in results:
        key = _key(result)
        if key not in expected or key in by_key:
            raise ValueError("Duplicate or unscheduled result")
        by_key[key] = result
    for qid, _ in expected:
        ref = reference_by_qid.get(qid)
        if not ref or not names(ref.get("members")) or not dates(ref.get("meeting_dates")) or type(ref.get("meeting_count")) is not int:
            raise ValueError("Missing or incomplete reference fields: " + qid)
    groups, rows = [], []
    for mode in dict.fromkeys(m for _, m in expected):
        cases = []
        for qid, case_mode in expected:
            if mode != case_mode:
                continue
            result = by_key.get((qid, mode))
            terminal = bool(result and result.get("status") in TERMINAL and result.get("terminal", True))
            answer = result.get("parsed") if result else None
            valid = bool(terminal and result["status"] == "completed" and
                         isinstance(result.get("text"), str) and result["text"].strip() and valid_answer(answer))
            cases.append({"question_id": qid, "mode": mode,
                          "result_status": result.get("status") if result else "not_started",
                          "failure_reason": result.get("failure_reason") if result else None,
                          "terminal": terminal, "valid_model_answer": valid,
                          "_scores": _scores(answer, reference_by_qid[qid]) if valid else dict.fromkeys(METRICS, 0.0)})
        observed = sum((c["question_id"], mode) in by_key for c in cases)
        terminal_count = sum(c["terminal"] for c in cases)
        answer_count = sum(c["valid_model_answer"] for c in cases)
        status = "awaiting" if observed == 0 else "partial" if terminal_count < len(cases) else "no_answers" if answer_count == 0 else "complete"
        publish = status == "complete"
        groups.append({"mode": mode, "status": status, "planned_units": len(cases),
                       "observed_units": observed, "terminal_units": terminal_count,
                       "valid_model_answers": answer_count, "quality_published": publish,
                       **{k: statistics.mean(c["_scores"][k] for c in cases) if publish else None for k in METRICS}})
        for case in cases:
            scores = case.pop("_scores")
            rows.append({**case, "condition_status": status, "quality_published": publish,
                         "failure_zero_in_denominator": publish and not case["valid_model_answer"],
                         **{k: scores[k] if publish else None for k in METRICS}})
    return {"classification": "exposed development regression, not independent test",
            "groups": groups, "rows": rows,
            "metrics": "Question-macro set precision/recall/F1; exact integer count; three-field exact match",
            "publication_gate": "All planned units terminal and at least one valid nonempty answer per condition; failures included as zero only after that gate",
            "semantic_citation_support_verified": False, "independent_human_review_completed": False}


def _load(path):
    return json.loads(path.read_bytes())


def _sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN)
    args = parser.parse_args(argv)
    run = args.run_dir.resolve()
    protocol_path = run / "generation_protocol.json"
    protocol = _load(protocol_path)
    schedule = protocol["schedule"]
    expected = {(s["question_id"], s["mode"]) for s in schedule}
    qids = {s["question_id"] for s in schedule}
    if len(schedule) != 32 or len(expected) != 32 or len(qids) != 8 or set(protocol["modes"]) != set(MODES):
        raise ValueError("Expected the frozen 32-unit, eight-question, four-mode protocol")
    if any({s["question_id"] for s in schedule if s["mode"] == mode} != qids for mode in MODES):
        raise ValueError("Every frozen condition must contain the same eight questions")
    start = run / "generation_start.json"
    if start.exists() and _load(start)["protocol_sha256"] != _sha(protocol_path):
        raise ValueError("Generation protocol differs from its start receipt")
    references = {}
    for version, filename, hash_field in [("frozen", "reference_labels.json", "reference_labels_sha256"),
                                           ("corrected", "reference_labels_corrected.json", "corrected_reference_labels_sha256")]:
        path = SOURCE / filename
        if _sha(path) != protocol[hash_field]:
            raise ValueError("Reference SHA256 differs from frozen protocol: " + version)
        references[version] = _load(path)
    if references["corrected"]["parent_sha256"] != protocol["reference_labels_sha256"]:
        raise ValueError("Corrected references do not link to the frozen parent")
    results = []
    for path in sorted((run / "calls").glob("*/*/result.json")):
        result = _load(path)
        if _key(result) != (path.parent.parent.name, path.parent.name):
            raise ValueError("Result identity differs from its saved path")
        results.append(result)
    analyses = {}
    for version, document in references.items():
        refs = {r["question_id"]: r for r in document["records"]}
        if len(refs) != len(document["records"]):
            raise ValueError("Duplicate reference question")
        analysis = summarize(results, refs, schedule)
        analysis.update(reference_version=version, reference_sha256=protocol["reference_labels_sha256" if version == "frozen" else "corrected_reference_labels_sha256"],
                        protocol_sha256=_sha(protocol_path), source_reference_scope=document.get("scope"),
                        reference_annotation_provenance=document.get("annotator"), corrected_labels_are_post_output=version == "corrected")
        analyses[version] = analysis
    # Validate every input/version before publishing either output.
    for version, analysis in analyses.items():
        atomic_write_json(run / f"extraction_analysis_{version}.json", analysis)
        with (run / f"extraction_scores_{version}.csv").open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(analysis["rows"][0]))
            writer.writeheader()
            writer.writerows(analysis["rows"])
    print(json.dumps({v: a["groups"] for v, a in analyses.items()}, ensure_ascii=False, indent=2))
    return analyses


if __name__ == "__main__":
    main()
