import os
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse
from dotenv import load_dotenv

# --- env ---
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

S3_ENDPOINT = os.getenv("S3_ENDPOINT", "https://s3.twcstorage.ru").rstrip("/")
S3_BUCKET   = os.getenv("S3_BUCKET", "").strip()
CACHE_SEC   = int(os.getenv("CACHE_SEC", "300"))

app = FastAPI()

# ---- helpers ----
def build_s3_url(key: str) -> str:
    # ключ приходит как yyyy/mm/dd/uuid.ext
    return f"{S3_ENDPOINT}/{S3_BUCKET}/{key.lstrip('/')}"

def is_preview_client(req: Request) -> bool:
    """
    Определяем бота предпросмотра по User-Agent.
    Браузерам ничего "видимого" не отдаём — только 302 на S3.
    """
    ua = (req.headers.get("User-Agent") or "").lower()
    bots = [
        "telegrambot",        # Telegram
        "whatsapp",           # WhatsApp
        "twitterbot",         # Twitter / X
        "facebookexternalhit",# Facebook
        "vkshare",            # VK
        "viber",              # Viber
        "discordbot",         # Discord
        "okhttp"              # иногда встречается у мессенджеров
    ]
    return any(b in ua for b in bots)

def render_meta_head(title: str, img_url: str, ext: str) -> str:
    """
    Возвращаем минимальный HTML с OG-мета. Никакого видимого тела.
    """
    og_type = "video.other" if ext in (".mp4", ".webm", ".mov") else "article"
    tags = [
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f'<meta property="og:type" content="{og_type}">',
        f'<meta property="og:title" content="{title}">',
        f'<meta property="og:image" content="{img_url}">',
        f'<meta property="twitter:card" content="summary_large_image">',
    ]
    # Боту достаточно <head>. Тело пустое.
    return "<!doctype html><html><head>" + "".join(tags) + "</head></html>"

@app.get("/healthz")
def healthz():
    return PlainTextResponse("ok")

@app.get("/uploads/{path:path}")
async def preview(path: str, request: Request):
    """
    Мы ждём путь вида yyyy/mm/dd/filename.ext
    - Боты получают head с OG-тегами (без тела)
    - Браузеры получают 302 на S3 (и уже там — сама картинка/видео)
    """
    key = (path or "").lstrip("/")
    ext = "." + key.split(".")[-1].lower() if "." in key else ""
    s3_url = build_s3_url(key)

    if is_preview_client(request):
        # только мета, без видимого контента
        title = ""  # пустой title, чтобы Telegram показал только картинку
        html = render_meta_head(title=title, img_url=s3_url, ext=ext)
        return HTMLResponse(html, headers={"Cache-Control": f"public, max-age={CACHE_SEC}"})
    else:
        # обычные браузеры → мгновенный редирект на S3
        return RedirectResponse(url=s3_url, status_code=302)