"""Pipeline orchestrator: executes stages 1 through 7 in sequential, modular steps."""
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional
from sqlalchemy.orm import Session

from app.db.models import DocumentModel
from app.llm.client import BaseLLMClient, get_llm_client
from app.pipeline.clean import clean_extracted_text
from app.pipeline.classify import classify_document_text
from app.pipeline.extract_fields import extract_structured_fields
from app.pipeline.extract_text import extract_text_from_file
from app.pipeline.store import persist_document
from app.pipeline.validate import validate_upload, DocumentValidationError
from app.schemas.common import DocumentStatus, DocumentType

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    document: DocumentModel
    success: bool
    stages_completed: list[str]


def run_pipeline(
    filename: str,
    file_bytes: bytes,
    db: Session,
    llm_client: Optional[BaseLLMClient] = None,
) -> PipelineResult:
    """Run full document ingestion and intelligence pipeline."""
    start_time = time.time()
    stages_completed = []
    client = llm_client or get_llm_client()

    # Stage 1 & 2: Validate
    validated = validate_upload(filename, file_bytes)
    stages_completed.append("validate")

    # Stage 4: Extract Text
    raw_extracted_text = extract_text_from_file(validated.file_bytes, validated.mime_type)
    stages_completed.append("extract_text")

    # Stage 5: Clean
    cleaned_text = clean_extracted_text(raw_extracted_text)
    stages_completed.append("clean")

    # Stage 3: Classify
    classification = classify_document_text(cleaned_text, client)
    stages_completed.append("classify")

    # Stage 6: Extract Structured Fields
    extraction = extract_structured_fields(cleaned_text, classification.doc_type, client)
    stages_completed.append("extract_fields")

    status = DocumentStatus.PROCESSED if extraction.is_valid else DocumentStatus.FAILED
    duration_ms = round((time.time() - start_time) * 1000, 2)

    processing_meta = {
        "file_size_bytes": validated.size_bytes,
        "processing_time_ms": duration_ms,
        "stages": stages_completed,
        "classification": {
            "source": classification.source,
            "confidence": classification.confidence,
            "reasoning": classification.reasoning,
        },
        "extraction": {
            "llm_provider": client.provider_name,
            "llm_model": client.model_name,
            "fallback_used": getattr(client, "last_fallback_used", False),
            "fallback_reason": getattr(client, "last_fallback_reason", None),
            "retries_used": extraction.retries_used,
            "is_valid": extraction.is_valid,
        },
    }

    # Stage 7: Store
    doc_record = persist_document(
        db=db,
        filename=validated.filename,
        file_type=validated.mime_type,
        doc_type=classification.doc_type,
        status=status,
        raw_text=cleaned_text,
        structured_data=extraction.structured_data,
        processing_meta=processing_meta,
        error_message=extraction.error_message,
    )
    stages_completed.append("store")

    return PipelineResult(
        document=doc_record,
        success=extraction.is_valid,
        stages_completed=stages_completed,
    )
