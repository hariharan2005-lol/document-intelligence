"""Tests for real LLM client implementations (OpenAI, Anthropic) and Hybrid fallback handling."""
import json
import pytest
import httpx
from unittest.mock import patch, MagicMock

from app.llm.client import (
    OpenAILLMClient,
    AnthropicLLMClient,
    HybridLLMClient,
    MockLLMClient,
    get_llm_client,
)
from app.schemas.invoice import InvoiceData
from app.config import settings


def test_openai_llm_client_extract_fields():
    """Verify OpenAILLMClient formats request properly and parses response from OpenAI API."""
    mock_response_payload = {
        "id": "chatcmpl-123",
        "object": "chat.completion",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": json.dumps({
                        "company_name": "Apex Cloud Systems",
                        "invoice_number": "INV-REAL-9988",
                        "date": "2026-09-02",
                        "customer_name": "Acme Global",
                        "amount": 9500.00,
                        "currency": "USD"
                    }),
                },
                "finish_reason": "stop"
            }
        ]
    }

    client = OpenAILLMClient(api_key="sk-test-key-12345", model="gpt-4o-mini")
    assert client.provider_name == "openai"
    assert client.model_name == "gpt-4o-mini"

    # Mock httpx.Client.post
    with patch.object(httpx.Client, "post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_response_payload
        mock_post.return_value = mock_resp

        extracted_raw = client.extract_fields(
            text="Invoice from Apex Cloud Systems. Invoice #: INV-REAL-9988. Total: $9500.00",
            schema_json=InvoiceData.model_json_schema(),
            instructions="Extract invoice details",
        )

        assert mock_post.called
        call_kwargs = mock_post.call_args[1]
        assert "api.openai.com/v1/chat/completions" in mock_post.call_args[0][0]
        assert call_kwargs["headers"]["Authorization"] == "Bearer sk-test-key-12345"
        assert call_kwargs["json"]["model"] == "gpt-4o-mini"
        assert call_kwargs["json"]["response_format"] == {"type": "json_object"}

        # Validate schema parsing
        parsed = json.loads(extracted_raw)
        validated = InvoiceData.model_validate(parsed)
        assert validated.invoice_number == "INV-REAL-9988"
        assert validated.amount == 9500.00


def test_anthropic_llm_client_extract_fields():
    """Verify AnthropicLLMClient formats request properly and parses response from Claude API."""
    mock_response_payload = {
        "id": "msg_123",
        "type": "message",
        "role": "assistant",
        "content": [
            {
                "type": "text",
                "text": json.dumps({
                    "company_name": "Anthropic Partner Corp",
                    "invoice_number": "CLAUDE-INV-001",
                    "date": "2026-09-03",
                    "customer_name": "Client XYZ",
                    "amount": 4200.50,
                    "currency": "USD"
                }),
            }
        ],
        "model": "claude-3-5-sonnet-20241022",
    }

    client = AnthropicLLMClient(api_key="sk-ant-test-key-67890", model="claude-3-5-sonnet-20241022")
    assert client.provider_name == "anthropic"
    assert client.model_name == "claude-3-5-sonnet-20241022"

    with patch.object(httpx.Client, "post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_response_payload
        mock_post.return_value = mock_resp

        extracted_raw = client.extract_fields(
            text="Invoice from Anthropic Partner Corp. Reference: CLAUDE-INV-001. Amount: $4200.50",
            schema_json=InvoiceData.model_json_schema(),
            instructions="Extract invoice details",
        )

        assert mock_post.called
        call_kwargs = mock_post.call_args[1]
        assert "api.anthropic.com/v1/messages" in mock_post.call_args[0][0]
        assert call_kwargs["headers"]["x-api-key"] == "sk-ant-test-key-67890"
        assert call_kwargs["headers"]["anthropic-version"] == "2023-06-01"
        assert call_kwargs["json"]["model"] == "claude-3-5-sonnet-20241022"

        parsed = json.loads(extracted_raw)
        validated = InvoiceData.model_validate(parsed)
        assert validated.invoice_number == "CLAUDE-INV-001"
        assert validated.amount == 4200.50


def test_hybrid_client_live_call_success():
    """Verify HybridLLMClient uses the primary real LLM when API call succeeds."""
    mock_primary = MagicMock()
    mock_primary.extract_fields.return_value = json.dumps({
        "company_name": "Live Primary Corp",
        "invoice_number": "LIVE-001",
        "date": "2026-09-02",
        "customer_name": "Test Client",
        "amount": 1000.0,
        "currency": "USD"
    })
    mock_primary.classify_document.return_value = {"document_type": "invoice", "confidence": 0.99}

    fallback = MockLLMClient()
    hybrid = HybridLLMClient(
        primary_client=mock_primary,
        fallback_client=fallback,
        target_provider="openai",
        target_model="gpt-4o-mini",
    )

    result = hybrid.extract_fields("Sample text", InvoiceData.model_json_schema(), "")
    assert json.loads(result)["invoice_number"] == "LIVE-001"
    assert hybrid.last_fallback_used is False
    assert hybrid.provider_name == "openai"


def test_hybrid_client_falls_back_when_api_call_fails():
    """Verify HybridLLMClient gracefully falls back to heuristic when primary LLM call fails."""
    mock_primary = MagicMock()
    mock_primary.extract_fields.side_effect = httpx.ConnectError("API server unreachable")

    fallback = MockLLMClient()
    hybrid = HybridLLMClient(
        primary_client=mock_primary,
        fallback_client=fallback,
        target_provider="anthropic",
        target_model="claude-3-5-sonnet-20241022",
    )

    # Document text that heuristic fallback can parse
    text = "Ref No: NM-77821\nDate: 02-Sep-2026\nGrand Total: 12,340.50 USD\nBill To: Contoso Ltd\nVendor: Northwind Traders"
    result = hybrid.extract_fields(text, InvoiceData.model_json_schema(), "")
    
    parsed = json.loads(result)
    assert parsed["invoice_number"] == "NM-77821"
    assert parsed["amount"] == 12340.50
    assert hybrid.last_fallback_used is True
    assert "API server unreachable" in hybrid.last_fallback_reason
    assert "fallback: mock" in hybrid.provider_name


def test_get_llm_client_auto_detection(monkeypatch):
    """Test get_llm_client factory respects ANTHROPIC_API_KEY and OPENAI_API_KEY."""
    monkeypatch.setattr(settings, "LLM_PROVIDER", "anthropic")
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-ant-test")
    client = get_llm_client()
    assert isinstance(client, HybridLLMClient)
    assert client._target_provider == "anthropic"
    assert client.primary_client is not None
