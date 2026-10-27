"""Portable, integrity-checked storage for a dual-corpus dense index."""
from __future__ import annotations

import csv
import hashlib
import hmac
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

import numpy as np

from src.config import ROOT
from src.data.clause_splitter import Chunk


FORMAT_VERSION = 2
PROJECT_ROOT_MARKER = "$PROJECT_ROOT/"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _portable_paths(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _portable_paths(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_portable_paths(item) for item in value]
    if isinstance(value, tuple):
        return [_portable_paths(item) for item in value]
    if isinstance(value, str):
        if value.startswith("file://"):
            parsed = urlsplit(value)
            raw_path = unquote(parsed.path)
            if parsed.netloc and parsed.netloc.lower() != "localhost":
                raw_path = f"//{parsed.netloc}{raw_path}"
            if len(raw_path) >= 3 and raw_path[0] == "/" and raw_path[2] == ":":
                raw_path = raw_path[1:]
            candidate = Path(raw_path)
            if candidate.is_absolute():
                try:
                    relative = candidate.resolve().relative_to(ROOT.resolve())
                except (OSError, ValueError):
                    return value
                return "file://" + PROJECT_ROOT_MARKER + relative.as_posix()
        candidate = Path(value)
        if candidate.is_absolute():
            try:
                relative = candidate.resolve().relative_to(ROOT.resolve())
            except (OSError, ValueError):
                return value
            return PROJECT_ROOT_MARKER + relative.as_posix()
    return value


def _restore_project_paths(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _restore_project_paths(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_restore_project_paths(item) for item in value]
    if isinstance(value, str) and value.startswith("file://" + PROJECT_ROOT_MARKER):
        relative = value[len("file://" + PROJECT_ROOT_MARKER):].replace("/", os.sep)
        return _resolve_project_relative(relative).as_uri()
    if isinstance(value, str) and value.startswith(PROJECT_ROOT_MARKER):
        relative = value[len(PROJECT_ROOT_MARKER):].replace("/", os.sep)
        return str(_resolve_project_relative(relative))
    return value


def _resolve_project_relative(relative: str) -> Path:
    root = ROOT.resolve()
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("Portable project path escapes the project root") from exc
    return candidate


def _artifact_file(directory: Path, filename: str) -> Path:
    root = directory.resolve()
    candidate = (root / filename).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("Index payload path escapes the artifact directory") from exc
    return candidate


def _chunk_record(chunk: Chunk) -> dict[str, Any]:
    return _portable_paths({
        "chunk_id": chunk.chunk_id,
        "doc_id": chunk.doc_id,
        "doc_title": chunk.doc_title,
        "doc_type": chunk.doc_type,
        "source": chunk.source,
        "clause_no": chunk.clause_no,
        "text": chunk.text,
        "dimension": chunk.dimension,
        "meta": chunk.meta,
    })


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _source_path(path_value: str) -> Path:
    value = str(path_value)
    if value.startswith("file://"):
        parsed = urlsplit(value)
        raw_path = unquote(parsed.path)
        if parsed.netloc and parsed.netloc.lower() != "localhost":
            # Preserve Windows UNC shares such as file://server/share/a.pdf.
            return Path(f"//{parsed.netloc}{raw_path}").resolve()
        if len(raw_path) >= 3 and raw_path[0] == "/" and raw_path[2] == ":":
            raw_path = raw_path[1:]
        return Path(raw_path).resolve()
    return Path(value).resolve()


def _recover_legacy_source_paths(chunks: list[Chunk], provenance: dict) -> dict:
    """Locate v1 files using recorded hashes, without changing source bytes.

    Older indices kept PDF URLs and hashes, but not local annual PDF paths.
    Their hash-pinned CSV can recover the path. OCR run/release records are
    current locators only: text/image bytes must match the v1 chunk hashes.
    This does not retroactively certify historical OCR run metadata.
    """
    recovered = dict(provenance)
    annual = dict(provenance.get("annual_reports", {}))
    reports = [dict(report) for report in annual.get("reports", [])]
    missing = [report for report in reports if not report.get("source_file")]
    if missing:
        manifest_value = annual.get("manifest")
        digest = str(annual.get("manifest_sha256", "")).lower()
        if not manifest_value or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("Legacy annual path recovery requires a recorded manifest SHA256")
        manifest_path = _source_path(manifest_value)
        if not hmac.compare_digest(_sha256_file(manifest_path), digest):
            raise ValueError(f"Index source SHA256 mismatch: {manifest_path}")
        with manifest_path.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
        for report in missing:
            matches = [row for row in rows
                       if row.get("stock_code") == str(report.get("stock_code", ""))
                       and row.get("year") == str(report.get("report_year", ""))]
            if len(matches) != 1:
                raise ValueError("Legacy annual manifest must have exactly one matching "
                                 f"company/year row: {report.get('stock_code')}")
            row = matches[0]
            pdf_sha = str(report.get("source_pdf_sha256", "")).lower()
            if (not re.fullmatch(r"[0-9a-f]{64}", pdf_sha)
                    or row.get("sha256", "").lower() != pdf_sha):
                raise ValueError("Legacy annual manifest PDF SHA256 conflicts with report")
            if (row.get("status") not in {"imported", "downloaded"}
                    or row.get("identity_verified", "").lower() != "true"):
                raise ValueError("Legacy annual manifest row is not identity-verified")
            file_value = row.get("file")
            if not file_value or urlsplit(file_value).scheme.lower() in {"http", "https"}:
                raise ValueError("Legacy annual manifest has no local PDF path")
            path = Path(file_value)
            if not path.is_absolute():
                beside = manifest_path.parent / path
                path = beside if beside.is_file() else ROOT / path
            report["source_file"] = str(path.resolve())
    if annual:
        annual["reports"] = reports
        recovered["annual_reports"] = annual

    ocr_chunks = [chunk for chunk in chunks if
                  (chunk.meta or {}).get("ocr_text_sha256") or
                  str((chunk.meta or {}).get("page_text_origin", "")).startswith("ocr_")]
    if ocr_chunks and not annual.get("ocr_source_files"):
        from src.data.document_corpora import _load_annual_ocr_sidecar

        locator = provenance.get("annual_ocr_run_dir")
        if not locator:
            raise ValueError("Legacy OCR chunks have no OCR run locator")
        root = Path(locator)
        if not root.is_absolute():
            root = ROOT / root
        pages = _load_annual_ocr_sidecar(root)
        sources = {}
        for chunk in ocr_chunks:
            meta = chunk.meta or {}
            key = (meta.get("stock_code"), int(meta["physical_pdf_page_1based"]))
            text_sha = str(meta.get("ocr_text_sha256", "")).lower()
            image_sha = str(meta.get("ocr_image_sha256", "")).lower()
            if not all(re.fullmatch(r"[0-9a-f]{64}", value)
                       for value in (text_sha, image_sha)):
                raise ValueError("Legacy OCR chunk is missing recorded text/image SHA256")
            matches = [page for page in pages.get(key, [])
                       if page["text_sha256"] == text_sha
                       and page["image_sha256"] == image_sha
                       and page["source_pdf_sha256"] == meta.get("source_pdf_sha256")
                       and page["run_id"] == meta.get("ocr_run_id")
                       and page["rotation_degrees"] == meta.get("ocr_rotation_degrees")]
            if len(matches) != 1:
                raise ValueError(f"Legacy OCR source hashes/identity do not resolve: {chunk.chunk_id}")
            page = matches[0]
            start, end = meta["page_text_char_start"], meta["page_text_char_end"]
            if (hashlib.sha256(page["text"].encode("utf-8")).hexdigest()
                    != meta.get("page_text_sha256") or
                    page["text"][start:end] != chunk.text):
                raise ValueError(f"Legacy OCR text coordinates mismatch: {chunk.chunk_id}")
            for path_key, sha, role in (("text_file", text_sha, "ocr_text"),
                                         ("image_file", image_sha, "ocr_page_image")):
                path = page[path_key]
                sources[path] = {"path": path, "sha256": sha, "roles": [role]}
        annual["ocr_source_files"] = [sources[path] for path in sorted(sources)]
        recovered["legacy_ocr_recovery"] = {
            "text_and_image_hashes_pinned_in_v1": True,
            "run_and_release_hashes_pinned_in_v1": False,
            "run_and_release_used_as_current_locators_only": True,
        }
    return recovered


def _collect_source_inventory(chunks: list[Chunk], provenance: dict, *,
                             require_expected_hash: bool = False) -> list[dict[str, Any]]:
    """Collect and verify every local source file needed to audit this index."""
    files: dict[str, dict[str, Any]] = {}

    def add(path_value: str | Path | None, expected_sha: str | None, role: str) -> None:
        if not path_value:
            return
        if require_expected_hash and not expected_sha:
            raise ValueError(f"Legacy index has no recorded source SHA256 for {path_value}")
        path = _source_path(str(path_value))
        key = str(path)
        record = files.get(key)
        if record is not None:
            if expected_sha and record["sha256"] != str(expected_sha).lower():
                raise ValueError(f"Index source SHA256 mismatch: {path}")
            record["roles"].add(role)
            return
        if not path.is_file():
            raise FileNotFoundError(f"Index source file is missing: {path}")
        actual = _sha256_file(path)
        if expected_sha and actual != str(expected_sha).lower():
            raise ValueError(f"Index source SHA256 mismatch: {path}")
        record = {"path": key, "sha256": actual, "roles": set()}
        files[key] = record
        record["roles"].add(role)

    add(provenance.get("source_manifest"), provenance.get("source_manifest_sha256"),
        "source_manifest")

    annual = provenance.get("annual_reports", {})
    source_by_doc_id: dict[str, tuple[str, str | None, str]] = {}
    if isinstance(annual, dict):
        add(annual.get("manifest"), annual.get("manifest_sha256"),
            "annual_report_manifest")
        for report in annual.get("reports", []):
            add(report.get("source_file"), report.get("source_pdf_sha256"),
                "annual_report_pdf")
            if report.get("stock_code") and report.get("report_year"):
                code = re.sub(r"\W", "", str(report["stock_code"]))
                doc_id = f"AR-{code}-{int(report['report_year'])}"
                source_by_doc_id[doc_id] = (
                    str(report.get("source_file", "")),
                    report.get("source_pdf_sha256"), "annual_report")
        for source in annual.get("ocr_source_files", []):
            for role in source.get("roles", ["annual_report_ocr_source"]):
                add(source.get("path"), source.get("sha256"), str(role))

    def collect_regulations(report: dict, manifest_role: str) -> None:
        add(report.get("manifest"), report.get("manifest_sha256"), manifest_role)
        for source in report.get("ocr_source_files", []):
            for role in source.get("roles", ["regulation_ocr_source"]):
                add(source.get("path"), source.get("sha256"), str(role))
        for document in report.get("documents", []):
            add(document.get("source_file"),
                document.get("source_pdf_sha256") or document.get("source_file_sha256"),
                "regulation_source")
            if document.get("doc_id") and document.get("source_file"):
                source_by_doc_id[str(document["doc_id"])] = (
                    str(document["source_file"]),
                    document.get("source_pdf_sha256") or
                    document.get("source_file_sha256"), "regulation")
        # Uploaded manifests are nested beside the legacy TXT report by the
        # dual-corpus builder. Pin their metadata bytes as well as source files.
        for key, role in (("uploaded_pdf_manifest", "regulation_pdf_manifest"),
                          ("uploaded_file_manifest", "regulation_file_manifest")):
            nested = report.get(key)
            if isinstance(nested, dict):
                collect_regulations(nested, role)

    regulations = provenance.get("regulations", {})
    if isinstance(regulations, dict):
        collect_regulations(regulations, "regulation_pdf_manifest")

    # Chunk metadata is the final authority for files that actually contributed
    # evidence. It also catches a missing manifest entry in an otherwise valid
    # provenance report.
    from dataclasses import replace
    from src.data.page_mapped_chunks import source_metas
    for chunk in (replace(c, meta=m) for c in chunks for m in source_metas(c)):
        meta = chunk.meta or {}
        mapped_source = source_by_doc_id.get(chunk.doc_id)
        path = (meta.get("source_pdf_file") or meta.get("source_file") or
                (mapped_source[0] if mapped_source else None) or chunk.source)
        digest = (meta.get("source_pdf_sha256") or
                  meta.get("source_document_sha256") or
                  (mapped_source[1] if mapped_source else None))
        if not path:
            raise ValueError(f"Chunk has no auditable local source file: {chunk.chunk_id}")
        add(path, digest, f"chunk_source:{meta.get('corpus_type', chunk.doc_type)}")
        if meta.get("corpus_type") == "regulation" and meta.get("page_text_origin") == "ocr_unreviewed":
            for path_key, hash_key, role in (
                    ("ocr_manifest_file", "ocr_manifest_sha256", "regulation_ocr_manifest"),
                    ("ocr_text_file", "ocr_text_sha256", "regulation_ocr_text"),
                    ("ocr_image_file", "ocr_image_sha256", "regulation_ocr_page_image")):
                if not meta.get(path_key) or not meta.get(hash_key):
                    raise ValueError(f"Regulation OCR chunk lacks a bound {role}: {chunk.chunk_id}")
                add(meta[path_key], meta[hash_key], role)

    if not files:
        raise ValueError("Index source inventory is empty")
    return [
        {"path": item["path"], "sha256": item["sha256"],
         "roles": sorted(item["roles"])}
        for _, item in sorted(files.items())
    ]


def _verify_source_inventory(inventory: list[dict[str, Any]]) -> None:
    if not isinstance(inventory, list) or not inventory:
        raise ValueError("Index artifact is missing its source inventory")
    seen: set[str] = set()
    for item in inventory:
        if not isinstance(item, dict) or not item.get("path"):
            raise ValueError("Index source inventory contains an invalid entry")
        path = _source_path(item["path"])
        key = str(path)
        if key in seen:
            raise ValueError(f"Index source inventory contains duplicate paths: {path}")
        seen.add(key)
        expected = str(item.get("sha256", "")).lower()
        if not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise ValueError(f"Index source inventory has an invalid SHA256: {path}")
        if not path.is_file():
            raise FileNotFoundError(f"Index source file is missing: {path}")
        if not hmac.compare_digest(_sha256_file(path), expected):
            raise ValueError(f"Index source SHA256 mismatch: {path}")


def encoder_identity(metadata: dict[str, Any]) -> dict[str, Any]:
    """Return fields that can change document or query vector semantics."""
    keys = (
        "backend", "model_name", "requested_revision", "resolved_revision",
        "requested_dtype", "model_dtype", "max_seq_length", "query_prompt_sha256",
        "document_prompt", "normalize_embeddings",
    )
    return {key: metadata.get(key) for key in keys}


def expected_encoder_identity(cfg: dict) -> dict[str, Any]:
    retrieval = cfg["retrieval"]
    backend = retrieval["embedding_backend"]
    if backend not in {"qwen", "bge"}:
        raise ValueError("Persistent dense artifacts currently require a pinned local qwen/bge encoder")
    prompt = retrieval.get("embedding_query_prompt", "")
    return {
        "backend": backend,
        "model_name": retrieval["embedding_model"],
        "requested_revision": retrieval.get("embedding_revision"),
        "requested_dtype": retrieval.get("embedding_dtype"),
        "query_prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "document_prompt": "",
        "normalize_embeddings": True,
    }


def _check_expected_encoder(saved: dict, expected: dict) -> None:
    identity = saved.get("encoder_identity")
    if not isinstance(identity, dict):
        raise ValueError("Index artifact is missing encoder identity")
    mismatches = {key: (expected_value, identity.get(key))
                  for key, expected_value in expected.items()
                  if identity.get(key) != expected_value}
    if mismatches:
        fields = ", ".join(sorted(mismatches))
        raise ValueError(f"Index encoder identity mismatch: {fields}; rebuild the index")


def _native_pdf_frame_policies(chunks):
    from src.data.page_mapped_chunks import source_metas
    from src.data.pdf_text_frames import LAYOUT, metadata_parser, parser_policy
    policies = {}
    for chunk in chunks:
        for meta in source_metas(chunk):
            if meta.get('source_format') == 'pdf' or meta.get('source_pdf_sha256'):
                parser = metadata_parser(meta)
                if parser == LAYOUT:
                    policies[parser] = parser_policy(parser)
    return policies


def _read_index_payload(source: Path, manifest: dict) -> tuple[list[Chunk], np.ndarray]:
    """Read chunks and vectors only after validating their declared hashes."""
    chunk_path = _artifact_file(source, manifest["chunk_file"])
    vector_path = _artifact_file(source, manifest["vector_file"])
    if _sha256_file(chunk_path) != manifest.get("chunk_file_sha256"):
        raise ValueError("Index chunks hash mismatch; artifact may be incomplete or changed")
    if _sha256_file(vector_path) != manifest.get("vector_file_sha256"):
        raise ValueError("Index vectors hash mismatch; artifact may be incomplete or changed")

    chunks = []
    with chunk_path.open("r", encoding="utf-8") as stream:
        for line_no, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            row = _restore_project_paths(json.loads(line))
            try:
                chunks.append(Chunk(**row))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Invalid chunk record at line {line_no}") from exc
    ids = [chunk.chunk_id for chunk in chunks]
    if len(chunks) != manifest.get("chunk_count") or len(ids) != len(set(ids)):
        raise ValueError("Index chunk count or unique-ID validation failed")
    from src.data.page_mapped_chunks import mapped_segments
    for chunk in chunks:
        if 'mapped_page_segments' in (chunk.meta or {}): mapped_segments(chunk)
    if manifest.get('native_pdf_frame_policies', {}) != _native_pdf_frame_policies(chunks):
        raise ValueError('Index native PDF frame policies differ or are missing')

    vectors = np.load(vector_path, mmap_mode="r", allow_pickle=False)
    if list(vectors.shape) != manifest.get("vector_shape") or vectors.shape[0] != len(chunks):
        raise ValueError("Index vector shape does not match its chunks or manifest")
    if str(vectors.dtype) != manifest.get("vector_dtype") or vectors.dtype != np.float32:
        raise ValueError("Index vector dtype is unsupported or changed")
    if not np.isfinite(vectors).all():
        raise ValueError("Index vectors contain non-finite values")
    norms = np.linalg.norm(vectors, axis=1)
    if len(norms) and (float(norms.min()) < 0.98 or float(norms.max()) > 1.02):
        raise ValueError("Index document vectors are not normalized")
    return chunks, vectors


def save_index_artifact(directory: str | Path, chunks: list[Chunk], vectors: np.ndarray,
                        encoding_metadata: dict, provenance: dict) -> dict:
    """Write a new immutable artifact directory. Existing paths are rejected."""
    output = Path(directory)
    if not output.is_absolute():
        output = ROOT / output
    output = output.resolve()
    if output.exists():
        raise FileExistsError(f"Index artifact path already exists: {output}")
    if not chunks:
        raise ValueError("Cannot save an empty index")
    ids = [chunk.chunk_id for chunk in chunks]
    if len(ids) != len(set(ids)):
        raise ValueError("Index artifact requires unique chunk IDs")
    native_policies = _native_pdf_frame_policies(chunks)
    matrix = np.asarray(vectors)
    if matrix.ndim != 2 or matrix.shape[0] != len(chunks):
        raise ValueError("Vector matrix row count must match chunks")
    if matrix.dtype != np.float32:
        matrix = matrix.astype(np.float32)
    if not np.isfinite(matrix).all():
        raise ValueError("Vector matrix contains non-finite values")

    source_inventory = _collect_source_inventory(chunks, provenance)
    portable_inventory = _portable_paths(source_inventory)
    source_inventory_sha256 = hashlib.sha256(
        _canonical_json(portable_inventory)).hexdigest()

    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir()
    chunk_path = output / "chunks.jsonl"
    with chunk_path.open("w", encoding="utf-8", newline="\n") as stream:
        for chunk in chunks:
            stream.write(json.dumps(_chunk_record(chunk), ensure_ascii=False,
                                    sort_keys=True, separators=(",", ":")) + "\n")
    vector_path = output / "document_vectors.npy"
    np.save(vector_path, matrix, allow_pickle=False)
    manifest = {
        "format": "xiao-traceable-dual-index",
        "format_version": FORMAT_VERSION,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "project_root_at_build": PROJECT_ROOT_MARKER,
        "chunk_count": len(chunks),
        "vector_shape": list(matrix.shape),
        "vector_dtype": str(matrix.dtype),
        "chunk_file": chunk_path.name,
        "chunk_file_sha256": _sha256_file(chunk_path),
        "vector_file": vector_path.name,
        "vector_file_sha256": _sha256_file(vector_path),
        "encoder_identity": encoder_identity(encoding_metadata),
        "encoding_metadata": _portable_paths(encoding_metadata),
        "source_inventory": portable_inventory,
        "source_inventory_sha256": source_inventory_sha256,
        "provenance": _portable_paths(provenance),
    }
    manifest_path = output / "index_manifest.json"
    if native_policies:
        manifest['native_pdf_frame_policies'] = native_policies
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
    manifest["manifest_sha256"] = _sha256_file(manifest_path)
    return manifest


def migrate_v1_index_artifact(source_directory: str | Path,
                              target_directory: str | Path, *,
                              expected_encoder: dict,
                              expected_manifest_sha256: str) -> dict:
    """Copy a verified v1 index into a new v2 artifact without re-embedding.

    Migration is deliberately fail-closed: the v1 artifact hashes and encoder
    must verify, and every source needed by its chunks must still be available
    with a matching SHA256. The original directory is never modified.
    """
    source = Path(source_directory)
    if not source.is_absolute():
        source = ROOT / source
    source = source.resolve()
    target = Path(target_directory)
    if not target.is_absolute():
        target = ROOT / target
    target = target.resolve()
    if source == target or source in target.parents:
        raise ValueError("Migration target must be outside the original index directory")
    if target.exists():
        raise FileExistsError(f"Index artifact path already exists: {target}")

    manifest_path = source / "index_manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Index artifact manifest not found: {manifest_path}")
    manifest_bytes = manifest_path.read_bytes()
    old_manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
    expected_digest = str(expected_manifest_sha256).strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected_digest):
        raise ValueError("Expected index manifest SHA256 must contain 64 hexadecimal characters")
    if not hmac.compare_digest(old_manifest_sha, expected_digest):
        raise ValueError("Index manifest SHA256 mismatch; artifact manifest changed")
    old = json.loads(manifest_bytes)
    if (old.get("format") != "xiao-traceable-dual-index"
            or old.get("format_version") != 1):
        raise ValueError("Migration accepts only xiao-traceable-dual-index format version 1")
    _check_expected_encoder(old, expected_encoder)
    chunks, vectors = _read_index_payload(source, old)
    provenance = _restore_project_paths(old.get("provenance", {}))
    if not isinstance(provenance, dict):
        raise ValueError("Legacy index provenance must be a JSON object")
    encoding_metadata = _restore_project_paths(old.get("encoding_metadata"))
    if not isinstance(encoding_metadata, dict):
        raise ValueError("Legacy index encoding metadata must be a JSON object")
    if encoder_identity(encoding_metadata) != old.get("encoder_identity"):
        raise ValueError("Legacy index encoder identity conflicts with encoding metadata")
    provenance = _recover_legacy_source_paths(chunks, provenance)
    inventory = _collect_source_inventory(
        chunks, provenance, require_expected_hash=True)
    _verify_source_inventory(inventory)

    provenance = dict(provenance)
    provenance["artifact_migration"] = {
        "from_format_version": 1,
        "source_manifest_sha256": old_manifest_sha,
        "vectors_reembedded": False,
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.with_name(f".{target.name}.migration-{uuid.uuid4().hex}")
    migrated = save_index_artifact(staging, chunks, vectors, encoding_metadata, provenance)
    # Validate the complete v2 output before publishing the final directory.
    load_index_artifact(
        staging, expected_encoder=expected_encoder,
        expected_manifest_sha256=migrated["manifest_sha256"])
    os.rename(staging, target)
    return migrated


def load_index_artifact(directory: str | Path, *, expected_encoder: dict,
                        expected_manifest_sha256: str | None = None
                        ) -> tuple[list[Chunk], np.ndarray, dict]:
    """Verify the optional external manifest hash and artifact before loading data."""
    source = Path(directory)
    if not source.is_absolute():
        source = ROOT / source
    source = source.resolve()
    manifest_path = source / "index_manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Index artifact manifest not found: {manifest_path}")
    manifest_bytes = manifest_path.read_bytes()
    if expected_manifest_sha256 is not None:
        expected_digest = expected_manifest_sha256.strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", expected_digest):
            raise ValueError("Expected index manifest SHA256 must contain 64 hexadecimal characters")
        actual_digest = hashlib.sha256(manifest_bytes).hexdigest()
        if not hmac.compare_digest(actual_digest, expected_digest):
            raise ValueError("Index manifest SHA256 mismatch; artifact manifest changed")
    manifest = json.loads(manifest_bytes)
    if manifest.get("format") != "xiao-traceable-dual-index" or manifest.get("format_version") != FORMAT_VERSION:
        raise ValueError("Unsupported index artifact format/version")
    _check_expected_encoder(manifest, expected_encoder)

    portable_inventory = manifest.get("source_inventory")
    if not isinstance(portable_inventory, list) or not portable_inventory:
        raise ValueError("Index artifact is missing its source inventory")
    if hashlib.sha256(_canonical_json(portable_inventory)).hexdigest() != manifest.get(
            "source_inventory_sha256"):
        raise ValueError("Index source inventory hash mismatch")
    source_inventory = _restore_project_paths(portable_inventory)
    _verify_source_inventory(source_inventory)

    chunks, vectors = _read_index_payload(source, manifest)

    manifest["directory"] = str(source)
    manifest["manifest_sha256"] = hashlib.sha256(manifest_bytes).hexdigest()
    manifest["provenance"] = _restore_project_paths(manifest.get("provenance", {}))
    manifest["source_inventory"] = source_inventory
    manifest["encoding_metadata"] = _restore_project_paths(
        manifest.get("encoding_metadata", {}))
    return chunks, vectors, manifest
