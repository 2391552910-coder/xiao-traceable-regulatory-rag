"""Load source-linked annual-report and regulation chunks for dual-corpus RAG.

The annual corpus is read from the source manifest produced by the annual-report
recovery workflow. Regulation inputs may be metadata-prefixed UTF-8 text or
hash-bound PDF/DOCX files. File integrity does not establish source identity,
version applicability or verified company facts.
"""
from __future__ import annotations

import csv
import hashlib
import importlib.metadata
import json
import re
from pathlib import Path

from src.data.annual_reports import inspect_pdf, sha256_file
from src.data.clause_splitter import Chunk, split_document
from src.data.knowledge_loader import load_documents
from src.data.structural_splitter import split_structural_document
from src.data.pdf_text_frames import LAYOUT, extract_native_text, parser_for_mode, parser_policy

LEGACY_DEMONSTRATION_EXCERPTS = {"DOC001", "DOC002", "DOC003"}


def _resolve_manifest_file(manifest_path: Path, file_value: str) -> Path:
    """Resolve absolute paths as-is and relative paths beside their manifest."""
    path = Path(file_value)
    if path.is_absolute():
        return path
    beside_manifest = manifest_path.parent / path
    if beside_manifest.is_file():
        return beside_manifest
    # Keep compatibility with older manifests whose relative paths were
    # interpreted from the caller's working directory.
    return path


def _split_page(text: str, size: int, overlap: int) -> list[tuple[int, int, str]]:
    if size < 1 or overlap < 0 or overlap >= size:
        raise ValueError("size must be positive and overlap must be in [0, size)")
    spans = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        # Prefer a nearby paragraph/sentence boundary without dropping text.
        if end < len(text):
            floor = start + max(size // 2, 1)
            candidates = [text.rfind(mark, floor, end) for mark in ("\n", "。", "；", "！", "？")]
            boundary = max(candidates)
            if boundary >= floor:
                end = boundary + 1
        left = start
        right = end
        while left < right and text[left].isspace():
            left += 1
        while right > left and text[right - 1].isspace():
            right -= 1
        if left < right:
            spans.append((left, right, text[left:right]))
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return spans


def _load_annual_ocr_sidecar(run_dir: str | Path | None) -> dict[tuple[str, int], list[dict]]:
    """Load OCR pages only when their text, image, and release hashes verify."""
    if run_dir is None:
        return {}
    root = Path(run_dir).resolve()
    release_path = root / "release_manifest.json"
    if not release_path.is_file():
        raise FileNotFoundError(f"OCR release manifest is missing: {release_path}")
    release_raw = release_path.read_bytes()
    release_sha = hashlib.sha256(release_raw).hexdigest()
    release = json.loads(release_raw.decode("utf-8"))
    artifacts = {item["path"]: item for item in release.get("artifacts", [])}

    def verified_bytes(path: Path) -> tuple[bytes, str]:
        resolved = path.resolve()
        try:
            relative = resolved.relative_to(root).as_posix()
        except ValueError as error:
            raise ValueError(f"OCR sidecar path is outside its run directory: {path}") from error
        expected = artifacts.get(relative)
        if expected is None:
            raise ValueError(f"OCR sidecar file is not listed in the release manifest: {relative}")
        raw = resolved.read_bytes()
        actual = hashlib.sha256(raw).hexdigest()
        if len(raw) != int(expected["bytes"]) or actual != expected["sha256"]:
            raise ValueError(f"OCR sidecar release hash mismatch: {relative}")
        return raw, actual

    pages: dict[tuple[str, int], list[dict]] = {}
    run_specs = (
        ("artifacts/ocr_text/ocr_run.json", "artifacts/ocr_text"),
        ("artifacts/ocr_text_rotated/ocr_run.json", "artifacts/ocr_text_rotated"),
    )
    loaded_run = False
    for run_relative, text_directory in run_specs:
        run_path = root / run_relative
        if not run_path.is_file():
            continue
        raw, run_sha = verified_bytes(run_path)
        rows = json.loads(raw.decode("utf-8-sig"))
        loaded_run = True
        for row in rows:
            if row.get("status") != "ocr_saved_needs_review":
                continue
            text_path = root / text_directory / Path(row["text_file"]).name
            text_raw, text_sha = verified_bytes(text_path)
            image_path = Path(row["rendered_image"])
            if not image_path.is_absolute():
                image_path = root / image_path
            _, image_sha = verified_bytes(image_path)
            if not row.get("image_hash_verified_before_ocr"):
                raise ValueError(f"OCR image was not hash-verified before recognition: {image_path}")
            text = text_raw.decode("utf-8-sig")
            pages.setdefault((row["stock_code"], int(row["pdf_page"])), []).append({
                "text": text,
                "text_sha256": text_sha,
                "image_sha256": image_sha,
                "source_pdf_sha256": row.get("source_document_sha256", "").lower(),
                "engine": row.get("engine") or "unknown_ocr",
                "run_id": release.get("run_id"),
                "rotation_degrees": row.get("render_rotation_degrees"),
                "confidence_available": bool(row.get("confidence_available", False)),
                "release_manifest_file": str(release_path.resolve()),
                "release_manifest_sha256": release_sha,
                "ocr_run_file": str(run_path.resolve()),
                "ocr_run_sha256": run_sha,
                "text_file": str(text_path.resolve()),
                "image_file": str(image_path.resolve()),
            })
    if not loaded_run:
        raise ValueError(f"No OCR run records found in {root}")
    return pages


def load_annual_report_chunks(manifest_path: str | Path, *,
                              chunk_chars: int = 1200,
                              overlap_chars: int = 160,
                              page_numbers: set[int] | None = None,
                              ocr_run_dir: str | Path | None = None,
                              limit: int | None = None) -> tuple[list[Chunk], dict]:
    """Parse identity-verified annual PDFs and return page-addressable chunks.

    The recovery manifest is authoritative for issuer/year identity, source URI,
    known publication date and source hash. Rows without those checks are
    rejected instead of silently entering the searchable corpus.
    """
    from pypdf import PdfReader

    manifest_path = Path(manifest_path)
    with manifest_path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ValueError(f"Annual-report manifest is empty: {manifest_path}")
    selected = rows if limit is None else rows[:limit]
    ocr_pages = _load_annual_ocr_sidecar(ocr_run_dir)
    chunks: list[Chunk] = []
    reports = []
    ocr_source_files: dict[str, dict] = {}
    for row in selected:
        if row.get("status") not in {"imported", "downloaded"} or row.get("identity_verified", "").lower() != "true":
            raise ValueError(f"Annual report is not identity-verified: {row.get('stock_code')}")
        path = _resolve_manifest_file(manifest_path, row["file"])
        if not path.is_file():
            raise FileNotFoundError(path)
        pdf_sha = sha256_file(path)
        if pdf_sha.lower() != row.get("sha256", "").lower():
            raise ValueError(f"Annual PDF SHA256 mismatch: {row.get('stock_code')}")
        native_parser = parser_for_mode(row.get('pdf_text_mode'))
        identity_parser = (row.get("identity_text_parser") or row.get("text_parser")
                           or "pypdf")
        identity = inspect_pdf(
            path, {"stock_code": row["stock_code"], "name": row["name"]},
            int(row["year"]), parser=identity_parser)
        if not identity["identity"]["verified"]:
            raise ValueError(f"Annual PDF identity does not match manifest: {row.get('stock_code')}")
        if identity["sha256"] != pdf_sha or identity["page_count"] != int(row["page_count"]):
            raise ValueError(f"Annual PDF source integrity mismatch: {row.get('stock_code')}")
        reader = PdfReader(path, strict=False)
        if reader.is_encrypted and not reader.decrypt(""):
            raise ValueError(f"Encrypted annual report: {row.get('stock_code')}")
        if len(reader.pages) != int(row["page_count"]):
            raise ValueError(f"Annual PDF page count mismatch: {row.get('stock_code')}")
        selected_pages = set(range(1, len(reader.pages) + 1)) if page_numbers is None else page_numbers
        if not selected_pages or min(selected_pages) < 1 or max(selected_pages) > len(reader.pages):
            raise ValueError(f"Annual page selection is outside PDF bounds: {row.get('stock_code')}")
        code = re.sub(r"\W", "", row["stock_code"])
        doc_id = f"AR-{code}-{row['year']}"
        report_chunks = 0
        empty_pages = []
        pdf_text_missing_pages = []
        ocr_pages_used = []
        for page_number in sorted(selected_pages):
            page = reader.pages[page_number - 1]
            text = extract_native_text(page, native_parser)
            page_text_parser = native_parser if native_parser == LAYOUT else "pypdf"
            page_text_origin = "pdf_text_layer"
            ocr_metadata = None
            if not text.strip():
                pdf_text_missing_pages.append(page_number)
                candidates = ocr_pages.get((row["stock_code"], page_number), [])
                mismatched = [candidate for candidate in candidates
                              if candidate["source_pdf_sha256"] != pdf_sha.lower()]
                if mismatched:
                    raise ValueError(
                        f"OCR source PDF SHA256 mismatch: {row['stock_code']} page {page_number}")
                candidates = [candidate for candidate in candidates
                              if candidate["text"].strip()]
                candidates = [candidate for candidate in candidates
                              if candidate["run_id"]]
                if candidates:
                    ocr_metadata = max(candidates, key=lambda candidate: len(candidate["text"].strip()))
                    text = ocr_metadata["text"]
                    page_text_parser = ocr_metadata["engine"]
                    page_text_origin = "ocr_sidecar_unreviewed"
                    ocr_pages_used.append(page_number)
            page_sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
            if not text.strip():
                empty_pages.append(page_number)
                continue
            for window_number, (start, end, excerpt) in enumerate(
                    _split_page(text, chunk_chars, overlap_chars), start=1):
                parser_tag = 'LAYOUT-' if page_text_parser == LAYOUT else ''
                chunk_id = f"{doc_id}-P{page_number:04d}-{parser_tag}W{window_number:03d}"
                chunks.append(Chunk(
                    chunk_id=chunk_id,
                    doc_id=doc_id,
                    doc_title=row.get("source_title") or path.name,
                    doc_type="annual_report",
                    source=row.get("source_url") or path.resolve().as_uri(),
                    clause_no=None,
                    text=excerpt,
                    meta={
                        "corpus_type": "annual_report",
                        "stock_code": row["stock_code"],
                        "company_name": row.get("name", ""),
                        "report_year": int(row["year"]),
                        "publication_date": row.get("publication_date") or None,
                        "physical_pdf_page_1based": page_number,
                        "page_text_parser": page_text_parser,
                        "page_text_origin": page_text_origin,
                        **({'native_pdf_text_policy': parser_policy(LAYOUT)} if page_text_parser == LAYOUT else {}),
                        "page_text_char_start": start,
                        "page_text_char_end": end,
                        "page_text_sha256": page_sha,
                        "source_pdf_sha256": pdf_sha,
                        "source_pdf_file": str(path.resolve()),
                        "ocr_text_sha256": ocr_metadata["text_sha256"] if ocr_metadata else None,
                        "ocr_image_sha256": ocr_metadata["image_sha256"] if ocr_metadata else None,
                        "ocr_run_id": ocr_metadata["run_id"] if ocr_metadata else None,
                        "ocr_rotation_degrees": ocr_metadata["rotation_degrees"] if ocr_metadata else None,
                        "ocr_confidence_available": ocr_metadata["confidence_available"] if ocr_metadata else None,
                    },
                ))
                if ocr_metadata:
                    for role, path_key, hash_key in (
                            ("ocr_release_manifest", "release_manifest_file",
                             "release_manifest_sha256"),
                            ("ocr_run_record", "ocr_run_file", "ocr_run_sha256"),
                            ("ocr_text", "text_file", "text_sha256"),
                            ("ocr_page_image", "image_file", "image_sha256")):
                        source_path = str(Path(ocr_metadata[path_key]).resolve())
                        source_hash = str(ocr_metadata[hash_key]).lower()
                        existing = ocr_source_files.get(source_path)
                        if existing and existing["sha256"] != source_hash:
                            raise ValueError(f"Conflicting OCR source hashes for {source_path}")
                        if existing:
                            existing["roles"].add(role)
                        else:
                            ocr_source_files[source_path] = {
                                "path": source_path, "sha256": source_hash,
                                "roles": {role},
                            }
                report_chunks += 1
        reports.append({
            "stock_code": row["stock_code"], "report_year": int(row["year"]),
            "source_file": str(path.resolve()),
            "source_pdf_sha256": pdf_sha, "page_count": len(reader.pages),
            "pages_scanned": sorted(selected_pages),
            "page_scan_scope": "selected_sample" if page_numbers is not None else "full_document",
            "identity_text_parser": identity_parser,
            **({'native_pdf_text_policy': parser_policy(LAYOUT)} if native_parser == LAYOUT else {}),
            "chunk_count": report_chunks, "empty_text_pages": empty_pages,
            "pdf_text_missing_pages": pdf_text_missing_pages,
            "ocr_pages_used": ocr_pages_used,
        })
    if not chunks:
        raise ValueError("No searchable annual-report text was extracted")
    return chunks, {"manifest": str(manifest_path.resolve()),
                    "manifest_sha256": sha256_file(manifest_path),
                    "reports": reports, "chunk_count": len(chunks),
                    "ocr_source_files": [
                        {**item, "roles": sorted(item["roles"])}
                        for _, item in sorted(ocr_source_files.items())],
                    "parser": "pypdf",
                    "parser_version": importlib.metadata.version("pypdf")}


def load_regulation_chunks(directory: str | Path, *, strategy: str = "clause",
                           window_size: int = 512,
                           window_overlap: int = 64) -> tuple[list[Chunk], dict]:
    """Load documents labeled TYPE=regulation; that label is not identity review."""
    docs = load_documents(directory)
    regulations = [doc for doc in docs if doc["doc_type"] == "regulation"
                   and doc["doc_id"] not in LEGACY_DEMONSTRATION_EXCERPTS]
    excluded_demo_documents = [doc["doc_id"] for doc in docs
                               if doc["doc_type"] == "regulation"
                               and doc["doc_id"] in LEGACY_DEMONSTRATION_EXCERPTS]
    if not regulations:
        raise ValueError(f"No TYPE=regulation documents found in {directory}")
    chunks = []
    for doc in regulations:
        pieces = (split_structural_document(doc, window_size=window_size,
                                            window_overlap=window_overlap)
                  if strategy == "structure" else
                  split_document(doc, strategy=strategy, window_size=window_size,
                                 window_overlap=window_overlap))
        for chunk in pieces:
            chunk.meta.update({
                "corpus_type": "regulation",
                "publication_date": doc.get("date") or None,
                "effective_from": doc.get("effective_from"),
                "effective_to": doc.get("effective_to"),
                "source_document_sha256": doc.get("source_file_sha256"),
                "source_file": doc.get("source_file"),
                "version_id": doc.get("version_id"),
                "applicability_status": "metadata_unverified",
            })
            chunks.append(chunk)
    if not chunks:
        raise ValueError("Regulation documents contain no searchable text")
    return chunks, {"document_count": len(regulations), "chunk_count": len(chunks),
                    "source_directory": str(Path(directory).resolve()),
                    "documents": [{"doc_id": doc["doc_id"],
                                   "source_file": doc["source_file"],
                                   "source_file_sha256": doc["source_file_sha256"],
                                   "version_id": doc.get("version_id"),
                                   "publication_date": doc.get("date") or None,
                                   "effective_from": doc.get("effective_from"),
                                   "effective_to": doc.get("effective_to")}
                                  for doc in regulations],
                    "source_files": [{"doc_id": doc["doc_id"],
                                      "doc_type": doc["doc_type"],
                                      "path": doc["source_file"],
                                      "sha256": doc["source_file_sha256"]}
                                     for doc in docs],
                    "excluded_legacy_demonstration_excerpts": excluded_demo_documents,
                    "chunking": strategy}


def load_regulation_pdf_chunks(manifest_path: str | Path, *,
                               chunk_chars: int = 1200,
                               overlap_chars: int = 160,
                               limit: int | None = None) -> tuple[list[Chunk], dict]:
    """Compatibility entry point that accepts PDF manifests only."""
    return _load_regulation_file_chunks(
        manifest_path, chunk_chars=chunk_chars, overlap_chars=overlap_chars,
        limit=limit, allowed_formats={"pdf"})


def load_regulation_file_chunks(manifest_path: str | Path, *,
                                chunk_chars: int = 1200,
                                overlap_chars: int = 160,
                                limit: int | None = None) -> tuple[list[Chunk], dict]:
    """Parse hash-bound PDF/DOCX files; supplied identity/dates stay unverified.

    Required columns: doc_id, title, source, file, sha256, page_count and
    doc_type=regulation. page_count is required for PDF and must be empty for
    DOCX, whose main-body character coordinates do not define physical pages.
    Optional physical_pages selects original PDF pages (e.g. "1,3-5"); an
    empty value reads every page. page_count always describes the whole file.
    Optional ocr_manifest and ocr_manifest_sha256 explicitly select hash-bound
    OCR frames for declared original pages; OCR quality remains unverified.
    """
    return _load_regulation_file_chunks(
        manifest_path, chunk_chars=chunk_chars, overlap_chars=overlap_chars,
        limit=limit, allowed_formats={"pdf", "docx"})


def _parse_physical_pages(value: str | None, page_count: int) -> list[int]:
    """Validate original, one-based page ranges before expanding them."""
    if not value or not value.strip():
        return list(range(1, page_count + 1))
    selected: set[int] = set()
    for token in value.split(","):
        match = re.fullmatch(r"([1-9][0-9]*)(?:\s*-\s*([1-9][0-9]*))?", token.strip())
        if not match:
            raise ValueError(f"Invalid physical_pages token: {token!r}")
        start = int(match[1])
        end = int(match[2]) if match[2] else start
        if start > end or end > page_count:
            raise ValueError(f"physical_pages range outside original PDF pages: {token!r}")
        pages = set(range(start, end + 1))
        if selected.intersection(pages):
            raise ValueError(f"Duplicate or overlapping physical_pages: {token!r}")
        selected.update(pages)
    return sorted(selected)


def _load_regulation_file_chunks(manifest_path: str | Path, *, chunk_chars: int,
                                 overlap_chars: int, limit: int | None,
                                 allowed_formats: set[str]) -> tuple[list[Chunk], dict]:
    from pypdf import PdfReader
    from src.data.docx_text import extract_docx_body

    manifest_path = Path(manifest_path)
    with manifest_path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ValueError(f"Regulation file manifest is empty: {manifest_path}")
    rows = rows if limit is None else rows[:limit]
    chunks: list[Chunk] = []
    documents = []
    seen_doc_ids = set()
    seen_pdf_pages: dict[str, set[int]] = {}
    formats = set()
    ocr_source_files: dict[str, dict] = {}
    for row in rows:
        required = ("doc_id", "title", "source", "file", "sha256", "doc_type")
        missing = [key for key in required if not row.get(key)]
        if missing:
            raise ValueError(f"Regulation manifest row missing {missing}: {row.get('doc_id')}")
        if row["doc_type"] != "regulation":
            raise ValueError(f"Non-regulation file in regulation manifest: {row['doc_id']}")
        if row["doc_id"] in seen_doc_ids:
            raise ValueError(f"Duplicate regulation doc_id: {row['doc_id']}")
        seen_doc_ids.add(row["doc_id"])
        path = _resolve_manifest_file(manifest_path, row["file"])
        if not path.is_file():
            raise FileNotFoundError(path)
        source_format = path.suffix.lower().lstrip(".")
        if source_format not in allowed_formats:
            raise ValueError(f"Unsupported regulation source format: {source_format}")
        if row.get("source_format") and row["source_format"].lower() != source_format:
            raise ValueError(f"Regulation source format disagrees with file: {row['doc_id']}")
        native_parser = parser_for_mode(row.get('pdf_text_mode'))
        if source_format != 'pdf' and native_parser == LAYOUT:
            raise ValueError('Layout PDF text mode requires an original PDF')
        source_sha = sha256_file(path)
        if source_sha.lower() != row["sha256"].lower():
            raise ValueError(f"Regulation file SHA256 mismatch: {row['doc_id']}")
        formats.add(source_format)
        source_role = row.get("source_role") or "unspecified"
        if source_role not in {"unspecified", "unknown", "normative_text", "amendment"}:
            raise ValueError(f"Non-normative or unsupported declared source_role: {source_role}")
        common_meta = {
            "corpus_type": "regulation", "source_format": source_format,
            "source_role": source_role, "source_role_status": "declared_unverified",
            "source_identity_status": "declared_unverified",
            "publication_date": row.get("publication_date") or None,
            "effective_from": row.get("effective_from") or None,
            "effective_to": row.get("effective_to") or None,
            "version_id": row.get("version_id") or None,
            "applicability_status": "metadata_unverified",
            "source_document_sha256": source_sha, "source_file": str(path.resolve()),
        }
        if source_format == "docx":
            if row.get("ocr_manifest") or row.get("ocr_manifest_sha256"):
                raise ValueError("Regulation OCR sidecars require an original PDF")
            if row.get("page_count"):
                raise ValueError("DOCX has no physical PDF page_count; leave it empty")
            if (row.get("physical_pages") or "").strip():
                raise ValueError("DOCX has no physical PDF pages; physical_pages must be empty")
            text, extraction = extract_docx_body(path)
            doc_chunks = 0
            for window_number, (start, end, excerpt) in enumerate(
                    _split_page(text, chunk_chars, overlap_chars), start=1):
                chunks.append(Chunk(
                    chunk_id=f"{row['doc_id']}-DOCX-W{window_number:03d}",
                    doc_id=row["doc_id"], doc_title=row["title"], doc_type="regulation",
                    source=row["source"], clause_no=None, text=excerpt,
                    meta={**common_meta, "source_text_origin": "docx_main_body",
                          "source_text_parser": extraction["parser"],
                          "source_text_char_start": start, "source_text_char_end": end,
                          "source_text_sha256": extraction["text_sha256"],
                          "docx_extraction": extraction},
                ))
                doc_chunks += 1
            documents.append({"doc_id": row["doc_id"], "source_file": str(path.resolve()),
                              "source_file_sha256": source_sha, "source_format": "docx",
                              "version_id": common_meta["version_id"], "chunk_count": doc_chunks,
                              "empty_body": not bool(text.strip()), "extraction": extraction})
            continue
        if not row.get("page_count"):
            raise ValueError(f"Regulation PDF manifest row missing page_count: {row['doc_id']}")
        pdf_sha = source_sha
        reader = PdfReader(path, strict=False)
        if reader.is_encrypted and not reader.decrypt(""):
            raise ValueError(f"Encrypted regulation PDF: {row['doc_id']}")
        if len(reader.pages) != int(row["page_count"]):
            raise ValueError(f"Regulation PDF page count mismatch: {row['doc_id']}")
        selected_pages = _parse_physical_pages(row.get("physical_pages"), len(reader.pages))
        if bool(row.get("ocr_manifest")) != bool(row.get("ocr_manifest_sha256")):
            raise ValueError("Regulation OCR requires ocr_manifest and ocr_manifest_sha256 together")
        ocr_pages, ocr_report = {}, None
        if row.get("ocr_manifest"):
            from src.data.evidence_sources import local_path
            from src.data.regulation_ocr import load_regulation_ocr_sidecar
            ocr_pages, ocr_report = load_regulation_ocr_sidecar(
                local_path(row["ocr_manifest"], manifest_path.parent), row["ocr_manifest_sha256"],
                source_pdf_sha256=pdf_sha, page_count=len(reader.pages),
                selected_pages=set(selected_pages))
            for item in ocr_report["source_files"]:
                old = ocr_source_files.get(item["path"])
                if old is not None and old["sha256"] != item["sha256"]:
                    raise ValueError("Regulation OCR asset changed between manifest rows")
                ocr_source_files[item["path"]] = item
        previous_pages = seen_pdf_pages.setdefault(pdf_sha, set())
        if previous_pages.intersection(selected_pages):
            raise ValueError(f"Overlapping original PDF pages across manifest rows: {row['doc_id']}")
        previous_pages.update(selected_pages)
        page_scan_scope = "selected" if (row.get("physical_pages") or "").strip() else "all"
        doc_chunks = 0
        empty_pages = []
        unusable_pages = []
        ocr_used_pages = []
        overridden_native_pages = []
        for page_number in selected_pages:
            page = reader.pages[page_number - 1]
            native_text = extract_native_text(page, native_parser)
            text = native_text
            ocr_meta = {}
            if page_number in ocr_pages:
                candidate = ocr_pages[page_number]
                text = candidate["text"]
                ocr_used_pages.append(page_number)
                if any(c.isalpha() for c in native_text):
                    overridden_native_pages.append(page_number)
                ocr_meta = {
                    "text_origin": "ocr_unreviewed", "page_text_origin": "ocr_unreviewed",
                    "page_text_parser": "declared_ocr_utf8_frame",
                    "native_page_text_sha256": hashlib.sha256(native_text.encode("utf-8")).hexdigest(),
                    "native_page_text_char_count": len(native_text),
                    "native_page_has_linguistic_text": any(c.isalpha() for c in native_text),
                    "ocr_text_file": candidate["text_file"], "ocr_text_sha256": candidate["text_sha256"],
                    "ocr_image_file": candidate["image_file"], "ocr_image_sha256": candidate["image_sha256"],
                    "ocr_manifest_file": ocr_report["manifest_file"],
                    "ocr_manifest_sha256": ocr_report["manifest_sha256"],
                    "ocr_engine": candidate["engine"], "ocr_rotation_degrees": candidate["rotation_degrees"],
                    "ocr_confidence_available": candidate["confidence_available"],
                    "ocr_review_status_as_declared": candidate["review_status"],
                    "ocr_visual_review_status": "pending_independent_review",
                    "ocr_transcription_accuracy_verified": False,
                    "ocr_image_to_original_page_verified": False,
                }
                if native_parser == LAYOUT:
                    ocr_meta['native_page_text_parser'] = LAYOUT
                    ocr_meta['native_page_text_policy'] = parser_policy(LAYOUT)
            page_sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
            if not text.strip():
                empty_pages.append(page_number)
                continue
            if not any(c.isalpha() for c in text):
                unusable_pages.append(page_number)
                continue
            for window_number, (start, end, excerpt) in enumerate(
                    _split_page(text, chunk_chars, overlap_chars), start=1):
                chunks.append(Chunk(
                    chunk_id=f"{row['doc_id']}-P{page_number:04d}-{'OCR-' if ocr_meta else 'LAYOUT-' if native_parser == LAYOUT else ''}W{window_number:03d}",
                    doc_id=row["doc_id"], doc_title=row["title"], doc_type="regulation",
                    source=row["source"], clause_no=None, text=excerpt,
                    meta={**common_meta,
                        "physical_pdf_page_1based": page_number,
                        "source_pdf_page_count": len(reader.pages),
                        "page_scan_scope": page_scan_scope,
                        "page_selection_status": "declared_unverified",
                        "page_text_parser": native_parser if native_parser == LAYOUT else "pypdf",
                        **({'native_pdf_text_policy': parser_policy(LAYOUT)} if native_parser == LAYOUT and not ocr_meta else {}),
                        "page_text_char_start": start,
                        "page_text_char_end": end,
                        "page_text_sha256": page_sha,
                        "source_pdf_sha256": pdf_sha,
                        "source_pdf_file": str(path.resolve()),
                        **ocr_meta,
                    },
                ))
                doc_chunks += 1
        documents.append({"doc_id": row["doc_id"], "source_file": str(path.resolve()),
                          "source_pdf_sha256": pdf_sha,
                          "source_file_sha256": pdf_sha, "source_format": "pdf",
                          **({'native_pdf_text_policy': parser_policy(LAYOUT)} if native_parser == LAYOUT else {}),
                          "version_id": common_meta["version_id"],
                          "page_count": len(reader.pages), "chunk_count": doc_chunks,
                          "physical_pages_requested": row.get("physical_pages") or None,
                          "selected_physical_pages_1based": selected_pages,
                          "selected_page_count": len(selected_pages),
                          "pages_scanned": len(selected_pages),
                          "page_scan_scope": page_scan_scope,
                          "page_selection_status": "declared_unverified",
                          "empty_text_pages": empty_pages,
                          "nonlinguistic_text_pages": unusable_pages,
                          "ocr_text_pages": ocr_used_pages,
                          "ocr_explicitly_overridden_native_pages": overridden_native_pages,
                          "ocr_sidecar": ocr_report})
    if not chunks:
        raise ValueError("No searchable regulation file text was extracted; blank or nonlinguistic PDF pages need explicit OCR assets")
    used_ocr = any(document.get("ocr_text_pages") for document in documents)
    return chunks, {"manifest": str(manifest_path.resolve()),
                    "manifest_sha256": sha256_file(manifest_path), "documents": documents,
                    "document_count": len(documents), "chunk_count": len(chunks),
                    "source_formats": sorted(formats),
                    "ocr_source_files": [ocr_source_files[key] for key in sorted(ocr_source_files)],
                    "parser": "mixed_native_and_declared_ocr" if used_ocr else "pypdf" if formats == {"pdf"} else "ooxml-main-body-v1" if formats == {"docx"} else "mixed",
                    "parser_version": None if used_ocr else importlib.metadata.version("pypdf") if formats == {"pdf"} else "1" if formats == {"docx"} else None,
                    "parser_versions": {**({"pypdf": importlib.metadata.version("pypdf")} if "pdf" in formats else {}),
                                        **({"ooxml-main-body": "1"} if "docx" in formats else {}),
                                        **({"declared_ocr_utf8_frame": "1"} if used_ocr else {})}}


class DualCorpusRetriever:
    """Run independent annual-report and regulation searches over a shared index."""

    def __init__(self, retriever, chunks: list[Chunk]):
        ids = [c.chunk_id for c in chunks]
        if len(ids) != len(set(ids)):
            raise ValueError("Dual-corpus index contains duplicate chunk IDs")
        self.retriever = retriever
        self.annual_chunks = [c for c in chunks if c.meta.get("corpus_type") == "annual_report"]
        self.regulation_chunks = [c for c in chunks if c.meta.get("corpus_type") == "regulation"]
        if not self.annual_chunks or not self.regulation_chunks:
            raise ValueError("Both annual-report and regulation corpora must be non-empty")

    def search(self, query: str, *, annual_top_k: int = 5,
               regulation_top_k: int = 5, stock_code: str | None = None,
               report_year: int | None = None, temporal_filter: bool = False,
               target_date: str | None = None, target_date_role: str | None = None,
               unknown_temporal: str = 'retain') -> dict:
        if not isinstance(temporal_filter, bool):
            raise ValueError('temporal_filter must be an explicit boolean')
        if not temporal_filter and (target_date is not None or target_date_role is not None
                                    or unknown_temporal != 'retain'):
            raise ValueError('Temporal date/policy arguments require temporal_filter=True')
        regulation_scope = self.regulation_chunks
        temporal_audit = None
        if temporal_filter:
            from src.retrieval.temporal import select_temporal_candidates
            allowed, temporal_audit = select_temporal_candidates(
                regulation_scope, query, target_date=target_date,
                target_date_role=target_date_role, unknown_policy=unknown_temporal)
            regulation_scope = [chunk for chunk in regulation_scope if chunk.chunk_id in allowed]
        annual_scope = self.annual_chunks
        if stock_code is not None:
            annual_scope = [chunk for chunk in annual_scope
                            if str(chunk.meta.get("stock_code", "")).upper()
                            == stock_code.upper()]
        if report_year is not None:
            annual_scope = [chunk for chunk in annual_scope
                            if chunk.meta.get("report_year") == report_year]
        if not annual_scope:
            raise ValueError(f"No annual-report chunks for {stock_code} {report_year}")
        result = {
            "company_evidence": self.retriever.search(query, top_k=annual_top_k,
                                                       pool=annual_scope),
            # Some backends interpret pool=[] as an unrestricted search. An
            # empty temporally eligible rule set must stay empty.
            "regulation_evidence": (self.retriever.search(query, top_k=regulation_top_k,
                                                            pool=regulation_scope)
                                    if regulation_scope else []),
        }
        if temporal_audit is not None:
            result['temporal_filter_audit'] = temporal_audit
        return result

    @staticmethod
    def format_evidence(hits: list[tuple[Chunk, float]], prefix: str = "E") -> str:
        lines = []
        for i, (chunk, _) in enumerate(hits, start=1):
            if chunk.meta.get("corpus_type") == "annual_report":
                location = (f"{chunk.meta['company_name']} {chunk.meta['report_year']}年报，"
                            f"PDF物理第{chunk.meta['physical_pdf_page_1based']}页")
            else:
                clause = f" {chunk.clause_no}" if chunk.clause_no else ""
                metadata = [f"来源={chunk.source}"]
                if 'mapped_page_segments' in chunk.meta:
                    from src.data.page_mapped_chunks import mapped_segments
                    parts = mapped_segments(chunk)
                    pages = '、'.join(str(r['meta']['physical_pdf_page_1based']) for r in parts)
                    metadata.extend([f'PDF物理第{pages}页', '逐页原文坐标分别保存，换页分隔符不是原文'])
                    if any(r['meta'].get('page_text_origin') == 'ocr_unreviewed' for r in parts):
                        metadata.append('含OCR辅助文字，转写与页图对应尚待独立复核')
                    if chunk.meta.get('mapped_strategy') == 'mapped_structure':
                        metadata.append('条款边界候选，尚待独立复核')
                if chunk.meta.get("physical_pdf_page_1based"):
                    metadata.append(f"PDF物理第{chunk.meta['physical_pdf_page_1based']}页")
                if chunk.meta.get("page_scan_scope") == "selected":
                    metadata.append("按声明页范围导入，正文边界未核验")
                if chunk.meta.get("page_text_origin") == "ocr_unreviewed":
                    metadata.append("OCR辅助文字，转写与页图对应尚待独立复核")
                if chunk.meta.get("source_format") == "docx":
                    metadata.append(f"DOCX正文字符区间[{chunk.meta['source_text_char_start']},"
                                    f"{chunk.meta['source_text_char_end']})")
                    if chunk.meta.get("docx_extraction", {}).get("automatic_numbering_present_or_possible"):
                        metadata.append("DOCX自动编号未展开，条号需对照原件")
                if chunk.meta.get("source_identity_status") == "declared_unverified":
                    metadata.append("来源身份与版本声明未核验")
                for label, key in (("版本", "version_id"), ("发布日期", "publication_date"),
                                   ("生效日期", "effective_from"), ("失效日期", "effective_to")):
                    if chunk.meta.get(key):
                        metadata.append(f"{label}={chunk.meta[key]}")
                if chunk.meta.get("applicability_status") == "metadata_unverified":
                    metadata.append("法规时点适用性未核验")
                location = f"{chunk.doc_title}{clause}；" + "；".join(metadata)
            lines.append(f"[{prefix}{i}] {location}\n{chunk.text}")
        return "\n\n".join(lines) if lines else "未检索到足以支持此类证据的内容。"

