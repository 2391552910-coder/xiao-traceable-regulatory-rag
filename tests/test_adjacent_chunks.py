import copy
import hashlib
import json
import sqlite3
from dataclasses import asdict

import pytest

from src.data.clause_splitter import Chunk
from src.retrieval.adjacent_chunks import FrozenAdjacentIndex


QUESTION = {'stock_code': '000001', 'report_year': 2024, 'query': 'Unused public question'}


def annual(page, start=0, *, stock='000001', year=2024, doc='REPORT-A', digest='a' * 64, cid=None):
    cid = cid or f'HELD-{stock}-{year}-P{page}-S{start}'
    return Chunk(cid, doc, 'Original annual report', 'annual_report',
                 'https://example.test/report.pdf', None, f'Unchanged text at page {page}, start {start}.\n ',
                 meta={'corpus_type': 'annual_report', 'stock_code': stock, 'report_year': year,
                       'source_pdf_sha256': digest, 'physical_pdf_page_1based': page,
                       'system_corpus_input': True})


def source(chunk, evidence_id='A1'):
    return {'evidence_id': evidence_id, 'chunk_id': chunk.chunk_id, 'doc_id': chunk.doc_id,
            'document_title': chunk.doc_title, 'doc_type': chunk.doc_type,
            'source': chunk.source, 'clause_no': chunk.clause_no, 'text': chunk.text,
            'score': .5, 'meta': copy.deepcopy(chunk.meta)}


def database(tmp_path, chunks):
    path = tmp_path/'index.sqlite'
    with sqlite3.connect(path) as connection:
        connection.execute('CREATE TABLE chunks(position INTEGER PRIMARY KEY,payload TEXT)')
        connection.executemany('INSERT INTO chunks VALUES (?,?)',
                               [(i, json.dumps(asdict(c))) for i, c in enumerate(chunks)])
    return path


def corpus():
    # Deliberately not in insertion/coordinate order.
    return [annual(2, 1000), annual(1, 1000), annual(3),
            annual(1), annual(2), annual(1, 2000)]


def ids(hits):
    return [c.chunk_id for c, _ in hits]


def test_round_robin_uses_initial_seed_order_and_exact_coordinate_neighbours(tmp_path):
    chunks = corpus();index = FrozenAdjacentIndex(database(tmp_path, chunks))
    records = [source(chunks[0]), source(chunks[1], 'A2')]
    hits, audit = index.select(QUESTION, {'source_records': records})
    assert ids(hits) == [annual(3).chunk_id, annual(1, 2000).chunk_id,
                         annual(2).chunk_id, annual(1).chunk_id]
    assert [r['direction'] for r in audit['selected_candidates']] == ['successor', 'successor', 'predecessor', 'predecessor']
    assert [r['seed_rank'] for r in audit['selected_candidates']] == [1, 2, 1, 2]
    assert [r['same_page'] for r in audit['selected_candidates']] == [False, True, True, True]
    assert [r['physical_page_delta'] for r in audit['selected_candidates']] == [1, 0, 0, 0]
    assert all(r['adjacent_hop'] == 1 for r in audit['candidates'])
    assert all(score == 0.0 for _, score in hits)


def test_continuation_first_is_a_declared_generic_order_not_content_ranking(tmp_path):
    chunks = corpus();index = FrozenAdjacentIndex(database(tmp_path, chunks))
    records = [source(chunks[0]), source(chunks[1], 'A2')]
    hits, audit = index.select(QUESTION, records, policy='continuation_first')
    assert ids(hits) == [annual(1, 2000).chunk_id, annual(3).chunk_id,
                         annual(2).chunk_id, annual(1).chunk_id]
    assert [r['seed_rank'] for r in audit['selected_candidates']] == [2, 1, 1, 2]
    alternative, other_audit = index.select({**QUESTION, 'query': 'A very different answer-oriented phrase'}, records,
                                           policy='continuation_first')
    assert alternative == hits and other_audit == audit
    assert audit['reference_labels_read'] is False and audit['query_terms_used'] is False


def test_does_not_skip_an_existing_neighbour_to_find_a_second_hop(tmp_path):
    chunks = [annual(1), annual(1, 1000), annual(1, 2000), annual(2)]
    index = FrozenAdjacentIndex(database(tmp_path, chunks))
    records = [source(chunks[0]), source(chunks[1], 'A2')]
    hits, audit = index.select(QUESTION, records)
    assert ids(hits) == [chunks[2].chunk_id]
    assert chunks[3].chunk_id not in ids(hits)
    assert audit['omission_reason_counts'] == {'already_in_initial_context': 2,
                                              'document_coordinate_sequence_boundary': 1}
    assert audit['recursive_expansion'] is False


def test_duplicate_neighbour_from_two_seeds_is_returned_once_with_full_audit(tmp_path):
    chunks = [annual(1), annual(1, 1000), annual(1, 2000)]
    index = FrozenAdjacentIndex(database(tmp_path, chunks))
    hits, audit = index.select(QUESTION, [source(chunks[0]), source(chunks[2], 'A2')])
    assert ids(hits) == [chunks[1].chunk_id]
    assert len(audit['candidates']) == 2
    assert audit['omission_reason_counts']['duplicate_neighbour_candidate'] == 1
    assert audit['selected_candidates'][0]['selection_rank'] == 1


def test_single_chunk_document_has_two_boundaries_and_no_candidate(tmp_path):
    seed = annual(1);index = FrozenAdjacentIndex(database(tmp_path, [seed]))
    hits, audit = index.select(QUESTION, [source(seed)])
    assert hits == [] and audit['candidates'] == []
    assert audit['omission_reason_counts'] == {'document_coordinate_sequence_boundary': 2}


@pytest.mark.parametrize('other', [annual(1, 500, doc='OTHER-DOCUMENT'),
                                  annual(1, 500, digest='b' * 64),
                                  annual(1, 500, stock='000002'),
                                  annual(1, 500, year=2023)])
def test_document_pdf_company_and_year_sequences_never_mix(tmp_path, other):
    seed, expected = annual(1), annual(1, 1000)
    index = FrozenAdjacentIndex(database(tmp_path, [other, expected, seed]))
    hits, audit = index.select(QUESTION, [source(seed)])
    assert ids(hits) == [expected.chunk_id]
    assert all(r['doc_id'] == seed.doc_id and r['source_pdf_sha256'] == 'a' * 64
               for r in audit['selected_candidates'])


def test_wrong_company_or_year_seed_is_rejected_even_if_it_exists(tmp_path):
    seed = annual(1);index = FrozenAdjacentIndex(database(tmp_path, [seed]))
    for question in [{**QUESTION, 'stock_code': '000002'}, {**QUESTION, 'report_year': 2023}]:
        with pytest.raises(ValueError, match='company/year'):index.select(question, [source(seed)])


@pytest.mark.parametrize('fault', ['text', 'doc_id', 'source', 'meta_hash', 'page'])
def test_seed_with_same_id_but_changed_content_is_not_accepted(tmp_path, fault):
    seed = annual(1);index = FrozenAdjacentIndex(database(tmp_path, [seed]));record = source(seed)
    if fault == 'meta_hash':record['meta']['source_pdf_sha256'] = 'b' * 64
    elif fault == 'page':record['meta']['physical_pdf_page_1based'] = 2
    else:record[fault] = 'different'
    with pytest.raises(ValueError, match='differs'):index.select(QUESTION, [record])


def test_missing_seed_duplicate_index_id_and_duplicate_initial_ids_are_rejected(tmp_path):
    seed = annual(1);path = database(tmp_path, [seed]);index = FrozenAdjacentIndex(path)
    with pytest.raises(ValueError, match='absent'):index.select(QUESTION, [source(annual(2))])
    with pytest.raises(ValueError, match='Duplicate initial source'):index.select(QUESTION, [source(seed), source(seed, 'A2')])
    with sqlite3.connect(path) as connection:
        connection.execute('INSERT INTO chunks VALUES (?,?)', (2, json.dumps(asdict(seed))))
    with pytest.raises(ValueError, match='Duplicate chunk ID'):FrozenAdjacentIndex(path)


@pytest.mark.parametrize('cid', ['HELD-000001-2024-P0-S0', 'HELD-000001-2024-P1-S-1',
                                'HELD-000001-2024-P1-S00', 'HELD-000001-2024-P01-S0',
                                'HELD-000001-2024-P1-S0;DROP TABLE chunks',
                                'HELD-000001-2024-P1-S0\n'])
def test_noncanonical_or_injected_coordinates_are_rejected(tmp_path, cid):
    with pytest.raises(ValueError, match='coordinates'):
        FrozenAdjacentIndex(database(tmp_path, [annual(1, cid=cid)]))


@pytest.mark.parametrize('fault', ['page', 'stock', 'year', 'hash', 'start'])
def test_id_coordinates_and_source_metadata_must_agree(tmp_path, fault):
    seed = annual(1)
    if fault == 'page':seed.meta['physical_pdf_page_1based'] = True
    elif fault == 'stock':seed.meta['stock_code'] = '000002'
    elif fault == 'year':seed.meta['report_year'] = '2024'
    elif fault == 'hash':seed.meta['source_pdf_sha256'] = 'invalid'
    else:seed.meta['page_text_char_start'] = 1
    with pytest.raises(ValueError):FrozenAdjacentIndex(database(tmp_path, [seed]))


def test_nonannual_chunks_are_not_seeds_or_neighbours(tmp_path):
    law = Chunk('LAW-1', 'LAW', 'Regulation', 'regulation', 'fixture', None, 'Norm text',
                meta={'corpus_type': 'regulation'})
    seed, neighbour = annual(1), annual(2)
    index = FrozenAdjacentIndex(database(tmp_path, [seed, law, neighbour]))
    law_record = source(law, 'R1')
    assert index.select(QUESTION, [law_record])[0] == []
    hits, audit = index.select(QUESTION, [law_record, source(seed)])
    assert ids(hits) == [neighbour.chunk_id] and audit['seed_count'] == 1
    assert audit['ignored_sources'][0]['reason'] == 'nonannual_source_not_a_seed'


def test_input_and_database_unchanged_and_returned_chunks_do_not_mutate_snapshot(tmp_path):
    seed, neighbour = annual(1), annual(2);path = database(tmp_path, [neighbour, seed])
    before_hash = hashlib.sha256(path.read_bytes()).hexdigest();index = FrozenAdjacentIndex(path)
    records = [source(seed)];before = copy.deepcopy(records)
    first, audit = index.select(QUESTION, records)
    assert records == before and first[0][0] == neighbour
    first[0][0].text = 'caller changes returned object'
    first[0][0].meta['report_year'] = 1999
    second, second_audit = index.select(QUESTION, records)
    assert second[0][0] == neighbour and second_audit == audit
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before_hash == audit['database_sha256']


def test_unknown_policy_and_missing_database_are_rejected(tmp_path):
    with pytest.raises(FileNotFoundError):FrozenAdjacentIndex(tmp_path/'missing.sqlite')
    seed = annual(1);index = FrozenAdjacentIndex(database(tmp_path, [seed]))
    with pytest.raises(ValueError, match='policy'):index.select(QUESTION, [source(seed)], policy='gold_target')
