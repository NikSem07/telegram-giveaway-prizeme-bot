# app.py — MiniApp + проверки подписки + прокси /uploads/* к S3

import os
import mimetypes
import json, hmac, hashlib
from pathlib import Path
import sqlite3
from typing import Optional, Dict, Any

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, Response, HTMLResponse, RedirectResponse
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

@app.middleware("http")
async def _head_as_get(request: Request, call_next):
    # Любой HEAD превращаем во внутренний GET, а наружу отдаем только заголовки и статус
    if request.method == "HEAD":
        request.scope["method"] = "GET"
        resp = await call_next(request)
        headers = dict(resp.headers)
        headers["content-length"] = "0"
        return Response(status_code=resp.status_code, headers=headers)
    return await call_next(request)


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

@app.get("/health", response_class=PlainTextResponse)
async def health_get():
    return "ok"

@app.head("/health")
async def health_head():
    # пустой 200 OK
    return Response(status_code=200)


# ──────────────────────────────────────────────────────────────────────────────
# Mini-App (фронт) — одна HTML-страница (GET) + отдельный HEAD
# ──────────────────────────────────────────────────────────────────────────────

# ================== PRIZEME MINI-APP BLOCK (BEGIN) ==================
# HTML контент мини-приложения (встроенный)
MINIAPP_HTML = """
<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>PrizeMe — Участие</title>
  <script src="https://telegram.org/js/telegram-web-app.js"></script>
  <style>
    html,body{margin:0;padding:0;font-family:Inter,system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;background:#0f1115;color:#fff}
    .wrap{max-width:640px;margin:0 auto;padding:24px}
    .card{background:#161a20;border:1px solid #22262e;border-radius:16px;padding:20px}
    .btn{display:inline-block;margin-top:16px;padding:12px 16px;border-radius:10px;border:none;cursor:pointer;font-weight:600}
    .btn-primary{background:#4f46e5;color:#fff}
    .muted{color:#cbd5e1;font-size:14px}
    a{color:#93c5fd;text-decoration:none}
    a:hover{text-decoration:underline}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1>PrizeMe — участие в розыгрыше</h1>
      <p class="muted">Проверим подписку на каналы и выдадим «билет участника».</p>
      <button id="check" class="btn btn-primary">Проверить подписку</button>
      <div id="result" class="muted" style="margin-top:12px;"></div>
    </div>
  </div>

  <script>
    const tg = window.Telegram?.WebApp;
    try { tg?.expand?.(); } catch(e) {}

    async function postJSON(url, data){
      const r = await fetch(url, {
        method: "POST",
        headers: {"Content-Type":"application/json"},
        body: JSON.stringify(data)
      });
      const ct = r.headers.get("content-type") || "";
      return ct.includes("application/json") ? r.json() : { ok:false, status:r.status };
    }

    document.getElementById('check').onclick = async () => {
      const result = document.getElementById('result');
      result.textContent = "Проверяем...";
      // Берём базовые данные из Telegram WebApp
      const initData = tg?.initDataUnsafe || {};
      const user = initData?.user || {};
      // TODO: сюда добавим реальные параметры (giveaway_id и т.п.)
      const payload = { tg_user_id: user.id || null };

      try {
        const resp = await postJSON('/api/check-join', payload);
        if (resp?.ok) {
          result.textContent = "Подписка подтверждена — билет выдан ✅";
        } else {
          if (resp?.channels_to_join?.length){
            result.innerHTML = "Нужно подписаться на каналы:<br>" +
              resp.channels_to_join.map(c => `<a href="${c.url}" target="_blank" rel="noopener">${c.title}</a>`).join("<br>");
          } else {
            result.textContent = "Не удалось подтвердить подписку. Попробуйте ещё раз.";
          }
        }
      } catch (e) {
        result.textContent = "Ошибка сети. Попробуйте позже.";
      }
    };
  </script>
</body>
</html>
"""

# /miniapp -> /miniapp/ (удобнее для относительных путей в HTML)
@app.get("/miniapp", response_class=HTMLResponse)
async def miniapp_get_no_slash():
    return RedirectResponse(url="/miniapp/", status_code=307)

# Основной рендер мини-аппа
@app.get("/miniapp/", response_class=HTMLResponse)
async def miniapp_get():
    return HTMLResponse(content=MINIAPP_HTML, status_code=200)

# Явные HEAD-обработчики (убирают 405 у проверок апстрима)
@app.head("/miniapp")
async def miniapp_head_no_slash():
    return Response(status_code=200)

@app.head("/miniapp/")
async def miniapp_head():
    return Response(status_code=200)


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