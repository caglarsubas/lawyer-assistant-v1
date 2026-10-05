"""Local bounded extraction worker. Container network isolation is required in production."""

import csv
import io
import json
import resource
import subprocess
import sys
import tempfile
import zipfile
from email import policy
from email.parser import BytesParser
from html.parser import HTMLParser
from pathlib import Path

SUPPORTED_SUFFIXES = frozenset(
    {
        ".txt",
        ".md",
        ".csv",
        ".docx",
        ".xlsx",
        ".pdf",
        ".png",
        ".jpg",
        ".jpeg",
        ".tiff",
        ".tif",
        ".bmp",
        ".webp",
        ".gif",
        ".pptx",
        ".odt",
        ".ods",
        ".odp",
        ".html",
        ".htm",
        ".eml",
        ".rtf",
        ".xls",
        ".msg",
        ".doc",
    }
)
ZIP_SUFFIXES = frozenset({".docx", ".xlsx", ".pptx", ".odt", ".ods", ".odp"})
MAX_TEXT = 2_000_000


class PlainHTML(HTMLParser):
    """Extract text without a browser, resource fetches or executable markup."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.skipped = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "template", "iframe", "object", "svg"}:
            self.skipped += 1
        elif tag in {"p", "div", "br", "tr", "li", "h1", "h2", "h3"} and not self.skipped:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "template", "iframe", "object", "svg"}:
            self.skipped = max(0, self.skipped - 1)

    def handle_data(self, data):
        if not self.skipped:
            self.parts.append(data)


def html_text(value):
    parser = PlainHTML()
    parser.feed(value)
    return "".join(parser.parts)


def check_archive(path):
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        if len(members) > 5000 or sum(m.file_size for m in members) > 100 * 1024 * 1024:
            raise ValueError("Archive expansion limit exceeded")
        if len({m.filename for m in members}) != len(members):
            raise ValueError("Duplicate archive members")
        if any("vbaproject" in m.filename.casefold() or m.filename.startswith("Basic/") for m in members):
            raise ValueError("Macros are prohibited")


def extract(path, suffix):
    passages, warnings = [], []
    page_count = None
    text_size = 0
    if suffix in ZIP_SUFFIXES:
        check_archive(path)

    def add(locator, text):
        nonlocal text_size
        text_size += len(text)
        if text_size > MAX_TEXT or len(passages) >= 100000:
            raise ValueError("Extracted text limit exceeded")
        if text.strip():
            passages.append({"locator": locator, "text": text.strip()})

    if suffix in (".txt", ".md", ".csv"):
        text = path.read_text(encoding="utf-8-sig", errors="strict")
        if suffix == ".csv":
            for index, row in enumerate(csv.reader(io.StringIO(text)), 1):
                add(f"Satır {index}", " | ".join(row))
        else:
            for index, paragraph in enumerate(text.split("\n\n"), 1):
                add(f"Paragraf {index}", paragraph)
    elif suffix in (".docx", ".xlsx"):
        if suffix == ".docx":
            from docx import Document

            doc = Document(path)
            for index, paragraph in enumerate(doc.paragraphs, 1):
                add(f"Paragraf {index}", paragraph.text)
            for ti, table in enumerate(doc.tables, 1):
                for ri, row in enumerate(table.rows, 1):
                    add(f"Tablo {ti}, satır {ri}", " | ".join(c.text for c in row.cells))
            xml = doc.element.xml
            if "<w:ins" in xml or "<w:del" in xml:
                warnings.append("İzlenen değişiklikler var; kabul edilmiş sürüm doğrulanmadı.")
            warnings.append("Üstbilgi, altbilgi, dipnot ve metin kutusu tamlığı doğrulanmadı.")
        else:
            from openpyxl import load_workbook

            book = load_workbook(path, read_only=True, data_only=False, keep_links=False)
            count = 0
            for sheet in book:
                for row in sheet:
                    values = []
                    for cell in row:
                        if cell.value is not None:
                            count += 1
                            if count > 100000:
                                raise ValueError("Spreadsheet cell limit exceeded")
                            values.append(f"{cell.coordinate}: {cell.value}")
                            if cell.data_type == "f":
                                warnings.append(
                                    "Formüller çalıştırılmadı; değerler bağımsız doğrulama gerektirir."
                                )
                    if values:
                        add(f"{sheet.title}!{row[0].row}", " | ".join(values))
            book.close()
    elif suffix == ".pptx":
        from pptx import Presentation

        presentation = Presentation(path)
        if len(presentation.slides) > 500:
            raise ValueError("Slide limit exceeded")
        page_count = len(presentation.slides)
        for si, slide in enumerate(presentation.slides, 1):
            for index, shape in enumerate(slide.shapes, 1):
                if shape.has_text_frame:
                    add(f"Slayt {si}, şekil {index}", shape.text_frame.text)
                if shape.has_table:
                    for ri, row in enumerate(shape.table.rows, 1):
                        add(f"Slayt {si}, tablo {index}, satır {ri}", " | ".join(c.text for c in row.cells))
        warnings.append("Slayt notları, gruplar, grafikler, görseller ve gömülü nesneler işlenmedi.")
    elif suffix in {".odt", ".ods", ".odp"}:
        from defusedxml.ElementTree import fromstring

        with zipfile.ZipFile(path) as archive:
            root = fromstring(archive.read("content.xml"))
        text_ns = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
        table_ns = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"

        def odf_text(element):
            pieces = [element.text or ""]
            for child in element:
                if child.tag == text_ns + "s":
                    count = int(child.attrib.get(text_ns + "c", "1"))
                    if not 1 <= count <= 1000:
                        raise ValueError("OpenDocument space expansion limit exceeded")
                    pieces.append(" " * count)
                elif child.tag == text_ns + "tab":
                    pieces.append("\t")
                elif child.tag == text_ns + "line-break":
                    pieces.append("\n")
                else:
                    pieces.append(odf_text(child))
                pieces.append(child.tail or "")
            return "".join(pieces)

        index = 0
        for element in root.iter():
            if element.tag in {text_ns + "p", text_ns + "h"}:
                index += 1
                add(f"İçerik paragrafı {index}", odf_text(element))
            if any(
                key in element.attrib
                for key in (
                    table_ns + "number-rows-repeated",
                    table_ns + "number-columns-repeated",
                    table_ns + "formula",
                )
            ):
                warnings.append("Tekrarlanan hücreler çoğaltılmadı; formüller çalıştırılmadı.")
        warnings.append(
            "OpenDocument: paragraf sırası korunur; hücre adresleri, düzen, nesneler ve imza doğrulanmadı."
        )
    elif suffix in {".html", ".htm"}:
        add("HTML metni", html_text(path.read_text(encoding="utf-8-sig", errors="strict")))
        warnings.append(
            "HTML kaynak metni: CSS görünürlüğü ve okuma düzeni doğrulanmadı; kaynaklar indirilmedi."
        )
    elif suffix == ".eml":
        message = BytesParser(policy=policy.default).parsebytes(path.read_bytes())
        for header in ("Subject", "From", "To", "Date", "Message-ID"):
            if message[header]:
                add(f"E-posta {header}", str(message[header]))
        parts = list(message.walk())
        if len(parts) > 1000:
            raise ValueError("Email part limit exceeded")
        body = message.get_body(preferencelist=("plain", "html"))
        if body is not None:
            content = body.get_content()
            if isinstance(content, str):
                add(
                    "E-posta gövdesi",
                    html_text(content) if body.get_content_type() == "text/html" else content,
                )
        else:
            warnings.append("E-posta düz metin/HTML gövdesi bulunamadı; ileti gövdesi işlenmedi.")
        omitted = sum(
            1 for part in parts if part.get_content_disposition() == "attachment" or part.get_filename()
        )
        warnings.append(
            f"E-posta ekleri ayrı yüklenmelidir; {omitted} ek işlenmedi. Başlıkların özgünlüğü doğrulanmadı."
        )
    elif suffix == ".rtf":
        from striprtf.striprtf import rtf_to_text

        content = path.read_bytes()
        if not content.startswith(b"{\\rtf"):
            raise ValueError("Invalid RTF header")
        # RTF control sequences carry the codepage; raw bytes survive this reversible decode.
        add("RTF metni", rtf_to_text(content.decode("latin-1"), errors="strict"))
        warnings.append("RTF düzeni, alanlar ve gömülü nesneler doğrulanmadı; nesneler çalıştırılmadı.")
    elif suffix == ".xls":
        import xlrd

        book = xlrd.open_workbook(str(path), on_demand=True)
        count = 0
        try:
            for sheet in book.sheets():
                count += sheet.nrows * sheet.ncols
                if count > 100000:
                    raise ValueError("Spreadsheet cell limit exceeded")
                for ri in range(sheet.nrows):
                    values = [
                        f"Sütun {ci + 1}: {sheet.cell_value(ri, ci)}"
                        for ci in range(sheet.ncols)
                        if sheet.cell_value(ri, ci) != ""
                    ]
                    add(f"{sheet.name}!Satır {ri + 1}", " | ".join(values))
        finally:
            book.release_resources()
        warnings.append(
            "XLS: kaydedilmiş hücre değerleri; formüller, makrolar, grafikler ve nesneler işlenmedi."
        )
    elif suffix == ".msg":
        import olefile

        with olefile.OleFileIO(str(path)) as message:
            streams = message.listdir()
            if len(streams) > 5000 or sum(message.get_size(s) for s in streams) > 100 * 1024 * 1024:
                raise ValueError("MSG stream limit exceeded")
            fields = {
                "0037": "Konu",
                "0C1A": "Gönderen adı",
                "0C1F": "Gönderen adresi",
                "0E04": "Alıcı",
                "1000": "Gövde",
                "007D": "İleti başlıkları",
            }
            for key, label in fields.items():
                stream = f"__substg1.0_{key}001F"
                if message.exists(stream):
                    add(
                        f"MSG {label}",
                        message.openstream(stream).read().decode("utf-16-le", errors="strict").rstrip("\0"),
                    )
            if not message.exists("__substg1.0_1000001F"):
                warnings.append("MSG Unicode düz metin gövdesi yok; HTML/RTF/ANSI gövde işlenmedi.")
            attachment_names = {s[0] for s in streams if s[0].startswith("__attach")}
            warnings.append(
                f"MSG: {len(attachment_names)} ek işlenmedi; ekleri ayrı yükleyin. Başlıklar doğrulanmadı."
            )
    elif suffix == ".doc":
        if not path.read_bytes().startswith(bytes.fromhex("D0CF11E0A1B11AE1")):
            raise ValueError("Invalid legacy Word header")
        result = subprocess.run(
            ["antiword", "-m", "UTF-8.txt", str(path)], check=True, capture_output=True, timeout=20
        )
        add("Eski Word metni", result.stdout.decode("utf-8", errors="strict"))
        warnings.append("DOC: düz metin; düzen, değişiklikler, makrolar ve gömülü nesneler doğrulanmadı.")
    elif suffix == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(path)
        if reader.is_encrypted:
            raise ValueError("Encrypted PDF requires a decrypted working copy")
        if len(reader.pages) > 500:
            raise ValueError("PDF page limit exceeded")
        page_count = len(reader.pages)
        ocr_pages = 0
        for index, page in enumerate(reader.pages, 1):
            text = page.extract_text() or ""
            if not text.strip():
                if ocr_pages < 3:
                    ocr_pages += 1
                    try:
                        import pytesseract
                        from PIL import Image

                        with tempfile.TemporaryDirectory(prefix="pdf-page-") as directory:
                            prefix = str(Path(directory) / "page")
                            subprocess.run(
                                [
                                    "pdftoppm",
                                    "-f",
                                    str(index),
                                    "-l",
                                    str(index),
                                    "-singlefile",
                                    "-scale-to",
                                    "2000",
                                    "-png",
                                    str(path),
                                    prefix,
                                ],
                                check=True,
                                capture_output=True,
                                timeout=6,
                            )
                            with Image.open(prefix + ".png") as picture:
                                text = pytesseract.image_to_string(picture, lang="tur+eng", timeout=6)
                        warnings.append(f"Sayfa {index}: OCR kullanıldı; görüntüyle doğrulayın.")
                    except (OSError, RuntimeError, subprocess.SubprocessError):
                        warnings.append(f"Sayfa {index}: yerel OCR kullanılamadı.")
                if not text.strip():
                    warnings.append(f"Sayfa {index}: içerik işlenemedi; bu çalışmaya dahil edilmedi.")
            add(f"Sayfa {index}", text)
        warnings.append("PDF okuma sırası ve tablo düzeni insan incelemesi gerektirir.")
    elif suffix in (".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp", ".gif"):
        import pytesseract
        from PIL import Image

        Image.MAX_IMAGE_PIXELS = 30_000_000
        with Image.open(path) as picture:
            if picture.width * picture.height > Image.MAX_IMAGE_PIXELS:
                raise ValueError("Image pixel limit exceeded")
            picture.verify()
        with Image.open(path) as picture:
            page_count = getattr(picture, "n_frames", 1)
            if page_count > 1:
                warnings.append(
                    f"Çok sayfalı görsel: yalnızca ilk kare işlendi; {page_count - 1} kare dahil edilmedi."
                )
            text = pytesseract.image_to_string(picture, lang="tur+eng", timeout=40)
        add("Görsel OCR", text)
        warnings.append("OCR çıktısı kaynak görselle doğrulanmalıdır.")
    else:
        raise ValueError("Format is not qualified; preserve original and convert locally")
    if sum(len(p["text"]) for p in passages) > 2_000_000:
        raise ValueError("Extracted text limit exceeded")
    return {
        "passages": passages,
        "warnings": list(dict.fromkeys(warnings)),
        "page_count": page_count,
        "passage_count": len(passages),
    }


if __name__ == "__main__":
    resource.setrlimit(resource.RLIMIT_CPU, (50, 50))
    resource.setrlimit(resource.RLIMIT_FSIZE, (10 * 1024 * 1024, 10 * 1024 * 1024))
    try:
        result = extract(Path(sys.argv[1]), sys.argv[2])
        print(json.dumps(result, ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"error": type(exc).__name__, "message": str(exc)[:200]}))
        sys.exit(1)
