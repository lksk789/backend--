from app.database import SessionLocal
from app.models import AiCurationCache

db = SessionLocal()
db.query(AiCurationCache).filter(AiCurationCache.theme_keyword.like('recommend_%')).delete(synchronize_session=False)
db.commit()
print("Cache cleared")
