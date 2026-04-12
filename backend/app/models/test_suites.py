"""SQLAlchemy model for the test_suites table."""

import uuid
from datetime import datetime

from sqlalchemy import Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.core.database import Base


class TestSuite(Base):
    """Batch test suite metadata."""

    __tablename__ = "test_suites"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    file_key: Mapped[str] = mapped_column(String(500), nullable=False)
    total_cases: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now()
    )

    records = relationship("TestRecord", back_populates="test_suite", cascade="all, delete-orphan")
