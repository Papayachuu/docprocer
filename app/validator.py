"""
Layer 4: validation. Runs cheap, deterministic checks on top of the
AI-extracted fields — these never require another LLM call.
"""
from sqlalchemy.orm import Session
from app.config import DOCUMENT_SCHEMAS
from app.models import Document


def run_validations(doc_type: str, fields: dict) -> list[dict]:
    schema = DOCUMENT_SCHEMAS.get(doc_type, DOCUMENT_SCHEMAS["generic"])
    results = []

    # 1. Missing required-looking fields (anything null)
    missing = [k for k, v in fields.items() if v in (None, "", [])]
    results.append({
        "check": "missing_fields",
        "passed": len(missing) == 0,
        "detail": f"Missing: {', '.join(missing)}" if missing else "All fields present",
    })

    # 2. Totals arithmetic check (invoice/receipt/PO)
    totals_check = schema.get("totals_check")
    if totals_check:
        parts = totals_check["parts"]
        sum_field = totals_check["sum_field"]
        try:
            part_values = [float(fields.get(p) or 0) for p in parts]
            expected = round(sum(part_values), 2)
            actual = float(fields.get(sum_field) or 0)
            passed = abs(expected - actual) < 0.01
            results.append({
                "check": "totals_arithmetic",
                "passed": passed,
                "detail": f"{'+'.join(parts)} = {expected}, {sum_field} = {actual}",
            })
        except (TypeError, ValueError):
            results.append({
                "check": "totals_arithmetic",
                "passed": False,
                "detail": "Could not compute — non-numeric totals",
            })

    return results


def find_duplicate(db: Session, doc_type: str, fields: dict, exclude_id: str = None) -> str | None:
    """
    Looks for an existing document of the same type whose key fields
    (as defined in DOCUMENT_SCHEMAS[...]['duplicate_key_fields']) match.
    Returns the matching Document's id, or None.
    """
    schema = DOCUMENT_SCHEMAS.get(doc_type, DOCUMENT_SCHEMAS["generic"])
    key_fields = schema.get("duplicate_key_fields", [])
    if not key_fields:
        return None

    key_values = {k: fields.get(k) for k in key_fields}
    if any(v in (None, "") for v in key_values.values()):
        return None  # not enough info to compare confidently

    candidates = db.query(Document).filter(Document.doc_type == doc_type)
    if exclude_id:
        candidates = candidates.filter(Document.id != exclude_id)

    for candidate in candidates:
        if not candidate.extracted_fields:
            continue
        cand_values = {k: candidate.extracted_fields.get(k) for k in key_fields}
        if cand_values == key_values:
            return candidate.id

    return None
