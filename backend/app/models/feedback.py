from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.database import Base
from app.core.security import utcnow

class Feedback(Base):
    __tablename__ = 'feedback'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True, nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    liked: Mapped[str] = mapped_column(Text, default='', nullable=False)
    improve: Mapped[str] = mapped_column(Text, default='', nullable=False)
    comment: Mapped[str] = mapped_column(Text, default='', nullable=False)
    is_bug_report: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_feature_request: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    public_consent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    admin_status: Mapped[str] = mapped_column(String(30), default='new', nullable=False)
    admin_note: Mapped[str] = mapped_column(Text, default='', nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    user = relationship("User", back_populates="feedbacks")
