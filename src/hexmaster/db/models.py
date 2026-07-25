# Copyright (c) 2024-2025 Gary Kuepper
# Licensed under the MIT License.

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class CatalogItem(Base):
    """Global reference for items found in the game."""

    __tablename__ = "catalog_items"

    codename: Mapped[str] = mapped_column(String(100), primary_key=True)
    displayname: Mapped[str] = mapped_column(String(255), primary_key=True)
    factionvariant: Mapped[str] = mapped_column(String(20))
    quantitypercrate: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)


class GuildConfig(Base):
    """Server-specific configuration for the bot."""

    __tablename__ = "guild_configs"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    faction: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # Colonial / Warden
    shard: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # Alpha / Bravo / Charlie
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Priority(Base):
    __tablename__ = "priority"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    codename: Mapped[str] = mapped_column(String(100), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    qty_per_crate: Mapped[int] = mapped_column(Integer)
    min_for_base_crates: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    priority: Mapped[float] = mapped_column(Float)


class StockpileSnapshot(Base):
    """A single 'upload' or snapshot of a stockpile at a point in time."""

    __tablename__ = "stockpile_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    guild_id: Mapped[Optional[int]] = mapped_column(BigInteger, index=True)
    town: Mapped[str] = mapped_column(String(100), index=True)
    struct_type: Mapped[str] = mapped_column(String(100))
    stockpile_name: Mapped[str] = mapped_column(String(255))
    war_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    shard: Mapped[Optional[str]] = mapped_column(String(20), index=True, nullable=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationship to the items within this snapshot
    items: Mapped[List["SnapshotItem"]] = relationship(back_populates="snapshot", cascade="all, delete-orphan")


class SnapshotItem(Base):
    """The individual item counts within a specific snapshot."""

    __tablename__ = "snapshot_items"

    snapshot_id: Mapped[int] = mapped_column(ForeignKey("stockpile_snapshots.id"), primary_key=True)
    code_name: Mapped[str] = mapped_column(String(100), primary_key=True)
    is_crated: Mapped[bool] = mapped_column(Boolean, default=False, primary_key=True)
    item_name: Mapped[str] = mapped_column(String(255))
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    per_crate: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer, default=0)
    description: Mapped[Optional[str]] = mapped_column(Text)

    snapshot: Mapped["StockpileSnapshot"] = relationship(back_populates="items")


class Town(Base):
    __tablename__ = "towns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    region_id: Mapped[int] = mapped_column(ForeignKey("regions.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String, unique=True, index=True)
    x: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    y: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    marker_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    global_q: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    global_r: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    town_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Region(Base):
    __tablename__ = "regions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, unique=True, index=True)
    q: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    raw_r: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    r: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    distance_to_origin: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class ReserveStockpileCode(Base):
    """Tracks 6-digit reserve stockpile codes and 48-hour expiration timers."""

    __tablename__ = "reserve_stockpile_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, index=True)
    town: Mapped[str] = mapped_column(String(100), index=True)
    struct_type: Mapped[str] = mapped_column(String(100))
    stockpile_name: Mapped[str] = mapped_column(String(255))
    access_code: Mapped[str] = mapped_column(String(10))
    last_refreshed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    created_by_user_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    alert_channel_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    alert_level: Mapped[int] = mapped_column(Integer, default=0)  # 0=normal, 1=6h, 2=2h
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class OperationTemplate(Base):
    """Regiment operation loadout manifest template."""

    __tablename__ = "operation_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, index=True)
    name: Mapped[str] = mapped_column(String(100), index=True)
    created_by_user_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    items: Mapped[List["OperationTemplateItem"]] = relationship(
        back_populates="template", cascade="all, delete-orphan"
    )


class OperationTemplateItem(Base):
    """Individual item requirements within an operation template."""

    __tablename__ = "operation_template_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("operation_templates.id", ondelete="CASCADE"))
    code_name: Mapped[str] = mapped_column(String(100))
    item_name: Mapped[str] = mapped_column(String(255))
    required_crates: Mapped[int] = mapped_column(Integer, default=1)

    template: Mapped["OperationTemplate"] = relationship(back_populates="items")


