from pydantic import BaseModel, Field
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
