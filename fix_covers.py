import asyncio
import httpx
from app.database import SessionLocal
from app.models import Manga
from app.config import settings

async def fetch_cover(client, title):
    API_KEY = settings.ALADIN_API_KEY
    if not API_KEY:
        print("No API Key")
        return None

    # Fallback logic simplified from frontend
    for fallback in [0, 1, 2]:
        query_type = 'Title' if fallback == 0 else 'Keyword'
        search_query = title
        if fallback == 2:
            import re
            search_query = re.split(r'[-:(]', title)[0].strip()
            if not search_query:
                search_query = title

        url = f"https://www.aladin.co.kr/ttb/api/ItemSearch.aspx"
        params = {
            "ttbkey": API_KEY,
            "Query": search_query,
            "QueryType": query_type,
            "SearchTarget": "Book",
            "SubTarget": "Comic",
            "Sort": "SalesPoint",
            "output": "js",
            "Version": "20131101",
            "Cover": "Big",
            "MaxResults": 20
        }
        try:
            resp = await client.get(url, params=params, timeout=10.0)
            resp.raise_for_status()
            data = resp.json()
            items = data.get("item", [])
            if items:
                # 1. Exact match
                import re
                escaped = re.escape(title)
                base_regex = re.compile(f"^{escaped}(\\s*(1|01)(권|화)?)?$", re.IGNORECASE)
                best_match = next((i for i in items if base_regex.match(i.get("title", "").strip())), None)
                
                # 2. Shortest match
                if not best_match:
                    matches = [i for i in items if title in i.get("title", "")]
                    if matches:
                        best_match = min(matches, key=lambda x: len(x.get("title", "")))
                    else:
                        best_match = items[0]
                
                return best_match.get("cover")
        except Exception as e:
            print(f"Error fetching {title} (level {fallback}): {e}")
    return None

async def main():
    db = SessionLocal()
    try:
        # Get all mangas with invalid image_url
        mangas = db.query(Manga).filter(~Manga.image_url.startswith("http")).all()
        print(f"Found {len(mangas)} mangas needing cover updates.")

        async with httpx.AsyncClient() as client:
            for m in mangas:
                print(f"Fetching cover for '{m.title}'...")
                cover_url = await fetch_cover(client, m.title)
                if cover_url:
                    print(f"  -> Found: {cover_url}")
                    m.image_url = cover_url
                    db.commit()
                else:
                    print("  -> Not found.")
                await asyncio.sleep(0.2) # sleep to prevent rate limiting
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(main())
