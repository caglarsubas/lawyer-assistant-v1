"""Offline enrolled-key registration attestations; signatures cannot prove wall time."""

import json
from typing import Annotated, Literal

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import Field, model_validator

from .qualification import MAX_COMPONENT_BYTES, parse_component
from .qualification_evidence import read_exact_directory
from .qualification_scoring import instant, unique
from .reference_cases import MAX_CASES, sha
from .research_qualification import Digest, RecordId, StrictRecord

PublicKey = Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]
SignatureBytes = Annotated[str, Field(pattern=r'^[0-9a-f]{128}$')]
DOMAIN = b'legal-evaluation-registration-witness-v1\n'


class WitnessKey(StrictRecord):
    id: RecordId
    subject_id: RecordId
    purpose: Literal['evaluation_registration']
    public_key_hex: PublicKey
    valid_from: str = Field(min_length=1, max_length=80)
    valid_until: str = Field(min_length=1, max_length=80)
    revoked: bool

    @model_validator(mode='after')
    def interval(self):
        if instant(self.valid_from) >= instant(self.valid_until):
            raise ValueError('Invalid witness enrollment interval')
        return self


class WitnessRegistry(StrictRecord):
    schema_version: Literal['legal-evaluation-witness-registry-v1']
    keys: list[WitnessKey] = Field(min_length=2, max_length=100)

    @model_validator(mode='after')
    def identities(self):
        unique([key.id for key in self.keys])
        # A rotated subject may have multiple keys, but one key must not be
        # enrolled under two identities to simulate separate witnesses.
        unique([key.public_key_hex for key in self.keys])
        return self


class Registration(StrictRecord):
    schema_version: Literal['legal-evaluation-registration-v1']
    casebook_sha256: Digest
    protocol_file_sha256: Digest
    snapshot_file_sha256: Digest
    source_catalog_sha256: Digest
    witness_registry_sha256: Digest
    witnessed_at: str = Field(min_length=1, max_length=80)

    @model_validator(mode='after')
    def timestamp(self):
        instant(self.witnessed_at)
        return self


class WitnessSignature(StrictRecord):
    key_id: RecordId
    algorithm: Literal['Ed25519']
    signature_hex: SignatureBytes


class RegistrationEnvelope(StrictRecord):
    schema_version: Literal['legal-evaluation-registration-envelope-v1']
    body: Registration
    signatures: list[WitnessSignature] = Field(min_length=2, max_length=10)

    @model_validator(mode='after')
    def keys(self):
        unique([signature.key_id for signature in self.signatures])
        return self


def signing_bytes(body):
    """All witnesses sign the same typed body with an explicit purpose prefix."""
    body = Registration.model_validate(body)
    return DOMAIN + json.dumps(body.model_dump(), sort_keys=True, ensure_ascii=False,
                               separators=(',', ':'), allow_nan=False).encode()


def verify_registration(directory, trust_directory, trusted_registry_sha256, captured,
                        catalog_sha256, registered_at, measured_at=()):
    """The out-of-band registry pin is mandatory; no key is trusted from its envelope.

    Times are signed declarations, not authenticated timestamps or proof that
    execution had not already started. Reports omit subject/key identities.
    """
    if (type(trusted_registry_sha256) is not str or len(trusted_registry_sha256) != 64
            or any(char not in '0123456789abcdef' for char in trusted_registry_sha256)):
        raise ValueError('An independently supplied witness registry pin is required')
    if type(measured_at) not in (list, tuple) or len(measured_at) > MAX_CASES:
        raise ValueError('Measurement chronology exceeds the bounded case inventory')
    specs = {'registration.json': MAX_COMPONENT_BYTES}
    trust_specs = {'witness-registry.json': MAX_COMPONENT_BYTES}
    raw = read_exact_directory(directory, specs, MAX_COMPONENT_BYTES)
    trusted = read_exact_directory(trust_directory, trust_specs, MAX_COMPONENT_BYTES)
    if sha(trusted['witness-registry.json']) != trusted_registry_sha256:
        raise ValueError('Witness registry differs from its independent pin')
    registry = WitnessRegistry.model_validate(parse_component(trusted['witness-registry.json']))
    envelope = RegistrationEnvelope.model_validate(parse_component(raw['registration.json']))
    body = envelope.body
    expected = {'casebook_sha256': sha(captured['casebook.json']),
                'protocol_file_sha256': sha(captured['protocol.json']),
                'snapshot_file_sha256': sha(captured['snapshot.json']),
                'source_catalog_sha256': catalog_sha256,
                'witness_registry_sha256': trusted_registry_sha256}
    if any(getattr(body, key) != value for key, value in expected.items()):
        raise ValueError('Registration does not bind the exact frozen inventory')
    witnessed_at = instant(body.witnessed_at)
    if witnessed_at < instant(registered_at) or any(instant(value) < witnessed_at for value in measured_at):
        raise ValueError('Declared registration/measurement chronology differs')
    keys = {key.id: key for key in registry.keys}
    subjects = set()
    payload = signing_bytes(body)
    for signature in envelope.signatures:
        key = keys.get(signature.key_id)
        if (key is None or key.revoked or not instant(key.valid_from) <= witnessed_at < instant(key.valid_until)
                or key.subject_id in subjects):
            raise ValueError('Witness key is unknown, revoked, expired or repeats a subject')
        try:
            Ed25519PublicKey.from_public_bytes(bytes.fromhex(key.public_key_hex)).verify(
                bytes.fromhex(signature.signature_hex), payload)
        except (InvalidSignature, ValueError):
            raise ValueError('Invalid registration signature') from None
        subjects.add(key.subject_id)
    if (read_exact_directory(directory, specs, MAX_COMPONENT_BYTES) != raw
            or read_exact_directory(trust_directory, trust_specs, MAX_COMPONENT_BYTES) != trusted):
        raise ValueError('Registration or trusted registry changed during verification')
    return {'status': 'verified_signatures', 'signature_count': len(subjects),
            'registration_sha256': sha(raw['registration.json']),
            'witness_registry_sha256': trusted_registry_sha256,
            'measurement_records_checked': len(measured_at),
            'declared_chronology_consistent': True, 'registration_time_authenticated': False,
            'execution_start_authenticated': False, 'witness_independence_verified': False,
            'current_registry_authenticated': False, 'legal_qualification': False,
            'runtime_authorization': 'none', 'production_qualified': False}
