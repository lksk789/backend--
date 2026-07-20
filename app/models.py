from sqlalchemy import Column, String, Integer, Text, JSON, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid
from .database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    tastes = relationship("UserTaste", back_populates="user", cascade="all, delete-orphan")

class UserTaste(Base):
    __tablename__ = "user_tastes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    tag_name = Column(String(50), nullable=False)
    score = Column(Integer, default=0)

    # Relationships
    user = relationship("User", back_populates="tastes")

class Manga(Base):
    __tablename__ = "mangas"

    id = Column(String(100), primary_key=True)  # custom prefix id like 'manga_123'
    title = Column(String(200), unique=True, index=True, nullable=False)
    genre = Column(String(50))
    author = Column(String(100))
    release_year = Column(Integer)
    image_url = Column(Text)
    description = Column(Text)
    otts = Column(String(200), default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    stats = relationship("MangaStat", back_populates="manga", uselist=False, cascade="all, delete-orphan")

class MangaStat(Base):
    __tablename__ = "manga_stats"

    manga_id = Column(String(100), ForeignKey("mangas.id", ondelete="CASCADE"), primary_key=True)
    balance_picks = Column(Integer, default=0)
    world_cup_wins = Column(Integer, default=0)
    total_score = Column(Integer, default=0, index=True)

    # Relationships
    manga = relationship("Manga", back_populates="stats")

class AiCurationCache(Base):
    __tablename__ = "ai_curation_cache"

    id = Column(Integer, primary_key=True, index=True)
    theme_keyword = Column(String(200), unique=True, index=True, nullable=False)
    manga_ids = Column(JSON, nullable=False)  # List of manga ids
    ai_comment = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

class Post(Base):
    __tablename__ = "posts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nickname = Column(String(50), nullable=False)
    password_hash = Column(String(255), nullable=False)
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)
    link_url = Column(Text, nullable=True)
    source_name = Column(String(100), nullable=True)
    is_official = Column(Boolean, default=False)
    thumbnail_url = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    comments = relationship("Comment", back_populates="post", cascade="all, delete-orphan")

class Comment(Base):
    __tablename__ = "comments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    post_id = Column(UUID(as_uuid=True), ForeignKey("posts.id", ondelete="CASCADE"), nullable=False)
    nickname = Column(String(50), nullable=False)
    password_hash = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    post = relationship("Post", back_populates="comments")
