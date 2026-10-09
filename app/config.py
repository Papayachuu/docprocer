"""
Central configuration: which document types the system understands,
and which fields it tries to extract for each type.

Add a new document type by adding an entry here — nothing else in the
codebase needs to change (classifier, extractor, and validator all
read from this).
"""
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    # Defaults to a local SQLite file so the project runs with zero setup.
    # Set DATABASE_URL to a postgres:// URL (see docker-compose.yml) for production.
    "sqlite:///./docproc.db",
)

HF_TOKEN = os.getenv("HF_TOKEN", "").strip()
# Qwen2.5-Coder-7B-Instruct: reliable JSON output, 32K context, free-tier friendly
# across Hugging Face's Inference Providers. Swap via env var if needed.
HF_MODEL = os.getenv("HF_MODEL", "Qwen/Qwen2.5-Coder-7B-Instruct").strip()

# Path to the tesseract binary itself (not the pytesseract Python package).
# Needed on Windows, where it's rarely on PATH by default — point this at
# e.g. C:\Program Files\Tesseract-OCR\tesseract.exe in your .env file.
# Leave unset on Mac/Linux if tesseract is already on PATH.
TESSERACT_CMD = os.getenv("TESSERACT_CMD", "").strip()

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads")
EXPORT_DIR = os.getenv("EXPORT_DIR", "./exports")

# Confidence below this threshold is routed to human review.
LOW_CONFIDENCE_THRESHOLD = float(os.getenv("LOW_CONFIDENCE_THRESHOLD", "0.75"))

# --- Document type schemas -------------------------------------------------
# Each schema describes the fields we want the LLM to extract, in plain
# language, plus which fields matter for validation/duplicate-detection.

DOCUMENT_SCHEMAS = {
    "invoice": {
        "description": "A supplier invoice or bill",
        "fields": {
            "supplier_name": "string",
            "invoice_number": "string",
            "invoice_date": "string (YYYY-MM-DD if determinable)",
            "due_date": "string (YYYY-MM-DD if determinable, else null)",
            "line_items": "array of {description, quantity, unit_price, amount}",
            "subtotal": "number",
            "tax": "number",
            "total": "number",
            "currency": "string (ISO code if determinable, else best guess symbol)",
        },
        "duplicate_key_fields": ["supplier_name", "invoice_number"],
        "totals_check": {"parts": ["subtotal", "tax"], "sum_field": "total"},
    },
    "receipt": {
        "description": "A purchase receipt from a store or vendor",
        "fields": {
            "vendor_name": "string",
            "receipt_number": "string",
            "date": "string (YYYY-MM-DD if determinable)",
            "line_items": "array of {description, quantity, unit_price, amount}",
            "subtotal": "number",
            "tax": "number",
            "total": "number",
            "payment_method": "string",
        },
        "duplicate_key_fields": ["vendor_name", "receipt_number", "total"],
        "totals_check": {"parts": ["subtotal", "tax"], "sum_field": "total"},
    },
    "purchase_order": {
        "description": "A purchase order issued to a supplier",
        "fields": {
            "buyer_name": "string",
            "supplier_name": "string",
            "po_number": "string",
            "order_date": "string (YYYY-MM-DD if determinable)",
            "line_items": "array of {description, quantity, unit_price, amount}",
            "subtotal": "number",
            "tax": "number",
            "total": "number",
        },
        "duplicate_key_fields": ["supplier_name", "po_number"],
        "totals_check": {"parts": ["subtotal", "tax"], "sum_field": "total"},
    },
    "resume": {
        "description": "A resume / CV",
        "fields": {
            "candidate_name": "string",
            "email": "string",
            "phone": "string",
            "location": "string",
            "years_experience": "number",
            "skills": "array of strings",
            "education": "array of {institution, degree, year}",
            "work_experience": "array of {company, title, start_date, end_date}",
        },
        "duplicate_key_fields": ["candidate_name", "email"],
        "totals_check": None,
    },
    "contract": {
        "description": "A legal or business contract/agreement",
        "fields": {
            "party_a": "string",
            "party_b": "string",
            "effective_date": "string (YYYY-MM-DD if determinable)",
            "expiration_date": "string (YYYY-MM-DD if determinable, else null)",
            "contract_value": "number",
            "key_terms": "array of short strings summarizing key clauses",
        },
        "duplicate_key_fields": ["party_a", "party_b", "effective_date"],
        "totals_check": None,
    },
    "application_form": {
        "description": "An application or intake form",
        "fields": {
            "applicant_name": "string",
            "email": "string",
            "phone": "string",
            "date_submitted": "string (YYYY-MM-DD if determinable)",
            "form_fields": "object mapping each visible form field label to its filled-in value",
        },
        "duplicate_key_fields": ["applicant_name", "email"],
        "totals_check": None,
    },
    "generic": {
        "description": "Any other business document not matching a known type",
        "fields": {
            "title": "string",
            "primary_date": "string (YYYY-MM-DD if determinable)",
            "key_entities": "array of strings (people/companies named)",
            "summary": "string (1-2 sentences)",
            "key_values": "object mapping any clearly labeled field to its value",
        },
        "duplicate_key_fields": ["title", "primary_date"],
        "totals_check": None,
    },
}

DOCUMENT_TYPES = list(DOCUMENT_SCHEMAS.keys())
