# app.py  — минимальный превью-сервис
import os
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse
from dotenv import load_dotenv

# env
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

S3_ENDPOINT = os.getenv("S3_ENDPOINT", "https://s3.twcstorage.ru").rstrip("/")
S3_BUCKET   = os.getenv("S3_BUCKET", "").strip()
CACHE_SEC   = int(os.getenv("CACHE_SEC", "300"))

app = FastAPI()

def build_s3_url(key: str) -> str:
    # ключ приходит как yyyy/mm/dd/uuid.ext
    return f"{S3_ENDPOINT}/{S3_BUCKET}/{key.lstrip('/')}"

# Определяем, что это бот предпросмотра (Telegram, Twitter, VK, WhatsApp, Discord)
BOT_UA = ("telegrambot", "twitterbot", "facebookexternalhit", "vkshare", "whatsapp", "discordbot", "okhttp")

def is_preview_client(req: Request) -> bool:
    ua = (req.headers.get("User-Agent") or "").lower()
    return any(b in ua for b in BOT_UA)

def head_only_html(s3_url: str, ext: str) -> str:
    """
    Возвращаем ТОЛЬКО <head> с OG-тегами.
    Никаких заголовков, стилей и видимого контента в <body>.
    """
    tags = []
    # Для видео Telegram использует og:video, для изображений — og:image
    if ext in (".mp4", ".webm", ".mov"):
        tags.append(f'<meta property="og:video" content="{s3_url}">')
    else:
        tags.append(f'<meta property="og:image" content="{s3_url}">')
    tags.append('<meta name="twitter:card" content="summary_large_image">')
    return "<!doctype html><html><head>" + "".join(tags) + "</head><body></body></html>"

@app.get("/healthz")
def healthz():
    return PlainTextResponse("ok")

@app.get("/uploads/{path:path}")
async def preview(path: str, request: Request):
    """
    Ботам предпросмотра — пустая страница с OG-тегами.
    Обычным пользователям — мгновенный 302 на сам файл в S3,
    чтобы в браузере открывался ТОЛЬКО файл (jpg/png/mp4 и т.п.).
    """
    key = path
    s3_url = build_s3_url(key)
    ext = ("." + path.rsplit(".", 1)[-1].lower()) if "." in path else ""

    if is_preview_client(request):
        html = head_only_html(s3_url, ext)
        return HTMLResponse(html, headers={"Cache-Control": f"public, max-age={CACHE_SEC}"})
    else:
        return RedirectResponse(url=s3_url, status_code=302)