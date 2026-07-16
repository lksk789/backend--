from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from . import models, schemas
import uuid

def get_top_ranking(db: Session, limit: int = 10):
    return db.query(models.MangaStat).order_by(models.MangaStat.total_score.desc()).limit(limit).all()

def get_random_mangas(db: Session, limit: int = 16):
    """DB에 저장된 만화 중 무작위로 N개를 뽑아온다 (월드컵 후보 등에 사용)."""
    from sqlalchemy import func
    return db.query(models.Manga).order_by(func.random()).limit(limit).all()

def get_recent_mangas(db: Session, limit: int = 40):
    """최근 발매작(수집한 최신작) N개. Gemini 추천 시 재료로 넘겨준다."""
    return db.query(models.Manga).order_by(models.Manga.release_year.desc()).limit(limit).all()

def _upsert_manga(db: Session, manga_data: schemas.MangaPayload):
    # title is UNIQUE. We should find by title to prevent IntegrityError when ID changes.
    m = db.query(models.Manga).filter(models.Manga.title == manga_data.title).first()
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
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            m = db.query(models.Manga).filter(models.Manga.title == manga_data.title).first()
    else:
        # 기존 레코드가 있지만 새로운 정보가 더 나은 경우 업데이트
        updated = False
        if manga_data.imageUrl and manga_data.imageUrl.startswith("http"):
            if not m.image_url or not m.image_url.startswith("http"):
                m.image_url = manga_data.imageUrl
                updated = True
        if new_otts and not m.otts:
            m.otts = new_otts
            updated = True
            
        if updated:
            db.commit()
    return m

def update_world_cup_winner(db: Session, manga_data: schemas.MangaPayload):
    m = _upsert_manga(db, manga_data)
    stat = db.query(models.MangaStat).filter(models.MangaStat.manga_id == m.id).first()
    if stat:
        stat.world_cup_wins += 1
        stat.total_score += 1
    else:
        stat = models.MangaStat(manga_id=m.id, world_cup_wins=1, total_score=1)
        db.add(stat)
    db.commit()
    db.refresh(stat)
    return stat

def update_balance_pick(db: Session, manga_data: schemas.MangaPayload):
    m = _upsert_manga(db, manga_data)
    stat = db.query(models.MangaStat).filter(models.MangaStat.manga_id == m.id).first()
    if stat:
        stat.balance_picks += 1
        stat.total_score += 1
    else:
        stat = models.MangaStat(manga_id=m.id, balance_picks=1, total_score=1)
        db.add(stat)
    db.commit()
    db.refresh(stat)
    return stat

def get_cached_curation(db: Session, theme: str):
    return db.query(models.AiCurationCache).filter(models.AiCurationCache.theme_keyword == theme).first()

def save_curation_cache(db: Session, theme: str, manga_ids: list, comment: str):
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
        db.rollback()
        return db.query(models.AiCurationCache).filter(
            models.AiCurationCache.theme_keyword == theme
        ).first()

def add_user_tastes(db: Session, user_id_str: str, tags: list):
    try:
        uid = uuid.UUID(user_id_str)
    except (ValueError, AttributeError):
        return {}

    user = db.query(models.User).filter(models.User.id == uid).first()
    if not user:
        user = models.User(id=uid)
        db.add(user)
        db.commit()

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

    return get_user_tastes(db, user_id_str)

def get_user_tastes(db: Session, user_id_str: str):
    try:
        uid = uuid.UUID(user_id_str)
    except (ValueError, AttributeError):
        return {}

    tastes = db.query(models.UserTaste).filter(models.UserTaste.user_id == uid).all()
    result = {}
    for t in tastes:
        result[t.tag_name] = t.score
    return result
