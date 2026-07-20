import asyncio
import sys
import os

# Set up paths
sys.path.insert(0, os.path.abspath("."))
from app.config import settings
import httpx

async def call_g():
    prompt = """반드시 아래의 순수 JSON 형식으로만 응답해야 하며, 응답 속도를 위해 최대한 간결하게 작성하세요.
{
  "comment": "메인으로 추천하는 1위 작품이 왜 위 취향과 잘 맞는지에 대한 친근하고 발랄한 추천 코멘트 (2문장 이내, 이모지 사용)",
  "mangas": [
    { "id": "ai_1", "title": "1위 메인 만화 제목", "genre": "장르", "reason": "이 작품을 추천하는 이유 (1문장, 이모지 포함)", "otts": ["넷플릭스", "라프텔"] }
  ]
}
"""
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": settings.GEMINI_API_KEY,
    }
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "maxOutputTokens": 4000,
            "temperature": 0.7
        }
    }
    
    async with httpx.AsyncClient(timeout=20.0) as client:
        # Use the lite model
        response = await client.post("https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-lite-latest:generateContent", headers=headers, json=payload)
        print("Status Code:", response.status_code)
        print("Response:", response.text)

asyncio.run(call_g())
