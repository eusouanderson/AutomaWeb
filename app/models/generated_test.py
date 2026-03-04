from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class GeneratedTest(Base):
    """Generated test model."""

    __tablename__ = "generated_tests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    test_request_id: Mapped[int] = mapped_column(ForeignKey("test_requests.id"), index=True)
    content: Mapped[str] = mapped_column(Text)
    file_path: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    test_request = relationship("TestRequest", back_populates="generated_test")
