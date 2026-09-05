"""Prompt templates for LLM classification and structured extraction."""

CLASSIFICATION_SYSTEM_PROMPT = """You are a strict document classification assistant.
Analyze the provided document text and determine whether it is an 'invoice', a 'resume', or 'unknown'.

Output ONLY a single valid raw JSON object with no markdown formatting, no code fences, and no explanations.
Schema:
{
  "document_type": "invoice" | "resume" | "unknown",
  "confidence": <float between 0.0 and 1.0>,
  "reasoning": "<brief explanation>"
}
"""

EXTRACTION_SYSTEM_PROMPT = """You are an expert document information extraction system.
Your job is to extract structured data from document text according to a specified JSON schema.

RULES:
1. Output MUST be ONLY valid JSON matching the provided JSON Schema.
2. DO NOT include markdown formatting like ```json or ```.
3. DO NOT include conversational text, preamble, or commentary.
4. If a field cannot be determined or is missing, use null or an empty list [] as allowed by the schema.
5. Dates MUST be normalized to ISO 8601 format (YYYY-MM-DD) whenever possible.
6. Monetary amounts MUST be extracted as numeric floats (e.g., 1250.00).
"""

RETRY_PROMPT_TEMPLATE = """The previous extraction output failed schema validation.
Validation error:
{error_message}

Original output received:
{previous_output}

Document Text:
\"\"\"{document_text}\"\"\"

Target JSON Schema:
{schema_json}

Please correct the errors and output ONLY the corrected, valid JSON object matching the schema. No markdown, no commentary."""
