"""
Layer 2: classify which document type this is, so the extractor knows
which schema (see app/config.py) to target.

Cheap keyword scoring runs first (free, instant). Only when it's
inconclusive do we spend an LLM call on classification.
"""
import json
from app.config import DOCUMENT_SCHEMAS, DOCUMENT_TYPES
from app import ai_client

KEYWORDS = {
    "invoice": ["invoice", "bill to", "invoice number", "invoice no", "amount due"],
    "receipt": ["receipt", "cashier", "change due", "thank you for your purchase"],
    "purchase_order": ["purchase order", "po number", "po#", "ship to"],
    "resume": ["resume", "curriculum vitae", "work experience", "education", "skills"],
    "contract": ["agreement", "contract", "party a", "party b", "whereas", "hereby agree"],
    "application_form": ["application form", "applicant", "please fill", "date submitted"],
}


def classify(text: str) -> tuple[str, float]:
    """Returns (doc_type, confidence 0-1)."""
    lower = text.lower()
    scores = {}
    for doc_type, words in KEYWORDS.items():
        hits = sum(1 for w in words if w in lower)
        if hits:
            scores[doc_type] = hits / len(words)

    if scores:
        best_type = max(scores, key=scores.get)
        best_score = scores[best_type]
        # Only trust the heuristic if it's reasonably confident
        if best_score >= 0.34:
            return best_type, min(0.6 + best_score * 0.4, 0.95)

    # Ambiguous — ask the LLM to pick from the known types.
    return _classify_with_llm(text)


def _classify_with_llm(text: str) -> tuple[str, float]:
    if not ai_client.is_configured():
        return "generic", 0.3

    type_list = ", ".join(DOCUMENT_TYPES)
    prompt = (
        f"Classify this document into exactly one of these types: {type_list}.\n"
        f"Respond ONLY with JSON: {{\"doc_type\": \"...\", \"confidence\": 0.0-1.0}}\n\n"
        f"Document text (may be truncated):\n{text[:4000]}"
    )
    try:
        raw = ai_client.complete_json(prompt)
        data = json.loads(raw)
        doc_type = data.get("doc_type", "generic")
        if doc_type not in DOCUMENT_SCHEMAS:
            doc_type = "generic"
        return doc_type, float(data.get("confidence", 0.5))
    except Exception:
        return "generic", 0.3
