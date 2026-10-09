"""
Layer 3: AI extraction. Given raw text and a classified doc_type, ask
the LLM to fill in exactly the fields defined for that type in
app/config.py, plus a confidence score per field.
"""
import json
from app.config import DOCUMENT_SCHEMAS
from app import ai_client


def extract_fields(text: str, doc_type: str) -> dict:
    """
    Returns:
        {
          "fields": {...extracted values...},
          "confidence": {field_name: 0-1, ...},
          "overall_confidence": 0-1,
        }
    """
    schema = DOCUMENT_SCHEMAS.get(doc_type, DOCUMENT_SCHEMAS["generic"])
    field_spec = "\n".join(f'  - "{name}": {desc}' for name, desc in schema["fields"].items())

    prompt = f"""Extract data from the following {schema['description']}.

Extract exactly these fields:
{field_spec}

Rules:
- If a field is not present in the document, set its value to null.
- Numbers must be plain numbers (no currency symbols or commas).
- Return an overall_confidence (0.0-1.0) and a per-field confidence in "field_confidence",
  where low confidence means the value was unclear, ambiguous, or guessed.

Respond ONLY with this JSON shape:
{{
  "fields": {{ ... one key per field above ... }},
  "field_confidence": {{ ... same keys, each a number 0.0-1.0 ... }},
  "overall_confidence": 0.0-1.0
}}

Document text:
{text[:12000]}
"""

    if not ai_client.is_configured():
        # No API key configured — return an empty low-confidence result
        # rather than failing the whole pipeline.
        return {
            "fields": {k: None for k in schema["fields"]},
            "confidence": {k: 0.0 for k in schema["fields"]},
            "overall_confidence": 0.0,
            "error": "HF_TOKEN not configured",
        }

    raw = ai_client.complete_json(prompt)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {
            "fields": {k: None for k in schema["fields"]},
            "confidence": {k: 0.0 for k in schema["fields"]},
            "overall_confidence": 0.0,
            "error": f"Could not parse model output: {raw[:300]}",
        }

    return {
        "fields": data.get("fields", {}),
        "confidence": data.get("field_confidence", {}),
        "overall_confidence": float(data.get("overall_confidence", 0.5)),
    }
