import hashlib
import os
import shutil
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import Base, engine, get_db
from app.models import Document, DocumentStatus
from app import ocr, classifier, extractor, validator, export
from app.config import UPLOAD_DIR, EXPORT_DIR, LOW_CONFIDENCE_THRESHOLD

Base.metadata.create_all(bind=engine)
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(EXPORT_DIR, exist_ok=True)

app = FastAPI(title="AI Document Processing & Data Extraction")


def _hash_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def process_document(doc_id: str):
    """The full pipeline, run in the background after upload:
    OCR/text extraction -> classification -> AI extraction -> validation ->
    duplicate detection -> status update.
    """
    db = next(get_db())
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        return

    try:
        doc.status = DocumentStatus.PROCESSING
        doc.error_message = None
        db.commit()

        text, used_ocr = ocr.extract_text(doc.file_path)
        doc.raw_text = text
        doc.used_ocr = used_ocr

        doc_type, _type_confidence = classifier.classify(text)
        doc.doc_type = doc_type

        result = extractor.extract_fields(text, doc_type)
        doc.extracted_fields = result["fields"]
        doc.confidence_scores = result["confidence"]
        doc.overall_confidence = result["overall_confidence"]

        checks = validator.run_validations(doc_type, result["fields"])
        dup_id = validator.find_duplicate(db, doc_type, result["fields"], exclude_id=doc.id)
        if dup_id:
            checks.append({"check": "duplicate", "passed": False, "detail": f"Matches document {dup_id}"})
            doc.is_duplicate_of = dup_id
        doc.validation_results = checks

        all_checks_passed = all(c["passed"] for c in checks)
        if doc.overall_confidence < LOW_CONFIDENCE_THRESHOLD or not all_checks_passed:
            doc.status = DocumentStatus.NEEDS_REVIEW
        else:
            doc.status = DocumentStatus.VALIDATED

    except Exception as e:
        doc.status = DocumentStatus.FAILED
        doc.error_message = str(e)

    db.commit()


@app.post("/documents/upload")
def upload_document(background_tasks: BackgroundTasks, file: UploadFile = File(...), db: Session = Depends(get_db)):
    dest_path = os.path.join(UPLOAD_DIR, file.filename)
    with open(dest_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    file_hash = _hash_file(dest_path)
    exact_dup = db.query(Document).filter(Document.file_hash == file_hash).first()

    doc = Document(filename=file.filename, file_path=dest_path, file_hash=file_hash)
    if exact_dup:
        doc.is_duplicate_of = exact_dup.id
    db.add(doc)
    db.commit()
    db.refresh(doc)

    background_tasks.add_task(process_document, doc.id)
    return {"id": doc.id, "filename": doc.filename, "status": doc.status}


@app.post("/documents/batch-upload")
def batch_upload(background_tasks: BackgroundTasks, files: list[UploadFile] = File(...), db: Session = Depends(get_db)):
    results = []
    for file in files:
        dest_path = os.path.join(UPLOAD_DIR, file.filename)
        with open(dest_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
        file_hash = _hash_file(dest_path)
        exact_dup = db.query(Document).filter(Document.file_hash == file_hash).first()

        doc = Document(filename=file.filename, file_path=dest_path, file_hash=file_hash)
        if exact_dup:
            doc.is_duplicate_of = exact_dup.id
        db.add(doc)
        db.commit()
        db.refresh(doc)

        background_tasks.add_task(process_document, doc.id)
        results.append({"id": doc.id, "filename": doc.filename})
    return {"queued": results}


@app.get("/documents")
def list_documents(
    status: Optional[str] = None,
    doc_type: Optional[str] = None,
    q: Optional[str] = None,
    db: Session = Depends(get_db),
):
    query = db.query(Document)
    if status:
        query = query.filter(Document.status == status)
    if doc_type:
        query = query.filter(Document.doc_type == doc_type)
    docs = query.order_by(Document.created_at.desc()).all()

    if q:
        q_lower = q.lower()
        docs = [
            d for d in docs
            if q_lower in (d.filename or "").lower()
            or q_lower in str(d.extracted_fields or "").lower()
        ]

    return [
        {
            "id": d.id,
            "filename": d.filename,
            "doc_type": d.doc_type,
            "status": d.status,
            "overall_confidence": d.overall_confidence,
            "is_duplicate_of": d.is_duplicate_of,
            "created_at": d.created_at,
        }
        for d in docs
    ]


@app.get("/documents/{doc_id}")
def get_document(doc_id: str, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")
    return {
        "id": doc.id,
        "filename": doc.filename,
        "doc_type": doc.doc_type,
        "status": doc.status,
        "used_ocr": doc.used_ocr,
        "raw_text": doc.raw_text,
        "extracted_fields": doc.extracted_fields,
        "confidence_scores": doc.confidence_scores,
        "overall_confidence": doc.overall_confidence,
        "validation_results": doc.validation_results,
        "is_duplicate_of": doc.is_duplicate_of,
        "error_message": doc.error_message,
        "created_at": doc.created_at,
    }


@app.get("/documents/{doc_id}/file")
def get_document_file(doc_id: str, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc or not os.path.exists(doc.file_path):
        raise HTTPException(404, "Document or file not found")
    return FileResponse(doc.file_path, filename=doc.filename)


@app.patch("/documents/{doc_id}")
def update_document_fields(doc_id: str, payload: dict, db: Session = Depends(get_db)):
    """Human review: lets a reviewer correct extracted fields and mark it validated."""
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")
    
    # Support both flat field dictionary and nested { fields, status } payload
    if "fields" in payload and isinstance(payload["fields"], dict):
        new_fields = payload["fields"]
        status_val = payload.get("status", "validated")
    else:
        new_fields = payload
        status_val = "validated"

    doc.extracted_fields = {**(doc.extracted_fields or {}), **new_fields}
    
    # Re-run validation checks with updated fields
    checks = validator.run_validations(doc.doc_type, doc.extracted_fields)
    dup_id = validator.find_duplicate(db, doc.doc_type, doc.extracted_fields, exclude_id=doc.id)
    if dup_id:
        checks.append({"check": "duplicate", "passed": False, "detail": f"Matches document {dup_id}"})
    doc.validation_results = checks

    if status_val in [s.value for s in DocumentStatus]:
        doc.status = DocumentStatus(status_val)
    else:
        doc.status = DocumentStatus.VALIDATED

    db.commit()
    return {
        "id": doc.id,
        "status": doc.status,
        "extracted_fields": doc.extracted_fields,
        "validation_results": doc.validation_results
    }


@app.post("/documents/{doc_id}/reprocess")
def reprocess_document(doc_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")
    background_tasks.add_task(process_document, doc.id)
    return {"id": doc.id, "status": "queued"}


@app.get("/export")
def export_documents(
    format: str = "xlsx",
    doc_type: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    query = db.query(Document)
    if doc_type:
        query = query.filter(Document.doc_type == doc_type)
    if status:
        query = query.filter(Document.status == status)
    docs = query.all()
    if not docs:
        raise HTTPException(404, "No documents match those filters")

    path = export.export_documents(docs, fmt=format)
    return FileResponse(path, filename=os.path.basename(path))


@app.get("/stats")
def stats(db: Session = Depends(get_db)):
    docs = db.query(Document).all()
    by_status = {}
    by_type = {}
    for d in docs:
        status_key = d.status.value if hasattr(d.status, "value") else d.status
        by_status[status_key] = by_status.get(status_key, 0) + 1
        by_type[d.doc_type] = by_type.get(d.doc_type, 0) + 1
    return {"total": len(docs), "by_status": by_status, "by_type": by_type}


# Serve the dashboard
app.mount("/", StaticFiles(directory="static", html=True), name="static")
