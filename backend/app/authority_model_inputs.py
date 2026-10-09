"""Typed public trial inputs: a current original review or an admitted renewal."""
from typing import Literal

from fastapi import HTTPException
from pydantic import Field, model_validator

from . import analysis_authorities as authorities
from . import authority_findings as findings
from . import authority_proposals as proposals
from . import authority_revalidations as renewals
from .analysis_feedback import editable_targets
from .analysis_workbench import _freshness
from .auth import require_child
from .db import digest
from .evidence_prompt import canonical
from .practice import StrictInput

RECIPE = 'registered-authority-model-input-v1'


class Selection(StrictInput):
    kind: Literal['original_review', 'admitted_renewal']
    context_id: str = Field(min_length=1, max_length=64)
    review_id: str = Field(min_length=1, max_length=64)
    review_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    renewal_id: str | None = Field(default=None, min_length=1, max_length=64)
    renewal_sha256: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')
    findings: list[proposals.SelectedFinding] = Field(min_length=1, max_length=5)

    @model_validator(mode='after')
    def distinct(self):
        if len({(item.source_index, item.dimension) for item in self.findings}) != len(self.findings):
            raise ValueError('Select distinct findings')
        if (self.kind == 'admitted_renewal') != bool(self.renewal_id and self.renewal_sha256):
            raise ValueError('A renewal requires both its identifier and seal')
        if self.kind == 'original_review' and (self.renewal_id or self.renewal_sha256):
            raise ValueError('Original review inputs cannot claim renewal provenance')
        return self


def resolve(app, session, matter_id, analysis_id, version_id, user, selection):
    store = app.state.store
    renewals._lawyer(session, matter_id, user)
    row = require_child(session, analysis_id, 'practice_analysis', matter_id, user)
    content = store.decode(row)
    if content['latest_version_id'] != version_id or _freshness(store, session, matter_id, user, content)['status'] != 'current':
        raise HTTPException(409, 'Deneme güncel taslak sürümüne bağlanmalıdır.')
    proposals.check_admission(store, session, matter_id, user, content)
    if selection.kind == 'original_review':
        spec = proposals.AuthorityFeedbackSelection(**selection.model_dump(exclude={'kind', 'renewal_id', 'renewal_sha256'}))
        feedback, _ = proposals.resolve(app, session, matter_id, analysis_id, version_id, user, spec)
        review = findings._view(app, session, matter_id, analysis_id, selection.context_id, selection.review_id, user)['snapshot']
        assessment = review['assessment']
        manifest = review['context_snapshot']['manifest']
        reviewer_id = review['reviewer_id']
        input_ref = {'kind': selection.kind, 'id': selection.review_id, 'sha256': selection.review_sha256}
    else:
        values = renewals.records(store, session, matter_id, user, content)
        if not values or values[-1]['id'] != selection.renewal_id or values[-1]['sha256'] != selection.renewal_sha256:
            raise HTTPException(409, 'Yalnız son kabul edilmiş güncel bağ yenilemesini seçin.')
        value = values[-1]
        deps = proposals.dependencies(content)
        dep = next((item for item in deps if all(item[key] == getattr(selection, key)
                   for key in ('context_id', 'review_id', 'review_sha256'))), None)
        if not dep:
            raise HTTPException(409, 'Bağ yenilemesinin özgün kaynak bağı bulunamadı.')
        assessment = next((item for item in value['snapshot']['renewals']
                           if item['dependency_sha256'] == digest(canonical(dep))), None)
        if not assessment:
            raise HTTPException(409, 'Yenilenmiş kaynak değerlendirmesi bulunamadı.')
        _, context, _, _ = authorities._require(store, session, matter_id, analysis_id, selection.context_id, user)
        manifest = context['manifest']
        reviewer_id = value['snapshot']['reviewer_id']
        selected, sources = [], {}
        for item in sorted(selection.findings, key=lambda item: (item.source_index, item.dimension)):
            if item.source_index >= len(assessment['sources']):
                raise HTTPException(422, 'Yenilemede bulunmayan kaynak seçilemez.')
            assessed = assessment['sources'][item.source_index]
            source = next(source for source in manifest['sources']
                          if findings._identity(source['selection']) == findings._identity(assessed))
            observation = next(value for value in assessed['observations'] if value['dimension'] == item.dimension)
            if observation['outcome'] not in {'needs_change', 'unresolved', 'not_assessed'}:
                raise HTTPException(422, 'Yalnız açık veya değişiklik gereken bulguları seçin.')
            ident = 'authority:' + str(item.source_index)
            sources[ident] = {'id': ident, 'selection': source['selection'], 'evidence': source['evidence'],
                             'temporal_alignment': source['temporal_alignment']}
            selected.append({'finding_id': ident + ':' + item.dimension, 'authority_id': ident,
                **observation, 'target_ids': assessed['target_ids'],
                'editable_targets': list(dict.fromkeys(target for original in assessed['target_ids']
                    for target in editable_targets(content, original)))})
        feedback = {'recipe': proposals.RECIPE, 'scope': 'selected_authority_findings_not_resolution',
                    'dependency': dep, 'findings': selected, 'sources': list(sources.values())}
        input_ref = {'kind': selection.kind, 'id': value['id'], 'sha256': value['sha256']}
    # The separate human basis never enters a prompt; only selected feedback does.
    basis = {'recipe': RECIPE, 'input_ref': input_ref, 'reviewer_id': reviewer_id,
             'original_dependency': feedback['dependency'], 'manifest': manifest,
             'assessment': assessment, 'authority_dimensions': findings.DIMENSIONS}
    if len(canonical(feedback).encode()) > 128 * 1024 or len(canonical(basis).encode()) > 2 * 1024 * 1024:
        raise HTTPException(409, 'Deneme girdisi sınırı aşıyor; özgün kanıt kesilemez.')
    return feedback, basis
