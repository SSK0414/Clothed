from datetime import datetime, date
from sqlalchemy import String, Date, DateTime, ForeignKey, Table, Column, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base

outfit_items = Table(
    "outfit_items", Base.metadata,
    Column("outfit_id", ForeignKey("outfits.id", ondelete="CASCADE"), primary_key=True),
    Column("item_id", ForeignKey("clothing_items.id", ondelete="CASCADE"), primary_key=True),
)

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class ClothingItem(Base):
    __tablename__ = "clothing_items"
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    subcategory: Mapped[str | None] = mapped_column(String(60))
    colour: Mapped[str | None] = mapped_column(String(60))
    secondary_colour: Mapped[str | None] = mapped_column(String(60))
    pattern: Mapped[str | None] = mapped_column(String(60))
    material: Mapped[str | None] = mapped_column(String(80))
    occasion: Mapped[str | None] = mapped_column(String(80))
    ai_confidence: Mapped[float | None] = mapped_column()
    purchase_price: Mapped[float | None] = mapped_column()  # user-entered amount in local currency
    is_favorite: Mapped[bool] = mapped_column(default=False, nullable=False)
    brand: Mapped[str | None] = mapped_column(String(80))
    style: Mapped[str | None] = mapped_column(String(50))
    product_code: Mapped[str | None] = mapped_column(String(100), index=True)
    image_url: Mapped[str | None] = mapped_column(String(500))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    outfits: Mapped[list["Outfit"]] = relationship(secondary=outfit_items, back_populates="items")

class Outfit(Base):
    __tablename__ = "outfits"
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_favorite: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    items: Mapped[list[ClothingItem]] = relationship(secondary=outfit_items, back_populates="outfits")
    wear_logs: Mapped[list["WearLog"]] = relationship(back_populates="outfit")

class WearLog(Base):
    __tablename__ = "wear_logs"
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    worn_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    outfit_id: Mapped[int | None] = mapped_column(ForeignKey("outfits.id", ondelete="SET NULL"))
    note: Mapped[str | None] = mapped_column(String(240))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    outfit: Mapped[Outfit | None] = relationship(back_populates="wear_logs")
