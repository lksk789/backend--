from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from . import models, schemas, crud
from .database import engine, get_db
from .config import settings
import httpx
import json

models.Base.metadata.create_all(bind=engine)

limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="Manga Vibe Secure API", version="1.0.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_origin_regex=r"https://.*\.vercel\.app|http://localhost:\d+",
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent"
ALADIN_LIST_URL = "https://www.aladin.co.kr/ttb/api/ItemList.aspx"

async def call_gemini(prompt: str) -> str:
    if not settings.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not set.")
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": settings.GEMINI_API_KEY,
    }
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "maxOutputTokens": 8000,
            "temperature": 0.7,
            "thinkingConfig": {"thinkingBudget": 0}  # '생각' 비활성화 → 빠르게 응답, 타임아웃 방지
        }
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(GEMINI_API_URL, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        candidates = data.get("candidates") or []
        if not candidates:
            raise ValueError("No candidates returned from Gemini")
        parts = candidates[0].get("content", {}).get("parts", []) or []
        for part in parts:
            if part.get("text"):
                return part["text"]
        raise ValueError("Gemini 응답에 텍스트가 없습니다.")

@app.get("/api/v1/health")
@limiter.limit("10/minute")
def health_check(request: Request):
    return {"status": "success", "message": "Backend is up and running securely."}

@app.get("/api/v1/mangas/ranking", response_model=schemas.RankingResponse)
@limiter.limit("30/minute")
def get_ranking(request: Request, limit: int = 10, db: Session = Depends(get_db)):
    stats = crud.get_top_ranking(db, limit=limit)
    data = []
    for rank, stat in enumerate(stats, start=1):
        data.append(schemas.RankingItem(
            rank=rank,
            id=stat.manga_id,
            title=stat.manga.title if stat.manga else f"Unknown Manga {stat.manga_id}",
            genre=stat.manga.genre if stat.manga else "Unknown",
            description=stat.manga.description if stat.manga else "",
            tags=[],
            imageUrl=stat.manga.image_url if stat.manga else "📚",
            otts=stat.manga.otts.split(",") if stat.manga and stat.manga.otts else [],
            popularityScore=stat.total_score
        ))
    return schemas.RankingResponse(status="success", data=data)

@app.get("/api/v1/mangas/ranking/reasons", response_model=schemas.RankingReasonsResponse)
@limiter.limit("10/minute")
async def get_ranking_reasons(request: Request, db: Session = Depends(get_db)):
    """랭킹 TOP 10 작품에 대해 AI가 생성한 '사람들이 좋아하는 이유'를 반환합니다."""
    # 1. 캐시 확인 (24시간 유효)
    cache_key = "ranking_reasons_v1"
    cached = crud.get_cached_curation(db, cache_key)
    if cached:
        reasons = cached.manga_ids.get("reasons", []) if isinstance(cached.manga_ids, dict) else []
        return schemas.RankingReasonsResponse(status="success", data=[schemas.RankingReasonItem(**r) for r in reasons])

    # 2. 현재 랭킹 TOP 10 가져오기
    stats = crud.get_top_ranking(db, limit=10)
    titles = [stat.manga.title for stat in stats if stat.manga]
    if not titles:
        return schemas.RankingReasonsResponse(status="success", data=[])

    titles_str = "\n".join([f"{i+1}. {t}" for i, t in enumerate(titles)])
    prompt = f"""다음은 사용자들이 가장 많이 추천한 만화 TOP {len(titles)} 목록입니다:
{titles_str}

각 작품에 대해, 독자들이 이 작품을 좋아하는 이유를 친근하고 감성적인 톤으로 1~2문장으로 작성해주세요.
이모지를 자연스럽게 활용하고, "~한 점이 매력적이에요", "~때문에 빠져들 수밖에 없어요" 같은 표현을 사용하세요.
반드시 아래의 순수 JSON 배열 형식으로만 응답해야 합니다. 백틱이나 부연 설명은 절대 금지합니다.
[
  {{"title": "작품 제목", "reason": "사람들이 좋아하는 이유"}}
]
배열의 길이는 정확히 {len(titles)}이어야 합니다.
"""
    try:
        text = await call_gemini(prompt)
        json_str = text.replace("```json", "").replace("```", "").strip()
        reasons = json.loads(json_str)

        # 캐시 저장
        crud.save_curation_cache(db, cache_key, {"reasons": reasons}, "")

        return schemas.RankingReasonsResponse(
            status="success",
            data=[schemas.RankingReasonItem(**r) for r in reasons]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/admin/fill_otts")
@limiter.limit("3/minute")  # BUG FIX: rate limit 추가 (남용 방지)
async def fill_missing_otts(request: Request, db: Session = Depends(get_db)):
    """DB에 저장된 만화 중 OTT 정보가 없는 것들을 AI로 자동 보완합니다."""
    from .models import Manga
    mangas_without_otts = db.query(Manga).filter(
        (Manga.otts.is_(None)) | (Manga.otts == "")
    ).all()
    
    if not mangas_without_otts:
        return {"status": "success", "message": "모든 작품에 이미 OTT 정보가 있습니다."}
    
    titles = [m.title for m in mangas_without_otts]
    titles_str = ", ".join([f'"{t}"' for t in titles])
    
    prompt = f"""
다음 만화/소설 작품들의 애니메이션 버전을 한국에서 시청할 수 있는 OTT 플랫폼을 알려주세요.
작품 목록: {titles_str}

반드시 아래의 순수 JSON 형식으로만 응답하세요. 각 작품의 "title"과 "otts" 배열을 포함하세요.
OTT가 없으면 빈 배열을 반환하세요. OTT는 넷플릭스, 라프텔, 왓챠, 티빙, 크런치롤 중에서만 선택하세요.
[
  {{"title": "작품제목", "otts": ["넷플릭스", "라프텔"]}}
]
"""
    try:
        text = await call_gemini(prompt)
        json_str = text.replace("```json", "").replace("```", "").strip()
        results = json.loads(json_str)
        
        updated_count = 0
        for item in results:
            manga = db.query(Manga).filter(Manga.title == item["title"]).first()
            if manga:
                manga.otts = ",".join(item.get("otts", []))
                updated_count += 1
        db.commit()
        return {"status": "success", "message": f"{updated_count}개 작품의 OTT 정보를 업데이트했습니다.", "updated": updated_count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/admin/collect_aladin")
@limiter.limit("3/minute")
async def collect_aladin_mangas(request: Request, pages: int = 2, db: Session = Depends(get_db)):
    """알라딘에서 만화를 가져와 mangas 테이블에 저장합니다.

    베스트셀러(명작·인기작)와 신간(최신작)을 함께 수집해, 풀이 최신작으로만
    치우치지 않고 유명작과 새 작품이 골고루 섞이게 합니다.
    pages: 각 목록에서 가져올 페이지 수 (한 페이지=50개).
    """
    if not settings.ALADIN_API_KEY:
        raise HTTPException(status_code=500, detail="ALADIN_API_KEY가 설정되지 않았습니다.")

    query_types = ["Bestseller", "ItemNewAll"]  # 인기작 + 최신작
    collected = 0
    async with httpx.AsyncClient(timeout=20.0) as client:
        for query_type in query_types:
            for page in range(1, pages + 1):
                params = {
                    "ttbkey": settings.ALADIN_API_KEY,
                    "QueryType": query_type,
                    "CategoryId": 2551,          # 만화/라이트노벨
                    "SearchTarget": "Book",
                    "MaxResults": 50,
                    "start": page,
                    "output": "js",
                    "Version": "20131101",
                }
                resp = await client.get(ALADIN_LIST_URL, params=params)
                resp.raise_for_status()
                try:
                    data = resp.json()
                except Exception:
                    data = json.loads(resp.text)

                items = data.get("item", [])
                if not items:
                    break

                for it in items:
                    title = (it.get("title") or "").strip()
                    if not title:
                        continue
                    isbn = it.get("isbn13") or it.get("isbn") or title
                    pub = it.get("pubDate") or ""
                    year = int(pub[:4]) if pub[:4].isdigit() else 0
                    payload = schemas.MangaPayload(
                        id=f"aladin-{isbn}",
                        title=title[:200],
                        genre=(it.get("categoryName") or "만화")[:50],
                        author=(it.get("author") or "")[:100],
                        releaseYear=year,
                        imageUrl=it.get("cover") or "",
                        description=it.get("description") or "",
                        otts=[],
                    )
                    try:
                        m = crud._upsert_manga(db, payload)
                        stat = db.query(models.MangaStat).filter(models.MangaStat.manga_id == m.id).first()
                        if not stat:
                            db.add(models.MangaStat(manga_id=m.id, total_score=0, balance_picks=0, world_cup_wins=0))
                            db.commit()
                        collected += 1
                    except Exception:
                        db.rollback()
                        continue

    return {"status": "success", "collected": collected, "message": f"알라딘 인기작+신간 만화 {collected}건을 수집/갱신했습니다."}


@app.post("/api/v1/mangas/worldcup/winner", response_model=schemas.GenericResponse)
@limiter.limit("20/minute")
def record_worldcup_winner(request: Request, body: schemas.WinnerRequest, db: Session = Depends(get_db)):
    crud.update_world_cup_winner(db, manga_data=body.manga)
    return schemas.GenericResponse(status="success", message="Winner recorded successfully.")

@app.post("/api/v1/mangas/balance_pick", response_model=schemas.GenericResponse)
@limiter.limit("20/minute")
def record_balance_pick(request: Request, body: schemas.BalancePickRequest, db: Session = Depends(get_db)):
    crud.update_balance_pick(db, manga_data=body.manga)
    return schemas.GenericResponse(status="success", message="Pick recorded successfully.")

@app.post("/api/v1/users/tastes", response_model=schemas.UserTasteResponse)
@limiter.limit("20/minute")
def save_user_tastes(request: Request, body: schemas.UserTasteRequest, db: Session = Depends(get_db)):
    tastes = crud.add_user_tastes(db, body.user_id, body.tags)
    return schemas.UserTasteResponse(status="success", data=tastes)

@app.get("/api/v1/users/{user_id}/tastes", response_model=schemas.UserTasteResponse)
@limiter.limit("20/minute")
def get_user_tastes(request: Request, user_id: str, db: Session = Depends(get_db)):
    tastes = crud.get_user_tastes(db, user_id)
    return schemas.UserTasteResponse(status="success", data=tastes)

@app.post("/api/v1/mangas/recommend", response_model=schemas.RecommendResponse)
@limiter.limit("10/minute")
async def get_recommendations(request: Request, body: schemas.RecommendRequest, db: Session = Depends(get_db)):
    tags_str = ", ".join(body.selectedTags)
    cache_key = f"recommend_{tags_str}"
    cached = crud.get_cached_curation(db, cache_key)
    
    if cached:
        mangas = cached.manga_ids
        return schemas.RecommendResponse(
            status="success", 
            data=schemas.RecommendData(
                aiComment=cached.ai_comment,
                mainRecommendation=schemas.RecommendManga(**mangas[0]),
                subRecommendations=[schemas.RecommendManga(**m) for m in mangas[1:]]
            )
        )
    
    # 최신작(알라딘 등에서 수집한 신작)을 Gemini에 재료로 제공 → Gemini가 모르는 최신작도 추천 가능 (RAG)
    recent = crud.get_recent_mangas(db, limit=40)
    recent_list_str = "\n".join(
        f"- {m.title} ({m.genre or '만화'})" for m in recent if m.title
    ) or "(등록된 최신작 없음)"

    prompt = f"""
당신은 만화 큐레이터입니다. 유저가 다음 취향 태그를 선택했습니다: {tags_str}.
이 취향에 완벽하게 부합하는 만화책 단행본 5개(메인 1개, 서브 4개)를 추천해주세요.

[최신작 목록] 아래는 최근 발매된 신작들입니다. 유저 취향에 맞는 작품이 있으면 이 목록에서 우선적으로 골라 포함하고, 부족하면 당신이 아는 명작으로 채워 총 5개를 구성하세요. 목록의 작품을 고를 때는 제목을 목록에 적힌 그대로 사용하되, 반드시 단행본 권수(예: 1권, 2권, 1 등)나 세트 표기는 지우고 **순수 작품 이름(시리즈명)**만 출력하세요. (예: "주술회전 20" -> "주술회전")
{recent_list_str}

만약 추천하는 작품이 애니메이션화되어 시청 가능한 OTT(넷플릭스, 라프텔, 왓챠, 티빙, 크런치롤 등)가 있다면 "otts" 배열에 포함시켜주세요. 없다면 빈 배열을 반환하세요.
출력할 모든 "title" 필드 값에는 절대 권수(숫자나 '권')가 포함되어서는 안 됩니다. 순수 작품 이름만 적어주세요.
반드시 아래의 순수 JSON 형식으로만 응답해야 하며, 응답 속도를 위해 최대한 간결하게 작성하세요.
{{
  "comment": "메인으로 추천하는 1위 작품이 왜 위 취향과 잘 맞는지에 대한 친근하고 발랄한 추천 코멘트 (2문장 이내, 이모지 사용)",
  "mangas": [
    {{ "id": "ai_1", "title": "1위 메인 만화 제목", "genre": "장르", "reason": "이 작품을 추천하는 이유 (1문장, 이모지 포함)", "otts": ["넷플릭스", "라프텔"] }},
    {{ "id": "ai_2", "title": "2위 서브 만화 제목", "genre": "장르", "reason": "이 작품을 추천하는 이유 (1문장, 이모지 포함)", "otts": [] }},
    {{ "id": "ai_3", "title": "3위 서브 만화 제목", "genre": "장르", "reason": "이 작품을 추천하는 이유 (1문장, 이모지 포함)", "otts": [] }},
    {{ "id": "ai_4", "title": "4위 서브 만화 제목", "genre": "장르", "reason": "이 작품을 추천하는 이유 (1문장, 이모지 포함)", "otts": [] }},
    {{ "id": "ai_5", "title": "5위 서브 만화 제목", "genre": "장르", "reason": "이 작품을 추천하는 이유 (1문장, 이모지 포함)", "otts": [] }}
  ]
}}
"""
    try:
        text = await call_gemini(prompt)
        json_str = text.replace("```json", "").replace("```", "").strip()
        data = json.loads(json_str)

        # 추천작이 DB에 있으면(=수집한 최신작) 실제 커버/설명/ID로 보강
        mangas = data["mangas"]
        for mg in mangas:
            db_m = db.query(models.Manga).filter(models.Manga.title == mg.get("title")).first()
            if db_m:
                mg["id"] = db_m.id
                if db_m.image_url:
                    mg["imageUrl"] = db_m.image_url
                if db_m.description:
                    mg["description"] = db_m.description
                if not mg.get("genre"):
                    mg["genre"] = db_m.genre or "만화"

        # Save to cache
        crud.save_curation_cache(db, cache_key, mangas, data["comment"])

        return schemas.RecommendResponse(
            status="success",
            data=schemas.RecommendData(
                aiComment=data.get("comment", "추천 코멘트가 제공되지 않았습니다."),
                mainRecommendation=schemas.RecommendManga(**mangas[0]),
                subRecommendations=[schemas.RecommendManga(**m) for m in mangas[1:]]
            )
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=repr(e))

@app.get("/api/v1/mangas/worldcup/candidates", response_model=schemas.WorldCupCandidatesResponse)
@limiter.limit("10/minute")
async def get_worldcup_candidates(request: Request, theme: str, db: Session = Depends(get_db)):
    # 매 게임마다 새로운 만화와 대진표를 제공하기 위해 캐시를 사용하지 않습니다.
    import random
    random_seed = random.randint(1, 10000)
    
    prompt = f"""
당신은 만화 큐레이터입니다. 유저가 만화 이상형 월드컵의 주제로 다음을 선택했습니다: "{theme}".
이 주제에 완벽하게 부합하는 한국에서 정발된 일본/한국 만화책 단행본 16개를 추천해 주세요. (중복 없이)
유저가 매번 색다른 게임을 즐길 수 있도록 뻔한 명작뿐만 아니라 숨겨진 수작도 포함하여 무작위성(Seed: {random_seed})을 띄게 골라주세요.
만약 추천하는 작품이 애니메이션화되어 시청 가능한 OTT(넷플릭스, 라프텔, 왓챠, 티빙, 크런치롤 등)가 있다면 "otts" 배열에 포함시켜주세요. 없다면 빈 배열을 반환하세요.
출력할 모든 "title" 필드 값에는 단행본 권수(예: 1권, 2권, 1 등)나 세트 표기를 절대 포함하지 말고 **순수 작품 이름(시리즈명)**만 적어주세요. (예: "주술회전 20" -> "주술회전")
반드시 아래의 순수 JSON 배열 형식으로만 응답해야 합니다. 백틱이나 부연 설명은 절대 금지합니다.
[
  {{
    "id": "wc_1",
    "title": "만화책 제목 (예: 강철의 연금술사)",
    "genre": "장르",
    "otts": ["라프텔", "왓챠"]
  }}
]
배열의 길이는 정확히 16이어야 합니다.
"""
    try:
        text = await call_gemini(prompt)
        json_str = text.replace("```json", "").replace("```", "").strip()
        mangas = json.loads(json_str)
        
        candidates = [schemas.WorldCupCandidate(**c) for c in mangas]
        return schemas.WorldCupCandidatesResponse(status="success", data=candidates)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/mangas/balance_questions", response_model=schemas.BalanceQuestionsResponse)
@limiter.limit("20/minute")
async def get_balance_questions(request: Request, genre: str, db: Session = Depends(get_db)):
    # 같은 장르는 캐시된 질문을 재사용 (24시간 유효) → 로딩 시간 단축
    cache_key = f"balance_{genre}"
    cached = crud.get_cached_curation(db, cache_key)
    if cached and isinstance(cached.manga_ids, list):
        return schemas.BalanceQuestionsResponse(
            status="success",
            data=[schemas.BalanceQuestionItem(**q) for q in cached.manga_ids]
        )

    prompt = f"""
당신은 만화 큐레이터입니다. 유저가 만화 취향을 알아보기 위한 밸런스 게임의 1단계로 "{genre}" 장르를 선택했습니다.
이 장르를 깊이 파고들어, 유저의 세부 취향을 분석할 수 있는 기발하고 재미있는 밸런스 질문 4개를 생성해주세요.
각 질문(step 2, 3, 4, 5)은 A와 B 두 가지 극단적이고 매력적인 선택지를 가져야 합니다.
반드시 아래의 순수 JSON 배열 형식으로만 응답해야 합니다. 백틱이나 부연 설명은 절대 금지합니다.
[
  {{
    "step": 2,
    "title": "가장 흥미를 끄는 갈등 구조는?",
    "A": {{ "text": "압도적인 외부의 적과 싸우는 것", "tag": "외부갈등", "emoji": "⚔️" }},
    "B": {{ "text": "가까운 인물과의 치열한 심리전", "tag": "내적갈등", "emoji": "🧠" }}
  }},
  {{
    "step": 3,
    "title": "질문 제목",
    "A": {{ "text": "선택지 A", "tag": "태그A", "emoji": "😎" }},
    "B": {{ "text": "선택지 B", "tag": "태그B", "emoji": "😭" }}
  }},
  {{
    "step": 4,
    "title": "질문 제목",
    "A": {{ "text": "선택지 A", "tag": "태그A", "emoji": "🔥" }},
    "B": {{ "text": "선택지 B", "tag": "태그B", "emoji": "💧" }}
  }},
  {{
    "step": 5,
    "title": "질문 제목",
    "A": {{ "text": "선택지 A", "tag": "태그A", "emoji": "⚡" }},
    "B": {{ "text": "선택지 B", "tag": "태그B", "emoji": "🌙" }}
  }}
]
"""
    try:
        text = await call_gemini(prompt)
        json_str = text.replace("```json", "").replace("```", "").strip()
        questions = json.loads(json_str)
        
        # 유효성 검증 및 파싱
        parsed = [schemas.BalanceQuestionItem(**q) for q in questions]
        # 다음번 같은 장르 요청 시 즉시 응답하도록 캐시에 저장
        crud.save_curation_cache(db, cache_key, questions, "")
        return schemas.BalanceQuestionsResponse(status="success", data=parsed)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# --- Community Posts API ---

@app.post("/api/v1/posts", response_model=schemas.PostResponse)
@limiter.limit("5/minute")
def create_post(request: Request, post: schemas.PostCreate, db: Session = Depends(get_db)):
    return crud.create_post(db, post)

@app.get("/api/v1/posts", response_model=schemas.PostListResponse)
@limiter.limit("30/minute")
def get_posts(request: Request, skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    posts = crud.get_posts(db, skip=skip, limit=limit)
    return schemas.PostListResponse(status="success", data=posts)

@app.get("/api/v1/posts/{post_id}", response_model=schemas.PostResponse)
@limiter.limit("30/minute")
def get_post(request: Request, post_id: str, db: Session = Depends(get_db)):
    try:
        import uuid
        uid = uuid.UUID(post_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid post ID format")
    
    post = crud.get_post_by_id(db, uid)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return post

@app.post("/api/v1/posts/{post_id}/verify-password")
@limiter.limit("10/minute")
def verify_post_password(request: Request, post_id: str, payload: schemas.PasswordVerifyRequest, db: Session = Depends(get_db)):
    try:
        import uuid
        uid = uuid.UUID(post_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid post ID format")
    
    # crud.delete_post logic for password check is the same, so we can just check it manually here
    post = crud.get_post_by_id(db, uid)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
        
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    if not pwd_context.verify(payload.password, post.password_hash):
        raise HTTPException(status_code=401, detail="Invalid password")
        
    return schemas.GenericResponse(status="success", message="Password verified")

@app.put("/api/v1/posts/{post_id}", response_model=schemas.PostResponse)
@limiter.limit("5/minute")
def update_post(request: Request, post_id: str, post_update: schemas.PostUpdate, db: Session = Depends(get_db)):
    try:
        import uuid
        uid = uuid.UUID(post_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid post ID format")

    try:
        updated_post = crud.update_post(db, uid, post_update)
        if not updated_post:
            raise HTTPException(status_code=404, detail="Post not found")
        return updated_post
    except ValueError as e:
        if str(e) == "Invalid password":
            raise HTTPException(status_code=401, detail="Invalid password")
        raise HTTPException(status_code=400, detail=str(e))

@app.delete("/api/v1/posts/{post_id}")
@limiter.limit("5/minute")
def delete_post(request: Request, post_id: str, payload: dict, db: Session = Depends(get_db)):
    # payload: {"password": "..."}
    password = payload.get("password")
    if not password:
        raise HTTPException(status_code=400, detail="Password is required")
        
    try:
        import uuid
        uid = uuid.UUID(post_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid post ID format")

    try:
        success = crud.delete_post(db, uid, password)
        if not success:
            raise HTTPException(status_code=404, detail="Post not found")
        return schemas.GenericResponse(status="success", message="Post deleted successfully")
    except ValueError as e:
        if str(e) == "Invalid password":
            raise HTTPException(status_code=401, detail="Invalid password")
        raise HTTPException(status_code=400, detail=str(e))

# --- Comments API ---

@app.get("/api/v1/posts/{post_id}/comments", response_model=schemas.CommentListResponse)
@limiter.limit("30/minute")
def get_comments(request: Request, post_id: str, db: Session = Depends(get_db)):
    try:
        import uuid
        uid = uuid.UUID(post_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid post ID format")
    
    comments = crud.get_comments_by_post(db, uid)
    return schemas.CommentListResponse(status="success", data=comments)

@app.post("/api/v1/posts/{post_id}/comments", response_model=schemas.CommentResponse)
@limiter.limit("10/minute")
def create_comment(request: Request, post_id: str, comment: schemas.CommentCreate, db: Session = Depends(get_db)):
    try:
        import uuid
        uid = uuid.UUID(post_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid post ID format")
        
    return crud.create_comment(db, uid, comment)

@app.delete("/api/v1/comments/{comment_id}")
@limiter.limit("10/minute")
def delete_comment(request: Request, comment_id: str, payload: dict, db: Session = Depends(get_db)):
    password = payload.get("password")
    if not password:
        raise HTTPException(status_code=400, detail="Password is required")
        
    try:
        import uuid
        uid = uuid.UUID(comment_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid comment ID format")

    try:
        success = crud.delete_comment(db, uid, password)
        if not success:
            raise HTTPException(status_code=404, detail="Comment not found")
        return schemas.GenericResponse(status="success", message="Comment deleted successfully")
    except ValueError as e:
        if str(e) == "Invalid password":
            raise HTTPException(status_code=401, detail="Invalid password")
        raise HTTPException(status_code=400, detail=str(e))
