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


def test_classify_billing_statement_without_word_invoice():
    """Verify Bug 1 fix: Document titled BILLING STATEMENT with Statement # and Amount Payable is classified as INVOICE."""
    statement_text = """
    BILLING STATEMENT
    Account Number: ACC-88301
    Statement #: STMT-2026-901
    Date: 2026-03-01
    Bill To: Sarah Jenkins
    Amount Payable: $3,200.00
    Payment Due: 2026-03-25
    """
    result = classify_document_text(statement_text)
    assert result.doc_type == DocumentType.INVOICE
    assert result.source in ("heuristic", "llm")
    assert result.confidence >= 0.75


def test_extract_commercial_invoice_consignee_and_eur():
    """Verify Bug 2 fix: COMMERCIAL INVOICE with Consignee and EUR currency extracts correctly without blank fields."""
    comm_invoice_text = """
    COMMERCIAL INVOICE
    Shipper / Exporter: Atlas Cargo Logistics BV, Rotterdam
    Consignee: Euro Trade GmbH, Berlin
    Ref No: CI-2026-0045
    Date: 14-Jan-2026
    Description: Industrial machinery parts
    Amount: 45,250.00 EUR
    Currency: EUR
    """
    mock_llm = MockLLMClient()
    result = extract_structured_fields(comm_invoice_text, DocumentType.INVOICE, mock_llm)
    assert result.is_valid is True
    data = result.structured_data
    assert data is not None
    assert "Atlas Cargo Logistics" in data["company_name"]
    assert "Euro Trade GmbH" in data["customer_name"]
    assert data["invoice_number"] == "CI-2026-0045"
    assert data["date"] == "2026-01-14"
    assert data["amount"] == 45250.00
    assert data["currency"] == "EUR"


def test_extract_invoice_number_prevents_slash_invoice_garbage():
    """Verify Bug 3 fix: Header with slash ('COMMERCIAL INVOICE / INVOICE') does not extract as '/Invoice' instead of real number."""
    text_with_slash_header = """
    COMMERCIAL INVOICE / INVOICE
    Seller: Pacific Oceanics Ltd
    Buyer: MegaRetail Inc
    Invoice / Ref No: MPL-9081
    Date: 2026-02-18
    Total Amount: $14,500.00
    """
    mock_llm = MockLLMClient()
    result = extract_structured_fields(text_with_slash_header, DocumentType.INVOICE, mock_llm)
    assert result.is_valid is True
    data = result.structured_data
    assert data["invoice_number"] == "MPL-9081"
    assert data["invoice_number"] != "/Invoice"
    assert not data["invoice_number"].startswith("/")


def test_extract_whole_number_amount_jpy():
    """Verify Bug 4 fix: Invoices with whole number amounts and comma separators (e.g. 890,000 JPY) extract correctly."""
    jpy_invoice_text = """
    INVOICE
    Issuer: Tokyo Electronics Ltd
    Customer: Osaka Industrial Corp
    Invoice #: TYO-88219
    Date: 2026-05-12
    Amount Payable: ¥890,000
    Currency: JPY
    """
    mock_llm = MockLLMClient()
    result = extract_structured_fields(jpy_invoice_text, DocumentType.INVOICE, mock_llm)
    assert result.is_valid is True
    data = result.structured_data
    assert data["amount"] == 890000.0
    assert data["amount"] != 100.0
    assert data["currency"] == "JPY"
    assert data["invoice_number"] == "TYO-88219"


def test_pdf_pipeline_stages_sample_invoice_6(fixtures_path):
    """Verify PDF text-extraction path for sample_invoice_6.pdf (Commercial invoice with Consignee and EUR)."""
    pdf_bytes = (fixtures_path / "sample_invoice_6.pdf").read_bytes()
    text = extract_text_from_file(pdf_bytes, "application/pdf")
    cleaned = clean_extracted_text(text)

    # Classify
    classification = classify_document_text(cleaned)
    assert classification.doc_type == DocumentType.INVOICE

    # Extract fields
    result = extract_structured_fields(cleaned, classification.doc_type, MockLLMClient())
    assert result.is_valid is True
    assert result.structured_data["company_name"] == "Ironclad Freight & Logistics"
    assert result.structured_data["customer_name"] == "Baltic Trade Partners B.V."
    assert result.structured_data["invoice_number"] == "ICF-EU-5567"
    assert result.structured_data["date"] == "2026-06-12"
    assert result.structured_data["amount"] == 4890.0
    assert result.structured_data["currency"] == "EUR"


def test_pdf_pipeline_stages_sample_invoice_7(fixtures_path):
    """Verify PDF text-extraction path for sample_invoice_7.pdf (MPL-9081 and avoid /Invoice garbage)."""
    pdf_bytes = (fixtures_path / "sample_invoice_7.pdf").read_bytes()
    text = extract_text_from_file(pdf_bytes, "application/pdf")
    cleaned = clean_extracted_text(text)

    result = extract_structured_fields(cleaned, DocumentType.INVOICE, MockLLMClient())
    assert result.is_valid is True
    assert result.structured_data["invoice_number"] == "MPL-9081"
    assert result.structured_data["invoice_number"] != "/Invoice"
    assert result.structured_data["customer_name"] == "Riverside Patisserie Ltd."
    assert result.structured_data["amount"] == 1462.75
    assert result.structured_data["currency"] == "CAD"


def test_pdf_pipeline_stages_sample_invoice_4(fixtures_path):
    """Verify PDF text-extraction path for sample_invoice_4.pdf (890,000 JPY whole number amount)."""
    pdf_bytes = (fixtures_path / "sample_invoice_4.pdf").read_bytes()
    text = extract_text_from_file(pdf_bytes, "application/pdf")
    cleaned = clean_extracted_text(text)

    result = extract_structured_fields(cleaned, DocumentType.INVOICE, MockLLMClient())
    assert result.is_valid is True
    assert result.structured_data["amount"] == 890000.0
    assert result.structured_data["amount"] != 100.0
    assert result.structured_data["currency"] == "JPY"
    assert result.structured_data["customer_name"] == "Green Leaf Distributors Pte Ltd"
    assert result.structured_data["invoice_number"] == "KTI-2026-3390"



