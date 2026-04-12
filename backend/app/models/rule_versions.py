"""SQLAlchemy model for the rule_versions table."""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.core.database import Base


class RuleVersion(Base):
    """Rule version history snapshot."""

    __tablename__ = "rule_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    rule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rules.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    modified_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    modified_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now()
    )
    change_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    rule = relationship("Rule", back_populates="versions")
