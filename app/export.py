import os
import pandas as pd
from app.config import EXPORT_DIR
from app.models import Document


def export_documents(documents: list[Document], fmt: str = "xlsx") -> str:
    """Flattens documents' extracted fields into a table and writes it to disk.
    Returns the file path."""
    os.makedirs(EXPORT_DIR, exist_ok=True)

    rows = []
    for doc in documents:
        row = {
            "id": doc.id,
            "filename": doc.filename,
            "doc_type": doc.doc_type,
            "status": doc.status.value if hasattr(doc.status, "value") else doc.status,
            "overall_confidence": doc.overall_confidence,
            "is_duplicate_of": doc.is_duplicate_of,
            "created_at": doc.created_at,
        }
        if doc.extracted_fields:
            for k, v in doc.extracted_fields.items():
                # keep flat scalars; stringify nested lists/dicts (line_items, etc.)
                row[k] = v if not isinstance(v, (list, dict)) else str(v)
        rows.append(row)

    df = pd.DataFrame(rows)
    ext = "xlsx" if fmt == "xlsx" else "csv"
    out_path = os.path.join(EXPORT_DIR, f"export.{ext}")

    if ext == "xlsx":
        df.to_excel(out_path, index=False)
    else:
        df.to_csv(out_path, index=False)

    return out_path
