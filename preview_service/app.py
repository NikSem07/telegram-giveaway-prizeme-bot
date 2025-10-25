# app.py — MiniApp + проверки подписки + прокси /uploads/* к S3

import os
import time
import mimetypes
import json, hmac, hashlib
from pathlib import Path
import sqlite3
from typing import Optional, Dict, Any, List
from starlette.staticfiles import StaticFiles
from fastapi.staticfiles import StaticFiles

import httpx
from httpx import AsyncClient
from dotenv import load_dotenv, find_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, FileResponse, Response, HTMLResponse, RedirectResponse, JSONResponse
from starlette.requests import Request

# ──────────────────────────────────────────────────────────────────────────────
# Инициализация
# ──────────────────────────────────────────────────────────────────────────────

# Загружаем .env из текущей папки
load_dotenv(find_dotenv(), override=False)

BOT_TOKEN   = os.getenv("BOT_TOKEN", "").strip()
WEBAPP_HOST = os.getenv("WEBAPP_HOST", "https://prizeme.ru").rstrip("/")
# БД: берём из .env, иначе по умолчанию ../tgbot/bot.db
DB_PATH     = Path(os.getenv("DB_PATH") or (Path(__file__).resolve().parents[1] / "tgbot" / "bot.db")).resolve()

S3_ENDPOINT = os.getenv("S3_ENDPOINT", "https://s3.twcstorage.ru").rstrip("/")
S3_BUCKET   = os.getenv("S3_BUCKET", "").strip()
CACHE_SEC   = int(os.getenv("CACHE_SEC", "300"))

app = FastAPI()

OT_TOKEN = os.getenv("BOT_TOKEN")
MEDIA_BASE_URL = os.getenv("MEDIA_BASE_URL", "https://media.prizeme.ru")
WEBAPP_BASE_URL = os.getenv("WEBAPP_BASE_URL", "https://prizeme.ru")

# безопасность: разрешаем дергать внутренний эндпоинт бота только с localhost
BOT_INTERNAL_URL = os.getenv("BOT_INTERNAL_URL", "http://127.0.0.1:8088")

app: FastAPI  # приложение у тебя уже создано выше — эту строку не трогаем

WEBAPP_DIR = Path(__file__).parent / "webapp"   # preview-service/webapp/
INDEX_FILE = WEBAPP_DIR / "index.html"
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
OK_STATUSES = {"creator", "administrator", "member", "restricted"}  # restricted с is_member=true

# --- POST /api/check ---
@app.post("/api/check")
async def api_check(req: Request):
    """
    Проверка условий розыгрыша.
    Ждём: { "gid": <int>, "init_data": "<Telegram WebApp initData>" }
    Возвращаем:
      { ok: true, done: false, need: [{title, username, url}], details: [...] }
      { ok: true, done: true,  ticket: "ABC123" | null, details: [...] }
    """
    if not BOT_TOKEN:
        return JSONResponse({"ok": False, "reason": "no_bot_token"}, status_code=500)

    # 0) тело запроса
    try:
        body = await req.json()
    except Exception:
        return JSONResponse({"ok": False, "reason": "bad_json"}, status_code=400)

    # 1) gid
    try:
        gid = int(body.get("gid") or 0)
    except Exception:
        gid = 0
    if not gid:
        return JSONResponse({"ok": False, "reason": "bad_gid"}, status_code=400)

    # 2) init_data → валидация и user_id
    init_data = (body.get("init_data") or "").strip()
    parsed = _tg_check_webapp_initdata(init_data)
    if not parsed or not parsed.get("user_parsed"):
        # здесь оставляем 400, чтобы видно было проблему на фронте
        return JSONResponse({"ok": False, "reason": "bad_initdata"}, status_code=400)
    user_id = int(parsed["user_parsed"]["id"])

    # 3) читаем каналы розыгрыша
    try:
        with _db() as db:
            rows = db.execute("""
                SELECT gc.chat_id, gc.title, oc.username
                FROM giveaway_channels gc
                LEFT JOIN organizer_channels oc ON oc.id = gc.channel_id
                WHERE gc.giveaway_id=?
                ORDER BY gc.id
            """, (gid,)).fetchall()
            channels = [{"chat_id": r["chat_id"], "title": r["title"], "username": r["username"]} for r in rows]
    except Exception as e:
        return JSONResponse({"ok": False, "reason": f"db_error: {type(e).__name__}: {e}"}, status_code=500)

    # 4) проверка подписки
    need, details = [], []
    async with AsyncClient(timeout=10.0) as client:
        for ch in channels:
            raw_id  = ch.get("chat_id")
            title   = ch.get("title") or ch.get("username") or "канал"
            uname   = ch.get("username")
            chat_id = None

            # a) привести chat_id к int, если он передан
            if raw_id is not None:
                try:
                    chat_id = int(str(raw_id))
                except Exception as e:
                    details.append(f"[{title}] bad chat_id={raw_id!r}: {e}")

            # b) если chat_id нет, но есть username — резолвим через getChat
            if chat_id is None and uname:
                try:
                    info = await tg_get_chat(client, uname)  # см. helper ниже
                    chat_id = int(info["id"])
                    details.append(f"[{title}] resolved id={chat_id}")
                except Exception as e:
                    need.append({
                        "title": "Ошибка проверки. Нажмите «Проверить подписку».",
                        "username": uname,
                        "url": f"https://t.me/{uname}",
                    })
                    details.append(f"[{title}] resolve failed: {e}")
                    continue

            # c) если chat_id так и не получили — даём «ошибка проверки»
            if chat_id is None:
                need.append({
                    "title": "Ошибка проверки. Нажмите «Проверить подписку».",
                    "username": uname,
                    "url": f"https://t.me/{uname}" if uname else None,
                })
                details.append(f"[{title}] no chat id & no username")
                continue

            # d) финальная проверка членства
            try:
                ok, dbg = await tg_get_chat_member(client, chat_id, user_id)
                details.append(f"[{title}] {dbg}")
                if not ok:
                    need.append({
                        "title": title,
                        "username": uname,
                        "url": f"https://t.me/{uname}" if uname else None,
                    })
            except Exception as e:
                need.append({
                    "title": "Ошибка проверки. Нажмите «Проверить подписку».",
                    "username": uname,
                    "url": f"https://t.me/{uname}" if uname else None,
                })
                details.append(f"[{title}] get_chat_member failed: {e}")

    done = len(need) == 0

    # 5) если всё ок — вернём уже выданный билет (если есть)
    ticket = None
    if done:
        try:
            with _db() as db:
                row = db.execute(
                    "SELECT ticket_code FROM entries WHERE giveaway_id=? AND user_id=?",
                    (gid, user_id),
                ).fetchone()
                ticket = row["ticket_code"] if row else None
        except Exception as e:
            details.append(f"ticket_lookup_error: {type(e).__name__}: {e}")

    return JSONResponse({"ok": True, "done": done, "need": need, "ticket": ticket, "details": details})


# --- POST /api/claim ---
@app.post("/api/claim")
async def api_claim(req: Request):
    """
    Выдача билета (повторно безопасно).
    Ждём: { "gid": <int>, "init_data": "<Telegram WebApp initData>" }
    Возвращаем:
      { ok: true,  ticket: "ABC123" }
      { ok: false, need: [...]}  # если вдруг подписки не выполнены
    """
    if not BOT_TOKEN:
        return JSONResponse({"ok": False, "reason": "no_bot_token"}, status_code=500)

    try:
        body = await req.json()
    except Exception:
        return JSONResponse({"ok": False, "reason": "bad_json"}, status_code=400)

    parsed = _tg_check_webapp_initdata((body.get("init_data") or "").strip())
    if not parsed or not parsed.get("user_parsed"):
        return JSONResponse({"ok": False, "reason": "bad_initdata"}, status_code=400)

    user_id = int(parsed["user_parsed"]["id"])
    try:
        gid = int(body.get("gid") or 0)
    except Exception:
        gid = 0
    if not gid:
        return JSONResponse({"ok": False, "reason": "bad_gid"}, status_code=400)

    # 1) повторная проверка подписки (защита, если фронт обходят вручную)
    need = []
    details = []
    try:
        with _db() as db:
            rows = db.execute("""
                SELECT gc.chat_id, gc.title, oc.username
                FROM giveaway_channels gc
                LEFT JOIN organizer_channels oc ON oc.id = gc.channel_id
                WHERE gc.giveaway_id=?
                ORDER BY gc.id
            """, (gid,)).fetchall()
            channels = [
                {"chat_id": r["chat_id"], "title": r["title"], "username": r["username"]}
                for r in rows
            ]
    except Exception as e:
        return JSONResponse({"ok": False, "reason": f"db_error: {type(e).__name__}: {e}"}, status_code=500)

    async with AsyncClient(timeout=10.0) as client:
        for ch in channels:
            title = ch.get("title") or "канал"
            username = ch.get("username")
            try:
                chat_id = int(ch.get("chat_id"))
                r = await client.get(
                    f"{TELEGRAM_API}/getChatMember",
                    params={"chat_id": chat_id, "user_id": user_id},
                )
                js = r.json()
                is_ok = js.get("ok") and (js["result"]["status"] or "").lower() in ("member","administrator","creator")
            except Exception:
                is_ok = False
            if not is_ok:
                need.append({
                    "title": title,
                    "username": username,
                    "url": f"https://t.me/{username}" if username else None,
                })

    if need:
        return JSONResponse({"ok": False, "need": need})

    # 2) выдаём (или возвращаем существующий) билет
    try:
        with _db() as db:
            row = db.execute(
                "SELECT ticket_code FROM entries WHERE giveaway_id=? AND user_id=?",
                (gid, user_id),
            ).fetchone()
            if row:
                return JSONResponse({"ok": True, "ticket": row["ticket_code"]})

            import random, string
            alphabet = string.ascii_uppercase + string.digits
            # простая попытка с редкими коллизиями
            for _ in range(8):
                code = "".join(random.choices(alphabet, k=6))
                try:
                    db.execute(
                        "INSERT INTO entries(giveaway_id, user_id, ticket_code, prelim_ok, prelim_checked_at) "
                        "VALUES (?, ?, ?, 1, strftime('%Y-%m-%d %H:%M:%f','now'))",
                        (gid, user_id, code),
                    )
                    db.commit()
                    return JSONResponse({"ok": True, "ticket": code})
                except Exception:
                    # коллизия по уникальному коду — пробуем ещё раз
                    pass
    except Exception as e:
        return JSONResponse({"ok": False, "reason": f"db_write_error: {type(e).__name__}: {e}"}, status_code=500)

    return JSONResponse({"ok": False, "reason": "ticket_issue_failed"}, status_code=500)


# 1. Отдаём всегда один и тот же index.html независимо от под-путей
@app.get("/miniapp/", response_class=HTMLResponse)
async def miniapp_index_get() -> HTMLResponse:
    html = INDEX_FILE.read_text(encoding="utf-8")
    return HTMLResponse(
        html,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )

# Для HEAD просто отдаём заголовки 200 (телу быть не обязательно)
@app.head("/miniapp/")
async def miniapp_index_head():
    return Response(
        status_code=200,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )

# 2. Подключаем статику (js/css) из preview-service/webapp/
#    Директория должна существовать и содержать app.js, styles.css, index.html
app.mount(
    "/miniapp-static",
    StaticFiles(directory=str(WEBAPP_DIR), html=False),
    name="miniapp-static",
)

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

# --- helper: аккуратная проверка членства с логами
async def tg_get_chat_member(client: AsyncClient, chat_id: int, user_id: int) -> tuple[bool, str]:
    try:
        r = await client.get(
            f"{TELEGRAM_API}/getChatMember",
            params={"chat_id": chat_id, "user_id": user_id},
            timeout=5.0
        )
        data = r.json()
    except Exception as e:
        # сеть / таймаут / иное
        return False, f"network_error: {type(e).__name__}: {e}"

    if not data.get("ok"):
        # типичная причина: бот не админ канала → "400 Bad Request: user not found"
        return False, f"tg_error: {data.get('error_code')} {data.get('description')}"

    status = (data["result"]["status"] or "").lower()
    # считаем подписчиком member | administrator | creator
    is_member = status in ("member", "administrator", "creator")
    return is_member, f"status={status}"

# --- helper: getChat по @username -> {id, title, ...}
async def tg_get_chat(client: AsyncClient, username: str) -> dict:
    uname = username if username.startswith("@") else f"@{username}"
    r = await client.get(f"{TELEGRAM_API}/getChat", params={"chat_id": uname}, timeout=5.0)
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"tg_error: {data.get('error_code')} {data.get('description')}")
    return data["result"]


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

