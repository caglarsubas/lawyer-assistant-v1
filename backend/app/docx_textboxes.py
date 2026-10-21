"""Conservative normalization of standalone Word text-box representations.

Only the in-memory extraction tree changes. This is not an Office renderer or a
general Markup Compatibility processor. Ambiguous alternatives fail closed.
"""

from hashlib import sha256

from docx.oxml.ns import qn

WPS = "http://schemas.microsoft.com/office/word/2010/wordprocessingShape"
VML = "urn:schemas-microsoft-com:vml"
MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"
BOX = qn("w:txbxContent")


def prepare_textboxes(root, visit):
    """Select equivalent alternatives once; return whether alternatives existed."""
    alternatives = False
    # Bound empty shapes and wrappers too, rather than only emitted passages.
    nodes = []
    for node in root.iter():
        visit()
        nodes.append(node)
        if node.tag == f"{{{WPS}}}linkedTxbx" or (
            node.tag in {f"{{{VML}}}shape", f"{{{VML}}}textbox"}
            and "mso-next-textbox" in node.get("style", "").casefold()
        ):
            raise ValueError("DOCX linked text boxes are unsupported")
        if node.tag == BOX and any(a.tag == BOX for a in node.iterancestors()):
            raise ValueError("DOCX nested text boxes are unsupported")
        if node.tag == BOX:
            # python-docx omits content controls/revisions and custom run
            # wrappers. Do not lose a condition while returning the rest of a
            # box as successful evidence, including inside physical cells.
            for paragraph in node.iter(qn("w:p")):
                visit()
                for ancestor in paragraph.iterancestors():
                    if ancestor is node:
                        break
                    if ancestor.tag not in {qn("w:tbl"), qn("w:tr"), qn("w:tc")}:
                        raise ValueError("DOCX text-box content is unsupported")
                for token in paragraph.iter(qn("w:t"), qn("w:delText"), qn("w:tab"),
                                            qn("w:br"), qn("w:cr"), qn("w:sym")):
                    visit()
                    run = token.getparent()
                    parent = run.getparent()
                    if token.tag in {qn("w:delText"), qn("w:sym")} or run.tag != qn("w:r") or not (
                        parent is paragraph or
                        (parent.tag == qn("w:hyperlink") and parent.getparent() is paragraph)
                    ):
                        raise ValueError("DOCX text-box content is unsupported")

    def signature(branch):
        boxes = list(branch.iter(BOX))
        if not boxes:
            raise ValueError("DOCX text-box alternatives are ambiguous")
        for node in branch.iter(qn("w:t"), qn("w:instrText"), qn("w:tab"), qn("w:br"),
                                qn("w:footnoteReference"), qn("w:endnoteReference")):
            visit()
            if not any(a.tag == BOX for a in node.iterancestors()):
                raise ValueError("DOCX text-box alternatives are ambiguous")
        digest = sha256()
        # Expanded names avoid prefix-only differences; all attributes, text,
        # tails and structural boundaries remain significant. No text dedup.
        for box in boxes:
            for node in box.iter():
                visit()
                value = node.text
                if node.tag not in {qn("w:t"), qn("w:instrText"), qn("w:delText")} and not (value or "").strip():
                    value = None
                digest.update(repr((node.tag, sorted(node.attrib.items()), value,
                                    (node.tail or "").strip(), len(node))).encode())
        return len(boxes), digest.digest()

    # Inner alternatives first, then compare the selected in-memory content.
    for node in reversed(nodes):
        if node.tag != f"{{{MC}}}AlternateContent" or not any(True for _ in node.iter(BOX)):
            continue
        alternatives = True
        choices, fallback = [], None
        for branch in node:
            visit()
            if branch.tag == f"{{{MC}}}Choice" and fallback is None:
                required = branch.get("Requires", "").split()
                if not required or any(prefix not in branch.nsmap for prefix in required):
                    raise ValueError("DOCX text-box alternatives are ambiguous")
                choices.append((branch, all(branch.nsmap[p] == WPS for p in required)))
            elif branch.tag == f"{{{MC}}}Fallback" and fallback is None and choices:
                fallback = branch
            else:
                raise ValueError("DOCX text-box alternatives are ambiguous")
        if not choices:
            raise ValueError("DOCX text-box alternatives are ambiguous")
        branches = [b for b, _ in choices] + ([fallback] if fallback is not None else [])
        signatures = [signature(b) for b in branches]
        if any(s != signatures[0] for s in signatures):
            raise ValueError("DOCX text-box alternatives disagree")
        selected = next((b for b, supported in choices if supported), fallback)
        if selected is None:
            raise ValueError("DOCX text-box alternatives are unsupported")
        parent = node.getparent()
        if parent is None:
            raise ValueError("DOCX text-box alternatives are ambiguous")
        index = parent.index(node)
        for child in list(selected):
            parent.insert(index, child)
            index += 1
        parent.remove(node)
    return alternatives


def validate_box_context(box, paragraph):
    allowed = {
        f"{{{WPS}}}txbx", f"{{{WPS}}}wsp", f"{{{VML}}}textbox",
        f"{{{VML}}}shape", f"{{{VML}}}group", qn("w:drawing"), qn("w:pict"),
        qn("w:r"), qn("w:hyperlink"), qn("wp:inline"), qn("wp:anchor"),
        qn("a:graphic"), qn("a:graphicData"),
    }
    if box.getparent().tag not in {f"{{{WPS}}}txbx", f"{{{VML}}}textbox"}:
        raise ValueError("DOCX text-box context is unsupported")
    for ancestor in box.iterancestors():
        if ancestor is paragraph:
            return
        if ancestor.tag not in allowed:
            break
    raise ValueError("DOCX text-box context is unsupported")
