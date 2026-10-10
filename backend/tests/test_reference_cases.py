"""Invented case/reference bytes test intake boundaries, never Turkish legal quality."""

import copy
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

from app import reference_cases as cases
from app.qualification_scoring import digest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / f'{name}.py')
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


builder = module('build_reference_case_fixture')
cli = module('qualify_reference_cases')
scorer = module('evaluate_release')


def package(tmp_path):
    raw = (ROOT / 'qualification/source-catalog.json').read_bytes()
    book, protocol, snapshot, artifacts, rows = builder.fixture(raw)
    for name in ('intake', 'artifacts', 'catalog'):
        (tmp_path / name).mkdir()
    (tmp_path / 'catalog/source-catalog.json').write_bytes(raw)
    return book, protocol, snapshot, artifacts, rows


def write(tmp_path, book, protocol, snapshot, artifacts):
    for name, value in (('casebook', book), ('protocol', protocol), ('snapshot', snapshot)):
        (tmp_path / 'intake' / f'{name}.json').write_bytes(builder.encoded(value))
    for path in (tmp_path / 'artifacts').iterdir():
        path.unlink()
    for name, raw in artifacts.items():
        (tmp_path / 'artifacts' / name).write_bytes(raw)


def inspect(tmp_path, *, rows=None):
    return cases.inspect_casebook(tmp_path / 'intake', tmp_path / 'artifacts', tmp_path / 'catalog', rows)


def change_reference(book, artifacts, index, mutate):
    entry = book['cases'][index]
    key = f"{entry['reference_sha256']}.bin"
    reference = json.loads(artifacts.pop(key))
    mutate(reference)
    raw = builder.encoded(reference)
    entry['reference_sha256'] = cases.sha(raw)
    artifacts[f'{cases.sha(raw)}.bin'] = raw


def test_inventory_separates_unknown_legal_quality_and_shared_norms(tmp_path):
    book, protocol, snapshot, artifacts, _ = package(tmp_path)
    write(tmp_path, book, protocol, snapshot, artifacts)
    result = inspect(tmp_path)
    assert result['intake_checks_pass']
    assert result['counts'] == {'real': {'development': 0, 'held_out': 0},
                                'synthetic': {'development': 1, 'held_out': 1}}
    assert result['family_checks']['identity_components'] == 2
    assert result['quality_metrics'] is result['preparation_time_gain'] is None
    assert not result['reference_case_binding_pass']
    for key in ('production_qualified', 'legal_qualification', 'privacy_verified',
                'source_authenticity_verified', 'original_transcription_verified',
                'registration_time_authenticated', 'reviewer_independence_verified',
                'sample_representativeness_verified'):
        assert result[key] is False
    printed = json.dumps(result)
    assert all(text not in printed for text in ('SYNTHETIC_LOCATOR', 'ödeme', 'synthetic-a', 'synthetic-source'))


@pytest.mark.parametrize('change', ['case_id', 'task_input', 'snapshot', 'rubric', 'post_registration',
                                   'passage_hash', 'passage_ordinal', 'foreign_source', 'duplicate_dimension',
                                   'duplicate_reviewer', 'gold_without_passage', 'adverse_not_gold'])
def test_dangling_or_replaced_reference_is_invalid(tmp_path, change):
    book, protocol, snapshot, artifacts, _ = package(tmp_path)

    def mutate(ref):
        if change == 'case_id':
            ref['case_id'] = 'other-case'
        elif change in ('task_input', 'snapshot', 'rubric'):
            ref[change + '_sha256'] = digest('changed')
        elif change == 'post_registration':
            ref['prepared_at'] = '2026-01-02T00:00:00Z'
        elif change == 'passage_hash':
            ref['citations'][0]['passage_text_sha256'] = digest('changed')
        elif change == 'passage_ordinal':
            ref['citations'][0]['ordinal'] = 99
        elif change == 'foreign_source':
            ref['citations'][0]['source_id'] = 'other-source'
        elif change == 'duplicate_dimension':
            ref['observations'][0] = ref['observations'][1]
        elif change == 'duplicate_reviewer':
            ref['reviewer_ids'][1] = ref['reviewer_ids'][0]
        elif change == 'gold_without_passage':
            ref['gold_authorities'].append('unreferenced-authority')
        elif change == 'adverse_not_gold':
            ref['gold_authorities'].remove('synthetic-adverse')
    change_reference(book, artifacts, 1, mutate)
    write(tmp_path, book, protocol, snapshot, artifacts)
    with pytest.raises(ValueError):
        inspect(tmp_path)


@pytest.mark.parametrize('kind', ['family', 'input', 'decision_identity', 'decision_bytes', 'proceeding'])
def test_known_cross_split_leakage_cannot_pass(tmp_path, kind):
    book, protocol, snapshot, artifacts, _ = package(tmp_path)
    if kind == 'family':
        # Development reservations are a hard protocol boundary, even without
        # duplicate bytes. A held-out family already reserved is invalid input.
        book['cases'][1]['family_sha256'] = book['cases'][0]['family_sha256']
    elif kind == 'input':
        book['cases'][1]['task_input_sha256'] = book['cases'][0]['task_input_sha256']
        change_reference(book, artifacts, 1, lambda ref: ref.update(task_input_sha256=book['cases'][0]['task_input_sha256']))
        artifacts.pop(next(key for key, raw in artifacts.items() if b'held_out ol' in raw))
    else:
        book['sources'][0]['kind'] = 'decision'
        if kind == 'proceeding':
            book['sources'][0]['proceeding_identity_sha256'] = digest('shared-proceeding')
    write(tmp_path, book, protocol, snapshot, artifacts)
    if kind == 'family':
        with pytest.raises(ValueError):
            inspect(tmp_path)
    else:
        result = inspect(tmp_path)
        assert result['family_checks']['cross_split_components'] == 1
        assert result['family_checks']['inconsistent_family_components'] == 1
        assert not result['intake_checks_pass']


@pytest.mark.parametrize('gap', ['family', 'rights', 'history', 'date', 'coverage', 'adverse', 'reviewers', 'dimension'])
def test_unassessed_records_stay_gaps_without_becoming_zero_or_approval(tmp_path, gap):
    book, protocol, snapshot, artifacts, _ = package(tmp_path)
    if gap == 'family':
        book['cases'][1].update(family_basis='unresolved', family_review_sha256=None)
    elif gap in ('rights', 'history'):
        book['sources'][0][gap + '_record_sha256'] = None
    else:
        def mutate(ref):
            if gap == 'date':
                ref['relevant_on'] = None
            elif gap == 'coverage':
                ref['coverage'] = 'partial'
            elif gap == 'adverse':
                ref['adverse_search'] = 'not_assessed'
            elif gap == 'reviewers':
                ref.update(reviewer_ids=[], independence_record_sha256=None)
            else:
                ref['observations'][0].update(status='unresolved', evidence_sha256=None)
        change_reference(book, artifacts, 1, mutate)
    write(tmp_path, book, protocol, snapshot, artifacts)
    result = inspect(tmp_path)
    assert not result['intake_checks_pass']
    assert result['family_checks']['unknown_family_records'] or any(result['reference_gaps'].values())


@pytest.mark.parametrize('change', ['protocol', 'snapshot', 'catalog', 'private', 'origin', 'reservation',
                                   'duplicate_case', 'unused_record', 'unknown_family', 'duplicate_json'])
def test_casebook_contract_and_catalog_are_exact(tmp_path, change):
    book, protocol, snapshot, artifacts, _ = package(tmp_path)
    if change in ('protocol', 'snapshot'):
        book[change + '_sha256'] = digest('wrong')
    elif change == 'catalog':
        book['source_catalog_sha256'] = digest('wrong')
    elif change == 'private':
        book['cases'][0]['data_classification'] = 'matter_private'
    elif change == 'origin':
        book['cases'][0].update(sample_kind='real', data_classification='public_scenario')
    elif change == 'reservation':
        protocol['development_family_sha256'] = []
        book['protocol_sha256'] = digest(protocol)
    elif change == 'duplicate_case':
        book['cases'][1]['id'] = book['cases'][0]['id']
    elif change == 'unused_record':
        key = cases.sha(b'UNUSED_PRIVATE_RECORD')
        book['reference_record_sha256'].append(key)
        artifacts[f'{key}.bin'] = b'UNUSED_PRIVATE_RECORD'
    elif change == 'unknown_family':
        book['sources'][0].update(sample_kind='real', source_family_id='nonexistent-family')
    write(tmp_path, book, protocol, snapshot, artifacts)
    if change == 'duplicate_json':
        (tmp_path / 'intake/casebook.json').write_bytes(b'{"secret":"DO_NOT_PRINT", "secret":2}')
    with pytest.raises(ValueError):
        inspect(tmp_path)


@pytest.mark.parametrize('attack', ['extra', 'missing', 'wrong_bytes', 'symlink', 'hardlink', 'symlink_parent', 'fifo'])
def test_physical_inventory_rejects_links_special_files_and_changed_bytes(tmp_path, attack):
    book, protocol, snapshot, artifacts, _ = package(tmp_path)
    write(tmp_path, book, protocol, snapshot, artifacts)
    path = tmp_path / 'artifacts' / next(iter(artifacts))
    if attack == 'extra':
        (tmp_path / 'artifacts/unexpected.env').write_text('DO_NOT_PRINT')
    elif attack == 'missing':
        path.unlink()
    elif attack == 'wrong_bytes':
        path.write_bytes(b'DO_NOT_PRINT')
    elif attack == 'symlink_parent':
        actual = tmp_path / 'actual-artifacts'
        (tmp_path / 'artifacts').rename(actual)
        (tmp_path / 'artifacts').symlink_to(actual, target_is_directory=True)
    else:
        path.unlink()
        other = tmp_path / 'private-secret'
        other.write_bytes(b'DO_NOT_PRINT')
        if attack == 'symlink':
            path.symlink_to(other)
        elif attack == 'hardlink':
            os.link(other, path)
        else:
            os.mkfifo(path)
    with pytest.raises(ValueError):
        inspect(tmp_path)


def test_changes_between_captures_discard_the_whole_report(tmp_path, monkeypatch):
    book, protocol, snapshot, artifacts, _ = package(tmp_path)
    write(tmp_path, book, protocol, snapshot, artifacts)
    original = cases.read_exact_directory
    captures = 0

    def changing(path, specs, budget, **kwargs):
        nonlocal captures
        captures += 1
        result = original(path, specs, budget, **kwargs)
        if captures == 3:
            target = tmp_path / 'intake/casebook.json'
            target.write_bytes(target.read_bytes() + b'\n')
        return result
    monkeypatch.setattr(cases, 'read_exact_directory', changing)
    with pytest.raises(ValueError):
        inspect(tmp_path)


@pytest.mark.parametrize('change', ['none', 'score', 'input', 'family', 'origin', 'practice', 'gold', 'adverse',
                                   'case', 'time', 'protocol', 'duplicate', 'reference_proof'])
def test_post_run_scores_bind_the_whole_row_to_prerun_reference(tmp_path, change):
    book, protocol, snapshot, artifacts, rows = package(tmp_path)
    builder.bind_rows(book, rows, artifacts)
    row = rows[0]
    if change == 'score':
        row['score']['claims'][0]['supported'] = False
    elif change == 'input':
        row['task_input_sha256'] = digest('changed')
        for pair in row['pairs']:
            for arm in ('baseline', 'candidate'):
                pair[arm]['task_input_sha256'] = row['task_input_sha256']
    elif change == 'family':
        row['split_family_sha256'] = digest('changed')
    elif change == 'origin':
        row['sample_kind'] = 'real'
    elif change == 'practice':
        row['score']['domain'] = 'employment'
    elif change == 'gold':
        row['score']['gold_authorities'] = ['synthetic-authority']
    elif change == 'adverse':
        row['analysis']['gold_adverse_authorities'] = []
    elif change == 'case':
        row['score']['task_id'] = book['cases'][0]['id']
    elif change == 'time':
        row['measured_at'] = '2025-12-31T00:00:00Z'
    elif change == 'protocol':
        row['protocol_sha256'] = digest('changed')
    elif change == 'duplicate':
        rows.append(copy.deepcopy(row))
    elif change == 'reference_proof':
        key = row['adjudication_evidence_sha256'] + '.bin'
        proof = json.loads(artifacts.pop(key))
        proof['reference_sha256'] = digest('wrong')
        raw = builder.encoded(proof)
        row['adjudication_evidence_sha256'] = cases.sha(raw)
        artifacts[f'{cases.sha(raw)}.bin'] = raw
    write(tmp_path, book, protocol, snapshot, artifacts)
    if change == 'none':
        result = inspect(tmp_path, rows=rows)
        assert result['measured_rows'] == 1 and result['missing_held_out_rows'] == 0
        assert not result['reference_case_binding_pass']  # Synthetic cannot qualify.
    else:
        with pytest.raises(ValueError):
            inspect(tmp_path, rows=rows)


def test_missing_rows_are_visible_not_silently_dropped(tmp_path):
    book, protocol, snapshot, artifacts, _ = package(tmp_path)
    write(tmp_path, book, protocol, snapshot, artifacts)
    report = inspect(tmp_path, rows=[])
    assert report['missing_held_out_rows'] == 1 and not report['reference_case_binding_pass']


def test_scorer_and_intake_use_the_same_exact_protocol_and_snapshot(tmp_path):
    book, protocol, snapshot, artifacts, rows = package(tmp_path)
    builder.bind_rows(book, rows, artifacts)
    write(tmp_path, book, protocol, snapshot, artifacts)
    path = tmp_path / 'tasks.jsonl'
    path.write_bytes(b'\n'.join(builder.encoded(row) for row in rows))
    result = scorer.score_files(path, tmp_path / 'intake/snapshot.json', tmp_path / 'intake/protocol.json',
                               casebook_dir=tmp_path / 'intake', case_artifacts_dir=tmp_path / 'artifacts',
                               source_catalog_dir=tmp_path / 'catalog')
    assert not result['gates']['reference_case_binding'] and not result['quantitative_gates_pass']
    other = tmp_path / 'protocol.json'
    other.write_bytes(builder.encoded(protocol) + b'\n')
    with pytest.raises(ValueError):
        scorer.score_files(path, tmp_path / 'intake/snapshot.json', other,
                           casebook_dir=tmp_path / 'intake', case_artifacts_dir=tmp_path / 'artifacts',
                           source_catalog_dir=tmp_path / 'catalog')
    with pytest.raises(ValueError):
        scorer.score_files(path, tmp_path / 'intake/snapshot.json', casebook_dir=tmp_path / 'intake')


def test_cli_redacts_invalid_values_and_preserves_gap_exit(tmp_path, capsys):
    book, protocol, snapshot, artifacts, _ = package(tmp_path)
    write(tmp_path, book, protocol, snapshot, artifacts)
    args = [str(tmp_path / 'intake'), '--artifacts-dir', str(tmp_path / 'artifacts'),
            '--source-catalog-dir', str(tmp_path / 'catalog')]
    assert cli.main(args) == 0
    capsys.readouterr()
    book['cases'][1].update(family_basis='unresolved', family_review_sha256=None)
    write(tmp_path, book, protocol, snapshot, artifacts)
    assert cli.main(args) == 1
    capsys.readouterr()
    (tmp_path / 'intake/casebook.json').write_text('{"private":"DO_NOT_PRINT"}')
    assert cli.main(args) == 2
    output = capsys.readouterr()
    assert not output.out and 'DO_NOT_PRINT' not in output.err and str(tmp_path) not in output.err
    assert cli.main(['--invalid', 'DO_NOT_PRINT']) == 2
    assert 'DO_NOT_PRINT' not in capsys.readouterr().err
    assert cli.main(['--schemas']) == 0


def test_generator_uses_private_exclusive_directories_and_never_overwrites(tmp_path):
    target = tmp_path / 'new-fixture'
    assert builder.main([str(target)]) == 0
    assert cases.inspect_casebook(target / 'intake', target / 'artifacts', target / 'catalog')['intake_checks_pass']
    originals = {path: path.read_bytes() for path in target.rglob('*') if path.is_file()}
    assert builder.main([str(target)]) == 2
    assert all(path.read_bytes() == raw for path, raw in originals.items())
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in originals)
    assert all(path.stat().st_mode & 0o777 == 0o700 for path in target.rglob('*') if path.is_dir())
    link = tmp_path / 'link'
    link.symlink_to(target, target_is_directory=True)
    assert builder.main([str(link / 'forbidden')]) == 2
    assert not (target / 'forbidden').exists()


def test_real_label_only_establishes_physical_binding_never_legal_approval(tmp_path):
    book, protocol, snapshot, artifacts, rows = package(tmp_path)
    catalog = json.loads((tmp_path / 'catalog/source-catalog.json').read_bytes())
    # Deliberate false declarations in invented test bytes exercise the distinction
    # between physical binding and actual source/reviewer authentication.
    book['sources'][0].update(sample_kind='real', source_family_id=catalog['sources'][0]['id'])
    for case in book['cases']:
        case.update(sample_kind='real', data_classification='public_scenario',
                    family_basis='declared_near_duplicate', period='2016_onward')
    rows[0]['sample_kind'] = 'real'
    rows[0]['score']['period'] = '2016_onward'
    builder.bind_rows(book, rows, artifacts)
    write(tmp_path, book, protocol, snapshot, artifacts)
    report = inspect(tmp_path, rows=rows)
    assert report['reference_case_binding_pass']
    assert not report['legal_qualification'] and not report['source_authenticity_verified']
    assert not report['reviewer_independence_verified'] and not report['privacy_verified']


def test_distinct_source_versions_of_one_proceeding_still_conflict(tmp_path):
    book, protocol, snapshot, artifacts, _ = package(tmp_path)
    first = book['sources'][0]
    first.update(kind='decision', proceeding_identity_sha256=digest('same-proceeding'))
    second = copy.deepcopy(first)
    second.update(id='synthetic-second', source_identity_sha256=digest('another-decision'))
    new_original = b'A second invented decision representation'
    second['representation_sha256'] = cases.sha(new_original)
    artifacts[f'{cases.sha(new_original)}.bin'] = new_original
    passage_set = json.loads(artifacts[first['passages_sha256'] + '.bin'])
    passage_set.update(source_id=second['id'], representation_sha256=second['representation_sha256'])
    new_passages = builder.encoded(passage_set)
    second['passages_sha256'] = cases.sha(new_passages)
    artifacts[f'{cases.sha(new_passages)}.bin'] = new_passages
    book['sources'].append(second)
    book['cases'][1]['source_ids'] = [second['id']]
    change_reference(book, artifacts, 1, lambda ref: [citation.update(source_id=second['id']) for citation in ref['citations']])
    write(tmp_path, book, protocol, snapshot, artifacts)
    report = inspect(tmp_path)
    assert report['family_checks']['cross_split_components'] == 1
    assert report['family_checks']['inconsistent_family_components'] == 1
    assert not report['intake_checks_pass']


def test_large_evidence_inventory_requires_explicit_bounded_opt_in(tmp_path):
    from app.qualification_evidence import MAX_FILES, read_exact_directory

    specs = {f'{i:064x}.bin': 1 for i in range(MAX_FILES + 1)}
    for name in specs:
        (tmp_path / name).write_bytes(b'a')
    with pytest.raises(ValueError):
        read_exact_directory(tmp_path, specs, len(specs))
    result = read_exact_directory(tmp_path, specs, len(specs), maximum_files=cases.MAX_REFERENCE_FILES)
    assert len(result) == MAX_FILES + 1
    for cap in (True, 0, cases.MAX_REFERENCE_FILES + 1):
        with pytest.raises(ValueError):
            read_exact_directory(tmp_path, specs, len(specs), maximum_files=cap)


def test_generator_evaluation_example_runs_end_to_end_without_qualification(tmp_path):
    target = tmp_path / 'new-evaluation'
    assert builder.main([str(target), '--with-evaluation']) == 0
    report = scorer.score_files(target / 'evaluation/tasks.jsonl', target / 'intake/snapshot.json',
                               target / 'intake/protocol.json', casebook_dir=target / 'intake',
                               case_artifacts_dir=target / 'artifacts', source_catalog_dir=target / 'catalog')
    assert report['reference_cases']['measured_rows'] == 1
    assert not report['quantitative_gates_pass'] and not report['production_qualified']


def test_thousand_case_roster_is_bounded_and_not_a_qualification_claim(tmp_path):
    book, protocol, snapshot, artifacts, _ = package(tmp_path)
    seed = book['cases'][1]
    reference = json.loads(artifacts[seed['reference_sha256'] + '.bin'])
    for entry in book['cases']:
        artifacts.pop(entry['reference_sha256'] + '.bin')
        artifacts.pop(entry['task_input_sha256'] + '.bin')
    book['cases'] = []
    for index in range(cases.MAX_CASES):
        entry = copy.deepcopy(seed)
        entry.update(id=f'synthetic-scale-{index}', family_sha256=digest(f'scale-{index}'))
        task = f'Invented scenario {index}'.encode()
        entry['task_input_sha256'] = cases.sha(task)
        artifacts[f'{cases.sha(task)}.bin'] = task
        ref = copy.deepcopy(reference)
        ref.update(case_id=entry['id'], task_input_sha256=entry['task_input_sha256'])
        raw = builder.encoded(ref)
        entry['reference_sha256'] = cases.sha(raw)
        artifacts[f'{cases.sha(raw)}.bin'] = raw
        book['cases'].append(entry)
    write(tmp_path, book, protocol, snapshot, artifacts)
    report = inspect(tmp_path)
    assert report['counts']['synthetic']['held_out'] == 1000
    assert report['verified_artifact_count'] > 2000
    assert report['intake_checks_pass'] and not report['reference_case_binding_pass']
    with pytest.raises(ValueError):
        inspect(tmp_path, rows=[{}] * (cases.MAX_CASES + 1))
    book['cases'].append(copy.deepcopy(book['cases'][0]))
    (tmp_path / 'intake/casebook.json').write_bytes(builder.encoded(book))
    with pytest.raises(ValueError):
        inspect(tmp_path)
