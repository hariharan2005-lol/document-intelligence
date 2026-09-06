# Document Ingestion + Intelligence Pipeline

A modular, production-ready document ingestion and intelligence pipeline built with **Python 3.13**, **FastAPI**, **SQLAlchemy**, and **Pydantic v2**.

Users can upload documents (PDF, DOCX, PNG, JPG), automatically validate and classify them (invoices vs. resumes), clean raw text, extract type-specific structured fields using an LLM with strict JSON schema enforcement and self-repair retry, persist them in SQLite, and perform structured searches.

---

## 1. Stack Choice & Rationale

| Component | Choice | Rationale |
| :--- | :--- | :--- |
| **Language & Web Framework** | **Python 3.13 + FastAPI** | Native async capabilities, automatic OpenAPI documentation (`/docs`), and unmatched ecosystem support for document extraction and AI/LLM integrations. |
| **Data Validation & Schemas** | **Pydantic v2** | Ultra-fast validation against JSON schemas, strict typing, and dynamic schema exports for LLM prompts. |
| **Database** | **SQLite + SQLAlchemy 2.0** | Zero-setup, single-file relational database with native JSON column support. Easy to swap to PostgreSQL via connection string. |
| **Parsers** | **`pypdf` + `python-docx` + `Pillow`** | High-performance pure Python and standard binary wheels without complex native C/C++ compilation steps on Windows. |
| **OCR** | **`pytesseract` with graceful fallback** | Supports local Tesseract OCR engine when available; provides graceful fallback if the binary is absent. |
| **LLM Provider** | **Live Primary (`openai`, `anthropic`, `gemini`) + Heuristic Fallback** | Executes live LLM calls (OpenAI GPT-4o-mini, Anthropic Claude 3.5 Sonnet) as the primary path with JSON schema enforcement. Transparently falls back to pattern heuristics if API key is not provided or upon connection failure. |

---

## 2. Pipeline Stages

The pipeline consists of 8 isolated, modular stages where each stage can be swapped independently:

1. **Upload (`POST /documents`)**: Accepts PDF, DOCX, PNG, and JPG files. Rejects unsupported formats and oversized files with HTTP 400 / 413.
2. **Validate (`pipeline/validate.py`)**: Validates magic bytes / file signatures (preventing extension spoofing), checks size limit, and verifies file integrity.
3. **Extract Text (`pipeline/extract_text.py`)**: Extracts text natively from PDF (`pypdf`) and DOCX (`python-docx`), and performs OCR for scanned images.
4. **Clean (`pipeline/clean.py`)**: Strips page numbers, headers/footers, and boilerplate; normalizes whitespace and Unicode characters (ligatures, stylized quotes).
5. **Classify (`pipeline/classify.py`)**: Uses high-speed keyword density heuristics first; falls back to an LLM classification call if ambiguous.
6. **Extract Fields (`pipeline/extract_fields.py`)**: Prompts the live LLM (OpenAI or Anthropic) with strict JSON output instructions and target schema. Validates against Pydantic model and performs **1 automatic retry** with error feedback on validation failure.
7. **Store (`pipeline/store.py`)**: Persists structured data, document metadata, processing metrics, and cleaned raw text in SQLite.
8. **Search/Retrieve (`GET /documents/search` & `GET /documents/{id}`)**: Exposes structured search endpoints to query candidates by skills, filter invoices by date range or monetary amount, and retrieve full document representations.

---

## 3. Schemas

### Invoice Schema (`InvoiceData`)
```json
{
  "company_name": "Acme Solutions Corp",
  "invoice_number": "INV-2024-8842",
  "date": "2024-03-15",
  "customer_name": "Globex International",
  "amount": 4500.00,
  "currency": "USD"
}
```

### Resume Schema (`ResumeData`)
```json
{
  "name": "Alex Mercer",
  "email": "alex.mercer@devmail.com",
  "phone": "(555) 234-5678",
  "skills": ["Python", "FastAPI", "Flask", "PostgreSQL", "Docker"],
  "education": [
    {
      "institution": "University of California, Berkeley",
      "degree": "Bachelor of Science in Computer Science",
      "year": 2018
    }
  ],
  "experience": [
    {
      "company": "DataCorp Solutions",
      "title": "Senior Backend Engineer",
      "duration": "2021 - Present"
    }
  ]
}
```

### Adding New Document Types
Adding a new document type (e.g., `receipt`, `contract`) requires no changes to the pipeline engine. Simply register the new type in `app/schemas/registry.py`:
```python
register_document_type(
    doc_type=DocumentType("contract"),
    schema_cls=ContractData,
    description="Legal contracts and agreements",
    heuristic_keywords=["agreement", "parties", "governing law"],
    extraction_instructions="Extract contracting parties, effective date, and governing jurisdiction."
)
```

---

## 4. Setup & Running Locally

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Configure your desired live LLM provider:
* **OpenAI**: Set `LLM_PROVIDER="openai"` and `OPENAI_API_KEY="sk-..."` (or point `OPENAI_BASE_URL` to a local Ollama instance at `http://localhost:11434/v1`).
* **Anthropic**: Set `LLM_PROVIDER="anthropic"` and `ANTHROPIC_API_KEY="sk-ant-..."`.
* **Heuristic / Offline Fallback**: If no API key is provided, the service runs the heuristic extractor with full logging and metadata indicating fallback.

### 3. Generate Test Fixtures
```bash
python fixtures/generate_fixtures.py
```

### 4. Run Automated Test Suite
```bash
pytest -v
```

### 5. Start the FastAPI Server
```bash
uvicorn app.main:app --reload --port 8000
```
* **Web UI Dashboard**: Visit **http://localhost:8000/** (or **http://localhost:8000/ui**) for the single-page document upload and review dashboard.
* **Interactive API Documentation**: Available at **http://localhost:8000/docs**.

---

## 5. API Usage Examples

### Upload a Document (`POST /documents`)
```bash
curl -X POST "http://localhost:8000/documents" \
  -F "file=@fixtures/sample_invoice.pdf"
```

### Retrieve a Document by ID (`GET /documents/{id}`)
```bash
curl -X GET "http://localhost:8000/documents/<DOCUMENT_UUID>"
```

### Search Resumes by Skills (`GET /documents/search`)
Find candidates who know Python and Flask:
```bash
curl -X GET "http://localhost:8000/documents/search?doc_type=resume&skill=Python,Flask"
```

### Search Invoices by Amount and Date Range (`GET /documents/search`)
Filter invoices between $1,000 and $5,000 billed in Q1 2024:
```bash
curl -X GET "http://localhost:8000/documents/search?doc_type=invoice&min_amount=1000&max_amount=5000&date_from=2024-01-01&date_to=2024-03-31"
```

### Clean Summary View (`GET /documents/search?summary=true`)
Retrieve only essential business fields (`id`, `filename`, `doc_type`, `structured_data`) without raw text clutter:
```bash
curl -X GET "http://localhost:8000/documents/search?summary=true"
```
**Sample response**:
```json
{
  "total": 1,
  "results": [
    {
      "id": "c5484c8e-9bf0-46c9-8672-096e286559ff",
      "filename": "sample_invoice.pdf",
      "doc_type": "invoice",
      "structured_data": {
        "company_name": "Acme Solutions Corp",
        "invoice_number": "INV-2024-8842",
        "date": "2024-03-15",
        "customer_name": "Globex International",
        "amount": 4500.0,
        "currency": "USD"
      }
    }
  ]
}
```
