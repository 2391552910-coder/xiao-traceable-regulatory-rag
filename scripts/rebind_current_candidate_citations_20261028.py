from __future__ import annotations
import hashlib
import json
import re
import zipfile
from pathlib import Path
from docx import Document

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'results/paper/condensed_candidate_20261028_01'
CANDIDATES = {
    'framework_audited': BASE / '年报与法规双源RAG_统一主文_评测框架表述收紧候选稿_待终审.docx',
    'literature_and_case_audited': BASE / '年报与法规双源RAG_统一主文_补充CFinRAG相关工作候选稿_待终审.docx',
    'source_deletion': BASE / '年报与法规双源RAG_统一主文_来源缺失配对口径修订候选稿_待终审.docx',
    'current': BASE / '年报与法规双源RAG_统一主文_回放范围限定候选稿_待终审.docx',
}
RECEIPT = BASE / 'evaluation_framework_wording_revision_receipt_20261028.json'
OUTPUT = BASE / 'current_candidate_citation_rebind_20261028.json'
CITATION = re.compile(r'\[\s*(\d{1,2})(?:\s*[-–]\s*(\d{1,2}))?\s*\]')
REFERENCE = re.compile(r'^\[(\d+)\]\s+')

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def read(path: Path):
    doc = Document(path)
    paragraphs = [p.text for p in doc.paragraphs]
    citation_paragraphs = {i: text for i, text in enumerate(paragraphs) if CITATION.search(text)}
    reference_entries = [p.strip() for p in paragraphs if REFERENCE.match(p.strip())]
    cited_ids = set()
    for text in citation_paragraphs.values():
        for first, last in CITATION.findall(text):
            lo, hi = int(first), int(last) if last else int(first)
            cited_ids.update(range(lo, hi + 1))
    tables = [[ [cell.text for cell in row.cells] for row in table.rows ] for table in doc.tables]
    with zipfile.ZipFile(path) as z:
        media = {name: sha(z.read(name)) for name in z.namelist() if name.startswith('word/media/') and not name.endswith('/')}
    return {'doc': doc, 'paragraphs': paragraphs, 'citation_paragraphs': citation_paragraphs,
            'reference_entries': reference_entries, 'cited_ids': sorted(cited_ids), 'tables': tables, 'media': media}

def file_sha(path: Path) -> str:
    return sha(path.read_bytes())

docs = {key: read(path) for key, path in CANDIDATES.items()}
receipt = json.loads(RECEIPT.read_text(encoding='utf-8'))
framework_text = docs['framework_audited']['paragraphs'][29]
source_text = docs['literature_and_case_audited']['paragraphs'][29]
intermediate_text = docs['source_deletion']['paragraphs'][29]
current_text = docs['current']['paragraphs'][29]
expected_framework_hash = receipt['change']['new_text_sha256_utf8']
assert sha(framework_text.encode('utf-8')) == expected_framework_hash
assert intermediate_text == framework_text and current_text == framework_text
assert {k:v for k,v in docs['literature_and_case_audited']['citation_paragraphs'].items() if k != 29} == {k:v for k,v in docs['source_deletion']['citation_paragraphs'].items() if k != 29}
assert docs['literature_and_case_audited']['reference_entries'] == docs['source_deletion']['reference_entries']
assert docs['source_deletion']['citation_paragraphs'] == docs['current']['citation_paragraphs']
assert docs['source_deletion']['reference_entries'] == docs['current']['reference_entries']
assert docs['source_deletion']['cited_ids'] == docs['current']['cited_ids'] == list(range(1, 32))
assert docs['source_deletion']['tables'] == docs['current']['tables']
assert docs['source_deletion']['media'] == docs['current']['media']
changed_latest = [i for i, (a, b) in enumerate(zip(docs['source_deletion']['paragraphs'], docs['current']['paragraphs'])) if a != b]
assert changed_latest == [131], changed_latest
assert not CITATION.search(docs['source_deletion']['paragraphs'][131])

result = {
    'audit_date': '2026-10-28',
    'status': 'passed_scoped_current_candidate_citation_version_binding',
    'current_candidate': {'path': str(CANDIDATES['current'].relative_to(ROOT)).replace('\\', '/'), 'sha256': file_sha(CANDIDATES['current']), 'paragraph_count': len(docs['current']['paragraphs']), 'table_count': len(docs['current']['tables']), 'media_part_count': len(docs['current']['media'])},
    'lineage': {key: {'path': str(path.relative_to(ROOT)).replace('\\', '/'), 'sha256': file_sha(path)} for key, path in CANDIDATES.items()},
    'citation_inventory': {'citation_paragraph_count': len(docs['current']['citation_paragraphs']), 'reference_count': len(docs['current']['reference_entries']), 'cited_ids': docs['current']['cited_ids'], 'uncited_reference_ids': []},
    'version_checks': {
        'source_deletion_to_current_changed_body_paragraphs_zero_based': changed_latest,
        'citation_paragraphs_identical_source_deletion_to_current': True,
        'only_citation_paragraph_changed_from_predecessor': [29],
        'new_paragraph_29_matches_framework_revision_receipt': True,
        'bibliography_identical_source_deletion_to_current': True,
        'all_12_table_texts_identical_source_deletion_to_current': True,
        'all_21_media_hashes_identical_source_deletion_to_current': True,
        'paragraph_29_matches_evaluation_framework_revision_receipt': True,
        'paragraph_29_sha256_utf8': sha(current_text.encode('utf-8')),
        'source_deletion_and_replay_scope_edits_are_not_citation_bearing': True
    },
    'inherited_source_audits': [
        {'references': '[1]-[11]', 'audit': 'retrieval_corpus_citation_audit_20261028.md'},
        {'references': '[12]-[23]', 'audit': 'rag_method_eval_citation_audit_20261028.md; evaluation_framework_wording_revision_receipt_20261028.json'},
        {'references': '[24]-[27]', 'audit': 'reasoning_budget_claim_audit_20261029.json; current_candidate_regulatory_source_audit_20261028.md'},
        {'references': '[28]-[29]', 'audit': 'annual_report_benchmark_citation_audit_20261028.md'},
        {'references': '[30]', 'audit': 'cfinrag_citation_audit_20261028.md'},
        {'references': '[31]', 'audit': 'case_citation_reference_revision_receipt_20261028.json'}
    ],
    'limitations': [
        'This verifies citation text, reference IDs, tables, and media continuity for the named candidate versions; it does not reread all cited papers or establish semantic support for every factual claim.',
        'Grouped source audits remain scoped to their documented claims and versions; this is not a full-source reread or a full manuscript semantic audit.',
        'It does not validate all 355 scored answers, historical legal applicability, author metadata, target-journal formatting, or acceptance readiness.'
    ],
    'new_model_calls': 0,
    'new_human_labels': 0
}
OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result, ensure_ascii=False, indent=2))


