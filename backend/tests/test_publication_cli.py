"""Offline CLI end-to-end using isolated TEST-ONLY ledgers and external signatures."""
import importlib.util
import json
from pathlib import Path

import pytest
from test_release_authorization import authorized as authorized_fixture
from test_release_authorization import mapping as mapping_fixture
from test_release_authorization import signed
from test_release_authorization import source as source_fixture
from test_release_authorization import workspace as workspace_fixture
from test_release_snapshot import operator_id
from test_source_reviews import assess

from app.graph_release import RuntimeGraphRelease, _load_serving
from app.release_authorization import ReleaseAuthorization
from app.release_snapshot import readonly_store

mapping = mapping_fixture
source = source_fixture
workspace = workspace_fixture
authorized = authorized_fixture
ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('publication_cli_tests', ROOT / 'scripts/review_publication.py')
cli = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cli)


def test_real_cli_candidate_external_approval_install_activation_and_revocation(authorized, tmp_path):
    fixture = dict(authorized)
    original = fixture['root']
    moved = original.with_name('private-review-input')
    original.rename(moved)
    fixture['auth_path'] = moved / fixture['info']['release_id'] / 'authorization.json'
    fixture['epoch_path'].rename(fixture['epoch_path'].with_name('input-policy-epoch'))
    app, client, sources, _, base = fixture['mapping']
    settings, tools = app.state.settings, fixture['tools']
    operator = operator_id(app)
    prepared = fixture['info']['bundle_path'].parent
    packet = fixture['auth_path'].parent / 'packet'
    assert cli.policy(settings)['policy_initialized']
    with pytest.raises(FileExistsError):
        cli.policy(settings)
    preview = tmp_path / 'signing-inputs'
    result = cli.candidate(settings, packet, operator_id=operator,
                           public_reviewer=fixture['info']['review']['reviewer'],
                           reviewed_at=fixture['info']['review']['reviewed_at'], output=preview)
    assert result == {'candidate_created': True, 'signed': False, 'publication_eligible': False}
    for family in ('structure', 'jurisprudence'):
        assert (preview / 'inputs' / (family + '.ttl')).read_bytes() == (fixture['info']['bundle_path'] / 'inputs' / (family + '.ttl')).read_bytes()
    output = tmp_path / 'authorization-request'
    cli.request(settings, prepared, packet=packet, operator_id=operator, trusted_review_key=fixture['public_key'],
                reviewer=fixture['body']['reviewer'], approved_at=fixture['body']['approved_at'],
                expires_at=fixture['body']['expires_at'], audience_evidence_sha256=fixture['evidence_digest'], output=output)
    body = json.loads((output / 'authorization-body.json').read_bytes())
    envelope = tmp_path / 'EXTERNALLY-SIGNED-TEST-ONLY.json'
    signed(envelope, body, fixture['key'], tools)
    result = cli.accept(settings, prepared, packet=packet, operator_id=operator,
                        trusted_review_key=fixture['public_key'], authorization=envelope)
    assert result['authorization_accepted'] and result['publication_performed'] is False
    destination = settings.data_dir / 'release-authorizations' / fixture['info']['release_id']
    assert destination.exists()
    assert all(p.stat().st_mode & 0o077 == 0 for p in (destination, *destination.rglob('*')))
    with pytest.raises(ValueError):
        cli.accept(settings, prepared, packet=packet, operator_id=operator,
                   trusted_review_key=fixture['public_key'], authorization=envelope)
    with readonly_store(settings) as reader:
        authorization = ReleaseAuthorization(reader, sources, settings.data_dir / 'release-authorizations',
                                             fixture['public_key'], ROOT / 'ontology', settings.data_dir / 'publication-epoch')
        serving = _load_serving()
        volume = tmp_path / 'isolated-graph-volume'
        serving.install(volume, prepared, fixture['public_key'], authorization_guard=authorization.guard)
        serving.activate(volume, body['release_id'], fixture['public_key'], expected_current=None,
                         expected_sequence=0, authorization_guard=authorization.guard)
        runtime = RuntimeGraphRelease(volume, fixture['public_key'], authorization_guard=authorization.guard)
        assert runtime.status()['status'] == 'verified'
        assert assess(client, base + '/review', 6, 'legal').status_code == 200
        assert runtime.status()['status'] == 'unavailable'
        with pytest.raises(ValueError):
            serving.install(volume, prepared, fixture['public_key'], authorization_guard=authorization.guard)
    assert not any(b'PRIVATE TEST' in path.read_bytes() for path in volume.rglob('*') if path.is_file())


@pytest.mark.parametrize('kind', ['bad_signature', 'changed_audience', 'stale_review'])
def test_accept_failure_never_installs_private_authorization(authorized, tmp_path, kind):
    fixture = dict(authorized)
    original = fixture['root']
    moved = original.with_name('private-review-input')
    original.rename(moved)
    fixture['auth_path'] = moved / fixture['info']['release_id'] / 'authorization.json'
    fixture['epoch_path'].rename(fixture['epoch_path'].with_name('input-policy-epoch'))
    app, client, _, _, base = fixture['mapping']
    cli.policy(app.state.settings)
    epoch = (app.state.settings.data_dir / 'publication-epoch').read_text().strip()
    body = {**fixture['body'], 'publication_epoch': epoch}
    if kind == 'changed_audience':
        body['audience'] = 'one_firm'
    envelope = tmp_path / 'external-approval.json'
    signed(envelope, body, fixture['key'], fixture['tools'])
    if kind == 'bad_signature':
        data = json.loads(envelope.read_bytes())
        data['signature'] = 'AAAA'
        envelope.write_bytes(fixture['tools'].canonical(data))
    if kind == 'stale_review':
        assert assess(client, base + '/review', 6, 'legal').status_code == 200
    with pytest.raises(ValueError):
        cli.accept(app.state.settings, fixture['info']['bundle_path'].parent,
                   packet=fixture['auth_path'].parent / 'packet', operator_id=operator_id(app),
                   trusted_review_key=fixture['public_key'], authorization=envelope)
    assert list((app.state.settings.data_dir / 'release-authorizations').iterdir()) == []


def test_parser_requires_explicit_review_identity_and_private_inputs():
    with pytest.raises(SystemExit):
        cli.parser().parse_args(['candidate', 'packet'])
