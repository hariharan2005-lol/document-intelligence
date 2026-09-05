"""Unit tests for individual pipeline stages (Validate, Extract, Clean, Classify, Field Extraction)."""
import pytest
from app.config import settings
from app.llm.client import MockLLMClient
from app.pipeline.clean import clean_extracted_text, normalize_whitespace, strip_headers_footers
from app.pipeline.classify import classify_document_text
from app.pipeline.extract_fields import extract_structured_fields
from app.pipeline.extract_text import extract_text_from_file
from app.pipeline.validate import validate_upload, DocumentValidationError
from app.schemas.common import DocumentType


def test_validate_valid_pdf(fixtures_path):
    pdf_bytes = (fixtures_path / "sample_invoice.pdf").read_bytes()
    validated = validate_upload("sample_invoice.pdf", pdf_bytes)
    assert validated.mime_type == "application/pdf"
    assert validated.size_bytes > 0


def test_validate_valid_docx(fixtures_path):
    docx_bytes = (fixtures_path / "sample_resume.docx").read_bytes()
    validated = validate_upload("sample_resume.docx", docx_bytes)
    assert validated.mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert validated.size_bytes > 0


def test_validate_unsupported_file_type():
    with pytest.raises(DocumentValidationError) as exc:
        validate_upload("script.exe", b"MZ\x90\x00executable binary")
    assert "Unsupported or unrecognized file format" in str(exc.value.message)


def test_validate_corrupted_pdf():
    # PDF magic bytes but broken content
    corrupted = b"%PDF-1.4\ncorrupted content that cannot be parsed"
    with pytest.raises(DocumentValidationError) as exc:
        validate_upload("broken.pdf", corrupted)
    assert "Corrupted or unreadable file" in str(exc.value.message)


def test_validate_oversized_file(monkeypatch):
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE_BYTES", 100)
    with pytest.raises(DocumentValidationError) as exc:
        validate_upload("large.pdf", b"%PDF-" + b"0" * 200)
    assert "exceeds maximum allowed limit" in str(exc.value.message)
    assert exc.value.status_code == 413


def test_extract_text_pdf(fixtures_path):
    pdf_bytes = (fixtures_path / "sample_invoice.pdf").read_bytes()
    text = extract_text_from_file(pdf_bytes, "application/pdf")
    assert "Acme Solutions Corp" in text
    assert "INV-2024-8842" in text


def test_extract_text_docx(fixtures_path):
    docx_bytes = (fixtures_path / "sample_resume.docx").read_bytes()
    text = extract_text_from_file(
        docx_bytes,
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert "Sarah Connor" in text
    assert "Cyberdyne Systems" in text


def test_clean_text():
    dirty_text = """
    Acme Solutions Corp
    Page 1 of 1
    Confidential - All rights reserved.
    
    Total Amount Due:    $4500.00
    
    
    — Contact us at info@example.com —
    Page 2
    """
    cleaned = clean_extracted_text(dirty_text)
    
    # Assert headers and footers stripped
    assert "Page 1 of 1" not in cleaned
    assert "Page 2" not in cleaned
    
    # Assert whitespace normalized
    assert "Total Amount Due: $4500.00" in cleaned
    assert "  " not in cleaned
    assert "\n\n\n" not in cleaned


def test_classify_heuristic_invoice():
    invoice_text = "INVOICE\nInvoice Number: INV-001\nBill To: John Doe\nAmount Due: $500.00\nSubtotal: $500.00"
    result = classify_document_text(invoice_text)
    assert result.doc_type == DocumentType.INVOICE
    assert result.source == "heuristic"
    assert result.confidence >= 0.7


def test_classify_heuristic_resume():
    resume_text = "Alex Mercer\nWork Experience:\nSoftware Engineer at TechCorp\nEducation: B.S. Computer Science\nSkills: Python, FastAPI, Docker"
    result = classify_document_text(resume_text)
    assert result.doc_type == DocumentType.RESUME
    assert result.source == "heuristic"
    assert result.confidence >= 0.7


def test_classify_llm_fallback():
    ambiguous_text = "Weekly general meeting notes and discussion on project roadmap."
    mock_llm = MockLLMClient()
    result = classify_document_text(ambiguous_text, llm_client=mock_llm)
    assert result.doc_type == DocumentType.UNKNOWN


def test_extract_fields_invoice():
    text = "Acme Solutions Corp\nInvoice Number: INV-2024-100\nDate: 2024-03-01\nBill To: Wayne Enterprises\nTotal Amount Due: $1,250.00"
    mock_llm = MockLLMClient()
    result = extract_structured_fields(text, DocumentType.INVOICE, mock_llm)
    assert result.is_valid is True
    assert result.retries_used == 0
    assert result.structured_data["invoice_number"] == "INV-2024-100"
    assert result.structured_data["amount"] == 1250.00
    assert result.structured_data["currency"] == "USD"


def test_extract_fields_resume():
    text = "John Smith\njohn.smith@example.com\n555-0100\nSkills: Python, Flask, Docker, PostgreSQL\nEducation: B.S. Computer Science, Stanford University, 2021\nExperience: Software Engineer at Acme Corp, 2021 - Present"
    mock_llm = MockLLMClient()
    result = extract_structured_fields(text, DocumentType.RESUME, mock_llm)
    assert result.is_valid is True
    assert result.retries_used == 0
    assert result.structured_data["name"] == "John Smith"
    assert "Python" in result.structured_data["skills"]
    assert "Flask" in result.structured_data["skills"]


def test_extract_fields_retry_mechanism():
    """Verify that if the LLM output fails validation on attempt 1, it retries and succeeds on attempt 2."""
    text = "Acme Corp\nInvoice Number: INV-RETRY-01\nDate: 2024-05-10\nBill To: Stark Industries\nTotal: $750.00"
    # Mock client configured to fail on attempt 1, succeed on attempt 2
    mock_llm_with_retry = MockLLMClient(fail_first_attempt=True)
    result = extract_structured_fields(text, DocumentType.INVOICE, mock_llm_with_retry)
    assert result.is_valid is True
    assert result.retries_used == 1
    assert result.structured_data["invoice_number"] == "INV-RETRY-01"


def test_extract_fields_invoice_alternative_wording():
    """Verify extraction when labels differ from original fixtures (Ref No, DD-Mon-YYYY, Grand Total)."""
    text = """
    Northwind Traders
    456 Commerce Boulevard, Dock 12
    TAX INVOICE
    Ref No: NM-77821
    Date: 02-Sep-2026
    Bill To: Contoso Ltd
    Subtotal: 12,340.50
    Grand Total: 12,340.50 USD
    """
    mock_llm = MockLLMClient()
    result = extract_structured_fields(text, DocumentType.INVOICE, mock_llm)
    assert result.is_valid is True
    data = result.structured_data
    assert data["company_name"] == "Northwind Traders"
    assert data["customer_name"] == "Contoso Ltd"
    assert data["invoice_number"] == "NM-77821"
    assert data["date"] == "2026-09-02"
    assert data["amount"] == 12340.50
    assert data["currency"] == "USD"

