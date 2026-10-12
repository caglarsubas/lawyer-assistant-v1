"""Release fixtures may share seed bytes, never writable copies or live verdicts."""
from pathlib import Path

import pytest
from test_runtime_graph_release import active_release

from app.graph_release import _load_serving


def hashes(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_each_copy_revalidates_and_mutation_cannot_reach_seed_or_sibling(tmp_path, synthetic_active_release_template, monkeypatch):
    template_root, _, _ = synthetic_active_release_template
    seed = hashes(template_root)
    serving = _load_serving()
    original, verified = serving.validate_prepared, []
    def counted(root, key):
        verified.append((Path(root), Path(key)))
        return original(root, key)
    monkeypatch.setattr(serving, "validate_prepared", counted)
    results = []
    for name in ("first", "second"):
        directory = tmp_path / name
        directory.mkdir()
        results.append(active_release.__wrapped__(directory, synthetic_active_release_template))
    assert len(verified) == 2 and verified[0] != verified[1]
    first, second = results
    assert first[2] is not second[2] and first[2]["graphs"] is not second[2]["graphs"]
    original_second = hashes(second[0])
    damaged = first[0] / "releases" / first[2]["release_id"] / "structure.nq"
    damaged.chmod(0o600)
    damaged.write_bytes(b"changed TEST-ONLY derivative")
    with pytest.raises(ValueError):
        original(damaged.parent, first[1])
    assert hashes(template_root) == seed and hashes(second[0]) == original_second
    assert original(second[0] / "releases" / second[2]["release_id"], second[1])["release_id"] == second[2]["release_id"]


def test_changed_copy_trust_key_is_not_hidden_by_fixture_reuse(tmp_path, synthetic_active_release_template):
    root, key, info = active_release.__wrapped__(tmp_path, synthetic_active_release_template)
    key.write_bytes(b"different TEST-ONLY key bytes")
    with pytest.raises(ValueError):
        _load_serving().validate_prepared(root / "releases" / info["release_id"], key)


def test_prepared_copies_are_independent_and_preparation_subject_stays_fresh(tmp_path, synthetic_serving_seeds, monkeypatch):
    from test_serving_releases import SeedTrust, prepared, serving

    key, seeds = synthetic_serving_seeds
    public = tmp_path / "TEST-ONLY-key.pem"
    from cryptography.hazmat.primitives import serialization
    public.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    trust = SeedTrust(key, public, seeds)
    before = hashes(seeds["a"])
    original, calls = serving.prepare, []
    def counted(*args, **kwargs):
        calls.append(args)
        return original(*args, **kwargs)
    monkeypatch.setattr(serving, "prepare", counted)
    copies = []
    for name in ("first", "second", "fresh"):
        directory = tmp_path / name
        directory.mkdir()
        copies.append(prepared(directory, trust, fresh=name == "fresh"))
    assert len(calls) == 1  # Dedicated preparation tests still execute the subject.
    assert len({result[0] for result in copies}) == 3
    target = copies[0][0] / "structure.nq"
    target.chmod(0o600)  # Simulate an out-of-band writer; production remains immutable.
    target.write_bytes(b"tampered TEST-ONLY copy")
    with pytest.raises(ValueError):
        serving.validate_prepared(copies[0][0], public)
    assert hashes(seeds["a"]) == before
    assert serving.validate_prepared(copies[1][0], public)["release_id"] == copies[1][1]["release_id"]


@pytest.mark.parametrize('kind', ['single', 'set'])
def test_authorized_copies_reverify_private_rights_and_never_modify_template_or_sibling(tmp_path, request, kind):
    from test_release_authorization import authorized, guard
    from test_release_set_authorization import authorized_set, guard_set
    from test_source_reviews import assess

    from app.release_authorization import AuthorizationError
    template = request.getfixturevalue('synthetic_authorized_seed' if kind == 'single' else 'synthetic_authorized_set_seed')
    before = hashes(template[0])
    build, verify = (authorized, guard) if kind == 'single' else (authorized_set, guard_set)
    lifetimes, copies = [], []
    try:
        for name in ('first', 'second'):
            folder = tmp_path / name
            folder.mkdir()
            lifetime = build.__wrapped__(folder, template)
            lifetimes.append(lifetime)
            copies.append(next(lifetime))
        first, second = copies
        assert first['body'] is not second['body'] and first['files'] is not second['files']
        mapping = first['mapping'] if kind == 'single' else first['mappings'][0]
        assert assess(mapping[1], mapping[4] + '/review', 6, 'rights', decision='needs_changes').status_code == 200
        with pytest.raises(AuthorizationError):
            with verify(first):
                pass
        with verify(second):
            pass
        assert hashes(template[0]) == before
    finally:
        for lifetime in lifetimes:
            lifetime.close()


def test_authorization_setup_builder_still_runs_complete_fresh_source_review(tmp_path):
    from test_provision_mappings import mapping
    from test_public_sources import source
    from test_release_authorization import build_authorized, guard
    from test_workspace import workspace
    lifetime = workspace.__wrapped__(tmp_path)
    try:
        fixture = build_authorized(mapping.__wrapped__(next(lifetime), source.__wrapped__(tmp_path)), tmp_path)
        with guard(fixture):
            pass
        assert fixture['body']['source_binding']['source_review_revision'] == 6
        assert fixture['info']['review']['verified']
    finally:
        lifetime.close()
