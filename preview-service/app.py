# app.py — proxy /uploads/* к S3 без редиректа (200 OK + image/*)
import os
import mimetypes
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, Response, HTMLResponse
from dotenv import load_dotenv
import httpx

# Загружаем .env
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

S3_ENDPOINT = os.getenv("S3_ENDPOINT", "https://s3.twcstorage.ru").rstrip("/")
S3_BUCKET = os.getenv("S3_BUCKET", "").strip()
CACHE_SEC = int(os.getenv("CACHE_SEC", "300"))

app = FastAPI()

# ---------- вспомогательные функции ----------
def build_s3_url(key: str) -> str:
    """Формируем полный URL к файлу в S3"""
    return f"{S3_ENDPOINT}/{S3_BUCKET}/{key.lstrip('/')}"

def is_bot_request(request: Request) -> bool:
    """Определяем, что это запрос от TelegramBot / TwitterBot"""
    ua = request.headers.get("user-agent", "").lower()
    return any(bot in ua for bot in ["telegrambot", "twitterbot", "facebookexternalhit", "linkedinbot"])

# ---------- маршруты ----------
@app.get("/healthz")
async def healthz():
    return PlainTextResponse(f"ok | {__file__}")

@app.api_route("/uploads/{path:path}", methods=["GET", "HEAD"])
async def uploads(path: str, request: Request):
    """
    Для TelegramBot и других ботов возвращаем HTML с OG-тегами.
    Для обычных браузеров — отдаём файл напрямую (проксирование без редиректа).
    """
    s3_url = build_s3_url(path)
    mime_guess = mimetypes.guess_type(path)[0] or "application/octet-stream"

    # Если запрос делает Telegram (бот-парсер) — отдаем OG HTML
    if is_bot_request(request):
        html = f"""<!DOCTYPE html>
        <html>
          <head>
            <meta property="og:type" content="article"/>
            <meta property="og:title" content="PrizeMe | Giveaway"/>
            <meta property="og:description" content="Participate and win!"/>
            <meta property="og:image" content="{s3_url}"/>
            <meta name="twitter:card" content="summary_large_image"/>
          </head>
          <body></body>
        </html>"""
        return HTMLResponse(content=html, headers={"Cache-Control": f"public, max-age={CACHE_SEC}"})

    # Иначе — обычный пользователь → проксируем файл (200 OK, без 302)
    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        if request.method == "HEAD":
            r = await client.head(s3_url)
            content = b""
        else:
            r = await client.get(s3_url)
            content = r.content

    ctype = r.headers.get("content-type", mime_guess)

    # Формируем ответ
    response = Response(
        content=content if request.method == "GET" else b"",
        status_code=r.status_code if r.status_code < 400 else 404,
        media_type=ctype,
    )

    # Добавляем нужные заголовки
    if "content-length" in r.headers:
        response.headers["Content-Length"] = r.headers["content-length"]
    response.headers["Cache-Control"] = f"public, max-age={CACHE_SEC}"
    response.headers["X-Proxy-From"] = s3_url
    response.headers["X-App-Path"] = __file__

    return response