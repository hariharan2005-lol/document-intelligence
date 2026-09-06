"""Generic document type registry for extensible schema management."""
from dataclasses import dataclass
from typing import Dict, List, Optional, Type
from pydantic import BaseModel

from app.schemas.common import DocumentType
from app.schemas.invoice import InvoiceData
from app.schemas.resume import ResumeData


@dataclass
class DocumentTypeConfig:
    doc_type: DocumentType
    schema_cls: Type[BaseModel]
    description: str
    heuristic_keywords: List[str]
    extraction_instructions: str


DOCUMENT_REGISTRY: Dict[DocumentType, DocumentTypeConfig] = {}


def register_document_type(
    doc_type: DocumentType,
    schema_cls: Type[BaseModel],
    description: str,
    heuristic_keywords: List[str],
    extraction_instructions: str,
) -> None:
    """Register a new document type with its associated schema and extraction rules."""
    DOCUMENT_REGISTRY[doc_type] = DocumentTypeConfig(
        doc_type=doc_type,
        schema_cls=schema_cls,
        description=description,
        heuristic_keywords=heuristic_keywords,
        extraction_instructions=extraction_instructions,
    )


def get_schema_for_type(doc_type: DocumentType) -> Optional[Type[BaseModel]]:
    """Retrieve Pydantic schema model for a given document type."""
    config = DOCUMENT_REGISTRY.get(doc_type)
    return config.schema_cls if config else None


# Pre-register built-in types
register_document_type(
    doc_type=DocumentType.INVOICE,
    schema_cls=InvoiceData,
    description="Invoices, billing statements, commercial invoices, tax receipts, payment requests",
    heuristic_keywords=[
        "invoice", "invoice number", "bill to", "due date", "subtotal",
        "total due", "amount due", "balance due", "vat", "tax invoice", "qty", "unit price",
        "billing statement", "statement", "statement #", "statement no", "statement number",
        "amount payable", "total payable", "net payable", "commercial invoice", "consignee",
        "payment due", "total amount"
    ],
    extraction_instructions=(
        "Extract invoice metadata including vendor/issuer/seller/exporter company name (company_name), "
        "unique invoice/statement/reference number (invoice_number), billing date in ISO format YYYY-MM-DD (date), "
        "customer/client/buyer/consignee name (customer_name), total numeric amount due (amount), and "
        "ISO currency code like USD, EUR, GBP, JPY (currency). For commercial invoices, map 'Consignee' or 'Buyer' "
        "to customer_name, and 'Shipper' or 'Exporter' to company_name. For billing statements, map 'Statement #' "
        "or 'Account' to invoice_number, and 'Amount Payable' to amount."
    ),
)


register_document_type(
    doc_type=DocumentType.RESUME,
    schema_cls=ResumeData,
    description="Resumes, CVs, curriculum vitae, candidate profiles, professional bios",
    heuristic_keywords=[
        "curriculum vitae", "resume", "experience", "work experience",
        "education", "skills", "employment history", "technologies", "bachelor", "master", "university", "projects"
    ],
    extraction_instructions="Extract candidate details: full name, email, phone number, list of skills, educational qualifications with degrees, and work history entries with roles and durations.",
)
