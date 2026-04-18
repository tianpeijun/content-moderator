"""SQLAlchemy model for the model_config table."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Float, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base


class ModelConfig(Base):
    """AI model configuration."""

    __tablename__ = "model_config"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    model_id: Mapped[str] = mapped_column(String(100), nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    temperature: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    max_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=1024)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_fallback: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    routing_type: Mapped[str] = mapped_column(String(20), nullable=False, default="any")  # text_only / multimodal / any
    fallback_result: Mapped[str | None] = mapped_column(String(20), nullable=True)
    cost_per_1k_input: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    cost_per_1k_output: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(), onupdate=func.now()
    )
