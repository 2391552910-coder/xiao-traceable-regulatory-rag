"""Deterministic, body-text-only DOCX extraction without manufacturing pages."""
from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile

PARSER_ID = "ooxml-main-body-v1"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def extract_docx_body(path: str | Path) -> tuple[str, dict]:
    """Read body text and report layout/features this parser cannot render.

    Paragraphs, table cells and table rows add LF, TAB and LF respectively.
    Character coordinates refer to this exact serialization, not to Word pages
    or XML byte offsets. No relationship or embedded code is executed.
    """
    with ZipFile(path) as package:
        if package.namelist().count("word/document.xml") != 1:
            raise ValueError("DOCX must contain exactly one word/document.xml")
        xml = package.read("word/document.xml")
        styles = package.read("word/styles.xml") if "word/styles.xml" in package.namelist() else b""
    root = ET.fromstring(xml)
    body = root.find(W + "body")
    if body is None:
        raise ValueError("DOCX main document has no body")
    parts: list[str] = []

    def visit(element) -> None:
        if element.tag in {W + "del", W + "moveFrom"}:
            return
        if element.tag == W + "t":
            parts.append(element.text or "")
            return
        if element.tag == W + "tab":
            parts.append("\t")
            return
        if element.tag in {W + "br", W + "cr"}:
            parts.append("\n")
            return
        for child in element:
            visit(child)
        if element.tag in {W + "p", W + "tr"}:
            parts.append("\n")
        elif element.tag == W + "tc":
            parts.append("\t")

    visit(body)
    text = "".join(parts)
    style_numbering = bool(styles and ET.fromstring(styles).find(".//" + W + "numPr") is not None)
    return text, {
        "parser": PARSER_ID,
        "main_document_xml_sha256": hashlib.sha256(xml).hexdigest(),
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "characters": len(text),
        "coordinate_unit": "Unicode code points; zero-based, right endpoint excluded",
        "serialization": "w:t unchanged; w:tab=TAB; w:br/w:cr=LF; paragraph/row end=LF; cell end=TAB",
        "parser_scope": "main document body; no headers, footers, footnotes or rendered page numbers",
        "automatic_numbering_present_or_possible": body.find(".//" + W + "numPr") is not None or style_numbering,
        "automatic_numbering_rendered": False,
        "text_boxes_present": body.find(".//" + W + "txbxContent") is not None,
        "hidden_runs_present": body.find(".//" + W + "vanish") is not None,
        "cached_field_results_used": body.find(".//" + W + "instrText") is not None,
        "tracked_deletions_and_move_from_excluded": True,
        "source_identity_verified": False,
        "physical_pdf_pages": None,
    }
