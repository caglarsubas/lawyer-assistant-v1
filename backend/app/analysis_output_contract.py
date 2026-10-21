"""Finite local sampling contracts, shared verbatim with the isolated relay.

No caller schema, external reference, source text or identifier enters a contract.
The application still checks fixed draft targets, evidence and legal constraints.
"""

import copy
import json
import re

PROSE_LIMIT = 400
# Numbered facts and legal/source locators stay in fixed, evidenced fields. The
# model edits prose only; identifiers remain available in separate link fields.
PROSE_PATTERN = r"^(?:[^0-9\r\n*`#.!?;]|[ms]\.[0-9]+){1,399}[.!?]$"
DANGLING_END = re.compile(
    r"\b(?:ve|veya|yahut|ancak|ama|fakat|ile|için|gibi|çünkü|rağmen|"
    r"and|or|but|because|however|although|unless|vb|vd|etc|m|s|md|art)[.!?]$", re.IGNORECASE)
ROMAN_LOCATOR = re.compile(
    r"\b(?:article|art\.?|madde|m\.|sayfa|page|s\.)\s*[ivxlcdm]+\b|"
    r"\b[ivxlcdm]+\.?\s*(?:madde|sayfa|article|page)\b", re.IGNORECASE)


class ProseValidationError(ValueError):
    """Safe diagnostic only; never include generated text or case identifiers."""

    def __init__(self, reason="boundary"):
        self.reason = reason if reason in {"reference", "boundary", "limit", "style"} else "boundary"
        super().__init__("Unsafe or unfinished proposal prose")


def _check_prose(value):
    # Only canonical candidate labels are allowed through the wire. Exact typed
    # source qualification follows in apply_patch; these labels are not grants.
    without_labels = re.sub(r"\b[ms]\.[0-9]+(?!\w)", " ", value)
    if (any(char.isnumeric() for char in without_labels) or ROMAN_LOCATOR.search(value)
            or re.search(r"\b(?:ev|r)\.[\w]+|\b[ms]\.(?![0-9])[A-Za-z_]+", value, re.IGNORECASE)):
        raise ProseValidationError("reference")
    if len(value) >= PROSE_LIMIT:
        raise ProseValidationError("limit")
    if (not any(char.isalpha() for char in without_labels) or value != value.strip()
            or any(char in value for char in "\r\n*`#")):
        raise ProseValidationError("style")
    if not re.fullmatch(PROSE_PATTERN, value) or DANGLING_END.search(value):
        raise ProseValidationError("boundary")


def _object(properties):
    return {"type": "object", "properties": properties,
            "required": list(properties), "additionalProperties": False}


def _array(items, maximum):
    return {"type": "array", "items": items, "maxItems": maximum}


def analysis_response_format(review=False, authority=False):
    identifier = {"$ref": "#/$defs/i"}
    text = {"$ref": "#/$defs/t"}
    refs = _array(identifier, 20)
    application = _object({"id": identifier, "rationale": {"anyOf": [text, {"type": "null"}]},
        "assessments": _array(_object({"condition_id": identifier,
            "status": {"enum": ["unknown", "met", "not_met"]}, "premise_ids": refs}), 12)})
    conclusion = _object({"text": text, "uncertainty": _array(text, 3 if review or authority else 0), "next_step": text})
    conclusion["type"] = ["object", "null"]
    properties = {"application_updates": _array(application, 12 if review or authority else 1), "conclusion_update": conclusion,
                  "review_notes": _array(_object({"target_id": identifier, "text": text,
                                                  "evidence_ids": refs}), 3 if review or authority else 1)}
    for selected, name, sources in ((review, "feedback_responses", "evidence_ids"),
                                    (authority, "authority_responses", "authority_ids")):
        if selected:
            properties[name] = _array(_object({"finding_id": identifier,
                "outcome": {"enum": ["proposed_change", "requires_manual_work", "unresolved"]},
                "edited_targets": refs, "text": text, sources: refs}), 5)
    suffix = ("_review" if review else "") + ("_authority" if authority else "")
    schema = _object(properties)
    schema["$defs"] = {"i": {"type": "string", "minLength": 1, "maxLength": 129},
                       "t": {"type": "string", "minLength": 2, "maxLength": PROSE_LIMIT, "pattern": PROSE_PATTERN}}
    return {"type": "json_schema", "json_schema": {"name": "private_analysis_v7" + suffix,
                                                    "strict": True, "schema": schema}}


def admitted_response_format(value):
    # Equality against four server-owned contracts prohibits arbitrary schemas,
    # remote $ref, grammar extensions and unbounded sampling fields.
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError):
        return False
    return any(encoded == json.dumps(analysis_response_format(review, authority),
                                     sort_keys=True, separators=(",", ":"))
               for review in (False, True) for authority in (False, True))


def response_format_for_messages(messages):
    payload = json.loads(messages[-1]["content"])
    return analysis_response_format(bool(payload.get("selected_review_findings")),
                                    bool(payload.get("selected_authority_findings")))


def validate_analysis_output(raw, response_format):
    """Check the exact small wire contract independently of upstream enforcement.

    Only our fixed schema vocabulary is interpreted. Pydantic and draft-scoped
    checks follow; a conforming JSON document is never evidence of legal truth.
    """
    if not admitted_response_format(response_format) or len(raw.encode("utf-8")) > 32768:
        raise ValueError("Invalid analysis output contract or size")

    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("Duplicate output key")
            value[key] = item
        return value

    root = response_format["json_schema"]["schema"]

    def check(value, schema):
        if "anyOf" in schema:
            # Our only union is the fixed nullable prose field. Preserve the
            # prose diagnostic if its string alternative fails that guard.
            failures = []
            for alternative in schema["anyOf"]:
                try:
                    check(value, alternative)
                    return
                except ValueError as exc:
                    failures.append(exc)
            for exc in failures:
                if isinstance(exc, ProseValidationError):
                    raise exc
            raise ValueError("Invalid output union")
        if "$ref" in schema:
            check(value, root["$defs"][schema["$ref"].removeprefix("#/$defs/")])
            return
        if "enum" in schema:
            if value not in schema["enum"] or not isinstance(value, str):
                raise ValueError("Invalid output enum")
            return
        types = schema["type"]
        types = types if isinstance(types, list) else [types]
        if value is None and "null" in types:
            return
        if isinstance(value, dict) and "object" in types:
            if set(value) != set(schema["required"]):
                raise ValueError("Invalid output fields")
            for key, item in value.items():
                check(item, schema["properties"][key])
        elif isinstance(value, list) and "array" in types:
            if len(value) > schema["maxItems"]:
                raise ValueError("Too many output entries")
            for item in value:
                check(item, schema["items"])
        elif isinstance(value, str) and "string" in types:
            if not schema["minLength"] <= len(value) <= schema["maxLength"]:
                raise ValueError("Invalid output text length")
            if "pattern" in schema:
                # A forced grammar boundary can end a string mid-sentence even
                # with finish_reason=stop. Do not add punctuation or rewrite it.
                _check_prose(value)
        else:
            raise ValueError("Invalid output type")

    check(json.loads(raw, object_pairs_hook=unique), copy.deepcopy(root))
