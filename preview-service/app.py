# app.py — MiniApp + проверки подписки + прокси /uploads/* к S3

import os
import mimetypes
import json, hmac, hashlib
from pathlib import Path
import sqlite3
from typing import Optional, Dict, Any
from starlette.staticfiles import StaticFiles

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse, FileResponse, Response, HTMLResponse, RedirectResponse
from starlette.requests import Request

# ──────────────────────────────────────────────────────────────────────────────
# Инициализация
# ──────────────────────────────────────────────────────────────────────────────

# Загружаем .env из текущей папки
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

BOT_TOKEN   = os.getenv("BOT_TOKEN", "").strip()
WEBAPP_HOST = os.getenv("WEBAPP_HOST", "https://prizeme.ru").rstrip("/")
DB_PATH     = Path(__file__).with_name("bot.db")

S3_ENDPOINT = os.getenv("S3_ENDPOINT", "https://s3.twcstorage.ru").rstrip("/")
S3_BUCKET   = os.getenv("S3_BUCKET", "").strip()
CACHE_SEC   = int(os.getenv("CACHE_SEC", "300"))

app = FastAPI()

# === Mini App: единый способ отдачи фронта ===
from pathlib import Path
from fastapi import Request
from fastapi.responses import FileResponse, Response
from starlette.staticfiles import StaticFiles

# 1) Точные пути
BASE_DIR = Path(__file__).resolve().parent           # preview-service/
WEBAPP_DIR = BASE_DIR / "webapp"                     # preview-service/webapp/
INDEX_HTML = WEBAPP_DIR / "index.html"               # preview-service/webapp/index.html

# 3) Статика Mini App (JS/CSS/картинки)
#    Будем подключать их относительными путями из index.html. 
#    Например: <link href="/miniapp-static/styles.css"> и <script src="/miniapp-static/app.js">
app.mount(
    "/miniapp-static",
    StaticFiles(directory=str(WEBAPP_DIR), html=False),
    name="miniapp-static",
)

# 4) Сам index.html + catch-all для всех подпутей
@app.get("/miniapp", include_in_schema=False)
@app.get("/miniapp/", include_in_schema=False)
@app.get("/miniapp/{_subpath:path}", include_in_schema=False)
async def miniapp_entry(_subpath: str | None = None):
    # Для SPA всегда отдаём один и тот же index.html,
    # а статику берём по /miniapp-static/*
    return FileResponse(str(INDEX_HTML))

# === /Mini App ===

@app.middleware("http")
async def _head_as_get(request: Request, call_next):
    if request.method != "HEAD":
        return await call_next(request)

    # Притворяемся GET, чтобы роуты/статик отработали
    request.scope["method"] = "GET"
    resp = await call_next(request)

    # Если нижний слой вернул 404/405 (нет GET-хендлера или не принял метод) —
    # всё равно отвечаем 200 OK для HEAD, чтобы nginx не падал в 502.
    if resp.status_code in (404, 405):
        return Response(status_code=200, headers={"content-length": "0"})

    # Иначе — отдадим те же заголовки/статус, но пустое тело (корректно для HEAD)
    headers = dict(resp.headers)
    headers["content-length"] = "0"
    return Response(status_code=resp.status_code, headers=headers)


# ──────────────────────────────────────────────────────────────────────────────
# Вспомогательные функции
# ──────────────────────────────────────────────────────────────────────────────

def _db():
    conn = sqlite3.connect(DB_PATH.as_posix())
    conn.row_factory = sqlite3.Row
    return conn

def _status_member_ok(status: str) -> bool:
    return status in ("member", "administrator", "creator")

def _tg_check_webapp_initdata(init_data: str) -> Optional[Dict[str, Any]]:
    """
    Валидируем initData из Telegram WebApp по алгоритму из доки.
    Возвращаем словарь parsed (tgWebAppData) либо None.
    """
    try:
        # init_data: "key1=value1&key2=value2..."
        data = dict([pair.split("=", 1) for pair in init_data.split("&")])
        hash_recv = data.pop("hash", "")
        data_check_string = "\n".join([f"{k}={v}" for k, v in sorted(data.items())])
        secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        h = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        if h != hash_recv:
            return None

        # внутри есть поле "user" с json
        user_json = data.get("user")
        user = json.loads(user_json) if user_json else None
        data["user_parsed"] = user
        return data
    except Exception:
        return None

def build_s3_url(key: str) -> str:
    return f"{S3_ENDPOINT}/{S3_BUCKET}/{key.lstrip('/')}"

def is_bot_request(request: Request) -> bool:
    ua = request.headers.get("user-agent", "").lower()
    return any(b in ua for b in ("telegrambot", "twitterbot", "facebookexternalhit", "linkedinbot"))


# ──────────────────────────────────────────────────────────────────────────────
# Служебные эндпоинты
# ──────────────────────────────────────────────────────────────────────────────

@app.api_route("/health", methods=["GET", "HEAD"])
async def health_any(request: Request):
    # Для GET вернём тело "ok", для HEAD — пустое тело с теми же заголовками/статусом
    if request.method == "HEAD":
        return Response(status_code=200, media_type="text/plain")
    return PlainTextResponse("ok")

# ──────────────────────────────────────────────────────────────────────────────
# Mini-App (бэкенд) — проверка подписок и выдача билета
# ──────────────────────────────────────────────────────────────────────────────

@app.post("/api/check-join")
async def api_check_join(req: Request):
    """
    Тело: { "gid": "<int>", "init_data": "<Telegram WebApp initData>" }
    Алгоритм:
      1) валидируем init_data;
      2) достаём user_id;
      3) читаем чаты розыгрыша из SQLite;
      4) через Bot API проверяем подписку;
      5) если всё ок — создаём/возвращаем билет (entries).
    """
    if not BOT_TOKEN:
        return PlainTextResponse("BOT_TOKEN is not configured", status_code=500)

    body = await req.json()
    gid = int(body.get("gid") or 0)
    init_data = body.get("init_data") or ""

    parsed = _tg_check_webapp_initdata(init_data)
    if not parsed or not parsed.get("user_parsed"):
        return Response(content=json.dumps({"ok": False, "reason": "bad_initdata"}), media_type="application/json")

    user = parsed["user_parsed"]
    user_id = int(user["id"])

    # читаем розыгрыш и каналы
    with _db() as db:
        row_g = db.execute("SELECT internal_title FROM giveaways WHERE id=?", (gid,)).fetchone()
        if not row_g:
            return Response(content=json.dumps({"ok": False, "reason": "not_found"}), media_type="application/json")

        rows = db.execute("""
            SELECT gc.chat_id, gc.title, oc.username
            FROM giveaway_channels gc
            LEFT JOIN organizer_channels oc ON oc.id = gc.channel_id
            WHERE gc.giveaway_id=?
        """, (gid,)).fetchall()
        chats = [{"chat_id": r["chat_id"], "title": r["title"], "username": r["username"]} for r in rows]

    # проверяем подписку
    need = []
    async with httpx.AsyncClient(timeout=15.0) as client:
        for ch in chats:
            try:
                url = f"https://api.telegram.org/bot{BOT_TOKEN}/getChatMember"
                params = {"chat_id": ch["chat_id"], "user_id": user_id}
                r = await client.get(url, params=params)
                js = r.json()
                st = js.get("result", {}).get("status")
                ok = _status_member_ok(st or "")
            except Exception:
                ok = False
            if not ok:
                link = f"https://t.me/{ch['username']}" if ch.get("username") else None
                need.append({"title": ch["title"], "username": ch.get("username"), "url": link})

    if need:
        return Response(content=json.dumps({"ok": False, "need": need}), media_type="application/json")

    # подписан везде → выдаем/возвращаем билет
    code = None
    with _db() as db:
        row_e = db.execute("SELECT ticket_code FROM entries WHERE giveaway_id=? AND user_id=?", (gid, user_id)).fetchone()
        if row_e:
            code = row_e["ticket_code"]
        else:
            import random, string
            ALPH = string.ascii_uppercase + string.digits
            # пробуем несколько раз на случай коллизии
            for _ in range(8):
                try_code = "".join(random.choices(ALPH, k=6))
                try:
                    db.execute(
                        "INSERT INTO entries(giveaway_id, user_id, ticket_code, prelim_ok, prelim_checked_at) "
                        "VALUES (?, ?, ?, 1, strftime('%Y-%m-%d %H:%M:%f','now'))",
                        (gid, user_id, try_code)
                    )
                    db.commit()
                    code = try_code
                    break
                except Exception:
                    continue

    title = row_g["internal_title"]
    return Response(content=json.dumps({"ok": True, "ticket": code, "title": title}), media_type="application/json")


# ──────────────────────────────────────────────────────────────────────────────
# Прокси /uploads/* → S3 (200 OK, без редиректа) + OG для ботов
# ──────────────────────────────────────────────────────────────────────────────

@app.api_route("/uploads/{path:path}", methods=["GET", "HEAD"])
async def uploads(path: str, request: Request):
    s3_url = build_s3_url(path)
    mime_guess = mimetypes.guess_type(path)[0] or "application/octet-stream"

    # Telegram/Twitter парсеры — отдаем OG HTML
    if is_bot_request(request):
        html = f"""<!DOCTYPE html>
<html><head>
  <meta property="og:type" content="article"/>
  <meta property="og:title" content="PrizeMe | Giveaway"/>
  <meta property="og:description" content="Participate and win!"/>
  <meta property="og:image" content="{s3_url}"/>
  <meta name="twitter:card" content="summary_large_image"/>
</head><body></body></html>"""
        return HTMLResponse(content=html, headers={"Cache-Control": f"public, max-age={CACHE_SEC}"})

    # Обычный пользователь — проксируем файл
    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        if request.method == "HEAD":
            r = await client.head(s3_url)
            content = b""
        else:
            r = await client.get(s3_url)
            content = r.content

    ctype = r.headers.get("content-type", mime_guess)
    resp = Response(
        content=content if request.method == "GET" else b"",
        status_code=r.status_code if r.status_code < 400 else 404,
        media_type=ctype,
    )
    if "content-length" in r.headers:
        resp.headers["Content-Length"] = r.headers["content-length"]
    resp.headers["Cache-Control"] = f"public, max-age={CACHE_SEC}"
    resp.headers["X-Proxy-From"] = s3_url
    return resp

# ──────────────────────────────────────────────────────────────────────────────
# Fallback: принять ЛЮБОЙ HEAD на любом пути → 200 OK без тела
# Это на случай, если до конкретного роутинга HEAD не «доезжает».
# ──────────────────────────────────────────────────────────────────────────────
@app.api_route("/{_path:path}", methods=["HEAD"])
async def _any_head_ok(_path: str):
    # Отдаём 200 и пустое тело (корректное поведение для HEAD)
    return Response(status_code=200)

# ===================== (NEW) Mini-App serving =====================
from pathlib import Path
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# Папка со статиками мини-аппа (index.html, app.js, styles.css)
WEBAPP_DIR = Path(__file__).parent / "webapp"

# Статика без кеша (чтобы правки виделись сразу)
class _NoCacheStatic(StaticFiles):
    async def get_response(self, path, scope):
        resp = await super().get_response(path, scope)
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        return resp

# Отдаём JS/CSS с /miniapp-static/
app.mount(
    "/miniapp-static",
    _NoCacheStatic(directory=str(WEBAPP_DIR), html=False),
    name="miniapp-static",
)

def _miniapp_index() -> FileResponse:
    """Один и тот же index.html для любых подпутей /miniapp/..."""
    return FileResponse(
        path=str(WEBAPP_DIR / "index.html"),
        media_type="text/html",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )

# /miniapp  → index.html
@app.api_route("/miniapp", methods=["GET", "HEAD"])
async def __miniapp_root():
    return _miniapp_index()

# /miniapp/что-угодно  → тот же index.html
@app.api_route("/miniapp/{path:path}", methods=["GET", "HEAD"])
async def __miniapp_any(path: str):
    return _miniapp_index()
# ================== / (NEW) Mini-App serving ======================