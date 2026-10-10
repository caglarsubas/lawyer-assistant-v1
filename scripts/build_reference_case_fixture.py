#!/usr/bin/env python3
"""Create invented reference-case intake; no real law, client data or judgments."""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from build_calibration_fixture import _create_private_directory, _open_parent, _write_new_file  # noqa: E402
from build_evaluation_fixture import fixture as evaluation_fixture  # noqa: E402

from app.qualification import read_components  # noqa: E402
from app.qualification_scoring import AdjudicatedTask, digest  # noqa: E402
from app.reference_cases import DIMENSIONS, sha  # noqa: E402


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def fixture(catalog_bytes):
    protocol, snapshot, rows = evaluation_fixture()
    protocol['development_family_sha256'] = [digest('synthetic-development')]
    artifacts = {}

    def add(raw):
        key = sha(raw)
        artifacts[f'{key}.bin'] = raw
        return key

    original = add('İcat edilmiş kaynak: süre başladı. Karşı yorum: süre başlamadı.'.encode())
    texts = ['İcat edilmiş test: süre başladı.', 'İcat edilmiş karşı test: süre başlamadı.']
    passage_hash = add(encoded({'schema_version': 'legal-reference-passages-v1', 'source_id': 'synthetic-source',
                               'representation_sha256': original,
                               'passages': [{'ordinal': i, 'locator': f'SYNTHETIC_LOCATOR_{i}', 'text': text}
                                            for i, text in enumerate(texts)]}))
    record = add(encoded({'fixture': 'unverified synthetic source, family and independence record'}))
    source = {'id': 'synthetic-source', 'sample_kind': 'synthetic', 'source_family_id': None, 'kind': 'norm',
              'source_identity_sha256': digest('synthetic-norm'), 'proceeding_identity_sha256': None,
              'representation_sha256': original, 'passages_sha256': passage_hash,
              'rights_record_sha256': record, 'history_record_sha256': record}
    cases = []
    for split in ('development', 'held_out'):
        ident = 'synthetic-' + split.replace('_', '-')
        task_hash = add(encoded({'fixture': True, 'scenario': f'İcat edilmiş {split} olayı: ödeme yapılmadı.'}))
        reference = {'schema_version': 'legal-reference-answer-v1', 'case_id': ident, 'task_input_sha256': task_hash,
                     'snapshot_sha256': digest(snapshot), 'rubric_sha256': protocol['rubric_sha256'],
                     'prepared_at': '2026-01-01T00:00:00Z', 'relevant_on': '2026-01-01',
                     'reviewer_ids': ['synthetic-a', 'synthetic-b'], 'independence_record_sha256': record,
                     'coverage': 'declared_complete', 'adverse_search': 'declared_complete',
                     'gold_authorities': ['synthetic-authority', 'synthetic-adverse'],
                     'citations': [{'source_id': source['id'], 'ordinal': i, 'passage_text_sha256': sha(text.encode()),
                                   'authority_id': authority, 'role': role}
                                  for i, (text, authority, role) in enumerate(zip(texts,
                                      ('synthetic-authority', 'synthetic-adverse'), ('support', 'adverse'), strict=True))],
                     'observations': [{'dimension': name, 'status': 'recorded', 'evidence_sha256': record}
                                      for name in sorted(DIMENSIONS)]}
        cases.append({'id': ident, 'sample_kind': 'synthetic', 'data_classification': 'synthetic_fixture',
                      'practice': 'contracts', 'period': 'synthetic', 'split': split, 'family_sha256': digest('synthetic-' + split),
                      'family_basis': 'synthetic_fixture', 'family_review_sha256': record,
                      'task_input_sha256': task_hash, 'reference_sha256': add(encoded(reference)),
                      'source_ids': [source['id']]})
    book = {'schema_version': 'legal-reference-casebook-v1', 'registered_at': protocol['registered_at'],
            'protocol_sha256': digest(protocol), 'snapshot_sha256': digest(snapshot),
            'rubric_sha256': protocol['rubric_sha256'], 'source_catalog_sha256': sha(catalog_bytes),
            'sources': [source], 'cases': cases, 'reference_record_sha256': [record]}
    row = rows[0]
    held = cases[1]
    row.update(protocol_sha256=digest(protocol), task_input_sha256=held['task_input_sha256'],
               split_family_sha256=held['family_sha256'])
    row['score'].update(task_id=held['id'], gold_authorities=['synthetic-authority', 'synthetic-adverse'])
    for pair in row['pairs']:
        for arm in ('baseline', 'candidate'):
            pair[arm]['task_input_sha256'] = held['task_input_sha256']
    return book, protocol, snapshot, artifacts, [row]


def bind_rows(book, rows, artifacts):
    """Invented post-run evidence, distinct from the pre-run reference answer."""
    for row in rows:
        case = next(case for case in book['cases'] if case['id'] == row['score']['task_id'])
        proof = encoded({'schema_version': 'legal-reference-adjudication-v1', 'casebook_sha256': sha(encoded(book)),
                         'case_id': case['id'], 'reference_sha256': case['reference_sha256'],
                         'row_content_sha256': digest(AdjudicatedTask.model_validate(row).model_dump(
                             exclude={'adjudication_evidence_sha256'}))})
        row['adjudication_evidence_sha256'] = sha(proof)
        artifacts[f'{sha(proof)}.bin'] = proof


def create(destination, with_rows=False):
    catalog_bytes = read_components(Path(__file__).resolve().parents[1] / 'qualification')['source-catalog.json']
    book, protocol, snapshot, artifacts, rows = fixture(catalog_bytes)
    if with_rows:
        bind_rows(book, rows, artifacts)
    files = {'intake': {'casebook.json': encoded(book), 'protocol.json': encoded(protocol),
                        'snapshot.json': encoded(snapshot)}, 'catalog': {'source-catalog.json': catalog_bytes},
             'artifacts': artifacts}
    if with_rows:
        files['evaluation'] = {'tasks.jsonl': b'\n'.join(encoded(row) for row in rows) + b'\n'}
    parent, name = _open_parent(destination)
    target = None
    try:
        target = _create_private_directory(parent, name)
        identity = os.fstat(target).st_ino
        for directory, contents in files.items():
            child = _create_private_directory(target, directory)
            try:
                for filename, raw in contents.items():
                    _write_new_file(child, filename, raw)
                os.fsync(child)
            finally:
                os.close(child)
        os.fsync(target)
        if os.stat(name, dir_fd=parent, follow_symlinks=False).st_ino != identity:
            raise ValueError('Fixture destination changed')
        os.fsync(parent)
    finally:
        if target is not None:
            os.close(target)
        os.close(parent)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--with-evaluation', action='store_true')
    args = parser.parse_args(argv)
    try:
        create(args.destination, args.with_evaluation)
    except (ValueError, OSError):
        print('Cannot create synthetic reference fixture; existing destinations are preserved.', file=sys.stderr)
        return 2
    print('Created two invented cases; real evidence, legal approval and measured benefit remain absent.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
