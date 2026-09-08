"""LLM Client abstractions supporting Mock, OpenAI, and Gemini providers."""
import json
import logging
import re
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

import httpx

from app.config import settings
from app.llm.prompts import (
    CLASSIFICATION_SYSTEM_PROMPT,
    EXTRACTION_SYSTEM_PROMPT,
    RETRY_PROMPT_TEMPLATE,
)

logger = logging.getLogger(__name__)


# Plain-English: Cleans up the LLM's response by removing markdown code fences (like ```json ... ```)
# and trimming surrounding whitespace so the text can be parsed directly as valid JSON.
def clean_llm_json_response(raw_text: str) -> str:
    """Strip code fences and trailing/leading artifacts from LLM JSON response."""
    text = raw_text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


# Plain-English: Finds dates written in various formats (e.g. "02-Sep-2026", "September 1, 2026",
# "2026-09-02", "12.06.2026") anywhere in the text and converts them into standard ISO YYYY-MM-DD format.
def parse_iso_date(text: str) -> str:
    """Extract and normalize a date string from arbitrary text into ISO 8601 (YYYY-MM-DD)."""
    # Look for explicit date labels first
    label_match = re.search(
        r'(?:date|dated|issue\s*date|billing\s*date|invoice\s*date|statement\s*date|doc\s*date|date\s*of\s*sale|date\s*issued|billing\s*period\s*start)\s*[:]?\s*([^\n\r]+)',
        text,
        re.IGNORECASE,
    )
    search_scopes = []
    if label_match:
        search_scopes.append(label_match.group(1).strip())
    search_scopes.append(text)

    month_names = 'jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec'
    full_months = 'january|february|march|april|may|june|july|august|september|october|november|december'

    for scope in search_scopes:
        # Pattern A: DD-Mon-YYYY or DD Mon YYYY or DD/Mon/YYYY (e.g. "02-Sep-2026", "21 Aug 2026")
        m = re.search(
            r'\b(\d{1,2})[-/\s](' + month_names + '|' + full_months + r')[-/\s](\d{4})\b',
            scope,
            re.IGNORECASE,
        )
        if m:
            try:
                d, mon, y = m.group(1), m.group(2)[:3].title(), m.group(3)
                dt = datetime.strptime(f"{int(d):02d}-{mon}-{y}", "%d-%b-%Y")
                return dt.strftime("%Y-%m-%d")
            except Exception:
                pass

        # Pattern B: Mon DD, YYYY or Month DD, YYYY (e.g. "Sep 03, 2026", "September 1, 2026")
        m = re.search(
            r'\b(' + month_names + '|' + full_months + r')\s+(\d{1,2}),?\s+(\d{4})\b',
            scope,
            re.IGNORECASE,
        )
        if m:
            try:
                mon, d, y = m.group(1)[:3].title(), m.group(2), m.group(3)
                dt = datetime.strptime(f"{int(d):02d}-{mon}-{y}", "%d-%b-%Y")
                return dt.strftime("%Y-%m-%d")
            except Exception:
                pass

        # Pattern C: YYYY-MM-DD or YYYY.MM.DD or YYYY/MM/DD (e.g. "2026-09-02")
        m = re.search(r'\b(\d{4})[-/\.](\d{1,2})[-/\.](\d{1,2})\b', scope)
        if m:
            try:
                y, mon, d = m.group(1), int(m.group(2)), int(m.group(3))
                if 1 <= mon <= 12 and 1 <= d <= 31:
                    return f"{y}-{mon:02d}-{d:02d}"
            except Exception:
                pass

        # Pattern D: DD/MM/YYYY or DD.MM.YYYY or DD-MM-YYYY (e.g. "12.06.2026", "30/07/2026")
        m = re.search(r'\b(\d{1,2})[-/\.](\d{1,2})[-/\.](\d{4})\b', scope)
        if m:
            try:
                d, mon, y = int(m.group(1)), int(m.group(2)), m.group(3)
                if mon > 12 and d <= 12:
                    d, mon = mon, d
                if 1 <= mon <= 12 and 1 <= d <= 31:
                    return f"{y}-{mon:02d}-{d:02d}"
            except Exception:
                pass

    return "2024-01-15"



INVALID_INVOICE_NUM_WORDS = {
    "invoice", "invoices", "tax", "statement", "statements", "bill", "billing",
    "receipt", "receipts", "order", "orders", "commercial", "proforma", "original",
    "copy", "date", "dated", "number", "numbers", "due", "total", "amount", "usd",
    "eur", "gbp", "jpy", "details", "summary", "page", "client", "customer", "vendor"
}


# Plain-English: Searches the text for invoice, reference, or statement numbers (e.g. "INV-2024-8842",
# "Ref No: MPL-9081", "Statement #: 5501"), while ignoring document headers or false positives like "/Invoice".
def parse_invoice_number(text: str) -> str:
    """Extract invoice or reference number supporting varied labels, avoiding slash/label collisions."""
    # Pattern 1: Explicit labels with colon, hash, or number keywords
    # e.g. "Invoice Number: INV-001", "Statement #: STMT-2026-901", "Ref No: MPL-9081", "Invoice / Ref No: MPL-9081"
    label_pattern = (
        r'(?:'
        r'(?:invoice|inv|statement|bill|ref(?:erence)?|doc(?:ument)?|receipt|order|p\.?o\.?)'
        r'(?:\s*/\s*(?:invoice|inv|statement|bill|ref(?:erence)?|doc(?:ument)?|receipt|order|p\.?o\.?))*'
        r'\s*(?:no\.?|number|#|id|code)?\s*[:#]\s*'
        r'|\b(?:invoice|inv|statement|bill|ref(?:erence)?|doc(?:ument)?|receipt|order|p\.?o\.?)\s+'
        r'(?:no\.?|number|#|id|code)\s*[:#]?\s*'
        r')([A-Za-z0-9][A-Za-z0-9\-_/]*[A-Za-z0-9]|[A-Za-z0-9]+)'
    )

    ignore_headers = (
        "INVOICE", "TAX INVOICE", "COMMERCIAL INVOICE", "BILL", "RECEIPT",
        "STATEMENT", "BILLING STATEMENT", "PROFORMA INVOICE"
    )

    for line in text.splitlines():
        line_clean = line.strip()
        if not line_clean:
            continue
        # Skip standalone header lines and slash combinations like "TAX INVOICE / INVOICE"
        clean_upper = line_clean.upper()
        if any(clean_upper == h or clean_upper.startswith(h + " /") or clean_upper.startswith(h + "/") for h in ignore_headers):
            # Check if there is also an explicit number on the same line, e.g. "TAX INVOICE / INVOICE No: 123"
            if not re.search(r'[:#]\s*[A-Za-z0-9]', line_clean):
                continue

        # Try label match
        for m in re.finditer(label_pattern, line_clean, re.IGNORECASE):
            candidate = m.group(1).strip().strip("/-_")
            cand_lower = candidate.lower()
            if (
                len(candidate) >= 2
                and cand_lower not in INVALID_INVOICE_NUM_WORDS
                and not cand_lower.startswith("invoice")
                and not cand_lower.startswith("/invoice")
            ):
                return candidate

    # Pattern 2: Reference code pattern like MPL-9081, INV-2024-8842, STMT-2026-901, CI-2026-0045
    code_match = re.search(r'\b([A-Z]{2,6}-[0-9A-Z]{3,10})\b', text)
    if code_match:
        cand = code_match.group(1)
        if cand.split("-")[0].lower() not in ("page", "date"):
            return cand

    # Pattern 3: Standalone "Statement #" or "Invoice #" where number follows
    stmt_match = re.search(r'(?:statement|invoice|ref)\s*#\s*[:]?\s*([A-Za-z0-9\-_]+)', text, re.IGNORECASE)
    if stmt_match:
        cand = stmt_match.group(1).strip("/-_")
        if cand.lower() not in INVALID_INVOICE_NUM_WORDS:
            return cand

    return "INV-DEFAULT-001"


# Plain-English: Finds the total amount due or payable in the invoice text (handling labels like
# "Grand Total", "Amount Payable", or currency signs) and converts whole numbers or decimals to float.
def parse_invoice_amount(text: str) -> float:
    """Extract numeric monetary amount due supporting varied labels, whole numbers (e.g. 890,000 JPY), and decimals."""
    # 1. High priority labels: Amount Payable, Grand Total, Net Payable, Total Due, Balance Due, etc.
    primary_label_pat = (
        r'(?:'
        r'grand\s*total|net\s*payable|amount\s*payable|total\s*payable|'
        r'balance\s*(?:due|payable)|total\s*amount\s*(?:due|payable)?|'
        r'amount\s*due|total\s*due|final\s*amount|invoice\s*total|statement\s*total'
        r')\s*[:]?\s*(?:[A-Z]{3}|[\$€£₹¥])?\s*'
        r'([0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]{1,2})?|[0-9]+\.[0-9]{1,2}|[0-9]{2,})'
    )
    matches = re.findall(primary_label_pat, text, re.IGNORECASE)
    if matches:
        for val in reversed(matches):
            clean_str = val.replace(',', '')
            try:
                amt = float(clean_str)
                if amt > 0:
                    return amt
            except ValueError:
                pass

    # 2. General total / amount label: Total: X, Amount: X
    sec_label_pat = (
        r'(?:total|amount)\s*[:]?\s*(?:[A-Z]{3}|[\$€£₹¥])?\s*'
        r'([0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]{1,2})?|[0-9]+\.[0-9]{1,2}|[0-9]{2,})'
    )
    matches = re.findall(sec_label_pat, text, re.IGNORECASE)
    if matches:
        for val in reversed(matches):
            clean_str = val.replace(',', '')
            try:
                amt = float(clean_str)
                if amt > 0:
                    return amt
            except ValueError:
                pass

    # 3. Currency-prefixed or postfixed amounts (e.g. "¥890,000", "890,000 JPY", "$4,500.00", "45,250.00 EUR")
    curr_prefix_pat = (
        r'[\$€£₹¥]\s*([0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]{1,2})?|[0-9]+\.[0-9]{1,2}|[0-9]{2,})'
    )
    matches = re.findall(curr_prefix_pat, text, re.IGNORECASE)
    if matches:
        for val in reversed(matches):
            clean_str = val.replace(',', '')
            try:
                amt = float(clean_str)
                if amt > 0:
                    return amt
            except ValueError:
                pass

    curr_postfix_pat = (
        r'([0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]{1,2})?|[0-9]+\.[0-9]{1,2}|[0-9]{2,})\s*'
        r'(?:USD|EUR|GBP|INR|JPY|CAD|AUD|CHF|CNY|SGD)'
    )
    matches = re.findall(curr_postfix_pat, text, re.IGNORECASE)
    if matches:
        for val in reversed(matches):
            clean_str = val.replace(',', '')
            try:
                amt = float(clean_str)
                if amt > 0:
                    return amt
            except ValueError:
                pass

    # 4. Fallback: Find any formatted number with comma thousands or decimals
    all_nums = re.findall(r'\b([0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]{1,2})?|[0-9]+\.[0-9]{2})\b', text)
    if all_nums:
        parsed = []
        for s in all_nums:
            try:
                parsed.append(float(s.replace(',', '')))
            except ValueError:
                pass
        if parsed:
            return max(parsed)

    return 100.00


# Plain-English: Detects which currency the invoice uses (e.g., USD, EUR, GBP, JPY, CAD)
# by checking for currency symbols ($, €, ¥, £) or currency abbreviations in the text.
def parse_currency(text: str) -> str:
    """Detect ISO currency code from symbols or text."""
    if "€" in text or re.search(r'\bEUR\b', text, re.IGNORECASE):
        return "EUR"
    if "£" in text or re.search(r'\bGBP\b', text, re.IGNORECASE):
        return "GBP"
    if "¥" in text or re.search(r'\bJPY\b', text, re.IGNORECASE):
        return "JPY"
    if "₹" in text or re.search(r'\bINR\b', text, re.IGNORECASE):
        return "INR"
    if re.search(r'\bCAD\b', text, re.IGNORECASE):
        return "CAD"
    if re.search(r'\bAUD\b', text, re.IGNORECASE):
        return "AUD"
    if re.search(r'\bCHF\b', text, re.IGNORECASE):
        return "CHF"
    if re.search(r'\bCNY\b', text, re.IGNORECASE):
        return "CNY"
    if re.search(r'\bSGD\b', text, re.IGNORECASE):
        return "SGD"
    if "$" in text or re.search(r'\bUSD\b', text, re.IGNORECASE):
        return "USD"
    return "USD"


# Plain-English: Extracts the names of both the issuer (seller/vendor/shipper) and the
# receiver (customer/client/consignee) of the invoice.
def parse_company_and_customer(text: str) -> Tuple[str, str]:
    """Extract issuing company name and customer name, supporting commercial invoices (Shipper/Consignee)."""
    # Vendor / Company / Exporter / Shipper
    company_match = re.search(
        r'\b(?:shipper\s*/\s*exporter|exporter|shipper|from|vendor|issuer|seller|issued\s*by|company)\b\s*[:]?\s*([^\n\r]+)',
        text,
        re.IGNORECASE,
    )
    if company_match:
        company_name = company_match.group(1).strip()
    else:
        # Take first non-empty line that isn't a generic heading
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        company_name = "Acme Corporation"
        ignore_titles = (
            "INVOICE", "TAX INVOICE", "COMMERCIAL INVOICE", "RECEIPT",
            "STATEMENT", "BILLING STATEMENT", "PROFORMA INVOICE", "BILL",
            "PROFESSIONAL SERVICES INVOICE", "SUBSCRIPTION INVOICE", "SALES INVOICE"
        )
        for line in lines[:5]:
            clean_upper = line.upper()
            if not any(clean_upper == t or clean_upper.startswith(t + " ") or clean_upper.startswith(t + "/") for t in ignore_titles) and len(line) > 2:
                company_name = line
                break

    # Customer / Client / Consignee / Buyer
    cust_match = re.search(
        r'\b(?:consignee|buyer|account\s*holder|client\s*name|bill\s*to|sold\s*to|invoiced\s*to|recipient|ship\s*to|deliver\s*to|customer|client)\b\s*[:]?\s*([^\n\r]*)',
        text,
        re.IGNORECASE,
    )
    customer_name = "Client Corp"
    if cust_match:
        candidate = cust_match.group(1).strip()
        if not candidate:
            after_pos = cust_match.end()
            rest = [line.strip() for line in text[after_pos:].splitlines() if line.strip()]
            if rest:
                candidate = rest[0]
        if candidate:
            candidate = re.sub(r'^(?:name\s*[:]?)\s*', '', candidate, flags=re.IGNORECASE).strip()
            customer_name = candidate

    return company_name, customer_name




# Plain-English: The blueprint (interface) that all LLM clients must follow.
# It defines the required contract for classifying documents and extracting structured fields.
class BaseLLMClient(ABC):
    """Abstract interface for LLM operations."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name of the provider (e.g. 'openai', 'gemini', 'mock')."""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Name of the underlying model."""
        pass

    @abstractmethod
    def classify_document(self, text: str) -> Dict[str, Any]:
        """Classify document type using LLM."""
        pass

    @abstractmethod
    def extract_fields(
        self,
        text: str,
        schema_json: Dict[str, Any],
        instructions: str,
        retry_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Extract structured JSON matching the provided schema."""
        pass


# Plain-English: A simulated, offline LLM client that uses regular expressions and pattern matching
# instead of calling an external AI API. Useful for automated tests and as an offline fallback.
class MockLLMClient(BaseLLMClient):
    """Deterministic Mock LLM client for offline execution and automated testing."""

    def __init__(self, fail_first_attempt: bool = False):
        self.fail_first_attempt = fail_first_attempt
        self.call_count = 0

    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def model_name(self) -> str:
        return "mock-heuristic-v1"

    # Plain-English: Checks for common invoice or resume keywords to categorize the document offline.
    def classify_document(self, text: str) -> Dict[str, Any]:
        """Classify text using semantic heuristic fallback."""
        lower = text.lower()
        invoice_kws = [
            "invoice", "bill to", "tax invoice", "subtotal", "amount due", "ref no",
            "billing statement", "statement", "statement #", "amount payable",
            "commercial invoice", "consignee", "payment due", "balance due", "total payable"
        ]
        if any(kw in lower for kw in invoice_kws):
            return {"document_type": "invoice", "confidence": 0.95, "reasoning": "Mock LLM detected invoice terms"}
        elif any(kw in lower for kw in ["resume", "curriculum vitae", "education", "experience", "skills"]):
            return {"document_type": "resume", "confidence": 0.95, "reasoning": "Mock LLM detected resume terms"}
        return {"document_type": "unknown", "confidence": 0.5, "reasoning": "Unrecognized content"}

    # Plain-English: Routes to the appropriate offline parser (invoice or resume) to extract fields as a JSON string.
    def extract_fields(
        self,
        text: str,
        schema_json: Dict[str, Any],
        instructions: str,
        retry_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        self.call_count += 1

        # Test retry capability if configured to fail first attempt
        if self.fail_first_attempt and self.call_count == 1:
            return '{"invalid_json": "missing_required_fields"}'

        title = schema_json.get("title", "").lower()
        if "invoice" in title:
            return self._extract_mock_invoice(text)
        elif "resume" in title:
            return self._extract_mock_resume(text)
        return "{}"

    # Plain-English: Uses regex patterns to extract invoice numbers, dates, amounts, currencies, and company names.
    def _extract_mock_invoice(self, text: str) -> str:
        """Extract invoice fields from text using generalized pattern matching."""
        company_name, customer_name = parse_company_and_customer(text)
        inv_num = parse_invoice_number(text)
        date_str = parse_iso_date(text)
        amount = parse_invoice_amount(text)
        currency = parse_currency(text)

        result = {
            "company_name": company_name,
            "invoice_number": inv_num,
            "date": date_str,
            "customer_name": customer_name,
            "amount": amount,
            "currency": currency,
        }
        return json.dumps(result)

    # Plain-English: Uses regex patterns to extract candidate name, email, phone, skills, education, and jobs.
    def _extract_mock_resume(self, text: str) -> str:
        """Extract resume fields from text using pattern matching."""
        # Candidate name
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        name = "Jane Doe"
        for line in lines[:5]:
            if not any(header in line.lower() for header in ["resume", "curriculum", "email", "phone", "summary"]):
                name = line
                break

        # Email
        email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', text)
        email = email_match.group(0) if email_match else "jane.doe@example.com"

        # Phone
        phone_match = re.search(r'(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}', text)
        phone = phone_match.group(0) if phone_match else "555-0199"

        # Skills
        known_skills = [
            "Python", "FastAPI", "Flask", "Django", "SQL", "PostgreSQL", "Docker",
            "Kubernetes", "AWS", "Git", "React", "TypeScript", "JavaScript",
            "Machine Learning", "PyTorch", "NLP", "Linux"
        ]
        found_skills = [skill for skill in known_skills if re.search(r'\b' + re.escape(skill) + r'\b', text, re.IGNORECASE)]
        if not found_skills:
            found_skills = ["Python", "FastAPI"]

        # Education
        education = []
        edu_match = re.search(r'(?:B\.S\.|B\.A\.|M\.S\.|Bachelor|Master|Ph\.D\.)[^\n\r]*', text, re.IGNORECASE)
        degree = edu_match.group(0).strip() if edu_match else "B.S. Computer Science"

        inst_match = re.search(r'(?:University|College|Institute|School)[^\n\r,]*', text, re.IGNORECASE)
        institution = inst_match.group(0).strip() if inst_match else "State University"

        year_match = re.search(r'\b(20[0-2][0-9]|19[89][0-9])\b', text)
        year = year_match.group(0) if year_match else "2020"

        education.append({
            "institution": institution,
            "degree": degree,
            "year": year
        })

        # Experience
        experience = []
        exp_match = re.search(r'(?:Software Engineer|Developer|Architect|Lead|Manager|DevOps Engineer)[^\n\r]*', text, re.IGNORECASE)
        title = exp_match.group(0).strip() if exp_match else "Software Engineer"

        comp_match = re.search(r'(?:at|company:)\s*([A-Za-z0-9\s&]+)(?:\n|$)', text, re.IGNORECASE)
        company = comp_match.group(1).strip() if comp_match else "Tech Solutions Inc"

        experience.append({
            "company": company,
            "title": title,
            "duration": "2021 - Present"
        })

        result = {
            "name": name,
            "email": email,
            "phone": phone,
            "skills": found_skills,
            "education": education,
            "experience": experience,
        }
        return json.dumps(result)


# Plain-English: Connects to OpenAI's Chat Completions API (or local OpenAI-compatible APIs
# like Ollama or LocalAI) to classify documents and extract structured JSON fields.
class OpenAILLMClient(BaseLLMClient):
    """OpenAI or OpenAI-compatible (e.g. Ollama/LocalAI) API client implementation."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-4o-mini",
        base_url: Optional[str] = None,
    ):
        self.api_key = api_key or "no-key-required"
        self.model = model
        base = (base_url or "https://api.openai.com/v1").rstrip("/")
        self.url = f"{base}/chat/completions"

    @property
    def provider_name(self) -> str:
        return "openai"

    @property
    def model_name(self) -> str:
        return self.model

    # Plain-English: Performs the HTTP POST request to the OpenAI API endpoint with JSON mode enabled.
    def _call_api(self, messages: list) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.0,
            "response_format": {"type": "json_object"},
        }
        with httpx.Client(timeout=30.0) as client:
            response = client.post(self.url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]

    # Plain-English: Asks OpenAI to determine whether the document is an invoice, resume, or unknown.
    def classify_document(self, text: str) -> Dict[str, Any]:
        messages = [
            {"role": "system", "content": CLASSIFICATION_SYSTEM_PROMPT},
            {"role": "user", "content": f"Document Text:\n{text[:4000]}"},
        ]
        raw = self._call_api(messages)
        cleaned = clean_llm_json_response(raw)
        return json.loads(cleaned)

    # Plain-English: Sends the document text and target JSON schema to OpenAI, returning extracted fields.
    def extract_fields(
        self,
        text: str,
        schema_json: Dict[str, Any],
        instructions: str,
        retry_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        if retry_context:
            user_msg = RETRY_PROMPT_TEMPLATE.format(
                error_message=retry_context.get("error_message"),
                previous_output=retry_context.get("previous_output"),
                document_text=text[:6000],
                schema_json=json.dumps(schema_json, indent=2),
            )
        else:
            user_msg = (
                f"Instructions:\n{instructions}\n\n"
                f"Target JSON Schema:\n{json.dumps(schema_json, indent=2)}\n\n"
                f"Document Text:\n{text[:6000]}"
            )

        messages = [
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ]
        raw = self._call_api(messages)
        return clean_llm_json_response(raw)


# Plain-English: Connects to Anthropic's Claude API (e.g. claude-3-5-sonnet) via HTTP
# to classify documents and extract structured JSON data.
class AnthropicLLMClient(BaseLLMClient):
    """Anthropic Claude API client implementation."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-3-5-sonnet-20241022",
        base_url: Optional[str] = None,
    ):
        self.api_key = api_key
        self.model = model
        base = (base_url or "https://api.anthropic.com/v1").rstrip("/")
        self.url = f"{base}/messages"

    @property
    def provider_name(self) -> str:
        return "anthropic"

    @property
    def model_name(self) -> str:
        return self.model

    # Plain-English: Sends the prompt to Anthropic's Messages API endpoint and extracts Claude's text answer.
    def _call_api(self, system_prompt: str, user_prompt: str) -> str:
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": self.model,
            "max_tokens": 2048,
            "temperature": 0.0,
            "system": system_prompt,
            "messages": [
                {"role": "user", "content": user_prompt}
            ],
        }
        with httpx.Client(timeout=45.0) as client:
            response = client.post(self.url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            content_blocks = data.get("content", [])
            text_parts = [b.get("text", "") for b in content_blocks if b.get("type") == "text"]
            return "".join(text_parts)

    # Plain-English: Prompts Claude to determine whether the document text is an invoice, resume, or unknown.
    def classify_document(self, text: str) -> Dict[str, Any]:
        prompt = f"Document Text:\n{text[:4000]}"
        raw = self._call_api(CLASSIFICATION_SYSTEM_PROMPT, prompt)
        cleaned = clean_llm_json_response(raw)
        return json.loads(cleaned)

    # Plain-English: Instructs Claude to extract structured fields matching the JSON schema, with error feedback on retries.
    def extract_fields(
        self,
        text: str,
        schema_json: Dict[str, Any],
        instructions: str,
        retry_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        if retry_context:
            user_msg = RETRY_PROMPT_TEMPLATE.format(
                error_message=retry_context.get("error_message"),
                previous_output=retry_context.get("previous_output"),
                document_text=text[:6000],
                schema_json=json.dumps(schema_json, indent=2),
            )
        else:
            user_msg = (
                f"Instructions:\n{instructions}\n\n"
                f"Target JSON Schema:\n{json.dumps(schema_json, indent=2)}\n\n"
                f"Document Text:\n{text[:6000]}"
            )
        raw = self._call_api(EXTRACTION_SYSTEM_PROMPT, user_msg)
        return clean_llm_json_response(raw)


# Plain-English: Connects to Google's Gemini REST API (e.g. gemini-1.5-flash) using JSON response mode
# to classify documents and extract structured schema data.
class GeminiLLMClient(BaseLLMClient):
    """Google Gemini REST API client implementation."""

    def __init__(self, api_key: str, model: str = "gemini-1.5-flash"):
        self.api_key = api_key
        self.model = model
        self.url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def model_name(self) -> str:
        return self.model

    # Plain-English: Sends the prompt to Google Gemini's generateContent endpoint and extracts the text content.
    def _call_api(self, system_instruction: str, user_prompt: str) -> str:
        headers = {"Content-Type": "application/json"}
        payload = {
            "systemInstruction": {"parts": [{"text": system_instruction}]},
            "contents": [{"parts": [{"text": user_prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.0,
            },
        }
        with httpx.Client(timeout=30.0) as client:
            response = client.post(self.url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]

    # Plain-English: Prompts Gemini to categorize the document text as an invoice, resume, or unknown.
    def classify_document(self, text: str) -> Dict[str, Any]:
        prompt = f"Document Text:\n{text[:4000]}"
        raw = self._call_api(CLASSIFICATION_SYSTEM_PROMPT, prompt)
        return json.loads(clean_llm_json_response(raw))

    # Plain-English: Prompts Gemini to extract structured fields conforming to the specified JSON schema.
    def extract_fields(
        self,
        text: str,
        schema_json: Dict[str, Any],
        instructions: str,
        retry_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        if retry_context:
            prompt = RETRY_PROMPT_TEMPLATE.format(
                error_message=retry_context.get("error_message"),
                previous_output=retry_context.get("previous_output"),
                document_text=text[:6000],
                schema_json=json.dumps(schema_json, indent=2),
            )
        else:
            prompt = (
                f"Instructions:\n{instructions}\n\n"
                f"Target JSON Schema:\n{json.dumps(schema_json, indent=2)}\n\n"
                f"Document Text:\n{text[:6000]}"
            )
        raw = self._call_api(EXTRACTION_SYSTEM_PROMPT, prompt)
        return clean_llm_json_response(raw)


# Plain-English: A resilient wrapper client that prioritizes calling the real live LLM (OpenAI, Anthropic, or Gemini),
# but automatically falls back to the offline heuristic extractor if no API key is provided or if an API call fails.
class HybridLLMClient(BaseLLMClient):
    """
    Primary live LLM client with heuristic fallback.
    Calls the real LLM API (OpenAI or Anthropic) as the primary extraction path.
    If no API key is provided or the API call fails and fallback is enabled,
    it falls back to the heuristic extractor and sets transparent fallback metadata.
    """

    def __init__(
        self,
        primary_client: Optional[BaseLLMClient],
        fallback_client: BaseLLMClient,
        target_provider: str,
        target_model: str,
    ):
        self.primary_client = primary_client
        self.fallback_client = fallback_client
        self._target_provider = target_provider
        self._target_model = target_model
        self.last_fallback_used = False
        self.last_fallback_reason: Optional[str] = None

    @property
    def provider_name(self) -> str:
        if self.last_fallback_used:
            return f"{self._target_provider} (fallback: mock)"
        return self._target_provider

    @property
    def model_name(self) -> str:
        return self._target_model

    # Plain-English: Attempts to classify the document with the primary live LLM; falls back to the heuristic classifier on failure.
    def classify_document(self, text: str) -> Dict[str, Any]:
        if self.primary_client:
            try:
                res = self.primary_client.classify_document(text)
                self.last_fallback_used = False
                self.last_fallback_reason = None
                return res
            except Exception as exc:
                if not settings.ENABLE_HEURISTIC_FALLBACK:
                    raise
                logger.warning(
                    "Primary LLM %s classification call failed (%s). Falling back to heuristic classifier.",
                    self._target_provider,
                    exc,
                )
                self.last_fallback_used = True
                self.last_fallback_reason = str(exc)

        self.last_fallback_used = True
        if not self.last_fallback_reason:
            self.last_fallback_reason = f"No API key configured for {self._target_provider.upper()}"
        return self.fallback_client.classify_document(text)

    # Plain-English: Attempts to extract fields using the primary live LLM API; falls back to the heuristic extractor if an error occurs.
    def extract_fields(
        self,
        text: str,
        schema_json: Dict[str, Any],
        instructions: str,
        retry_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        if self.primary_client:
            try:
                res = self.primary_client.extract_fields(
                    text=text,
                    schema_json=schema_json,
                    instructions=instructions,
                    retry_context=retry_context,
                )
                self.last_fallback_used = False
                self.last_fallback_reason = None
                return res
            except Exception as exc:
                if not settings.ENABLE_HEURISTIC_FALLBACK:
                    raise
                logger.warning(
                    "Primary LLM %s field extraction call failed (%s). Falling back to heuristic extractor.",
                    self._target_provider,
                    exc,
                )
                self.last_fallback_used = True
                self.last_fallback_reason = str(exc)

        if not settings.ENABLE_HEURISTIC_FALLBACK:
            raise RuntimeError(
                f"Primary LLM provider '{self._target_provider}' requires {self._target_provider.upper()}_API_KEY."
            )

        self.last_fallback_used = True
        if not self.last_fallback_reason:
            self.last_fallback_reason = f"No API key configured for {self._target_provider.upper()}"
        return self.fallback_client.extract_fields(
            text=text,
            schema_json=schema_json,
            instructions=instructions,
            retry_context=retry_context,
        )


# Plain-English: Factory function that reads application settings and environment variables
# (API keys and chosen provider) to construct and return the configured LLM client instance.
def get_llm_client() -> BaseLLMClient:
    """Factory function to provide the configured LLM client instance with live primary path and transparent fallback."""
    provider = settings.LLM_PROVIDER.lower()
    fallback_engine = MockLLMClient()

    # Automatically switch provider if Anthropic key is configured but OpenAI key is not
    if provider == "openai" and not settings.OPENAI_API_KEY and settings.ANTHROPIC_API_KEY:
        provider = "anthropic"

    if provider == "anthropic":
        primary = None
        if settings.ANTHROPIC_API_KEY:
            logger.info("Initializing live AnthropicLLMClient (model=%s)", settings.ANTHROPIC_MODEL)
            primary = AnthropicLLMClient(
                api_key=settings.ANTHROPIC_API_KEY,
                model=settings.ANTHROPIC_MODEL,
            )
        else:
            logger.warning(
                "LLM_PROVIDER is set to 'anthropic' but ANTHROPIC_API_KEY is not set. "
                "Will use heuristic fallback until ANTHROPIC_API_KEY is provided."
            )
        return HybridLLMClient(
            primary_client=primary,
            fallback_client=fallback_engine,
            target_provider="anthropic",
            target_model=settings.ANTHROPIC_MODEL,
        )

    elif provider == "openai":
        primary = None
        if settings.OPENAI_API_KEY or settings.OPENAI_BASE_URL:
            logger.info(
                "Initializing live OpenAILLMClient (model=%s, base_url=%s)",
                settings.OPENAI_MODEL,
                settings.OPENAI_BASE_URL,
            )
            primary = OpenAILLMClient(
                api_key=settings.OPENAI_API_KEY,
                model=settings.OPENAI_MODEL,
                base_url=settings.OPENAI_BASE_URL,
            )
        else:
            logger.warning(
                "LLM_PROVIDER is set to 'openai' but OPENAI_API_KEY is not set. "
                "Will use heuristic fallback until OPENAI_API_KEY is provided."
            )
        return HybridLLMClient(
            primary_client=primary,
            fallback_client=fallback_engine,
            target_provider="openai",
            target_model=settings.OPENAI_MODEL,
        )

    elif provider == "gemini":
        primary = None
        if settings.GEMINI_API_KEY:
            logger.info("Initializing live GeminiLLMClient (model=%s)", settings.GEMINI_MODEL)
            primary = GeminiLLMClient(api_key=settings.GEMINI_API_KEY, model=settings.GEMINI_MODEL)
        else:
            logger.warning(
                "LLM_PROVIDER is set to 'gemini' but GEMINI_API_KEY is not set. "
                "Will use heuristic fallback until GEMINI_API_KEY is provided."
            )
        return HybridLLMClient(
            primary_client=primary,
            fallback_client=fallback_engine,
            target_provider="gemini",
            target_model=settings.GEMINI_MODEL,
        )

    logger.info("Explicit mock LLM provider requested.")
    return fallback_engine
