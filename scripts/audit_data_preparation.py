"""Read-only data readiness audit; historical download status is not current file availability."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def annual_report_availability(root: Path, report_path: Path) -> list[dict]:
    with report_path.open(encoding='utf-8-sig', newline='') as f:
        records = list(csv.DictReader(f))
    rows = []
    for record in records:
        name = record.get('file', '')
        path = (root / name).resolve() if name else None
        inside = path is not None and path.is_relative_to(root.resolve())
        present = bool(inside and path.is_file())
        valid_header = False
        if present:
            with path.open('rb') as f:
                valid_header = f.read(5) == b'%PDF-'
        rows.append({'stock_code': record['stock_code'], 'name': record['name'],
                     'year': record['year'], 'historical_status': record['status'],
                     'expected_file': name, 'file_present': present,
                     'pdf_header_valid': valid_header,
                     'availability': ('present_pdf' if valid_header else 'invalid_pdf' if present
                                      else 'unsafe_or_empty_path' if not inside else 'missing'),
                     'bytes': path.stat().st_size if present else 0})
    return rows


def audit(out: Path) -> dict:
    from src.config import load_config
    from src.data.benchmark import load_benchmark
    from scripts.compile_independent_review import check_artifacts

    check_artifacts()
    benchmark = load_benchmark(load_config())
    structural = benchmark.audit()
    companies = ROOT / 'data/companies'
    annual = annual_report_availability(ROOT, companies / 'download_report.csv')
    with (companies / 'sampling_frame.csv').open(encoding='utf-8-sig', newline='') as f:
        frame = list(csv.DictReader(f))
    manifest = json.loads((ROOT / 'data/knowledge_base/manifest.json').read_text())
    registered = {d['doc_id'] for d in manifest}
    facts = []
    for path in sorted(companies.glob('*.json')):
        data = json.loads(path.read_text())
        demonstration = path.name.startswith('sample_') or '示例' in data.get('stock_name', '')
        records = data.get('facts', [])
        linked = [f for f in records if isinstance(f, dict) and f.get('source_document')
                  and f.get('page') is not None and f.get('quote')]
        facts.append({'file': str(path.relative_to(ROOT)), 'demonstration': demonstration,
                      'fact_records': len(records), 'source_linked_fact_records': len(linked),
                      'note': 'Presence of source fields alone does not verify a fact.'})
    generation_path = ROOT / 'data/annotation/generation_annotation_template.csv'
    with generation_path.open(encoding='utf-8-sig', newline='') as f:
        generation = list(csv.DictReader(f))
    completed = [r for r in generation if r.get('sample_id', '').strip()
                 and r.get('citation_supported') in {'0', '1'} and r.get('fact_error') in {'0', '1'}]
    reviews = ROOT / 'data/annotation/reviews/independent_20261013'
    review = json.loads((reviews / 'review_summary.json').read_text())
    policy_path = Path('/etc/codex/network-policy.json')
    policy = json.loads(policy_path.read_text()) if policy_path.exists() else {}
    allowed = {r['host'] for r in policy.get('http_network_policy', {}).get('egress_rules', [])}
    corpus_dates_missing = [d['doc_id'] for d in benchmark.documents.values() if not d.get('date')]
    report = {'audited_at_utc': datetime.now(timezone.utc).isoformat(), 'audit_completed': True,
              'status': 'data_preparation_incomplete', 'formal_data_ready': False,
              'root': str(ROOT), 'original_inputs_modified': False,
              'frozen_development_hashes_verified': True, 'benchmark_hashes': benchmark.hashes,
              'corpus': {'loaded_documents': len(benchmark.documents),
                         'document_types': dict(Counter(d['doc_type'] for d in benchmark.documents.values())),
                         'registered_manifest_documents': len(manifest),
                         'unregistered_loaded_document_ids': sorted(set(benchmark.documents) - registered),
                         'missing_metadata_date_ids': corpus_dates_missing,
                         'historical_chunks': len(benchmark.chunks),
                         'duplicate_document_groups': structural['duplicate_document_groups'],
                         'positive_chunks_with_structural_issues': len(structural['structural_issues']),
                         'positive_chunk_issue_counts': dict(Counter(flag for r in structural['structural_issues'] for flag in r['flags'])),
                         'legal_version_and_temporal_applicability_verified': False,
                         'formal_status': 'not_ready'},
              'annual_reports': {'sampling_frame_companies': len(frame), 'historical_manifest_rows': len(annual),
                                 'historical_status_counts': dict(Counter(r['historical_status'] for r in annual)),
                                 'current_availability_counts': dict(Counter(r['availability'] for r in annual)),
                                 'available_pdf_count': sum(r['pdf_header_valid'] for r in annual),
                                 'manifest_sha256': hashlib.sha256((companies / 'download_report.csv').read_bytes()).hexdigest(),
                                 'required_source_hosts_in_startup_allowlist': {h: h in allowed for h in ['www.cninfo.com.cn', 'static.cninfo.com.cn']},
                                 'formal_status': 'not_ready'},
              'company_facts': {'files': facts,
                                'non_demonstration_fact_files': sum(not f['demonstration'] for f in facts),
                                'source_linked_fact_records': sum(f['source_linked_fact_records'] for f in facts if not f['demonstration']),
                                'formal_status': 'not_ready'},
              'retrieval_evaluation': {'development_queries': len(benchmark.queries),
                                      'independent_review': {k: review[k] for k in ['n_queries', 'n_candidates', 'n_direct_positive', 'n_broad_positive', 'scope']},
                                      'default_benchmark_uses_independent_review': False,
                                      'candidate_pool_exhaustiveness_verified': False,
                                      'registered_heldout_final_test_set': False,
                                      'formal_status': 'not_ready'},
              'generation_evaluation': {'template_rows': len(generation),
                                       'completed_template_judgments': len(completed),
                                       'registered_real_generation_validation_set': False,
                                       'formal_status': 'not_ready'},
              'next_actions': ['恢复 39 家年报原文，记录来源 URL、公告日期、报告年度和文件 SHA256；保留旧下载清单。',
                               '提取带 PDF 页码、原文引句及文档哈希的公司事实；缺失指标显式标记，演示样本隔离。',
                               '审计法规版本、时间适用性、重复和切分，建立新证据坐标及标签迁移记录，保留旧冻结版本。',
                               '补齐检索候选池，重新冻结独立复核版本，并按问题族建立未用于开发的最终测试集。',
                               '建立真实生成输出与引用、事实错误、支持关系的核验集，保留抽样和复核记录。'],
              'limitations': ['本审计检查本工作区文件和已登记产物，不认证法规现行有效性或事实语义正确性。',
                              '网络清单检查不替代实际下载探测。']}
    with (out / 'annual_report_availability.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(annual[0]))
        writer.writeheader()
        writer.writerows(annual)
    (out / 'data_readiness.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir', required=True)
    args = parser.parse_args()
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=False)
    report = audit(out)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
