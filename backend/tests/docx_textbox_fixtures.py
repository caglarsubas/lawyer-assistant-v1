"""Invented DrawingML/VML text-box package content, never a client document."""

from copy import deepcopy

from docx.oxml import parse_xml

WPS = "http://schemas.microsoft.com/office/word/2010/wordprocessingShape"
MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def textbox(paragraph, blocks, kind="modern"):
    if kind == "modern":
        shape = parse_xml(f'''<w:drawing xmlns:w="{W}"
            xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
            xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:wps="{WPS}">
            <wp:anchor><a:graphic><a:graphicData uri="{WPS}"><wps:wsp><wps:txbx>
            <w:txbxContent/></wps:txbx></wps:wsp></a:graphicData></a:graphic></wp:anchor></w:drawing>''')
    else:
        shape = parse_xml(f'''<w:pict xmlns:w="{W}" xmlns:v="urn:schemas-microsoft-com:vml">
            <v:shape><v:textbox><w:txbxContent/></v:textbox></v:shape></w:pict>''')
    content = next(shape.iter(f"{{{W}}}txbxContent"))
    for block in blocks.element.body:
        if block.tag != f"{{{W}}}sectPr":
            content.append(deepcopy(block))
    paragraph.add_run()._r.append(shape)
    return shape, content


def alternate_textbox(paragraph, blocks, different=None, requires="wps"):
    modern, _ = textbox(paragraph, blocks)
    legacy, _ = textbox(paragraph, different if different is not None else blocks, "legacy")
    modern.getparent().remove(modern)
    legacy.getparent().remove(legacy)
    alternative = parse_xml(f'''<mc:AlternateContent xmlns:mc="{MC}" xmlns:wps="{WPS}"
        xmlns:other="urn:unsupported"><mc:Choice Requires="{requires}"/>
        <mc:Fallback/></mc:AlternateContent>''')
    alternative[0].append(modern)
    alternative[1].append(legacy)
    paragraph.add_run()._r.append(alternative)
    return alternative
