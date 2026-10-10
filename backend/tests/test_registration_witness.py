"""Invented signing keys exercise exact binding, never actual legal registration."""

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app import reference_cases
from app import registration_witness as witness

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / f'{name}.py')
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


builder = load('build_reference_case_fixture')
cli = load('qualify_reference_cases')
scorer = load('evaluate_release')


@pytest.fixture
def packet(tmp_path):
    base = tmp_path / 'fixture'
    builder.create(base, with_rows=True)
    keys = [Ed25519PrivateKey.generate() for _ in range(2)]
    registry = {'schema_version': 'legal-evaluation-witness-registry-v1',
                'keys': [{'id': f'key-{i}', 'subject_id': f'subject-{i}', 'purpose': 'evaluation_registration',
                          'public_key_hex': key.public_key().public_bytes_raw().hex(),
                          'valid_from': '2025-01-01T00:00:00Z', 'valid_until': '2027-01-01T00:00:00Z',
                          'revoked': False} for i, key in enumerate(keys)]}
    body = {'schema_version': 'legal-evaluation-registration-v1',
            'casebook_sha256': witness.sha((base / 'intake/casebook.json').read_bytes()),
            'protocol_file_sha256': witness.sha((base / 'intake/protocol.json').read_bytes()),
            'snapshot_file_sha256': witness.sha((base / 'intake/snapshot.json').read_bytes()),
            'source_catalog_sha256': witness.sha((base / 'catalog/source-catalog.json').read_bytes()),
            'witness_registry_sha256': witness.sha(builder.encoded(registry)),
            'witnessed_at': '2026-01-01T00:00:01Z'}
    (base / 'registration').mkdir()
    (base / 'trust').mkdir()
    result = {'base': base, 'keys': keys, 'registry': registry, 'body': body}
    write(result)
    return result


def write(packet, *, payload=None):
    base, registry, body = packet['base'], packet['registry'], packet['body']
    raw = builder.encoded(registry)
    packet['pin'] = body['witness_registry_sha256'] = witness.sha(raw)
    envelope = {'schema_version': 'legal-evaluation-registration-envelope-v1', 'body': body,
                'signatures': [{'key_id': f'key-{i}', 'algorithm': 'Ed25519',
                                'signature_hex': key.sign(payload or witness.signing_bytes(body)).hex()}
                               for i, key in enumerate(packet['keys'])]}
    (base / 'trust/witness-registry.json').write_bytes(raw)
    (base / 'registration/registration.json').write_bytes(builder.encoded(envelope))


def inspect(packet, **overrides):
    base = packet['base']
    options = {'registration_directory': base / 'registration', 'witness_registry_directory': base / 'trust',
               'trusted_registry_sha256': packet['pin']}
    options.update(overrides)
    rows = [json.loads(line) for line in (base / 'evaluation/tasks.jsonl').read_text().splitlines()]
    return reference_cases.inspect_casebook(base / 'intake', base / 'artifacts', base / 'catalog', rows, **options)


def test_enrolled_signatures_bind_bytes_without_proving_times_or_legal_review(packet):
    report = inspect(packet)
    registration = report['registration_witness']
    assert registration['status'] == 'verified_signatures' and registration['signature_count'] == 2
    assert registration['declared_chronology_consistent']
    assert registration['measurement_records_checked'] == 1
    assert not report['reference_case_binding_pass']  # Invented cases never qualify.
    assert registration['runtime_authorization'] == 'none'
    assert all(registration[key] is False for key in ('registration_time_authenticated', 'execution_start_authenticated',
               'witness_independence_verified', 'current_registry_authenticated', 'legal_qualification', 'production_qualified'))
    assert all(value not in json.dumps(report) for value in ('subject-0', 'key-0', 'ödeme', str(packet['base'])))


@pytest.mark.parametrize('field', ['casebook_sha256', 'protocol_file_sha256', 'snapshot_file_sha256', 'source_catalog_sha256'])
def test_even_resigned_changed_inventory_is_rejected(packet, field):
    packet['body'][field] = 'a' * 64
    write(packet)
    with pytest.raises(ValueError):
        inspect(packet)


@pytest.mark.parametrize('change', ['revoked', 'expired', 'future', 'same_subject', 'duplicate_public_key',
                                   'duplicate_key_id', 'wrong_purpose', 'invalid_interval', 'invalid_key'])
def test_ineligible_or_aliased_enrollment_cannot_create_two_witnesses(packet, change):
    keys = packet['registry']['keys']
    if change == 'revoked':
        keys[1]['revoked'] = True
    elif change == 'expired':
        keys[1]['valid_until'] = packet['body']['witnessed_at']  # Upper bound excluded.
    elif change == 'future':
        keys[1]['valid_from'] = '2026-01-02T00:00:00Z'
    elif change == 'same_subject':
        keys[1]['subject_id'] = keys[0]['subject_id']
    elif change == 'duplicate_public_key':
        keys[1]['public_key_hex'] = keys[0]['public_key_hex']
    elif change == 'duplicate_key_id':
        keys[1]['id'] = keys[0]['id']
    elif change == 'wrong_purpose':
        keys[1]['purpose'] = 'source_publication'
    elif change == 'invalid_interval':
        keys[1]['valid_from'] = keys[1]['valid_until']
    else:
        keys[1]['public_key_hex'] = '0' * 64
    write(packet)
    with pytest.raises(ValueError):
        inspect(packet)


@pytest.mark.parametrize('change', ['unknown_key', 'one_signature', 'duplicate_signature', 'changed_signature',
                                   'wrong_algorithm', 'extra_field', 'unsigned_field_change', 'wrong_domain'])
def test_signature_envelope_is_strict_and_domain_separated(packet, change):
    path = packet['base'] / 'registration/registration.json'
    value = json.loads(path.read_text())
    if change == 'unknown_key':
        value['signatures'][1]['key_id'] = 'unenrolled'
    elif change == 'one_signature':
        value['signatures'].pop()
    elif change == 'duplicate_signature':
        value['signatures'][1] = value['signatures'][0]
    elif change == 'changed_signature':
        value['signatures'][1]['signature_hex'] = '0' * 128
    elif change == 'wrong_algorithm':
        value['signatures'][1]['algorithm'] = 'RSA'
    elif change == 'extra_field':
        value['legal_approval'] = True
    elif change == 'unsigned_field_change':
        value['body']['witnessed_at'] = '2026-01-01T00:00:02Z'
    else:
        write(packet, payload=builder.encoded(packet['body']))
        value = json.loads(path.read_text())
    path.write_bytes(builder.encoded(value))
    with pytest.raises(ValueError):
        inspect(packet)


@pytest.mark.parametrize('change', ['before_registration', 'after_measurement', 'naive_timestamp'])
def test_signed_declared_chronology_is_checked_not_authenticated(packet, change):
    if change == 'naive_timestamp':
        path = packet['base'] / 'registration/registration.json'
        envelope = json.loads(path.read_text())
        envelope['body']['witnessed_at'] = '2026-01-01T00:00:00'
        path.write_bytes(builder.encoded(envelope))
    else:
        packet['body']['witnessed_at'] = ('2025-12-31T23:59:59Z' if change == 'before_registration'
                                       else '2026-12-31T00:00:00Z')
        write(packet)
    with pytest.raises(ValueError):
        inspect(packet)


@pytest.mark.parametrize('pin', [None, '', True, 'f' * 64, 'A' * 64])
def test_no_self_selected_or_malformed_trust_pin(packet, pin):
    with pytest.raises(ValueError):
        inspect(packet, trusted_registry_sha256=pin)


@pytest.mark.parametrize('kind', ['extra', 'symlink', 'hardlink', 'fifo', 'duplicate_json', 'oversized'])
def test_witness_files_use_exact_bounded_no_follow_capture(packet, kind):
    path = packet['base'] / 'registration/registration.json'
    if kind == 'extra':
        (path.parent / 'extra.txt').write_text('undeclared')
    elif kind == 'symlink':
        original = path.with_name('outside')
        path.rename(original)
        path.symlink_to(original)
    elif kind == 'hardlink':
        os.link(path, packet['base'] / 'other-link')
    elif kind == 'fifo':
        path.unlink()
        os.mkfifo(path)
    elif kind == 'duplicate_json':
        raw = path.read_bytes()
        path.write_bytes(raw[:-1] + b',"schema_version":"duplicate"}')
    else:
        path.write_bytes(b' ' * (witness.MAX_COMPONENT_BYTES + 1))
    with pytest.raises(ValueError):
        inspect(packet)


def test_changed_registry_during_verification_is_rejected(packet, monkeypatch):
    original = witness.read_exact_directory
    count = 0

    def changed(directory, specs, limit):
        nonlocal count
        count += 1
        if count == 4:
            (packet['base'] / 'trust/witness-registry.json').write_text('{}')
        return original(directory, specs, limit)

    monkeypatch.setattr(witness, 'read_exact_directory', changed)
    with pytest.raises(ValueError):
        inspect(packet)


def test_changed_witness_during_final_casebook_capture_is_rejected(packet, monkeypatch):
    original = reference_cases.read_exact_directory
    count = 0

    def changed(directory, specs, limit, **kwargs):
        nonlocal count
        count += 1
        if count == 4:
            (packet['base'] / 'registration/registration.json').write_text('{}')
        return original(directory, specs, limit, **kwargs)

    monkeypatch.setattr(reference_cases, 'read_exact_directory', changed)
    with pytest.raises(ValueError):
        inspect(packet)


def test_optional_scorer_path_and_cli_failure_do_not_disclose_private_inputs(packet, capsys):
    base = packet['base']
    options = {'casebook_dir': base / 'intake', 'case_artifacts_dir': base / 'artifacts',
               'source_catalog_dir': base / 'catalog', 'registration_dir': base / 'registration',
               'witness_registry_dir': base / 'trust', 'trusted_registry_sha256': packet['pin']}
    report = scorer.score_files(base / 'evaluation/tasks.jsonl', base / 'intake/snapshot.json',
                                base / 'intake/protocol.json', **options)
    assert report['reference_cases']['registration_witness']['status'] == 'verified_signatures'
    assert not report['quantitative_gates_pass']
    assert scorer.main(['--registration-dir', str(base / 'registration')]) == 2
    result = capsys.readouterr()
    assert result.out == '' and str(base) not in result.err
    assert cli.main(['--schemas', '--trusted-registry-sha256', packet['pin']]) == 2
    result = capsys.readouterr()
    assert result.out == '' and packet['pin'] not in result.err


def test_schema_command_reports_separate_witness_contracts_without_reading_keys(capsys):
    assert cli.main(['--schemas']) == 0
    report = json.loads(capsys.readouterr().out)
    assert report['registration'] and report['witness_registry']
    assert report['runtime_authorization'] == 'none' and not report['production_qualified']


@pytest.mark.parametrize('missing', ['registration_directory', 'witness_registry_directory'])
def test_partial_witness_options_are_invalid(packet, missing):
    with pytest.raises(ValueError):
        inspect(packet, **{missing: None})


@pytest.mark.parametrize('which', ['cli', 'scorer'])
def test_empty_trust_pin_is_not_ignored_by_schema_commands(which, capsys):
    assert (cli if which == 'cli' else scorer).main(['--schemas', '--trusted-registry-sha256', '']) == 2
    assert capsys.readouterr().out == ''


def test_no_rows_checks_registration_only_and_does_not_claim_execution_chronology(packet):
    base = packet['base']
    # Remove only the invented post-run receipt. It is not part of the casebook.
    row = json.loads((base / 'evaluation/tasks.jsonl').read_text())
    (base / 'artifacts' / (row['adjudication_evidence_sha256'] + '.bin')).unlink()
    report = reference_cases.inspect_casebook(base / 'intake', base / 'artifacts', base / 'catalog',
                registration_directory=base / 'registration', witness_registry_directory=base / 'trust',
                trusted_registry_sha256=packet['pin'])
    assert report['registration_witness']['measurement_records_checked'] == 0
    assert not report['registration_witness']['execution_start_authenticated']


def test_actual_cli_accepts_enrolled_signatures_and_preserves_synthetic_failure(packet, capsys):
    base = packet['base']
    args = [str(base / 'evaluation/tasks.jsonl'), '--snapshot', str(base / 'intake/snapshot.json'),
            '--protocol', str(base / 'intake/protocol.json'), '--casebook-dir', str(base / 'intake'),
            '--case-artifacts-dir', str(base / 'artifacts'), '--source-catalog-dir', str(base / 'catalog'),
            '--registration-dir', str(base / 'registration'), '--witness-registry-dir', str(base / 'trust'),
            '--trusted-registry-sha256', packet['pin']]
    assert scorer.main(args) == 1
    report = json.loads(capsys.readouterr().out)
    assert report['reference_cases']['registration_witness']['status'] == 'verified_signatures'
    path = base / 'trust/witness-registry.json'
    path.write_text('{}')
    assert scorer.main(args) == 2
    result = capsys.readouterr()
    assert result.out == '' and str(base) not in result.err
