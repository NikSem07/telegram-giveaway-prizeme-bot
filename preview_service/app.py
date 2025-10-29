import os, time, mimetypes
import json, hmac, hashlib
from dotenv import load_dotenv, find_dotenv
from fastapi import FastAPI, Request, Response, HTTPException
from pathlib import Path
import sqlite3
from typing import Optional, Dict, Any, List
from fastapi.staticfiles import StaticFiles
from urllib.parse import parse_qsl, unquote

import httpx
from httpx import AsyncClient
from fastapi.responses import PlainTextResponse, FileResponse, Response, HTMLResponse, RedirectResponse, JSONResponse

# ──────────────────────────────────────────────────────────────────────────────
# Инициализация
# ──────────────────────────────────────────────────────────────────────────────

# Загружаем .env из текущей папки
load_dotenv(find_dotenv(), override=False)

print("[BOOT] FILE =", Path(__file__).resolve())
print("[BOOT] MTIME=", int(Path(__file__).stat().st_mtime))
print("[BOOT] CWD  =", Path.cwd())

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
BOT_INTERNAL_URL = os.getenv("BOT_INTERNAL_URL", "http://127.0.0.1:8088")
MEDIA_BASE_URL = os.getenv("MEDIA_BASE_URL", "https://media.prizeme.ru")
WEBAPP_BASE_URL = os.getenv("WEBAPP_BASE_URL", "https://prizeme.ru")

WEBAPP_HOST = os.getenv("WEBAPP_HOST", "https://prizeme.ru").rstrip("/")
DB_PATH = Path("/root/telegram-giveaway-prizeme-bot/tgbot/bot.db")
S3_ENDPOINT = os.getenv("S3_ENDPOINT", "https://s3.twcstorage.ru").rstrip("/")
S3_BUCKET = os.getenv("S3_BUCKET", "").strip()
CACHE_SEC = int(os.getenv("CACHE_SEC", "300"))

WEBAPP_DIR = Path(__file__).parent / "webapp"   # preview-service/webapp/
INDEX_FILE = WEBAPP_DIR / "index.html"
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
OK_STATUSES = {"creator", "administrator", "member", "restricted"}  # restricted с is_member=true

app: FastAPI  # приложение у тебя уже создано выше — эту строку не трогаем


app = FastAPI()
@app.middleware("http")
async def _head_as_get(request, call_next):
    if request.method != "HEAD":
        return await call_next(request)
    request.scope["method"] = "GET"
    resp = await call_next(request)
    if resp.status_code in (404, 405):
        return Response(status_code=200, headers={"content-length": "0"})
    headers = dict(resp.headers)
    headers["content-length"] = "0"
    return Response(status_code=resp.status_code, headers=headers)

if BOT_TOKEN:
    print("[BOOT] BOT_TOKEN_SHA256=", hashlib.sha256(BOT_TOKEN.encode()).hexdigest()[:10])

def _normalize_chat_id(raw: str | int | None, username: str | None = None) -> tuple[int | None, str]:
    """
    Приводит chat_id к корректному виду для каналов/супергрупп.
    Возвращает (chat_id:int|None, debug:str).
    Логика:
      - если уже начинается с '-', просто вернём int(raw)
      - если положительное число -> попробуем превратить в -100<raw>
      - если строка и не число -> bad format
    """
    try:
        if raw is None:
            return None, "no_raw_chat_id"

        s = str(raw).strip()
        # уже корректный формат (-100…)
        if s.startswith("-"):
            return int(s), "chat_id_ok"

        # положительное число без префикса — пробуем починить
        if s.isdigit():
            fixed = f"-100{s}"
            return int(fixed), f"patched_from_positive raw={s} -> {fixed}"

        return None, f"bad_chat_id_format raw={raw!r}"
    except Exception as e:
        return None, f"normalize_error {type(e).__name__}: {e}"

def _is_member_local(chat_id: int, user_id: int) -> bool:
    """
    Проверка локальной БД на членство пользователя
    """
    try:
        with _db() as db:
            row = db.execute(
                "SELECT 1 FROM channel_memberships WHERE chat_id=? AND user_id=?",
                (int(chat_id), int(user_id)),
            ).fetchone()
            return row is not None
    except Exception as e:
        print(f"[WARNING] Local membership check failed: {e}")
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

    # 2) init_data → валидация и user_id - УПРОЩЕННАЯ ВЕРСИЯ
    raw_init = (body.get("init_data") or "").strip()
    
    # ВРЕМЕННО: упрощенная валидация
    try:
        # Парсим user напрямую без проверки подписи
        parsed = dict(parse_qsl(raw_init, keep_blank_values=True))
        user_json_encoded = parsed.get("user")
        if not user_json_encoded:
            return JSONResponse({"ok": False, "reason": "no_user_in_initdata"}, status_code=400)
            
        user_json = unquote(user_json_encoded)
        user = json.loads(user_json)
        user_id = int(user["id"])
        print(f"[CHECK] USER_EXTRACTED: id={user_id}")
        
    except Exception as e:
        print(f"[CHECK] USER_EXTRACTION_FAILED: {e}")
        return JSONResponse({"ok": False, "reason": "bad_initdata"}, status_code=400)

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

    print(f"[CHECK] user_id={user_id}, gid={gid}")
    print(f"[CHECK] channels_from_db: {channels}")
    
    # ДОПОЛНИТЕЛЬНАЯ ДИАГНОСТИКА: проверяем конкретные каналы для gid=25
    if gid == 25:
        print(f"[CHECK][GID-25] Проверяем каналы для розыгрыша 25: {channels}")
        if not channels:
            print("[CHECK][GID-25] ❌ НЕТ КАНАЛОВ В БАЗЕ!")
        else:
            for ch in channels:
                print(f"[CHECK][GID-25] Канал: {ch}")
    
    if not channels:
        return JSONResponse({
            "ok": True, 
            "done": False, 
            "need": [{"title": "Ошибка конфигурации", "username": None, "url": "#"}],
            "details": ["No channels configured for this giveaway"]
        })


    # 4) проверка подписки
    need, details = [], []
    is_ok_overall = True  # общий флаг выполнения условий
    
    async with AsyncClient(timeout=10.0) as client:
        for ch in channels:
            raw_id  = ch.get("chat_id")
            title   = ch.get("title") or ch.get("username") or "канал"
            uname   = (ch.get("username") or "").lstrip("@") or None
            chat_id = None

            # 1) Нормализация chat_id
            chat_id, dbg_norm = _normalize_chat_id(raw_id, uname)
            details.append(f"[{title}] norm: {dbg_norm}")

            # 2) Если не смогли получить chat_id из raw — пробуем резолв по username
            if chat_id is None and uname:
                try:
                    info = await tg_get_chat(client, uname)
                    chat_id = int(info["id"])
                    details.append(f"[{title}] resolved id={chat_id} from @{uname}")
                    ch["chat_id"] = chat_id
                except Exception as e:
                    details.append(f"[{title}] resolve_failed: {type(e).__name__}: {e}")
                    # Продолжаем с исходным chat_id для проверки через getChatMember

            # 3) Если chat_id так и не появился — используем raw_id для проверки
            if chat_id is None and raw_id:
                chat_id = raw_id
                details.append(f"[{title}] using_raw_id: {raw_id}")

            # 4) Финальная проверка членства
            channel_ok = False
            try:
                if chat_id and _is_member_local(int(chat_id), int(user_id)):
                    details.append(f"[{title}] local=OK")
                    channel_ok = True
                else:
                    ok_api, dbg, status = await tg_get_chat_member(client, int(chat_id), int(user_id))
                    details.append(f"[{title}] {dbg}")
                    
                    # КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: проверяем статус, а не ok_api
                    if status in {"creator", "administrator", "member"}:
                        channel_ok = True
                    else:
                        channel_ok = False
                        # ВСЕГДА отдаем username+url, чтобы фронт мог показать ссылку
                        need.append({
                            "title": title,
                            "username": uname,
                            "url": f"https://t.me/{uname}" if uname else f"https://t.me/{chat_id}",
                        })
            except Exception as e:
                details.append(f"[{title}] get_chat_member_failed: {type(e).__name__}: {e}")
                channel_ok = False
                need.append({
                    "title": title,
                    "username": uname,
                    "url": f"https://t.me/{uname}" if uname else f"https://t.me/{chat_id}",
                })

            if not channel_ok:
                is_ok_overall = False

    print(f"[DIAGNOSTICS] user_id={user_id}, is_ok_overall={is_ok_overall}")
    print(f"[DIAGNOSTICS] need list: {need}")
    print(f"[DIAGNOSTICS] details: {details}")

    done = is_ok_overall 

    # 5) если всё ок — вернём уже выданный билет (если есть), иначе попробуем выдать новый
    ticket = None
    if done:
        try:
            with _db() as db:
                # ВАЖНО: сначала ищем существующий билет
                row = db.execute(
                    "SELECT ticket_code FROM entries WHERE giveaway_id=? AND user_id=?",
                    (gid, user_id),
                ).fetchone()
                if row:
                    ticket = row["ticket_code"]
                    print(f"[CHECK] ✅ Найден существующий билет: {ticket} для user_id={user_id}, gid={gid}")
                else:
                    print(f"[CHECK] 📝 Билет не найден, создаем новый для user_id={user_id}, gid={gid}")
                    import random, string
                    alphabet = string.ascii_uppercase + string.digits
                    # до 8 попыток, чтобы избежать редкой коллизии кода
                    for attempt in range(8):
                        code = "".join(random.choices(alphabet, k=6))
                        try:
                            db.execute(
                                "INSERT INTO entries(giveaway_id, user_id, ticket_code, prelim_ok, prelim_checked_at) "
                                "VALUES (?, ?, ?, 1, strftime('%Y-%m-%d %H:%M:%f','now'))",
                                (gid, user_id, code),
                            )
                            db.commit()
                            ticket = code
                            print(f"[CHECK] ✅ Создан новый билет: {ticket} (попытка {attempt + 1})")
                            break
                        except Exception as e:
                            if "UNIQUE constraint failed" in str(e):
                                print(f"[CHECK] ⚠️ Коллизия билета {code}, пробуем другой")
                                continue
                            else:
                                raise e
        except Exception as e:
            print(f"[CHECK] ❌ Ошибка при работе с билетом: {e}")
            details.append(f"ticket_issue_error: {type(e).__name__}: {e}")

    # 6) итоговый ответ
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

    # Проверяем есть ли уже билет ПРЕЖДЕ проверки подписки
    try:
        with _db() as db:
            row = db.execute(
                "SELECT ticket_code FROM entries WHERE giveaway_id=? AND user_id=?",
                (gid, user_id),
            ).fetchone()
            if row:
                print(f"[CLAIM] ✅ Пользователь уже имеет билет: {row['ticket_code']}")
                return JSONResponse({
                    "ok": True, 
                    "done": True, 
                    "ticket": row["ticket_code"], 
                    "details": ["Already have ticket - skipping subscription check"]
                })
    except Exception as e:
        print(f"[CLAIM] ⚠️ Ошибка при проверке существующего билета: {e}")

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
            username = (ch.get("username") or "").lstrip("@") or None
            try:
                chat_id = int(ch.get("chat_id"))
                if _is_member_local(chat_id, user_id):
                    is_ok = True
                else:
                    ok_check, dbg, status = await tg_get_chat_member(client, chat_id, user_id)
                    details.append(f"[{title}] {dbg}")
                    is_ok = status in {"creator", "administrator", "member"}
            except Exception as e:
                details.append(f"[{title}] claim_check_failed: {type(e).__name__}: {e}")
                is_ok = False

            if not is_ok:
                # ВСЕГДА отдаем username+url
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
            # Еще раз проверяем (на случай параллельных запросов)
            row = db.execute(
                "SELECT ticket_code FROM entries WHERE giveaway_id=? AND user_id=?",
                (gid, user_id),
            ).fetchone()
            if row:
                print(f"[CLAIM] ✅ Билет уже существует: {row['ticket_code']}")
                return JSONResponse({"ok": True, "done": True, "ticket": row["ticket_code"], "details": details})

            print(f"[CLAIM] 📝 Создаем новый билет для user_id={user_id}, gid={gid}")
            import random, string
            alphabet = string.ascii_uppercase + string.digits
            
            for attempt in range(12):  # увеличим попытки до 12
                code = "".join(random.choices(alphabet, k=6))
                try:
                    db.execute(
                        "INSERT INTO entries(giveaway_id, user_id, ticket_code, prelim_ok, prelim_checked_at) "
                        "VALUES (?, ?, ?, 1, strftime('%Y-%m-%d %H:%M:%f','now'))",
                        (gid, user_id, code),
                    )
                    db.commit()
                    print(f"[CLAIM] ✅ Успешно создан билет: {code}")
                    return JSONResponse({"ok": True, "done": True, "ticket": code, "details": details})
                except Exception as e:
                    if "UNIQUE constraint failed" in str(e):
                        print(f"[CLAIM] ⚠️ Коллизия билета {code}, попытка {attempt + 1}")
                        continue
                    else:
                        print(f"[CLAIM] ❌ Ошибка базы данных: {e}")
                        raise e
            
            print(f"[CLAIM] ❌ Не удалось создать уникальный билет после 12 попыток")
            return JSONResponse({"ok": False, "done": True, "reason": "ticket_issue_failed_after_retries"}, status_code=500)
            
    except Exception as e:
        print(f"[CLAIM] ❌ Критическая ошибка при создании билета: {e}")
        return JSONResponse({"ok": False, "reason": f"db_write_error: {type(e).__name__}: {e}"}, status_code=500)


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
    Валидация для Telegram Mini Apps - УПРОЩЕННАЯ ВЕРСИЯ
    """
    try:
        if not init_data:
            return None
            
        print(f"[CHECK][mini] raw_init_data: {init_data}")
        
        # ВРЕМЕННО: пропускаем проверку подписи для тестирования
        # Парсим данные чтобы получить user_id
        parsed = dict(parse_qsl(init_data, keep_blank_values=True))
        
        user_json_encoded = parsed.get("user")
        if not user_json_encoded:
            return None
            
        user_json = unquote(user_json_encoded)
        user = json.loads(user_json)
        
        if not user or "id" not in user:
            return None
            
        print(f"[CHECK][mini] USER EXTRACTED: id={user['id']}")
        return {
            "user_parsed": user,
            "start_param": unquote(parsed.get("start_param", "")) if parsed.get("start_param") else None
        }
        
    except Exception as e:
        print(f"[CHECK][mini] ERROR: {e}")
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

# --- helper: getChat c поддержкой @username / ссылок / числовых id
async def tg_get_chat(client: AsyncClient, ref: str | int) -> dict:
    """
    Возвращает объект chat по username (@name), t.me/ссылке или числовому chat_id.
    Бросает Exception с понятным текстом, если Telegram API вернул ошибку.
    """
    # Нормализуем вход
    if isinstance(ref, int):
        chat_ref = ref
    else:
        s = str(ref).strip()
        s = s.replace("https://t.me/", "").replace("t.me/", "")
        if s.startswith("@"):
            s = s[1:]
        # если осталась чистая цифра — это id, иначе имя
        chat_ref = int(s) if s.lstrip("-").isdigit() else f"@{s}"

    r = await client.get(f"{TELEGRAM_API}/getChat", params={"chat_id": chat_ref}, timeout=10.0)
    data = r.json()
    if not data.get("ok"):
        desc = data.get("description", "")
        code = data.get("error_code")
        raise RuntimeError(f"getChat failed: {code} {desc}")

    return data["result"]

# --- helper: аккуратная проверка членства с логами
async def tg_get_chat_member(client: AsyncClient, chat_id: int, user_id: int) -> tuple[bool, str, str]:
    """
    Проверка членства с улучшенной обработкой ошибок и статусов
    Возвращает (ok: bool, debug: str, status: str)
    """
    try:
        print(f"[DEBUG] Checking membership: chat_id={chat_id}, user_id={user_id}")
        
        r = await client.get(
            f"{TELEGRAM_API}/getChatMember",
            params={"chat_id": chat_id, "user_id": user_id},
            timeout=10.0
        )
        data = r.json()
        print(f"[DEBUG] getChatMember response: {data}")
        
    except Exception as e:
        print(f"[ERROR] Network error: {e}")
        return False, f"network_error: {type(e).__name__}: {e}", "error"

    if not data.get("ok"):
        error_code = data.get('error_code')
        description = data.get('description', '')
        
        print(f"[ERROR] Telegram API error: {error_code} - {description}")
        
        # Анализ ошибок
        if "bot was kicked" in description.lower():
            return False, "bot_kicked_from_chat", "kicked"
        elif "bot is not a member" in description.lower():
            return False, "bot_not_member_of_chat", "left"
        elif "chat not found" in description.lower():
            return False, "chat_not_found", "left"
        elif "user not found" in description.lower():
            return False, "user_not_found_in_chat", "left"
        elif "not enough rights" in description.lower():
            return False, "bot_not_admin", "restricted"
        elif error_code == 400:
            return False, f"bad_request: {description}", "error"
        elif error_code == 403:
            return False, f"forbidden: {description}", "restricted"
        else:
            return False, f"tg_api_error: {error_code} {description}", "error"

    result = data["result"]
    status = (result.get("status") or "").lower()
    
    print(f"[DEBUG] User status: {status}")
    
    # КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: возвращаем статус как третье значение
    debug_info = f"status={status}"
    
    # Дополнительная диагностика для restricted
    if status == "restricted":
        is_member = result.get("is_member", False)
        debug_info += f", is_member={is_member}"
        return is_member, debug_info, status
    
    # Для остальных статусов определяем доступ
    is_ok = status in {"creator", "administrator", "member"}
    
    print(f"[DEBUG] Final result: {debug_info}, is_ok={is_ok}")
    return is_ok, debug_info, status


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

# Эндпоинт для полной диагностики
@app.post("/api/debug/full_check")
async def debug_full_check(req: Request):
    try:
        body = await req.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "bad_json"}, status_code=400)

    user_id = int(body.get("user_id") or 0)
    gid = body.get("gid") or "test"
    
    if not user_id:
        return JSONResponse({"ok": False, "error": "bad_user_id"}, status_code=400)

    # Получаем каналы для розыгрыша
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
        return JSONResponse({"ok": False, "error": f"db_error: {e}"}, status_code=500)

    results = []
    async with AsyncClient(timeout=10.0) as client:
        for ch in channels:
            chat_id = ch.get("chat_id")
            title = ch.get("title") or "канал"
            
            try:
                # Проверяем через Telegram API
                ok_api, dbg, status = await tg_get_chat_member(client, int(chat_id), int(user_id))
                results.append({
                    "channel": title,
                    "chat_id": chat_id,
                    "status": status,
                    "is_member": ok_api,
                    "debug": dbg,
                    "allowed": status in {"creator", "administrator", "member"}
                })
            except Exception as e:
                results.append({
                    "channel": title,
                    "chat_id": chat_id,
                    "error": str(e)
                })

    return JSONResponse({"ok": True, "user_id": user_id, "gid": gid, "results": results})

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
            ok, dbg, status = await tg_get_chat_member(client, int(chat_id), int(user_id))
            return JSONResponse({"ok": True, "result": {"is_member": ok, "debug": dbg, "status": status, "chat_id": int(chat_id)}})
        except Exception as e:
            return JSONResponse({"ok": False, "error": f"{type(e).__name__}: {e}"}, status_code=500)