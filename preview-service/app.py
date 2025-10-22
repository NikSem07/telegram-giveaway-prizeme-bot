# app.py — proxy /uploads/* к S3 без редиректа (200 OK + image/*)
import os
import mimetypes
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, Response, HTMLResponse
from dotenv import load_dotenv
import httpx
import json, hmac, hashlib, time
from pathlib import Path
import sqlite3

# Загружаем .env
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
WEBAPP_HOST = os.getenv("WEBAPP_HOST", "https://prizeme.ru").rstrip("/")
DB_PATH = Path(file).with_name("bot.db")
S3_ENDPOINT = os.getenv("S3_ENDPOINT", "https://s3.twcstorage.ru").rstrip("/")
S3_BUCKET = os.getenv("S3_BUCKET", "").strip()
CACHE_SEC = int(os.getenv("CACHE_SEC", "300"))

app = FastAPI()

# ---- utils ----
def _tg_check_webapp_initdata(init_data: str) -> dict | None:
    """
    Валидируем initData из Telegram WebApp по алгоритму из доки.
    Возвращаем словарь parsed (tgWebAppData) либо None.
    """
    try:
        # init_data is "key1=value1&key2=value2..."
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

def _db():
    # простой синхронный доступ — SQLite отлично переживает совместное чтение
    conn = sqlite3.connect(DB_PATH.as_posix())
    conn.row_factory = sqlite3.Row
    return conn

def _status_member_ok(status: str) -> bool:
    return status in ("member", "administrator", "creator")

# ---------- вспомогательные функции ----------
def build_s3_url(key: str) -> str:
    """Формируем полный URL к файлу в S3"""
    return f"{S3_ENDPOINT}/{S3_BUCKET}/{key.lstrip('/')}"

def is_bot_request(request: Request) -> bool:
    """Определяем, что это запрос от TelegramBot / TwitterBot"""
    ua = request.headers.get("user-agent", "").lower()
    return any(bot in ua for bot in ["telegrambot", "twitterbot", "facebookexternalhit", "linkedinbot"])

# ---------- маршруты ----------
@app.get("/healthz")
async def healthz():
    return PlainTextResponse(f"ok | {__file__}")

@app.get("/miniapp")
async def miniapp(request: Request):
    """
    Простая одна HTML-страница Mini-App.
    Ожидает параметр ?gid=...
    Внутри использует Telegram.WebApp для получения initData и POST /api/check-join.
    """
    html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>PrizeMe — участие</title>
  <script src="https://telegram.org/js/telegram-web-app.js"></script>
  <style>
    body {{ margin:0; font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; }}
    .wrap {{ padding:16px; }}
    .card {{ background:#1c1f26; color:#fff; border-radius:12px; padding:16px; }}
    .btn {{ display:block; width:100%; padding:12px 16px; margin-top:12px; border:0; border-radius:10px; font-size:16px; }}
    .btn-primary {{ background:#8257e6; color:#fff; }}
    .btn-ghost {{ background:#2a2f3a; color:#fff; }}
    .list {{ margin-top:8px; }}
    .item {{ background:#2a2f3a; padding:12px; border-radius:10px; margin-top:8px; display:flex; justify-content:space-between; align-items:center; }}
    .small {{ opacity:.8; font-size:13px; }}
    .center {{ text-align:center; }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card" id="box">Загружаем данные...</div>
  </div>

  <script>
    const tg = window.Telegram.WebApp;
    tg.expand();

    function qs(name) {{
      const url = new URL(window.location.href);
      return url.searchParams.get(name);
    }}

    async function checkJoin() {{
      const gid = qs('gid');
      const initData = tg.initData;
      const r = await fetch('/api/check-join', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ gid, init_data: initData }})
      }});
      const data = await r.json();
      render(data);
    }}

    function render(data) {{
      const box = document.getElementById('box');
      if (!data.ok) {{
        // Не подписан хотя бы на один канал
        let html = '<h3>Вы не выполнили условия розыгрыша!</h3><div class="small">Подпишитесь на все каналы указанные ниже.</div>';
        html += '<div class="list">';
        for (const ch of data.need) {{
          const url = ch.url  ('https://t.me/' + (ch.username  ''));
          html += '<div class="item"><div><div><b>' + (ch.title  'Канал') + '</b></div><div class="small">' + (ch.username ? '@'+ch.username : '') + '</div></div>' +
                  '<a class="btn btn-ghost" href="'+url+'" target="_blank">Подписаться</a></div>';
        }}
        html += '</div>';
        html += '<button class="btn btn-primary" onclick="checkJoin()">Проверить подписку</button>';
        box.innerHTML = html;
      }} else {{
        // Успех — есть билет
        let html = '<div class="center"><h3>Вы получили билет «' + data.ticket + '»</h3>' +
                   '<div class="small">Теперь вы участвуете в розыгрыше: <b>' + (data.title  '') + '</b></div></div>';
        box.innerHTML = html;
      }}
    }}

    checkJoin();
  </script>
</body>
</html>"""
    return HTMLResponse(html)

#--- Бэкенд-проверка и выдача билета ---
@app.post("/api/check-join")
async def api_check_join(req: Request):
    """
    Тело: { "gid": "<int>", "init_data": "<Telegram WebApp initData>" }
    Логика:
      - валидируем init_data;
      - достаём user_id и проверяем подписку во всех чатах розыгрыша;
      - если всё ок — создаём/возвращаем билет в entries;
      - отдаём JSON.
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

    # --- читаем чаты розыгрыша и сам розыгрыш ---
    with _db() as db:
        row_g = db.execute("SELECT internal_title, end_at_utc, winners_count, status FROM giveaways WHERE id=?", (gid,)).fetchone()
        if not row_g:
            return Response(content=json.dumps({"ok": False, "reason": "not_found"}), media_type="application/json")

        rows = db.execute("SELECT gc.chat_id, gc.title, oc.username FROM giveaway_channels gc LEFT JOIN organizer_channels oc ON oc.id = gc.channel_id WHERE gc.giveaway_id=?", (gid,)).fetchall()
        chats = [{"chat_id": r["chat_id"], "title": r["title"], "username": r["username"]} for r in rows]

    # --- проверка подписки через Bot API ---
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
                # ссылка
                link = None
                if ch.get("username"):
                    link = f"https://t.me/{ch['username']}"
                need.append({"title": ch["title"], "username": ch.get("username"), "url": link})

    if need:
        return Response(content=json.dumps({"ok": False, "need": need}), media_type="application/json")

    # --- подписка везде есть → выдаём/создаём билет ---
    code = None
    with _db() as db:
        row_e = db.execute("SELECT ticket_code FROM entries WHERE giveaway_id=? AND user_id=?", (gid, user_id)).fetchone()
        if row_e:
            code = row_e["ticket_code"]
        else:
            # генерируем 6-символьный, как в боте
            ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
            import random
            for _ in range(6):
                pass
            # пробуем несколько раз на случай коллизии
            for _ in range(5):
                code_try = "".join(random.choices(ALPHABET, k=6))
                try:
                    db.execute(
                        "INSERT INTO entries(giveaway_id, user_id, ticket_code, prelim_ok, prelim_checked_at) VALUES (?, ?, ?, 1, strftime('%Y-%m-%d %H:%M:%f','now'))",
                        (gid, user_id, code_try)
                    )
                    db.commit()
                    code = code_try
                    break
                except Exception:
                    continue

    title = row_g["internal_title"] if row_g else ""
    return Response(content=json.dumps({"ok": True, "ticket": code, "title": title}), media_type="application/json")


@app.api_route("/uploads/{path:path}", methods=["GET", "HEAD"])
async def uploads(path: str, request: Request):
    """
    Для TelegramBot и других ботов возвращаем HTML с OG-тегами.
    Для обычных браузеров — отдаём файл напрямую (проксирование без редиректа).
    """
    s3_url = build_s3_url(path)
    mime_guess = mimetypes.guess_type(path)[0] or "application/octet-stream"

    # Если запрос делает Telegram (бот-парсер) — отдаем OG HTML
    if is_bot_request(request):
        html = f"""<!DOCTYPE html>
        <html>
          <head>
            <meta property="og:type" content="article"/>
            <meta property="og:title" content="PrizeMe | Giveaway"/>
            <meta property="og:description" content="Participate and win!"/>
            <meta property="og:image" content="{s3_url}"/>
            <meta name="twitter:card" content="summary_large_image"/>
          </head>
          <body></body>
        </html>"""
        return HTMLResponse(content=html, headers={"Cache-Control": f"public, max-age={CACHE_SEC}"})

    # Иначе — обычный пользователь → проксируем файл (200 OK, без 302)
    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        if request.method == "HEAD":
            r = await client.head(s3_url)
            content = b""
        else:
            r = await client.get(s3_url)
            content = r.content

    ctype = r.headers.get("content-type", mime_guess)

    # Формируем ответ
    response = Response(
        content=content if request.method == "GET" else b"",
        status_code=r.status_code if r.status_code < 400 else 404,
        media_type=ctype,
    )

    # Добавляем нужные заголовки
    if "content-length" in r.headers:
        response.headers["Content-Length"] = r.headers["content-length"]
    response.headers["Cache-Control"] = f"public, max-age={CACHE_SEC}"
    response.headers["X-Proxy-From"] = s3_url
    response.headers["X-App-Path"] = __file__

    return response