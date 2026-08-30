"""SQLAlchemy ORM models for the Samsung phone database.

Schema summary
--------------
- ``phones``          one row per scraped phone, plus a few denormalized
                      numeric columns (battery mAh, display inches, camera MP,
                      RAM, weight) so the API/chatbot can answer
                      "best battery", "largest display" style questions with a
                      simple ordered query.
- ``specifications``  the full structured key/value spec sheet for each phone,
                      grouped by GSMArena category (Network, Display, Battery,
                      ...).  Unique on (phone_id, category, key).
- ``reviews``         stores generated product reviews keyed to a phone.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.connection import Base


class Phone(Base):
    __tablename__ = "phones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    brand: Mapped[str] = mapped_column(String(100), nullable=False, default="Samsung")

    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Raw text fields straight from GSMArena.
    announced: Mapped[str | None] = mapped_column(String(255), nullable=True)
    released: Mapped[str | None] = mapped_column(String(255), nullable=True)
    price: Mapped[str | None] = mapped_column(String(255), nullable=True)
    chipset: Mapped[str | None] = mapped_column(String(255), nullable=True)
    os: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Denormalized numeric fields (parsed during scraping) to enable sorting.
    price_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    battery_capacity_mah: Mapped[int | None] = mapped_column(Integer, nullable=True)
    display_size_inches: Mapped[float | None] = mapped_column(Float, nullable=True)
    main_camera_mp: Mapped[float | None] = mapped_column(Float, nullable=True)
    ram_gb: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight_g: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    specifications: Mapped[list["Specification"]] = relationship(
        back_populates="phone",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    reviews: Mapped[list["Review"]] = relationship(
        back_populates="phone",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Phone id={self.id} name={self.name!r}>"


class Specification(Base):
    __tablename__ = "specifications"
    __table_args__ = (
        UniqueConstraint("phone_id", "category", "key", name="uq_spec_phone_cat_key"),
        Index("ix_specifications_phone_id", "phone_id"),
        Index("ix_specifications_category", "category"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    phone_id: Mapped[int] = mapped_column(
        ForeignKey("phones.id", ondelete="CASCADE"), nullable=False
    )
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)

    phone: Mapped["Phone"] = relationship(back_populates="specifications")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Spec {self.category}.{self.key}={self.value[:30]!r}>"


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (Index("ix_reviews_phone_id", "phone_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    phone_id: Mapped[int] = mapped_column(
        ForeignKey("phones.id", ondelete="CASCADE"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    phone: Mapped["Phone"] = relationship(back_populates="reviews")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Review id={self.id} phone_id={self.phone_id}>"
