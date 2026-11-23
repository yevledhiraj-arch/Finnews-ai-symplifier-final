# FinNews AI - Financial News Simplifier

FastAPI + NewsAPI + Groq (Llama 3.3 70B Versatile) + vanilla HTML/CSS/JS.

## Setup
```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # then add your NEWS_API_KEY and GROQ_API_KEY
uvicorn main:app --reload
```
Open http://127.0.0.1:8000 and click **Fetch & Simplify**.

## Endpoints
| Method | Path | Purpose |
|---|---|---|
| GET | /api/health | Service status and key configuration check |
| GET | /api/news?category=business&count=5 | Fetch and filter articles only |
| POST | /api/simplify | Simplify `{title, text}` you supply |
| GET | /api/fetch-and-simplify | Full pipeline (what the UI calls) |
| GET | /docs | Interactive Swagger docs |

## Notes
- Keys live in `.env` only. The browser never sees them.
- NewsAPI's free tier truncates article `content`, so summaries use title + description + the snippet.
- NewsAPI's free plan only allows requests from localhost during development.
- Each article is simplified independently, so one failure doesn't break the page.
