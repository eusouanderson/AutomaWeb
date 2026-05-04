from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class BuilderSession(Base):
    __tablename__ = "builder_sessions"

    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    url: Mapped[str] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    steps = relationship(
        "BuilderStep",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="BuilderStep.step",
    )


class BuilderStep(Base):
    __tablename__ = "builder_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("builder_sessions.session_id", ondelete="CASCADE"), index=True
    )
    step: Mapped[int] = mapped_column(Integer, index=True)
    action: Mapped[str] = mapped_column(String(32), index=True)
    selector: Mapped[str] = mapped_column(Text)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    step_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    page_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    page_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    element_tag: Mapped[str | None] = mapped_column(String(100), nullable=True)
    element_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    href: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    session = relationship("BuilderSession", back_populates="steps")