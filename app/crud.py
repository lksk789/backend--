from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from . import models, schemas
import uuid
from passlib.context import CryptContext
from .config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

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

def get_cached_curation(db: Session, theme: str, max_age_hours: int = 24):
    """캐시를 가져오되, 만든 지 max_age_hours(기본 24시간)가 지났으면 무시(None 반환)한다.
    → 하루가 지나면 자동으로 새 추천을 생성하도록 만든다."""
    from datetime import datetime, timedelta
    row = db.query(models.AiCurationCache).filter(
        models.AiCurationCache.theme_keyword == theme
    ).first()
    if not row:
        return None
    if row.created_at and row.created_at < datetime.utcnow() - timedelta(hours=max_age_hours):
        return None  # 하루 지난 캐시 → 새로 생성하게 함
    return row

def save_curation_cache(db: Session, theme: str, manga_ids: list, comment: str):
    from datetime import datetime
    existing = db.query(models.AiCurationCache).filter(
        models.AiCurationCache.theme_keyword == theme
    ).first()
    if existing:
        # 기존 캐시가 있으면 새 내용으로 갱신하고 시간도 갱신 (하루 주기 재시작)
        existing.manga_ids = manga_ids
        existing.ai_comment = comment
        existing.created_at = datetime.utcnow()
        db.commit()
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

# --- Community Posts CRUD ---

def create_post(db: Session, post: schemas.PostCreate):
    hashed_password = pwd_context.hash(post.password)
    is_official = False
    if settings.ADMIN_SECRET and post.admin_code == settings.ADMIN_SECRET:
        is_official = True

    db_post = models.Post(
        nickname=post.nickname,
        password_hash=hashed_password,
        title=post.title,
        content=post.content,
        link_url=post.link_url,
        source_name=post.source_name,
        is_official=is_official,
        thumbnail_url=post.thumbnail_url
    )
    db.add(db_post)
    db.commit()
    db.refresh(db_post)
    return db_post

def get_posts(db: Session, skip: int = 0, limit: int = 100):
    posts = db.query(models.Post).order_by(models.Post.is_official.desc(), models.Post.created_at.desc()).offset(skip).limit(limit).all()
    for p in posts:
        p.comment_count = len(p.comments)
    return posts

def get_post_by_id(db: Session, post_id: uuid.UUID):
    post = db.query(models.Post).filter(models.Post.id == post_id).first()
    if post:
        post.comment_count = len(post.comments)
    return post

def update_post(db: Session, post_id: uuid.UUID, post_update: schemas.PostUpdate):
    db_post = get_post_by_id(db, post_id)
    if not db_post:
        return None
    
    if not pwd_context.verify(post_update.password, db_post.password_hash):
        raise ValueError("Invalid password")
    
    is_official = db_post.is_official
    if settings.ADMIN_SECRET and post_update.admin_code:
        if post_update.admin_code == settings.ADMIN_SECRET:
            is_official = True
        else:
            is_official = False

    db_post.title = post_update.title
    db_post.content = post_update.content
    db_post.link_url = post_update.link_url
    db_post.source_name = post_update.source_name
    db_post.is_official = is_official
    db_post.thumbnail_url = post_update.thumbnail_url
    db.commit()
    db.refresh(db_post)
    return db_post

def delete_post(db: Session, post_id: uuid.UUID, password: str):
    db_post = get_post_by_id(db, post_id)
    if not db_post:
        return None
    
    if not pwd_context.verify(password, db_post.password_hash):
        raise ValueError("Invalid password")
    
    db.delete(db_post)
    db.commit()
    return True

# --- Comments CRUD ---

def create_comment(db: Session, post_id: uuid.UUID, comment: schemas.CommentCreate):
    hashed_password = pwd_context.hash(comment.password)
    db_comment = models.Comment(
        post_id=post_id,
        nickname=comment.nickname,
        password_hash=hashed_password,
        content=comment.content
    )
    db.add(db_comment)
    db.commit()
    db.refresh(db_comment)
    return db_comment

def get_comments_by_post(db: Session, post_id: uuid.UUID):
    return db.query(models.Comment).filter(models.Comment.post_id == post_id).order_by(models.Comment.created_at.asc()).all()

def get_comment_by_id(db: Session, comment_id: uuid.UUID):
    return db.query(models.Comment).filter(models.Comment.id == comment_id).first()

def delete_comment(db: Session, comment_id: uuid.UUID, password: str):
    db_comment = get_comment_by_id(db, comment_id)
    if not db_comment:
        return None
    
    if not pwd_context.verify(password, db_comment.password_hash):
        raise ValueError("Invalid password")
    
    db.delete(db_comment)
    db.commit()
    return True
