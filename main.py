"""FinNews AI - Financial News Simplifier (FastAPI backend)."""
import asyncio
import json
import os
from pathlib import Path

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from groq import Groq
from pydantic import BaseModel, Field

load_dotenv()

NEWS_API_KEY = os.getenv("NEWS_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MODEL = "llama-3.3-70b-versatile"
NEWS_URL = "https://newsapi.org/v2/top-headlines"
CATEGORIES = {"business", "technology", "general"}
STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="FinNews AI", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten to your frontend origin in production
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

SYSTEM_PROMPT = """You are a financial news explainer for people with no finance background.
Rewrite the article in plain language. Rules:
- Never invent facts, numbers, or names. Use only what the article gives you.
- Explain any jargon in one short sentence.
- Keep the summary under 80 words.
- If the article text is too thin to summarize, say so in the summary.
Respond with JSON only, using exactly these keys:
{
  "plain_headline": string,
  "summary": string,
  "key_takeaways": [string, string, string],
  "why_it_matters": string,
  "jargon": [{"term": string, "meaning": string}]
}"""


class SimplifyRequest(BaseModel):
    title: str = Field(..., min_length=3, max_length=300)
    text: str = Field(..., min_length=20, max_length=8000)


# ---------- Services ----------
def fetch_news(category: str, count: int) -> list[dict]:
    if not NEWS_API_KEY:
        raise HTTPException(500, "NEWS_API_KEY is not set. Add it to your .env file.")
    try:
        r = requests.get(
            NEWS_URL,
            headers={"X-Api-Key": NEWS_API_KEY},
            params={"category": category, "language": "en", "pageSize": count * 2},
            timeout=15,
        )
    except requests.RequestException as e:
        raise HTTPException(502, f"Could not reach NewsAPI: {e}")
    if r.status_code != 200:
        raise HTTPException(502, f"NewsAPI error: {r.json().get('message', r.status_code)}")

    articles = []
    for a in r.json().get("articles", []):
        # Validation + filtering: drop removed/empty items
        if not a.get("title") or a["title"] == "[Removed]":
            continue
        body = " ".join(filter(None, [a.get("description"), a.get("content")]))
        if len(body) < 40:
            continue
        articles.append(
            {
                "title": a["title"],
                "source": (a.get("source") or {}).get("name", "Unknown"),
                "url": a.get("url"),
                "image": a.get("urlToImage"),
                "published_at": a.get("publishedAt"),
                "text": body,
            }
        )
        if len(articles) == count:
            break
    return articles


def simplify_sync(title: str, text: str) -> dict:
    if not groq_client:
        raise HTTPException(500, "GROQ_API_KEY is not set. Add it to your .env file.")
    try:
        res = groq_client.chat.completions.create(
            model=MODEL,
            temperature=0.3,
            max_tokens=700,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Title: {title}\n\nArticle:\n{text}"},
            ],
        )
        return json.loads(res.choices[0].message.content)
    except json.JSONDecodeError:
        raise HTTPException(502, "The model returned an unreadable response. Try again.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"Groq API error: {e}")


async def simplify_safe(article: dict) -> dict:
    """Simplify one article; a failure on one card never breaks the whole batch."""
    try:
        article["ai"] = await asyncio.to_thread(simplify_sync, article["title"], article["text"])
        article["error"] = None
    except HTTPException as e:
        article["ai"], article["error"] = None, e.detail
    article.pop("text", None)
    return article


# ---------- Routes ----------
@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "model": MODEL,
        "news_api_configured": bool(NEWS_API_KEY),
        "groq_configured": bool(GROQ_API_KEY),
    }


@app.get("/api/news")
def news(category: str = "business", count: int = Query(5, ge=1, le=10)):
    if category not in CATEGORIES:
        raise HTTPException(400, f"category must be one of {sorted(CATEGORIES)}")
    return {"articles": fetch_news(category, count)}


@app.post("/api/simplify")
async def simplify(body: SimplifyRequest):
    return await asyncio.to_thread(simplify_sync, body.title, body.text)


@app.get("/api/fetch-and-simplify")
async def fetch_and_simplify(category: str = "business", count: int = Query(5, ge=1, le=10)):
    if category not in CATEGORIES:
        raise HTTPException(400, f"category must be one of {sorted(CATEGORIES)}")
    articles = await asyncio.to_thread(fetch_news, category, count)
    if not articles:
        raise HTTPException(404, "No usable articles found right now. Try another category.")
    results = await asyncio.gather(*(simplify_safe(a) for a in articles))
    return {"articles": results}


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")
