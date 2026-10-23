from sqlalchemy import String, Integer, Text, ForeignKey, Boolean, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base

class DocumentVersion(Base):
    __tablename__ = "document_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    document_key: Mapped[str] = mapped_column(String(120), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    source_name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[str] = mapped_column(String(40))
    __table_args__ = (UniqueConstraint("document_key", "version_number"),)

class Node(Base):
    __tablename__ = "nodes"
    id: Mapped[int] = mapped_column(primary_key=True)
    logical_key: Mapped[str] = mapped_column(String(64), index=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("document_versions.id"), index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("nodes.id"), nullable=True)
    heading: Mapped[str] = mapped_column(Text)
    level: Mapped[int] = mapped_column(Integer, default=1)
    body_text: Mapped[str] = mapped_column(Text, default="")
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    changed_from_previous: Mapped[bool] = mapped_column(Boolean, default=False)
    children = relationship("Node", backref="parent", remote_side=[id], foreign_keys=[parent_id])

class Selection(Base):
    __tablename__ = "selections"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[str] = mapped_column(String(40))
    items = relationship("SelectionItem", back_populates="selection", cascade="all, delete-orphan")

class SelectionItem(Base):
    __tablename__ = "selection_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    selection_id: Mapped[int] = mapped_column(ForeignKey("selections.id"), index=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id"))
    version_id: Mapped[int] = mapped_column(ForeignKey("document_versions.id"))
    content_hash: Mapped[str] = mapped_column(String(64))
    heading_snapshot: Mapped[str] = mapped_column(Text)
    text_snapshot: Mapped[str] = mapped_column(Text)
    selection = relationship("Selection", back_populates="items")

class Generation(Base):
    __tablename__ = "generations"
    id: Mapped[int] = mapped_column(primary_key=True)
    selection_id: Mapped[int] = mapped_column(ForeignKey("selections.id"), index=True)
    created_at: Mapped[str] = mapped_column(String(40))
    provider: Mapped[str] = mapped_column(String(80), default="fallback")
    payload_json: Mapped[str] = mapped_column(Text)
    source_snapshot_json: Mapped[str] = mapped_column(Text)
