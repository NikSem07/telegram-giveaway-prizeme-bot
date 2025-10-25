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

# --- POST /api/claim ---
@app.post("/api/check")
async def api_check(req: Request):
    """
    1) Получаем от фронта gid и user_id (он приходит из tgWebAppData).
    2) Идём во внутренний HTTP бота (aiohttp на 127.0.0.1:8088) за сведениями о каналах и дедлайне.
    3) Сами проверяем подписку по каждому каналу через Bot API getChatMember.
    4) Возвращаем фронту "ok"/"need"/"error" и подробности.
    """
    data = await req.json()
    gid = str(data.get("gid") or "")
    user_id = int(data.get("user_id") or 0)

    if not gid or not user_id:
        return JSONResponse({"ok": False, "error": "bad_request"}, status_code=400)

    # 1) Берём сведения о розыгрыше у внутреннего сервера бота
    internal_url = f"{BOT_INTERNAL_URL}/api/giveaway_info"
    try:
        async with httpx.AsyncClient(timeout=10.0) as cli:
            r = await cli.post(internal_url, json={"gid": gid, "user_id": user_id})
            txt = r.text
            if r.status_code != 200:
                print(f"[api_check] INTERNAL FAIL {internal_url} -> {r.status_code} :: {txt}")
                return JSONResponse({"ok": False, "error": "internal_fail"}, status_code=502)
            info = r.json()
    except Exception as e:
        print(f"[api_check] INTERNAL EXC {internal_url}: {e!r}")
        return JSONResponse({"ok": False, "error": "internal_exc"}, status_code=502)

    channels = info.get("channels") or []
    ends_at  = info.get("ends_at")

    # 2) Проверяем подписку пользователя на каждом канале
    need   = []
    detail = []
    try:
        async with AsyncClient() as client:
            for ch in channels:
                chat_id = ch.get("chat_id")
                title   = ch.get("title") or "канал"

                # нормализуем chat_id если вдруг строка
                try:
                    chat_id = int(chat_id)
                except Exception:
                    detail.append(f"{title}: bad chat_id={chat_id!r}")
                    need.append({
                        "title": "Ошибка проверки. Нажмите «Проверить подписку».",
                        "username": ch.get("username"),
                        "url": f"https://t.me/{ch['username']}" if ch.get("username") else None,
                    })
                    continue

                ok, dbg = await tg_get_chat_member(client, chat_id, user_id)
                detail.append(f"{title}: {dbg}")
                if not ok:
                    need.append({
                        "title": title,
                        "username": ch.get("username"),
                        "url": f"https://t.me/{ch['username']}" if ch.get("username") else None,
                    })
    except Exception as e:
        print(f"[api_check] CHAT_MEMBER EXC: {e!r}")
        return JSONResponse({"ok": False, "error": "check_exc"}, status_code=502)

    if need:
        # надо подписаться хотя бы на один канал
        return JSONResponse({
            "ok": True,
            "done": False,
            "need": need,
            "ends_at": ends_at,
            "details": detail,
        })

    # всё ок — подписка выполнена
    return JSONResponse({
        "ok": True,
        "done": True,
        "ticket": None,   # билет выдаём отдельным вызовом (ниже)
        "ends_at": ends_at,
        "details": detail,
    })


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


@app.post("/api/check-join")
async def api_check_join(req: Request):
    """
    Тело: { "gid": <int>, "init_data": "<Telegram WebApp initData>" }

    Ответ:
      ok: bool
      need: [{title, username, url}]
      ticket?: str
      title?: str
      details?: [str]
      reason?: str  # при ошибке
    """
    if not BOT_TOKEN:
        return JSONResponse({"ok": False, "reason": "no_bot_token"}, status_code=500)

    try:
        body = await req.json()
    except Exception:
        return JSONResponse({"ok": False, "reason": "bad_json"}, status_code=400)

    # 0) проверка init_data (подпись Telegram WebApp)
    parsed = _tg_check_webapp_initdata((body.get("init_data") or "").strip())
    if not parsed or not parsed.get("user_parsed"):
        return JSONResponse({"ok": False, "reason": "bad_initdata"}, status_code=400)

    user_id = int(parsed["user_parsed"]["id"])
    gid = int(body.get("gid") or 0)
    if not gid:
        return JSONResponse({"ok": False, "reason": "no_gid"}, status_code=400)

    details: list[str] = []
    # 1) читаем розыгрыш и каналы из БД
    try:
        with _db() as db:
            g_row = db.execute(
                "SELECT internal_title FROM giveaways WHERE id=?",
                (gid,)
            ).fetchone()
            if not g_row:
                return JSONResponse({"ok": False, "reason": "giveaway_not_found"}, status_code=404)

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
        # самая частая причина: неправильный путь к БД → no such table ...
        return JSONResponse({
            "ok": False,
            "reason": f"db_error: {type(e).__name__}: {e}",
            "details": details
        }, status_code=500)

    # 2) проверяем подписку по каждому каналу
    need = []
    async with AsyncClient(timeout=10.0) as client:
        for ch in channels:
            raw_chat_id = ch.get("chat_id")
            title = ch.get("title") or "канал"
            username = ch.get("username")

            try:
                chat_id = int(raw_chat_id)
            except Exception:
                details.append(f"[{title}] bad chat_id={raw_chat_id!r}")
                need.append({
                    "title": "Ошибка проверки. Нажмите «Проверить подписку».",
                    "username": username,
                    "url": f"https://t.me/{username}" if username else None,
                })
                continue

            try:
                r = await client.get(
                    f"{TELEGRAM_API}/getChatMember",
                    params={"chat_id": chat_id, "user_id": user_id},
                )
                js = r.json()
                if not js.get("ok"):
                    details.append(f"[{title}] tg_error {js.get('error_code')} {js.get('description')}")
                    is_member = False
                else:
                    status = (js["result"]["status"] or "").lower()
                    details.append(f"[{title}] status={status}")
                    is_member = status in ("member", "administrator", "creator")
            except Exception as e:
                details.append(f"[{title}] network_error: {type(e).__name__}: {e}")
                is_member = False

            if not is_member:
                need.append({
                    "title": title,
                    "username": username,
                    "url": f"https://t.me/{username}" if username else None,
                })

    # 3) если подписан везде — выдаём/возвращаем билет
    if not need:
        code = None
        try:
            with _db() as db:
                row = db.execute(
                    "SELECT ticket_code FROM entries WHERE giveaway_id=? AND user_id=?",
                    (gid, user_id),
                ).fetchone()
                if row:
                    code = row["ticket_code"]
                else:
                    import random, string
                    alphabet = string.ascii_uppercase + string.digits
                    for _ in range(8):
                        try_code = "".join(random.choices(alphabet, k=6))
                        try:
                            db.execute(
                                "INSERT INTO entries(giveaway_id, user_id, ticket_code, prelim_ok, prelim_checked_at) "
                                "VALUES (?, ?, ?, 1, strftime('%Y-%m-%d %H:%M:%f','now'))",
                                (gid, user_id, try_code),
                            )
                            db.commit()
                            code = try_code
                            break
                        except Exception:
                            pass
        except Exception as e:
            return JSONResponse({
                "ok": False,
                "reason": f"db_write_error: {type(e).__name__}: {e}",
                "details": details
            }, status_code=500)

        return JSONResponse({
            "ok": True,
            "ticket": code,
            "title": g_row["internal_title"],
            "details": details,
        })

    # 4) не все условия выполнены
    return JSONResponse({
        "ok": False,
        "need": need,
        "details": details,
    })

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

