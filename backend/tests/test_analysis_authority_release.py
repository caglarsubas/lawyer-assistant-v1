"""Real signed bytes and pointer checks, simulated permissions, invented law only."""

import base64
import json
from contextlib import contextmanager

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import select
from test_analysis_authorities import freeze
from test_analysis_authorities import workbench as workbench_fixture
from test_analysis_workbench import create
from test_release_preparation import ONTOLOGY, compile_fixture
from test_release_preparation import preparation as preparation_fixture

from app.analysis_authorities import IDENTITY
from app.db import User
from app.graph_release import RuntimeGraphRelease, _load_serving
from app.release_promotion import signing_inputs

workbench = workbench_fixture


class SyntheticRights:
    active = True

    @contextmanager
    def guard(self, info, action):
        assert action in {'read', 'install', 'activate', 'rollback'}
        if not self.active:
            raise ValueError('PRIVATE RIGHTS CANARY')
        yield {'release_id': info['release_id'], 'current': True}
        if not self.active:
            raise ValueError('PRIVATE RIGHTS CANARY')


def signed_source(workbench, monkeypatch, root):
    """Only isolated test storage/key. No actual rights or source review is granted."""
    app, client, base, *_ = workbench
    root.mkdir(parents=True, exist_ok=True)
    prepared = preparation_fixture.__wrapped__(root)
    files, summary = compile_fixture(prepared)
    outputs = signing_inputs(files, ontology_sha256=summary['ontology_sha256'],
        public_reviewer='SYNTHETIC SOURCE — TEST ONLY, NOT LEGAL REVIEW', reviewed_at='2026-01-01T00:00:00Z')
    for name, raw in outputs.items():
        path = root / 'signing' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    key = Ed25519PrivateKey.generate()
    public = root / 'TEST-ONLY-public.pem'
    public.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    body_bytes = outputs['public-review-body.json']
    attestation = root / 'TEST-ONLY-attestation.json'
    attestation.write_text(json.dumps({'algorithm': 'Ed25519', 'body': json.loads(body_bytes),
        'signature': base64.b64encode(key.sign(body_bytes)).decode()}))
    serving = _load_serving()
    bundle, release_root = root / 'bundle', root / 'serving'
    serving._release.create_bundle(ONTOLOGY, {family: root / 'signing/inputs' / (family + '.ttl')
        for family in serving.FAMILIES}, root / 'signing/evidence', bundle, attestation, public)
    serving.prepare(bundle, public, root / 'prepared')
    permission = SyntheticRights()
    installed = serving.install(release_root, root / 'prepared', public, authorization_guard=permission.guard)
    serving.activate(release_root, installed['release_id'], public, expected_current=None, authorization_guard=permission.guard)
    reader = RuntimeGraphRelease(release_root, public, authorization_guard=permission.guard)
    assert reader.status()['status'] == 'verified'
    monkeypatch.setattr(app.state.graph, 'release', reader)
    analysis = create(workbench)
    # This packet intentionally tests a historical 2011 source against a 2024
    # private event. Matching dates are never fabricated by selection.
    with reader.current_guard():
        hits = [source for source in reader.iter_search_documents() if reader.project_search_hit(source, as_of='2011-03-01')]
    pin = {'status': 'verified', 'release_id': reader.info['release_id'], 'serving_sha256': reader.info['serving_sha256'],
           'activation_sequence': reader.info['pointer']['sequence']}
    with app.state.store.session() as session:
        user = session.scalar(select(User).where(User.username == 'demo'))
        row = app.state.store.add(session, 'product', user, {'title': 'SYNTHETIC signed-source research', 'status': 'needs_review',
            'snapshots': {'graph_release_pin': pin}, 'authority_candidates': {'hits': hits,
                'snapshot': {'release_id': pin['release_id'], 'as_of': '2011-03-01'},
                'limitations': ['SYNTHETIC fixture; no actual Turkish source or review']}}, base.split('/')[-1])
        session.commit()
    hit = next(source for source in hits if reader.authority_context(source, as_of='2011-03-01')['target_provision_version'])
    endpoint = base + '/analyses/' + analysis['id'] + '/authority-contexts'
    spec = {'version_id': analysis['latest_version_id'], 'product_id': row.id,
        'title': 'SYNTHETIC signed-source context', 'purpose': 'SYNTHETIC exact byte and date inspection only',
        'selections': [{**{name: hit[name] for name in IDENTITY}, 'target_ids': ['rule:r1', 'application:a1'],
            'relationship': 'unresolved', 'note': 'SYNTHETIC — Dates differ. No legal applicability assessment.'}]}
    return endpoint, spec, reader, permission, prepared


def test_signed_physical_source_is_exact_and_current_permission_and_pointer_are_required(workbench, monkeypatch, tmp_path):
    app, client, *_ = workbench
    endpoint, spec, reader, permission, prepared = signed_source(workbench, monkeypatch, tmp_path / 'signed-fixture')
    monkeypatch.setattr(app.state.provider, 'generate', lambda *_: (_ for _ in ()).throw(AssertionError('No inference')))
    value, _ = freeze(client, endpoint, spec)
    source = value['manifest']['sources'][0]['evidence']
    assert source['text'] == prepared['snapshot']['package'].text[source['start_offset']:source['end_offset']]
    assert source['source_sha256'] == prepared['snapshot']['package'].locators.raw_sha256
    assert source['text_sha256'] == prepared['snapshot']['package'].locators.text_sha256
    assert value['manifest']['sources'][0]['temporal_alignment']['target_version_within_interval'] is False
    assert client.get(endpoint + '/' + value['id'] + '/export').status_code == 200
    assert all('PRIVATE' not in path.read_text(errors='replace') for path in (reader.info['bundle_path'] / 'inputs').glob('*.ttl'))
    permission.active = False
    withheld = client.get(endpoint + '/' + value['id']).json()
    assert withheld['manifest'] is None and 'PRIVATE' not in json.dumps(withheld)
    assert client.get(endpoint + '/' + value['id'] + '/export').status_code == 409
    permission.active = True
    pointer = reader.root / 'active.json'
    changed = json.loads(pointer.read_text())
    changed['sequence'] += 1
    pointer.chmod(0o600)  # Deliberate corruption of this test-only read-only pointer.
    pointer.write_text(json.dumps(changed))
    assert client.get(endpoint + '/' + value['id']).json()['manifest'] is None
    assert client.get(endpoint + '/' + value['id'] + '/export').status_code == 409
