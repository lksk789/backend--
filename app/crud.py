from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from . import models, schemas
import uuid

def get_top_ranking(db: Session, limit: int = 10):
    return db.query(models.MangaStat).order_by(models.MangaStat.total_score.desc()).limit(limit).all()

def _upsert_manga(db: Session, manga_data: schemas.MangaPayload):
    m = db.query(models.Manga).filter(models.Manga.id == manga_data.id).first()
    new_otts = ",".join(manga_data.otts) if manga_data.otts else ""
    if not m:
        m = models.Manga(
            id=manga_data.id,
            title=manga_data.title,
            genre=manga_data.genre,
            author=manga_data.author,
            release_year=manga_data.releaseYear,
            image_url=manga_data.imageUrl,
            description=manga_data.description,
            otts=new_otts
        )
        db.add(m)
        db.commit()
    else:
        # 기존 레코드가 있지만 OTT 정보가 추가된 경우 업데이트
        if new_otts and not m.otts:
            m.otts = new_otts
            db.commit()
    return m

def update_world_cup_winner(db: Session, manga_data: schemas.MangaPayload):
    _upsert_manga(db, manga_data)
    stat = db.query(models.MangaStat).filter(models.MangaStat.manga_id == manga_data.id).first()
    if stat:
        stat.world_cup_wins += 1
        stat.total_score += 1
    else:
        stat = models.MangaStat(manga_id=manga_data.id, world_cup_wins=1, total_score=1)
        db.add(stat)
    db.commit()
    db.refresh(stat)
    return stat

def update_balance_pick(db: Session, manga_data: schemas.MangaPayload):
    _upsert_manga(db, manga_data)
    stat = db.query(models.MangaStat).filter(models.MangaStat.manga_id == manga_data.id).first()
    if stat:
        stat.balance_picks += 1
        stat.total_score += 1
    else:
        stat = models.MangaStat(manga_id=manga_data.id, balance_picks=1, total_score=1)
        db.add(stat)
    db.commit()
    db.refresh(stat)
    return stat

def get_cached_curation(db: Session, theme: str):
    return db.query(models.AiCurationCache).filter(models.AiCurationCache.theme_keyword == theme).first()

def save_curation_cache(db: Session, theme: str, manga_ids: list, comment: str):
    # BUG FIX: 동일 theme_keyword가 이미 존재하면 UNIQUE 제약 위반으로 500 오류 발생.
    # 먼저 기존 캐시를 확인하고, 없을 때만 새로 저장 (upsert 패턴).
    existing = db.query(models.AiCurationCache).filter(
        models.AiCurationCache.theme_keyword == theme
    ).first()
    if existing:
        return existing

    try:
        cache = models.AiCurationCache(
            theme_keyword=theme,
            manga_ids=manga_ids,
            ai_comment=comment
        )
        db.add(cache)
        db.commit()
        db.refresh(cache)
        return cache
    except IntegrityError:
        # Race condition 대비: 동시 요청으로 insert가 겹쳤을 경우
        db.rollback()
        return db.query(models.AiCurationCache).filter(
            models.AiCurationCache.theme_keyword == theme
        ).first()

def add_user_tastes(db: Session, user_id_str: str, tags: list):
    # BUG FIX: bare except -> 구체적인 예외 타입만 캐치
    try:
        uid = uuid.UUID(user_id_str)
    except (ValueError, AttributeError):
        return {}

    user = db.query(models.User).filter(models.User.id == uid).first()
    if not user:
        user = models.User(id=uid)
        db.add(user)
        db.commit()

    # BUG FIX: 태그 루프 전체를 try/except로 감싸 부분 저장 방지
    try:
        for tag in tags:
            ut = db.query(models.UserTaste).filter(
                models.UserTaste.user_id == uid,
                models.UserTaste.tag_name == tag
            ).first()
            if ut:
                ut.score += 1
            else:
                ut = models.UserTaste(user_id=uid, tag_name=tag, score=1)
                db.add(ut)
        db.commit()
    except Exception:
        db.rollback()
        raise

    # Return all tags
    return get_user_tastes(db, user_id_str)

def get_user_tastes(db: Session, user_id_str: str):
    # BUG FIX: bare except -> 구체적인 예외 타입만 캐치
    try:
        uid = uuid.UUID(user_id_str)
    except (ValueError, AttributeError):
        return {}

    tastes = db.query(models.UserTaste).filter(models.UserTaste.user_id == uid).all()
    result = {}
    for t in tastes:
        result[t.tag_name] = t.score
    return result
