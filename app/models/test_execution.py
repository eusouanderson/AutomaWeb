"""Model for test execution results"""
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class TestExecution(Base):
    """Test execution result model."""

    __tablename__ = "test_executions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    total_tests: Mapped[int] = mapped_column(Integer, default=0)
    passed: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    skipped: Mapped[int] = mapped_column(Integer, default=0)
    log_file: Mapped[str] = mapped_column(String(500), nullable=False)
    report_file: Mapped[str] = mapped_column(String(500), nullable=False)
    output_file: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="running")  # running, completed, failed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    mkdocs_index: Mapped[str | None] = mapped_column(String(500), nullable=True)
    test_cases: Mapped[list | None] = mapped_column(JSON, nullable=True)

    project = relationship("Project", back_populates="test_executions")
