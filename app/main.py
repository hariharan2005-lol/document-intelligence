"""FastAPI Main Application and API Route Handlers."""
import logging
from contextlib import asynccontextmanager
from typing import List, Optional
from fastapi import FastAPI, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import DocumentModel
from app.db.session import get_db, init_db
from app.pipeline.runner import run_pipeline
from app.pipeline.validate import DocumentValidationError
from app.schemas.common import DocumentResponse, DocumentSummaryResponse, DocumentSearchResult, DocumentDeleteResponse, DocumentType
from app.ui import HTML_CONTENT

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ensure database tables are initialized on startup."""
    init_db()
    yield


# Initialize FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    description="Full Document Ingestion + Intelligence Pipeline (Upload, Validate, Classify, Extract, Clean, Store, Search)",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["System"])
def health_check():
    """Service health and configuration check."""
    return {
        "status": "healthy",
        "app_name": settings.APP_NAME,
        "llm_provider": settings.LLM_PROVIDER,
        "max_upload_size_mb": settings.MAX_UPLOAD_SIZE_BYTES / (1024 * 1024),
    }


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
@app.get("/ui", response_class=HTMLResponse, tags=["Frontend"], summary="Document Intelligence Web Dashboard")
def serve_dashboard():
    """Serve single-page HTML dashboard for uploading, filtering, and viewing documents."""
    return HTMLResponse(content=HTML_CONTENT)


@app.post(
    "/documents",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Documents"],
    summary="Upload and ingest a document",
)
async def upload_document(
    file: UploadFile = File(..., description="Document file (PDF, DOCX, PNG, JPG)"),
    db: Session = Depends(get_db),
):
    """
    Ingest a document through the 7-stage intelligence pipeline:
    1. Upload & size guard
    2. Format & integrity validation (magic bytes)
    3. Text extraction (native or OCR)
    4. Text cleaning & normalization
    5. Classification (heuristic with LLM fallback)
    6. Structured field extraction with schema validation & 1x retry
    7. Storage in SQLite database
    """
    try:
        content = await file.read()
        pipeline_result = run_pipeline(
            filename=file.filename or "uploaded_file",
            file_bytes=content,
            db=db,
        )
        return pipeline_result.document
    except DocumentValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    except Exception as exc:
        logger.exception("Unexpected error processing document: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal document pipeline error: {str(exc)}",
        )


@app.get(
    "/documents/search",
    response_model=DocumentSearchResult,
    tags=["Documents"],
    summary="Search documents with structured and keyword filters",
)
def search_documents(
    doc_type: Optional[DocumentType] = Query(None, description="Filter by document type (invoice or resume)"),
    # Resume-specific filters
    skill: Optional[str] = Query(None, description="Comma-separated skills (e.g. 'Python,Flask')"),
    candidate_name: Optional[str] = Query(None, description="Filter by candidate full name substring"),
    # Invoice-specific filters
    company_name: Optional[str] = Query(None, description="Filter by invoice issuing company name"),
    customer_name: Optional[str] = Query(None, description="Filter by customer name"),
    date_from: Optional[str] = Query(None, description="Filter invoices on or after this ISO date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="Filter invoices on or before this ISO date (YYYY-MM-DD)"),
    min_amount: Optional[float] = Query(None, description="Minimum invoice total amount"),
    max_amount: Optional[float] = Query(None, description="Maximum invoice total amount"),
    currency: Optional[str] = Query(None, description="Invoice currency code (e.g. USD)"),
    # Output formatting
    summary: bool = Query(
        False,
        description="When true, return only id, filename, doc_type, and structured_data (skips raw_text and processing_meta)",
    ),
    # General text search
    query: Optional[str] = Query(None, description="Keyword search in cleaned raw document text"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """
    Execute structured queries across documents:
    - Find candidates matching one or more skills (e.g., 'find candidates who know Python and Flask')
    - Filter invoices by date ranges and amounts
    - Search across raw cleaned text
    - Optionally return summary view omitting raw text and processing metadata
    """
    db_query = db.query(DocumentModel)

    if doc_type:
        db_query = db_query.filter(DocumentModel.doc_type == doc_type.value)

    if query:
        db_query = db_query.filter(DocumentModel.raw_text.ilike(f"%{query}%"))

    # Fetch candidates matching base filters, then evaluate JSON structured field filters
    documents = db_query.order_by(DocumentModel.created_at.desc()).all()
    filtered: List[DocumentModel] = []

    for doc in documents:
        data = doc.structured_data or {}

        # 1. Resume filter checks
        if doc.doc_type == DocumentType.RESUME.value:
            if candidate_name and candidate_name.lower() not in str(data.get("name", "")).lower():
                continue

            if skill:
                req_skills = [s.strip().lower() for s in skill.split(",") if s.strip()]
                doc_skills = [s.lower() for s in data.get("skills", [])]
                # Check that all requested skills are present in the candidate's skills
                if not all(any(req in ds for ds in doc_skills) for req in req_skills):
                    continue

        # 2. Invoice filter checks
        if doc.doc_type == DocumentType.INVOICE.value:
            if company_name and company_name.lower() not in str(data.get("company_name", "")).lower():
                continue

            if customer_name and customer_name.lower() not in str(data.get("customer_name", "")).lower():
                continue

            if currency and currency.upper() != str(data.get("currency", "")).upper():
                continue

            inv_amount = data.get("amount")
            if min_amount is not None:
                if inv_amount is None or float(inv_amount) < min_amount:
                    continue
            if max_amount is not None:
                if inv_amount is None or float(inv_amount) > max_amount:
                    continue

            inv_date = str(data.get("date", ""))
            if date_from and inv_date and inv_date < date_from:
                continue
            if date_to and inv_date and inv_date > date_to:
                continue

        filtered.append(doc)

    total = len(filtered)
    paginated = filtered[offset : offset + limit]

    if summary:
        results = [DocumentSummaryResponse.model_validate(doc) for doc in paginated]
    else:
        results = [DocumentResponse.model_validate(doc) for doc in paginated]

    return DocumentSearchResult(
        total=total,
        results=results
    )


@app.get(
    "/documents/{document_id}",
    response_model=DocumentResponse,
    tags=["Documents"],
    summary="Retrieve a document and its extracted structured data",
)
def get_document(document_id: str, db: Session = Depends(get_db)):
    """Retrieve full structured document representation by document ID."""
    doc = db.query(DocumentModel).filter(DocumentModel.id == document_id).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID '{document_id}' not found.",
        )
    return doc


@app.delete(
    "/documents/{document_id}",
    response_model=DocumentDeleteResponse,
    tags=["Documents"],
    summary="Delete a document by ID",
)
def delete_document(document_id: str, db: Session = Depends(get_db)):
    """Remove the specified document from the database and return confirmation (404 if not found)."""
    doc = db.query(DocumentModel).filter(DocumentModel.id == document_id).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID '{document_id}' not found.",
        )
    db.delete(doc)
    db.commit()
    return DocumentDeleteResponse(
        status="success",
        message=f"Document '{document_id}' successfully deleted.",
        id=document_id,
    )
