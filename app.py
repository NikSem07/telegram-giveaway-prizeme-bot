import os, html
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse
from dotenv import load_dotenv

# ---- env ----
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

S3_ENDPOINT = os.getenv("S3_ENDPOINT", "https://s3.twcstorage.ru").rstrip("/")
S3_BUCKET   = os.getenv("S3_BUCKET", "").strip()
CACHE_SEC   = int(os.getenv("CACHE_SEC", "300"))
DEF_TITLE   = os.getenv("DEFAULT_TITLE", "PrizeMe | Giveaway")
DEF_DESC    = os.getenv("DEFAULT_DESC", "Participate and win!")

app = FastAPI()

# ---- helpers ----
def build_s3_url(key: str) -> str:
    # key приходит как yyyy/mm/dd/uuid.ext
    return f"{S3_ENDPOINT}/{S3_BUCKET}/{key.lstrip('/')}"

def is_preview_client(req: Request) -> bool:
    """
    Определяем бота предпросмотра по User-Agent.
    Никакой «видимой» страницы не отдаём — только <head> с OG-тегами.
    """
    ua = (req.headers.get("User-Agent") or "").lower()
    bots = [
        "telegrambot",          # Telegram
        "whatsapp",             # WhatsApp
        "twitterbot",           # Twitter / X
        "facebookexternalhit",  # Facebook
        "vkshare",              # VK
        "viber",                # Viber
        "discordbot",           # Discord
        "okhttp"                # иногда встречается у мессенджеров
    ]
    return any(b in ua for b in bots)

def render_meta_html(title: str, desc: str, s3_url: str, ext: str) -> str:
    """
    Возвращаем МИНИМАЛЬНЫЙ документ без тела — только мета-теги.
    Никаких текстов, ссылок, рамок и т.п.
    """
    t = html.escape((title or DEF_TITLE)[:220])
    d = html.escape((desc  or DEF_DESC )[:300])

    # базовые OG
    head = [
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f'<meta property="og:title" content="{t}">',
        f'<meta property="og:description" content="{d}">',
        f'<meta property="og:image" content="{s3_url}">',
        '<meta name="twitter:card" content="summary_large_image">',
        f'<link rel="canonical" href="{s3_url}">'
    ]

    # если видео — добавим og:video (Telegram его понимает)
    if ext in ("mp4", "webm", "mov"):
        head.append(f'<meta property="og:video" content="{s3_url}">')
        head.append('<meta property="og:type" content="video.other">')
    else:
        head.append('<meta property="og:type" content="article">')

    # БЕЗ body-контента.
    return "<!doctype html><html><head>" + "".join(head) + "</head><body></body></html>"

# ---- routes ----
@app.get("/healthz")
def healthz() -> PlainTextResponse:
    return PlainTextResponse("ok")

@app.get("/uploads/{path:path}")
async def preview(path: str, request: Request):
    """
    /uploads/yyyy/mm/dd/uuid.ext?t=...&d=...
    - для ботов предпросмотра: отдаём только мета-теги (OG) в <head>
    - для обычных браузеров: 302 на «чистый» файл из S3
    """
    # параметры из ссылки (используем ТОЛЬКО в мета-тегах)
    title = request.query_params.get("t") or DEF_TITLE
    desc  = request.query_params.get("d") or DEF_DESC

    key = path.strip("/")
    ext = key.rsplit(".", 1)[-1].lower() if "." in key else ""
    s3_url = build_s3_url(key)

    if is_preview_client(request):
        html_doc = render_meta_html(title, desc, s3_url, ext)
        # никаких видимых блоков; кэшируем
        return HTMLResponse(
            html_doc,
            headers={"Cache-Control": f"public, max-age={CACHE_SEC}"}
        )

    # обычному пользователю — мгновенный редирект на сам файл
    return RedirectResponse(url=s3_url, status_code=302)