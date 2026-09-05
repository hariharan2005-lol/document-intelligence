"""Stage 1 & 2: Upload validation, size checks, magic byte MIME detection, integrity checks."""
import io
import zipfile
from dataclasses import dataclass
from typing import Optional, Tuple
from PIL import Image
import pypdf

from app.config import settings


class DocumentValidationError(Exception):
    """Raised when uploaded file fails validation or corruption checks."""
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass
class ValidatedFile:
    filename: str
    file_bytes: bytes
    mime_type: str
    size_bytes: int


def detect_mime_from_bytes(file_bytes: bytes) -> Optional[str]:
    """Inspect magic bytes to detect file MIME type reliably without relying on client headers."""
    if len(file_bytes) < 4:
        return None

    # PDF: %PDF- (0x25 0x50 0x44 0x46 0x2D)
    if file_bytes.startswith(b"%PDF-"):
        return "application/pdf"

    # PNG: \x89PNG\r\n\x1a\n
    if file_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"

    # JPEG: \xFF\xD8\xFF
    if file_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"

    # DOCX: Zip archive PK\x03\x04
    if file_bytes.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
                namelist = zf.namelist()
                if "word/document.xml" in namelist or "[Content_Types].xml" in namelist:
                    return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        except Exception:
            return None

    return None


def verify_file_integrity(file_bytes: bytes, mime_type: str) -> None:
    """Verify file integrity and ensure the file is not corrupted."""
    try:
        if mime_type == "application/pdf":
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            # Test reading number of pages
            if len(reader.pages) == 0:
                raise DocumentValidationError("Corrupted PDF: Document has no pages.")
        elif mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
                bad_file = zf.testzip()
                if bad_file:
                    raise DocumentValidationError(f"Corrupted DOCX archive: invalid file {bad_file}")
        elif mime_type in ("image/png", "image/jpeg"):
            with Image.open(io.BytesIO(file_bytes)) as img:
                img.verify()
        else:
            raise DocumentValidationError(f"Unsupported MIME type: {mime_type}")
    except DocumentValidationError:
        raise
    except Exception as exc:
        raise DocumentValidationError(f"Corrupted or unreadable file: {str(exc)}") from exc


def validate_upload(filename: str, file_bytes: bytes) -> ValidatedFile:
    """Execute Stage 1 & 2 validation on an incoming upload."""
    if not filename:
        raise DocumentValidationError("Missing filename.")

    size = len(file_bytes)
    if size == 0:
        raise DocumentValidationError("File is empty (0 bytes).")

    if size > settings.MAX_UPLOAD_SIZE_BYTES:
        max_mb = settings.MAX_UPLOAD_SIZE_BYTES / (1024 * 1024)
        raise DocumentValidationError(
            f"File size exceeds maximum allowed limit of {max_mb:.1f} MB.",
            status_code=413,
        )

    # Detect MIME type from file content
    detected_mime = detect_mime_from_bytes(file_bytes)
    if not detected_mime:
        raise DocumentValidationError(
            f"Unsupported or unrecognized file format. Allowed formats: PDF, DOCX, PNG, JPEG."
        )

    # Integrity verification
    verify_file_integrity(file_bytes, detected_mime)

    return ValidatedFile(
        filename=filename,
        file_bytes=file_bytes,
        mime_type=detected_mime,
        size_bytes=size,
    )
