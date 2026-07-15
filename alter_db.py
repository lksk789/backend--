import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.database import engine

def alter_db():
    print("Altering mangas table to add otts column...")
    try:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE mangas ADD COLUMN otts VARCHAR(200) DEFAULT ''"))
            conn.commit()
            print("Successfully added otts column.")
    except Exception as e:
        print("Error altering table, it might already exist:", e)

if __name__ == "__main__":
    alter_db()
