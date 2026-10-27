"""Conservative, auditable connected groups for question-level holdouts.

This is a metadata/coordinate check. It cannot certify semantic independence,
independent review or final-test eligibility, and never changes split labels.
"""
from __future__ import annotations

import hashlib
import itertools
import re
import unicodedata
from collections import defaultdict


def normalize(value) -> str:
    return " ".join(unicodedata.normalize("NFKC", str(value or "")).casefold().split())


def question_identifier(row: dict) -> str:
    return str(row.get("query_id") or row.get("question_id") or row.get("candidate_id") or "").strip()


def connected_question_groups(questions: list[dict], annual_evidence: list[dict] | None = None,
                              regulation_evidence: list[dict] | None = None, *,
                              links: list[dict] | None = None,
                              development_exposed_ids: set[str] | None = None) -> dict:
    """Join declared families/events, identical questions and overlapping targets.

    Source coordinates are half-open. Shared source documents alone, company
    names and coincident dates do not imply one event. On a shared PDF page (or
    an uncertain document/page frame), incomparable text coordinates are joined
    conservatively and flagged. Explicit relevance=0 rows are not target evidence.
    """
    by_id = {}
    for row in questions:
        query_id = question_identifier(row)
        if not query_id or query_id in by_id:
            raise ValueError("Question IDs must be present and unique before grouping")
        by_id[query_id] = row
    parents = {query_id: query_id for query_id in by_id}
    edges: dict[tuple[str, str], list[dict]] = defaultdict(list)
    issues = []
    exposed = set(development_exposed_ids or set())

    def find(query_id):
        while parents[query_id] != query_id:
            parents[query_id] = parents[parents[query_id]]
            query_id = parents[query_id]
        return query_id

    def join(left, right, reason, **details):
        if left == right:
            return
        pair = tuple(sorted((left, right)))
        edge = {"reason": reason, **details}
        if edge not in edges[pair]:
            edges[pair].append(edge)
        root_a, root_b = find(left), find(right)
        if root_a != root_b:
            parents[max(root_a, root_b)] = min(root_a, root_b)

    for field in ("query_family_id", "event_group_id", "query_text"):
        buckets = defaultdict(list)
        for query_id, row in by_id.items():
            raw = row.get(field) or ((row.get("query") or row.get("question"))
                                     if field == "query_text" else "")
            key = normalize(raw)
            if key and key not in {"unknown", "unresolved", "u"}:
                buckets[key].append(query_id)
        for key, members in buckets.items():
            for left, right in itertools.combinations(sorted(members), 2):
                join(left, right, "identical_query_text" if field == "query_text" else field,
                     key=key)

    unresolved_semantic_links, rejected_links = [], []
    allowed_link_types = {"same_family", "same_event", "near_duplicate", "evidence_overlap",
                          "possible_family_overlap"}
    for row in links or []:
        left, right = str(row.get("query_id_a", "")), str(row.get("query_id_b", ""))
        kind = row.get("link_type", "")
        if left not in by_id or right not in by_id or kind not in allowed_link_types:
            raise ValueError("Question-group link has an unknown endpoint or link_type")
        status = str(row.get("review_status") or "unverified")
        if status in {"rejected", "different_event_or_family", "different"}:
            rejected_links.append(dict(row))
            continue
        if status not in {"accepted", "adjudicated"}:
            unresolved_semantic_links.append(dict(row))
        join(left, right, "declared_link", link_type=kind,
             basis=str(row.get("reason", "")), review_status=status)

    evidence_buckets = defaultdict(list)
    ignored_negative_rows = 0
    for role, records in (("annual_report", annual_evidence or []),
                          ("regulation", regulation_evidence or [])):
        for index, row in enumerate(records):
            query_id = str(row.get("query_id", ""))
            if query_id not in by_id:
                raise ValueError("Evidence references an unknown query_id")
            if str(row.get("relevance_grade_gold", "")).strip() == "0":
                ignored_negative_rows += 1
                continue
            digest = str((row.get("source_pdf_sha256") if role == "annual_report"
                          else row.get("source_document_sha256")) or "").lower()
            if not re.fullmatch(r"[0-9a-f]{64}", digest):
                issues.append({"code": "evidence_source_hash_missing_or_invalid",
                               "query_id": query_id, "evidence_id": row.get("evidence_id", "")})
                continue
            page_raw = str(row.get("pdf_physical_page_1based") or "")
            page = str(int(page_raw)) if page_raw.isdecimal() and int(page_raw) > 0 else ""
            text_hash = str((row.get("page_text_sha256") if role == "annual_report"
                             else row.get("source_text_sha256")) or "").lower()
            if not re.fullmatch(r"[0-9a-f]{64}", text_hash):
                text_hash = ""
            try:
                start, end = int(row["source_char_start"]), int(row["source_char_end"])
                if start < 0 or end <= start:
                    raise ValueError
                interval = (start, end)
            except (KeyError, TypeError, ValueError):
                interval = None
            evidence_buckets[(role, digest)].append({
                "query_id": query_id, "evidence_id": str(row.get("evidence_id", index)),
                "page": page, "text_hash": text_hash, "interval": interval})
    for (role, digest), records in evidence_buckets.items():
        for first, second in itertools.combinations(records, 2):
            left, right = first["query_id"], second["query_id"]
            if left == right:
                continue
            if first["page"] and second["page"] and first["page"] != second["page"]:
                continue
            comparable = (first["page"] == second["page"] and first["text_hash"] and
                          first["text_hash"] == second["text_hash"] and
                          first["interval"] is not None and second["interval"] is not None)
            details = {"source_role": role, "source_sha256": digest,
                       "evidence_ids": [first["evidence_id"], second["evidence_id"]]}
            if comparable:
                a, b = first["interval"], second["interval"]
                if max(a[0], b[0]) < min(a[1], b[1]):
                    join(left, right, "overlapping_source_interval", **details)
            else:
                join(left, right, "incomparable_source_coordinates", **details)
                issues.append({"code": "incomparable_source_coordinates",
                               "query_ids": sorted((left, right)), **details})

    components = defaultdict(list)
    for query_id in sorted(by_id):
        components[find(query_id)].append(query_id)
    groups, conflicts = [], []
    for members in sorted(components.values()):
        group_id = "GROUP-" + hashlib.sha256("\n".join(members).encode()).hexdigest()[:16]
        splits = sorted({str(by_id[qid].get("split", "unassigned")) for qid in members})
        development = sorted(qid for qid in members
                             if by_id[qid].get("split") == "development" or qid in exposed)
        evaluation = sorted(qid for qid in members
                            if by_id[qid].get("split") in {"final_test", "robustness"})
        group = {"group_id": group_id, "query_ids": members, "splits": splits,
                 "development_or_exposed_query_ids": development}
        groups.append(group)
        if development and evaluation:
            conflicts.append({**group, "evaluation_query_ids": evaluation})
    return {
        "schema_version": "question-evidence-connected-groups-v1",
        "question_count": len(by_id), "group_count": len(groups),
        "groups": groups,
        "edges": [{"query_id_a": pair[0], "query_id_b": pair[1], "reasons": reasons}
                  for pair, reasons in sorted(edges.items())],
        "development_evaluation_conflicts": conflicts,
        "coordinate_issues": issues,
        "unresolved_semantic_links": unresolved_semantic_links,
        "rejected_links_not_grouped": rejected_links,
        "explicitly_negative_evidence_rows_excluded": ignored_negative_rows,
        "unmapped_development_exposure_ids": sorted(exposed - set(by_id)),
        "queries_missing_declared_event_group": sorted(
            qid for qid, row in by_id.items() if not row.get("event_group_id")),
        "queries_missing_declared_family": sorted(
            qid for qid, row in by_id.items() if not row.get("query_family_id")),
        "queries_without_annual_target_coordinates": sorted(
            set(by_id) - {row["query_id"] for (role, _), records in evidence_buckets.items()
                          if role == "annual_report" for row in records}),
        "queries_without_regulation_target_coordinates": sorted(
            set(by_id) - {row["query_id"] for (role, _), records in evidence_buckets.items()
                          if role == "regulation" for row in records}),
        "metadata_group_checks_passed": not conflicts and not issues and not unresolved_semantic_links
                                        and not (exposed - set(by_id)),
        "semantic_grouping_verified": False,
        "accepted_as_gold": False, "frozen_test_set": False,
        "limitations": [
            "Shared company identity or event date alone does not prove one event.",
            "Equal source bytes alone do not prove overlapping target evidence.",
            "Family/event IDs and declared links are supplied metadata, not certified semantics.",
            "Missing event IDs and paraphrases require independent semantic/exposure crosswalk review.",
            "Equivalent source versions with different file hashes require a canonical-source crosswalk.",
            "Common regulation intervals may form large conservative components; report actual feasibility.",
            "No source files, text transcriptions, labels or semantic support were reverified here.",
        ],
    }


def suggest_semantic_crosswalk(questions: list[dict], *, min_shared_bigrams: int = 4,
                               min_overlap: float = 0.6) -> list[dict]:
    """Prioritize possible overlaps for review; these are not semantic labels."""
    prepared = []
    for row in questions:
        query_id = question_identifier(row)
        text = str(row.get("query_text") or row.get("query") or row.get("question") or "")
        clean = re.sub(r"[^\w]", "", normalize(text))
        bigrams = {clean[index:index + 2] for index in range(len(clean) - 1)}
        prepared.append((query_id, text, bigrams))
    suggestions = []
    for first, second in itertools.combinations(prepared, 2):
        a, b = first[2], second[2]
        shared = len(a & b)
        overlap = shared / min(len(a), len(b)) if a and b else 0.0
        if shared >= min_shared_bigrams and overlap >= min_overlap:
            suggestions.append({"query_id_a": first[0], "query_id_b": second[0],
                "query_text_a": first[1], "query_text_b": second[1],
                "shared_character_bigrams": shared, "overlap_coefficient": overlap,
                "jaccard": shared / len(a | b),
                "suggested_relation": "text_overlap_candidate_only",
                "semantic_relation": "unreviewed", "reviewer_id": "",
                "decision": "", "reason": ""})
    return sorted(suggestions, key=lambda row: (-row["overlap_coefficient"],
                                               -row["jaccard"], row["query_id_a"], row["query_id_b"]))
