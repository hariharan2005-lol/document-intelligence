"""Stage 4: Extract text natively for PDF/DOCX or OCR for scanned/image documents."""
import io
import logging
from typing import Optional
from PIL import Image
import docx
import pypdf

from app.config import settings

logger = logging.getLogger(__name__)


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract native text from PDF document."""
    reader = pypdf.PdfReader(io.BytesIO(file_bytes))
    extracted_pages = []
    for idx, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        extracted_pages.append(text)
    return "\n".join(extracted_pages)


def extract_text_from_docx(file_bytes: bytes) -> str:
    """Extract paragraphs and tables from DOCX document."""
    doc = docx.Document(io.BytesIO(file_bytes))
    lines = []
    for p in doc.paragraphs:
        if p.text.strip():
            lines.append(p.text.strip())

    for table in doc.tables:
        for row in table.rows:
            row_data = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if row_data:
                lines.append(" | ".join(row_data))

    return "\n".join(lines)


def extract_text_from_image(file_bytes: bytes) -> str:
    """Extract text from scanned image using OCR (pytesseract or fallback)."""
    image = Image.open(io.BytesIO(file_bytes))
    
    # Try pytesseract if available
    try:
        import pytesseract
        if settings.TESSERACT_CMD:
            pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD
        text = pytesseract.image_to_string(image)
        if text.strip():
            return text
    except Exception as exc:
        logger.warning("Pytesseract OCR unavailable or failed: %s. Using fallback image metadata.", exc)

    # Graceful fallback: return informative placeholder or image metadata
    return f"[Scanned Image Document: {image.format} {image.size[0]}x{image.size[1]}]"


def extract_text_from_file(file_bytes: bytes, mime_type: str) -> str:
    """Extract text based on MIME type."""
    if mime_type == "application/pdf":
        return extract_text_from_pdf(file_bytes)
    elif mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        return extract_text_from_docx(file_bytes)
    elif mime_type in ("image/png", "image/jpeg"):
        return extract_text_from_image(file_bytes)
    else:
        raise ValueError(f"Cannot extract text from unsupported MIME type: {mime_type}")
