"""Stage 3: Classify document type using fast heuristics first, falling back to LLM if ambiguous."""
import logging
import re
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from app.llm.client import BaseLLMClient
from app.schemas.common import DocumentType
from app.schemas.registry import DOCUMENT_REGISTRY

logger = logging.getLogger(__name__)

# Heuristic confidence threshold above which we accept heuristic classification
HEURISTIC_THRESHOLD = 0.35


# Plain-English: A data container holding the classification outcome:
# the decided document type (invoice, resume, or unknown), the confidence score (0.0 to 1.0),
# the method used to decide ("heuristic", "llm", or "fallback"), and an explanation of why.
@dataclass
class ClassificationResult:
    doc_type: DocumentType
    confidence: float
    source: str  # "heuristic" or "llm"
    reasoning: Optional[str] = None


# Plain-English: Evaluates the text against keyword lists for invoices and resumes.
# It checks how many signature keywords appear in the document (using whole-word matching
# for single words and phrase matching for compound terms like "bill to") and calculates
# a percentage match score for each document type.
def score_heuristics(text: str) -> Dict[DocumentType, Tuple[int, float]]:
    """Calculate matched keyword count and density score for each registered document type."""
    text_lower = text.lower()
    results: Dict[DocumentType, Tuple[int, float]] = {}

    for doc_type, config in DOCUMENT_REGISTRY.items():
        if not config.heuristic_keywords:
            results[doc_type] = (0, 0.0)
            continue

        matched_count = 0
        for kw in config.heuristic_keywords:
            # Word boundary matching for short words, substring for phrases
            if " " in kw:
                if kw in text_lower:
                    matched_count += 1
            else:
                if re.search(r'\b' + re.escape(kw) + r'\b', text_lower):
                    matched_count += 1

        score = matched_count / len(config.heuristic_keywords)
        results[doc_type] = (matched_count, score)

    return results


# Plain-English: The decision maker that categorizes a document as invoice, resume, or unknown:
# 1. If the text is empty, returns UNKNOWN immediately.
# 2. Checks for definite title phrases (e.g. "billing statement", "commercial invoice") -> INVOICE.
# 3. Tallies keyword counts; if a category has >= 2 strong matches and beats rivals, classifies via fast heuristics.
# 4. If ambiguous (e.g. ties or low keyword counts), sends the text to the LLM for deep semantic reasoning.
# 5. If the LLM is unreachable or fails, falls back to the best weak keyword match or marks as UNKNOWN.
def classify_document_text(
    text: str,
    llm_client: Optional[BaseLLMClient] = None,
) -> ClassificationResult:
    """Classify document type using heuristic rules, falling back to LLM if ambiguous."""
    if not text.strip():
        return ClassificationResult(
            doc_type=DocumentType.UNKNOWN,
            confidence=1.0,
            source="heuristic",
            reasoning="Document text is empty",
        )

    text_lower = text.lower()

    # 1. Direct title/phrase matching for high-confidence classification
    strong_invoice_indicators = [
        "billing statement", "commercial invoice", "tax invoice", "proforma invoice"
    ]
    if any(indicator in text_lower for indicator in strong_invoice_indicators):
        return ClassificationResult(
            doc_type=DocumentType.INVOICE,
            confidence=0.95,
            source="heuristic",
            reasoning="Matched strong invoice document title indicator",
        )

    # 2. Run heuristic scoring
    stats = score_heuristics(text)
    sorted_by_score = sorted(stats.items(), key=lambda item: (item[1][0], item[1][1]), reverse=True)

    if sorted_by_score:
        top_type, (top_count, top_score) = sorted_by_score[0]
        second_count = sorted_by_score[1][1][0] if len(sorted_by_score) > 1 else 0

        # Strong heuristic match: at least 2 distinct keywords and clear margin over other types
        if top_count >= 2 and (top_count > second_count or top_score >= 0.15):
            confidence = min(0.99, max(0.75, round(0.55 + top_score * 1.1, 2)))
            return ClassificationResult(
                doc_type=top_type,
                confidence=confidence,
                source="heuristic",
                reasoning=f"Matched {top_count} signature keywords ({round(top_score * 100, 1)}%) for {top_type.value}",
            )

    # 3. Fall back to LLM if heuristics were ambiguous and LLM client is provided
    if llm_client:
        try:
            llm_result = llm_client.classify_document(text)
            classified_str = str(llm_result.get("document_type", "unknown")).lower()

            try:
                doc_type = DocumentType(classified_str)
            except ValueError:
                doc_type = DocumentType.UNKNOWN

            return ClassificationResult(
                doc_type=doc_type,
                confidence=float(llm_result.get("confidence", 0.7)),
                source="llm",
                reasoning=llm_result.get("reasoning", "Classified via LLM inference"),
            )
        except Exception as exc:
            logger.warning("LLM classification failed: %s. Defaulting to top heuristic or unknown.", exc)

    # 4. Default fallback if no LLM or LLM fails
    if sorted_by_score and sorted_by_score[0][1][0] >= 1:
        top_type, (top_count, top_score) = sorted_by_score[0]
        return ClassificationResult(
            doc_type=top_type,
            confidence=0.6,
            source="heuristic_low_confidence",
            reasoning=f"Ambiguous match, highest weak heuristic score ({top_count} keyword)",
        )

    return ClassificationResult(
        doc_type=DocumentType.UNKNOWN,
        confidence=0.5,
        source="fallback",
        reasoning="No strong patterns detected",
    )

