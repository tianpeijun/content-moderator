"""SQLAlchemy model for the moderation_logs table."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Float, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base


class ModerationLog(Base):
    """Content moderation audit log."""

    __tablename__ = "moderation_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    task_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    input_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_image_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    business_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    final_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[str | None] = mapped_column(String(20), nullable=True)
    text_label: Mapped[str | None] = mapped_column(String(50), nullable=True)
    image_label: Mapped[str | None] = mapped_column(String(50), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    matched_rules: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    processing_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    degraded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    model_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("idx_logs_result_created", "result", "created_at"),
        Index("idx_logs_business_type_created", "business_type", "created_at"),
        Index("idx_logs_task_id", "task_id", unique=True),
        Index("idx_logs_text_label_created", "text_label", "created_at"),
        Index("idx_logs_image_label_created", "image_label", "created_at"),
        Index("idx_logs_language_created", "language", "created_at"),
    )
