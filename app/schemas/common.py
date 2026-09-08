"""Common data types and API response schemas."""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, ConfigDict, Field


class DocumentType(str, Enum):
    INVOICE = "invoice"
    RESUME = "resume"
    UNKNOWN = "unknown"


class DocumentStatus(str, Enum):
    PROCESSED = "processed"
    FAILED = "failed"


class DocumentResponse(BaseModel):
    """Response payload for a single document."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    file_type: str
    doc_type: DocumentType
    status: DocumentStatus
    raw_text: Optional[str] = None
    structured_data: Optional[Dict[str, Any]] = None
    processing_meta: Optional[Dict[str, Any]] = None
    created_at: datetime
    error_message: Optional[str] = None


class DocumentSummaryResponse(BaseModel):
    """Summary representation of a document containing only essential business fields."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    doc_type: DocumentType
    structured_data: Optional[Dict[str, Any]] = None


class DocumentSearchResult(BaseModel):
    """Search query response list item."""
    total: int
    results: List[Union[DocumentSummaryResponse, DocumentResponse]]


class DocumentDeleteResponse(BaseModel):
    """Confirmation payload returned when a document is deleted."""
    status: str = "success"
    message: str
    id: str

