"""Stage 7: Persist document metadata, raw cleaned text, and extracted structured fields."""
import logging
import uuid
from typing import Any, Dict, Optional
from sqlalchemy.orm import Session

from app.db.models import DocumentModel
from app.schemas.common import DocumentStatus, DocumentType

logger = logging.getLogger(__name__)


def persist_document(
    db: Session,
    filename: str,
    file_type: str,
    doc_type: DocumentType,
    status: DocumentStatus,
    raw_text: Optional[str] = None,
    structured_data: Optional[Dict[str, Any]] = None,
    processing_meta: Optional[Dict[str, Any]] = None,
    error_message: Optional[str] = None,
    doc_id: Optional[str] = None,
) -> DocumentModel:
    """Store document record into the database."""
    document_id = doc_id or str(uuid.uuid4())

    doc_record = DocumentModel(
        id=document_id,
        filename=filename,
        file_type=file_type,
        doc_type=doc_type.value,
        status=status.value,
        raw_text=raw_text,
        structured_data=structured_data,
        processing_meta=processing_meta or {},
        error_message=error_message,
    )

    db.add(doc_record)
    db.commit()
    db.refresh(doc_record)
    logger.info("Persisted document %s (type=%s, status=%s)", document_id, doc_type.value, status.value)
    return doc_record
