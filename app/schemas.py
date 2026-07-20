from pydantic import BaseModel, Field, validator
from typing import List, Dict, Optional
from uuid import UUID

# --- Ranking Response ---
class RankingItem(BaseModel):
    rank: int
    id: str
    title: str
    genre: str
    description: str
    tags: List[str]
    imageUrl: str
    otts: List[str]
    popularityScore: int

class RankingResponse(BaseModel):
    status: str
    data: List[RankingItem]

# --- Recommend Request/Response ---
class RecommendRequest(BaseModel):
    selectedTags: List[str] = Field(..., max_items=10)

class RecommendManga(BaseModel):
    id: Optional[str] = None
    title: str
    genre: str
    description: Optional[str] = None
    reason: Optional[str] = None
    tags: Optional[List[str]] = []
    imageUrl: Optional[str] = None
    otts: Optional[List[str]] = []
    matchRate: Optional[int] = 100

class RecommendData(BaseModel):
    aiComment: str
    mainRecommendation: RecommendManga
    subRecommendations: List[RecommendManga]

class RecommendResponse(BaseModel):
    status: str
    data: RecommendData

# --- WorldCup Response ---
class WorldCupCandidate(BaseModel):
    id: str
    title: str
    genre: str
    description: Optional[str] = ""
    tags: Optional[List[str]] = []
    imageUrl: Optional[str] = None
    otts: Optional[List[str]] = []

class WorldCupCandidatesResponse(BaseModel):
    status: str
    data: List[WorldCupCandidate]

class MangaPayload(BaseModel):
    id: str
    title: str
    genre: str
    description: Optional[str] = ""
    imageUrl: Optional[str] = ""
    author: Optional[str] = ""
    releaseYear: Optional[int] = 0
    otts: Optional[List[str]] = []

class WinnerRequest(BaseModel):
    manga: MangaPayload

class GenericResponse(BaseModel):
    status: str
    message: str

# --- User Tastes ---
class UserTasteRequest(BaseModel):
    user_id: str
    tags: List[str]

class UserTasteResponse(BaseModel):
    status: str
    data: Dict[str, int]

# --- Balance Pick ---
class BalancePickRequest(BaseModel):
    manga: MangaPayload

# --- Balance Questions ---
class BalanceOption(BaseModel):
    text: str
    tag: str
    emoji: str

class BalanceQuestionItem(BaseModel):
    step: int
    title: str
    A: BalanceOption
    B: BalanceOption

class BalanceQuestionsResponse(BaseModel):
    status: str
    data: List[BalanceQuestionItem]

# --- Ranking Reasons ---
class RankingReasonItem(BaseModel):
    title: str
    reason: str

class RankingReasonsResponse(BaseModel):
    status: str
    data: List[RankingReasonItem]

# --- Community Posts ---
from datetime import datetime

class PostCreate(BaseModel):
    nickname: str
    password: str
    title: str
    content: str
    link_url: Optional[str] = None
    source_name: Optional[str] = None
    admin_code: Optional[str] = None
    thumbnail_url: Optional[str] = None

    @validator('link_url')
    def validate_link_url(cls, v):
        if v and not (v.startswith('http://') or v.startswith('https://')):
            raise ValueError('link_url must start with http:// or https://')
        return v

class PostUpdate(BaseModel):
    password: str
    title: str
    content: str
    link_url: Optional[str] = None
    source_name: Optional[str] = None
    admin_code: Optional[str] = None
    thumbnail_url: Optional[str] = None

    @validator('link_url')
    def validate_link_url(cls, v):
        if v and not (v.startswith('http://') or v.startswith('https://')):
            raise ValueError('link_url must start with http:// or https://')
        return v

class PostResponse(BaseModel):
    id: UUID
    nickname: str
    title: str
    content: str
    created_at: datetime
    link_url: Optional[str] = None
    source_name: Optional[str] = None
    is_official: bool = False
    thumbnail_url: Optional[str] = None
    comment_count: Optional[int] = 0

    class Config:
        from_attributes = True

class PostListResponse(BaseModel):
    status: str
    data: List[PostResponse]

# --- Comments ---
class CommentCreate(BaseModel):
    nickname: str
    password: str
    content: str

class CommentResponse(BaseModel):
    id: UUID
    post_id: UUID
    nickname: str
    content: str
    created_at: datetime

    class Config:
        from_attributes = True

class CommentListResponse(BaseModel):
    status: str
    data: List[CommentResponse]
