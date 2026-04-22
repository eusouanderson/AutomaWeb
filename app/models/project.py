from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Project(Base):
    """Project model."""

    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(150), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    test_directory: Mapped[str | None] = mapped_column(String(500), nullable=True)
    scan_cache: Mapped[str | None] = mapped_column(Text, nullable=True)
    scan_cached_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    test_requests = relationship(
        "TestRequest", back_populates="project", cascade="all, delete-orphan"
    )
    test_executions = relationship(
        "TestExecution", back_populates="project", cascade="all, delete-orphan"
    )
