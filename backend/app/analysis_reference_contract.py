"""Source-qualified labels for bounded private proposal prose, not legal truth."""
import re

REFERENCE = re.compile(r"(?<!\w)([ms])\.([0-9]+)(?!\w)", re.IGNORECASE)
REFERENCE_STEM = re.compile(r"(?<!\w)[ms]\.[0-9]+", re.IGNORECASE)
HEADING = re.compile(r"^\s*(\d{1,8})\.\s+\S")
PAGE = re.compile(r"Sayfa\s+(\d{1,8})", re.IGNORECASE)


class ReferenceValidationError(ValueError):
    code = "proposal_reference_unqualified"

    def __init__(self):
        super().__init__("Proposal reference lacks a matching typed source label")


def reference_labels(content, evidence_ids):
    """A page never becomes a clause. Ambiguous/unrecognized labels stay absent.

    A contract-clause label requires both the fixed rule's explicit label and a
    matching heading at the beginning of its exact selected quotation. A page
    label comes only from the extractor locator, never an authored inference.
    """
    selected = set(evidence_ids)
    evidence = {item['evidence_id']: item for item in content['evidence'] if item['evidence_id'] in selected}
    labels = {('s', match[1]) for item in evidence.values()
              if (match := PAGE.fullmatch(item.get('locator', '')))}
    for rule in content['rules']:
        if rule['kind'] != 'contract_clause':
            continue
        declared = {number for kind, number in REFERENCE.findall(rule['text']) if kind.lower() == 'm'}
        for identity in set(rule['evidence_ids']) & selected:
            item = evidence.get(identity)
            match = HEADING.match(item['text']) if item else None
            if match and match[1] in declared:
                labels.add(('m', match[1]))
    return labels


def validate_patch_references(content, patch):
    rules = {item['id']: item for item in content['rules']}
    apps = {item['id']: item for item in content['applications']}
    conclusion_sources = {identity for app_id in content['conclusion']['application_ids']
                          for identity in rules[apps[app_id]['rule_id']]['evidence_ids']}

    def sources_for(target):
        if target == 'conclusion':
            return conclusion_sources
        if target in apps:
            return rules[apps[target]['rule_id']]['evidence_ids']
        if target in rules:
            return rules[target]['evidence_ids']
        return {identity for rule in rules.values() if any(c['id'] == target for c in rule['conditions'])
                for identity in rule['evidence_ids']}

    def check(value, identities):
        if value is not None:
            matches = REFERENCE.findall(value)
            stems = REFERENCE_STEM.findall(value)
            if not matches and not stems:
                return
            if (len(matches) != len(stems)
                    or not {(kind.lower(), number) for kind, number in matches} <= reference_labels(content, identities)):
                raise ReferenceValidationError()

    for update in patch.application_updates:
        check(update.rationale, sources_for(update.id))
    if patch.conclusion_update:
        for value in [patch.conclusion_update.text, patch.conclusion_update.next_step, *patch.conclusion_update.uncertainty]:
            check(value, conclusion_sources)
    for note in patch.review_notes:
        check(note.text, note.evidence_ids or sources_for(note.target_id))
    for response in patch.feedback_responses:
        check(response.text, response.evidence_ids)
    # Public authority numbers require a separately reviewed provision identity
    # mapping. They remain in existing exact authority links, not inferred here.
    for response in patch.authority_responses:
        check(response.text, [])
