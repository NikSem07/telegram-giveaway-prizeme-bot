import hashlib
print("[BOOT] BOT_TOKEN_SHA256=", hashlib.sha256(BOT_TOKEN.encode()).hexdigest())

# app.py — MiniApp + проверки подписки + прокси /uploads/* к S3
import os
import time
import mimetypes
import json, hmac
from pathlib import Path
import sqlite3
from typing import Optional, Dict, Any, List
from fastapi.staticfiles import StaticFiles
from urllib.parse import parse_qsl, unquote

import httpx
from httpx import AsyncClient
from dotenv import load_dotenv, find_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, FileResponse, Response, HTMLResponse, RedirectResponse, JSONResponse

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

MEDIA_BASE_URL = os.getenv("MEDIA_BASE_URL", "https://media.prizeme.ru")
WEBAPP_BASE_URL = os.getenv("WEBAPP_BASE_URL", "https://prizeme.ru")

# безопасность: разрешаем дергать внутренний эндпоинт бота только с localhost
BOT_INTERNAL_URL = os.getenv("BOT_INTERNAL_URL", "http://127.0.0.1:8088")

app: FastAPI  # приложение у тебя уже создано выше — эту строку не трогаем

WEBAPP_DIR = Path(__file__).parent / "webapp"   # preview-service/webapp/
INDEX_FILE = WEBAPP_DIR / "index.html"
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
OK_STATUSES = {"creator", "administrator", "member", "restricted"}  # restricted с is_member=true

def _is_member_local(chat_id: int, user_id: int) -> bool:
    try:
        with _db() as db:
            row = db.execute(
                "SELECT 1 FROM channel_memberships WHERE chat_id=? AND user_id=?",
                (int(chat_id), int(user_id)),
            ).fetchone()
            return row is not None
    except Exception:
        return False

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
        print(f"[CHECK] body={body!r}")
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
    raw_init = (body.get("init_data") or "").strip()
    validator_used = "mini" if "signature=" in raw_init else "web"
    parsed = _tg_check_miniapp_initdata(raw_init) if validator_used == "mini" else _tg_check_webapp_initdata(raw_init)
    print(f"[CHECK] validator={validator_used} init_data_len={len(raw_init)} parsed={'ok' if parsed else 'None'}")  # лог

    if not parsed or not parsed.get("user_parsed"):
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

    print(f"[CHECK] channels_in_db={channels}")


    # 4) проверка подписки
    need, details = [], []
    async with AsyncClient(timeout=10.0) as client:
        for ch in channels:
            raw_id  = ch.get("chat_id")
            title   = ch.get("title") or ch.get("username") or "канал"
            uname   = ch.get("username")
            chat_id = None

            print(f"[DEBUG] Processing channel: {title}, username: {uname}, raw_id: {raw_id}")

            # a) привести chat_id к int, если он передан
            if raw_id is not None:
                try:
                    chat_id = int(str(raw_id))
                    details.append(f"[{title}] using chat_id={chat_id}")
                except Exception as e:
                    details.append(f"[{title}] bad chat_id={raw_id!r}: {e}")

            # b) если chat_id нет, но есть username — резолвим через getChat
            if chat_id is None and uname:
                try:
                    print(f"[DEBUG] Resolving username: {uname}")
                    info = await tg_get_chat(client, uname)
                    chat_id = int(info["id"])
                    details.append(f"[{title}] resolved id={chat_id} from username")
                    
                    # Обновляем chat_id в памяти для последующих проверок
                    ch["chat_id"] = chat_id
                except Exception as e:
                    need.append({
                        "title": f"Ошибка проверки {title}. Нажмите «Проверить подписку».",
                        "username": uname,
                        "url": f"https://t.me/{uname}",
                    })
                    details.append(f"[{title}] resolve failed: {e}")
                    continue

            # c) если chat_id так и не получили — даём «ошибка проверки»
            if chat_id is None:
                need.append({
                    "title": f"Ошибка проверки {title}. Нажмите «Проверить подписку».",
                    "username": uname,
                    "url": f"https://t.me/{uname}" if uname else None,
                })
                details.append(f"[{title}] no chat id & no username")
                continue

            # d) финальная проверка членства: сначала локально, потом Bot API
            try:
                # быстрый путь — после одобренного join-request у нас уже есть отметка
                if _is_member_local(chat_id, user_id):
                    details.append(f"[{title}] local=OK")
                else:
                    ok_api, dbg = await tg_get_chat_member(client, int(chat_id), int(user_id))
                    details.append(f"[{title}] {dbg}")
                    if not ok_api:
                        need.append({
                            "title": title,
                            "username": uname,
                            "url": f"https://t.me/{uname}" if uname else None,
                        })
            except Exception as e:
                need.append({
                    "title": f"Ошибка проверки {title}. Нажмите «Проверить подписку».",
                    "username": uname,
                    "url": f"https://t.me/{uname}" if uname else None,
                })
                details.append(f"[{title}] get_chat_member failed: {e}")
            except Exception as e:
                need.append({
                    "title": f"Ошибка проверки {title}. Нажмите «Проверить подписку».",
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

    if not BOT_TOKEN:
        return JSONResponse({"ok": False, "reason": "no_bot_token"}, status_code=500)

    try:
        body = await req.json()
        print(f"[CLAIM] body={body!r}")
    except Exception:
        return JSONResponse({"ok": False, "reason": "bad_json"}, status_code=400)

    raw_init = (body.get("init_data") or "").strip()
    validator_used = "mini" if "signature=" in raw_init else "web"
    parsed = _tg_check_miniapp_initdata(raw_init) if validator_used == "mini" else _tg_check_webapp_initdata(raw_init)
    print(f"[CLAIM] validator={validator_used} init_data_len={len(raw_init)} parsed={'ok' if parsed else 'None'}")  # лог

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
                if _is_member_local(chat_id, user_id):
                    is_ok = True
                else:
                    ok_check, dbg = await tg_get_chat_member(client, chat_id, user_id)
                    is_ok = ok_check
            except Exception:
                is_ok = False
            if not is_ok:
                need.append({
                    "title": title,
                    "username": username,
                    "url": f"https://t.me/{username}" if username else None,
                })

    # после цикла по каналам
    done = len(need) == 0
    if not done:
        return JSONResponse({"ok": True, "done": False, "need": need, "details": details})

    # 2) выдаём (или возвращаем существующий) билет
    try:
        with _db() as db:
            row = db.execute(
                "SELECT ticket_code FROM entries WHERE giveaway_id=? AND user_id=?",
                (gid, user_id),
            ).fetchone()
            if row:
                return JSONResponse({"ok": True, "done": True, "ticket": row["ticket_code"], "details": details})

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
                    return JSONResponse({"ok": True, "done": True, "ticket": code, "details": details})
                except Exception:
                    # коллизия по уникальному коду — пробуем ещё раз
                    pass
    except Exception as e:
        return JSONResponse({"ok": False, "reason": f"db_write_error: {type(e).__name__}: {e}"}, status_code=500)

    return JSONResponse({"ok": False, "done": True, "reason": "ticket_issue_failed"}, status_code=500)


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
    Проверяем initData по правилам Telegram Mini Apps.
    ВАЖНО: при построении data_check_string игнорируем поля 'hash' и 'signature'.
    Возвращаем parsed dict и кладём разобранного user в parsed["user_parsed"].
    """
    try:
        if not init_data or not isinstance(init_data, str):
            return None

        # Разбираем query-string в словарь (сохраняем пустые значения)
        parsed_items = dict(parse_qsl(init_data, keep_blank_values=True))

        # Вынимаем хэш, а также убираем 'signature' (не участвует в подписи)
        tg_hash = parsed_items.pop("hash", "")
        parsed_items.pop("signature", None)

        if not tg_hash:
            return None

        # Собираем data_check_string: key=value по алфавиту, через \n
        data_check_string = "\n".join(f"{k}={parsed_items[k]}" for k in sorted(parsed_items.keys()))

        # Ключ = HMAC-SHA256("WebAppData", BOT_TOKEN) → затем HMAC-SHA256(data_check_string, ключ)
        secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode("utf-8"), hashlib.sha256).digest()
        check_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

        if not hmac.compare_digest(check_hash, tg_hash):
            return None

        # Разбираем JSON из поля user
        user_json = parsed_items.get("user")
        user = json.loads(user_json) if user_json else None
        parsed_items["user_parsed"] = user
        return parsed_items
    except Exception:
        return None
    
# --- Валидатор для Mini Apps ---

def _tg_check_miniapp_initdata(init_data: str) -> dict | None:
    """
    Проверяем init_data из Telegram Mini Apps по официальной спецификации.
    Секрет: HMAC-SHA256("WebAppData", bot_token)
    Data-check-string: все поля кроме 'hash' в исходном URL-encoded виде
    """
    try:
        raw = (init_data or "").strip()
        print(f"[CHECK][mini] raw_len={len(raw)}")
        
        # 1) Парсим как query string сохраняя исходное кодирование
        parsed = dict(parse_qsl(raw, keep_blank_values=True, encoding='latin-1'))
        
        # Извлекаем hash до любой обработки
        tg_hash = parsed.get("hash", "")
        if not tg_hash:
            print("[CHECK][mini] no hash -> fail")
            return None
        
        # 2) Собираем data-check-string из ВСЕХ полей кроме 'hash'
        # Используем исходные URL-encoded значения как есть
        check_parts = []
        for key in sorted(parsed.keys()):
            if key == "hash":
                continue
            # Берем значения в том виде, как они пришли (URL-encoded)
            value = parsed[key]
            check_parts.append(f"{key}={value}")
        
        data_check_string = "\n".join(check_parts)
        print(f"[CHECK][mini] data_check_string='{data_check_string}'")
        print(f"[CHECK][mini] tg_hash='{tg_hash}'")
        
        # 3) Вычисляем секрет по спецификации Mini Apps
        # Ключ = HMAC-SHA256("WebAppData", bot_token)
        secret_key = hmac.new(
            key=b"WebAppData",
            msg=BOT_TOKEN.encode(),
            digestmod=hashlib.sha256
        ).digest()
        
        # 4) Вычисляем ожидаемый hash
        check_hash = hmac.new(
            key=secret_key,
            msg=data_check_string.encode(),
            digestmod=hashlib.sha256
        ).hexdigest()
        
        print(f"[CHECK][mini] computed_hash='{check_hash}'")
        
        # 5) Сравниваем хэши
        ok = hmac.compare_digest(check_hash, tg_hash)
        print(f"[CHECK][mini] digest_ok={ok}")
        
        if not ok:
            return None

        # 6) Декодируем user для извлечения ID
        user_json_encoded = parsed.get("user")
        if user_json_encoded:
            user_json = unquote(user_json_encoded)
            user = json.loads(user_json)
            if not user or "id" not in user:
                print("[CHECK][mini] no user.id -> fail")
                return None
        else:
            print("[CHECK][mini] no user -> fail")
            return None

        return {
            "user_parsed": user, 
            "start_param": unquote(parsed.get("start_param", "")) if parsed.get("start_param") else None
        }
        
    except Exception as e:
        print(f"[CHECK][mini] exception={e!r}")
        import traceback
        print(f"[CHECK][mini] traceback: {traceback.format_exc()}")
        return None


def build_s3_url(key: str) -> str:
    return f"{S3_ENDPOINT}/{S3_BUCKET}/{key.lstrip('/')}"

def is_bot_request(request: Request) -> bool:
    ua = request.headers.get("user-agent", "").lower()
    return any(b in ua for b in ("telegrambot", "twitterbot", "facebookexternalhit", "linkedinbot"))

# Добавьте эту функцию для тестирования
def test_miniapp_validation():
    """Тест на реальных данных Mini Apps"""
    # Пример реального init_data (замените на актуальный из логов)
    test_init_data = "user=%7B%22id%22%3A428883823%2C%22first_name%22%3A%22Nikita%22%2C%22last_name%22%3A%22Semenov%22%2C%22username%22%3A%22NikSemyonov%22%2C%22language_code%22%3A%22ru%22%2C%22is_premium%22%3Atrue%2C%22allows_write_to_pm%22%3Atrue%2C%22photo_url%22%3A%22https%3A%5C%2F%5C%2Ft.me%5C%2Fi%5C%2Fuserpic%5C%2F320%5C%2FYehTOpkUodPx8emwyz2PN7JwrDxf2aHqZN7fofdhjvw.svg%22%7D&chat_instance=3485967117599202343&chat_type=channel&start_param=13&auth_date=1761558433&signature=rvUP2hyaDgqfJ_vrS4tdwtUMQH6g_9o1DB-xYBV2iBGDEsrukYC8wSk_MAslZyVR60SW1qoX5flPM44tqldNBg&hash=2ed65a38563fcedfb9b3fb1a7091ae3a7a6e06ba9c69c2e4e75955a18b132ab4"
    
    result = _tg_check_miniapp_initdata(test_init_data)
    print(f"Test result: {result is not None}")
    if result:
        print(f"User ID: {result['user_parsed']['id']}")
    
    return result

# Можно вызвать тест где-нибудь в коде при запуске
# test_miniapp_validation()

# ──────────────────────────────────────────────────────────────────────────────
# Mini-App (бэкенд) — проверка подписок и выдача билета
# ──────────────────────────────────────────────────────────────────────────────

# --- helper: аккуратная проверка членства с логами
async def tg_get_chat_member(client: AsyncClient, chat_id: int, user_id: int) -> tuple[bool, str]:
    """
    Проверка членства с улучшенной обработкой ошибок и статусов
    """
    try:
        print(f"[DEBUG] Checking membership: chat_id={chat_id}, user_id={user_id}")
        
        r = await client.get(
            f"{TELEGRAM_API}/getChatMember",
            params={"chat_id": chat_id, "user_id": user_id},
            timeout=10.0
        )
        data = r.json()
        print(f"[DEBUG] getChatMember FULL response: {data}")
        
    except Exception as e:
        print(f"[ERROR] Network error: {e}")
        return False, f"network_error: {type(e).__name__}: {e}"

    if not data.get("ok"):
        error_code = data.get('error_code')
        description = data.get('description', '')
        
        print(f"[ERROR] Telegram API error: {error_code} - {description}")
        
        # Анализ ошибок
        if "bot was kicked" in description.lower():
            return False, "bot_kicked_from_chat"
        elif "bot is not a member" in description.lower():
            return False, "bot_not_member_of_chat"
        elif "chat not found" in description.lower():
            return False, "chat_not_found"
        elif "user not found" in description.lower():
            return False, "user_not_found_in_chat"
        elif "not enough rights" in description.lower():
            return False, "bot_not_admin"
        elif error_code == 400:
            return False, f"bad_request: {description}"
        elif error_code == 403:
            return False, f"forbidden: {description}"
        else:
            return False, f"tg_api_error: {error_code} {description}"

    result = data["result"]
    status = (result.get("status") or "").lower()
    
    print(f"[DEBUG] User status: {status}")
    
    # Расширенная проверка статусов
    is_member = False
    if status in ("member", "administrator", "creator"):
        is_member = True
        print(f"[DEBUG] User is member with status: {status}")
    elif status == "restricted":
        # Для restricted проверяем is_member
        is_member = result.get("is_member", False)
        print(f"[DEBUG] Restricted user, is_member: {is_member}")
    else:
        print(f"[DEBUG] User is NOT member, status: {status}")
    
    debug_info = f"status={status}, is_member={is_member}"
    
    # Дополнительная диагностика для restricted
    if status == "restricted":
        debug_info += f", permissions={result.get('permissions', {})}"
    
    print(f"[DEBUG] Final result: {debug_info}")
    return is_member, debug_info


# ──────────────────────────────────────────────────────────────────────────────
# Прокси /uploads/* → S3 (200 OK, без редиректа) + OG для ботов
# ──────────────────────────────────────────────────────────────────────────────

@app.api_route("/uploads/{path:path}", methods=["GET", "HEAD"])
async def uploads(path: str, request: Request):
    """
    Отдаём ИМЕННО медиа-файл для всех клиентов (и для ботов тоже),
    без OG-HTML — чтобы в Telegram не появлялись title/description.
    """
    s3_url = build_s3_url(path)
    method = "HEAD" if request.method == "HEAD" else "GET"

    # Тянем файл с S3 (или только заголовки, если HEAD)
    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        r = await client.request(method, s3_url)

    # Если S3 вернул ошибку — маппим её на 404 (чтобы Telegram не строил карточки-ошибки)
    status = 200 if r.status_code < 400 else 404

    # Тело отдаём только для GET
    content = b"" if method == "HEAD" else (r.content or b"")

    # Корректный Content-Type
    ctype = r.headers.get("content-type") or (mimetypes.guess_type(path)[0] or "application/octet-stream")

    resp = Response(content=content, status_code=status, media_type=ctype)

    # Пробрасываем длину файла (для GET). Для HEAD тело пустое — длину не ставим.
    if method == "GET" and "content-length" in r.headers:
        resp.headers["Content-Length"] = r.headers["content-length"]

    # Кэш и отладка
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

# ──────────────────────────────────────────────────────────────────────────────
# Служебные эндпоинты
# ──────────────────────────────────────────────────────────────────────────────

@app.api_route("/health", methods=["GET", "HEAD"])
async def health_any(request: Request):
    # Для GET вернём тело "ok", для HEAD — пустое тело с теми же заголовками/статусом
    if request.method == "HEAD":
        return Response(status_code=200, media_type="text/plain")
    return PlainTextResponse("ok")

# Эндпоинт для диагностики
@app.post("/api/debug/check_membership")
async def debug_check_membership(req: Request):
    try:
        body = await req.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "bad_json"}, status_code=400)

    user_id = int(body.get("user_id") or 0)
    chat_id = body.get("chat_id")
    username = (body.get("username") or "").lstrip("@") or None
    if not user_id or (not chat_id and not username):
        return JSONResponse({"ok": False, "error": "bad_args"}, status_code=400)

    async with AsyncClient(timeout=10.0) as client:
        # a) resolve @username -> chat_id при необходимости
        if chat_id is None and username:
            try:
                info = await tg_get_chat(client, username)   # используем существующий helper
                chat_id = int(info["id"])
            except Exception as e:
                return JSONResponse({"ok": True, "result": {"resolve_error": f"{type(e).__name__}: {e}"}}, status_code=200)

        # b) membership
        try:
            ok, dbg = await tg_get_chat_member(client, int(chat_id), int(user_id))
            return JSONResponse({"ok": True, "result": {"is_member": ok, "debug": dbg, "chat_id": int(chat_id)}})
        except Exception as e:
            return JSONResponse({"ok": False, "error": f"{type(e).__name__}: {e}"}, status_code=500)