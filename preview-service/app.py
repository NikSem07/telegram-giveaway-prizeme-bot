# app.py — proxy /uploads/* к S3 без редиректа (200 OK + image/*)
import os
import mimetypes
from fastapi import FastAPI, Request, Response
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv
import httpx

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

S3_ENDPOINT = os.getenv("S3_ENDPOINT", "https://s3.twcstorage.ru").rstrip("/")
S3_BUCKET   = os.getenv("S3_BUCKET", "").strip()
CACHE_SEC   = int(os.getenv("CACHE_SEC", "300"))

app = FastAPI()
client = httpx.AsyncClient(follow_redirects=True, timeout=20.0)

def build_s3_url(key: str) -> str:
    return f"{S3_ENDPOINT}/{S3_BUCKET}/{key.lstrip('/')}"

@app.get("/healthz")
async def healthz():
    return PlainTextResponse(f"ok | {__file__}")

@app.api_route("/uploads/{path:path}", methods=["GET", "HEAD"])
async def uploads(path: str, request: Request):
    # 1) определим MIME по расширению (на случай если S3 не вернёт)
    guess = mimetypes.guess_type(path)[0] or "application/octet-stream"

    # 2) тянем байты из S3 (мы — прокси, никаких 302 наружу)
    s3_url = build_s3_url(path)
    # HEAD -> делаем HEAD к S3, GET -> делаем GET
    method = request.method.upper()
    if method == "HEAD":
        r = await client.head(s3_url)
        content = b""
    else:
        r = await client.get(s3_url)

        # если S3 всё-таки вернул редирект/HTML, мы уже follow_redirects=True, получим контент
        content = r.content

    # 3) берём тип из S3, но подстрахуем нашим guess
    ctype = r.headers.get("Content-Type", guess)

    # 4) 200 OK наружу, без Location, только байты файла
    resp = Response(
        content=content if request.method == "GET" else b"",
        status_code=r.status_code if r.status_code < 400 else 404,
        media_type=ctype,
    )
    # полезные заголовки
    if "Content-Length" in r.headers:
        resp.headers["Content-Length"] = r.headers["Content-Length"]
    resp.headers["Cache-Control"] = f"public, max-age={CACHE_SEC}"
    resp.headers["X-Proxy-From"] = s3_url
    resp.headers["X-App-Path"] = __file__
    return resp