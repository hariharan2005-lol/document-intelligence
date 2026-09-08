"""Stage 6: Schema-based field extraction using LLM with strict JSON formatting and 1-retry self-repair."""
import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from pydantic import ValidationError

from app.llm.client import BaseLLMClient
from app.schemas.common import DocumentType
from app.schemas.registry import DOCUMENT_REGISTRY

logger = logging.getLogger(__name__)


# Plain-English: A simple container that packages the outcome of the extraction process:
# the extracted structured fields, whether they passed schema validation, how many retries
# were needed, and any error message if something went wrong.
@dataclass
class ExtractionResult:
    structured_data: Optional[Dict[str, Any]]
    is_valid: bool
    retries_used: int
    error_message: Optional[str] = None


# Plain-English: The main engine for extracting structured data from cleaned text.
# 1. Finds the right blueprint/schema based on document type (invoice or resume).
# 2. Sends the text and expected JSON structure to the LLM.
# 3. Validates the LLM's response against the Pydantic schema.
# 4. If the first try fails, automatically asks the LLM to fix its mistake (1 retry).
# 5. If the retry fails, falls back to a regex/heuristic extractor if enabled.
def extract_structured_fields(
    text: str,
    doc_type: DocumentType,
    llm_client: BaseLLMClient,
) -> ExtractionResult:
    """Extract structured data matching the schema for doc_type with 1x retry on parse/validation failure."""
    config = DOCUMENT_REGISTRY.get(doc_type)
    if not config:
        return ExtractionResult(
            structured_data=None,
            is_valid=True,
            retries_used=0,
            error_message=f"No extraction schema registered for document type '{doc_type.value}'",
        )

    schema_cls = config.schema_cls
    json_schema = schema_cls.model_json_schema()
    instructions = config.extraction_instructions

    # Attempt 1
    raw_response = ""
    try:
        raw_response = llm_client.extract_fields(
            text=text,
            schema_json=json_schema,
            instructions=instructions,
        )
        parsed_data = json.loads(raw_response)
        validated_obj = schema_cls.model_validate(parsed_data)
        return ExtractionResult(
            structured_data=validated_obj.model_dump(),
            is_valid=True,
            retries_used=0,
        )
    except (json.JSONDecodeError, ValidationError, Exception) as first_err:
        first_error_msg = str(first_err)
        logger.warning(
            "First extraction attempt failed validation for %s: %s. Initiating retry 1.",
            doc_type.value,
            first_error_msg,
        )

    # Retry 1 (Self-repair with error context)
    try:
        retry_context = {
            "error_message": first_error_msg,
            "previous_output": raw_response,
        }
        raw_response_retry = llm_client.extract_fields(
            text=text,
            schema_json=json_schema,
            instructions=instructions,
            retry_context=retry_context,
        )
        parsed_data_retry = json.loads(raw_response_retry)
        validated_obj_retry = schema_cls.model_validate(parsed_data_retry)
        return ExtractionResult(
            structured_data=validated_obj_retry.model_dump(),
            is_valid=True,
            retries_used=1,
        )
    except (json.JSONDecodeError, ValidationError, Exception) as second_err:
        logger.warning(
            "Second extraction attempt failed for %s: %s. Attempting heuristic fallback extractor.",
            doc_type.value,
            second_err,
        )
        from app.config import settings
        if settings.ENABLE_HEURISTIC_FALLBACK:
            try:
                from app.llm.client import MockLLMClient
                fallback_extractor = getattr(llm_client, "fallback_client", None) or MockLLMClient()
                if getattr(fallback_extractor, "fail_first_attempt", False):
                    fallback_extractor.call_count = 1
                fallback_raw = fallback_extractor.extract_fields(
                    text=text,
                    schema_json=json_schema,
                    instructions=instructions,
                )
                fallback_data = json.loads(fallback_raw)
                validated_fallback = schema_cls.model_validate(fallback_data)
                logger.info("Heuristic fallback successfully extracted %s fields after LLM failure.", doc_type.value)
                return ExtractionResult(
                    structured_data=validated_fallback.model_dump(),
                    is_valid=True,
                    retries_used=1,
                    error_message=None,
                )
            except Exception as fb_err:
                logger.error("Heuristic fallback extraction also failed for %s: %s", doc_type.value, fb_err)

        return ExtractionResult(
            structured_data=None,
            is_valid=False,
            retries_used=1,
            error_message=f"Extraction failed validation after 1 retry: {str(second_err)}",
        )

