"""Literal, bounded comparison of verified passages; never resolve legal identity."""

import hashlib

MAX_COMPARISON_WINDOW = 2000


class SourceComparisonUnavailable(ValueError):
    pass


def _sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _window(package, passage_id, offset, limit):
    passage = next((p for p in package.locators.passages if p.id == passage_id), None)
    if (passage is None or type(offset) is not int or type(limit) is not int
            or not 1 <= limit <= MAX_COMPARISON_WINDOW
            or not 0 <= offset < passage.end - passage.start):
        raise SourceComparisonUnavailable('Unknown passage or invalid comparison window')
    start = passage.start + offset
    end = min(start + limit, passage.end)
    text = package.text[start:end]
    return {
        'source_id': package.detail['id'], 'source_version_id': package.metadata.source_version_id,
        'title': package.metadata.title, 'source_url': package.metadata.source_url,
        'domain': package.metadata.domain, 'raw_media_type': package.metadata.raw_media_type,
        'artifacts': package.detail['artifacts'], 'source_text_code_points': len(package.text),
        'passage_id': passage.id, 'locator': passage.locator,
        'passage_start': passage.start, 'passage_end': passage.end,
        'passage_sha256': passage.text_sha256, 'start': start, 'end': end,
        'text': text, 'window_sha256': _sha(text),
        'next_offset': end - passage.start if end < passage.end else None,
        'integrity_scope': 'all_artifacts_verified',
    }


def literal_difference(left, right):
    """O(n) common edges, not an edit alignment or legal-change detector."""
    prefix = 0
    shortest = min(len(left), len(right))
    while prefix < shortest and left[prefix] == right[prefix]:
        prefix += 1
    suffix = 0
    while suffix < shortest - prefix and left[-1 - suffix] == right[-1 - suffix]:
        suffix += 1
    return {'scope': 'selected_windows_only', 'equal': left == right,
            'common_prefix_code_points': prefix, 'common_suffix_code_points': suffix,
            'left_range': [prefix, len(left) - suffix],
            'right_range': [prefix, len(right) - suffix],
            'range_unit': 'window_relative_unicode_code_points',
            'method': 'literal_common_edges_v1'}


def compare_sources(left, right, *, passage_id, other_passage_id,
                    offset=0, other_offset=0, limit=MAX_COMPARISON_WINDOW):
    if left.detail['id'] == right.detail['id']:
        raise SourceComparisonUnavailable('Choose two different source packages')
    a = _window(left, passage_id, offset, limit)
    b = _window(right, other_passage_id, other_offset, limit)
    return {
        'schema_version': 'public-source-comparison-v1', 'left': a, 'right': b,
        'offset_unit': 'unicode_code_points', 'window_limit': limit,
        'raw_bytes_equal': left.raw == right.raw,
        'extracted_text_equal': left.text == right.text,
        'difference': literal_difference(a['text'], b['text']),
        'normalization': 'none', 'legal_identity_status': 'unresolved',
        'legal_version_status': 'unresolved', 'independent_originals_verified': False,
        'current_law_verified': False, 'human_review_recorded': False,
        'limitations': [
            'Selected passages and offsets are chosen by the curator; no automatic provision alignment.',
            'Literal equality or difference does not establish legal identity, version or applicability.',
            'Common edges describe only selected windows, not all edits or source omissions.',
            'Extraction fidelity, rights and sensitivity require separate accountable human review.',
            'This unsigned mechanical record neither merges authorities nor qualifies independent study originals.',
        ],
    }
