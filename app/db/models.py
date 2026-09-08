"""Database models for Document persistence."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, JSON, DateTime
from sqlalchemy.orm import declarative_base

Base = declarative_base()


# Plain-English: Defines the "documents" table structure in the SQLite database.
# Using SQLAlchemy's ORM, it maps Python object properties directly to SQLite table columns.
# It stores basic file info (name, format), classification (invoice/resume), cleaned text,
# timestamps, and stores the extracted business fields directly as a queryable JSON column.
class DocumentModel(Base):
    """Document record storing raw metadata, text, and extracted structured fields."""
    __tablename__ = "documents"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    filename = Column(String(255), nullable=False)
    file_type = Column(String(100), nullable=False)
    doc_type = Column(String(50), nullable=False, index=True)
    status = Column(String(50), nullable=False, default="processed", index=True)
    raw_text = Column(Text, nullable=True)
    structured_data = Column(JSON, nullable=True)
    processing_meta = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )
