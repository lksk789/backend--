"""알라딘 만화(인기작+신간)를 가져와 DB에 저장하는 1회용 스크립트.

사용법 (backend 폴더에서, venv 켠 상태):
    python collect_now.py
"""
import json
import httpx
from app.config import settings
from app.database import SessionLocal
from app import crud, schemas, models

ALADIN_LIST_URL = "https://www.aladin.co.kr/ttb/api/ItemList.aspx"
PAGES = 4  # 각 목록에서 가져올 페이지 수 (1페이지=50개)


def main():
    if not settings.ALADIN_API_KEY:
        print("❌ ALADIN_API_KEY가 .env에 없습니다.")
        return

    db = SessionLocal()
    collected = 0
    try:
        with httpx.Client(timeout=30.0) as client:
            for query_type in ["Bestseller", "ItemNewAll"]:  # 인기작 + 최신작
                for page in range(1, PAGES + 1):
                    params = {
                        "ttbkey": settings.ALADIN_API_KEY,
                        "QueryType": query_type,
                        "CategoryId": 2551,       # 만화/라이트노벨
                        "SearchTarget": "Book",
                        "MaxResults": 50,
                        "start": page,
                        "output": "js",
                        "Version": "20131101",
                    }
                    resp = client.get(ALADIN_LIST_URL, params=params)
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
                            stat = db.query(models.MangaStat).filter(
                                models.MangaStat.manga_id == m.id
                            ).first()
                            if not stat:
                                db.add(models.MangaStat(
                                    manga_id=m.id, total_score=0,
                                    balance_picks=0, world_cup_wins=0,
                                ))
                                db.commit()
                            collected += 1
                        except Exception:
                            db.rollback()
                            continue
                    print(f"  [{query_type}] {page}페이지 완료 · 누적 {collected}건")
    finally:
        db.close()

    print(f"\n✅ 완료! 총 {collected}건 수집/갱신했습니다.")


if __name__ == "__main__":
    main()
