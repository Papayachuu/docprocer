import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, Float, Integer, DateTime, Text, Boolean, ForeignKey, JSON, Enum
)
from sqlalchemy.orm import relationship

from app.database import Base


def gen_id():
    return str(uuid.uuid4())


class DocumentStatus(str, enum.Enum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    NEEDS_REVIEW = "needs_review"
    VALIDATED = "validated"
    FAILED = "failed"


class Document(Base):
    __tablename__ = "documents"

    id = Column(String, primary_key=True, default=gen_id)
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_hash = Column(String, index=True)  # for exact-duplicate detection
    doc_type = Column(String, index=True, default="generic")
    status = Column(Enum(DocumentStatus), default=DocumentStatus.UPLOADED)

    raw_text = Column(Text)                 # extracted text (OCR or parsed)
    used_ocr = Column(Boolean, default=False)

    extracted_fields = Column(JSON)         # the structured JSON payload
    confidence_scores = Column(JSON)        # per-field confidence (0-1)
    overall_confidence = Column(Float, default=0.0)

    validation_results = Column(JSON)       # list of {check, passed, detail}
    is_duplicate_of = Column(String, ForeignKey("documents.id"), nullable=True)

    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    duplicate_of = relationship("Document", remote_side=[id])
