# app.py — минимальный редирект-сервис без HTML-страниц
import os
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, PlainTextResponse
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

S3_ENDPOINT = os.getenv("S3_ENDPOINT", "https://s3.twcstorage.ru").rstrip("/")
S3_BUCKET   = os.getenv("S3_BUCKET",   "").strip()
CACHE_SEC   = int(os.getenv("CACHE_SEC", "300"))

app = FastAPI()

def build_s3_url(key: str) -> str:
    # ключ приходит как yyyy/mm/dd/uuid.ext
    return f"{S3_ENDPOINT}/{S3_BUCKET}/{key.lstrip('/')}"

@app.get("/healthz")
def healthz():
    # помогает понять, КАКОЙ файл сейчас крутится
    return PlainTextResponse(f"ok | {__file__}")

@app.api_route("/uploads/{path:path}", methods=["GET", "HEAD"])
async def uploads(path: str, request: Request):
    s3_url = build_s3_url(path)
    # Всегда — 302 на S3: в браузере открывается ЧИСТАЯ картинка/видео,
    # у Telegram тоже будет только медиа, без заголовков/описаний.
    resp = RedirectResponse(url=s3_url, status_code=302)
    resp.headers["Cache-Control"] = f"public, max-age={CACHE_SEC}"
    # Отладочный заголовок — чтобы убедиться, что ответил именно этот файл
    resp.headers["X-App-Path"] = __file__
    return resp