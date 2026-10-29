"""Align future evaluation wording with the no-new-human-label decision."""
from pathlib import Path
from docx import Document

root = Path(__file__).resolve().parents[1]
edits = [
    ('results/paper/condensed_candidate_20261028_01/年报与法规双源RAG_引用编号审计候选稿_待终审.docx',
     'results/paper/condensed_candidate_20261028_01/年报与法规双源RAG_无新增人工标注候选稿_待终审.docx',
     '后续若需提出这些更强主张，应分别建立独立问题集、相关证据标注和盲评协议。',
     '后续评测不新增人工标注；在缺少独立可信参考的情况下，自动匹配指标仅供诊断，不足以支持这些更强主张。'),
    ('results/paper/english_translation_current_20261028_01/Controlled_Evaluation_Dual_Source_RAG_citation_id_audit_20261029.docx',
     'results/paper/english_translation_current_20261028_01/Controlled_Evaluation_Dual_Source_RAG_no_new_human_labels_20261029.docx',
     'Stronger claims would require separate question sets, relevance judgments, and blinded review protocols.',
     'Future evaluation will add no human annotations; without independent, trustworthy references, automated matching metrics remain diagnostic and cannot support these stronger claims.')]
for source, target, old, new in edits:
    doc = Document(root/source)
    runs = [r for p in doc.paragraphs for r in p.runs if old in r.text]
    if len(runs) != 1:
        raise ValueError('Expected exactly one occurrence in a single run')
    runs[0].text = runs[0].text.replace(old, new)
    doc.save(root/target)
    print(root/target)
