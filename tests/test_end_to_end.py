import io
import docx
import pytest


def test_upload_invoice_pdf_and_retrieve(client, fixtures_path):
    """Test full pipeline: POST invoice PDF -> GET /documents/{id} -> assert schema fields."""
    invoice_path = fixtures_path / "sample_invoice.pdf"
    with open(invoice_path, "rb") as f:
        response = client.post(
            "/documents",
            files={"file": ("sample_invoice.pdf", f, "application/pdf")}
        )

    assert response.status_code == 201, response.text
    data = response.json()

    # Verify root fields
    doc_id = data["id"]
    assert doc_id is not None
    assert data["filename"] == "sample_invoice.pdf"
    assert data["file_type"] == "application/pdf"
    assert data["doc_type"] == "invoice"
    assert data["status"] == "processed"
    assert "Acme Solutions" in data["raw_text"]

    # Verify structured fields against Invoice schema
    structured = data["structured_data"]
    assert structured is not None
    assert "company_name" in structured
    assert structured["invoice_number"] == "INV-2024-8842"
    assert structured["amount"] == 4500.00
    assert structured["date"] == "2024-03-15"
    assert structured["currency"] == "USD"

    # Verify GET /documents/{id}
    get_resp = client.get(f"/documents/{doc_id}")
    assert get_resp.status_code == 200
    get_data = get_resp.json()
    assert get_data["id"] == doc_id
    assert get_data["structured_data"]["invoice_number"] == "INV-2024-8842"


def test_upload_resume_pdf_and_retrieve(client, fixtures_path):
    """Test full pipeline: POST resume PDF -> GET /documents/{id} -> assert schema fields."""
    resume_path = fixtures_path / "sample_resume.pdf"
    with open(resume_path, "rb") as f:
        response = client.post(
            "/documents",
            files={"file": ("sample_resume.pdf", f, "application/pdf")}
        )

    assert response.status_code == 201, response.text
    data = response.json()

    doc_id = data["id"]
    assert data["filename"] == "sample_resume.pdf"
    assert data["doc_type"] == "resume"
    assert data["status"] == "processed"

    # Verify structured fields against Resume schema
    structured = data["structured_data"]
    assert structured is not None
    assert "Alex Mercer" in structured["name"]
    assert "alex.mercer@devmail.com" in structured["email"]

    # Verify skills list
    skills = structured["skills"]
    assert isinstance(skills, list)
    assert any("Python" in s for s in skills)
    assert any("FastAPI" in s for s in skills)
    assert any("Flask" in s for s in skills)

    # Verify education and experience lists
    assert len(structured["education"]) >= 1
    assert len(structured["experience"]) >= 1


def test_upload_docx_files(client, fixtures_path):
    """Test DOCX ingestion for both resume and invoice."""
    # 1. Invoice DOCX
    with open(fixtures_path / "sample_invoice.docx", "rb") as f:
        inv_resp = client.post(
            "/documents",
            files={"file": ("sample_invoice.docx", f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
        )
    assert inv_resp.status_code == 201
    assert inv_resp.json()["doc_type"] == "invoice"

    # 2. Resume DOCX
    with open(fixtures_path / "sample_resume.docx", "rb") as f:
        res_resp = client.post(
            "/documents",
            files={"file": ("sample_resume.docx", f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
        )
    assert res_resp.status_code == 201
    assert res_resp.json()["doc_type"] == "resume"


def test_search_candidates_by_skills(client, fixtures_path):
    """Test candidate querying e.g. 'find candidates who know Python and Flask'."""
    # Ingest resume
    with open(fixtures_path / "sample_resume.pdf", "rb") as f:
        client.post("/documents", files={"file": ("sample_resume.pdf", f, "application/pdf")})

    # Search for Python and Flask
    resp = client.get("/documents/search", params={"doc_type": "resume", "skill": "Python,Flask"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    matched = data["results"][0]
    assert matched["doc_type"] == "resume"
    assert "Alex Mercer" in matched["structured_data"]["name"]

    # Search for a non-existent skill
    empty_resp = client.get("/documents/search", params={"doc_type": "resume", "skill": "Cobol,Fortran"})
    assert empty_resp.status_code == 200
    assert empty_resp.json()["total"] == 0


def test_search_invoices_by_amount_and_date(client, fixtures_path):
    """Test invoice querying by date range and amount."""
    with open(fixtures_path / "sample_invoice.pdf", "rb") as f:
        client.post("/documents", files={"file": ("sample_invoice.pdf", f, "application/pdf")})

    # Query matching amount range ($4000 - $5000)
    resp = client.get(
        "/documents/search",
        params={"doc_type": "invoice", "min_amount": 4000.0, "max_amount": 5000.0}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert data["results"][0]["structured_data"]["amount"] == 4500.00

    # Query matching date range (2024-01-01 to 2024-03-31)
    date_resp = client.get(
        "/documents/search",
        params={"doc_type": "invoice", "date_from": "2024-01-01", "date_to": "2024-03-31"}
    )
    assert date_resp.status_code == 200
    assert date_resp.json()["total"] >= 1

    # Query non-matching amount range ($100 - $500)
    no_match_resp = client.get(
        "/documents/search",
        params={"doc_type": "invoice", "min_amount": 100.0, "max_amount": 500.0}
    )
    assert no_match_resp.status_code == 200
    assert no_match_resp.json()["total"] == 0


def test_reject_unsupported_file_upload(client):
    """Test rejection of unsupported file types."""
    response = client.post(
        "/documents",
        files={"file": ("bad.exe", b"MZ\x90\x00corrupt executable", "application/octet-stream")}
    )
    assert response.status_code == 400
    assert "Unsupported or unrecognized file format" in response.json()["detail"]


def test_get_nonexistent_document(client):
    """Test 404 for invalid document ID."""
    response = client.get("/documents/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


def test_upload_image_file(client, fixtures_path):
    """Test image upload through the pipeline."""
    with open(fixtures_path / "sample_invoice.png", "rb") as f:
        resp = client.post(
            "/documents",
            files={"file": ("sample_invoice.png", f, "image/png")}
        )
    assert resp.status_code == 201
    data = resp.json()
    assert data["filename"] == "sample_invoice.png"
    assert data["file_type"] == "image/png"
    assert data["status"] in ("processed", "failed")


def test_upload_invoice_with_alternative_labels_and_search(client, fixtures_path):
    """Test invoice with alternative labels (Ref No, DD-Mon-YYYY, Grand Total) through full pipeline and search."""
    pdf_path = fixtures_path / "sample_invoice_variant.pdf"
    with open(pdf_path, "rb") as f:
        resp = client.post(
            "/documents",
            files={"file": ("sample_invoice_variant.pdf", f, "application/pdf")}
        )

    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["doc_type"] == "invoice"
    assert data["status"] == "processed"

    # Confirm extracted values are real values, not hardcoded defaults
    structured = data["structured_data"]
    assert structured["invoice_number"] == "NM-77821"
    assert structured["date"] == "2026-09-02"
    assert structured["amount"] == 12340.50
    assert structured["company_name"] == "Northwind Traders"
    assert structured["customer_name"] == "Contoso Ltd"
    assert structured["currency"] == "USD"

    # Confirm provider and model are explicitly surfaced in metadata
    meta = data["processing_meta"]
    assert "extraction" in meta
    assert "openai" in meta["extraction"]["llm_provider"]
    assert meta["extraction"]["llm_model"] == "gpt-4o-mini"
    assert meta["extraction"]["fallback_used"] is True

    # Confirm searchable by amount ($10,000 - $15,000)
    search_amt = client.get(
        "/documents/search",
        params={"doc_type": "invoice", "min_amount": 10000.0, "max_amount": 15000.0}
    )
    assert search_amt.status_code == 200
    assert search_amt.json()["total"] >= 1
    assert any(doc["structured_data"]["invoice_number"] == "NM-77821" for doc in search_amt.json()["results"])

    # Confirm searchable by company and date range
    search_date = client.get(
        "/documents/search",
        params={
            "doc_type": "invoice",
            "company_name": "Northwind",
            "date_from": "2026-01-01",
            "date_to": "2026-12-31",
        }
    )
    assert search_date.status_code == 200
    assert search_date.json()["total"] >= 1
    assert search_date.json()["results"][0]["structured_data"]["invoice_number"] == "NM-77821"


def test_upload_with_live_llm_primary_path(client, fixtures_path, monkeypatch):
    """Verify that when an LLM API key is configured, the primary real LLM path is called directly."""
    import json
    import httpx
    from unittest.mock import patch, MagicMock
    from app.config import settings

    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-live-test-key")
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")

    live_llm_json = {
        "company_name": "Northwind Traders Inc",
        "invoice_number": "NM-77821-LLM",
        "date": "2026-09-02",
        "customer_name": "Contoso Global Ltd",
        "amount": 12340.50,
        "currency": "USD"
    }

    with patch("app.llm.client.OpenAILLMClient._call_api", return_value=json.dumps(live_llm_json)):
        with open(fixtures_path / "sample_invoice_variant.pdf", "rb") as f:
            resp = client.post(
                "/documents",
                files={"file": ("sample_invoice_variant.pdf", f, "application/pdf")}
            )

    assert resp.status_code == 201
    data = resp.json()

    # Confirms live LLM extraction was used directly
    assert data["structured_data"]["invoice_number"] == "NM-77821-LLM"
    assert data["structured_data"]["company_name"] == "Northwind Traders Inc"

    # Confirms primary provider metadata with NO fallback
    meta = data["processing_meta"]["extraction"]
    assert meta["llm_provider"] == "openai"
    assert meta["llm_model"] == "gpt-4o-mini"
    assert meta["fallback_used"] is False
    assert meta["fallback_reason"] is None


def test_search_documents_with_summary_flag(client, fixtures_path):
    """Test search endpoint summary flag: summary=true returns clean business fields without raw_text or processing_meta."""
    # Ingest sample invoice
    with open(fixtures_path / "sample_invoice.pdf", "rb") as f:
        upload_resp = client.post(
            "/documents",
            files={"file": ("sample_invoice.pdf", f, "application/pdf")}
        )
    assert upload_resp.status_code == 201

    # 1. Query with summary=true
    sum_resp = client.get("/documents/search", params={"doc_type": "invoice", "summary": True})
    assert sum_resp.status_code == 200
    sum_data = sum_resp.json()
    assert sum_data["total"] >= 1

    item = sum_data["results"][0]
    # Required summary fields MUST be present
    assert "id" in item
    assert "filename" in item
    assert "doc_type" in item
    assert "structured_data" in item
    assert item["doc_type"] == "invoice"

    # Verify structured business fields are intact
    bus_fields = item["structured_data"]
    assert "company_name" in bus_fields
    assert "invoice_number" in bus_fields
    assert "date" in bus_fields
    assert "customer_name" in bus_fields
    assert "amount" in bus_fields
    assert "currency" in bus_fields

    # Verbose clutter fields MUST NOT be present
    assert "raw_text" not in item
    assert "processing_meta" not in item
    assert "file_type" not in item
    assert "status" not in item

    # 2. Query with summary=false (default full object)
    full_resp = client.get("/documents/search", params={"doc_type": "invoice", "summary": False})
    assert full_resp.status_code == 200
    full_item = full_resp.json()["results"][0]
    assert "raw_text" in full_item
    assert "processing_meta" in full_item
    assert "file_type" in full_item
    assert "status" in full_item


def test_serve_frontend_dashboard(client):
    """Verify GET / and GET /ui return 200 OK with HTML dashboard content."""
    for path in ("/", "/ui"):
        resp = client.get(path)
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "Document Intelligence Dashboard" in resp.text
        assert "uploadForm" in resp.text
        assert "docTypeFilter" in resp.text
        assert "/documents/search?summary=true" in resp.text
        assert "deleteDocument" in resp.text
        assert "Are you sure you want to delete this document?" in resp.text


def _create_docx_bytes(text: str) -> bytes:
    """Helper to generate an in-memory DOCX file from multiline text."""
    doc = docx.Document()
    for line in text.strip().splitlines():
        doc.add_paragraph(line.strip())
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_e2e_billing_statement_upload_and_classify(client):
    """End-to-end test: Upload BILLING STATEMENT with Statement # and Amount Payable, verify classified as invoice."""
    content = """
    BILLING STATEMENT
    Apex Cloud Hosting Services
    Account Number: ACC-9920
    Statement #: STMT-5501
    Date: 2026-03-10
    Bill To: Acme Corp
    Amount Payable: $1,450.00
    Payment Due: 2026-03-31
    """
    file_bytes = _create_docx_bytes(content)
    resp = client.post(
        "/documents",
        files={"file": ("billing_stmt.docx", file_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["doc_type"] == "invoice"
    assert data["status"] == "processed"
    structured = data["structured_data"]
    assert structured["invoice_number"] == "STMT-5501"
    assert structured["amount"] == 1450.0
    assert "Acme Corp" in structured["customer_name"]


def test_e2e_commercial_invoice_consignee_and_eur(client):
    """End-to-end test: Commercial invoice with Consignee, Exporter, and EUR currency extracts all fields."""
    content = """
    COMMERCIAL INVOICE
    Shipper / Exporter: Atlas Cargo Logistics BV
    Consignee: Euro Trade GmbH
    Ref No: CI-2026-0045
    Date: 14-Jan-2026
    Amount Payable: 45,250.00 EUR
    Currency: EUR
    """
    file_bytes = _create_docx_bytes(content)
    resp = client.post(
        "/documents",
        files={"file": ("commercial_invoice.docx", file_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["doc_type"] == "invoice"
    assert data["status"] == "processed"
    structured = data["structured_data"]
    assert structured is not None
    assert "Atlas Cargo Logistics" in structured["company_name"]
    assert "Euro Trade GmbH" in structured["customer_name"]
    assert structured["invoice_number"] == "CI-2026-0045"
    assert structured["date"] == "2026-01-14"
    assert structured["amount"] == 45250.0
    assert structured["currency"] == "EUR"


def test_e2e_invoice_number_prevents_slash_invoice(client):
    """End-to-end test: Invoice with 'COMMERCIAL INVOICE / INVOICE' extracts real 'MPL-9081' not '/Invoice'."""
    content = """
    COMMERCIAL INVOICE / INVOICE
    Seller: Pacific Oceanics Ltd
    Buyer: MegaRetail Inc
    Invoice / Ref No: MPL-9081
    Date: 2026-02-18
    Total Amount: $14,500.00
    """
    file_bytes = _create_docx_bytes(content)
    resp = client.post(
        "/documents",
        files={"file": ("slash_header_invoice.docx", file_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    structured = data["structured_data"]
    assert structured["invoice_number"] == "MPL-9081"
    assert structured["invoice_number"] != "/Invoice"
    assert not structured["invoice_number"].startswith("/")


def test_e2e_whole_number_amount_jpy(client):
    """End-to-end test: Invoices with whole number amounts (890,000 JPY) extract correctly, not default 100."""
    content = """
    INVOICE
    Issuer: Tokyo Electronics Ltd
    Customer: Osaka Industrial Corp
    Invoice #: TYO-88219
    Date: 2026-05-12
    Amount Payable: ¥890,000
    Currency: JPY
    """
    file_bytes = _create_docx_bytes(content)
    resp = client.post(
        "/documents",
        files={"file": ("jpy_invoice.docx", file_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    structured = data["structured_data"]
    assert structured["amount"] == 890000.0
    assert structured["amount"] != 100.0
    assert structured["currency"] == "JPY"
    assert structured["invoice_number"] == "TYO-88219"


def test_e2e_commercial_invoice_real_pdf_upload(client, fixtures_path):
    """Regression test: Upload real PDF sample_invoice_6.pdf, assert Consignee and EUR extracted without blank fields."""
    with open(fixtures_path / "sample_invoice_6.pdf", "rb") as f:
        resp = client.post(
            "/documents",
            files={"file": ("sample_invoice_6.pdf", f, "application/pdf")}
        )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["status"] == "processed"
    assert data["doc_type"] == "invoice"
    structured = data["structured_data"]
    assert structured is not None
    assert structured["company_name"] == "Ironclad Freight & Logistics"
    assert structured["customer_name"] == "Baltic Trade Partners B.V."
    assert structured["invoice_number"] == "ICF-EU-5567"
    assert structured["date"] == "2026-06-12"
    assert structured["amount"] == 4890.0
    assert structured["currency"] == "EUR"


def test_e2e_invoice_number_real_pdf_upload(client, fixtures_path):
    """Regression test: Upload real PDF sample_invoice_7.pdf, assert invoice number is MPL-9081, not /Invoice."""
    with open(fixtures_path / "sample_invoice_7.pdf", "rb") as f:
        resp = client.post(
            "/documents",
            files={"file": ("sample_invoice_7.pdf", f, "application/pdf")}
        )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["status"] == "processed"
    structured = data["structured_data"]
    assert structured["invoice_number"] == "MPL-9081"
    assert structured["invoice_number"] != "/Invoice"
    assert structured["customer_name"] == "Riverside Patisserie Ltd."
    assert structured["amount"] == 1462.75
    assert structured["currency"] == "CAD"


def test_e2e_whole_number_amount_real_pdf_upload(client, fixtures_path):
    """Regression test: Upload real PDF sample_invoice_4.pdf, assert amount is 890000.0 JPY, not 100.0."""
    with open(fixtures_path / "sample_invoice_4.pdf", "rb") as f:
        resp = client.post(
            "/documents",
            files={"file": ("sample_invoice_4.pdf", f, "application/pdf")}
        )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["status"] == "processed"
    structured = data["structured_data"]
    assert structured["amount"] == 890000.0
    assert structured["amount"] != 100.0
    assert structured["currency"] == "JPY"
    assert structured["customer_name"] == "Green Leaf Distributors Pte Ltd"
    assert structured["invoice_number"] == "KTI-2026-3390"


def test_e2e_billing_statement_real_pdf_upload(client, fixtures_path):
    """Regression test: Upload real PDF sample_invoice_3.pdf, assert classified as invoice with correct fields."""
    with open(fixtures_path / "sample_invoice_3.pdf", "rb") as f:
        resp = client.post(
            "/documents",
            files={"file": ("sample_invoice_3.pdf", f, "application/pdf")}
        )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["status"] == "processed"
    assert data["doc_type"] == "invoice"
    structured = data["structured_data"]
    assert structured["invoice_number"] == "SOL-88231"
    assert structured["amount"] == 3275.0
    assert structured["customer_name"] == "Meadowbrook Schools District"


def test_delete_document_and_verify_search_removal(client, fixtures_path):
    """Test deleting a document removes it from DB and search results, and returns 404 subsequently."""
    # 1. Upload a document
    pdf_path = fixtures_path / "sample_invoice.pdf"
    with open(pdf_path, "rb") as f:
        upload_resp = client.post(
            "/documents",
            files={"file": ("sample_invoice.pdf", f, "application/pdf")}
        )
    assert upload_resp.status_code == 201
    doc_id = upload_resp.json()["id"]

    # 2. Verify it exists via GET /documents/{id} and GET /documents/search
    get_resp = client.get(f"/documents/{doc_id}")
    assert get_resp.status_code == 200

    search_resp = client.get("/documents/search", params={"summary": "true"})
    assert search_resp.status_code == 200
    found_ids = [d["id"] for d in search_resp.json()["results"]]
    assert doc_id in found_ids

    # 3. Delete the document via DELETE /documents/{id}
    del_resp = client.delete(f"/documents/{doc_id}")
    assert del_resp.status_code == 200
    del_data = del_resp.json()
    assert del_data["status"] == "success"
    assert del_data["id"] == doc_id
    assert f"Document '{doc_id}' successfully deleted." in del_data["message"]

    # 4. Confirm document no longer exists (GET -> 404)
    get_after = client.get(f"/documents/{doc_id}")
    assert get_after.status_code == 404

    # 5. Confirm document no longer appears in search results
    search_after = client.get("/documents/search", params={"summary": "true"})
    assert search_after.status_code == 200
    found_after_ids = [d["id"] for d in search_after.json()["results"]]
    assert doc_id not in found_after_ids

    # 6. Attempting to delete again returns 404
    del_again = client.delete(f"/documents/{doc_id}")
    assert del_again.status_code == 404
    assert f"Document with ID '{doc_id}' not found." in del_again.json()["detail"]


def test_delete_nonexistent_document_returns_404(client):
    """Test DELETE /documents/{id} with nonexistent ID returns 404."""
    resp = client.delete("/documents/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
    assert "Document with ID '00000000-0000-0000-0000-000000000000' not found." in resp.json()["detail"]






