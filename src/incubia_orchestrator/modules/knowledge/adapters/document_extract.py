"""Text extraction adapters for Orbit permitted document MIME types."""
from __future__ import annotations

import csv
import io
import xml.etree.ElementTree as ET
import zipfile

from pypdf import PdfReader

from incubia_orchestrator.modules.knowledge.domain import DocumentExtractionError, DocumentRejectedError

MAX_DOCX_UNCOMPRESSED_BYTES = 25 * 1024 * 1024
MAX_PDF_PAGES = 250
MAX_EXTRACTED_CHARS = 500_000
_WORD_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _clean_text(text: str) -> str:
    cleaned = text.replace("\x00", "").lstrip("\ufeff")
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    return cleaned[:MAX_EXTRACTED_CHARS].strip()


def _decode_text(content: bytes) -> str:
    if not content:
        raise DocumentExtractionError("Text document is empty")
    try:
        raw = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raw = content.decode("latin-1", errors="replace")
    return _clean_text(raw)


def _extract_csv(content: bytes) -> str:
    text = _decode_text(content)
    reader = csv.reader(io.StringIO(text))
    lines = [" | ".join(cell.strip() for cell in row) for row in reader if any(cell.strip() for cell in row)]
    result = _clean_text("\n".join(lines))
    if not result:
        raise DocumentExtractionError("CSV document contains no readable rows")
    return result


def _extract_docx(content: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            total_uncompressed = sum(info.file_size for info in archive.infolist())
            if total_uncompressed > MAX_DOCX_UNCOMPRESSED_BYTES:
                raise DocumentExtractionError("DOCX uncompressed content exceeds limit")
            if "word/document.xml" not in archive.namelist():
                raise DocumentExtractionError("DOCX archive missing word/document.xml")
            xml_bytes = archive.read("word/document.xml")
    except DocumentExtractionError:
        raise
    except Exception as exc:
        raise DocumentExtractionError("Invalid DOCX archive") from exc

    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise DocumentExtractionError("Malformed DOCX XML payload") from exc

    paragraphs: list[str] = []
    for paragraph in root.iter(f"{_WORD_NS}p"):
        parts: list[str] = []
        for elem in paragraph.iter():
            if elem.tag == f"{_WORD_NS}t" and elem.text:
                parts.append(elem.text)
            elif elem.tag == f"{_WORD_NS}tab":
                parts.append("\t")
            elif elem.tag == f"{_WORD_NS}br":
                parts.append("\n")
        line = "".join(parts).strip()
        if line:
            paragraphs.append(line)

    result = _clean_text("\n\n".join(paragraphs))
    if not result:
        raise DocumentExtractionError("DOCX document contains no readable text")
    return result


def _extract_pdf(content: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(content), strict=False)
        if reader.is_encrypted and not reader.decrypt(""):
            raise DocumentExtractionError("Encrypted PDF documents cannot be indexed")
        if len(reader.pages) > MAX_PDF_PAGES:
            raise DocumentExtractionError("PDF exceeds maximum allowed page count")
        pages: list[str] = []
        total_chars = 0
        for page in reader.pages:
            extracted = (page.extract_text() or "").strip()
            if extracted:
                pages.append(extracted)
                total_chars += len(extracted)
                if total_chars >= MAX_EXTRACTED_CHARS:
                    break
    except DocumentExtractionError:
        raise
    except Exception as exc:
        raise DocumentExtractionError("Invalid or unreadable PDF document") from exc

    result = _clean_text("\n\n".join(pages))
    if not result:
        raise DocumentExtractionError("PDF document contains no extractable text")
    return result


class DocumentTextExtractor:
    """Extracts normalized plain text from TXT, Markdown, CSV, PDF, and DOCX files."""

    def extract_text(self, content: bytes, *, content_type: str) -> str:
        base_type = content_type.split(";", 1)[0].strip().lower()
        if base_type in {"text/plain", "text/markdown"}:
            result = _decode_text(content)
            if not result:
                raise DocumentExtractionError("Document contains no readable text")
            return result
        if base_type == "text/csv":
            return _extract_csv(content)
        if base_type == "application/pdf":
            return _extract_pdf(content)
        if base_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            return _extract_docx(content)
        raise DocumentRejectedError("Unsupported document contentType")

