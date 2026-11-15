"""Bind DOCX tracked-change warnings to the frozen parser's exact passages."""

import io
import json
import re
import resource
import secrets
import signal
import sys
import time
import zipfile
from pathlib import Path

from docx.opc.constants import CONTENT_TYPE as CT
from docx.oxml.ns import qn
from lxml import etree

from .docx_textboxes import BOX, prepare_textboxes
from .extract import MAX_DOCX_BLOCKS, extract
from .extraction_client import MAX_RESPONSE_BYTES

DOCUMENT_WARNING = "İzlenen değişiklikler var; kabul edilmiş sürüm doğrulanmadı."
PASSAGE_WARNING = "{locator}: İzlenen değişiklik var; özgün pasajı inceleyin."
UNBOUND_WARNING = "İzlenen değişiklik içeren bazı kaynak bölümlerinden pasaj çıkarılmadı; özgün belgeyi inceleyin."
UNKNOWN_WARNING = "DOCX değişikliklerinin pasaj konumları doğrulanamadı; özgün belgeyi inceleyin."

_MAX_PROBE_BYTES = 32 * 1024 * 1024
_MAX_STORY_BYTES = 8 * 1024 * 1024
_MAX_MARKED_PARAGRAPHS = 2_000
_PROBE_SECONDS = 4
_CONTENT_TYPES_NAMESPACE = "{http://schemas.openxmlformats.org/package/2006/content-types}"
_STORIES = {
    CT.WML_DOCUMENT_MAIN: qn("w:document"),
    CT.WML_HEADER: qn("w:hdr"),
    CT.WML_FOOTER: qn("w:ftr"),
    CT.WML_FOOTNOTES: qn("w:footnotes"),
    CT.WML_ENDNOTES: qn("w:endnotes"),
}
_PARAGRAPH = qn("w:p")
_REVISIONS = tuple(qn("w:" + name) for name in (
    "ins", "del", "moveFrom", "moveTo", "rPrChange", "pPrChange", "numberingChange",
    "tblPrChange", "tblGridChange", "tblPrExChange", "trPrChange", "tcPrChange",
    "cellIns", "cellDel", "cellMerge", "sectPrChange",
))
_TABLE_PROPERTIES = frozenset(qn("w:" + name) for name in ("tblPr", "tblGrid", "tblPrEx", "trPr", "tcPr"))
_STRUCTURAL_CONTAINERS = frozenset(qn("w:" + name) for name in ("tbl", "tr", "tc"))
_RANGE_MARKS = tuple(qn("w:" + name) for name in (
    "moveFromRangeStart", "moveFromRangeEnd", "moveToRangeStart", "moveToRangeEnd",
    "customXmlInsRangeStart", "customXmlInsRangeEnd", "customXmlDelRangeStart", "customXmlDelRangeEnd",
    "customXmlMoveFromRangeStart", "customXmlMoveFromRangeEnd",
    "customXmlMoveToRangeStart", "customXmlMoveToRangeEnd",
))


def _xml(archive, member, tag):
    root = etree.fromstring(archive.read(member), etree.XMLParser(resolve_entities=False, no_network=True))
    if root.tag != tag or root.getroottree().docinfo.doctype:
        raise ValueError("DOCX revision inspection cannot verify package part")
    return root


def _story_members(archive):
    member = archive.getinfo("[Content_Types].xml")
    if member.file_size > _MAX_STORY_BYTES:
        raise ValueError("DOCX revision manifest exceeds inspection budget")
    manifest = _xml(archive, member, _CONTENT_TYPES_NAMESPACE + "Types")
    overrides = {node.get("PartName"): node.get("ContentType")
                 for node in manifest if node.tag == _CONTENT_TYPES_NAMESPACE + "Override"}
    defaults = {node.get("Extension", "").casefold(): node.get("ContentType")
                for node in manifest if node.tag == _CONTENT_TYPES_NAMESPACE + "Default"}
    for part in archive.infolist():
        extension = part.filename.rsplit(".", 1)[-1].casefold()
        content_type = overrides.get("/" + part.filename, defaults.get(extension))
        if content_type in _STORIES:
            yield part, _STORIES[content_type]


def _revision_paragraphs(root):
    affected = set()
    observed = unbound = any(True for _ in root.iter(*_RANGE_MARKS))
    for change in root.iter(*_REVISIONS):
        observed = True
        if any(True for _ in change.iter(_PARAGRAPH, *_STRUCTURAL_CONTAINERS)):
            # Block-level revision wrappers are omitted by the original parser.
            unbound = True
            continue
        paragraphs = []
        parent = change.getparent()
        if parent.tag in _TABLE_PROPERTIES:
            owner = next((node for node in parent.iterancestors() if node.tag in _STRUCTURAL_CONTAINERS), None)
            if owner is not None:
                paragraphs = list(owner.iter(_PARAGRAPH))
        elif change.tag != qn("w:sectPrChange"):
            owner = next((node for node in change.iterancestors() if node.tag == _PARAGRAPH), None)
            if owner is not None:
                paragraphs = [owner]
        affected.update(paragraphs)
        unbound |= not paragraphs
        if len(affected) > _MAX_MARKED_PARAGRAPHS:
            raise ValueError("DOCX revision inspection paragraph limit exceeded")
    return affected, observed, unbound


def _normalize_textboxes(root):
    # Equal alternatives share one evidence passage. Normalize only the
    # disposable tree so unique markers do not make equal branches disagree.
    if not any(True for _ in root.iter(BOX)):
        return
    visited = 0

    def visit():
        nonlocal visited
        visited += 1
        if visited > MAX_DOCX_BLOCKS:
            raise ValueError("DOCX revision text-box inspection limit exceeded")

    prepare_textboxes(root, visit)


def _probe_package(source, marker_prefix):
    """Mark a bounded in-memory copy. No derived DOCX is written to disk."""
    with zipfile.ZipFile(source) as archive:
        stories = list(_story_members(archive))
        if sum(member.file_size for member, _ in stories) > _MAX_STORY_BYTES:
            raise ValueError("DOCX text parts exceed revision inspection budget")
        changed = {}
        markers = set()
        observed = unbound = False
        for member, tag in stories:
            root = _xml(archive, member, tag)
            _normalize_textboxes(root)
            owners, has_revisions, unknown_owners = _revision_paragraphs(root)
            observed |= has_revisions
            unbound |= unknown_owners
            if not owners:
                continue
            if len(markers) + len(owners) > _MAX_MARKED_PARAGRAPHS:
                raise ValueError("DOCX revision inspection paragraph limit exceeded")
            for node in owners:
                marker = f"{marker_prefix}{len(markers)}⟧"
                markers.add(marker)
                run = etree.SubElement(node, qn("w:r"))
                etree.SubElement(run, qn("w:t")).text = marker
            changed[member.filename] = etree.tostring(root, encoding="UTF-8")
        if not changed:
            return None, markers, observed, unbound
        if sum(part.file_size for part in archive.infolist()) > _MAX_PROBE_BYTES:
            raise ValueError("DOCX package exceeds revision probe budget")
        probe = io.BytesIO()
        with zipfile.ZipFile(probe, "w") as marked:
            for part in archive.infolist():
                payload = changed.get(part.filename)
                marked.writestr(part.filename, payload if payload is not None else archive.read(part))
        return probe, markers, observed, unbound


def _bind_probe(result, probe, marker_prefix, markers):
    projected = extract(probe, ".docx")["passages"]
    expected = result["passages"]
    projected_originals = []
    marked_locators = set()
    marker_pattern = re.compile(re.escape(marker_prefix) + r"[0-9]+⟧")
    seen = set()
    unbound = False
    for passage in projected:
        text = passage["text"]
        found = set(marker_pattern.findall(text))
        if not found:
            projected_originals.append(passage)
            continue
        if not found <= markers:
            raise ValueError("DOCX revision probe returned an unknown marker")
        seen.update(found)
        original_text = marker_pattern.sub("", text).strip()
        if original_text:
            projected_originals.append({**passage, "text": original_text})
            marked_locators.add(passage["locator"])
        else:
            unbound = True
    # The probe must preserve each locator and its exact text in original order.
    if projected_originals != expected or len({p["locator"] for p in expected}) != len(expected):
        raise ValueError("DOCX revision probe could not bind exact original passages")
    return marked_locators, unbound or markers != seen


def _with_warnings(result, additions):
    warnings = list(dict.fromkeys([*result["warnings"], *additions]))
    if warnings == result["warnings"]:
        return result
    output = {**result, "warnings": warnings}
    if (len(warnings) > 1_000 or sum(map(len, warnings)) > 100_000
            or len(json.dumps(output, ensure_ascii=False).encode("utf-8")) >= MAX_RESPONSE_BYTES):
        raise ValueError("DOCX revision warnings exceed extraction response budget")
    return output


def _inspection_unknown(result):
    try:
        return _with_warnings(result, [UNKNOWN_WARNING])
    except ValueError:
        return result


def _deadline_expired(*_):
    raise TimeoutError("DOCX revision inspection timed out")


def add_docx_revision_warnings(source, result):
    """Add annotations only; never select a Word revision or change a passage."""
    try:
        marker_prefix = "⟦DOCX-" + secrets.token_hex(16) + "-"
        if any(marker_prefix in p["text"] for p in result["passages"]):
            raise ValueError("DOCX revision probe marker is already present in source text")
        probe, markers, observed, unbound = _probe_package(source, marker_prefix)
        if not observed:
            return result
        additions = [DOCUMENT_WARNING]
        if probe is not None:
            locators, incomplete = _bind_probe(result, probe, marker_prefix, markers)
            unbound |= incomplete
            additions.extend(PASSAGE_WARNING.format(locator=p["locator"]) for p in result["passages"]
                             if p["locator"] in locators)
        if unbound:
            additions.append(UNBOUND_WARNING)
        return _with_warnings(result, additions)
    except Exception:
        # Optional annotation failure must never erase admitted baseline text.
        return _inspection_unknown(result)


def main():
    if len(sys.argv) != 3 or sys.argv[2] != ".docx":
        return 1
    started = time.monotonic()
    resource.setrlimit(resource.RLIMIT_CPU, (50, 50))
    resource.setrlimit(resource.RLIMIT_FSIZE, (10 * 1024 * 1024, 10 * 1024 * 1024))
    try:
        source = Path(sys.argv[1])
        result = extract(source, ".docx")
        if time.process_time() < 45 and time.monotonic() - started < 54:
            signal.signal(signal.SIGALRM, _deadline_expired)
            signal.setitimer(signal.ITIMER_REAL, _PROBE_SECONDS)
            try:
                result = add_docx_revision_warnings(source, result)
            except TimeoutError:
                result = _inspection_unknown(result)
            finally:
                signal.setitimer(signal.ITIMER_REAL, 0)
        else:
            result = _inspection_unknown(result)
        print(json.dumps(result, ensure_ascii=False))
    except Exception:
        # The isolated API receives only the controlled extraction failure.
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
