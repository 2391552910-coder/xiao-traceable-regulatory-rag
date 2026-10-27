"""Read-only-input acceptance audit for the offline adjacent-window experiment."""
from pathlib import Path
import datetime
import json
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.generation.annual_audit_development import file_sha256
from src.generation.comparison import canonical_sha256

RUNS = ROOT / 'results/runs'
FIRST = RUNS / 'adjacent_evidence_development_20261027_01'
READY = RUNS / 'adjacent_evidence_development_20261027_02'


def load(path):
    return json.loads(path.read_bytes())


def audit():
    errors = []
    protocol = load(READY / 'offline_protocol.json')
    analysis = load(READY / 'offline_analysis.json')
    for mapping in ['source_inputs_sha256', 'code_sha256']:
        for name, digest in protocol[mapping].items():
            if file_sha256(ROOT / name) != digest:
                errors.append('Frozen input/runtime changed: ' + name)
    saved = load(READY / 'contexts_saved_before_reference_analysis.json')
    repeated = 0
    contexts = []
    for relative, digest in saved['context_files_sha256'].items():
        path = READY / relative
        if file_sha256(path) != digest:
            errors.append('Saved context artifact changed: ' + relative)
        case = load(path)
        contexts.append(case)
        previous = load(FIRST / relative)
        if case != previous:
            errors.append('Repeated context/trace differs: ' + relative)
        else:
            repeated += 1
        final = case['final_context']
        if case['generated_answer'] is not None or any(v is not None for v in case['answer_quality'].values()):
            errors.append('Offline run invented generated quality: ' + relative)
        if final['reference_tokens'] > 6000:
            errors.append('Context exceeded budget: ' + relative)
        packet = ROOT / 'results/paper/heldout_validation_20261023_01/packets' / (case['question']['question_id'] + '.json')
        initial = load(packet)['context']
        if not final['context'].startswith(initial['context']) or final['source_records'][:len(initial['source_records'])] != initial['source_records']:
            errors.append('Initial evidence changed: ' + relative)
        for stage in case['trace']:
            packing = stage['packing']
            if (not packing['within_token_budget'] or not packing['old_context_is_unchanged_prefix'] or
                    not packing['old_ids_and_source_records_preserved']):
                errors.append('Stage violated preservation: ' + relative)
            selection = stage['selection']
            if 'adjacent' in stage['stage']:
                if selection['reference_labels_read'] or selection['query_terms_used'] or selection['recursive_expansion']:
                    errors.append('Selector used forbidden information: ' + relative)
                for candidate in selection['selected_candidates']:
                    if candidate['adjacent_hop'] != 1:
                        errors.append('Selector expanded beyond one coordinate neighbor')
    if len(contexts) != 48 or repeated != 48:
        errors.append('Expected 48 fully repeated contexts')
    source = load(READY / 'source_verification.json')
    if (source['status'] != 'passed' or source['pdf_files'] != 8 or
            source['used_pages_reparsed'] != len(source['reparsed_pages']) or
            source['used_pages_reparsed'] != 65 or source['unique_chunk_spans'] != 82):
        errors.append('Source reparse receipt incomplete')
    tests = list(ET.parse(READY / 'tests_passed.xml').getroot().iter('testsuite'))
    counts = {k: sum(int(s.get(k, '0')) for s in tests) for k in ['tests', 'failures', 'errors', 'skipped']}
    if counts != dict(tests=170, failures=0, errors=0, skipped=0):
        errors.append('Expected all 170 acceptance tests to pass')
    prepared = RUNS / 'evidence_retention_development_20261026_03'
    prior_protocol = load(prepared / 'generation_protocol.json')
    for relative, digest in prior_protocol['code_and_replay_sha256'].items():
        if file_sha256(ROOT / relative) != digest:
            errors.append('Prior prepared runtime changed: ' + relative)
    if (prepared / 'generation_start.json').exists() or list(prepared.glob('calls/*/*/call[123].json')):
        errors.append('Prior offline-only prepared generation unexpectedly dispatched')
    if any(v is not None for v in analysis['answer_quality'].values()):
        errors.append('Unavailable generation quality must stay null')
    if analysis['new_model_calls'] or analysis['generated_answers']:
        errors.append('Unexpected model execution')
    manifest_path = ROOT.parent / 'github_delivery_20261026_01/upload_manifest.json'
    historical = [r for r in load(manifest_path) if r['path'].startswith('results/paper/heldout_validation_20261023_01/')]
    for row in historical:
        if file_sha256(ROOT / row['path']) != row['sha256']:
            errors.append('Historical published file changed: ' + row['path'])
    case_rows = [r for r in analysis['rows'] if r['question_id'] == 'NEW-600036-2024-AUDIT']
    expected_case = dict(initial=5, fixed_preserve=5, adjacent_rank=5,
                         adjacent_continuation=9, fixed_then_adjacent=5, adjacent_then_fixed=9)
    if {r['mode']: r['case_audit_date_spans_supplied'] for r in case_rows} != expected_case:
        errors.append('Case span supply differs from reported development comparison')
    receipt = dict(status='passed' if not errors else 'failed',
                   checked_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                   new_model_calls=0, generated_answers=0, contexts_checked=len(contexts),
                   repeated_contexts_and_traces_identical=repeated,
                   original_published_files_unchanged=len(historical),
                   prior_prepared_runtime_unchanged=True, prior_prepared_model_calls=0,
                   initial_evidence_and_ids_preserved=True, all_contexts_within_6000=True,
                   local_annual_pdf_files_verified=8, used_annual_pages_reparsed=65,
                   unique_annual_chunk_spans_verified=82, tests=counts,
                   independent_human_validation=False, answer_quality=analysis['answer_quality'],
                   case_date_source_spans=case_rows, github_updated=False,
                   first_attempt_note='01 preserved 48 contexts but lacked PDFium dependency before analysis; 02 repeats unchanged retrieval code with existing bundled PDFium packages.',
                   errors=errors)
    (READY / 'implementation_audit.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in receipt.items() if k != 'case_date_source_spans'}, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)
    return receipt


if __name__ == '__main__':
    audit()
