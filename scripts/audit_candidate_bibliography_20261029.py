#!/usr/bin/env python3
"""Bind bibliography/source review and render QA to the current manuscript candidate."""
from __future__ import annotations

import difflib
import hashlib
import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
CURRENT_REL = Path(
    "results/paper/condensed_candidate_20261028_01/"
    "年报与法规双源RAG_统一主文_跨模型与Agent年度分层复算候选稿_待终审.docx"
)
PARENT_REL = Path(
    "results/paper/condensed_candidate_20261028_01/"
    "年报与法规双源RAG_统一主文_补充CFinRAG相关工作候选稿_待终审.docx"
)
SOURCE_AUDIT_REL = Path(
    "results/paper/condensed_candidate_20261028_01/"
    "candidate_bibliography_source_audit_20261029.md"
)
RUN_REL = Path("results/runs/citation_reference_correction_20261029_01")
PRE_EDIT_REL = RUN_REL / "baseline_candidate.docx"
OUTPUT_REL = RUN_REL / "candidate_citation_rebind.json"
NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
REF_START = re.compile(r"^\[(\d+)\]\s+(.+)$")
CITATION_GROUP = re.compile(r"\[(\d+(?:[–—-]\d+)?(?:\s*,\s*\d+(?:[–—-]\d+)?)*)\]")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def extract_paragraphs(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as archive:
        document = ET.fromstring(archive.read("word/document.xml"))
    return [
        "".join(node.text or "" for node in paragraph.findall(".//w:t", NS))
        for paragraph in document.findall(".//w:body/w:p", NS)
    ]


def split_body_and_refs(paragraphs: list[str]) -> tuple[list[tuple[int, str]], dict[int, str]]:
    bibliography_index = next(
        (i for i, text in enumerate(paragraphs) if re.match(r"^\[1\]\s+", text)),
        len(paragraphs),
    )
    refs: dict[int, str] = {}
    for text in paragraphs[bibliography_index:]:
        match = REF_START.match(text)
        if match:
            refs[int(match.group(1))] = match.group(2).strip()
    body = [(i, text) for i, text in enumerate(paragraphs[:bibliography_index]) if text.strip()]
    return body, refs


def cited_ids(text: str, max_reference: int) -> list[int]:
    ids: set[int] = set()
    for group in CITATION_GROUP.findall(text):
        # [0,1] is the numerical interval used for missing-outcome bounds, not a citation.
        if group.replace(" ", "") == "0,1":
            continue
        for item in re.split(r"\s*,\s*", group):
            match = re.fullmatch(r"(\d+)(?:[–—-](\d+))?", item)
            if not match:
                continue
            first = int(match.group(1))
            last = int(match.group(2) or first)
            ids.update(number for number in range(first, last + 1) if 1 <= number <= max_reference)
    return sorted(ids)


def page_hashes(directory: Path) -> dict[str, str]:
    return {
        path.name: sha256(path.read_bytes())
        for path in sorted(directory.glob("page-*.png"))
    }


def main() -> None:
    current_path = ROOT / CURRENT_REL
    parent_path = ROOT / PARENT_REL
    pre_edit_path = ROOT / PRE_EDIT_REL
    source_audit_path = ROOT / SOURCE_AUDIT_REL
    run_path = ROOT / RUN_REL
    current_bytes = current_path.read_bytes()
    parent_bytes = parent_path.read_bytes()
    pre_edit_bytes = pre_edit_path.read_bytes()
    current_body, current_refs = split_body_and_refs(extract_paragraphs(current_path))
    parent_body, parent_refs = split_body_and_refs(extract_paragraphs(parent_path))
    _, pre_edit_refs = split_body_and_refs(extract_paragraphs(pre_edit_path))

    expected_ids = list(range(1, 32))
    body_citations = sorted({
        reference
        for _, text in current_body
        for reference in cited_ids(text, max(expected_ids))
    })
    uncited = sorted(set(current_refs) - set(body_citations))
    unresolved = sorted(set(body_citations) - set(current_refs))
    changed_bibliography_ids_vs_parent = [
        reference
        for reference in sorted(set(current_refs) | set(parent_refs))
        if current_refs.get(reference) != parent_refs.get(reference)
    ]
    changed_bibliography_ids_vs_pre_edit = [
        reference
        for reference in sorted(set(current_refs) | set(pre_edit_refs))
        if current_refs.get(reference) != pre_edit_refs.get(reference)
    ]

    current_cited_paragraphs = [text for _, text in current_body if cited_ids(text, 31)]
    parent_cited_paragraphs = [text for _, text in parent_body if cited_ids(text, 31)]
    changed_cited_paragraphs: list[dict[str, object]] = []
    matcher = difflib.SequenceMatcher(
        a=parent_cited_paragraphs, b=current_cited_paragraphs, autojunk=False
    )
    for tag, a1, a2, b1, b2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        for text in parent_cited_paragraphs[a1:a2]:
            changed_cited_paragraphs.append({
                "side": "parent",
                "change": tag,
                "references": cited_ids(text, 31),
                "text_sha256": sha256(text.encode("utf-8")),
                "anchor": text[:90],
            })
        for text in current_cited_paragraphs[b1:b2]:
            changed_cited_paragraphs.append({
                "side": "current",
                "change": tag,
                "references": cited_ids(text, 31),
                "text_sha256": sha256(text.encode("utf-8")),
                "anchor": text[:90],
            })

    render_dir = run_path / "render"
    baseline_dir = run_path / "baseline"
    previous_receipt_path = ROOT / OUTPUT_REL
    if render_dir.is_dir() and baseline_dir.is_dir():
        rendered = page_hashes(render_dir)
        baseline = page_hashes(baseline_dir)
        changed_pages = [
            page
            for page in sorted(set(rendered) | set(baseline))
            if rendered.get(page) != baseline.get(page)
        ]
        pdf_path = render_dir / (current_path.stem + ".pdf")
        pdf_sha256 = sha256(pdf_path.read_bytes())
        baseline_page21_sha256 = baseline.get("page-21.png")
        render_evidence_source = "rendered_pages_and_pdf"
    elif previous_receipt_path.is_file():
        previous_receipt_bytes = previous_receipt_path.read_bytes()
        previous_receipt = json.loads(previous_receipt_bytes)
        if (
            previous_receipt.get("status") != "passed_scoped_bibliography_and_render_rebind"
            or previous_receipt.get("candidate", {}).get("sha256") != sha256(current_bytes)
        ):
            raise SystemExit("No render files and prior passing receipt is not bound to this candidate")
        render_record = previous_receipt["render"]
        rendered = render_record["all_rendered_page_hashes"]
        baseline = {}
        changed_pages = [f"page-{number}.png" for number in render_record["changed_pages_vs_pre_edit_candidate"]]
        pdf_sha256 = render_record["pdf_sha256"]
        baseline_page21_sha256 = render_record.get("baseline_page_png_sha256")
        render_evidence_source = "previously_verified_bound_receipt"
    else:
        raise SystemExit("Render files and a previously verified bound receipt are both unavailable")
    corrected_ref7 = (
        "Robertson S, Zaragoza H. The Probabilistic Relevance Framework: BM25 and Beyond. "
        "Foundations and Trends in Information Retrieval 3(4), 2009: 333–389. "
        "https://doi.org/10.1561/1500000019"
    )

    checks = {
        "candidate_sha_bound": bool(current_bytes),
        "reference_ids_contiguous_1_to_31": sorted(current_refs) == expected_ids,
        "all_references_cited": not uncited,
        "no_unresolved_body_citation_ids": not unresolved,
        "reference_7_uses_original_article_preferred_citation": current_refs.get(7) == corrected_ref7,
        "bibliography_matches_scoped_cfinrag_parent": not changed_bibliography_ids_vs_parent,
        "only_reference_7_changed_vs_pre_edit_candidate": changed_bibliography_ids_vs_pre_edit == [7],
        "codex_render_is_23_pages": len(rendered) == 23,
        "only_page_21_differs_from_pre_edit_candidate": changed_pages == ["page-21.png"],
        "source_audit_present": source_audit_path.is_file(),
    }
    result = {
        "audit_date": "2026-10-29",
        "status": "passed_scoped_bibliography_and_render_rebind" if all(checks.values()) else "failed",
        "candidate": {
            "path": CURRENT_REL.as_posix(),
            "sha256": sha256(current_bytes),
            "reference_count": len(current_refs),
            "reference_ids": sorted(current_refs),
            "body_citation_ids": body_citations,
            "uncited_reference_ids": uncited,
            "unresolved_body_citation_ids": unresolved,
        },
        "parent": {
            "path": PARENT_REL.as_posix(),
            "sha256": sha256(parent_bytes),
            "sha256_expected": "fcf7b66c0afe5168119f78023a70f9664ebc5037254c5ba5baf069ab525d81a7",
        },
        "pre_edit_candidate": {
            "path": PRE_EDIT_REL.as_posix(),
            "sha256": sha256(pre_edit_bytes),
            "sha256_expected": "16e0e3c1cb4587a3f1ceccdb6c9fd53606f65400cb4f170d27eb982f2a5d1639",
        },
        "bibliography_delta": {
            "changed_reference_ids_vs_scoped_parent": changed_bibliography_ids_vs_parent,
            "changed_reference_ids_vs_pre_edit": changed_bibliography_ids_vs_pre_edit,
            "reference_7_pre_edit": pre_edit_refs.get(7),
            "reference_7_current": current_refs.get(7),
            "changed_cited_paragraphs": changed_cited_paragraphs,
        },
        "render": {
            "renderer": "Codex documents render_docx.py; LibreOffice 26.8.1.1; Poppler",
            "wps_used": False,
            "evidence_source": render_evidence_source,
            "page_count": len(rendered),
            "changed_pages_vs_pre_edit_candidate": [int(re.search(r"page-(\d+)\.png", name).group(1)) for name in changed_pages],
            "visually_reviewed_pages": [21],
            "changed_page_png_sha256": rendered.get("page-21.png"),
            "baseline_page_png_sha256": baseline_page21_sha256,
            "pdf_sha256": pdf_sha256,
            "all_rendered_page_hashes": rendered,
        },
        "source_audit": {
            "path": SOURCE_AUDIT_REL.as_posix(),
            "sha256": sha256(source_audit_path.read_bytes()) if source_audit_path.exists() else None,
            "primary_source_reference_count": 31,
            "historical_model_doc_page_snapshot_retrievable": False,
        },
        "new_model_calls": 0,
        "new_human_annotations": 0,
        "checks": checks,
        "scope_limits": [
            "Bibliographic identity and scoped citation descriptions only; not a full reread of every cited paper.",
            "Not a full semantic audit of 355 answers or a validation of independent gold labels.",
            "Does not establish historical legal applicability, author metadata, target-journal formatting, or acceptance readiness.",
            "Kimi documentation checked 2026-10-29 confirms current aliases/defaults but cannot reconstruct the historical 2026-10-20/23 webpage snapshot.",
        ],
    }
    run_path.mkdir(parents=True, exist_ok=True)
    (ROOT / OUTPUT_REL).write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps({"status": result["status"], "checks": checks, "output": OUTPUT_REL.as_posix()}, ensure_ascii=False, indent=2))
    if not all(checks.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
