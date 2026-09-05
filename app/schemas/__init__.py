"""Schemas package initialization."""
from app.schemas.common import DocumentType, DocumentStatus, DocumentResponse, DocumentSearchResult
from app.schemas.invoice import InvoiceData
from app.schemas.resume import ResumeData, EducationItem, ExperienceItem
from app.schemas.registry import DOCUMENT_REGISTRY, get_schema_for_type, register_document_type

__all__ = [
    "DocumentType",
    "DocumentStatus",
    "DocumentResponse",
    "DocumentSearchResult",
    "InvoiceData",
    "ResumeData",
    "EducationItem",
    "ExperienceItem",
    "DOCUMENT_REGISTRY",
    "get_schema_for_type",
    "register_document_type",
]
