import os
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse
from dotenv import load_dotenv

load_dotenv()

S3_ENDPOINT = os.getenv("S3_ENDPOINT", "https://s3.twcstorage.ru").rstrip("/")
S3_BUCKET   = os.getenv("S3_BUCKET", "").strip()
CACHE_SEC   = int(os.getenv("CACHE_SEC", "300"))

app = FastAPI()

@app.get("/healthz")
def healthz():
    return PlainTextResponse("ok")

def build_s3_url(key: str) -> str:
    # ключ приходит как yyyy/mm/dd/uuid.ext
    return f"{S3_ENDPOINT}/{S3_BUCKET}/{key.lstrip('/')}"

def is_preview_client(req: Request) -> bool:
    """
    Определяем бота предпросмотра по User-Agent.
    НИКАКИХ body/видимых страниц не отдаём — только <head> с OG-метой.
    """
    ua = (req.headers.get("User-Agent") or "").lower()
    bots = [
        "telegrambot",         # Telegram
        "whatsapp",            # WhatsApp
        "twitterbot",          # Twitter / X
        "facebookexternalhit", # Facebook
        "vkshare",             # VK
        "viber",               # Viber
        "discordbot",          # Discord
        "okhttp"               # встречается у мессенджеров
    ]
    return any(b in ua for b in bots)

def render_meta_html(s3_url: str, ext: str) -> str:
    """
    Возвращаем минимальный документ: без body — только meta.
    Telegram возьмёт media по og:image / og:video и НИЧЕГО больше.
    """
    is_video = ext in (".mp4", ".webm", ".mov")
    head = [
        '<meta charset="utf-8">',
        '<meta name="robots" content="noindex,nofollow">',
        '<meta property="og:type" content="article">',
        '<meta property="twitter:card" content="summary_large_image">',
    ]
    if is_video:
        head.append(f'<meta property="og:video" content="{s3_url}">')
    else:
        head.append(f'<meta property="og:image" content="{s3_url}">')

    # Никаких title/desc! Никакого <body>!
    return "<!doctype html><html><head>" + "".join(head) + "</head></html>"

@app.get("/uploads/{path:path}")
async def preview(path: str, request: Request):
    # path ожидаем как yyyy/mm/dd/filename.ext
    s3_url = build_s3_url(path)
    ext = ""
    if "." in path:
        ext = "." + path.rsplit(".", 1)[-1].lower()

    if is_preview_client(request):
        html = render_meta_html(s3_url, ext)
        # только хэдеры и мета, кэш можно оставить
        return HTMLResponse(
            html,
            headers={"Cache-Control": f"public, max-age={CACHE_SEC}"}
        )
    else:
        # обычному браузеру — мгновенный 302 на S3 (там откроется чистая картинка/видео)
        return RedirectResponse(url=s3_url, status_code=302)