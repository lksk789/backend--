"""
이 스크립트는 DB에 저장된 만화들의 OTT 정보를 수동으로 채울 때 사용합니다.
현재는 /api/v1/admin/fill_otts 엔드포인트(AI 자동화)로 대체되었습니다.

직접 실행 방법: backend/ 폴더에서
  source venv/bin/activate && python update_otts.py
"""
import os
import sys

# .env 로드를 위해 backend/ 폴더를 경로에 추가
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BACKEND_DIR)

# .env 파일 수동 로드 (python-dotenv 없는 환경 대비)
env_path = os.path.join(os.path.dirname(BACKEND_DIR), ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip())

import asyncio

# OTT 정보가 알려진 작품 목록 (AI fill_otts 엔드포인트로 대체 가능)
KNOWN_OTT_MAP = {
    "괴짜가족": ["라프텔"],
    "괴수 8호": ["넷플릭스", "라프텔", "티빙"],
    "체인소 맨": ["넷플릭스", "라프텔"],
    "지옥락": ["라프텔"],
    "나나": ["라프텔", "왓챠"],
    "주술회전": ["넷플릭스", "라프텔"],
    "나 혼자만 레벨업": ["라프텔"],
}

async def update_otts():
    from app.database import SessionLocal
    from app import models

    db = SessionLocal()
    try:
        mangas = db.query(models.Manga).all()
        updated = 0
        for manga in mangas:
            if not manga.otts:
                otts = KNOWN_OTT_MAP.get(manga.title)
                if otts is not None:
                    manga.otts = ",".join(otts)
                    print(f"Updated '{manga.title}': {otts}")
                    updated += 1
                else:
                    print(f"No OTT data for '{manga.title}' - skipping")
        db.commit()
        print(f"\nDone! Updated {updated} records.")
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(update_otts())
