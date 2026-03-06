import logging
import uuid
import mimetypes
import boto3
import asyncio, os, hashlib, random, string
from datetime import datetime, timezone, timedelta
from contextlib import asynccontextmanager
from pathlib import Path
from io import BytesIO
from html import escape
from html import escape as _escape
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from urllib.parse import urlencode
import time
import json

from functools import lru_cache

from aiogram.enums import ChatType
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import ChatMemberUpdated, ChatJoinRequest
from aiogram import Bot, Dispatcher, F
import aiogram.types as types
from aiogram.filters import Command, StateFilter
from aiogram.types import (Message, CallbackQuery, InlineKeyboardMarkup,
                           InlineKeyboardButton, InputMediaPhoto,
                           PreCheckoutQuery)
from aiogram.types import WebAppInfo
from aiogram.types import BotCommand
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, KeyboardButtonRequestChat, ChatAdministratorRights
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import LinkPreviewOptions

from sqlalchemy import text as _sqltext
from sqlalchemy import text as stext
from sqlalchemy import (text, String, Integer, BigInteger,
                        Boolean, DateTime, ForeignKey)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import (create_async_engine, async_sessionmaker)

from html.parser import HTMLParser
from aiogram.types import MessageEntity

# 🔧 ПРИНУДИТЕЛЬНАЯ ЗАГРУЗКА ASYNCPG ДЛЯ ИЗБЕЖАНИЯ КОНФЛИКТА
import sys
venv_path = "/root/telegram-giveaway-prizeme-bot/venv/lib/python3.12/site-packages"
if venv_path not in sys.path:
    sys.path.insert(0, venv_path)
try:
    import asyncpg
    print("✅ asyncpg принудительно загружен из venv")
except ImportError as e:
    print(f"❌ Ошибка загрузки asyncpg: {e}")
    sys.exit(1)

from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger

import aiohttp
from aiohttp import web
from aiohttp import ClientSession, ClientTimeout, FormData
import httpx

def normalize_datetime(dt: datetime) -> datetime:

    from datetime import timezone as _tz  # локальный алиас, чтобы не путаться

    if dt.tzinfo is None:
        # Наивную дату трактуем как «московскую»
        local_dt = dt.replace(tzinfo=MSK_TZ)
    else:
        # Любую aware-дату сначала приводим к Москве
        local_dt = dt.astimezone(MSK_TZ)

    # Для внутренних расчётов и планировщика используем всегда UTC
    return local_dt.astimezone(_tz.utc)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
load_dotenv()


# --- ОТДЕЛЬНЫЙ ЛОГГЕР ДЛЯ МЕХАНИК ---
mechanics_logger = logging.getLogger('mechanics')
mechanics_logger.setLevel(logging.DEBUG)

# Обработчик для файла
try:
    mechanics_handler = logging.FileHandler('/var/log/prizeme/mechanics.log')
    mechanics_handler.setLevel(logging.DEBUG)
    
    # Форматирование логов
    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    mechanics_handler.setFormatter(formatter)
    
    mechanics_logger.addHandler(mechanics_handler)
    
    # Не дублируем логи в корневой логгер
    mechanics_logger.propagate = False
    
except Exception as e:
    print(f"⚠️ Не удалось создать файловый логгер для механик: {e}")
    # Используем стандартный логгер как fallback
    mechanics_logger = logging.getLogger()

# --- Конец блока логирования механик ---

MEDIA_BASE_URL = os.getenv("MEDIA_BASE_URL", "https://media.prizeme.ru")
WEBAPP_BASE_URL = os.getenv("WEBAPP_BASE_URL", "https://prizeme.ru")

DESCRIPTION_PROMPT = (
    "✏️ <b>Введите текст подробного описания розыгрыша:</b>\n\n"
    "Можно использовать не более 2500 символов, премиум-эмодзи пока недоступны (скоро подключим)\n\n"
    "<i>Подробно опишите условия розыгрыша для ваших подписчиков, "
    "после начала розыгрыша введённый текст будет опубликован на всех связанных с ним каналах</i>")

MEDIA_QUESTION = "📷 Хотите ли добавить изображение / gif / видео для текущего розыгрыша?"

MEDIA_INSTRUCTION = (
    "📷 <b>Отправьте изображение / <i>gif</i> / видео для текущего розыгрыша</b>\n\n"
    "<i>Используйте стандартную доставку. Не отправляйте \"несжатым\" способом (НЕ как документ)</i>\n\n"
    "<b>Внимание!</b> Видео должно быть в формате MP4, а его размер не должен превышать 5 МБ"
)

BTN_GIVEAWAYS = "Мои розыгрыши"
BTN_CREATE = "Создать розыгрыш"
BTN_ADD_CHANNEL = "Добавить канал"
BTN_ADD_GROUP = "Добавить группу"
BTN_SUBSCRIPTIONS = "Буст"
BTN_CHANNELS = "Мои каналы"
BOT_USERNAME: str | None = None

# === callbacks for draft flow ===
CB_PREVIEW_CONTINUE = "preview:continue"
CB_TO_CHANNELS_MENU = "draft:to_channels"
CB_OPEN_CHANNELS    = "channels:open"
CB_CHANNEL_ADD      = "channels:add"
CB_CHANNEL_START    = "raffle:start"
CB_CHANNEL_SETTINGS = "raffle:settings"

MSK_TZ = ZoneInfo("Europe/Moscow")

logger_media = logging.getLogger("media")
logger_media.setLevel(logging.DEBUG)

BOT_TOKEN = os.getenv("BOT_TOKEN")
DEFAULT_TZ = os.getenv("TZ", "Europe/Moscow")
S3_ENDPOINT = os.getenv("S3_ENDPOINT")
S3_BUCKET   = os.getenv("S3_BUCKET")
S3_KEY      = os.getenv("S3_ACCESS_KEY")
S3_SECRET   = os.getenv("S3_SECRET_KEY")
S3_REGION   = os.getenv("S3_REGION", "ru-1")

t = os.getenv("BOT_TOKEN","")
logging.info("[BOOT] BOT_TOKEN_SHA256=%s", hashlib.sha256(t.encode()).hexdigest())

# Тексты экранов
CONNECT_INVITE_TEXT = (
    "🌟 <b>Ваш розыгрыш создан, осталось только запустить!</b>\n\n"
    "<i>Подключите минимум 1 канал/группу, чтобы можно было запустить розыгрыш</i>"
)

# Инфо-блок про подключение канала/группы (HTML)
ADD_CHAT_HELP_HTML = (
    "Подключение канала / группы необходимо для проведения розыгрыша, без этого действия розыгрыш провести не удастся, "
    "будьте внимательны и подключайте те каналы / группы, в которых действительно хотите проводить розыгрыш.\n\n"
    "При добавлении бота @prizeme_official_bot в канал / группу Вы даёте право на следующие действия "
    "(не переживайте, это минимальный набор прав без возможности реального управления каналом / группой):\n\n"
    "• Публикация сообщений\n"
    "• Редактирование сообщений\n"
    "• Добавление подписчиков\n"
    "• Создание пригласительных ссылок\n\n"
    "<b>Нажмите на соответствующую кнопку под строкой поиска для подключения канала / группы к боту.</b>"
)

# --- Константы для количества победителей ---
WINNERS_LIMIT_PREMIUM = 100
WINNERS_LIMIT_STANDARD = 30

# ---- Другое ----
def kb_add_cancel() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Отмена", callback_data="add:cancel")
    kb.adjust(1)
    return kb.as_markup()

if not all([S3_ENDPOINT, S3_BUCKET, S3_KEY, S3_SECRET]):
    logging.warning("S3 env not fully set — uploads will fail.")

# --- Функция безопасного HTML ---
def safe_html_text(html_text: str, max_length: int = 2500) -> str:
    """
    Безопасно обрезает HTML-текст до максимальной длины,
    сохраняя целостность тегов и премиум эмодзи.
    """
    if len(html_text) <= max_length:
        return html_text
    
    # Простое обрезание
    return html_text[:max_length] + "..."

def message_text_to_html_with_entities(text: str, entities: list) -> str:
    """
    Конвертирует Telegram entities (включая custom_emoji) в HTML.
    Поддерживает: bold/italic/underline/strikethrough/spoiler/code/pre/text_link/url/custom_emoji.
    """
    if not text:
        return ""

    # Собираем events открытия/закрытия тегов по позициям
    opens: dict[int, list[tuple[int, str]]] = {}
    closes: dict[int, list[tuple[int, str]]] = {}

    def add_event(offset: int, end: int, prio: int, open_tag: str, close_tag: str):
        opens.setdefault(offset, []).append((prio, open_tag))
        closes.setdefault(end, []).append((prio, close_tag))

    for ent in (entities or []):
        t = getattr(ent, "type", None)
        off16 = int(getattr(ent, "offset", 0))
        ln16  = int(getattr(ent, "length", 0))
        end16 = off16 + ln16

        off = _utf16_to_py_index(text, off16)
        end = _utf16_to_py_index(text, end16)

        if end <= off:
            continue
        if ln16 <= 0:
            continue

        if t == "bold":
            add_event(off, end, 10, "<b>", "</b>")
        elif t == "italic":
            add_event(off, end, 20, "<i>", "</i>")
        elif t == "underline":
            add_event(off, end, 30, "<u>", "</u>")
        elif t == "strikethrough":
            add_event(off, end, 40, "<s>", "</s>")
        elif t == "spoiler":
            add_event(off, end, 50, "<span class=\"tg-spoiler\">", "</span>")
        elif t == "code":
            add_event(off, end, 60, "<code>", "</code>")
        elif t == "pre":
            # язык (optional)
            lang = getattr(ent, "language", None)
            if lang:
                add_event(off, end, 70, f"<pre><code class=\"language-{_escape(str(lang))}\">", "</code></pre>")
            else:
                add_event(off, end, 70, "<pre>", "</pre>")
        elif t == "text_link":
            url = getattr(ent, "url", None)
            if url:
                add_event(off, end, 80, f"<a href=\"{_escape(str(url))}\">", "</a>")
        elif t == "url":
            # auto-url: просто обернём текст в ссылку на него же
            # (внутри HTML Telegram нормально принимает)
            # Важно: сам URL берём из среза текста
            # Теги поставим позднее в проходе по символам — тут зададим "заглушку"
            # Реализуем как text_link на self:
            url_text = text[off:end]
            add_event(off, end, 80, f"<a href=\"{_escape(url_text)}\">", "</a>")
        elif t == "custom_emoji":
            emoji_id = getattr(ent, "custom_emoji_id", None)
            if emoji_id:
                add_event(off, end, 90, f"<tg-emoji emoji-id=\"{_escape(str(emoji_id))}\">", "</tg-emoji>")
        else:
            # Остальные типы можно добавлять по мере необходимости
            pass

    # Важно: закрытия должны идти в обратном порядке вложенности
    for k in closes:
        closes[k].sort(key=lambda x: -x[0])
    for k in opens:
        opens[k].sort(key=lambda x: x[0])

    out: list[str] = []
    n = len(text)
    for i in range(n + 1):
        if i in closes:
            for _, tag in closes[i]:
                out.append(tag)
        if i == n:
            break
        if i in opens:
            for _, tag in opens[i]:
                out.append(tag)

        ch = text[i]
        # переносы
        if ch == "\n":
            out.append("\n")
        else:
            out.append(_escape(ch))

    return "".join(out)

def html_with_emojis_to_text_and_entities(html_text: str):
    """
    Преобразует HTML с <tg-emoji> обратно в текст и Telegram entities
    Возвращает: (text, entities)
    """
    if not html_text or '<tg-emoji' not in html_text:
        return html_text, []
    
    import re
    
    # Регулярное выражение для поиска тегов <tg-emoji>
    emoji_pattern = r'<tg-emoji\s+emoji-id="([^"]+)">([^<]+)</tg-emoji>'
    
    text_parts = []
    entities = []
    current_position = 0
    
    # Заменяем все теги эмодзи на символ эмодзи
    def replace_emoji(match):
        nonlocal current_position, entities
        
        emoji_id = match.group(1)
        emoji_char = match.group(2)
        start_pos = current_position
        
        # Добавляем entity для кастомного эмодзи
        entities.append({
            'type': 'custom_emoji',
            'offset': start_pos,
            'length': len(emoji_char),
            'custom_emoji_id': emoji_id
        })
        
        current_position += len(emoji_char)
        return emoji_char
    
    # Удаляем все теги <tg-emoji> и заменяем на символы эмодзи
    text = re.sub(emoji_pattern, replace_emoji, html_text)
    
    # Убираем остальные HTML теги (сохраняем только текст)
    text = re.sub(r'<[^>]+>', '', text)
    
    # Убираем HTML entities
    import html
    text = html.unescape(text)
    
    return text, entities

def _utf16_pos_from_py_text(s: str, py_index: int) -> int:
    """Позиция в UTF-16 code units для первых py_index символов строки."""
    cur16 = 0
    for ch in s[:py_index]:
        cur16 += _utf16_len(ch)
    return cur16


class _HtmlToEntitiesParser(HTMLParser):
    """
    Парсер ограниченного Telegram-HTML в (text + entities).
    Поддержка:
      <b>, <i>, <u>, <s>, <code>, <pre>, <a href="...">, <span class="tg-spoiler">,
      <tg-emoji emoji-id="...">X</tg-emoji>
    """
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.entities: list[MessageEntity] = []
        # stack элементов: (tag_type, start_utf16, extra)
        self.stack: list[tuple[str, int, dict]] = []

    @property
    def text(self) -> str:
        return "".join(self.out)

    def _cur_utf16(self) -> int:
        # текущая длина в UTF-16 units
        return sum(_utf16_len(ch) for ch in self.text)

    def handle_starttag(self, tag: str, attrs):
        attrs_d = dict(attrs or [])
        t = tag.lower()

        if t == "b":
            self.stack.append(("bold", self._cur_utf16(), {}))
        elif t == "i":
            self.stack.append(("italic", self._cur_utf16(), {}))
        elif t == "u":
            self.stack.append(("underline", self._cur_utf16(), {}))
        elif t == "s":
            self.stack.append(("strikethrough", self._cur_utf16(), {}))
        elif t == "code":
            self.stack.append(("code", self._cur_utf16(), {}))
        elif t == "pre":
            # language не поддерживаем тут (у тебя он и так не используется при вводе)
            self.stack.append(("pre", self._cur_utf16(), {}))
        elif t == "span":
            cls = (attrs_d.get("class") or "").strip()
            if cls == "tg-spoiler":
                self.stack.append(("spoiler", self._cur_utf16(), {}))
        elif t == "a":
            href = attrs_d.get("href")
            if href:
                self.stack.append(("text_link", self._cur_utf16(), {"url": href}))
        elif t == "tg-emoji":
            emoji_id = attrs_d.get("emoji-id")
            if emoji_id:
                self.stack.append(("custom_emoji", self._cur_utf16(), {"custom_emoji_id": emoji_id}))
        # прочие теги игнорируем

    def handle_endtag(self, tag: str):
        t = tag.lower()

        # Закрываем последний соответствующий тип (с конца стека)
        tag_map = {
            "b": "bold",
            "i": "italic",
            "u": "underline",
            "s": "strikethrough",
            "code": "code",
            "pre": "pre",
            "a": "text_link",
            "tg-emoji": "custom_emoji",
            "span": "spoiler",
        }
        want = tag_map.get(t)
        if not want:
            return

        # Ищем с конца
        for idx in range(len(self.stack) - 1, -1, -1):
            ent_type, start, extra = self.stack[idx]
            if ent_type != want:
                continue

            end = self._cur_utf16()
            length = end - start
            # Удаляем со стека
            self.stack.pop(idx)

            if length <= 0:
                return

            if ent_type == "text_link":
                self.entities.append(
                    MessageEntity(type="text_link", offset=start, length=length, url=extra["url"])
                )
            elif ent_type == "custom_emoji":
                self.entities.append(
                    MessageEntity(type="custom_emoji", offset=start, length=length, custom_emoji_id=extra["custom_emoji_id"])
                )
            else:
                self.entities.append(
                    MessageEntity(type=ent_type, offset=start, length=length)
                )
            return

    def handle_data(self, data: str):
        if not data:
            return
        self.out.append(data)

    def handle_entityref(self, name):
        # convert_charrefs=True обычно уже обработает, но оставим на всякий случай
        self.out.append(f"&{name};")

    def handle_charref(self, name):
        self.out.append(f"&#{name};")


def html_to_text_and_entities(html_text: str) -> tuple[str, list[MessageEntity]]:
    """
    Конвертирует HTML (включая <tg-emoji>) в текст + entities.
    Важно: offsets/length в UTF-16, как требует Telegram.
    """
    if not html_text:
        return "", []

    p = _HtmlToEntitiesParser()
    p.feed(html_text)
    p.close()

    # Telegram ожидает entities в любом порядке, но лучше стабильный: по offset
    ents = sorted(p.entities, key=lambda e: (e.offset, e.length))
    return p.text, ents


def _utf16_len(ch: str) -> int:
    # символы вне BMP (например многие emoji) занимают 2 code units в UTF-16
    return 2 if ord(ch) > 0xFFFF else 1

def _utf16_to_py_index(s: str, utf16_pos: int) -> int:
    """
    Перевод позиции из UTF-16 code units (как в Telegram entities)
    в индекс Python-строки (codepoints).
    """
    if utf16_pos <= 0:
        return 0

    cur16 = 0
    for i, ch in enumerate(s):
        nxt = cur16 + _utf16_len(ch)
        if nxt > utf16_pos:
            return i
        cur16 = nxt
        if cur16 == utf16_pos:
            return i + 1
    return len(s)

# --- Для ссылок формата https://t.me/c/<internal>/<msg_id> ---
def _tg_internal_chat_id(chat_id: int) -> int | None:
    try:
        cid = abs(int(chat_id))
    except Exception:
        return None

    if cid < 1_000_000_000_000:
        return None

    internal = cid - 1_000_000_000_000
    return internal if internal > 0 else None

# --- Возвращает ссылку на пост с розыгрышем в ПЕРВОМ подключенном канале/группе ---
async def get_first_giveaway_post_url(gid: int) -> str | None:
    try:
        async with session_scope() as s:
            row = (await s.execute(
                text("""
                    SELECT oc.chat_id, oc.username, gc.message_id
                    FROM giveaway_channels gc
                    JOIN organizer_channels oc ON oc.id = gc.channel_id
                    WHERE gc.giveaway_id = :gid
                    ORDER BY gc.id ASC
                    LIMIT 1
                """),
                {"gid": gid},
            )).first()

        if not row:
            return None

        chat_id, username, message_id = row
        if not message_id:
            return None

        if username:
            uname = str(username).lstrip("@")
            return f"https://t.me/{uname}/{int(message_id)}"

        internal = _tg_internal_chat_id(int(chat_id))
        if not internal:
            return None
        return f"https://t.me/c/{internal}/{int(message_id)}"

    except Exception as e:
        logging.warning("Failed to build giveaway post url for gid=%s: %s", gid, e)
        return None

# --- HTML-строка: либо <a href="...">title</a>, либо просто экранированный title ---
async def format_giveaway_title_link(gid: int, title: str) -> str:
    url = await get_first_giveaway_post_url(gid)
    title_html = escape(title or "")
    if url:
        return f'<a href="{url}">{title_html}</a>'
    return title_html


# --- Функция очистки текста от пользовательских ссылок ---
class TextPreviewCleaner:
    """
    УЛУЧШЕННАЯ СИСТЕМА: разделяет превью медиа (работает) и пользовательских ссылок (отключается)
    """
    @staticmethod
    def contains_user_links(html_text: str) -> bool:
        """
        Проверяет есть ли в тексте пользовательские ссылки (не наши медиа)
        Теперь работает корректно с HTML-разметкой
        """
        import re
        
        # Наши медиа ссылки имеют определенные паттерны
        our_media_patterns = [
            f"{MEDIA_BASE_URL}/uploads/",
            f"{S3_ENDPOINT}/{S3_BUCKET}/",
            r"https?://[^/]+/uploads/\d{4}/\d{2}/\d{2}/[a-f0-9-]+\.\w+",  # наш uploads паттерн
        ]
        
        # Ищем все ссылки в HTML (теперь корректно обрабатываем HTML-теги)
        link_pattern = r'<a\s+[^>]*href="([^"]+)"[^>]*>'
        links = re.findall(link_pattern, html_text)
        
        if not links:
            return False  # Нет ссылок вообще
        
        # Проверяем каждую найденную ссылку
        for link in links:
            is_our_media = False
            for pattern in our_media_patterns:
                if re.search(pattern, link):
                    is_our_media = True
                    break
            
            # Если найдена хотя бы одна НЕ наша ссылка - возвращаем True
            if not is_our_media:
                return True
        
        return False  # Все ссылки - наши медиа
    
    # --- Возвращает (очищенный_текст, нужно_ли_отключить_превью) ---
    @staticmethod
    def clean_text_preview(html_text: str, has_media: bool = False) -> tuple[str, bool]:
        
        # 🔍 ДИАГНОСТИКА ПРЕМИУМ-ЭМОДЗИ
        logging.info(f"🔍 [CLEAN_TEXT_DEBUG] Входной html_text содержит <tg-emoji>: {'<tg-emoji' in html_text}")
        logging.info(f"🔍 [CLEAN_TEXT_DEBUG] Входной html_text первые 100 символов: {html_text[:100]}")

        if has_media:
            # ЕСТЬ МЕДИА - НИКОГДА не отключаем превью, чтобы работала фиолетовая рамка
            return html_text, False
        else:
            # НЕТ МЕДИА - отключаем превью только если есть пользовательские ссылки
            if TextPreviewCleaner.contains_user_links(html_text):
                return html_text, True
            else:
                return html_text, False

# Создаем экземпляр
text_preview_cleaner = TextPreviewCleaner()


# --- Тексты экранов_2 ---

def build_connect_invite_kb(event_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    # NB: в callback передаём id розыгрыша, чтобы потом понимать, к какому событию подключаем каналы
    kb.button(text="Добавить канал/группу", callback_data=f"raffle:connect_channels:{event_id}")
    return kb.as_markup()

# Экран с уже подключенными каналами и действиями
def build_connect_channels_text(
    event_title: str | None = None,
    attached: list[tuple[str, str | None, int]] | None = None,
) -> str:
    """
    Собирает "серый" текстовый блок БЕЗ кликабельных ссылок на каналы
    и БЕЗ лишних пустых строк.
    """
    # Очищаем список от пустых значений
    clean_attached = []
    if attached:
        for item in attached:
            title, username, chat_id = item
            if title and title.strip():  # Проверяем, что title не пустой
                clean_attached.append((title.strip(), username, chat_id))
    
    title = (
        f"🔗 Подключение канала к розыгрышу \"{event_title}\""
        if event_title else
        "🔗 Подключение канала к розыгрышу"
    )

    lines = [
        title,
        "",
        "Подключить канал к розыгрышу сможет только администратор, "
        "который обладает достаточным уровнем прав в прикреплённом канале",
        "",
        "<b>Подключённые каналы:</b>",
    ]

    if clean_attached:
        for i, (t, uname, _cid) in enumerate(clean_attached, start=1):
            # ИЗМЕНЕНИЕ: показываем только название канала, без ссылки
            lines.append(f"{i}. {t}")
    else:
        lines.append("— пока нет")

    return "\n".join(lines)

def build_channels_menu_kb(
    event_id: int,
    channels: list[tuple[int, str]],
    attached_ids: set[int] | None = None
) -> InlineKeyboardMarkup:
    """
    channels: список (organizer_channel_id, title)
    attached_ids: ids organizer_channels, уже прикреплённых к текущему розыгрышу
    """
    attached_ids = attached_ids or set()
    kb = InlineKeyboardBuilder()

    # Кнопки всех ранее подключённых к боту каналов/групп (вертикальным списком)
    for ch_id, title in channels:
        mark = "✅ " if ch_id in attached_ids else ""
        kb.button(
            text=f"{mark}{title}",
            callback_data=f"raffle:attach:{event_id}:{ch_id}"
        )
    if channels:
        kb.adjust(1)

    # Первая строка — две кнопки рядом: "Добавить канал" и "Добавить группу"
    kb.row(
        InlineKeyboardButton(text="Добавить канал", callback_data=f"raffle:add_channel:{event_id}"),
        InlineKeyboardButton(text="Добавить группу", callback_data=f"raffle:add_group:{event_id}")
    )

    # Отдельными строками, в заданном порядке
    kb.row(InlineKeyboardButton(text="➡️ Продолжить", callback_data=f"raffle:start:{event_id}"))

    return kb.as_markup()

# === Launch confirm helpers ===

def build_final_check_text() -> str:
    # формат как на твоём скриншоте
    return (
        "🚀 <b>Остался последний шаг и можно запускать розыгрыш</b>\n\n"
        "Выше показан блок с розыгрышем, убедитесь, что всё указано верно. "
        "Как только это сделаете, можете запускать розыгрыш, нажав на кнопку снизу\n\n"
        "<b><i>Внимание!</i></b> <i>После запуска пост с розыгрышем будет автоматически опубликован "
        "в подключённых каналах / группах к текущему розыгрышу, не редактируйте его после публикации вручную, после объявления результатов он вернется в изначальный вид</i>"
    )

def kb_launch_confirm(gid: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Запустить розыгрыш", callback_data=f"launch:do:{gid}")
    kb.button(text="Настройки розыгрыша", callback_data=f"raffle:settings_menu:{gid}")
    kb.button(text="Дополнительные механики", callback_data=f"raffle:mechanics:{gid}")
    kb.adjust(1)
    return kb.as_markup()

# --- Клавиатура меню настроек розыгрыша ---
def kb_settings_menu(gid: int, giveaway_title: str, context: str = "settings") -> InlineKeyboardMarkup:

    kb = InlineKeyboardBuilder()
    
    # Первая строка: две кнопки рядом
    kb.row(
        InlineKeyboardButton(text="Название", callback_data=f"settings:name:{gid}:{context}"),
        InlineKeyboardButton(text="Описание", callback_data=f"settings:desc:{gid}:{context}")
    )
    
    # Вторая строка: две кнопки рядом  
    kb.row(
        InlineKeyboardButton(text="Дата окончания", callback_data=f"settings:date:{gid}:{context}"),
        InlineKeyboardButton(text="Медиа", callback_data=f"settings:media:{gid}:{context}")
    )
    
    # Третья строка: одна кнопка
    kb.row(InlineKeyboardButton(text="Количество победителей", callback_data=f"settings:winners:{gid}:{context}"))
    
    # Четвертая строка: кнопка назад (теперь 4-я строка вместо 5-й)
    back_callback = f"settings:back:{gid}:{context}"
    kb.row(InlineKeyboardButton(text="⬅️ Назад", callback_data=back_callback))
    
    return kb.as_markup()


# Клавиатура под постом в канале: открываем WebApp по нашему домену, а не по t.me/startapp

def kb_public_participate(gid: int, *, for_channel: bool = False) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if for_channel:
        # В КАНАЛЫ — ТОЛЬКО URL-кнопка на t.me с startapp (web_app в каналах запрещён)
        global BOT_USERNAME
        url = f"https://t.me/{BOT_USERNAME}?startapp={gid}"
        kb.button(text="Участвовать", url=url)
    else:
        # В ЛИЧКЕ/ГРУППЕ можно открыть напрямую наш домен как WebApp
        webapp_url = f"{WEBAPP_BASE_URL}/miniapp/?tgWebAppStartParam={gid}"
        kb.button(text="Участвовать", web_app=WebAppInfo(url=webapp_url))
    return kb.as_markup()

def kb_public_participate_disabled() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    webapp_url = f"{WEBAPP_BASE_URL}/miniapp/?tgWebAppStartParam=demo"
    kb.button(text="Участвовать", web_app=WebAppInfo(url=webapp_url))
    return kb.as_markup()

def kb_finished_giveaway(gid: int, *, for_channel: bool = False) -> InlineKeyboardMarkup:
    """
    Клавиатура для завершенного розыгрыша - кнопка "Результаты"
    """
    kb = InlineKeyboardBuilder()
    
    if for_channel:
        # В КАНАЛАХ - только URL кнопка через бота
        global BOT_USERNAME
        url = f"https://t.me/{BOT_USERNAME}?startapp=results_{gid}"
        kb.button(text="🎲 Результаты", url=url)
    else:
        # В ЛИЧКЕ/ГРУППАХ - WebApp кнопка
        webapp_url = f"{WEBAPP_BASE_URL}/miniapp/?tgWebAppStartParam=results_{gid}"
        kb.button(text="🎲 Результаты", web_app=WebAppInfo(url=webapp_url))
    
    return kb.as_markup()

# Следующие функции

def format_endtime_prompt() -> str:
    now_msk = datetime.now(MSK_TZ)
    example = now_msk.strftime("%H:%M %d.%m.%Y")
    current = example  # показываем текущее время и как пример, и как "текущее"

    return (
        "⏰ <b>Укажите время окончания розыгрыша в формате (ЧЧ:ММ ДД.ММ.ГГГГ)</b>\n\n"
        f"<b>Например:</b> <code>{example}</code>\n\n"
        "⚠️ <b>Внимание!</b> Бот работает в соответствии с часовым поясом MSK (GMT+3).\n"
        f"Текущее время в боте: <code>{current}</code>"
    )

def kb_yes_no() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Да",  callback_data="media:yes")
    kb.button(text="Нет", callback_data="media:no")
    kb.adjust(2)
    return kb.as_markup()

def kb_skip_media() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Пропустить", callback_data="media:skip")
    kb.adjust(1)
    return kb.as_markup()

def _s3_client():
    return boto3.client(
        "s3",
        region_name=S3_REGION,
        endpoint_url=S3_ENDPOINT,
        aws_access_key_id=S3_KEY,
        aws_secret_access_key=S3_SECRET,
    )

def _make_s3_key(filename: str) -> str:
    """ключ в бакете: yyyy/mm/dd/<uuid>.<ext>"""
    now = datetime.utcnow()
    ext = (os.path.splitext(filename)[1] or "").lower() or ".bin"
    return f"{now:%Y/%m/%d}/{uuid.uuid4().hex}{ext}"

async def upload_bytes_to_s3(data: bytes, filename: str) -> tuple[str, str]:
    """
    Кладём байты в S3.
    Возвращаем (key, public_url), где key = yyyy/mm/dd/uuid.ext
    """
    logging.info(f"📤 UPLOAD_TO_S3 filename={filename}, bytes={len(data)}")
    key = _make_s3_key(filename)
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

    def _put():
        _s3_client().put_object(
            Bucket=S3_BUCKET,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
    await asyncio.to_thread(_put)
    logging.info(f"✅ S3_PUT_OK key={key}")

    public_url = f"{S3_ENDPOINT.rstrip('/')}/{S3_BUCKET}/{key}"
    return key, public_url


async def file_id_to_public_url_via_s3(bot: Bot, file_id: str, suggested_name: str) -> tuple[str, str]:
    tg_file = await bot.get_file(file_id)
    buf = BytesIO()
    await bot.download(tg_file, destination=buf)

    filename = os.path.basename(tg_file.file_path or "") or suggested_name
    if not os.path.splitext(filename)[1]:
        filename = suggested_name

    return await upload_bytes_to_s3(buf.getvalue(), filename)  # (key, s3_url)

def _make_preview_url(key: str, title: str, desc: str) -> str:
    # Без каких-либо параметров — только путь к файлу на нашем домене
    base = MEDIA_BASE_URL.rstrip("/")
    return f"{base}/uploads/{key}"

# Храним тип вместе с file_id в одном поле БД
def pack_media(kind: str, file_id: str) -> str:
    return f"{kind}:{file_id}"

def unpack_media(value: str | None) -> tuple[str|None, str|None]:
    if not value:
        return None, None
    if ":" in value:
        k, fid = value.split(":", 1)
        return k, fid
    # обратная совместимость: старое поле только с photo id
    return "photo", value


async def _fallback_preview_with_native_media(m: Message, state: FSMContext, kind: str, fid: str) -> None:
    """Показываем обычное медиа с подписью и той же клавиатурой (без линк-превью)."""
    data = await state.get_data()
    title = (data.get("title") or "").strip() or "Без названия"
    prizes = int(data.get("winners_count") or 0)

    caption = _compose_preview_text(title, prizes)
    # Порядок «сверху/снизу» в одном сообщении тут невозможен — это fallback.
    if kind == "photo":
        msg = await m.answer_photo(fid, caption=caption, reply_markup=kb_media_preview_with_memory(media_on_top=False))
    elif kind == "animation":
        msg = await m.answer_animation(fid, caption=caption, reply_markup=kb_media_preview_with_memory(media_on_top=False))
    else:
        msg = await m.answer_video(fid, caption=caption, reply_markup=kb_media_preview_with_memory(media_on_top=False))

    await state.update_data(
        media_preview_msg_id=msg.message_id,
        media_top=False,
        media_url=None,      # важный маркер: работаем в fallback-режиме
    )
    await state.set_state(CreateFlow.MEDIA_PREVIEW)

async def _ensure_link_preview_or_fallback(
    m: Message,
    state: FSMContext,
    kind: str,
    fid: str,
    filename: str
):
    logger_media.info("ensure_link_preview_or_fallback: kind=%s fid=%s", kind, fid)

    async def _do_once() -> tuple[str, str, str]:
        # 1) качаем из TG и кладем в S3
        key, s3_url = await file_id_to_public_url_via_s3(m.bot, fid, filename)
        # 2) собираем ссылку-прокладку на наш домен (uploads)
        data = await state.get_data()
        title = (data.get("title") or "").strip()
        desc  = (data.get("desc")  or "").strip()
        preview_url = _make_preview_url(key, title, desc)
        return key, s3_url, preview_url

    try:
        try:
            key, s3_url, preview_url = await _do_once()
        except Exception as e1:
            logger_media.warning("First try failed (%s), retrying once...", repr(e1))
            key, s3_url, preview_url = await _do_once()

        logger_media.info("✅ S3 uploaded: key=%s s3_url=%s preview=%s", key, s3_url, preview_url)

        # 3) кладём в state ИМЕННО preview_url (а не s3_url!)
        await state.update_data(media_url=preview_url)

        # 4) рисуем одно сообщение с линк-превью (фиолетовая рамка)
        await render_link_preview_message(m, state)
        await state.set_state(CreateFlow.MEDIA_PREVIEW)

    except Exception:
        logger_media.exception("Link-preview failed after retry; go fallback")
        await _fallback_preview_with_native_media(m, state, kind, fid)

def _compose_preview_text(
    title: str,
    prizes: int,
    *,
    desc_html: str | None = None,
    end_at_msk: str | None = None,
    days_left: int | None = None
) -> str:
    """
    Текст «серого блока» предпросмотра.
    Сохраняет пользовательское форматирование из message.html_text
    """
    lines = []
    if title:
        # БЕЗ escape() - сохраняем форматирование
        lines.append(title)
        lines.append("")

    if desc_html:
        # ВАЖНО: это уже HTML из message.html_text, не экранируем
        lines.append(desc_html)
        lines.append("")

    return "\n".join(lines)


def _compose_post_text(
    title: str,
    prizes: int,
    *,
    desc_html: str | None = None,
    end_at_msk: str | None = None,
    days_left: int | None = None
) -> str:
    """
    Текст для публикации в посте (БЕЗ двойной коррекции времени).
    Сохраняет пользовательское форматирование из message.html_text
    """
    lines = []
    if title:
        # БЕЗ escape() - сохраняем форматирование
        lines.append(title)
        lines.append("")

    if desc_html:
        # БЕЗ escape() - сохраняем пользовательское форматирование из message.html_text
        lines.append(desc_html)
        lines.append("")

    return "\n".join(lines)


async def render_link_preview_message(
    m: Message,
    state: FSMContext,
    *,
    reedit: bool = False
) -> None:
    """
    Рендерит одно сообщение с link preview:
    - «невидимая» ссылка <a href="...">&#8203;</a> запускает рамку от Telegram;
    - сверху текст: название (обычным), описание (как ввёл пользователь),
      участники/призы/дата (с русским "N дней").
    """
    data = await state.get_data()
    media = data.get("media_url")
    
    # Получаем позицию медиа: из state или из БД (при редактировании)
    media_top = bool(data.get("media_top") or False)
    
    # Если редактируем существующий розыгрыш, берем позицию из БД
    editing_gid = data.get("editing_giveaway_id")
    if editing_gid and not reedit:
        async with session_scope() as s:
            gw = await s.get(Giveaway, editing_gid)
            if gw and gw.media_position:
                media_top = (gw.media_position == "top")

    # title   = (data.get("title") or "").strip()
    prizes  = int(data.get("winners_count") or 0)

    # описание: храним исходный текст и его HTML-версию
    # text — это «как прислал пользователь»; мы экранировали только в предпросмотре описания.
    desc_raw  = (data.get("desc") or "").strip()
    # Разрешаем базовую разметку, поэтому НЕ экранируем здесь (смотри пункт в докстринге выше).
    desc_html = desc_raw

    # дата (строка для человека) и дни
    end_at_msk = data.get("end_at_msk_str")  # "HH:MM DD.MM.YYYY"
    days_left  = data.get("days_left")       # int

    txt = _compose_preview_text(
        "", prizes,
        desc_html=desc_html if desc_html else None,
        end_at_msk=end_at_msk,
        days_left=days_left
    )

    if not media:
        # ЕСЛИ НЕТ МЕДИА - ПРОВЕРЯЕМ ПОЛЬЗОВАТЕЛЬСКИЕ ССЫЛКИ
        cleaned_text, disable_preview = text_preview_cleaner.clean_text_preview(txt, has_media=False)
        send_kwargs = {
            "text": cleaned_text,
            "parse_mode": "HTML"
        }
        if disable_preview:
            send_kwargs["disable_web_page_preview"] = True
            
        await m.answer(**send_kwargs)
        return

    hidden_link = f'<a href="{media}"> </a>'

    if media_top:
        full = hidden_link + "\n" + txt
    else:
        full = txt + "\n\n" + hidden_link

    lp = LinkPreviewOptions(
        is_disabled=False,
        prefer_large_media=True,
        prefer_small_media=False, 
        show_above_text=media_top,
        url=media  # 🔄 ЯВНО указываем URL для превью
    )

    old_id = data.get("media_preview_msg_id")
    if reedit and old_id:
        try:
            await m.bot.edit_message_text(
                chat_id=m.chat.id,
                message_id=old_id,
                text=full,
                link_preview_options=lp,
                reply_markup=kb_media_preview_with_memory(media_top, editing_gid if editing_gid else None),
                parse_mode="HTML",
            )
            return
        except Exception:
            pass

    prev_id = data.get("media_preview_msg_id")
    if prev_id and not reedit:
        try:
            await m.bot.delete_message(chat_id=m.chat.id, message_id=prev_id)
        except Exception:
            pass

    # ЕСЛИ ЕСТЬ МЕДИА - НИКОГДА НЕ ОТКЛЮЧАЕМ ПРЕВЬЮ!
    msg = await m.answer(
        full,
        link_preview_options=lp,
        reply_markup=kb_media_preview_with_memory(media_top, editing_gid if editing_gid else None),
        parse_mode="HTML",
    )
    await state.update_data(media_preview_msg_id=msg.message_id)

#--- Рендер текста предпросмотра БЕЗ медиа ---
async def render_text_preview_message(
    m: Message,
    state: FSMContext,
    *,
    reedit: bool = False
) -> None:
    """
    Предпросмотр без медиа: одно сообщение с описанием/счётчиками/датой
    и клавиатурой kb_preview_no_media().
    """
    data = await state.get_data()

    # описание берём как есть (разрешаем базовую HTML-разметку пользователя)
    desc_raw  = (data.get("desc") or "").strip()
    desc_html = desc_raw or None

    prizes     = int(data.get("winners_count") or 0)
    end_at_msk = data.get("end_at_msk_str")  
    days_left  = data.get("days_left")

    txt = _compose_preview_text(
        "", prizes,
        desc_html=desc_html,
        end_at_msk=end_at_msk,
        days_left=days_left
    )

    # ОЧИСТКА ТЕКСТА ОТ ПОЛЬЗОВАТЕЛЬСКИХ ПРЕВЬЮ
    has_media = bool(data.get("media_url"))
    cleaned_text, disable_preview = text_preview_cleaner.clean_text_preview(txt, has_media)

    # если до этого уже рисовали предпросмотр — аккуратно удалим
    prev_id = data.get("media_preview_msg_id")
    if prev_id and not reedit:
        try:
            await m.bot.delete_message(chat_id=m.chat.id, message_id=prev_id)
        except Exception:
            pass

    # ДИНАМИЧЕСКОЕ ОТКЛЮЧЕНИЕ ПРЕВЬЮ
    send_kwargs = {
        "text": cleaned_text,
        "reply_markup": kb_preview_no_media(),
        "parse_mode": "HTML"
    }
    
    if disable_preview:
        send_kwargs["disable_web_page_preview"] = True

    msg = await m.answer(**send_kwargs)
    await state.update_data(
        media_preview_msg_id=msg.message_id,
        media_url=None,      # критично: помечаем, что медиа нет
        media_top=False,
    )

# --- Предпросмотр для шага "Запустить розыгрыш" (тот же вид, что и при обычном предпросмотре) ---
async def _send_launch_preview_message(m: Message, gw: "Giveaway") -> None:
    """
    Рисуем предпросмотр перед финальным подтверждением:
    - если медиа есть: пробуем сделать link-preview через наш /uploads (фиолетовая рамка),
      при сбое — нативная отправка медиа (fallback);
    - если медиа нет: просто текстовый предпросмотр.
    """
    # 🔄 КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: получаем оригинальное время из БД или вычисляем правильно
    try:
        # Пробуем получить оригинальное время из базы данных
        async with session_scope() as s:
            # Ищем запись о времени создания розыгрыша
            res = await s.execute(
                stext("SELECT end_at_utc FROM giveaways WHERE id=:id"),
                {"id": gw.id}
            )
            db_time = res.scalar_one()
            
            # Если время в базе хранится как строка, парсим ее
            if isinstance(db_time, str):
                if '+' in db_time or 'Z' in db_time:
                    # Время с timezone info
                    end_at_utc = datetime.fromisoformat(db_time.replace('Z', '+00:00'))
                else:
                    # Время без timezone - считаем UTC
                    end_at_utc = datetime.strptime(db_time, "%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=timezone.utc)
            else:
                end_at_utc = db_time
            
            # Конвертируем в MSK для отображения
            end_at_msk_dt = end_at_utc.astimezone(MSK_TZ)
            end_at_msk_str = end_at_msk_dt.strftime("%H:%M %d.%m.%Y")
            
    except Exception as e:
        # Fallback: используем текущую логику
        logging.warning(f"Failed to get original time: {e}")
        end_at_msk_dt = gw.end_at_utc.astimezone(MSK_TZ)
        end_at_msk_str = end_at_msk_dt.strftime("%H:%M %d.%m.%Y")
    
    # Вычисляем дни
    now_msk = datetime.now(MSK_TZ).date()
    end_at_date = end_at_msk_dt.date()
    days_left = max(0, (end_at_date - now_msk).days)

    # Используем _compose_preview_text для предпросмотра
    preview_text = _compose_preview_text(
        "",
        gw.winners_count,
        desc_html=(gw.public_description or ""),
        end_at_msk=end_at_msk_str,  # Должно быть 17:51
        days_left=days_left,
    )

    # 2) если медиа нет — просто текст
    kind, fid = unpack_media(gw.photo_file_id)
    if not fid:
        # ЕСЛИ НЕТ МЕДИА - ПРОВЕРЯЕМ ПОЛЬЗОВАТЕЛЬСКИЕ ССЫЛКИ
        has_media = bool(fid)  # fid из unpack_media(gw.photo_file_id)
        cleaned_text, disable_preview = text_preview_cleaner.clean_text_preview(preview_text, has_media)
        send_kwargs = {
            "text": cleaned_text,
            "parse_mode": "HTML"
        }
        if disable_preview:
            send_kwargs["disable_web_page_preview"] = True
            
        await m.answer(**send_kwargs)
        return

    # 3) пробуем сделать link-preview как в обычном предпросмотре
    try:
        # подбираем имя файла под тип
        if kind == "photo":
            suggested = "image.jpg"
        elif kind == "animation":
            suggested = "animation.mp4"
        elif kind == "video":
            suggested = "video.mp4"
        else:
            suggested = "file.bin"

        key, s3_url = await file_id_to_public_url_via_s3(m.bot, fid, suggested)
        preview_url = _make_preview_url(key, gw.internal_title or "", gw.public_description or "")

        # 🔄 УСИЛЕННЫЙ LINK-PREVIEW (как в render_link_preview_message)
        hidden_link = f'<a href="{preview_url}"> </a>'  # Пробел вместо невидимого символа
        
        # 🔄 ИСПРАВЛЕНИЕ: Используем сохраненную позицию медиа
        # Получаем позицию медиа, по умолчанию "bottom" для обратной совместимости
        media_position = getattr(gw, 'media_position', 'bottom')
        
        if media_position == "top":
            full_text = f"{hidden_link}\n{preview_text}"
        else:
            full_text = f"{preview_text}\n\n{hidden_link}"

        lp = LinkPreviewOptions(
            is_disabled=False,
            prefer_large_media=True,
            prefer_small_media=False,
            show_above_text=(media_position == "top"),  # <-- ДИНАМИЧЕСКОЕ ЗНАЧЕНИЕ
            url=preview_url  # 🔄 ЯВНО указываем URL
        )

        # ЕСЛИ ЕСТЬ МЕДИА - НИКОГДА НЕ ОТКЛЮЧАЕМ ПРЕВЬЮ!
        await m.answer(full_text, link_preview_options=lp, parse_mode="HTML")

    except Exception:
        # 4) fallback — отдать нативно (фото/гиф/видео) с той же подписью
        try:
            if kind == "photo":
                await m.answer_photo(fid, caption=preview_text, parse_mode="HTML")
            elif kind == "animation":
                await m.answer_animation(fid, caption=preview_text, parse_mode="HTML")
            elif kind == "video":
                await m.answer_video(fid, caption=preview_text, parse_mode="HTML")
            else:
                await m.answer(preview_text, parse_mode="HTML")
        except Exception:
            await m.answer(preview_text, parse_mode="HTML")

# ----------------- DB MODELS -----------------
class Base(DeclarativeBase): pass

class GiveawayStatus:
    DRAFT="draft"; ACTIVE="active"; FINISHED="finished"; CANCELLED="cancelled"

class User(Base):
    __tablename__ = "users"
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str|None] = mapped_column(String(64), nullable=True)
    tz: Mapped[str] = mapped_column(String(64), default=DEFAULT_TZ)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class BotUser(Base):
    __tablename__ = "bot_users"
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_status: Mapped[str] = mapped_column(String(10), default='standard')
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    last_group_check: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_prime: Mapped[bool] = mapped_column(Boolean, default=False)
    last_prime_check: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class OrganizerChannel(Base):
    __tablename__="organizer_channels"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    chat_id: Mapped[int] = mapped_column(BigInteger)
    username: Mapped[str|None] = mapped_column(String(128), nullable=True)
    title: Mapped[str] = mapped_column(String(255))
    is_private: Mapped[bool] = mapped_column(Boolean, default=False)
    bot_role: Mapped[str] = mapped_column(String(32), default="member")  # member|admin
    status: Mapped[str] = mapped_column(String(32), default="ok")
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class Giveaway(Base):
    __tablename__="giveaways"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    internal_title: Mapped[str] = mapped_column(String(100))
    public_description: Mapped[str] = mapped_column(String(3000))
    photo_file_id: Mapped[str|None] = mapped_column(String(512), nullable=True)
    media_position: Mapped[str] = mapped_column(String(10), default='bottom')
    end_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    winners_count: Mapped[int] = mapped_column(Integer, default=1)
    commit_hash: Mapped[str|None] = mapped_column(String(128), nullable=True)
    secret: Mapped[str|None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default=GiveawayStatus.DRAFT)
    tz: Mapped[str] = mapped_column(String(64), default=DEFAULT_TZ)
    cancelled_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_by: Mapped[int|None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class GiveawayChannel(Base):
    __tablename__="giveaway_channels"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    giveaway_id: Mapped[int] = mapped_column(ForeignKey("giveaways.id"), index=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("organizer_channels.id"))
    chat_id: Mapped[int] = mapped_column(BigInteger)
    title: Mapped[str] = mapped_column(String(255))

class Entry(Base):
    __tablename__="entries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    giveaway_id: Mapped[int] = mapped_column(ForeignKey("giveaways.id"), index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    ticket_code: Mapped[str] = mapped_column(String(6), index=True)
    prelim_ok: Mapped[bool] = mapped_column(Boolean, default=False)
    final_ok: Mapped[bool|None] = mapped_column(Boolean, nullable=True)
    prelim_checked_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True))
    final_checked_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True))

class Winner(Base):
    __tablename__="winners"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    giveaway_id: Mapped[int] = mapped_column(ForeignKey("giveaways.id"), index=True)
    user_id: Mapped[int] = mapped_column(BigInteger)
    rank: Mapped[int] = mapped_column(Integer)
    hash_used: Mapped[str] = mapped_column(String(128))

class ServiceOrder(Base):
    """Заявка на сервис продвижения розыгрыша."""
    __tablename__ = "service_orders"

    id:            Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    giveaway_id:   Mapped[int]      = mapped_column(ForeignKey("giveaways.id", ondelete="CASCADE"), index=True)
    owner_user_id: Mapped[int]      = mapped_column(BigInteger, index=True)
    service_type:  Mapped[str]      = mapped_column(String(32))   # top_placement | bot_promotion | tasks
    status:        Mapped[str]      = mapped_column(String(16), default="pending")  # pending | paid | active | cancelled | expired
    price_rub:     Mapped[int|None] = mapped_column(Integer, nullable=True)
    created_at:    Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at:    Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class TopPlacement(Base):
    """Активное размещение розыгрыша в блоке Топ."""
    __tablename__ = "top_placements"

    id:             Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    giveaway_id:    Mapped[int]      = mapped_column(ForeignKey("giveaways.id", ondelete="CASCADE"), index=True)
    order_id:       Mapped[int]      = mapped_column(ForeignKey("service_orders.id", ondelete="CASCADE"))
    starts_at:      Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    ends_at:        Mapped[datetime] = mapped_column(DateTime(timezone=True))
    placement_type: Mapped[str]      = mapped_column(String(16), default="week")  # week | full_period
    is_active:      Mapped[bool]     = mapped_column(Boolean, default=True)

class PrimeChannelPost(Base):
    __tablename__ = "prime_channel_posts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    giveaway_id: Mapped[int] = mapped_column(ForeignKey("giveaways.id"), unique=True, index=True)
    message_id: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class GiveawayMechanic(Base):
    __tablename__ = "giveaway_mechanics"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    giveaway_id: Mapped[int] = mapped_column(ForeignKey("giveaways.id"), index=True)
    mechanic_type: Mapped[str] = mapped_column(String(50))  # 'captcha', 'referral'
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    config: Mapped[str] = mapped_column(String(1000), default="{}")  # <-- ИЗМЕНЕНО: String(1000) вместо JSONB
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

# ---- DB INIT ----

# --- OWNER / ADMIN ---
# Telegram user_id владельца бота — единственный, кто может
# выполнять admin-команды. Замените на свой реальный user_id.
BOT_OWNER_ID: int = int(os.getenv("BOT_OWNER_ID", "0"))

def owner_only(handler):
    """
    Декоратор для admin-команд.
    Если команду вызвал не владелец — молча игнорируем.
    Это безопаснее, чем отвечать «нет доступа» — не раскрываем существование команды.
    Используем functools.wraps чтобы aiogram видел оригинальную сигнатуру хендлера.
    """
    import functools

    @functools.wraps(handler)
    async def wrapper(message: Message, **kwargs):
        if message.from_user and message.from_user.id == BOT_OWNER_ID:
            return await handler(message, **kwargs)
        logging.warning(
            "[ADMIN] Попытка вызова %s от user_id=%s",
            handler.__name__,
            message.from_user.id if message.from_user else "unknown"
        )
    return wrapper


# ID закрытой группы (Premium — для создателей)
PREMIUM_GROUP_ID = int(os.getenv("PREMIUM_GROUP_ID", "0"))

# ID закрытого канала PRIME (для участников)
PRIME_CHANNEL_ID = int(os.getenv("PRIME_CHANNEL_ID", "0"))

# Берём DATABASE_URL из .env и конвертируем в asyncpg-формат для SQLAlchemy
_db_url = os.getenv("DATABASE_URL", "")
DB_URL = _db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

# 🔧 ПРИНУДИТЕЛЬНО ЗАГРУЖАЕМ ASYNCPG ДРАЙВЕР ДЛЯ SQLALCHEMY
import sqlalchemy.dialects.postgresql.asyncpg
print("✅ asyncpg драйвер принудительно зарегистрирован в SQLAlchemy")

engine = create_async_engine(DB_URL, echo=True, future=True)
Session = async_sessionmaker(engine, expire_on_commit=False)

async def mark_membership(chat_id: int, user_id: int) -> None:
    async with Session() as s:
        async with s.begin():
            await s.execute(
                _sqltext(
                    "INSERT INTO channel_memberships(chat_id, user_id) "
                    "VALUES (:c, :u) ON CONFLICT (chat_id, user_id) DO NOTHING"
                ),
                {"c": chat_id, "u": user_id},
            )

# --- Проверяет подписку пользователя в локальной базе данных ---
async def is_member_local(chat_id: int, user_id: int) -> bool:
    try:
        async with session_scope() as s:
            # 🔧 ИСПРАВЛЕННЫЙ SQL ДЛЯ POSTGRESQL
            res = await s.execute(
                text("SELECT 1 FROM channel_memberships WHERE chat_id = :chat_id AND user_id = :user_id"),
                {"chat_id": chat_id, "user_id": user_id}
            )
            return res.scalar() is not None
    except Exception as e:
        print(f"⚠️ Ошибка проверки локальной подписки: {e}")
        return False

# создать все таблицы по ORM-моделям (если их ещё нет)
async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# --- DB bootstrap: гарантируем нужные индексы/уникальности ---

async def ensure_schema():
    """
    Создаём, если вдруг нет:
      - таблицу organizer_channels с нужными полями,
      - уникальный индекс на (owner_user_id, chat_id).
    """
    async with engine.begin() as conn:
        # 1) Таблица (если нет) — полная версия со всеми колонками.
        await conn.exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS organizer_channels (
            id            SERIAL PRIMARY KEY,
            owner_user_id BIGINT   NOT NULL,
            chat_id       BIGINT   NOT NULL,
            username      TEXT,
            title         TEXT     NOT NULL,
            is_private    BOOLEAN  NOT NULL DEFAULT false,
            bot_role      TEXT     NOT NULL DEFAULT 'member',
            status        TEXT     NOT NULL DEFAULT 'ok',
            added_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        # 2) Уникальный индекс для upsert
        await conn.exec_driver_sql("""
        CREATE UNIQUE INDEX IF NOT EXISTS ux_org_channels_owner_chat
        ON organizer_channels(owner_user_id, chat_id);
        """)
        # 3) Индекс на owner_user_id для быстрых выборок
        await conn.exec_driver_sql("""
        CREATE INDEX IF NOT EXISTS idx_owner ON organizer_channels(owner_user_id);
        """)
        # 4) Локальный кэш фактов вступления (chat_id + user_id)
        await conn.exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS channel_memberships (
            chat_id   BIGINT NOT NULL,
            user_id   BIGINT NOT NULL,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (chat_id, user_id)
        );
        """)

@asynccontextmanager
async def session_scope():
    async with Session() as s:
        try:
            yield s
            await s.commit()
        except:
            await s.rollback()
            raise

# ----------------- HELPERS -----------------
ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
def gen_ticket_code(): return "".join(random.choices(ALPHABET, k=6))
def utcnow(): return datetime.now(timezone.utc)

async def ensure_user(user_id: int, username: str | None):
    username = (username or "").strip() or None

    async with session_scope() as s:
        u = await s.get(User, user_id)
        if not u:
            u = User(user_id=user_id, username=username)
            s.add(u)
        else:
            # важное: обновляем username, если он появился
            if username and u.username != username:
                u.username = username

    # Регистрируем пользователя и в bot_users (как у тебя было)
    try:
        await ensure_bot_user(user_id, username)
        logging.info(f"✅ Пользователь {user_id} зарегистрирован в bot_users")
    except Exception as e:
        logging.error(f"❌ Ошибка регистрации в bot_users: {e}")


# Функция для регистрации/обновления пользователя бота
async def ensure_bot_user(user_id: int, username: str | None = None, first_name: str | None = None) -> BotUser:
    """
    Регистрирует или обновляет пользователя в таблице bot_users
    Автоматически проверяет членство в премиум-группе
    """
    async with session_scope() as s:
        # Ищем существующего пользователя
        bot_user = await s.get(BotUser, user_id)
        
        if not bot_user:
            # Создаем нового пользователя
            bot_user = BotUser(
                user_id=user_id,
                username=username,
                first_name=first_name,
                user_status='standard',  # По умолчанию standard
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                is_active=True
            )
            s.add(bot_user)
            await s.flush()  # Важно: получить ID перед дальнейшими операциями
            logging.info(f"✅ Новый пользователь бота зарегистрирован: {user_id}")
        else:
            # Обновляем данные существующего пользователя
            if username and bot_user.username != username:
                bot_user.username = username
            if first_name and bot_user.first_name != first_name:
                bot_user.first_name = first_name
            bot_user.updated_at = datetime.now(timezone.utc)
            bot_user.is_active = True
            logging.info(f"✅ Данные пользователя бота обновлены: {user_id}")
        
        # Проверяем членство в премиум-группе и PRIME-канале
        await check_and_update_premium_status(bot_user, s)
        await check_and_update_prime_status(bot_user, s)
        await s.commit()  # КОММИТ после обновлений
        return bot_user

# Функция проверки членства в группе
async def check_group_membership(user_id: int) -> bool:
    """
    Проверяет, состоит ли пользователь в закрытой премиум-группе
    Возвращает True если состоит, False если нет
    """
    try:
        logging.info(f"🔍 Начинаю проверку группы для user_id={user_id}, группа={PREMIUM_GROUP_ID}")
        
        chat_member = await bot.get_chat_member(
            chat_id=PREMIUM_GROUP_ID,
            user_id=user_id
        )
        
        # Пользователь считается участником если его статус:
        status = chat_member.status.lower()
        logging.info(f"🔍 Статус пользователя {user_id} в группе: {status}")
        
        is_member = status in ["member", "administrator", "creator"]
        
        # Для статуса "restricted" проверяем явно
        if status == "restricted":
            is_member = getattr(chat_member, "is_member", False)
            logging.info(f"🔍 Ограниченный пользователь {user_id}, is_member={is_member}")
        
        logging.info(f"🔍 Проверка группы: user={user_id}, status={status}, is_member={is_member}")
        return is_member
        
    except Exception as e:
        # Если пользователь не найден в группе или произошла ошибка
        logging.warning(f"⚠️ Ошибка проверки группы для {user_id}: {e}")
        return False

# Функция обновления PRIME-статуса
async def check_prime_channel_membership(user_id: int) -> bool:
    """
    Проверяет, состоит ли пользователь в закрытом канале PrizeMe PRIME
    Возвращает True если состоит, False если нет
    """
    try:
        logging.info(f"🔍 Проверка PRIME-канала для user_id={user_id}, канал={PRIME_CHANNEL_ID}")
        chat_member = await bot.get_chat_member(
            chat_id=PRIME_CHANNEL_ID,
            user_id=user_id
        )
        status = chat_member.status.lower()
        logging.info(f"🔍 Статус пользователя {user_id} в PRIME-канале: {status}")

        is_member = status in ["member", "administrator", "creator"]
        if status == "restricted":
            is_member = getattr(chat_member, "is_member", False)

        logging.info(f"🔍 PRIME-канал: user={user_id}, status={status}, is_member={is_member}")
        return is_member

    except Exception as e:
        logging.warning(f"⚠️ Ошибка проверки PRIME-канала для {user_id}: {e}")
        return False

# Функция обновления PRIME-статуса_2
async def check_and_update_prime_status(bot_user: BotUser, session) -> None:
    """
    Проверяет членство в PrizeMe PRIME и обновляет is_prime пользователя.
    Независима от premium-логики — пользователь может быть одновременно premium и prime.
    """
    current_time = datetime.now(timezone.utc)
    check_delay = 2  # секунд

    if (bot_user.last_prime_check and
            (current_time - bot_user.last_prime_check).total_seconds() < check_delay):
        logging.info(f"⏰ Пропускаем PRIME-проверку для {bot_user.user_id} (слишком рано)")
        return

    try:
        is_prime = await check_prime_channel_membership(bot_user.user_id)

        old_prime = bot_user.is_prime
        if old_prime != is_prime:
            bot_user.is_prime = is_prime
            logging.info(f"🔄 PRIME-статус пользователя {bot_user.user_id}: {old_prime} -> {is_prime}")
        else:
            logging.info(f"ℹ️ PRIME-статус пользователя {bot_user.user_id} не изменился: {is_prime}")

        bot_user.last_prime_check = current_time
        bot_user.updated_at = current_time

        logging.info(f"✅ PRIME-проверка завершена для {bot_user.user_id}")

    except Exception as e:
        logging.error(f"❌ Ошибка обновления PRIME-статуса для {bot_user.user_id}: {e}")

# Функция обновления премиум-статуса
async def check_and_update_premium_status(bot_user: BotUser, session) -> None:
    """
    Проверяет членство в PrizeMe ПРЕМИУМ и обновляет статус пользователя
    """
    current_time = datetime.now(timezone.utc)

    check_delay = 2  # секунд
    
    if (bot_user.last_group_check and 
        (current_time - bot_user.last_group_check).total_seconds() < check_delay):
        logging.info(f"⏰ Пропускаем проверку для {bot_user.user_id} (слишком рано)")
        return
    
    try:
        # 🔥 ДОБАВЬТЕ ДИАГНОСТИЧЕСКИЙ ЛОГ
        logging.info(f"🔍 Начинаю проверку канала для user_id={bot_user.user_id}")
        
        # Проверяем членство в группе
        is_member = await check_group_membership(bot_user.user_id)
        
        old_status = bot_user.user_status
        new_status = 'premium' if is_member else 'standard'
        
        # Обновляем статус если изменился
        if old_status != new_status:
            bot_user.user_status = new_status
            logging.info(f"🔄 Статус пользователя {bot_user.user_id} изменен: {old_status} -> {new_status}")
        else:
            logging.info(f"ℹ️ Статус пользователя {bot_user.user_id} не изменился: {old_status}")
        
        # Обновляем время последней проверки
        bot_user.last_group_check = current_time
        bot_user.updated_at = current_time
        
        logging.info(f"✅ Проверка премиум-статуса завершена для {bot_user.user_id}")
        
    except Exception as e:
        logging.error(f"❌ Ошибка обновления премиум-статуса для {bot_user.user_id}: {e}")

# Функция получения статуса пользователя
async def get_user_status(user_id: int) -> str:
    """
    Возвращает статус пользователя (standard/premium)
    Если пользователя нет в базе - регистрирует со статусом standard
    """
    async with session_scope() as s:
        bot_user = await s.get(BotUser, user_id)
        
        if not bot_user:
            # Пользователя нет - создаем со статусом standard
            # Нужно получить username и first_name через бота
            try:
                user = await bot.get_chat(user_id)
                bot_user = BotUser(
                    user_id=user_id,
                    username=user.username,
                    first_name=user.first_name,
                    user_status='standard',
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc)
                )
                s.add(bot_user)
                logging.info(f"📝 Авторегистрация пользователя {user_id} со статусом standard")
            except Exception:
                # Если не удалось получить данные - создаем базовую запись
                bot_user = BotUser(
                    user_id=user_id,
                    user_status='standard',
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc)
                )
                s.add(bot_user)
        
        return bot_user.user_status


# ============================================================================
# ФУНКЦИИ ДЛЯ РАБОТЫ С ДОПОЛНИТЕЛЬНЫМИ МЕХАНИКАМИ
# ============================================================================

# ---  Сохраняет или обновляет механику для розыгрыша / Возвращает True если успешно, False если ошибка ---
async def save_giveaway_mechanic(
    giveaway_id: int, 
    mechanic_type: str, 
    is_active: bool = True, 
    config: dict = None,
    max_retries: int = 3
) -> bool:
    
    for attempt in range(max_retries):
        try:
            config_json = json.dumps(config) if config else '{}'
            
            async with session_scope() as s:
                # Проверяем существующую запись
                existing = await s.execute(
                    text("""
                        SELECT id, config 
                        FROM giveaway_mechanics 
                        WHERE giveaway_id = :gid AND mechanic_type = :type
                    """),
                    {"gid": giveaway_id, "type": mechanic_type}
                )
                existing_row = existing.first()
                
                if existing_row:
                    # Обновляем существующую запись
                    existing_id, existing_config = existing_row
                    
                    # Проверяем, нужно ли обновлять (изменения есть)
                    should_update = True
                    if existing_config:
                        try:
                            existing_config_dict = json.loads(existing_config)
                            if (existing_config_dict == config) and (existing_row[0] == is_active):
                                # Нет изменений - пропускаем обновление
                                should_update = False
                        except:
                            pass
                    
                    if should_update:
                        await s.execute(
                            text("""
                                UPDATE giveaway_mechanics 
                                SET is_active = :active, config = :config, created_at = CURRENT_TIMESTAMP
                                WHERE id = :id
                            """),
                            {
                                "id": existing_id,
                                "active": is_active,
                                "config": config_json
                            }
                        )
                        mechanics_logger.info(f"✅ Обновлена механика {mechanic_type} для розыгрыша {giveaway_id} (attempt {attempt + 1})")
                    else:
                        mechanics_logger.info(f"ℹ️ Механика {mechanic_type} не изменилась, пропускаем обновление")
                else:
                    # Создаем новую запись
                    await s.execute(
                        text("""
                            INSERT INTO giveaway_mechanics 
                            (giveaway_id, mechanic_type, is_active, config, created_at)
                            VALUES (:gid, :type, :active, :config, CURRENT_TIMESTAMP)
                        """),
                        {
                            "gid": giveaway_id,
                            "type": mechanic_type,
                            "active": is_active,
                            "config": config_json
                        }
                    )
                    mechanics_logger.info(f"✅ Создана механика {mechanic_type} для розыгрыша {giveaway_id} (attempt {attempt + 1})")
                
                # Детальное логирование
                mechanics_logger.debug(f"📝 Механика сохранена: giveaway_id={giveaway_id}, type={mechanic_type}, "
                            f"active={is_active}, config={config_json[:50]}...")
                
                # Очищаем кэш SQLAlchemy для этого запроса
                await s.commit()  # Сначала коммитим изменения
                
                # Очищаем application-level кэш
                await clear_mechanics_cache(giveaway_id)
                
                # Принудительно помечаем таблицу giveaway_mechanics как обновленную
                s.expire_all()
                
                mechanics_logger.debug(f"🧹 Очищен кэш для механики {mechanic_type}, giveaway {giveaway_id}")
                
                return True
                
        except Exception as e:
            mechanics_logger.error(f"❌ Ошибка сохранения механики {mechanic_type} для розыгрыша {giveaway_id} "
                         f"(attempt {attempt + 1}/{max_retries}): {e}")
            
            if attempt < max_retries - 1:
                # Экспоненциальная задержка перед повторной попыткой
                wait_time = 2 ** attempt  # 1, 2, 4 секунды
                mechanics_logger.info(f"⏳ Повтор через {wait_time} сек...")
                await asyncio.sleep(wait_time)
            else:
                # Все попытки исчерпаны
                import traceback
                mechanics_logger.error(f"🔥 Все попытки сохранения механики исчерпаны. Traceback: {traceback.format_exc()}")
                return False
    
    return False


# ---  Удаляет механику для розыгрыша ---
async def remove_giveaway_mechanic(giveaway_id: int, mechanic_type: str) -> bool:

    try:
        async with session_scope() as s:
            await s.execute(
                text("DELETE FROM giveaway_mechanics WHERE giveaway_id = :gid AND mechanic_type = :type"),
                {"gid": giveaway_id, "type": mechanic_type}
            )
            mechanics_logger.info(f"✅ Удалена механика {mechanic_type} для розыгрыша {giveaway_id}")
            return True
    except Exception as e:
        mechanics_logger.error(f"❌ Ошибка удаления механики {mechanic_type} для розыгрыша {giveaway_id}: {e}")
        return False

# --- Возвращает список всех механик для розыгрыша с поддержкой кэширования ---
# ГЛОБАЛЬНЫЙ КЭШ ДЛЯ МЕХАНИК
_mechanics_cache = {}
_cache_lock = asyncio.Lock()
_CACHE_TTL = 60  # Время жизни кэша в секундах (1 минута)
_MAX_CACHE_SIZE = 1000  # Максимальное количество записей в кэше

async def get_giveaway_mechanics(giveaway_id: int, use_cache: bool = True) -> list:
    """Получает список механик для розыгрыша с правильным парсингом JSON"""
    
    cache_key = f"mechanics_{giveaway_id}"
    current_time = time.time()
    
    # Проверка кэша
    if use_cache:
        async with _cache_lock:
            if cache_key in _mechanics_cache:
                cached_data, timestamp = _mechanics_cache[cache_key]
                if current_time - timestamp < _CACHE_TTL:
                    mechanics_logger.debug(f"🔄 Используем кэшированные механики для розыгрыша {giveaway_id}")
                    return cached_data.copy()
    
    try:
        async with session_scope() as s:
            # 🔥 КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: правильный SQL запрос
            result = await s.execute(
                text("""
                    SELECT 
                        id,
                        mechanic_type, 
                        is_active, 
                        config,
                        created_at
                    FROM giveaway_mechanics 
                    WHERE giveaway_id = :gid
                    ORDER BY created_at DESC
                """),
                {"gid": giveaway_id}
            )
            rows = result.fetchall()
            
            mechanics_list = []
            for row in rows:
                try:
                    # 🔥 ИСПРАВЛЕНИЕ: правильно получаем значения из row
                    mechanic_id = row[0]
                    mechanic_type = row[1]
                    is_active = bool(row[2])
                    config_str = row[3] if row[3] else '{}'
                    
                    # 🔥 ПРАВИЛЬНО ПАРСИМ JSON
                    config_dict = {}
                    if config_str and config_str != '{}':
                        try:
                            config_dict = json.loads(config_str)
                        except json.JSONDecodeError:
                            config_dict = {}
                    
                    mechanics_list.append({
                        "id": mechanic_id,
                        "type": mechanic_type,
                        "is_active": is_active,
                        "config": config_dict,
                        "created_at": row[4].isoformat() if hasattr(row[4], 'isoformat') else str(row[4]),
                        "has_config": bool(config_dict)
                    })
                    
                    mechanics_logger.debug(f"📝 Механика прочитана: type={mechanic_type}, active={is_active}, config_len={len(config_str)}")
                    
                except Exception as row_error:
                    mechanics_logger.error(f"❌ Ошибка обработки строки механики: {row_error}, row={row}")
                    continue
            
            mechanics_logger.info(f"📊 Получено {len(mechanics_list)} механик для розыгрыша {giveaway_id}")
            
            # Обновляем кэш
            if use_cache and mechanics_list:
                async with _cache_lock:
                    _mechanics_cache[cache_key] = (mechanics_list.copy(), current_time)
            
            return mechanics_list
            
    except Exception as e:
        mechanics_logger.error(f"❌ Ошибка получения механик для розыгрыша {giveaway_id}: {e}")
        
        # При ошибке возвращаем пустой список
        return []

# --- Очищает кэш механик (Если передан giveaway_id - очищает только для этого розыгрыша) ---
async def clear_mechanics_cache(giveaway_id: int = None):

    async with _cache_lock:
        if giveaway_id:
            cache_key = f"mechanics_{giveaway_id}"
            if cache_key in _mechanics_cache:
                del _mechanics_cache[cache_key]
                mechanics_logger.info(f"🧹 Очищен кэш механик для розыгрыша {giveaway_id}")
        else:
            _mechanics_cache.clear()
            mechanics_logger.info("🧹 Очищен весь кэш механик")


# --- Проверяет, активна ли конкретная механика для розыгрыша с кэшированием ---
async def is_mechanic_active(giveaway_id: int, mechanic_type: str, use_cache: bool = True) -> bool:

    cache_key = f"active_{giveaway_id}_{mechanic_type}"
    current_time = time.time()
    
    # ПРОВЕРКА КЭША
    if use_cache:
        async with _cache_lock:
            if cache_key in _mechanics_cache:
                cached_result, timestamp = _mechanics_cache[cache_key]
                if current_time - timestamp < _CACHE_TTL:
                    mechanics_logger.debug(f"🔄 Используем кэшированный статус активности для {mechanic_type} розыгрыша {giveaway_id}")
                    return cached_result
    
    try:
        async with session_scope() as s:
            # ОЧИСТКА КЭША SQLAlchemy ПЕРЕД ЗАПРОСОМ
            s.expire_all()
            
            # УЛУЧШЕННЫЙ ЗАПРОС С БОЛЬШЕЙ ИНФОРМАЦИЕЙ
            result = await s.execute(
                text("""
                    SELECT is_active, config 
                    FROM giveaway_mechanics 
                    WHERE giveaway_id = :gid AND mechanic_type = :type
                """),
                {"gid": giveaway_id, "type": mechanic_type}
            )
            row = result.first()
            
            is_active = bool(row and row[0])
            
            # ДОПОЛНИТЕЛЬНАЯ ИНФОРМАЦИЯ ДЛЯ ЛОГИРОВАНИЯ
            if row:
                config = row[1] if len(row) > 1 else None
                mechanics_logger.debug(f"🔍 Проверка активности: giveaway_id={giveaway_id}, "
                            f"type={mechanic_type}, active={is_active}, "
                            f"config_present={bool(config)}")
            else:
                mechanics_logger.debug(f"🔍 Механика {mechanic_type} не найдена для розыгрыша {giveaway_id}")
            
            # 🔄 ОБНОВЛЕНИЕ КЭША
            if use_cache:
                async with _cache_lock:
                    _mechanics_cache[cache_key] = (is_active, current_time)
            
            return is_active
            
    except Exception as e:
        mechanics_logger.error(f"❌ Ошибка проверки активности механики {mechanic_type} для розыгрыша {giveaway_id}: {e}")
        
        # ПРИ ОШИБКЕ ПРОБУЕМ ВЕРНУТЬ КЭШИРОВАННЫЙ РЕЗУЛЬТАТ
        if use_cache and cache_key in _mechanics_cache:
            mechanics_logger.warning(f"⚠️ Используем устаревший кэш статуса из-за ошибки БД")
            cached_result, _ = _mechanics_cache[cache_key]
            return cached_result
        
        return False


# ============================================================================
# ФУНКЦИИ ДЛЯ РАБОТЫ С CLOUDFLARE TURNSTILE CAPTCHA
# ============================================================================

async def generate_simple_captcha(giveaway_id: int, user_id: int) -> dict:
    """
    Генерирует простую текстовую Captcha (4 цифры)
    Возвращает: {"digits": "7094", "token": "abc123"}
    """
    # Генерируем 4 случайные цифры
    digits = ''.join([str(random.randint(0, 9)) for _ in range(4)])
    
    # Создаем токен для проверки
    captcha_token = hashlib.sha256(
        f"{giveaway_id}:{user_id}:{digits}:{int(time.time())}".encode()
    ).hexdigest()[:20]
    
    # Сохраняем в БД
    async with session_scope() as s:
        await s.execute(
            text("""
                INSERT INTO captcha_sessions 
                (giveaway_id, user_id, captcha_digits, captcha_token, expires_at)
                VALUES (:gid, :uid, :digits, :token, :expires)
                ON CONFLICT (giveaway_id, user_id) 
                DO UPDATE SET 
                    captcha_digits = EXCLUDED.captcha_digits,
                    captcha_token = EXCLUDED.captcha_token,
                    expires_at = EXCLUDED.expires_at,
                    created_at = CURRENT_TIMESTAMP
            """),
            {
                "gid": giveaway_id,
                "uid": user_id,
                "digits": digits,
                "token": captcha_token,
                "expires": datetime.now(timezone.utc) + timedelta(minutes=10)
            }
        )
    
    return {
        "digits": digits,
        "token": captcha_token,
        "expires_in": 600  # 10 минут в секундах
    }

async def verify_simple_captcha_answer(giveaway_id: int, user_id: int, answer: str, token: str) -> dict:
    """
    Проверяет введенные пользователем цифры
    Возвращает: {"ok": True/False, "message": str}
    """
    async with session_scope() as s:
        # Получаем сохраненные данные
        result = await s.execute(
            text("""
                SELECT captcha_digits, captcha_token 
                FROM captcha_sessions 
                WHERE giveaway_id = :gid 
                AND user_id = :uid 
                AND expires_at > CURRENT_TIMESTAMP
            """),
            {"gid": giveaway_id, "uid": user_id}
        )
        
        row = result.first()
        if not row:
            return {"ok": False, "message": "Время проверки истекло. Пожалуйста, начните заново."}
        
        stored_digits, stored_token = row
        
        # Проверяем токен
        if token != stored_token:
            return {"ok": False, "message": "Неверный токен проверки. Пожалуйста, начните заново."}
        
        # Проверяем введенные цифры (игнорируем пробелы и нецифровые символы)
        user_answer = ''.join(filter(str.isdigit, answer))
        
        if user_answer == stored_digits:
            # Удаляем использованную captcha из БД
            await s.execute(
                text("DELETE FROM captcha_sessions WHERE giveaway_id = :gid AND user_id = :uid"),
                {"gid": giveaway_id, "uid": user_id}
            )
            return {"ok": True, "message": "✅ Проверка пройдена успешно!"}
        else:
            return {"ok": False, "message": "❌ Неверные цифры. Попробуйте еще раз."}

async def process_simple_captcha_participation(user_id: int, giveaway_id: int, captcha_answer: str, captcha_token: str) -> dict:
    """
    Основная функция: проверяет простую Captcha и регистрирует участие
    Возвращает: {"ok": bool, "message": str, "ticket_code": str or None, "already_participating": bool}
    """
    try:
        # 1. Проверяем Captcha
        captcha_result = await verify_simple_captcha_answer(giveaway_id, user_id, captcha_answer, captcha_token)
        if not captcha_result["ok"]:
            return {"ok": False, "message": captcha_result["message"], "ticket_code": None, "already_participating": False}
        
        # 2. Проверяем активность розыгрыша
        async with session_scope() as s:
            gw = await s.get(Giveaway, giveaway_id)
            if gw.status != GiveawayStatus.ACTIVE:
                return {"ok": False, "message": "Розыгрыш не активен.", "ticket_code": None, "already_participating": False}
        
        logging.info(f"[DB][captcha] DATABASE_URL env = {os.getenv('DATABASE_URL')}")
        logging.info(f"[DB][captcha] DB_PATH env = {os.getenv('DB_PATH')}")

        # 2.5 Проверяем подписки ДО выдачи билета (как в обычном user_join)
        ok, details = await check_membership_on_all(bot, user_id, giveaway_id)
        if not ok:
            logging.info(f"🚫 [SIMPLE-CAPTCHA] Membership not ok for user={user_id}, giveaway={giveaway_id}")
            return {
                "ok": False,
                "message": "Подпишитесь на все каналы и попробуйте снова.",
                "ticket_code": None,
                "already_participating": False,
                "need_subscription_required": True
            }

        # 3. Выдаем билет
        async with session_scope() as s:

            try:
                bind = s.get_bind()
                logging.info(f"[DB][captcha] SQLAlchemy bind = {bind}")
            except Exception as e:
                logging.error(f"[DB][captcha] Cannot get bind: {e}")

            # Проверяем, участвует ли уже пользователь
            res = await s.execute(
                text("SELECT ticket_code FROM entries WHERE giveaway_id=:gid AND user_id=:u"),
                {"gid": giveaway_id, "u": user_id}
            )
            row = res.first()
            
            if row:
                # Уже участвует - возвращаем существующий билет
                return {
                    "ok": True, 
                    "message": "Вы уже участвуете в этом розыгрыше!", 
                    "ticket_code": row[0],
                    "already_participating": True
                }
            else:
                # Выдаем новый билет
                for attempt in range(5):
                    code = gen_ticket_code()
                    try:
                        # source_channel
                        src_res = await s.execute(
                            text("SELECT chat_id FROM giveaway_channels WHERE giveaway_id=:gid ORDER BY id LIMIT 1"),
                            {"gid": giveaway_id}
                        )
                        src_row = src_res.first()
                        source_channel_id = src_row[0] if src_row else None

                        await s.execute(
                            text("""
                                INSERT INTO entries(giveaway_id, user_id, ticket_code, prelim_ok, prelim_checked_at, source_channel_id)
                                VALUES (:gid, :u, :code, :prelim_ok, :ts, :src)
                            """),
                            {
                                "gid": giveaway_id, "u": user_id, "code": code,
                                "prelim_ok": True, "ts": datetime.utcnow(), "src": source_channel_id
                            }
                        )

                        # entry_subscriptions
                        try:
                            ch_res = await s.execute(
                                text("SELECT chat_id FROM giveaway_channels WHERE giveaway_id=:gid"),
                                {"gid": giveaway_id}
                            )
                            for (ch_id,) in ch_res.fetchall():
                                try:
                                    member = await bot.get_chat_member(ch_id, user_id)
                                    already_was = member.status not in ("left", "kicked", "banned")
                                except Exception:
                                    already_was = True
                                await s.execute(
                                    text("""
                                        INSERT INTO entry_subscriptions(giveaway_id, user_id, channel_id, was_subscribed)
                                        VALUES (:gid, :uid, :chid, :was)
                                        ON CONFLICT(giveaway_id, user_id, channel_id) DO NOTHING
                                    """),
                                    {"gid": giveaway_id, "uid": user_id, "chid": ch_id, "was": already_was}
                                )
                        except Exception as _e:
                            logging.warning(f"[captcha] entry_subscriptions failed: {_e}")

                        await s.commit()
                        # Проверяем порог для публикации в PRIME
                        asyncio.create_task(_check_and_publish_prime(giveaway_id))

                        return {
                            "ok": True,
                            "message": "✅ Вы успешно участвуете в розыгрыше!",
                            "ticket_code": code,
                            "already_participating": False
                        }

                    except Exception as e:
                        logging.error(
                            f"❌ Ticket insert failed (captcha) gid={giveaway_id} uid={user_id} attempt={attempt+1} code={code}: {e}",
                            exc_info=True
                        )
                        await s.rollback()
                        continue
                    
                return {"ok": False, "message": "Ошибка при выдаче билета. Попробуйте еще раз.", "ticket_code": None, "already_participating": False}
                
    except Exception as e:
        logging.error(f"Ошибка в process_simple_captcha_participation: {e}")
        return {"ok": False, "message": "Внутренняя ошибка сервера.", "ticket_code": None, "already_participating": False}


async def verify_captcha_token(token: str) -> bool:
    """
    Проверяет токен Cloudflare Turnstile Captcha через API Cloudflare
    Возвращает True если токен валидный, False если нет
    """
    if not token or token == "test_token":
        # Для тестирования
        return True
    
    captcha_secret_key = os.getenv("CAPTCHA_SECRET_KEY")
    if not captcha_secret_key or captcha_secret_key == "1x0000000000000000000000000000000AA":
        # Если ключ не настроен или тестовый
        logging.warning("⚠️ Captcha ключ не настроен, пропускаем проверку")
        return True
    
    try:
        # URL для проверки токена
        url = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
        
        # Данные для отправки
        data = {
            "secret": captcha_secret_key,
            "response": token,
            "remoteip": ""  # Можно добавить IP пользователя если нужно
        }
        
        # Асинхронный запрос к Cloudflare API
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, data=data)
            result = response.json()
            
            logging.info(f"🔍 Captcha verify response: {result}")
            
            # Проверяем результат
            if result.get("success", False):
                logging.info("✅ Captcha токен валидный")
                return True
            else:
                logging.warning(f"❌ Captcha проверка не пройдена: {result.get('error-codes', [])}")
                return False
                
    except Exception as e:
        logging.error(f"❌ Ошибка проверки Captcha токена: {e}")
        # В случае ошибки сети или API, лучше пропустить проверку
        return True


def is_captcha_enabled() -> bool:
    """
    Проверяет, включена ли Captcha в настройках
    """
    enabled = os.getenv("CAPTCHA_ENABLED", "false").lower() == "true"
    return enabled

# --- Проверка с явным указанием user_id ---
async def update_mechanics_text_with_user(message: types.Message, giveaway_id: int, user_id: int):

    try:
        # ДИАГНОСТИЧЕСКИЙ ЛОГ
        logging.info(f"🔍 [DIAGNOSTICS] update_mechanics_text_with_user: user_id={user_id}, giveaway_id={giveaway_id}")
        
        # Получаем статус пользователя
        user_status = await get_user_status(user_id)
        logging.info(f"🔍 [DIAGNOSTICS] Статус пользователя {user_id}: {user_status}")
        
        # Получаем список подключенных механик
        mechanics = await get_giveaway_mechanics(giveaway_id)
        
        # Формируем базовый текст
        text = "<b>Вы можете подключить дополнительные механики к розыгрышу</b>\n\n"
        text += "🤖 Защита от ботов с Captcha <i>(только для ПРЕМИУМ)</i>\n"
        text += "🤝🏼 Реферальная система\n\n"
        text += "Подключенные дополнительные механики:\n"
        
        # Добавляем подключенные механики
        active_mechanics = [m for m in mechanics if m.get("is_active", False)]
        if active_mechanics:
            for mechanic in active_mechanics:
                if mechanic.get("type") == "captcha":
                    text += "✅ Защита от ботов с Captcha\n"
                elif mechanic.get("type") == "referral":
                    text += "✅ Реферальная система\n"
        else:
            text += "(пока пусто)"
        
        # Клавиатура
        kb = InlineKeyboardBuilder()
        
        # Динамическая кнопка в зависимости от статуса
        if user_status == 'premium':
            # Премиум пользователи: кнопка с алмазом
            kb.button(text="💎🤖 Подключить Captcha", callback_data=f"mechanics:captcha:{giveaway_id}")
            logging.info(f"🔍 [DIAGNOSTICS] Показана PREMIUM кнопка для пользователя {user_id}")
        else:
            # Стандартные пользователи: заблокированная кнопка
            kb.button(text="🔒🤖 Подключить Captcha", callback_data=f"mechanics:captcha_blocked:{giveaway_id}")
            logging.info(f"🔍 [DIAGNOSTICS] Показана STANDARD кнопка для пользователя {user_id}")
        
        kb.button(text="🤝🏼 Подключить рефералов", callback_data=f"mechanics:referral:{giveaway_id}")
        kb.button(text="⬅️ Назад", callback_data=f"mechanics:back:{giveaway_id}")
        kb.adjust(1)
        
        # Редактируем сообщение
        try:
            await message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
            logging.info(f"✅ [DIAGNOSTICS] Сообщение обновлено для пользователя {user_id}")
            return True
        except Exception as e:
            logging.error(f"❌ [DIAGNOSTICS] Ошибка редактирования сообщения: {e}")
            return False
            
    except Exception as e:
        logging.error(f"❌ [DIAGNOSTICS] Ошибка в update_mechanics_text_with_user: {e}")
        return False


# --- Обновляет текст в блоке "Дополнительные механики" с учетом подключенных механик ---
async def update_mechanics_text(message: types.Message, giveaway_id: int):

    try:
        # Пытаемся определить user_id
        user_id = None
        
        if hasattr(message, 'from_user') and message.from_user:
            user_id = message.from_user.id
        elif hasattr(message, 'chat') and message.chat:
            user_id = message.chat.id
        
        logging.info(f"🔍 [DIAGNOSTICS] update_mechanics_text: user_id={user_id}, giveaway_id={giveaway_id}")
        
        if user_id:
            # Используем новую функцию
            return await update_mechanics_text_with_user(message, giveaway_id, user_id)
        else:
            # Fallback: показываем заблокированную версию
            text = "<b>Вы можете подключить дополнительные механики к розыгрышу</b>\n\n"
            text += "🤖 Защита от ботов с Captcha <i>(только для ПРЕМИУМ)</i>\n"
            text += "🤝🏼 Реферальная система\n\n"
            text += "Подключенные дополнительные механики:\n"
            
            mechanics = await get_giveaway_mechanics(giveaway_id)
            active_mechanics = [m for m in mechanics if m.get("is_active", False)]
            if active_mechanics:
                for mechanic in active_mechanics:
                    if mechanic.get("type") == "captcha":
                        text += "✅ Защита от ботов с Captcha\n"
                    elif mechanic.get("type") == "referral":
                        text += "✅ Реферальная система\n"
            else:
                text += "(пока пусто)"
            
            kb = InlineKeyboardBuilder()
            kb.button(text="🔒🤖 Подключить Captcha", callback_data=f"mechanics:captcha_blocked:{giveaway_id}")
            kb.button(text="🤝🏼 Подключить рефералов", callback_data=f"mechanics:referral:{giveaway_id}")
            kb.button(text="⬅️ Назад", callback_data=f"mechanics:back:{giveaway_id}")
            kb.adjust(1)
            
            try:
                await message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
                return True
            except Exception as e:
                logging.error(f"❌ Ошибка fallback редактирования: {e}")
                return False
                
    except Exception as e:
        logging.error(f"❌ Ошибка в update_mechanics_text: {e}")
        return False

# --- Отладочная функция для проверки механик ---
async def debug_mechanics(giveaway_id: int):
    try:
        async with session_scope() as s:
            # Прямой SQL запрос для проверки
            result = await s.execute(
                text("""
                    SELECT id, mechanic_type, is_active, config, created_at
                    FROM giveaway_mechanics 
                    WHERE giveaway_id = :gid
                """),
                {"gid": giveaway_id}
            )
            rows = result.fetchall()
            
            mechanics_logger.info(f"🔍 DEBUG: Raw rows for giveaway {giveaway_id}:")
            for i, row in enumerate(rows):
                mechanics_logger.info(f"🔍 DEBUG: Row {i}: id={row[0]}, type={row[1]}, active={row[2]}, config={row[3]}, created={row[4]}")
            
            # Вызываем основную функцию для проверки
            mechanics = await get_giveaway_mechanics(giveaway_id, use_cache=False)
            mechanics_logger.info(f"🔍 DEBUG: Processed mechanics: {len(mechanics)} items")
            for i, m in enumerate(mechanics):
                mechanics_logger.info(f"🔍 DEBUG: Mech {i}: type={m.get('type')}, active={m.get('is_active')}")
            
            return rows, mechanics
            
    except Exception as e:
        mechanics_logger.error(f"❌ DEBUG Error: {e}")
        return [], []

# === продолжение с премиум ===
#--- Возвращает (лимит_победителей, статус_пользователя) для указанного user_id ---

async def get_winners_limit(user_id: int) -> tuple[int, str]:
    status = await get_user_status(user_id)
    if status == 'premium':
        return WINNERS_LIMIT_PREMIUM, 'premium'
    else:
        return WINNERS_LIMIT_STANDARD, 'standard'


async def is_user_admin_of_chat(bot: Bot, chat_id: int, user_id: int) -> bool:
    """
    Надёжнее проверяем админство через get_chat_administrators().
    В каналах get_chat_member может давать ошибки/пустые статусы,
    поэтому пробуем оба варианта.
    """
    # 1) пробуем списком админов (основной путь)
    try:
        admins = await bot.get_chat_administrators(chat_id)
        for a in admins:
            if a.user.id == user_id:
                return True
    except TelegramBadRequest:
        # упали на правах/доступе – продолжим запасным путём
        pass
    except Exception:
        pass

    # 2) запасной путь – точечная проверка участника
    try:
        m = await bot.get_chat_member(chat_id, user_id)
        return m.status in {"administrator", "creator"}
    except Exception:
        return False

async def check_membership_on_all(bot, user_id:int, giveaway_id:int):
    async with session_scope() as s:
        res = await s.execute(
            text("SELECT title, chat_id FROM giveaway_channels WHERE giveaway_id = :gid"),
            {"gid": giveaway_id}
        )
        rows = res.all()
    
    details = []; all_ok = True
    for title, chat_id in rows:
        # 1) Быстрый путь: уже знаем, что он вступил (одобренный join-request)
        ok = await is_member_local(int(chat_id), int(user_id))
        status = "local" if ok else "unknown"

        # 2) Если нет локальной отметки — подстрахуемся Bot API
        if not ok:
            try:
                m = await bot.get_chat_member(chat_id, user_id)
                status = (m.status or "").lower()
                ok = (
                    status in {"member", "administrator", "creator"} or
                    (status == "restricted" and getattr(m, "is_member", False))
                )
            except Exception as e:
                logging.warning(f"[CHK] chat={chat_id} user={user_id} err={e}")
        details.append((f"{title} (status={status})", ok))
        all_ok = all_ok and ok
    return all_ok, details

def commit_hash(secret:str, gid:int)->str:
    return hashlib.sha256((secret+str(gid)).encode()).hexdigest()

def deterministic_draw(secret:str, gid:int, user_ids:list[int], k:int):
    h = hashlib.sha256((secret+str(gid)).encode()).digest()
    pool = list(sorted(user_ids))
    winners=[]; rank=1
    while pool and len(winners)<k:
        idx = int.from_bytes(h,"big") % len(pool)
        uid = pool.pop(idx)
        winners.append((uid, rank, hashlib.sha256(h).hexdigest()))
        h = hashlib.sha256(h).digest()
        rank+=1
    return winners

#--- Клавиатура для предпросмотра С медиа ---
def kb_media_preview_with_memory(media_on_top: bool, giveaway_id: int = None) -> InlineKeyboardMarkup:
    """
    Улучшенная клавиатура с "эффектом памяти".
    Если передан giveaway_id, показывает текущую сохраненную позицию.
    """
    kb = InlineKeyboardBuilder()
    kb.button(text="Изменить изображение/gif/видео", callback_data="preview:change")
    
    if media_on_top:
        kb.button(text="Показывать медиа снизу", callback_data="preview:move:down")
    else:
        kb.button(text="Показывать медиа сверху", callback_data="preview:move:up")
    
    kb.button(text="➡️ Продолжить", callback_data="preview:continue")
    kb.adjust(1)
    return kb.as_markup()

#--- Клавиатура для предпросмотра БЕЗ медиа ---
def kb_preview_no_media() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Добавить изображение/gif/видео", callback_data="preview:add_media")
    kb.button(text="➡️ Продолжить", callback_data="preview:continue")
    kb.adjust(1)
    return kb.as_markup()

def _preview_text(title: str, winners: int) -> str:
    return (
        f"{escape(title)}\n\n"
        f"Число участников: 0\n"
        f"Количество призов: {max(1, int(winners))}\n"
        f"Дата розыгрыша: 00:00, 00.00.0000 (0 days)"
    )

async def _send_media(chat_id: int, kind: str|None, fid: str|None):
    if not kind or not fid:
        return None
    if kind == "photo":
        return await bot.send_photo(chat_id, fid)
    if kind == "animation":
        return await bot.send_animation(chat_id, fid)
    if kind == "video":
        return await bot.send_video(chat_id, fid)
    return None


# --- Добавление канала ---

async def save_shared_chat(
    *,
    owner_user_id: int,
    chat_id: int,
    title: str,
    chat_type: str,
    bot_role: str
) -> bool:
    is_private = chat_type in (ChatType.GROUP, ChatType.SUPERGROUP)
    
    try:
        # aware datetime с timezone (UTC)
        added_at_aware = datetime.now(timezone.utc)
        
        async with session_scope() as s:
            result = await s.execute(
                text("""
                    INSERT INTO organizer_channels
                        (owner_user_id, chat_id, title, is_private, bot_role, status, added_at)
                    VALUES (:user_id, :chat_id, :title, :is_private, :role, 'ok', :added_at)
                    ON CONFLICT (owner_user_id, chat_id)
                    DO UPDATE SET
                        title      = EXCLUDED.title,
                        is_private = EXCLUDED.is_private,
                        bot_role   = EXCLUDED.bot_role,
                        status     = 'ok',
                        added_at   = EXCLUDED.added_at
                    RETURNING id, (xmax = 0) as is_new
                """),
                {
                    "user_id": owner_user_id,
                    "chat_id": chat_id,
                    "title": title,
                    "is_private": is_private,
                    "role": bot_role,
                    "added_at": added_at_aware
                }
            )
            
            row = result.first()
            if row:
                is_new = bool(row[1])
                action = "добавлен" if is_new else "обновлён"
                logging.info(f"✅ Канал {action}: {title} (chat_id={chat_id}) для user_id={owner_user_id}")
                return is_new
            else:
                logging.error(f"❌ Не удалось сохранить канал {title} для user_id={owner_user_id}")
                return False
                
    except Exception as e:
        logging.error(f"❌ Error in save_shared_chat: {e}")
        import traceback
        logging.error(f"Traceback: {traceback.format_exc()}")
        return False


async def save_channel_for_user(
    *,
    user_id: int,
    chat_id: int,
    title: str,
    username: str | None = None,
    chat_type: str,
    bot_role: str
) -> bool:
    """
    УНИВЕРСАЛЬНАЯ функция сохранения канала для пользователя.
    Использует UPSERT для избежания UniqueViolationError.
    """
    is_private = chat_type in (ChatType.GROUP, ChatType.SUPERGROUP)
    
    try:
        added_at_aware = datetime.now(timezone.utc)
        
        async with session_scope() as s:
            result = await s.execute(
                text("""
                    INSERT INTO organizer_channels
                        (owner_user_id, chat_id, title, username, is_private, bot_role, status, added_at, channel_type)
                    VALUES (:user_id, :chat_id, :title, :username, :is_private, :role, 'ok', :added_at, :channel_type)
                    ON CONFLICT (owner_user_id, chat_id)
                    DO UPDATE SET
                        title        = EXCLUDED.title,
                        username     = EXCLUDED.username,
                        is_private   = EXCLUDED.is_private,
                        bot_role     = EXCLUDED.bot_role,
                        status       = EXCLUDED.status,
                        added_at     = EXCLUDED.added_at,
                        channel_type = EXCLUDED.channel_type
                    RETURNING id, (xmax = 0) as is_new
                """),
                {
                    "user_id": user_id,
                    "chat_id": chat_id,
                    "title": title,
                    "username": username,
                    "is_private": is_private,
                    "role": bot_role,
                    "added_at": added_at_aware,
                    "channel_type": chat_type,
                }
            )

            row = result.first()
            if row:
                is_new = bool(row[1])  # xmax = 0 означает новая запись
                if is_new:
                    logging.info(f"✅ Новый канал добавлен: {title} (chat_id={chat_id}) для user_id={user_id}")
                else:
                    logging.info(f"✅ Канал обновлен: {title} (chat_id={chat_id}) для user_id={user_id}")
                return is_new
            else:
                logging.error(f"❌ Не удалось сохранить канал {title} для user_id={user_id}")
                return False
                
    except Exception as e:
        logging.error(f"❌ Error in save_channel_for_user: {e}")
        import traceback
        logging.error(f"Traceback: {traceback.format_exc()}")
        return False

# ----------------- FSM -----------------
class CreateFlow(StatesGroup):
    TITLE = State()
    WINNERS = State()
    DESC = State()
    CONFIRM_DESC = State()   # подтверждение описания
    MEDIA_DECIDE = State()   # новый шаг: задать вопрос Да/Нет
    MEDIA_UPLOAD = State()   # новый шаг: ожидать файл (photo/animation/video)
    MEDIA_PREVIEW = State()
    PHOTO = State()          # больше не используется, но пусть останется если где-то ссылаешься
    ENDAT = State()

# --- Состояния для редактирования существующего розыгрыша ---
class EditFlow(StatesGroup):
    WAITING_SETTING_TYPE = State()  # Ожидаем выбора типа настройки
    EDIT_TITLE = State()           # Редактирование названия
    EDIT_DESC = State()            # Редактирование описания  
    EDIT_ENDAT = State()           # Редактирование даты окончания
    EDIT_MEDIA = State()           # Редактирование медиа
    EDIT_WINNERS = State()         # Редактирование кол-ва победителей
    CONFIRM_EDIT = State()         # Подтверждение изменений

# ----------------- BOT -----------------
bot = Bot(BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher()
scheduler = AsyncIOScheduler()

async def deactivate_expired_top_placements():
    """
    Периодическая задача: деактивирует топ-размещения у которых истёк ends_at.
    Запускается каждые 30 минут через APScheduler.
    """
    async with Session() as s:
        result = await s.execute(stext("""
            UPDATE top_placements
            SET is_active = false
            WHERE is_active = true AND ends_at <= NOW()
            RETURNING giveaway_id
        """))
        deactivated = result.fetchall()
        await s.commit()

    if deactivated:
        ids = [str(r.giveaway_id) for r in deactivated]
        logging.info(
            "[TOP_PLACEMENTS] Деактивировано истёкших размещений: %d (giveaway_ids: %s)",
            len(ids), ", ".join(ids)
        )

@dp.chat_join_request()
async def on_join_request(ev: ChatJoinRequest, bot: Bot):
    try:
        chat_id = ev.chat.id
        user_id = ev.from_user.id
        await bot.approve_chat_join_request(chat_id, user_id)
        await mark_membership(chat_id, user_id)
        logging.info(f"[JOIN] approved chat={chat_id} user={user_id}")
    except Exception as e:
        logging.exception(f"[JOIN][ERR] {e}")

# --- Требуемые права администратора для каналов и групп ---
CHAN_ADMIN_RIGHTS = ChatAdministratorRights(
    is_anonymous=False,
    can_manage_chat=True,
    can_post_messages=True,
    can_edit_messages=True,
    can_delete_messages=True,
    can_invite_users=True,
    can_restrict_members=True,
    can_promote_members=True,
    can_change_info=True,
    can_pin_messages=False,
    can_manage_topics=True,
    can_post_stories=False,
    can_edit_stories=False,
    can_delete_stories=False,
    can_manage_video_chats=True,
)

GROUP_ADMIN_RIGHTS = ChatAdministratorRights(
    is_anonymous=False,
    can_manage_chat=False,      # УБРАТЬ - нельзя запросить для ботов
    can_post_messages=True,     # ✅ КРИТИЧЕСКИ ВАЖНО - для публикации
    can_edit_messages=True,     # ✅ Для редактирования постов
    can_delete_messages=False,  # УБРАТЬ - обычно не нужно
    can_invite_users=True,      # ✅ Для приглашения участников
    can_restrict_members=False, # УБРАТЬ - нельзя запросить
    can_promote_members=False,  # УБРАТЬ - нельзя запросить
    can_change_info=False,      # УБРАТЬ - нельзя запросить
    can_pin_messages=False,     # УБРАТЬ - обычно не нужно
    can_manage_topics=False,    # УБРАТЬ - для форумов, не нужно
    can_post_stories=False,
    can_edit_stories=False,
    can_delete_stories=False,
    can_manage_video_chats=False, # УБРАТЬ - не нужно
)

async def set_bot_commands(bot: Bot):
    # Команды для всех пользователей
    public_commands = [
        BotCommand(command="start",    description="перезапустить бота"),
        BotCommand(command="create",   description="создать розыгрыш"),
        BotCommand(command="giveaways", description="мои розыгрыши"),
        BotCommand(command="boost",    description="подписка, сервисы и донат"),
    ]
    await bot.set_my_commands(public_commands)

    # Дополнительные команды только для владельца бота
    # BotCommandScopeChat ограничивает видимость конкретным чатом/пользователем
    from aiogram.types import BotCommandScopeChat
    owner_commands = public_commands + [
        BotCommand(command="admin", description="🔧 Панель администратора"),
    ]
    await bot.set_my_commands(
        owner_commands,
        scope=BotCommandScopeChat(chat_id=BOT_OWNER_ID)
    )

def kb_main():
    kb = InlineKeyboardBuilder()
    kb.button(text="Создать розыгрыш", callback_data="create")
    kb.button(text="Мои розыгрыши", callback_data="my_events")
    kb.button(text="Мои каналы", callback_data="my_channels")
    return kb.as_markup()

# ===== Reply-кнопки: перенаправляем на готовые сценарии =====

def reply_main_kb() -> ReplyKeyboardMarkup:
    btn_add_channel = KeyboardButton(
        text=BTN_ADD_CHANNEL,
        request_chat=KeyboardButtonRequestChat(
            request_id=1,
            chat_is_channel=True,
            bot_administrator_rights=CHAN_ADMIN_RIGHTS,
            user_administrator_rights=CHAN_ADMIN_RIGHTS,
        )
    )

    btn_add_group = KeyboardButton(
        text=BTN_ADD_GROUP,
        request_chat=KeyboardButtonRequestChat(
            request_id=2,
            chat_is_channel=False,
            bot_administrator_rights=GROUP_ADMIN_RIGHTS,
            user_administrator_rights=GROUP_ADMIN_RIGHTS,
        )
    )

    # ОБНОВЛЕННАЯ КЛАВИАТУРА: 6 кнопок в формате 2x3
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_GIVEAWAYS), KeyboardButton(text=BTN_CREATE)],
            [btn_add_channel, btn_add_group],
            [KeyboardButton(text="Мои каналы"), KeyboardButton(text=BTN_SUBSCRIPTIONS)],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Сообщение",
    )

def chooser_reply_kb() -> ReplyKeyboardMarkup:
    btn_add_channel = KeyboardButton(
        text=BTN_ADD_CHANNEL,
        request_chat=KeyboardButtonRequestChat(
            request_id=101,  # Уникальный ID для каналов
            chat_is_channel=True,
            bot_administrator_rights=CHAN_ADMIN_RIGHTS,
            user_administrator_rights=CHAN_ADMIN_RIGHTS,
        )
    )
    btn_add_group = KeyboardButton(
        text=BTN_ADD_GROUP,
        request_chat=KeyboardButtonRequestChat(
            request_id=102,  # Уникальный ID для групп
            chat_is_channel=False,
            chat_is_forum=False,  # ✅ ДОБАВЛЕНО: явно указываем не форум
            bot_administrator_rights=GROUP_ADMIN_RIGHTS,
            user_administrator_rights=GROUP_ADMIN_RIGHTS,
        )
    )
    # Минимальная «одноразовая» клавиатура только с этими двумя кнопками
    return ReplyKeyboardMarkup(
        keyboard=[[btn_add_channel, btn_add_group]],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="Выберите канал/группу ниже"
    )

# === СИСТЕМНОЕ окно выбора канала/группы (chat_shared) ===
@dp.message(F.chat_shared)
async def on_chat_shared(m: Message, state: FSMContext):
    """УНИВЕРСАЛЬНЫЙ обработчик добавления каналов/групп из ВСЕХ мест"""
    shared = m.chat_shared
    chat_id = shared.chat_id
    user_id = m.from_user.id
    
    logging.info(f"🔍 CHAT_SHARED: user={user_id}, chat_id={chat_id}, request_id={shared.request_id}")

    try:
        # Получаем информацию о чате
        chat = await bot.get_chat(chat_id)
        me = await bot.get_me()
        
        # Проверяем права бота в чате
        try:
            cm = await bot.get_chat_member(chat_id, me.id)
            role = "admin" if cm.status == "administrator" else ("member" if cm.status == "member" else "none")
        except Exception as e:
            logging.warning(f"⚠️ Не удалось проверить права бота: {e}")
            role = "none"
        
        title = chat.title or getattr(chat, "first_name", None) or "Без названия"
        username = getattr(chat, "username", None)
        
        # Определяем тип чата
        if chat.type == "channel":
            chat_type = "channel"
        elif chat.type in ["group", "supergroup"]:
            chat_type = "group"
        else:
            chat_type = chat.type

        # Получаем число участников
        try:
            member_count = await bot.get_chat_member_count(chat.id)
        except Exception:
            member_count = None

        # Сохраняем канал с использованием единой функции
        is_new = await save_channel_for_user(
            user_id=user_id,
            chat_id=chat.id,
            title=title,
            username=username,
            chat_type=chat_type,
            bot_role=role
        )

        # Сохраняем member_count отдельным запросом
        if member_count is not None:
            try:
                async with session_scope() as s:
                    await s.execute(
                        text("UPDATE organizer_channels SET member_count = :mc WHERE owner_user_id = :u AND chat_id = :c"),
                        {"mc": member_count, "u": user_id, "c": chat.id}
                    )
            except Exception as e:
                logging.warning(f"member_count update failed: {e}")

        kind = "канал" if chat.type == "channel" else "группа"
        action_text = "подключён" if is_new else "обновлён"
        # Отправляем подтверждение только если это НЕ сценарий mini-app
        # (в mini-app сценарии своё сообщение об успехе отправляется ниже)
        data_pre = await state.get_data()
        if not data_pre.get("add_channel_from_miniapp", False):
            await m.answer(
                f"{kind.capitalize()} <b>{title}</b> {action_text} к боту.",
                parse_mode="HTML",
                reply_markup=ReplyKeyboardRemove(),
            )

        # 🔄 УЛУЧШЕННАЯ ЛОГИКА: возвращаемся в правильный контекст
        data = await state.get_data()
        
        # 1. Если это добавление канала во время создания розыгрыша
        event_id = data.get("chooser_event_id")
        if event_id:
            async with session_scope() as s:
                gw = await s.get(Giveaway, event_id)
                res = await s.execute(
                    text("SELECT id, title FROM organizer_channels WHERE owner_user_id = :u AND status = 'ok'"),
                    {"u": gw.owner_user_id}
                )
                channels = [(r[0], r[1]) for r in res.all()]
                res = await s.execute(
                    text("SELECT channel_id FROM giveaway_channels WHERE giveaway_id = :g"),
                    {"g": event_id}
                )
                attached_ids = {r[0] for r in res.fetchall()}
            
            await m.answer(
                build_connect_channels_text(gw.internal_title),
                reply_markup=build_channels_menu_kb(event_id, channels, attached_ids)
            )
            await state.update_data(chooser_event_id=None)
        
        # 2. Если это добавление из главного меню или кнопок "Добавить канал/группу"
        elif shared.request_id in [1, 2, 101, 102]:
            data = await state.get_data()
            from_miniapp = data.get("add_channel_from_miniapp", False)

            member_label = "Участников" if chat_type == "group" else "Подписчиков"
            count_str = f"{member_count:,}".replace(",", " ") if member_count else "—"
            entity_str = "Группа" if chat_type == "group" else "Канал"
            her_his = "её" if chat_type == "group" else "его"

            success_text = (
                f"🎯 <b>{entity_str} {title} успешно добавлен к боту</b>\n\n"
                f"🎉 Теперь вы можете подключать {her_his} к розыгрышам. "
                f"Если хотите добавить новый канал или группу — нажмите на соответствующую кнопку под строкой поиска.\n\n"
            )

            if from_miniapp:
                await state.update_data(add_channel_from_miniapp=False)
                miniapp_url = f"{WEBAPP_BASE_URL}/miniapp/?tgWebAppStartParam=page_home"
                kb = InlineKeyboardBuilder()
                kb.button(text="📲 Вернуться в mini-app", web_app=WebAppInfo(url=miniapp_url))
                kb.adjust(1)
                await m.answer(
                    success_text,
                    parse_mode="HTML",
                    reply_markup=kb.as_markup()
                )
            else:
                await m.answer(
                    success_text,
                    parse_mode="HTML",
                    reply_markup=reply_main_kb()
                )
        
        # 3. Если это добавление из меню "Мои каналы"
        else:
            # Просто показываем обновленный список
            rows = await get_user_org_channels(user_id)
            label = "Ваши каналы:\n\n" + ("" if rows else "Пока пусто.")
            await m.answer(label, reply_markup=kb_my_channels(rows))
            
    except Exception as e:
        logging.error(f"❌ Ошибка в on_chat_shared: {e}")
        await m.answer(
            f"Не удалось добавить чат. Попробуйте ещё раз. ({str(e)[:100]})",
            reply_markup=ReplyKeyboardRemove()
        )


def kb_event_actions(gid:int, status:str, user_id: int | None = None):

    kb = InlineKeyboardBuilder()
    
    if status == GiveawayStatus.DRAFT:
        # Для черновиков используем новую клавиатуру kb_draft_actions
        return kb_draft_actions(gid)
    elif status == GiveawayStatus.ACTIVE:
        # Для активных розыгрышей - кнопка "Звершить досрочно"
        kb.button(text="🏁 Завершить досрочно", callback_data=f"ev:early_finish:{gid}")
        # Для активных розыгрышей - только статистика (всегда доступна)
        kb.button(text="📊 Статистика", callback_data=f"ev:status:{gid}")
    elif status in (GiveawayStatus.FINISHED, GiveawayStatus.CANCELLED):
        # ПЕРЕРОЗЫГРЫШ: проверяем премиум-статус если user_id передан
        if user_id:
            # Асинхронная проверка статуса - возвращаем callback_data для стандартных пользователей
            # Здесь просто создаем кнопку, а проверка будет в обработчике
            kb.button(text="🎲 Перерозыгрыш", callback_data=f"ev:redraw:{gid}")
        else:
            # Если user_id не передан (старый вызов), показываем для всех
            kb.button(text="🎲 Перерозыгрыш", callback_data=f"ev:redraw:{gid}")
        
        # Для завершенных/отмененных - только статистика
        kb.button(text="📊 Статистика", callback_data=f"ev:status:{gid}")
    
    # Кнопка "Назад" ПРОСТО УДАЛЯЕТ СООБЩЕНИЕ (испаряется)
    kb.button(text="⬅️ Назад", callback_data="close_message")
    
    kb.adjust(1)
    return kb.as_markup()


@dp.callback_query(F.data == "close_message")
async def close_message(cq: CallbackQuery):
    """Просто удаляет сообщение с кнопками"""
    try:
        await cq.message.delete()
    except Exception:
        try:
            await cq.message.edit_reply_markup()
        except Exception:
            pass
    await cq.answer()

# --- Новая клавиатура для черновиков розыгрышей ---
def kb_draft_actions(gid: int) -> InlineKeyboardMarkup:

    kb = InlineKeyboardBuilder()
    
    # 1 ряд: "Добавить канал / группу"
    kb.button(text="Добавить канал / группу", callback_data=f"ev:add_channels:{gid}")
    
    # 2 ряд: "Настройки розыгрыша" 
    kb.button(text="Настройки розыгрыша", callback_data=f"ev:settings:{gid}")
    
    # 3 ряд: "Удалить черновик"
    kb.button(text="🗑️ Удалить черновик", callback_data=f"ev:delete_draft:{gid}")
    
    # 4 ряд: "Назад" - просто удаляет сообщение с черновиком
    kb.button(text="⬅️ Назад", callback_data="close_message")
    
    kb.adjust(1)  # Все кнопки в один столбец
    return kb.as_markup()


def kb_participate(gid:int, allow:bool, cancelled:bool=False):
    kb = InlineKeyboardBuilder()
    if cancelled:
        kb.button(text="❌ Розыгрыш отменён", callback_data="noop")
    else:
        kb.button(text="Проверить подписку", callback_data=f"u:check:{gid}")
        if allow:
            kb.button(text="Принять участие", callback_data=f"u:join:{gid}")
    return kb.as_markup()

def kb_confirm_description() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✏️ Редактировать текст", callback_data="desc:edit")
    kb.button(text="➡️ Продолжить", callback_data="desc:continue")
    kb.adjust(1)
    return kb.as_markup()

@dp.message(Command("start"))
async def cmd_start(m: Message, state: FSMContext):

    # === START PARAM ROUTER: edit_creator_<status>_<gid> ===
    # Пример: /start edit_creator_active_123
    args = (m.text or "").split(maxsplit=1)
    start_param = args[1].strip() if len(args) > 1 else ""

    if start_param.startswith("edit_creator_"):
        try:
            # edit_creator_active_123 -> ["edit", "creator", "active", "123"]
            _, _, status, gid_str = start_param.split("_", 3)
            gid = int(gid_str)
        except Exception:
            await m.answer("Не удалось открыть розыгрыш для редактирования.")
            return
        await show_event_card(m.chat.id, gid)
        return

    if start_param.startswith("pay_"):
        await ensure_user(m.from_user.id, m.from_user.username)
        inv_id_str = start_param[4:]  # убираем "pay_"
        try:
            inv_id = int(inv_id_str)
        except ValueError:
            await m.answer("❌ Неверная ссылка оплаты.")
            return

        # Получаем данные заказа из БД через Node API
        import aiohttp
        node_url = os.environ.get("WEBAPP_BASE_URL", "https://prizeme.ru")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{node_url}/api/robokassa_order_status?inv_id={inv_id}"
                ) as resp:
                    order_data = await resp.json()
        except Exception as e:
            logging.error(f"[pay_start] order fetch error: {e}")
            order_data = {}

        # Если уже оплачен
        if order_data.get("status") == "paid":
            miniapp_url = f"{WEBAPP_BASE_URL}/miniapp/?tgWebAppStartParam=page_services"
            kb = InlineKeyboardBuilder()
            kb.button(text="🚀 К сервисам", web_app=WebAppInfo(url=miniapp_url))
            kb.adjust(1)
            await m.answer(
                "✅ <b>Оплата уже прошла успешно!</b>\n\n"
                "Услуга «Включение в топ-розыгрыши» активирована.",
                parse_mode="HTML",
                reply_markup=kb.as_markup()
            )
            return

        # Получаем детали заказа из БД напрямую
        try:
            async with Session() as session:
                result = await session.execute(
                    sqlalchemy.text(
                        "SELECT period, amount_rub FROM robokassa_orders WHERE inv_id = :inv_id"
                    ),
                    {"inv_id": inv_id}
                )
                order_row = result.fetchone()
        except Exception as e:
            logging.error(f"[pay_start] db error: {e}")
            order_row = None

        if not order_row:
            await m.answer("❌ Заказ не найден. Попробуйте оформить заново.")
            return

        period_label = "1 день" if order_row[0] == "day" else "1 неделю"
        price = order_row[1]

        # Формируем ссылку на Robokassa
        import hashlib
        robo_login   = os.environ.get("ROBOKASSA_LOGIN", "prizeme")
        is_test      = os.environ.get("ROBOKASSA_IS_TEST", "1") == "1"
        p1           = os.environ.get("ROBOKASSA_TEST_PASSWORD1" if is_test else "ROBOKASSA_PASSWORD1", "")
        out_sum      = f"{float(price):.2f}"
        sig          = hashlib.md5(f"{robo_login}:{out_sum}:{inv_id}:{p1}".encode()).hexdigest().upper()
        is_test_param = "1" if is_test else "0"
        pay_url = (
            f"https://auth.robokassa.ru/Merchant/Index.aspx"
            f"?MerchantLogin={robo_login}"
            f"&OutSum={out_sum}"
            f"&InvId={inv_id}"
            f"&SignatureValue={sig}"
            f"&IsTest={is_test_param}"
            f"&Culture=ru"
            f"&Encoding=utf-8"
        )

        miniapp_url = f"{WEBAPP_BASE_URL}/miniapp/?tgWebAppStartParam=page_services"
        kb = InlineKeyboardBuilder()
        kb.button(text="💳 Оплатить через Robokassa", url=pay_url)
        kb.button(text="❌ Отмена", callback_data=f"pay_cancel:{inv_id}")
        kb.adjust(1)
        await m.answer(
            f"💳 <b>Оплата услуги «Включение в топ-розыгрыши»</b>\n\n"
            f"Цена: <b>{price} ₽</b> (период: {period_label})\n\n"
            f"Нажмите «Оплатить через Robokassa», после оплаты вы сможете вернуться в mini-app.",
            parse_mode="HTML",
            reply_markup=kb.as_markup()
        )
        return

    if start_param == "add_channel":
        await ensure_user(m.from_user.id, m.from_user.username)
        await state.update_data(add_channel_from_miniapp=True)

        help_text = (
            "<b>✚ Добавьте канал / группу для проведения розыгрышей</b>\n\n"
            "При добавлении бота @prizeme_official_bot в канал / группу Вы даёте право на следующие действия "
            "(не переживайте, это минимальный набор прав без возможности реального управления каналом / группой):\n\n"
            "• Публикация сообщений\n"
            "• Редактирование сообщений\n"
            "• Добавление подписчиков\n"
            "• Создание пригласительных ссылок\n\n"
            "<b>Нажмите на соответствующую кнопку под строкой поиска для подключения канала / группы к боту</b>"
        )
        await m.answer(help_text, parse_mode="HTML", reply_markup=chooser_reply_kb())
        return

    await ensure_user(m.from_user.id, m.from_user.username)
    text = (
        "👋🏻 Добро пожаловать в сервис для проведения розыгрышей PrizeMe!\n\n"
        "🎁 Бот способен запускать розыгрыши среди участников одного или нескольких "
        "Telegram-каналов и самостоятельно выбирать победителей в назначенное время.\n\n"
        "🤖 Команды бота:\n"
        "<b>/start</b> – перезапустить бота\n"
        "<b>/create</b> – создать розыгрыш\n"
        "<b>/events</b> – мои розыгрыши\n"
        "<b>/boost</b> – подписка, сервисы и донат"
    )
    await m.answer(text, parse_mode="HTML", reply_markup=reply_main_kb())

@dp.callback_query(F.data.startswith("pay_cancel:"))
async def cb_pay_cancel(cq: CallbackQuery):
    await cq.answer()
    miniapp_url = f"{WEBAPP_BASE_URL}/miniapp/?tgWebAppStartParam=page_services"
    kb = InlineKeyboardBuilder()
    kb.button(text="🚀 Вернуться к сервисам", web_app=WebAppInfo(url=miniapp_url))
    kb.adjust(1)
    await cq.message.edit_text(
        "❌ Вы отказались от оплаты услуги «Включение в топ-розыгрыши».\n\n"
        "Вы можете вернуться обратно к сервисам.",
        parse_mode="HTML",
        reply_markup=kb.as_markup()
    )

# ===== Меню "Мои розыгрыши" =====
def kb_my_events_menu() -> InlineKeyboardMarkup:

    kb = InlineKeyboardBuilder()
    
    kb.button(text="👤 Я - участник", callback_data="mev:as_participant")
    kb.button(text="👑 Я - создатель", callback_data="mev:as_creator")
    
    kb.adjust(1)  # Каждая кнопка в отдельном ряду
    return kb.as_markup()

@dp.message(Command("dbg_dbpath"))
async def dbg_dbpath(m: types.Message):
    await m.answer(f"DB: <code>{DB_PATH.resolve()}</code>")

@dp.message(Command("dbg_channels"))
async def dbg_channels(m: types.Message):
    rows = await get_user_org_channels(m.from_user.id)
    if not rows:
        await m.answer("Всего: 0")
    else:
        # rows = [(row_id, title)]
        # вытащим ещё chat_id для наглядности
        async with Session() as s:
            chat_ids = []
            for row_id, _title in rows:
                r = await s.execute(stext("SELECT chat_id, title FROM organizer_channels WHERE id=:id"), {"id": row_id})
                rec = r.first()
                chat_ids.append(rec)
        lines = [f"{i+1}. {rec.title} (chat_id={rec.chat_id})" for i, rec in enumerate(chat_ids)]
        await m.answer("Всего: " + str(len(rows)) + "\n" + "\n".join(lines))


# --- Меню "Я - участник" - розыгрыши где пользователь участник ---
def kb_participant_menu(count_involved: int, count_finished: int) -> InlineKeyboardMarkup:

    kb = InlineKeyboardBuilder()
    
    kb.button(text=f"🎲 В которых участвую ({count_involved})", callback_data="mev:involved")
    kb.button(text=f"🏁 Завершённые розыгрыши ({count_finished})", callback_data="mev:finished")
    kb.button(text=f"⬅️ Назад", callback_data="mev:back_to_main")
    
    kb.adjust(1)  # Все кнопки в один столбец
    return kb.as_markup()

async def show_participant_menu(cq: CallbackQuery):
    """Показывает меню 'Я - участник'"""
    uid = cq.from_user.id
    
    # Получаем актуальные данные для счетчиков
    async with session_scope() as s:
        # в которых участвую — уникальные активные розыгрыши, где у пользователя есть entries
        res = await s.execute(stext(
            "SELECT COUNT(DISTINCT g.id) "
            "FROM entries e JOIN giveaways g ON g.id=e.giveaway_id "
            "WHERE e.user_id=:u AND g.status='active'"
        ), {"u": uid})
        count_involved = res.scalar_one() or 0

        # завершённые вообще (по системе) где пользователь участвовал
        res = await s.execute(stext(
            "SELECT COUNT(DISTINCT g.id) "
            "FROM entries e JOIN giveaways g ON g.id=e.giveaway_id "
            "WHERE e.user_id=:u AND g.status='finished'"
        ), {"u": uid})
        count_finished = res.scalar_one() or 0

    text = "👤 <b>Я - участник</b>\n\nРозыгрыши, где вы принимаете участие:"
    
    await cq.message.edit_text(
        text,
        reply_markup=kb_participant_menu(count_involved, count_finished),
        parse_mode="HTML"
    )
    await cq.answer()



# --- Меню "Я - создатель" - розыгрыши где пользователь создатель ---
def kb_creator_menu(my_active: int, my_draft: int, my_finished: int) -> InlineKeyboardMarkup:

    kb = InlineKeyboardBuilder()
    
    kb.button(text=f"🚀 Мои запущенные ({my_active})", callback_data="mev:my_active")
    kb.button(text=f"📝 Мои незапущенные ({my_draft})", callback_data="mev:my_drafts") 
    kb.button(text=f"🏁 Мои завершённые ({my_finished})", callback_data="mev:my_finished")
    kb.button(text=f"⬅️ Назад", callback_data="mev:back_to_main")
    
    kb.adjust(1)  # Все кнопки в один столбец
    return kb.as_markup()

async def show_creator_menu(cq: CallbackQuery):
    """Показывает меню 'Я - создатель'"""
    uid = cq.from_user.id
    
    # Получаем актуальные данные для счетчиков
    async with session_scope() as s:
        # мои активные, черновики и завершённые
        res = await s.execute(stext(
            "SELECT "
            "SUM(CASE WHEN status='active' THEN 1 ELSE 0 END), "
            "SUM(CASE WHEN status='draft' THEN 1 ELSE 0 END), "
            "SUM(CASE WHEN status='finished' THEN 1 ELSE 0 END) "
            "FROM giveaways WHERE owner_user_id=:u"
        ), {"u": uid})
        row = res.first()
        my_active = int(row[0] or 0)
        my_draft = int(row[1] or 0)
        my_finished = int(row[2] or 0)

    text = "👑 <b>Я - создатель</b>\n\nРозыгрыши, которые вы создали:"
    
    await cq.message.edit_text(
        text,
        reply_markup=kb_creator_menu(my_active, my_draft, my_finished),
        parse_mode="HTML"
    )
    await cq.answer()

# === Досрочное завершение розыгрыша ===
# ОБРАБОТЧИК: Кнопка "Завершить досрочно"
@dp.callback_query(F.data.startswith("ev:early_finish:"))
async def cb_early_finish(cq: CallbackQuery):
    """Показывает диалог подтверждения досрочного завершения"""
    gid = int(cq.data.split(":")[2])
    
    # Получаем информацию о розыгрыше для отображения времени
    async with session_scope() as s:
        gw = await s.get(Giveaway, gid)
        if not gw or gw.status != GiveawayStatus.ACTIVE:
            await cq.answer("Розыгрыш не найден или не активен.", show_alert=True)
            return
        
        # Форматируем время окончания
        end_time = gw.end_at_utc.astimezone(MSK_TZ).strftime("%H:%M %d.%m.%Y")
    
    # Текст подтверждения как в задании
    confirm_text = (
        f"<b>Вы действительно собираетесь завершить розыгрыш досрочно?</b>\n\n"
        f"Подтвердите свое действие, нажав на кнопку \"✅ Да\", если хотите завершить розыгрыш досрочно "
        f"или \"❌ Нет\", если хотите сохранить текущее время окончания: <b>{end_time}</b>\n\n"
        f"<i>Внимание, после нажатия на кнопку \"✅ Да\", розыгрыш будет завершен досрочно "
        f"и отменить это действие уже будет нельзя!</i>"
    )
    
    # Клавиатура с кнопками Да/Нет
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Да", callback_data=f"ev:confirm_early:{gid}")
    kb.button(text="❌ Нет", callback_data="ev:cancel_early")
    kb.adjust(2)
    
    # Отправляем сообщение с подтверждением
    await cq.message.answer(confirm_text, reply_markup=kb.as_markup(), parse_mode="HTML")
    await cq.answer()
 

# ОБРАБОТЧИК: Отмена досрочного завершения
@dp.callback_query(F.data == "ev:cancel_early")
async def cb_cancel_early(cq: CallbackQuery):
    """Просто удаляет сообщение с подтверждением"""
    try:
        await cq.message.delete()
    except Exception:
        pass
    await cq.answer("Досрочное завершение отменено")


# ОБРАБОТЧИК: Подтверждение досрочного завершения
@dp.callback_query(F.data.startswith("ev:confirm_early:"))
async def cb_confirm_early(cq: CallbackQuery):
    """Завершает розыгрыш досрочно"""
    gid = int(cq.data.split(":")[2])
    
    try:
        # Удаляем сообщение с подтверждением
        try:
            await cq.message.delete()
        except Exception:
            pass
        
        # 1. Меняем время окончания на текущее
        async with session_scope() as s:
            gw = await s.get(Giveaway, gid)
            if not gw or gw.status != GiveawayStatus.ACTIVE:
                await cq.answer("Розыгрыш не найден или не активен.", show_alert=True)
                return
            
            # Сохраняем текущее время как время окончания
            current_time = datetime.now(timezone.utc)
            gw.end_at_utc = current_time
            s.add(gw)
            
            # Получаем информацию для логирования
            giveaway_title = gw.internal_title
        
        # 2. Удаляем задачу из планировщика (если есть)
        try:
            scheduler.remove_job(f"final_{gid}")
            logging.info(f"🗑️ Удален планировщик для досрочного завершения розыгрыша {gid}")
        except Exception as e:
            logging.info(f"⚠️ Планировщик не найден для розыгрыша {gid}: {e}")
        
        # 3. Удаляем сообщение с карточкой розыгрыша (как кнопка "Назад")
        try:
            # Ищем предыдущее сообщение с карточкой (обычно за 1-2 сообщения до подтверждения)
            # Проще: отправим команду на удаление через бота
            await cq.message.bot.delete_message(cq.message.chat.id, cq.message.message_id - 1)
        except Exception as e:
            logging.info(f"⚠️ Не удалось удалить карточку розыгрыша: {e}")
        
        # 4. Запускаем стандартный процесс завершения
        await cq.answer(f"🔄 Завершаю розыгрыш \"{giveaway_title}\" досрочно...")
        await finalize_and_draw_job(gid)
        
        # 5. Уведомляем пользователя
        await cq.message.answer(f"✅ Розыгрыш \"{giveaway_title}\" завершен досрочно!")
        
    except Exception as e:
        logging.error(f"❌ Ошибка при досрочном завершении розыгрыша {gid}: {e}")
        await cq.message.answer(f"❌ Произошла ошибка при завершении розыгрыша: {e}")
        await cq.answer("Ошибка", show_alert=True)

# === Конец блока "Досрочное завершение розыгрыша" ===

# === Блок с перерозыгрышем ===
# ОБРАБОТЧИК: Кнопка "Перерозыгрыш"
@dp.callback_query(F.data.startswith("ev:redraw:"))
async def cb_redraw(cq: CallbackQuery):
    """Показывает диалог подтверждения перерозыгрыша"""
    gid = int(cq.data.split(":")[2])

    # ПРОВЕРКА ПРЕМИУМ СТАТУСА
    user_id = cq.from_user.id
    user_status = await get_user_status(user_id)
    
    if user_status == 'standard':
        # Стандартный пользователь - показываем pop-up о необходимости подписки
        await cq.answer(
            "💎 Оформите подписку ПРЕМИУМ для доступа к функционалу",
            show_alert=True
        )
        return
    
    # Получаем информацию о розыгрыше
    async with session_scope() as s:
        gw = await s.get(Giveaway, gid)
        if not gw or gw.status != GiveawayStatus.FINISHED:
            await cq.answer("Розыгрыш не найден или не завершен.", show_alert=True)
            return
    
    # Текст подтверждения как в задании
    confirm_text = (
        f"<b>🎲 Перерозыгрыш позволяет определить новых победителей розыгрыша</b>\n\n"
        f"Вы действительно собираетесь провести перерозыгрыш? "
        f"Подтвердите свое действие, нажав на кнопку \"✅ Да\", если хотите провести перерозыгрыш "
        f"или \"❌ Нет\", если не хотите ничего менять.\n\n"
        f"<i>Внимание, после нажатия на кнопку \"✅ Да\", будут определены новые победители розыгрыша "
        f"и отменить это действие уже будет нельзя!</i>"
    )
    
    # Клавиатура с кнопками Да/Нет
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Да", callback_data=f"ev:confirm_redraw:{gid}")
    kb.button(text="❌ Нет", callback_data="ev:cancel_redraw")
    kb.adjust(2)
    
    # Отправляем сообщение с подтверждением
    await cq.message.answer(confirm_text, reply_markup=kb.as_markup(), parse_mode="HTML")
    await cq.answer()


# ОБРАБОТЧИК: Отмена перерозыгрыша
@dp.callback_query(F.data == "ev:cancel_redraw")
async def cb_cancel_redraw(cq: CallbackQuery):
    """Просто удаляет сообщение с подтверждением"""
    try:
        await cq.message.delete()
    except Exception:
        pass
    await cq.answer("Перерозыгрыш отменён")


# ОБРАБОТЧИК: Подтверждение перерозыгрыша
@dp.callback_query(F.data.startswith("ev:confirm_redraw:"))
async def cb_confirm_redraw(cq: CallbackQuery):
    """Выполняет перерозыгрыш"""
    gid = int(cq.data.split(":")[2])
    
    try:
        # Удаляем сообщение с подтверждением
        try:
            await cq.message.delete()
        except Exception:
            pass
        
        # Удаляем сообщение с карточкой розыгрыша (как кнопка "Назад")
        try:
            await cq.message.bot.delete_message(cq.message.chat.id, cq.message.message_id - 1)
        except Exception as e:
            logging.info(f"⚠️ Не удалось удалить карточку розыгрыша: {e}")
        
        # Запускаем перерозыгрыш
        await cq.answer(f"🔄 Провожу перерозыгрыш...")
        success = await redraw_winners(gid)
        
        if success:
            await cq.message.answer(f"✅ Перерозыгрыш успешно выполнен! Новые победители определены.")
        else:
            await cq.message.answer(f"❌ Не удалось выполнить перерозыгрыш. Проверьте, есть ли участники у розыгрыша.")
        
    except Exception as e:
        logging.error(f"❌ Ошибка при перерозыгрыше {gid}: {e}")
        await cq.message.answer(f"❌ Произошла ошибка при перерозыгрыше: {e}")
        await cq.answer("Ошибка", show_alert=True)


@dp.message(Command("dbg_scan"))
async def dbg_scan(m: types.Message):
    # показываем, что видим в organizer_channels, и по каждому чату — статусы
    async with Session() as s:
        res = await s.execute(stext("""
            SELECT oc.id, oc.chat_id, oc.title
            FROM organizer_channels oc
            JOIN (
                SELECT chat_id, MAX(id) AS max_id
                FROM organizer_channels
                GROUP BY chat_id
            ) last ON last.max_id = oc.id
            ORDER BY oc.id DESC
        """))
        rows = res.all()

    me = await bot.get_me()
    lines = [f"Всего в БД по chat_id: {len(rows)}"]
    for row_id, chat_id, title in rows:
        try:
            bot_admin = await is_user_admin_of_chat(bot, chat_id, me.id)
        except Exception:
            bot_admin = False
        try:
            user_admin = await is_user_admin_of_chat(bot, chat_id, m.from_user.id)
        except Exception:
            user_admin = False
        mark = "✅" if (bot_admin and user_admin) else "❌"
        lines.append(f"{mark} {title} (chat_id={chat_id}) bot_admin={bot_admin} user_admin={user_admin}")

    await m.answer("\n".join(lines))

@dp.message(Command("test_group_add"))
async def cmd_test_group_add(m: Message):
    """Тестовая команда для диагностики добавления групп"""
    await m.answer(
        "🔧 Тестирование добавления группы...",
        reply_markup=chooser_reply_kb()  # Покажем те же кнопки что и в основном интерфейсе
    )

@dp.message(Command("dbg_gw"))
async def dbg_gw(m: types.Message):
    """Показывает прикреплённые каналы текущего (последнего) моего черновика/актива."""
    uid = m.from_user.id
    async with session_scope() as s:
        # берём последний мой розыгрыш
        res = await s.execute(stext(
            "SELECT id, internal_title FROM giveaways WHERE owner_user_id=:u ORDER BY id DESC LIMIT 1"
        ), {"u": uid})
        row = res.first()
        if not row:
            await m.answer("У вас пока нет розыгрышей."); return
        gid, title = row
        res = await s.execute(stext(
            "SELECT gc.chat_id, gc.title FROM giveaway_channels gc WHERE gc.giveaway_id=:g"
        ), {"g": gid})
        rows = res.fetchall()
    if not rows:
        await m.answer(f"Розыгрыш «{title}» (id={gid}). Прикреплений пока нет.")
    else:
        lines = [f"Розыгрыш «{title}» (id={gid}). Прикреплено:"]
        lines += [f"• {t} (chat_id={cid})" for cid, t in rows]
        await m.answer("\n".join(lines))

# ============================================================
# ADMIN: главная панель
# ============================================================

# ── Уровень 1: главное меню ───────────────────────────────────────────────
def kb_admin_main() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="⚙️ Управление сервисами", callback_data="adm:services")
    kb.adjust(1)
    return kb.as_markup()

# ── Уровень 2: управление сервисами ──────────────────────────────────────
def kb_admin_services() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🏆 Топ-розыгрыши",       callback_data="adm:top_menu")
    kb.button(text="📣 Продвижение в боте",   callback_data="adm:promo_menu")
    kb.button(text="◀️ Назад",                callback_data="adm:back_main")
    kb.adjust(1)
    return kb.as_markup()

# ══════════════════════════════════════════════════════════════════════════
# ── ПРОДВИЖЕНИЕ В БОТЕ — клавиатуры ──────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════

def kb_admin_promo_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📋 Заявки на продвижение",  callback_data="adm:promo_requests")
    kb.button(text="⏳ Ожидают публикации",      callback_data="adm:promo_scheduled")
    kb.button(text="🚀 Продвинуть вручную",      callback_data="adm:promo_manual:0")
    kb.button(text="◀️ Назад",                   callback_data="adm:back_services")
    kb.adjust(1)
    return kb.as_markup()


# ══════════════════════════════════════════════════════════════════════════
# ── ПРОДВИЖЕНИЕ В БОТЕ — handlers ────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════

@dp.callback_query(F.data == "adm:promo_menu")
async def cb_admin_promo_menu(cb: CallbackQuery):
    if not await _admin_guard(cb): return
    await cb.message.edit_text(
        "📣 <b>Продвижение в боте</b>\n\nВыберите действие:",
        parse_mode="HTML",
        reply_markup=kb_admin_promo_menu()
    )
    await cb.answer()


@dp.callback_query(F.data == "adm:back_promo_menu")
async def cb_admin_back_promo_menu(cb: CallbackQuery):
    if not await _admin_guard(cb): return
    await cb.message.edit_text(
        "📣 <b>Продвижение в боте</b>\n\nВыберите действие:",
        parse_mode="HTML",
        reply_markup=kb_admin_promo_menu()
    )
    await cb.answer()


# ── Заявки на продвижение (статус pending) ────────────────────────────────
@dp.callback_query(F.data == "adm:promo_requests")
async def cb_admin_promo_requests(cb: CallbackQuery):
    if not await _admin_guard(cb): return
    async with Session() as s:
        result = await s.execute(stext("""
            SELECT bp.id, bp.giveaway_id, g.internal_title
            FROM bot_promotions bp
            JOIN giveaways g ON g.id = bp.giveaway_id
            WHERE bp.status = 'pending'
            ORDER BY bp.created_at ASC
        """))
        rows = result.fetchall()

    if not rows:
        await cb.message.edit_text(
            "📣 <b>Заявки на продвижение</b>\n\nНет новых заявок.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardBuilder().button(
                text="◀️ Назад", callback_data="adm:promo_menu"
            ).as_markup()
        )
        await cb.answer()
        return

    kb = InlineKeyboardBuilder()
    for row in rows:
        kb.button(
            text=f"#{row.giveaway_id} — {row.internal_title[:30]}",
            callback_data=f"adm:promo_req_info:{row.id}"
        )
    kb.button(text="◀️ Назад", callback_data="adm:promo_menu")
    kb.adjust(1)

    await cb.message.edit_text(
        "📣 <b>Заявки на продвижение</b>\n\nВыберите заявку:",
        parse_mode="HTML",
        reply_markup=kb.as_markup()
    )
    await cb.answer()


# ── Карточка заявки ───────────────────────────────────────────────────────
@dp.callback_query(F.data.startswith("adm:promo_req_info:"))
async def cb_admin_promo_req_info(cb: CallbackQuery):
    if not await _admin_guard(cb): return
    promo_id = int(cb.data.split(":")[3])

    async with Session() as s:
        result = await s.execute(stext("""
            SELECT bp.id, bp.giveaway_id, g.internal_title,
                   bp.payment_method, bp.payment_status, bp.price_stars, bp.price_rub,
                   bp.publish_type, bp.scheduled_at, bp.created_at,
                   array_agg(DISTINCT COALESCE(oc.title, oc.username)) FILTER (WHERE oc.id IS NOT NULL) AS channels
            FROM bot_promotions bp
            JOIN giveaways g ON g.id = bp.giveaway_id
            LEFT JOIN giveaway_channels gc ON gc.giveaway_id = bp.giveaway_id
            LEFT JOIN organizer_channels oc ON oc.id = gc.channel_id
            WHERE bp.id = :pid
            GROUP BY bp.id, g.internal_title
        """), {"pid": promo_id})
        row = result.fetchone()

    if not row:
        await cb.answer("Заявка не найдена.", show_alert=True)
        return

    channels_str = ", ".join(row.channels) if row.channels else "—"
    pay_method   = "Stars ⭐" if row.payment_method == "stars" else "Картой 💳"
    pay_amount   = f"{row.price_stars} ⭐" if row.payment_method == "stars" else f"{row.price_rub} ₽"
    time_str     = (
        "Сразу после утверждения"
        if row.publish_type == "immediate"
        else row.scheduled_at.strftime("%d.%m.%Y %H:%M (МСК)") if row.scheduled_at else "—"
    )

    text = (
        f"📣 <b>Заявка #{promo_id}</b>\n\n"
        f"<b>Розыгрыш:</b> #{row.giveaway_id} — {row.internal_title}\n"
        f"<b>Каналы/группы:</b> {channels_str}\n"
        f"<b>Оплата:</b> {pay_method}, {pay_amount}\n"
        f"<b>Статус оплаты:</b> {row.payment_status}\n"
        f"<b>Время публикации:</b> {time_str}\n"
        f"<b>Заявка создана:</b> {row.created_at.strftime('%d.%m.%Y %H:%M')}"
    )

    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Утвердить", callback_data=f"adm:promo_approve:{promo_id}")
    kb.button(text="◀️ Назад",     callback_data="adm:promo_requests")
    kb.adjust(1)

    await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    await cb.answer()


# ── Утвердить заявку ──────────────────────────────────────────────────────
@dp.callback_query(F.data.startswith("adm:promo_approve:"))
async def cb_admin_promo_approve(cb: CallbackQuery):
    if not await _admin_guard(cb): return
    promo_id = int(cb.data.split(":")[3])

    async with Session() as s:
        result = await s.execute(stext("""
            SELECT bp.*, g.internal_title
            FROM bot_promotions bp
            JOIN giveaways g ON g.id = bp.giveaway_id
            WHERE bp.id = :pid
        """), {"pid": promo_id})
        row = result.fetchone()

        if not row:
            await cb.answer("Заявка не найдена.", show_alert=True)
            return

        now_utc = datetime.now(timezone.utc)

        if row.publish_type == "immediate" or (
            row.scheduled_at and row.scheduled_at <= now_utc
        ):
            # Публикуем сразу
            await s.execute(stext("""
                UPDATE bot_promotions
                SET status = 'published', approved_at = :now, published_at = :now
                WHERE id = :pid
            """), {"now": now_utc, "pid": promo_id})
            await s.commit()
            await _publish_giveaway_to_bot(row.giveaway_id)

            # Уведомляем создателя розыгрыша
            try:
                await bot.send_message(
                    chat_id=row.owner_user_id,
                    text=(
                        f"✅ <b>Ваша заявка на продвижение розыгрыша в боте одобрена!</b>\n\n"
                        f"Розыгрыш <b>#{row.giveaway_id}</b> опубликован в боте — "
                        f"пользователи уже видят его и могут принять участие."
                    ),
                    parse_mode="HTML"
                )
            except Exception as e:
                logging.warning(f"[PROMO] Не удалось уведомить создателя {row.owner_user_id}: {e}")

            await cb.message.edit_text(
                f"✅ Розыгрыш <b>#{row.giveaway_id}</b> опубликован в боте!",
                parse_mode="HTML",
                reply_markup=InlineKeyboardBuilder().button(
                    text="◀️ Назад", callback_data="adm:promo_menu"
                ).as_markup()
            )
        else:
            # Запланированная публикация
            await s.execute(stext("""
                UPDATE bot_promotions
                SET status = 'approved', approved_at = :now
                WHERE id = :pid
            """), {"now": now_utc, "pid": promo_id})
            await s.commit()
            sched_str = row.scheduled_at.strftime("%d.%m.%Y %H:%M")

            # Уведомляем создателя об одобрении
            try:
                sched_str_notify = row.scheduled_at.strftime("%d.%m.%Y %H:%M") if row.scheduled_at else "—"
                await bot.send_message(
                    chat_id=row.owner_user_id,
                    text=(
                        f"✅ <b>Ваша заявка на продвижение розыгрыша в боте одобрена!</b>\n\n"
                        f"Розыгрыш <b>#{row.giveaway_id}</b> будет опубликован "
                        f"<b>{sched_str_notify} (МСК)</b>."
                    ),
                    parse_mode="HTML"
                )
            except Exception as e:
                logging.warning(f"[PROMO] Не удалось уведомить создателя {row.owner_user_id}: {e}")

            await cb.message.edit_text(
                f"✅ Заявка утверждена!\n\nРозыгрыш <b>#{row.giveaway_id}</b> "
                f"будет опубликован <b>{sched_str} (МСК)</b>.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardBuilder().button(
                    text="◀️ Назад", callback_data="adm:promo_menu"
                ).as_markup()
            )

    await cb.answer()


# ── Ожидают публикации (статус approved) ─────────────────────────────────
@dp.callback_query(F.data == "adm:promo_scheduled")
async def cb_admin_promo_scheduled(cb: CallbackQuery):
    if not await _admin_guard(cb): return
    async with Session() as s:
        result = await s.execute(stext("""
            SELECT bp.id, bp.giveaway_id, g.internal_title
            FROM bot_promotions bp
            JOIN giveaways g ON g.id = bp.giveaway_id
            WHERE bp.status = 'approved'
            ORDER BY bp.scheduled_at ASC NULLS LAST
        """))
        rows = result.fetchall()

    if not rows:
        await cb.message.edit_text(
            "⏳ <b>Ожидают публикации</b>\n\nНет запланированных публикаций.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardBuilder().button(
                text="◀️ Назад", callback_data="adm:promo_menu"
            ).as_markup()
        )
        await cb.answer()
        return

    kb = InlineKeyboardBuilder()
    for row in rows:
        kb.button(
            text=f"#{row.giveaway_id} — {row.internal_title[:30]}",
            callback_data=f"adm:promo_sched_info:{row.id}"
        )
    kb.button(text="◀️ Назад", callback_data="adm:promo_menu")
    kb.adjust(1)

    await cb.message.edit_text(
        "⏳ <b>Ожидают публикации</b>\n\nВыберите розыгрыш:",
        parse_mode="HTML",
        reply_markup=kb.as_markup()
    )
    await cb.answer()


# ── Карточка запланированной публикации ───────────────────────────────────
@dp.callback_query(F.data.startswith("adm:promo_sched_info:"))
async def cb_admin_promo_sched_info(cb: CallbackQuery):
    if not await _admin_guard(cb): return
    promo_id = int(cb.data.split(":")[3])

    async with Session() as s:
        result = await s.execute(stext("""
            SELECT bp.id, bp.giveaway_id, g.internal_title,
                   bp.payment_method, bp.price_stars, bp.price_rub,
                   bp.publish_type, bp.scheduled_at, bp.approved_at,
                   array_agg(DISTINCT COALESCE(oc.title, oc.username)) FILTER (WHERE oc.id IS NOT NULL) AS channels
            FROM bot_promotions bp
            JOIN giveaways g ON g.id = bp.giveaway_id
            LEFT JOIN giveaway_channels gc ON gc.giveaway_id = bp.giveaway_id
            LEFT JOIN organizer_channels oc ON oc.id = gc.channel_id
            WHERE bp.id = :pid
            GROUP BY bp.id, g.internal_title
        """), {"pid": promo_id})
        row = result.fetchone()

    if not row:
        await cb.answer("Не найдено.", show_alert=True)
        return

    channels_str = ", ".join(row.channels) if row.channels else "—"
    pay_method   = "Stars ⭐" if row.payment_method == "stars" else "Картой 💳"
    pay_amount   = f"{row.price_stars} ⭐" if row.payment_method == "stars" else f"{row.price_rub} ₽"
    time_str     = (
        row.scheduled_at.strftime("%d.%m.%Y %H:%M (МСК)")
        if row.scheduled_at else "Сразу (уже утверждено)"
    )

    text = (
        f"⏳ <b>Запланирована публикация #{promo_id}</b>\n\n"
        f"<b>Розыгрыш:</b> #{row.giveaway_id} — {row.internal_title}\n"
        f"<b>Каналы/группы:</b> {channels_str}\n"
        f"<b>Оплата:</b> {pay_method}, {pay_amount}\n"
        f"<b>Время публикации:</b> {time_str}\n"
        f"<b>Утверждено:</b> {row.approved_at.strftime('%d.%m.%Y %H:%M') if row.approved_at else '—'}"
    )

    kb = InlineKeyboardBuilder()
    kb.button(text="🚀 Опубликовать сейчас",   callback_data=f"adm:promo_pub_now:{promo_id}")
    kb.button(text="❌ Отменить публикацию",    callback_data=f"adm:promo_cancel_confirm:{promo_id}")
    kb.button(text="◀️ Назад",                  callback_data="adm:promo_scheduled")
    kb.adjust(1)

    await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    await cb.answer()


# ── Опубликовать сейчас ───────────────────────────────────────────────────
@dp.callback_query(F.data.startswith("adm:promo_pub_now:"))
async def cb_admin_promo_pub_now(cb: CallbackQuery):
    if not await _admin_guard(cb): return
    promo_id = int(cb.data.split(":")[3])

    async with Session() as s:
        result = await s.execute(stext(
            "SELECT giveaway_id FROM bot_promotions WHERE id = :pid"
        ), {"pid": promo_id})
        row = result.fetchone()
        if not row:
            await cb.answer("Не найдено.", show_alert=True)
            return

        await s.execute(stext("""
            UPDATE bot_promotions
            SET status = 'published', published_at = :now
            WHERE id = :pid
        """), {"now": datetime.now(timezone.utc), "pid": promo_id})
        await s.commit()

    await _publish_giveaway_to_bot(row.giveaway_id)
    await cb.message.edit_text(
        f"✅ Розыгрыш <b>#{row.giveaway_id}</b> опубликован в боте!",
        parse_mode="HTML",
        reply_markup=InlineKeyboardBuilder().button(
            text="◀️ Назад", callback_data="adm:promo_menu"
        ).as_markup()
    )
    await cb.answer()


# ── Отменить публикацию — подтверждение (pop-up) ─────────────────────────
@dp.callback_query(F.data.startswith("adm:promo_cancel_confirm:"))
async def cb_admin_promo_cancel_confirm(cb: CallbackQuery):
    if not await _admin_guard(cb): return
    promo_id = int(cb.data.split(":")[3])

    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Да, отменить",  callback_data=f"adm:promo_cancel:{promo_id}")
    kb.button(text="◀️ Отмена",        callback_data=f"adm:promo_sched_info:{promo_id}")
    kb.adjust(1)

    await cb.message.edit_text(
        "⚠️ <b>Вы уверены?</b>\n\n"
        "Публикация будет отменена, услуга не будет оказана.",
        parse_mode="HTML",
        reply_markup=kb.as_markup()
    )
    await cb.answer()


# ── Отменить публикацию — выполнение ─────────────────────────────────────
@dp.callback_query(F.data.startswith("adm:promo_cancel:"))
async def cb_admin_promo_cancel(cb: CallbackQuery):
    if not await _admin_guard(cb): return
    promo_id = int(cb.data.split(":")[2])

    async with Session() as s:
        result = await s.execute(stext(
            "SELECT giveaway_id, owner_user_id FROM bot_promotions WHERE id = :pid"
        ), {"pid": promo_id})
        row = result.fetchone()
        if not row:
            await cb.answer("Не найдено.", show_alert=True)
            return

        await s.execute(stext("""
            UPDATE bot_promotions SET status = 'cancelled' WHERE id = :pid
        """), {"pid": promo_id})
        await s.commit()

    try:
        await bot.send_message(
            chat_id=row.owner_user_id,
            text=(
                f"❌ <b>Публикация розыгрыша #{row.giveaway_id} отменена.</b>\n\n"
                f"По вопросам возврата средств обращайтесь: @prizeme_support"
            ),
            parse_mode="HTML"
        )
    except Exception:
        pass

    await cb.message.edit_text(
        f"❌ Публикация розыгрыша <b>#{row.giveaway_id}</b> отменена.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardBuilder().button(
            text="◀️ Назад", callback_data="adm:promo_menu"
        ).as_markup()
    )
    await cb.answer()


# ── Продвинуть вручную — список всех активных розыгрышей (с пагинацией) ──
@dp.callback_query(F.data.startswith("adm:promo_manual:"))
async def cb_admin_promo_manual(cb: CallbackQuery):
    if not await _admin_guard(cb): return
    offset = int(cb.data.split(":")[2])
    page_size = 10

    async with Session() as s:
        result = await s.execute(stext("""
            SELECT id, internal_title
            FROM giveaways
            WHERE status = 'active'
            ORDER BY id DESC
            LIMIT :lim OFFSET :off
        """), {"lim": page_size + 1, "off": offset})
        rows = result.fetchall()

    has_next = len(rows) > page_size
    rows     = rows[:page_size]
    has_prev = offset > 0

    if not rows:
        await cb.message.edit_text(
            "🚀 <b>Продвинуть вручную</b>\n\nНет активных розыгрышей.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardBuilder().button(
                text="◀️ Назад", callback_data="adm:promo_menu"
            ).as_markup()
        )
        await cb.answer()
        return

    kb = InlineKeyboardBuilder()
    for row in rows:
        kb.button(
            text=f"#{row.id} — {row.internal_title[:30]}",
            callback_data=f"adm:promo_manual_info:{row.id}"
        )

    nav_row = []
    if has_prev:
        nav_row.append(("◀️", f"adm:promo_manual:{offset - page_size}"))
    if has_next:
        nav_row.append(("▶️", f"adm:promo_manual:{offset + page_size}"))

    kb.adjust(1)
    if nav_row:
        nav_kb = InlineKeyboardBuilder()
        for label, data in nav_row:
            nav_kb.button(text=label, callback_data=data)
        kb.attach(nav_kb)

    kb.button(text="◀️ Назад", callback_data="adm:promo_menu")
    kb.adjust(1)

    await cb.message.edit_text(
        f"🚀 <b>Продвинуть вручную</b>\n\nВыберите розыгрыш:",
        parse_mode="HTML",
        reply_markup=kb.as_markup()
    )
    await cb.answer()


# ── Продвинуть вручную — карточка розыгрыша ──────────────────────────────
@dp.callback_query(F.data.startswith("adm:promo_manual_info:"))
async def cb_admin_promo_manual_info(cb: CallbackQuery):
    if not await _admin_guard(cb): return
    giveaway_id = int(cb.data.split(":")[2])

    async with Session() as s:
        result = await s.execute(stext("""
            SELECT g.id, g.internal_title, g.end_at_utc,
                   array_agg(DISTINCT COALESCE(oc.title, oc.username)) FILTER (WHERE oc.id IS NOT NULL) AS channels
            FROM giveaways g
            LEFT JOIN giveaway_channels gc ON gc.giveaway_id = g.id
            LEFT JOIN organizer_channels oc ON oc.id = gc.channel_id
            WHERE g.id = :gid AND g.status = 'active'
            GROUP BY g.id
        """), {"gid": giveaway_id})
        row = result.fetchone()

    if not row:
        await cb.answer("Розыгрыш не найден.", show_alert=True)
        return

    channels_str = ", ".join(row.channels) if row.channels else "—"
    end_str      = row.end_at_utc.strftime("%d.%m.%Y %H:%M") if row.end_at_utc else "—"

    text = (
        f"🚀 <b>Розыгрыш #{giveaway_id}</b>\n\n"
        f"<b>Название:</b> {row.internal_title}\n"
        f"<b>Каналы/группы:</b> {channels_str}\n"
        f"<b>Завершается:</b> {end_str} UTC"
    )

    kb = InlineKeyboardBuilder()
    kb.button(text="📢 Опубликовать", callback_data=f"adm:promo_manual_confirm:{giveaway_id}")
    kb.button(text="◀️ Назад",        callback_data="adm:promo_manual:0")
    kb.adjust(1)

    await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    await cb.answer()


# ── Продвинуть вручную — подтверждение (pop-up) ───────────────────────────
@dp.callback_query(F.data.startswith("adm:promo_manual_confirm:"))
async def cb_admin_promo_manual_confirm(cb: CallbackQuery):
    if not await _admin_guard(cb): return
    giveaway_id = int(cb.data.split(":")[2])

    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Да, опубликовать", callback_data=f"adm:promo_manual_pub:{giveaway_id}")
    kb.button(text="◀️ Отмена",           callback_data=f"adm:promo_manual_info:{giveaway_id}")
    kb.adjust(1)

    await cb.message.edit_text(
        f"⚠️ <b>Опубликовать розыгрыш #{giveaway_id} в боте?</b>\n\n"
        f"Все пользователи получат уведомление.",
        parse_mode="HTML",
        reply_markup=kb.as_markup()
    )
    await cb.answer()


# ── Продвинуть вручную — публикация ──────────────────────────────────────
@dp.callback_query(F.data.startswith("adm:promo_manual_pub:"))
async def cb_admin_promo_manual_pub(cb: CallbackQuery):
    if not await _admin_guard(cb): return
    giveaway_id = int(cb.data.split(":")[2])

    await _publish_giveaway_to_bot(giveaway_id)

    await cb.message.edit_text(
        f"✅ Розыгрыш <b>#{giveaway_id}</b> опубликован в боте!",
        parse_mode="HTML",
        reply_markup=InlineKeyboardBuilder().button(
            text="◀️ Назад", callback_data="adm:promo_menu"
        ).as_markup()
    )
    await cb.answer()


# ── Вспомогательная функция публикации розыгрыша в бот ───────────────────
async def _publish_giveaway_to_bot(giveaway_id: int):
    """Публикует пост розыгрыша в личку всем пользователям бота."""
    async with Session() as s:
        gw_result = await s.execute(stext("""
            SELECT g.id, g.internal_title, g.end_at_utc, g.owner_user_id,
                   array_agg(DISTINCT COALESCE(oc.title, oc.username)) FILTER (WHERE oc.id IS NOT NULL) AS channels
            FROM giveaways g
            LEFT JOIN giveaway_channels gc ON gc.giveaway_id = g.id
            LEFT JOIN organizer_channels oc ON oc.id = gc.channel_id
            WHERE g.id = :gid AND g.status = 'active'
            GROUP BY g.id
        """), {"gid": giveaway_id})
        gw = gw_result.fetchone()

        if not gw:
            logging.warning(f"[PROMO_PUB] Розыгрыш #{giveaway_id} не найден или неактивен")
            return

        # Получаем всех пользователей
        users_result = await s.execute(stext(
            "SELECT user_id FROM users ORDER BY user_id ASC"
        ))
        user_ids = [r.user_id for r in users_result.fetchall()]

    channels_str = ", ".join(gw.channels) if gw.channels else "—"
    end_str      = gw.end_at_utc.strftime("%d.%m.%Y %H:%M") if gw.end_at_utc else "—"

    text = (
        f"🎉 <b>Новый розыгрыш!</b>\n\n"
        f"<b>{gw.internal_title}</b>\n\n"
        f"📢 <b>Каналы:</b> {channels_str}\n"
        f"⏰ <b>Завершается:</b> {end_str} UTC\n\n"
        f"Нажмите «Участвовать», чтобы принять участие!"
    )

    kb = InlineKeyboardBuilder()
    kb.button(text="🎟 Участвовать", callback_data=f"participate:{giveaway_id}")
    markup = kb.as_markup()

    sent = 0
    failed = 0
    for uid in user_ids:
        try:
            await bot.send_message(chat_id=uid, text=text,
                                   parse_mode="HTML", reply_markup=markup)
            sent += 1
            await asyncio.sleep(0.05)  # антифлуд
        except Exception:
            failed += 1

    logging.info(f"[PROMO_PUB] #{giveaway_id}: отправлено {sent}, ошибок {failed}")


# ── Планировщик запланированных публикаций ────────────────────────────────
async def check_scheduled_promotions():
    """Запускается планировщиком каждую минуту — публикует розыгрыши по расписанию."""
    try:
        now_utc = datetime.now(timezone.utc)
        async with Session() as s:
            result = await s.execute(stext("""
                SELECT id, giveaway_id
                FROM bot_promotions
                WHERE status = 'approved'
                  AND publish_type = 'scheduled'
                  AND scheduled_at <= :now
            """), {"now": now_utc})
            due = result.fetchall()

            for row in due:
                await s.execute(stext("""
                    UPDATE bot_promotions
                    SET status = 'published', published_at = :now
                    WHERE id = :pid
                """), {"now": now_utc, "pid": row.id})
            await s.commit()

        for row in due:
            await _publish_giveaway_to_bot(row.giveaway_id)
            logging.info(f"[PROMO_SCHED] Опубликован #{row.giveaway_id}")

    except Exception as e:
        logging.error(f"[PROMO_SCHED] Ошибка: {e}")


# ── Уровень 3: меню топ-розыгрышей ───────────────────────────────────────
def kb_admin_top_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📋 Активные размещения", callback_data="adm:top_list")
    kb.button(text="➕ Добавить в топ",      callback_data="adm:top_add_start")
    kb.button(text="➖ Убрать из топа",      callback_data="adm:top_remove_start")
    kb.button(text="◀️ Назад",               callback_data="adm:back_services")
    kb.adjust(1)
    return kb.as_markup()

# ── Общий guard для всех admin-callback ──────────────────────────────────
async def _admin_guard(cb: CallbackQuery) -> bool:
    """Возвращает True если доступ разрешён, иначе отвечает и возвращает False."""
    if cb.from_user and cb.from_user.id == BOT_OWNER_ID:
        return True
    await cb.answer("Нет доступа.", show_alert=True)
    return False


@dp.message(Command("admin"))
@owner_only
async def cmd_admin(m: Message):
    """Главная панель администратора."""
    await m.answer(
        "🔧 <b>Панель администратора PrizeMe</b>\n\n"
        "Выберите раздел:",
        parse_mode="HTML",
        reply_markup=kb_admin_main()
    )


# ── Уровень 2: переход в «Управление сервисами» ───────────────────────────
@dp.callback_query(F.data == "adm:services")
async def cb_admin_services(cb: CallbackQuery):
    if not await _admin_guard(cb): return
    await cb.message.edit_text(
        "⚙️ <b>Управление сервисами</b>\n\n"
        "Выберите сервис:",
        parse_mode="HTML",
        reply_markup=kb_admin_services()
    )
    await cb.answer()


# ── Уровень 3: меню топ-розыгрышей ───────────────────────────────────────
@dp.callback_query(F.data == "adm:top_menu")
async def cb_admin_top_menu(cb: CallbackQuery):
    if not await _admin_guard(cb): return
    await cb.message.edit_text(
        "🏆 <b>Топ-розыгрыши</b>\n\n"
        "Выберите действие:",
        parse_mode="HTML",
        reply_markup=kb_admin_top_menu()
    )
    await cb.answer()


# ── Назад: сервисы → главная ──────────────────────────────────────────────
@dp.callback_query(F.data == "adm:back_main")
async def cb_admin_back_main(cb: CallbackQuery):
    if not await _admin_guard(cb): return
    await cb.message.edit_text(
        "🔧 <b>Панель администратора PrizeMe</b>\n\n"
        "Выберите раздел:",
        parse_mode="HTML",
        reply_markup=kb_admin_main()
    )
    await cb.answer()


# ── Назад: топ → сервисы ─────────────────────────────────────────────────
@dp.callback_query(F.data == "adm:back_services")
async def cb_admin_back_services(cb: CallbackQuery):
    if not await _admin_guard(cb): return
    await cb.message.edit_text(
        "⚙️ <b>Управление сервисами</b>\n\n"
        "Выберите сервис:",
        parse_mode="HTML",
        reply_markup=kb_admin_services()
    )
    await cb.answer()


# ── Назад: карточка/выбор → меню топа ────────────────────────────────────
@dp.callback_query(F.data == "adm:back_top_menu")
async def cb_admin_back_top_menu(cb: CallbackQuery):
    if not await _admin_guard(cb): return
    await cb.message.edit_text(
        "🏆 <b>Топ-розыгрыши</b>\n\n"
        "Выберите действие:",
        parse_mode="HTML",
        reply_markup=kb_admin_top_menu()
    )
    await cb.answer()


# ── Активные топ-размещения ───────────────────────────────────────────────
@dp.callback_query(F.data == "adm:top_list")
async def cb_admin_top_list(cb: CallbackQuery):
    if not await _admin_guard(cb): return

    async with Session() as s:
        result = await s.execute(stext("""
            SELECT tp.giveaway_id, g.internal_title,
                   tp.placement_type, tp.starts_at, tp.ends_at
            FROM top_placements tp
            JOIN giveaways g ON g.id = tp.giveaway_id
            WHERE tp.is_active = true AND tp.ends_at > NOW()
            ORDER BY tp.starts_at ASC
        """))
        rows = result.fetchall()

    if not rows:
        text = "ℹ️ Активных топ-размещений нет."
    else:
        lines = ["<b>Активные топ-размещения:</b>\n"]
        for row in rows:
            ends = row.ends_at.strftime("%d.%m.%Y %H:%M")
            lines.append(
                f"• <b>#{row.giveaway_id}</b> {row.internal_title}\n"
                f"  Тип: <code>{row.placement_type}</code> | До: <code>{ends} UTC</code>"
            )
        text = "\n".join(lines)

    await cb.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardBuilder()
            .button(text="◀️ Назад", callback_data="adm:back_top_menu")
            .as_markup()
    )
    await cb.answer()


# ── Добавить в топ: выбор розыгрыша ──────────────────────────────────────
@dp.callback_query(F.data == "adm:top_add_start")
async def cb_admin_top_add_start(cb: CallbackQuery):
    if not await _admin_guard(cb): return

    # Берём все активные розыгрыши, которых ещё НЕТ в топе
    async with Session() as s:
        result = await s.execute(stext("""
            SELECT g.id, g.internal_title
            FROM giveaways g
            WHERE g.status = 'active'
              AND g.id NOT IN (
                SELECT giveaway_id FROM top_placements
                WHERE is_active = true AND ends_at > NOW()
              )
            ORDER BY g.id DESC
        """))
        rows = result.fetchall()

    if not rows:
        await cb.message.edit_text(
            "ℹ️ Нет активных розыгрышей для добавления в топ\n"
            "(все уже в топе или активных розыгрышей нет).",
            reply_markup=InlineKeyboardBuilder()
                .button(text="◀️ Назад", callback_data="adm:back_top_menu")
                .as_markup()
        )
        await cb.answer()
        return

    kb = InlineKeyboardBuilder()
    for row in rows:
        kb.button(
            text=f"🎁 #{row.id} {row.internal_title[:35]}",
            callback_data=f"adm:top_add_info:{row.id}"
        )
    kb.button(text="◀️ Назад", callback_data="adm:back_top_menu")
    kb.adjust(1)

    await cb.message.edit_text(
        "➕ <b>Добавить в топ-розыгрыши</b>\n\n"
        "Выберите розыгрыш:",
        parse_mode="HTML",
        reply_markup=kb.as_markup()
    )
    await cb.answer()


# ── Добавить в топ: карточка розыгрыша ───────────────────────────────────
@dp.callback_query(F.data.startswith("adm:top_add_info:"))
async def cb_admin_top_add_info(cb: CallbackQuery):
    if not await _admin_guard(cb): return

    giveaway_id = int(cb.data.split(":")[2])

    async with Session() as s:
        # Основные данные розыгрыша
        gw = await s.get(Giveaway, giveaway_id)
        if not gw:
            await cb.answer("Розыгрыш не найден.", show_alert=True)
            return

        # Подключённые каналы
        channels_result = await s.execute(stext("""
            SELECT COALESCE(gc.title, oc.title, oc.username) AS title,
                   oc.chat_id
            FROM giveaway_channels gc
            JOIN organizer_channels oc ON oc.id = gc.channel_id
            WHERE gc.giveaway_id = :gid
        """), {"gid": giveaway_id})
        channels = channels_result.fetchall()

        # Число участников
        participants_result = await s.execute(stext("""
            SELECT COUNT(DISTINCT user_id) AS cnt
            FROM entries
            WHERE giveaway_id = :gid
        """), {"gid": giveaway_id})
        participants = participants_result.scalar() or 0

        # Статус подписки организатора
        owner = await s.get(BotUser, gw.owner_user_id)
        is_premium = getattr(owner, "user_status", "standard") == "premium"

    # Форматируем даты
    created = gw.created_at.strftime("%d.%m.%Y %H:%M") if gw.created_at else "—"
    ends    = gw.end_at_utc.strftime("%d.%m.%Y %H:%M") if gw.end_at_utc else "—"

    # Каналы в виде гиперссылок
    if channels:
        ch_lines = []
        for ch in channels:
            if ch.chat_id:
                # Публичная ссылка: убираем минус и добавляем 100 для supergroup ID
                abs_id = str(abs(ch.chat_id))
                if abs_id.startswith("100"):
                    abs_id = abs_id[3:]
                ch_lines.append(f'<a href="https://t.me/c/{abs_id}/1">{ch.title or ch.chat_id}</a>')
            else:
                ch_lines.append(ch.title or "—")
        channels_text = ", ".join(ch_lines)
    else:
        channels_text = "нет"

    text = (
        f"🎁 <b>{gw.internal_title}</b>\n\n"
        f"📅 Запущен: <code>{created}</code>\n"
        f"⏰ Завершится: <code>{ends} UTC</code>\n"
        f"👥 Участников: <b>{participants}</b>\n"
        f"💎 Premium у организатора: {'✅ Да' if is_premium else '❌ Нет'}\n"
        f"📢 Каналы: {channels_text}"
    )

    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Добавить в топ (24 часа)",   callback_data=f"adm:top_confirm:{giveaway_id}:1:day")
    kb.button(text="✅ Добавить в топ (1 неделя)",  callback_data=f"adm:top_confirm:{giveaway_id}:7:week")
    kb.button(text="◀️ Назад",                           callback_data="adm:top_add_start")
    kb.adjust(1)

    await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    await cb.answer()


# ── Добавить в топ: подтверждение ────────────────────────────────────────
@dp.callback_query(F.data.startswith("adm:top_confirm:"))
async def cb_admin_top_confirm(cb: CallbackQuery):
    if not await _admin_guard(cb): return

    parts          = cb.data.split(":")
    giveaway_id    = int(parts[2])
    days           = int(parts[3])
    placement_type = parts[4]

    async with Session() as s:
        gw = await s.get(Giveaway, giveaway_id)
        if not gw:
            await cb.answer("Розыгрыш не найден.", show_alert=True)
            return

        now_utc = datetime.now(timezone.utc)
        ends_at = now_utc + timedelta(days=days)

        # Деактивируем предыдущее размещение
        await s.execute(
            stext("UPDATE top_placements SET is_active = false WHERE giveaway_id = :gid"),
            {"gid": giveaway_id}
        )

        # Создаём service_order
        order_result = await s.execute(
            stext("""
                INSERT INTO service_orders
                    (giveaway_id, owner_user_id, service_type, status, price_rub)
                VALUES (:gid, :uid, 'top_placement', 'active', 0)
                RETURNING id
            """),
            {"gid": giveaway_id, "uid": gw.owner_user_id}
        )
        order_id = order_result.scalar_one()

        # Создаём top_placement
        await s.execute(
            stext("""
                INSERT INTO top_placements
                    (giveaway_id, order_id, starts_at, ends_at, placement_type, is_active)
                VALUES (:gid, :oid, :starts, :ends, :ptype, true)
            """),
            {"gid": giveaway_id, "oid": order_id, "starts": now_utc,
             "ends": ends_at, "ptype": placement_type}
        )
        await s.commit()

    await cb.answer("✅ Добавлено в топ!", show_alert=True)
    await cb.message.edit_text(
        "🏆 <b>Топ-розыгрыши</b>\n\n"
        "Выберите действие:",
        parse_mode="HTML",
        reply_markup=kb_admin_top_menu()
    )


# ── Убрать из топа: выбор розыгрыша ──────────────────────────────────────
@dp.callback_query(F.data == "adm:top_remove_start")
async def cb_admin_top_remove_start(cb: CallbackQuery):
    if not await _admin_guard(cb): return

    async with Session() as s:
        result = await s.execute(stext("""
            SELECT tp.giveaway_id, g.internal_title,
                   tp.placement_type, tp.ends_at
            FROM top_placements tp
            JOIN giveaways g ON g.id = tp.giveaway_id
            WHERE tp.is_active = true AND tp.ends_at > NOW()
            ORDER BY tp.starts_at ASC
        """))
        rows = result.fetchall()

    if not rows:
        await cb.message.edit_text(
            "ℹ️ Нет активных размещений для удаления.",
            reply_markup=InlineKeyboardBuilder()
                .button(text="◀️ Назад", callback_data="adm:back_top_menu")
                .as_markup()
        )
        await cb.answer()
        return

    kb = InlineKeyboardBuilder()
    for row in rows:
        kb.button(
            text=f"❌ #{row.giveaway_id} {row.internal_title[:35]}",
            callback_data=f"adm:top_remove_info:{row.giveaway_id}"
        )
    kb.button(text="◀️ Назад", callback_data="adm:back_top_menu")
    kb.adjust(1)

    await cb.message.edit_text(
        "➖ <b>Убрать из топ-розыгрышей</b>\n\n"
        "Выберите розыгрыш:",
        parse_mode="HTML",
        reply_markup=kb.as_markup()
    )
    await cb.answer()


# ── Убрать из топа: карточка розыгрыша ───────────────────────────────────
@dp.callback_query(F.data.startswith("adm:top_remove_info:"))
async def cb_admin_top_remove_info(cb: CallbackQuery):
    if not await _admin_guard(cb): return

    giveaway_id = int(cb.data.split(":")[2])

    async with Session() as s:
        gw = await s.get(Giveaway, giveaway_id)
        if not gw:
            await cb.answer("Розыгрыш не найден.", show_alert=True)
            return

        channels_result = await s.execute(stext("""
            SELECT COALESCE(gc.title, oc.title, oc.username) AS title,
                   oc.chat_id
            FROM giveaway_channels gc
            JOIN organizer_channels oc ON oc.id = gc.channel_id
            WHERE gc.giveaway_id = :gid
        """), {"gid": giveaway_id})
        channels = channels_result.fetchall()

        participants_result = await s.execute(stext("""
            SELECT COUNT(DISTINCT user_id) AS cnt
            FROM entries WHERE giveaway_id = :gid
        """), {"gid": giveaway_id})
        participants = participants_result.scalar() or 0

        placement_result = await s.execute(stext("""
            SELECT placement_type, starts_at, ends_at
            FROM top_placements
            WHERE giveaway_id = :gid AND is_active = true
            LIMIT 1
        """), {"gid": giveaway_id})
        placement = placement_result.fetchone()

        owner = await s.get(BotUser, gw.owner_user_id)
        is_premium = getattr(owner, "user_status", "standard") == "premium"

    ends = gw.end_at_utc.strftime("%d.%m.%Y %H:%M") if gw.end_at_utc else "—"
    p_ends = placement.ends_at.strftime("%d.%m.%Y %H:%M") if placement and placement.ends_at else "—"
    p_type = placement.placement_type if placement else "—"

    if channels:
        ch_lines = []
        for ch in channels:
            if ch.chat_id:
                abs_id = str(abs(ch.chat_id))
                if abs_id.startswith("100"):
                    abs_id = abs_id[3:]
                ch_lines.append(f'<a href="https://t.me/c/{abs_id}/1">{ch.title or ch.chat_id}</a>')
            else:
                ch_lines.append(ch.title or "—")
        channels_text = ", ".join(ch_lines)
    else:
        channels_text = "нет"

    text = (
        f"🎁 <b>{gw.internal_title}</b>\n\n"
        f"⏰ Завершится: <code>{ends} UTC</code>\n"
        f"👥 Участников: <b>{participants}</b>\n"
        f"💎 Premium у организатора: {'✅ Да' if is_premium else '❌ Нет'}\n"
        f"📢 Каналы: {channels_text}\n\n"
        f"🏆 В топе: тип <code>{p_type}</code> | до <code>{p_ends} UTC</code>"
    )

    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Убрать из топа",  callback_data=f"adm:top_del:{giveaway_id}")
    kb.button(text="◀️ Отмена",          callback_data="adm:top_remove_start")
    kb.adjust(1)

    await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    await cb.answer()


# ── Убрать из топа: подтверждение ────────────────────────────────────────
@dp.callback_query(F.data.startswith("adm:top_del:"))
async def cb_admin_top_delete(cb: CallbackQuery):
    if not await _admin_guard(cb): return

    giveaway_id = int(cb.data.split(":")[2])

    async with Session() as s:
        await s.execute(
            stext("UPDATE top_placements SET is_active = false WHERE giveaway_id = :gid AND is_active = true"),
            {"gid": giveaway_id}
        )
        await s.commit()

    await cb.answer(f"✅ Розыгрыш #{giveaway_id} убран из топа.", show_alert=True)
    await cb.message.edit_text(
        "🏆 <b>Топ-розыгрыши</b>\n\n"
        "Выберите действие:",
        parse_mode="HTML",
        reply_markup=kb_admin_top_menu()
    )

# ============================================================
# ADMIN: управление топ-размещениями
# ============================================================

@dp.message(Command("admin_top_add"))
@owner_only
async def cmd_admin_top_add(m: Message):
    """
    Добавить розыгрыш в топ вручную (для тестирования).
    Использование:
      /admin_top_add <giveaway_id> <days> <type>
      type: week | full_period
    Пример:
      /admin_top_add 42 1 day    (24 часа)
      /admin_top_add 42 7 week   (1 неделя)
    """
    parts = (m.text or "").split()
    if len(parts) < 3:
        await m.answer(
            "Использование:\n"
            "<code>/admin_top_add &lt;giveaway_id&gt; &lt;days&gt; &lt;type&gt;</code>\n\n"
            "type: <code>week</code> | <code>full_period</code>\n"
            "Если type=full_period, days игнорируется — срок до конца розыгрыша.",
            parse_mode="HTML"
        )
        return

    try:
        giveaway_id    = int(parts[1])
        days           = int(parts[2])
        placement_type = parts[3] if len(parts) > 3 else "week"
    except ValueError:
        await m.answer("❌ Некорректные параметры. giveaway_id и days должны быть числами.")
        return

    if placement_type not in ("day", "week"):
        await m.answer("❌ type должен быть: day или week")
        return

    async with Session() as s:
        # Проверяем что розыгрыш существует и активен
        gw = await s.get(Giveaway, giveaway_id)
        if not gw:
            await m.answer(f"❌ Розыгрыш #{giveaway_id} не найден.")
            return
        if gw.status != "active":
            await m.answer(f"❌ Розыгрыш #{giveaway_id} не активен (статус: {gw.status}).")
            return

        # Определяем ends_at
        now_utc = datetime.now(timezone.utc)
        if placement_type == "full_period":
            # До конца розыгрыша
            ends_at = gw.end_at_utc if gw.end_at_utc.tzinfo else gw.end_at_utc.replace(tzinfo=timezone.utc)
        else:
            ends_at = now_utc + timedelta(days=days if days > 0 else 7)

        # Деактивируем предыдущее размещение для этого розыгрыша (если есть)
        await s.execute(
            stext("UPDATE top_placements SET is_active = false WHERE giveaway_id = :gid"),
            {"gid": giveaway_id}
        )

        # Создаём service_order (ручное, без оплаты)
        order_result = await s.execute(
            stext("""
                INSERT INTO service_orders
                    (giveaway_id, owner_user_id, service_type, status, price_rub)
                VALUES
                    (:gid, :uid, 'top_placement', 'active', 0)
                RETURNING id
            """),
            {"gid": giveaway_id, "uid": gw.owner_user_id}
        )
        order_id = order_result.scalar_one()

        # Создаём top_placement
        await s.execute(
            stext("""
                INSERT INTO top_placements
                    (giveaway_id, order_id, starts_at, ends_at, placement_type, is_active)
                VALUES
                    (:gid, :oid, :starts, :ends, :ptype, true)
            """),
            {
                "gid":    giveaway_id,
                "oid":    order_id,
                "starts": now_utc,
                "ends":   ends_at,
                "ptype":  placement_type,
            }
        )
        await s.commit()

    await m.answer(
        f"✅ Розыгрыш <b>#{giveaway_id}</b> добавлен в топ.\n"
        f"Тип: <code>{placement_type}</code>\n"
        f"До: <code>{ends_at.strftime('%d.%m.%Y %H:%M')} UTC</code>",
        parse_mode="HTML"
    )
    logging.info("[ADMIN] top_placement добавлен: giveaway_id=%s, ends_at=%s", giveaway_id, ends_at)


@dp.message(Command("admin_top_remove"))
@owner_only
async def cmd_admin_top_remove(m: Message):
    """
    Убрать розыгрыш из топа вручную.
    Использование: /admin_top_remove <giveaway_id>
    """
    parts = (m.text or "").split()
    if len(parts) < 2:
        await m.answer("Использование: <code>/admin_top_remove &lt;giveaway_id&gt;</code>", parse_mode="HTML")
        return

    try:
        giveaway_id = int(parts[1])
    except ValueError:
        await m.answer("❌ giveaway_id должен быть числом.")
        return

    async with Session() as s:
        result = await s.execute(
            stext("""
                UPDATE top_placements
                SET is_active = false
                WHERE giveaway_id = :gid AND is_active = true
            """),
            {"gid": giveaway_id}
        )
        await s.commit()
        updated = result.rowcount

    if updated:
        await m.answer(f"✅ Розыгрыш #{giveaway_id} убран из топа.")
    else:
        await m.answer(f"ℹ️ Розыгрыш #{giveaway_id} не был в топе.")


@dp.message(Command("admin_top_list"))
@owner_only
async def cmd_admin_top_list(m: Message):
    """
    Показать все активные топ-размещения.
    Использование: /admin_top_list
    """
    async with Session() as s:
        result = await s.execute(stext("""
            SELECT
                tp.giveaway_id,
                g.internal_title,
                tp.placement_type,
                tp.starts_at,
                tp.ends_at
            FROM top_placements tp
            JOIN giveaways g ON g.id = tp.giveaway_id
            WHERE tp.is_active = true AND tp.ends_at > NOW()
            ORDER BY tp.starts_at ASC
        """))
        rows = result.fetchall()

    if not rows:
        await m.answer("ℹ️ Активных топ-размещений нет.")
        return

    lines = ["<b>Активные топ-размещения:</b>\n"]
    for row in rows:
        ends = row.ends_at.strftime("%d.%m.%Y %H:%M") if row.ends_at else "—"
        lines.append(
            f"• <b>#{row.giveaway_id}</b> {row.internal_title}\n"
            f"  Тип: <code>{row.placement_type}</code> | До: <code>{ends} UTC</code>"
        )

    await m.answer("\n".join(lines), parse_mode="HTML")


@dp.message(Command("admin_draw"))
@owner_only
async def cmd_admin_draw(m: Message):
    """Ручной запуск определения победителей"""
    print(f"🔄 COMMAND /admin_draw получен: {m.text}")
    
    if not m.text or " " not in m.text:
        await m.answer("Использование: /admin_draw <giveaway_id>")
        return
    
    try:
        gid = int(m.text.split(" ")[1])
    except ValueError:
        await m.answer("❌ Некорректный ID розыгрыша")
        return
    
    print(f"🎯 Запуск finalize_and_draw_job для розыгрыша {gid}")
    await m.answer(f"🔄 Запускаю ручное определение победителей для розыгрыша {gid}...")
    
    await finalize_and_draw_job(gid)
    
    print(f"✅ finalize_and_draw_job завершена для {gid}")
    await m.answer("✅ Функция finalize_and_draw_job завершена. Проверьте логи.")

@dp.message(Command("debug_scheduler"))
async def cmd_debug_scheduler(m: Message):
    """Проверка запланированных jobs"""
    jobs = scheduler.get_jobs()
    response = f"📋 Scheduled jobs: {len(jobs)}\n"
    for job in jobs:
        response += f"• {job.id} - {job.next_run_time}\n"
    await m.answer(response)

@dp.message(Command("debug_scheduler_full"))
async def cmd_debug_scheduler_full(m: Message):
    """Полная диагностика планировщика"""
    jobs = scheduler.get_jobs()
    response = f"📋 Scheduled jobs: {len(jobs)}\n\n"
    
    for job in jobs:
        response += f"• **{job.id}**\n"
        response += f"  Next run: {job.next_run_time}\n"
        response += f"  Trigger: {job.trigger}\n"
        response += f"  Func: {job.func.__name__ if hasattr(job.func, '__name__') else job.func}\n\n"
    
    # Проверим активные розыгрыши которые ДОЛЖНЫ быть запланированы
    async with session_scope() as s:
        active_giveaways = await s.execute(
            stext("SELECT id, internal_title, end_at_utc FROM giveaways WHERE status='active'")
        )
        active_rows = active_giveaways.all()
        
        response += f"🎯 Active giveaways in DB: {len(active_rows)}\n"
        for gid, title, end_at in active_rows:
            job_id = f"final_{gid}"
            job_exists = any(job.id == job_id for job in jobs)
            status = "✅" if job_exists else "❌"
            response += f"{status} {title} (ID: {gid}) - ends: {end_at}\n"
    
    await m.answer(response)

@dp.message(Command("debug_giveaway"))
async def cmd_debug_giveaway(m: Message):
    """Диагностика конкретного розыгрыша"""
    try:
        gid = int(m.text.split(" ")[1])
    except:
        await m.answer("Использование: /debug_giveaway <id>")
        return
    
    async with session_scope() as s:
        # Данные розыгрыша
        gw = await s.get(Giveaway, gid)
        if not gw:
            await m.answer("❌ Розыгрыш не найден")
            return
        
        # Участники
        entries = await s.execute(
            stext("SELECT user_id, ticket_code, prelim_ok, final_ok FROM entries WHERE giveaway_id=:gid"),
            {"gid": gid}
        )
        entries_data = entries.all()
        
        # Победители
        winners = await s.execute(
            stext("SELECT user_id, rank FROM winners WHERE giveaway_id=:gid"),
            {"gid": gid}
        )
        winners_data = winners.all()
        
        response = f"""
📊 **Диагностика розыгрыша {gid}**

**Основные данные:**
- Название: {gw.internal_title}
- Статус: {gw.status}
- Победителей: {gw.winners_count}
- Окончание: {gw.end_at_utc}

**Участники:** {len(entries_data)}
**Победители в БД:** {len(winners_data)}

**Статус планировщика:**
"""
        
        # Проверим job в планировщике
        job_id = f"final_{gid}"
        job = scheduler.get_job(job_id)
        if job:
            response += f"✅ Job '{job_id}' запланирован на {job.next_run_time}"
        else:
            response += f"❌ Job '{job_id}' НЕ найден в планировщике!"
    
    await m.answer(response)

@dp.message(Command("test_finalize"))
async def cmd_test_finalize(m: Message):
    """Тест что функция finalize_and_draw_job существует"""
    try:
        # Пробуем вызвать функцию напрямую
        import inspect
        source = inspect.getsource(finalize_and_draw_job)
        await m.answer(f"✅ Функция существует\nПервые 200 символов:\n{source[:200]}")
    except Exception as e:
        await m.answer(f"❌ Ошибка: {e}")

async def show_my_giveaways_menu(m: Message | CallbackQuery):
    """УНИВЕРСАЛЬНАЯ ВЕРСИЯ: показывает новое главное меню 'Мои розыгрыши'"""
    if isinstance(m, CallbackQuery):
        message = m.message
        is_callback = True
    else:
        message = m
        is_callback = False

    text = "🎯 <b>Мои розыгрыши</b>\n\nВыберите роль для просмотра розыгрышей:"
    
    if is_callback:
        # Для callback: редактируем существующее сообщение
        await message.edit_text(
            text, 
            reply_markup=kb_my_events_menu(),
            parse_mode="HTML"
        )
        if isinstance(m, CallbackQuery):
            await m.answer()
    else:
        # Для обычного сообщения: отправляем новое
        await message.answer(
            text, 
            reply_markup=kb_my_events_menu(),
            parse_mode="HTML"
        )


# === ДИАГНОСТИЧЕСКИЕ КОМАНДЫ ПРЕМИУМ ===

@dp.message(Command("debug_botuser"))
async def cmd_debug_botuser(m: Message):
    """Диагностика регистрации в bot_users"""
    user_id = m.from_user.id
    
    # 1. Проверяем есть ли пользователь в bot_users
    async with session_scope() as s:
        bot_user = await s.get(BotUser, user_id)
        
        if bot_user:
            # Проверяем актуальное членство в группе
            is_in_group = await check_group_membership(user_id)
            
            await m.answer(
                f"✅ <b>Пользователь найден в bot_users:</b>\n\n"
                f"🆔 User ID: <code>{user_id}</code>\n"
                f"📋 Статус в БД: <b>{bot_user.user_status}</b>\n"
                f"📋 Актуальный статус группы: {'✅ В группе' if is_in_group else '❌ Не в группе'}\n"
                f"👤 Username: {bot_user.username or 'не указан'}\n"
                f"📅 Создан: {bot_user.created_at}\n"
                f"🔄 Обновлен: {bot_user.updated_at}\n"
                f"⏰ Последняя проверка группы: {bot_user.last_group_check or 'никогда'}\n\n"
                f"<i>Используйте /start для принудительной проверки статуса</i>",
                parse_mode="HTML"
            )
        else:
            await m.answer(
                f"❌ <b>Пользователь НЕ найден в bot_users</b>\n\n"
                f"🆔 User ID: <code>{user_id}</code>\n"
                f"👤 Username: {m.from_user.username}\n"
                f"👤 First name: {m.from_user.first_name}\n\n"
                f"<i>Попробуйте команду /start для регистрации</i>",
                parse_mode="HTML"
            )

@dp.message(Command("force_check"))
async def cmd_force_check(m: Message):
    """Принудительная проверка и обновление статуса"""
    user_id = m.from_user.id
    
    try:
        # 1. Регистрируем/обновляем пользователя
        bot_user = await ensure_bot_user(user_id, m.from_user.username, m.from_user.first_name)
        
        # 2. Проверяем актуальное членство в группе
        is_in_group = await check_group_membership(user_id)
        
        await m.answer(
            f"🔄 <b>Принудительная проверка завершена:</b>\n\n"
            f"🆔 User ID: <code>{user_id}</code>\n"
            f"📋 Новый статус: <b>{bot_user.user_status}</b>\n"
            f"👥 В премиум-группе: {'✅ Да' if is_in_group else '❌ Нет'}\n"
            f"⏰ Время проверки: {bot_user.last_group_check}\n\n"
            f"<i>Статус автоматически обновляется при каждом взаимодействии</i>",
            parse_mode="HTML"
        )
        
    except Exception as e:
        await m.answer(
            f"❌ <b>Ошибка при проверке:</b>\n\n"
            f"🆔 User ID: <code>{user_id}</code>\n"
            f"💥 Ошибка: {e}\n\n"
            f"<i>Проверьте логи бота</i>",
            parse_mode="HTML"
        )
        logging.error(f"❌ Ошибка в force_check для {user_id}: {e}")


# ===== Команда /menu чтобы вернуть/показать клавиатуру внизу =====
@dp.message(Command("menu"))
async def cmd_menu(m: Message):
    # показать актуальную клавиатуру с системными кнопками
    await m.answer("Главное меню:", reply_markup=reply_main_kb())

@dp.message(Command("hide"))
async def hide_menu(m: Message):
    # Полностью убрать клавиатуру
    await m.answer("Кнопки скрыты. Чтобы вернуть — отправьте /menu.", reply_markup=ReplyKeyboardRemove())

@dp.message(Command("create"))
async def create_giveaway_start(message: Message, state: FSMContext):
    await state.clear()
    await state.update_data(owner=message.from_user.id)
    
    # Получаем лимит для пользователя
    limit, status = await get_winners_limit(message.from_user.id)
    
    await message.answer(
        "✏️ Введите название розыгрыша:\n\n"
        "Максимум — <b>50 символов</b>\n\n"
        "Это название будет отображаться пользователям в списке розыгрышей "
        "в боте. Подойдите к выбору названия как можно более ответственно, "
        "чтобы участники могли легко идентифицировать ваш розыгрыш среди всех остальных\n\n"
        "<i>Пример названия:</i> <b>Розыгрыш Iphone от канала PrizeMe</b>",
        parse_mode="HTML"
    )
    await state.set_state(CreateFlow.TITLE)

# ===== Reply-кнопки: перенаправляем на готовые сценарии =====

# "Мои розыгрыши" -> используем cmd_events
@dp.message(F.text == BTN_GIVEAWAYS)
async def on_btn_giveaways(m: Message, state: FSMContext):
    await show_my_giveaways_menu(m)

# "Новый розыгрыш" -> create_giveaway_start
@dp.message(F.text == BTN_CREATE)
async def on_btn_create(m: Message, state: FSMContext):
    await create_giveaway_start(m, state)

# ── Раздел Буст ───────────────────────────────────────────────────────────
@dp.message(Command("boost"))
@dp.message(Command("premium"))   # обратная совместимость
@dp.message(F.text == "Буст")
async def cmd_boost(m: Message):
    """Главный экран раздела Буст"""
    text = (
        "<b>Добро пожаловать в раздел Буст:</b>\n\n"
        "💎 <b>ПРЕМИУМ</b> — подписка для создателей розыгрышей с продвинутым функционалом\n"
        "🔥 <b>PRIME</b> — подписка для участников с расширенным доступом и уникальным механикам\n"
        "🚀 <b>Сервисы</b> — уникальные механики продвижения и вовлечения для создателей розыгрыша\n"
        "❤️ <b>Донат</b> — пожертвования команде сервиса"
    )
    kb = InlineKeyboardBuilder()
    kb.button(text="💎ПРЕМИУМ",  callback_data="boost:premium")
    kb.button(text="🔥PRIME",    callback_data="boost:prime")
    kb.button(text="🚀Сервисы",  callback_data="boost:services")
    kb.button(text="❤️Донат",    callback_data="boost:donate")
    kb.adjust(2, 2)
    await m.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")


@dp.callback_query(F.data == "boost:premium")
async def cb_boost_premium(cq: CallbackQuery):
    """💎ПРЕМИУМ — подписка для создателей"""
    await cq.answer()
    text = (
        "<b>💎ПРЕМИУМ</b> — подписка для создателей розыгрышей с продвинутым функционалом:\n\n"
        "🥇 Увеличенные лимиты числа победителей\n"
        "🤖 Защита от накрутки и ботов через Captcha\n"
        "📊 Продвинутая статистика и выгрузка CSV\n"
        "🎲 Проведение перерозыгрыша\n"
        "🔥 И другие механики\n\n"
        "<i>После оплаты тарифа для активации подписки Вам потребуется перезапустить бота "
        "с помощью команды /start, Вы также будете добавлены в приватный канал (не выходите из него). "
        "Оплата и управление подпиской осуществляется через сервис @tribute, "
        "при оплате вы подтверждаете, что ознакомились с офертой регулярных платежей.</i>"
    )
    kb = InlineKeyboardBuilder()
    kb.button(text="💵 Тарифы", url="https://t.me/tribute/app?startapp=sHOW")
    kb.button(text="📄 Оферта", url="https://prizeme.ru/legal.html?doc=subscription")
    kb.button(text="⬅️ Назад",  callback_data="boost:back")
    kb.adjust(1)
    await cq.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")


@dp.callback_query(F.data == "boost:prime")
async def cb_boost_prime(cq: CallbackQuery):
    """🔥PRIME — подписка для участников"""
    await cq.answer()
    text = (
        "<b>🔥PRIME</b> — подписка для участников с расширенным доступом и уникальным механикам:\n\n"
        "📂 Доступ ко всему каталогу розыгрышей\n"
        "📢 Доступ в приватный канал со всеми розыгрышами\n\n"
        "<i>После оплаты тарифа для активации подписки Вам потребуется перезапустить бота с помощью команды /start, "
        "Вы также будете добавлены в приватный канал (не выходите из него). "
        "Оплата и управление подпиской осуществляется через сервис @tribute, "
        "при оплате вы подтверждаете, что ознакомились с офертой регулярных платежей</i>"
    )
    kb = InlineKeyboardBuilder()
    kb.button(text="💵 Тарифы",  url="https://t.me/tribute/app?startapp=sNMT")
    kb.button(text="📄 Оферта",  url="https://prizeme.ru/legal.html?doc=subscription")
    kb.button(text="⬅️ Назад",   callback_data="boost:back")
    kb.adjust(1)
    await cq.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")


@dp.callback_query(F.data == "boost:services")
async def cb_boost_services(cq: CallbackQuery):
    """🚀Сервисы — механики продвижения"""
    await cq.answer()
    miniapp_url = f"{WEBAPP_BASE_URL}/miniapp/?tgWebAppStartParam=page_services"
    text = (
        "<b>🚀Сервисы</b> — уникальные механики продвижения и вовлечения для создателей розыгрыша:\n\n"
        "🏆 <b>Включение в Топ-розыгрыши:</b> розыгрыш будет опубликован в блоке «Топ-розыгрыши» "
        "на главной странице режима «Участник».\n"
        "📣 <b>Продвижение розыгрыша в боте:</b> розыгрыш будет опубликован в боте и пользователи "
        "получат уведомление с возможностью принять участие.\n"
        "🌟 <b>Задания для участников:</b> Создайте задания для участников розыгрыша, "
        "за выполнение они получат дополнительные билеты.\n\n"
        "<i>Оплатить сервисы можно картой через Robokassa или с помощью Telegram Stars, "
        "для получения подробной информации ознакомьтесь с публичной офертой.</i>"
    )
    kb = InlineKeyboardBuilder()
    kb.button(text="🚀 К сервисам", web_app=WebAppInfo(url=miniapp_url))
    kb.button(text="📄 Оферта",     url="https://prizeme.ru/legal.html?doc=offer")
    kb.button(text="⬅️ Назад",      callback_data="boost:back")
    kb.adjust(1)
    await cq.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")


@dp.callback_query(F.data == "boost:donate")
async def cb_boost_donate(cq: CallbackQuery):
    """❤️Донат"""
    await cq.answer()
    text = (
        "❤️ <b>Спасибо за интерес к сервису</b>\n\n"
        "Лучшая поддержка на свете дарует лучший сервис, проект будет развиваться, "
        "а донат способствовать этому 🙌🏻"
    )
    kb = InlineKeyboardBuilder()
    kb.button(text="❤️ Поддержать", url="https://t.me/tribute/app?startapp=dA1o")
    kb.button(text="⬅️ Назад",      callback_data="boost:back")
    kb.adjust(1)
    await cq.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")


@dp.callback_query(F.data == "boost:back")
async def cb_boost_back(cq: CallbackQuery):
    """⬅️ Назад — возврат на главный экран Буста"""
    await cq.answer()
    text = (
        "<b>Добро пожаловать в раздел Буст:</b>\n\n"
        "💎 <b>ПРЕМИУМ</b> — подписка для создателей розыгрышей с продвинутым функционалом\n"
        "🔥 <b>PRIME</b> — подписка для участников с расширенным доступом и уникальным механикам\n"
        "🚀 <b>Сервисы</b> — уникальные механики продвижения и вовлечения для создателей розыгрыша\n"
        "❤️ <b>Донат</b> — пожертвования команде сервиса"
    )
    kb = InlineKeyboardBuilder()
    kb.button(text="💎ПРЕМИУМ",  callback_data="boost:premium")
    kb.button(text="🔥PRIME",    callback_data="boost:prime")
    kb.button(text="🚀Сервисы",  callback_data="boost:services")
    kb.button(text="❤️Донат",    callback_data="boost:donate")
    kb.adjust(2, 2)
    await cq.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")


# Обработчик для новой кнопки "Мои каналы"
@dp.message(F.text == BTN_CHANNELS)
async def on_btn_my_channels(m: Message):
    rows = await get_user_org_channels(m.from_user.id)
    text = "Ваши каналы / группы:\n\n" + ("" if rows else "Пока пусто.")
    await m.answer(text, reply_markup=kb_my_channels(rows))

# Обработчик для кнопки "Добавить канал" в главном меню
@dp.message(F.text == BTN_ADD_CHANNEL)
async def on_btn_add_channel_main(m: Message, state: FSMContext):
    """Обработчик кнопки 'Добавить канал' в главном меню"""
    logging.info(f"🔍 MAIN MENU: Добавление канала, user={m.from_user.id}")
    
    # Показываем инструкцию
    await m.answer(ADD_CHAT_HELP_HTML, parse_mode="HTML", reply_markup=kb_add_cancel())
    
    # Показываем кнопки выбора чата
    INVISIBLE = "\u2060"
    await m.answer(INVISIBLE, reply_markup=chooser_reply_kb())

# Обработчик для кнопки "Добавить группу" в главном меню
@dp.message(F.text == BTN_ADD_GROUP)
async def on_btn_add_group_main(m: Message, state: FSMContext):
    """Обработчик кнопки 'Добавить группу' в главном меню"""
    logging.info(f"🔍 MAIN MENU: Добавление группы, user={m.from_user.id}")
    
    # Показываем инструкцию
    await m.answer(ADD_CHAT_HELP_HTML, parse_mode="HTML", reply_markup=kb_add_cancel())
    
    # Показываем кнопки выбора чата
    INVISIBLE = "\u2060"
    await m.answer(INVISIBLE, reply_markup=chooser_reply_kb())


#--- Обработчики в создании розыгрыша ---

@dp.message(CreateFlow.TITLE)
async def handle_giveaway_name(m: Message, state: FSMContext):
    name = (m.text or "").strip()
    if not name:
        await m.answer("✏️ Введите название розыгрыша:")
        return
    if len(name) > 50:
        await m.answer("Название не должно превышать 50 символов, попробуйте снова")
        return

    await state.update_data(title=name)

    # Получаем лимит для пользователя
    limit, status = await get_winners_limit(m.from_user.id)
    
    # Динамический текст в зависимости от статуса
    if status == 'premium':
        prompt = f"🥇 Укажите количество победителей в этом розыгрыше от 1 до {limit} (введите только число, не указывая других символов):"
    else:
        prompt = f"🥇 Укажите количество победителей в этом розыгрыше от 1 до {limit} (до 100 только для ПРЕМИУМ, введите только число, не указывая других символов):"
    
    await state.set_state(CreateFlow.WINNERS)
    await m.answer(prompt)


# --- Обработчик ввода количества победителей с учетом статуса пользователя ---

@dp.message(CreateFlow.WINNERS)
async def handle_winners_count(m: Message, state: FSMContext):
    raw = (m.text or "").strip()
    user_id = m.from_user.id
    
    # Получаем лимит для пользователя
    limit, status = await get_winners_limit(user_id)
    
    # Проверяем что введено число
    if not raw.isdigit():
        await m.answer(f"Нужно целое число от 1 до {limit}. Введите ещё раз:")
        return

    winners = int(raw)
    
    # Проверяем лимиты в зависимости от статуса
    if status == 'standard':
        if not (1 <= winners <= WINNERS_LIMIT_STANDARD):
            if winners > WINNERS_LIMIT_STANDARD:
                # Premium-ограничение для standard пользователей
                await m.answer(
                    "<b>💎 Больше 30 победителей могут устанавливать пользователи с подпиской, "
                    "оформить подписку можно в разделе \"Буст\"</b>\n\n"
                    f"Введите новое значение количества победителей от 1 до {WINNERS_LIMIT_STANDARD}:",
                    parse_mode="HTML"
                )
            else:
                await m.answer(f"Число должно быть от 1 до {WINNERS_LIMIT_STANDARD}. Введите ещё раз:")
            return
    else:  # premium
        if not (1 <= winners <= WINNERS_LIMIT_PREMIUM):
            await m.answer(f"Число должно быть от 1 до {WINNERS_LIMIT_PREMIUM}. Введите ещё раз:")
            return

    # Сохраняем количество победителей
    await state.update_data(winners_count=winners)

    # Переходим к описанию
    await state.set_state(CreateFlow.DESC)
    await m.answer(DESCRIPTION_PROMPT, parse_mode="HTML")


# --- Пользователь прислал описание ---
@dp.message(CreateFlow.DESC, F.text)
async def step_desc(m: Message, state: FSMContext):
    raw_text = m.text or ""
    entities = m.entities or []

    # DEBUG (временно)
    logging.info("[DESC] raw_text=%r", raw_text)
    logging.info(
        "[DESC] entities=%s",
        [
            {
                "type": getattr(e, "type", None),
                "offset": getattr(e, "offset", None),
                "length": getattr(e, "length", None),
                "url": getattr(e, "url", None),
                "custom_emoji_id": getattr(e, "custom_emoji_id", None),
            }
            for e in entities
        ],
    )

    # Конвертим в HTML с поддержкой premium-emoji (custom_emoji)
    html_text = message_text_to_html_with_entities(raw_text, entities)

    logging.info("[DESC] html has tg-emoji=%s", "<tg-emoji" in html_text)
    if "<tg-emoji" in html_text:
        logging.info("[DESC] html snippet=%r", html_text[:300])

    if len(html_text) > 2500:
        await m.answer("⚠️ Слишком длинно. Укороти до 2500 символов и пришли ещё раз.")
        return

    await state.update_data(desc=html_text)

    preview = f"<b>Предпросмотр описания:</b>\n\n{html_text}"
    await m.answer(
        preview,
        parse_mode="HTML",
        reply_markup=kb_confirm_description(),
        disable_web_page_preview=True
    )

    await state.set_state(CreateFlow.CONFIRM_DESC)

# если прислали не текст
@dp.message(CreateFlow.DESC)
async def step_desc_wrong(m: Message):
    await m.answer("Пришлите, пожалуйста, текст (до 2500 символов).")

# --- кнопка «Редактировать текст» ---
@dp.callback_query(CreateFlow.CONFIRM_DESC, F.data == "desc:edit")
async def desc_edit(cq: CallbackQuery, state: FSMContext):
    try:
        await cq.message.edit_reply_markup()  # скроем старые кнопки
    except Exception:
        pass
    await state.set_state(CreateFlow.DESC)
    await cq.message.answer(DESCRIPTION_PROMPT, parse_mode="HTML")
    await cq.answer()

# --- кнопка «Продолжить» ---
@dp.callback_query(CreateFlow.CONFIRM_DESC, F.data == "desc:continue")
async def desc_continue(cq: CallbackQuery, state: FSMContext):
    try:
        await cq.message.edit_reply_markup()
    except Exception:
        pass
    # Сразу просим время окончания (перенос шага раньше медиа)
    await state.set_state(CreateFlow.ENDAT)
    await cq.message.answer(format_endtime_prompt(), parse_mode="HTML")
    await cq.answer()

@dp.callback_query(CreateFlow.MEDIA_DECIDE, F.data == "media:yes")
async def media_yes(cq: CallbackQuery, state: FSMContext):
    try:
        await cq.message.edit_reply_markup()
    except Exception:
        pass
    await state.set_state(CreateFlow.MEDIA_UPLOAD)
    await state.update_data(media_top=False)   # <-- медиа изначально «внизу»
    await cq.message.answer(MEDIA_INSTRUCTION, parse_mode="HTML", reply_markup=kb_skip_media())
    await cq.answer()

@dp.callback_query(CreateFlow.MEDIA_DECIDE, F.data == "media:no")
async def media_no(cq: CallbackQuery, state: FSMContext):
    # прячем кнопки «Да/Нет»
    try:
        await cq.message.edit_reply_markup()
    except Exception:
        pass

    # Переходим к предпросмотру БЕЗ медиа (ничего пока не сохраняем в БД)
    await state.set_state(CreateFlow.MEDIA_PREVIEW)
    await state.update_data(media_url=None, media_top=False)

    await render_text_preview_message(cq.message, state)
    await cq.answer()

MAX_VIDEO_BYTES = 5 * 1024 * 1024  # 5 МБ

# --- кнопка «Пропустить» ---

@dp.callback_query(CreateFlow.MEDIA_UPLOAD, F.data == "media:skip")
async def media_skip_callback(cq: CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Пропустить' в состоянии MEDIA_UPLOAD"""
    try:
        await cq.message.edit_reply_markup()  # убираем кнопки
    except Exception:
        pass
    
    # Переходим к предпросмотру БЕЗ медиа
    await state.set_state(CreateFlow.MEDIA_PREVIEW)
    await state.update_data(media_url=None, media_top=False)
    
    # Рендерим предпросмотр без медиа
    await render_text_preview_message(cq.message, state)
    await cq.answer()


@dp.message(CreateFlow.MEDIA_UPLOAD, F.photo)
async def got_photo(m: Message, state: FSMContext):
    logging.info("HANDLER photo: state=MEDIA_UPLOAD, sizes=%d", len(m.photo))
    fid = m.photo[-1].file_id
    await state.update_data(photo=pack_media("photo", fid))
    # пробуем «рамку», иначе — fallback
    await _ensure_link_preview_or_fallback(m, state, "photo", fid, "image.jpg")

@dp.message(CreateFlow.MEDIA_UPLOAD, F.animation)
async def got_animation(m: Message, state: FSMContext):
    logging.info("HANDLER animation: state=MEDIA_UPLOAD")
    anim = m.animation
    if anim.file_size and anim.file_size > MAX_VIDEO_BYTES:
        await m.answer("⚠️ Слишком большой файл (до 5 МБ).", reply_markup=kb_skip_media())
        return
    await state.update_data(photo=pack_media("animation", anim.file_id))
    await _ensure_link_preview_or_fallback(m, state, "animation", anim.file_id, "animation.mp4")

@dp.message(CreateFlow.MEDIA_UPLOAD, F.video)
async def got_video(m: Message, state: FSMContext):
    logging.info("HANDLER video: state=MEDIA_UPLOAD")
    v = m.video
    if v.mime_type and v.mime_type != "video/mp4":
        await m.answer("⚠️ Видео должно быть MP4.", reply_markup=kb_skip_media())
        return
    if v.file_size and v.file_size > MAX_VIDEO_BYTES:
        await m.answer("⚠️ Слишком большой файл (до 5 МБ).", reply_markup=kb_skip_media())
        return
    await state.update_data(photo=pack_media("video", v.file_id))
    await _ensure_link_preview_or_fallback(m, state, "video", v.file_id, "video.mp4")

@dp.message(CreateFlow.ENDAT, F.text)
async def step_endat(m: Message, state: FSMContext):
    """
    Пользователь ввёл время. Валидируем, сохраняем,
    считаем "N дней" и переходим к вопросу про медиа.
    """
    txt = (m.text or "").strip()
    logging.info("[ENDAT] got=%r", txt)
    try:
        # ожидаем "HH:MM DD.MM.YYYY" по МСК (как просили)
        dt_msk = datetime.strptime(txt, "%H:%M %d.%m.%Y")
        # в БД храним UTC
        dt_utc = dt_msk.replace(tzinfo=MSK_TZ).astimezone(timezone.utc)

        # КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: гарантируем aware datetime
        dt_utc = normalize_datetime(dt_utc)

        # дедлайн не раньше чем через 5 минут
        if dt_utc <= datetime.now(timezone.utc) + timedelta(minutes=5):
            await m.answer("Дедлайн должен быть минимум через 5 минут. Введите ещё раз:")
            return

        # сколько дней осталось (по календарным датам МСК)
        now_msk = datetime.now(MSK_TZ).date()
        days_left = (dt_msk.date() - now_msk).days
        if days_left < 0:
            days_left = 0

        # сохраняем
        await state.update_data(
            end_at_utc=dt_utc,
            end_at_msk_str=dt_msk.strftime("%H:%M %d.%m.%Y"),
            days_left=days_left
        )

        # явное текстовое подтверждение для пользователя
        # Точное время до окончания
        dt_msk_aware = dt_msk if dt_msk.tzinfo else MSK_TZ.localize(dt_msk) if hasattr(MSK_TZ, 'localize') else dt_msk.replace(tzinfo=MSK_TZ)
        delta = dt_msk_aware - datetime.now(MSK_TZ)
        total_seconds = int(delta.total_seconds())
        d = total_seconds // 86400
        h = (total_seconds % 86400) // 3600
        mins = (total_seconds % 3600) // 60
        parts = []
        if d: parts.append(f"{d} дн.")
        if h: parts.append(f"{h} ч.")
        if mins or not parts: parts.append(f"{mins} мин.")
        time_left_str = " ".join(parts)

        confirm_text = (
            f"🗓 Время окончания установлено: <b>{dt_msk.strftime('%H:%M %d.%m.%Y')}</b>\n"
            f"Осталось: <b>{time_left_str}</b>"
        )
        await m.answer(confirm_text, parse_mode="HTML")

        # задаём вопрос про медиа (кнопки Да/Нет)
        await state.set_state(CreateFlow.MEDIA_DECIDE)
        await m.answer(MEDIA_QUESTION, reply_markup=kb_yes_no(), parse_mode="HTML")
        logging.info("[ENDAT] saved and asked MEDIA_DECIDE (days_left=%s)", days_left)

    except ValueError:
        await m.answer("Неверный формат. Пример: 13:58 06.10.2025")
    except Exception as e:
        logging.exception("[ENDAT] unexpected error: %s", e)
        await m.answer("Что-то пошло не так при сохранении времени. Попробуйте ещё раз.")

# --- СПЕЦИАЛЬНЫЕ ОБРАБОТЧИКИ МЕДИА ДЛЯ РЕДАКТИРОВАНИЯ ---

@dp.message(EditFlow.EDIT_MEDIA, F.photo)
async def edit_media_photo(m: Message, state: FSMContext):
    """Обработчик фото при редактировании (специальный для EditFlow)"""
    logging.info("EDIT_MEDIA_PHOTO: state=EditFlow.EDIT_MEDIA")
    fid = m.photo[-1].file_id
    await state.update_data(
        new_value=pack_media("photo", fid), 
        display_value="Новое изображение"
    )
    await state.set_state(EditFlow.CONFIRM_EDIT)
    
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Применить изменения", callback_data="edit:apply")
    kb.button(text="✏️ Исправить", callback_data="edit:fix")
    kb.button(text="❌ Отмена", callback_data="edit:cancel")
    kb.adjust(1)
    
    await m.answer(
        "✅ Новое изображение принято",
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )

@dp.message(EditFlow.EDIT_MEDIA, F.animation)
async def edit_media_animation(m: Message, state: FSMContext):
    """Обработчик анимации при редактировании (специальный для EditFlow)"""
    logging.info("EDIT_MEDIA_ANIMATION: state=EditFlow.EDIT_MEDIA")
    anim = m.animation
    if anim.file_size and anim.file_size > MAX_VIDEO_BYTES:
        await m.answer("⚠️ Слишком большой файл (до 5 МБ).", reply_markup=kb_skip_media())
        return
        
    await state.update_data(
        new_value=pack_media("animation", anim.file_id), 
        display_value="Новая GIF-анимация"
    )
    await state.set_state(EditFlow.CONFIRM_EDIT)
    
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Применить изменения", callback_data="edit:apply")
    kb.button(text="✏️ Исправить", callback_data="edit:fix")
    kb.button(text="❌ Отмена", callback_data="edit:cancel")
    kb.adjust(1)
    
    await m.answer(
        "✅ Новая GIF-анимация принята",
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )

@dp.message(EditFlow.EDIT_MEDIA, F.video)
async def edit_media_video(m: Message, state: FSMContext):
    """Обработчик видео при редактировании (специальный для EditFlow)"""
    logging.info("EDIT_MEDIA_VIDEO: state=EditFlow.EDIT_MEDIA")
    v = m.video
    if v.mime_type and v.mime_type != "video/mp4":
        await m.answer("⚠️ Видео должно быть MP4.", reply_markup=kb_skip_media())
        return
    if v.file_size and v.file_size > MAX_VIDEO_BYTES:
        await m.answer("⚠️ Слишком большой файл (до 5 МБ).", reply_markup=kb_skip_media())
        return
        
    await state.update_data(
        new_value=pack_media("video", v.file_id), 
        display_value="Новое видео"
    )
    await state.set_state(EditFlow.CONFIRM_EDIT)
    
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Применить изменения", callback_data="edit:apply")
    kb.button(text="✏️ Исправить", callback_data="edit:fix")
    kb.button(text="❌ Отмена", callback_data="edit:cancel")
    kb.adjust(1)
    
    await m.answer(
        "✅ Новое видео принято",
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )


#--- ОБРАБОТЧИКИ РЕДАКТИРОВАНИЯ НАСТРОЕК РОЗЫГРЫША ---

# Обработчик для редактирования названия
@dp.message(EditFlow.EDIT_TITLE)
async def handle_edit_title(m: Message, state: FSMContext):
    data = await state.get_data()
    gid = data.get("editing_giveaway_id")
    
    new_title = (m.text or "").strip()
    if not new_title:
        await m.answer("✏️ Введите название розыгрыша:")
        return
    if len(new_title) > 50:
        await m.answer("Название не должно превышать 50 символов, попробуйте снова")
        return

    # Сохраняем новое значение
    await state.update_data(new_value=new_title, display_value=new_title)
    await state.set_state(EditFlow.CONFIRM_EDIT)
    
    # Показываем подтверждение
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Применить изменения", callback_data="edit:apply")
    kb.button(text="✏️ Исправить", callback_data="edit:fix")
    kb.button(text="❌ Отмена", callback_data="edit:cancel")
    kb.adjust(1)
    
    await m.answer(
        f"Название розыгрыша изменено на: <b>{new_title}</b>",
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )

# Обработчик для редактирования описания
@dp.message(EditFlow.EDIT_DESC)
async def handle_edit_desc(m: Message, state: FSMContext):
    data = await state.get_data()
    gid = data.get("editing_giveaway_id")
    
    new_desc = m.html_text
    if len(new_desc) > 2500:
        await m.answer("⚠️ Слишком длинно. Укороти до 2500 символов и пришли ещё раз.")
        return

    display_text = safe_html_text(new_desc, max_length=2500)
    
    await state.update_data(new_value=new_desc, display_value=display_text)
    await state.set_state(EditFlow.CONFIRM_EDIT)
    
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Применить изменения", callback_data="edit:apply")
    kb.button(text="✏️ Исправить", callback_data="edit:fix") 
    kb.button(text="❌ Отмена", callback_data="edit:cancel")
    kb.adjust(1)

    await m.answer(
        f"Описание розыгрыша изменено на:\n\n{display_text}",
        reply_markup=kb.as_markup(),
        parse_mode="HTML",
        disable_web_page_preview=True
    )

# Обработчик для редактирования даты окончания
@dp.message(EditFlow.EDIT_ENDAT)
async def handle_edit_endat(m: Message, state: FSMContext):
    data = await state.get_data()
    gid = data.get("editing_giveaway_id")
    
    txt = (m.text or "").strip()
    logging.info("[EDIT_ENDAT] got=%r", txt)
    
    try:
        # ожидаем "HH:MM DD.MM.YYYY" по МСК
        dt_msk = datetime.strptime(txt, "%H:%M %d.%m.%Y")
        # в БД храним UTC
        dt_utc = dt_msk.replace(tzinfo=MSK_TZ).astimezone(timezone.utc)
        dt_utc = normalize_datetime(dt_utc)

        # дедлайн не раньше чем через 5 минут
        if dt_utc <= datetime.now(timezone.utc) + timedelta(minutes=5):
            await m.answer("Дедлайн должен быть минимум через 5 минут. Введите ещё раз:")
            return

        # сколько дней осталось (по календарным датам МСК)
        now_msk = datetime.now(MSK_TZ).date()
        days_left = (dt_msk.date() - now_msk).days
        if days_left < 0:
            days_left = 0

        # сохраняем
        display_value = dt_msk.strftime("%H:%M %d.%m.%Y")
        await state.update_data(
            new_value=dt_utc,
            display_value=display_value,
            end_at_msk_str=display_value,
            days_left=days_left
        )
        await state.set_state(EditFlow.CONFIRM_EDIT)
        
        kb = InlineKeyboardBuilder()
        kb.button(text="✅ Применить изменения", callback_data="edit:apply")
        kb.button(text="✏️ Исправить", callback_data="edit:fix")
        kb.button(text="❌ Отмена", callback_data="edit:cancel")
        kb.adjust(1)
        
        await m.answer(
            f"Дата окончания изменена на: <b>{display_value}</b>",
            reply_markup=kb.as_markup(),
            parse_mode="HTML"
        )

    except ValueError:
        await m.answer("Неверный формат. Пример: 13:58 06.10.2025")
    except Exception as e:
        logging.exception("[EDIT_ENDAT] unexpected error: %s", e)
        await m.answer("Что-то пошло не так при сохранении времени. Попробуйте ещё раз.")

# Обработчик для редактирования количества победителей
@dp.message(EditFlow.EDIT_WINNERS)
async def handle_edit_winners(m: Message, state: FSMContext):
    data = await state.get_data()
    gid = data.get("editing_giveaway_id")
    user_id = m.from_user.id
    
    raw = (m.text or "").strip()
    
    # Получаем лимит для пользователя
    limit, status = await get_winners_limit(user_id)
    
    if not raw.isdigit():
        await m.answer(f"Нужно целое число от 1 до {limit}. Введите ещё раз:")
        return

    winners = int(raw)
    
    # Проверяем лимиты в зависимости от статуса
    if status == 'standard':
        if not (1 <= winners <= WINNERS_LIMIT_STANDARD):
            if winners > WINNERS_LIMIT_STANDARD:
                # Premium-ограничение для standard пользователей
                await m.answer(
                    "<b>💎 Больше 30 победителей могут устанавливать пользователи с подпиской, "
                    "оформить подписку можно в разделе \"Буст\"</b>\n\n"
                    f"Введите новое значение количества победителей от 1 до {WINNERS_LIMIT_STANDARD}:",
                    parse_mode="HTML"
                )
            else:
                await m.answer(f"Число должно быть от 1 до {WINNERS_LIMIT_STANDARD}. Введите ещё раз:")
            return
    else:  # premium
        if not (1 <= winners <= WINNERS_LIMIT_PREMIUM):
            await m.answer(f"Число должно быть от 1 до {WINNERS_LIMIT_PREMIUM}. Введите ещё раз:")
            return

    await state.update_data(new_value=winners, display_value=str(winners))
    await state.set_state(EditFlow.CONFIRM_EDIT)
    
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Применить изменения", callback_data="edit:apply")
    kb.button(text="✏️ Исправить", callback_data="edit:fix")
    kb.button(text="❌ Отмена", callback_data="edit:cancel")
    kb.adjust(1)
    
    await m.answer(
        f"Количество победителей изменено на: <b>{winners}</b>",
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )


# Обработчик для решения о медиа (Да/Нет)
@dp.callback_query(EditFlow.EDIT_MEDIA, F.data == "media:yes")
async def edit_media_yes(cq: CallbackQuery, state: FSMContext):
    """Пользователь хочет добавить медиа"""
    try:
        await cq.message.edit_reply_markup()
    except Exception:
        pass
    
    await cq.message.answer(MEDIA_INSTRUCTION, parse_mode="HTML", reply_markup=kb_skip_media())
    await cq.answer()

@dp.callback_query(EditFlow.EDIT_MEDIA, F.data == "media:no")
async def edit_media_no(cq: CallbackQuery, state: FSMContext):
    """Пользователь не хочет медиа - очищаем существующее"""
    data = await state.get_data()
    gid = data.get("editing_giveaway_id")
    
    # Сохраняем None как новое значение медиа
    await state.update_data(new_value=None, display_value="Медиа удалено")
    await state.set_state(EditFlow.CONFIRM_EDIT)
    
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Применить изменения", callback_data="edit:apply")
    kb.button(text="✏️ Исправить", callback_data="edit:fix")
    kb.button(text="❌ Отмена", callback_data="edit:cancel")
    kb.adjust(1)
    
    await cq.message.answer(
        "Медиафайл удалён из розыгрыша",
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )
    await cq.answer()

# Обработчики для загрузки медиа
@dp.message(EditFlow.EDIT_MEDIA, F.photo)
async def edit_got_photo(m: Message, state: FSMContext):
    """Обработчик фото при редактировании"""
    fid = m.photo[-1].file_id
    await state.update_data(new_value=pack_media("photo", fid), display_value="Новое изображение")
    await state.set_state(EditFlow.CONFIRM_EDIT)
    
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Применить изменения", callback_data="edit:apply")
    kb.button(text="✏️ Исправить", callback_data="edit:fix")
    kb.button(text="❌ Отмена", callback_data="edit:cancel")
    kb.adjust(1)
    
    await m.answer(
        "Новое изображение принято",
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )

@dp.message(EditFlow.EDIT_MEDIA, F.animation)
async def edit_got_animation(m: Message, state: FSMContext):
    """Обработчик анимации при редактировании"""
    anim = m.animation
    if anim.file_size and anim.file_size > MAX_VIDEO_BYTES:
        await m.answer("⚠️ Слишком большой файл (до 5 МБ).", reply_markup=kb_skip_media())
        return
        
    await state.update_data(new_value=pack_media("animation", anim.file_id), display_value="Новая GIF-анимация")
    await state.set_state(EditFlow.CONFIRM_EDIT)
    
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Применить изменения", callback_data="edit:apply")
    kb.button(text="✏️ Исправить", callback_data="edit:fix")
    kb.button(text="❌ Отмена", callback_data="edit:cancel")
    kb.adjust(1)
    
    await m.answer(
        "Новая GIF-анимация принята",
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )

@dp.message(EditFlow.EDIT_MEDIA, F.video)
async def edit_got_video(m: Message, state: FSMContext):
    """Обработчик видео при редактировании"""
    v = m.video
    if v.mime_type and v.mime_type != "video/mp4":
        await m.answer("⚠️ Видео должно быть MP4.", reply_markup=kb_skip_media())
        return
    if v.file_size and v.file_size > MAX_VIDEO_BYTES:
        await m.answer("⚠️ Слишком большой файл (до 5 МБ).", reply_markup=kb_skip_media())
        return
        
    await state.update_data(new_value=pack_media("video", v.file_id), display_value="Новое видео")
    await state.set_state(EditFlow.CONFIRM_EDIT)
    
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Применить изменения", callback_data="edit:apply")
    kb.button(text="✏️ Исправить", callback_data="edit:fix")
    kb.button(text="❌ Отмена", callback_data="edit:cancel")
    kb.adjust(1)
    
    await m.answer(
        "Новое видео принято",
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )

@dp.callback_query(EditFlow.EDIT_MEDIA, F.data == "media:skip")
async def edit_media_skip(cq: CallbackQuery, state: FSMContext):
    """Пропустить изменение медиа - оставить как есть"""
    await state.update_data(new_value="skip", display_value="Медиа не изменено")
    await state.set_state(EditFlow.CONFIRM_EDIT)
    
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Применить изменения", callback_data="edit:apply")
    kb.button(text="✏️ Исправить", callback_data="edit:fix")
    kb.button(text="❌ Отмена", callback_data="edit:cancel")
    kb.adjust(1)
    
    await cq.message.answer(
        "Медиафайл остаётся без изменений",
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )
    await cq.answer()


# --- ОБРАБОТЧИКИ ПОДТВЕРЖДЕНИЯ ИЗМЕНЕНИЙ ---

@dp.callback_query(EditFlow.CONFIRM_EDIT, F.data == "edit:apply")
async def edit_apply(cq: CallbackQuery, state: FSMContext):
    """Применить изменения"""
    data = await state.get_data()
    gid = data.get("editing_giveaway_id")
    setting_type = data.get("setting_type")
    new_value = data.get("new_value")
    return_context = data.get("return_context", "settings")  # по умолчанию черновик
    
    # Сохраняем изменения в БД
    async with session_scope() as s:
        gw = await s.get(Giveaway, gid)
        
        if setting_type == "title":
            gw.internal_title = new_value
        elif setting_type == "desc":
            gw.public_description = new_value
        elif setting_type == "endat":
            # КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: сохраняем время и обновляем планировщик
            gw.end_at_utc = new_value
            
            # Если розыгрыш активен - обновляем планировщик
            if gw.status == GiveawayStatus.ACTIVE:
                try:
                    # Удаляем старый job
                    scheduler.remove_job(f"final_{gid}")
                    
                    # Создаем новый job с новым временем
                    scheduler.add_job(
                        func=finalize_and_draw_job,
                        trigger=DateTrigger(run_date=new_value),
                        args=[gid],
                        id=f"final_{gid}",
                        replace_existing=True,
                    )
                    logging.info(f"🔄 Обновлен планировщик для розыгрыша {gid}, новое время: {new_value}")
                except Exception as e:
                    logging.error(f"❌ Ошибка обновления планировщика для {gid}: {e}")
                    
        elif setting_type == "winners":
            gw.winners_count = new_value
        elif setting_type == "media":
            if new_value == "skip":
                # Пропустить - не изменять медиа
                pass
            elif new_value is None:
                # Удалить медиа
                gw.photo_file_id = None
            else:
                # Новое медиа
                gw.photo_file_id = new_value
        
        s.add(gw)
    
    await state.clear()
    
    # Возврат в соответствующий контекст
    if return_context == "settings":
        # Возврат к карточке черновика
        await show_event_card(cq.message.chat.id, gid)
    else:
        # Возврат к финальному предпросмотру (контекст запуска)
        await _send_launch_preview_message(cq.message, gw)
        await cq.message.answer(
            build_final_check_text(),
            reply_markup=kb_launch_confirm(gid),
            parse_mode="HTML"
        )
    
    await cq.answer("✅ Изменения применены")

# --- Исправить - вернуться к вводу ---
@dp.callback_query(EditFlow.CONFIRM_EDIT, F.data == "edit:fix")
async def edit_fix(cq: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    setting_type = data.get("setting_type")
    
    # Возвращаемся к соответствующему состоянию ввода
    if setting_type == "title":
        await state.set_state(EditFlow.EDIT_TITLE)
        await cq.message.answer("Введите новое название розыгрыша:")
    elif setting_type == "desc":
        await state.set_state(EditFlow.EDIT_DESC)
        await cq.message.answer(DESCRIPTION_PROMPT, parse_mode="HTML")
    elif setting_type == "endat":
        await state.set_state(EditFlow.EDIT_ENDAT)
        await cq.message.answer("Введите новое время окончания в формате ЧЧ:ММ ДД.ММ.ГГГГ (например, 20:00 15.12.2024):")
    elif setting_type == "winners":
        await state.set_state(EditFlow.EDIT_WINNERS)
        
        # Получаем лимит для пользователя
        user_id = cq.from_user.id
        limit, status = await get_winners_limit(user_id)
        
        if status == 'premium':
            prompt = f"Введите новое количество победителей (от 1 до {limit}):"
        else:
            prompt = f"Введите новое количество победителей (от 1 до {limit}):"
        
        await cq.message.answer(prompt)
    elif setting_type == "media":
        await state.set_state(EditFlow.EDIT_MEDIA)
        await cq.message.answer(MEDIA_QUESTION, reply_markup=kb_yes_no(), parse_mode="HTML")
    else:
        # Если тип не распознан, возвращаем в меню настроек
        gid = data.get("editing_giveaway_id")
        return_context = data.get("return_context", "settings")
        await state.clear()
        
        async with session_scope() as s:
            gw = await s.get(Giveaway, gid)
            await cq.message.answer(
                f"Что вы хотите настроить в розыгрыше <b>{gw.internal_title}</b>",
                reply_markup=kb_settings_menu(gid, gw.internal_title, return_context),
                parse_mode="HTML"
            )
    
    await cq.answer()

@dp.callback_query(EditFlow.CONFIRM_EDIT, F.data == "edit:cancel")
async def edit_cancel(cq: CallbackQuery, state: FSMContext):
    """Отмена редактирования"""
    data = await state.get_data()
    gid = data.get("editing_giveaway_id")
    return_context = data.get("return_context")
    
    await state.clear()
    
    # Возвращаемся в меню настроек
    async with session_scope() as s:
        gw = await s.get(Giveaway, gid)
        await cq.message.answer(
            f"Что вы хотите настроить в розыгрыше <b>{gw.internal_title}</b>",
            reply_markup=kb_settings_menu(gid, gw.internal_title, return_context),
            parse_mode="HTML"
        )
    
    await cq.answer()


# ===== Раздел "Мои каналы" =====

def kb_my_channels(rows: list[tuple[int, str]]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    # список каналов/групп столбиком
    for row_id, title in rows:
        kb.button(text=title, callback_data=f"mych:info:{row_id}")
    if rows:
        kb.adjust(1)

    # нижняя линия: две кнопки рядом
    kb.row(
        InlineKeyboardButton(text="Добавить канал",  callback_data="mych:add_channel"),
        InlineKeyboardButton(text="Добавить группу", callback_data="mych:add_group"),
    )
    return kb.as_markup()

@dp.callback_query(F.data == "my_channels")
async def show_my_channels(cq: types.CallbackQuery):
    uid = cq.from_user.id
    rows = await get_user_org_channels(uid)
    text = "Ваши каналы / группы:\n\n" + ("" if rows else "Пока пусто.")
    await cq.message.answer(text, reply_markup=kb_my_channels(rows))
    await cq.answer()

# Хелпер для списка каналов

# Вернуть список организаторских каналов/групп пользователя [(id, title)]
async def get_user_org_channels(user_id: int) -> list[tuple[int, str]]:
    """
    Возвращает список организаторских каналов/групп пользователя [(id, title)]
    УПРОЩЕННАЯ ВЕРСИЯ: убраны сложные JOIN, работает для каналов и групп
    """
    async with Session() as s:
        res = await s.execute(
            stext(
                """
                SELECT id, title 
                FROM organizer_channels 
                WHERE owner_user_id = :user_id 
                AND status = 'ok'
                ORDER BY id DESC
                """
            ),
            {"user_id": user_id}
        )
        rows = res.all()
    return [(r[0], r[1]) for r in rows]

# Показать карточку канала
@dp.callback_query(F.data.startswith("mych:info:"))
async def cb_my_channel_info(cq: CallbackQuery):
    _, _, sid = cq.data.split(":")
    oc_id = int(sid)
    async with session_scope() as s:
        res = await s.execute(
            stext("SELECT title, chat_id, added_at FROM organizer_channels WHERE id=:id"),
            {"id": oc_id}
        )
        row = res.first()
    if not row:
        await cq.answer("Канал/группа не найдены.", show_alert=True); return

    title, chat_id, added_at = row
    kind = "Канал" if str(chat_id).startswith("-100") else "Группа"

    # Приводим дату к МСК (аккуратно обрабатываем разные форматы SQLite)
    dt_msk = None
    if isinstance(added_at, datetime):
        try:
            dt_msk = (added_at.replace(tzinfo=timezone.utc)
                      if added_at.tzinfo is None else added_at).astimezone(MSK_TZ)
        except Exception:
            dt_msk = added_at
    else:
        try:
            parsed = datetime.strptime(str(added_at), "%Y-%m-%d %H:%M:%S")
            dt_msk = parsed.replace(tzinfo=timezone.utc).astimezone(MSK_TZ)
        except Exception:
            dt_msk = None

    dt_text = dt_msk.strftime("%H:%M, %d.%m.%Y") if isinstance(dt_msk, datetime) else str(added_at)

    text = (
        f"<b>Название:</b> {title}\n"
        f"<b>Тип:</b> {kind}\n"
        f"<b>ID:</b> {chat_id}\n"
        f"<b>Дата добавления:</b> {dt_text}\n\n"
        "Удалить канал — канал будет удалён только из списка ваших каналов в боте, "
        "однако во всех активных розыгрышах, к которым канал был прикреплён, он останется."
    )

    kb = InlineKeyboardBuilder()
    delete_text = "Удалить канал" if kind == "Канал" else "Удалить группу"
    kb.button(text=delete_text, callback_data=f"mych:del:{oc_id}")
    kb.button(text="Пропустить", callback_data="mych:dismiss")
    kb.adjust(2)

    await cq.message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    await cq.answer()

# ---- Обработчик "Пропустить" ----
@dp.callback_query(F.data == "mych:dismiss")
async def cb_my_channel_dismiss(cq: CallbackQuery):
    try:
        await cq.message.delete()
    except Exception:
        try:
            await cq.message.edit_reply_markup()
        except Exception:
            pass
    await cq.answer()

# Удаление
@dp.callback_query(F.data.startswith("mych:del:"))
async def cb_my_channel_delete(cq: CallbackQuery):
    _, _, sid = cq.data.split(":")
    oc_id = int(sid)

    async with session_scope() as s:
        res = await s.execute(
            stext("SELECT title, chat_id FROM organizer_channels WHERE id=:id"),
            {"id": oc_id}
        )
        row = res.first()
        if not row:
            await cq.answer("Канал/группа не найдены.", show_alert=True)
            return

        title, chat_id = row
        # Мягкое удаление
        await s.execute(
            stext("UPDATE organizer_channels SET status='deleted' WHERE id=:id"),
            {"id": oc_id}
        )

    # Определяем тип (канал или группа)
    kind = "канал" if str(chat_id).startswith("-100") else "группа"

    # Сообщаем об удалении и даём выбор
    text = f"{kind.capitalize()} <b>{title}</b> был удалён."
    kb = InlineKeyboardBuilder()
    kb.button(text="Восстановить", callback_data=f"mych:restore:{oc_id}:{kind}")
    kb.button(text="Отмена", callback_data="mych:cancel_after_del")
    kb.adjust(2)

    await cq.message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    await cq.answer()

# Восстановление
@dp.callback_query(F.data.startswith("mych:restore:"))
async def cb_my_channel_restore(cq: CallbackQuery):
    try:
        _, _, sid, kind = cq.data.split(":")
        oc_id = int(sid)
    except Exception:
        await cq.answer("Некорректные данные.", show_alert=True)
        return

    async with session_scope() as s:
        await s.execute(
            stext("UPDATE organizer_channels SET status='ok' WHERE id=:id"),
            {"id": oc_id}
        )

    text = f"{kind.capitalize()} был восстановлен."
    kb = InlineKeyboardBuilder()
    # подберём правильную надпись для повтора удаления
    delete_text = "Удалить канал" if kind == "канал" else "Удалить группу"
    kb.button(text=delete_text, callback_data=f"mych:del:{oc_id}")
    kb.button(text="Отмена", callback_data="mych:cancel_after_del")
    kb.adjust(2)

    await cq.message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    await cq.answer()

# Кнопка удаления
@dp.callback_query(F.data == "mych:cancel_after_del")
async def cb_my_channel_cancel_after_del(cq: CallbackQuery):
    # Убираем сообщение с кнопками
    try:
        await cq.message.delete()
    except Exception:
        pass
    # Возвращаем список каналов/групп
    rows = await get_user_org_channels(cq.from_user.id)
    text = "Ваши каналы / группы:\n\n" + ("" if rows else "Пока пусто.")
    await cq.message.answer(text, reply_markup=kb_my_channels(rows))
    await cq.answer()

# Отмена — просто ничего не делаем, чтобы «карточка» схлопнулась диалогом
@dp.callback_query(F.data == "mych:cancel")
async def cb_my_channel_cancel(cq: CallbackQuery):
    await cq.answer("Отменено")

# Подключение новых "Добавить канал/группу" в разделе "Мои каналы"

@dp.callback_query(F.data == "mych:add_channel")
async def cb_mych_add_channel(cq: CallbackQuery, state: FSMContext):
    # 1) Показать инфо-блок + кнопку «Отмена»
    await cq.message.answer(ADD_CHAT_HELP_HTML, parse_mode="HTML", reply_markup=kb_add_cancel())
    # 2) Выставить системное окно выбора (кнопки под строкой поиска)
    INVISIBLE = "\u2060"
    await cq.message.answer(INVISIBLE, reply_markup=chooser_reply_kb())
    await cq.answer()

@dp.callback_query(F.data == "mych:add_group")
async def cb_mych_add_group(cq: CallbackQuery, state: FSMContext):
    await cq.message.answer(ADD_CHAT_HELP_HTML, parse_mode="HTML", reply_markup=kb_add_cancel())
    INVISIBLE = "\u2060"
    await cq.message.answer(INVISIBLE, reply_markup=chooser_reply_kb())
    await cq.answer()

# Обработчик "Отмена" для инфо-блока

@dp.callback_query(F.data == "add:cancel")
async def cb_add_cancel(cq: CallbackQuery):
    # 1) Удаляем ТОЛЬКО инфо-сообщение с текстом
    try:
        await cq.message.delete()
    except Exception:
        pass

    # 2) Возвращаем обычную reply-клавиатуру «внизу» (без нового текста в чате)
    INVISIBLE = "\u2060"
    try:
        await cq.message.answer(INVISIBLE, reply_markup=reply_main_kb())
    except Exception:
        pass

    # Ничего не присылаем заново со «Списком каналов» — он уже выше в чате.
    await cq.answer()

# Клик по inline "Создать розыгрыш" в новом меню

@dp.callback_query(F.data == "create")
async def cb_create_inline(cq: CallbackQuery, state: FSMContext):
    await create_giveaway_start(cq.message, state)
    await cq.answer()


# --- Обработчики для меню "Мои розыгрыши" ---

@dp.callback_query(F.data == "mev:involved")
async def show_involved_giveaways(cq: CallbackQuery):
    """Показать розыгрыши, в которых пользователь участвует - ОБНОВЛЕННАЯ ВЕРСИЯ"""
    uid = cq.from_user.id
    async with session_scope() as s:
        res = await s.execute(stext(
            "SELECT DISTINCT g.id, g.internal_title "
            "FROM entries e "
            "JOIN giveaways g ON g.id = e.giveaway_id "
            "WHERE e.user_id = :u AND g.status = 'active' "
            "ORDER BY g.id DESC"
        ), {"u": uid})
        giveaways = res.all()

    if not giveaways:
        text = "👤 <b>Я - участник</b>\n\nНиже собраны все активные розыгрыши, в которых <b>вы принимаете участие</b> и которые актуальны в данный момент.\n\nПока пусто."
        kb = InlineKeyboardBuilder()
        kb.button(text="⬅️ Назад", callback_data="mev:back_to_participant")
        await cq.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
        await cq.answer()
        return

    text = "👤 <b>Я - участник</b>\n\nНиже собраны все активные розыгрыши, в которых <b>вы принимаете участие</b> и которые актуальны в данный момент."
    kb = InlineKeyboardBuilder()
    
    for gid, title in giveaways:
        kb.button(text=title, callback_data=f"mev:view_involved:{gid}")
    
    kb.button(text="⬅️ Назад", callback_data="mev:back_to_participant")
    kb.adjust(1)
    
    await cq.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    await cq.answer()


@dp.callback_query(F.data == "mev:finished")
async def show_finished_participated_giveaways(cq: CallbackQuery):
    """Показать завершенные розыгрыши, в которых пользователь участвовал - ОБНОВЛЕННАЯ ВЕРСИЯ"""
    uid = cq.from_user.id
    async with session_scope() as s:
        res = await s.execute(stext(
            "SELECT DISTINCT g.id, g.internal_title "
            "FROM entries e "
            "JOIN giveaways g ON g.id = e.giveaway_id "
            "WHERE e.user_id = :u AND g.status = 'finished' "
            "ORDER BY g.id DESC"
        ), {"u": uid})
        giveaways = res.all()

    if not giveaways:
        text = "👤 <b>Я - участник</b>\n\nНиже указаны все <b>завершённые розыгрыши</b>, в которых вы ранее принимали участие.\n\nПока пусто."
        kb = InlineKeyboardBuilder()
        kb.button(text="⬅️ Назад", callback_data="mev:back_to_participant")
        await cq.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
        await cq.answer()
        return

    text = "👤 <b>Я - участник</b>\n\nНиже указаны все <b>завершённые розыгрыши</b>, в которых вы ранее принимали участие."
    kb = InlineKeyboardBuilder()
    
    for gid, title in giveaways:
        kb.button(text=title, callback_data=f"mev:view_finished_part:{gid}")
    
    kb.button(text="⬅️ Назад", callback_data="mev:back_to_participant")
    kb.adjust(1)
    
    await cq.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    await cq.answer()


@dp.callback_query(F.data == "mev:my_active")
async def show_my_active_giveaways(cq: CallbackQuery):
    """Показать активные розыгрыши пользователя - ОБНОВЛЕННАЯ ВЕРСИЯ"""
    uid = cq.from_user.id
    async with session_scope() as s:
        res = await s.execute(stext(
            "SELECT id, internal_title FROM giveaways "
            "WHERE owner_user_id = :u AND status = 'active' "
            "ORDER BY id DESC"
        ), {"u": uid})
        giveaways = res.all()

    if not giveaways:
        text = "👑 <b>Я - создатель</b>\n\nНиже указаны все <b>активные розыгрыши</b>, которые вы создали и уже запустили.\n\n\nВыберите из списка ниже розыгрыш для управления им.\n\nПока пусто."
        kb = InlineKeyboardBuilder()
        kb.button(text="⬅️ Назад", callback_data="mev:back_to_creator")
        
        try:
            await cq.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
        except Exception:
            try:
                await cq.message.edit_reply_markup(reply_markup=kb.as_markup())
            except Exception:
                pass
                
        await cq.answer()
        return

    text = "👑 <b>Я - создатель</b>\n\nНиже указаны все <b>активные розыгрыши</b>, которые вы создали и уже запустили.\n\n\nВыберите из списка ниже розыгрыш для управления им."
    kb = InlineKeyboardBuilder()
    
    for gid, title in giveaways:
        kb.button(text=title, callback_data=f"mev:view_my_active:{gid}")
    
    kb.button(text="⬅️ Назад", callback_data="mev:back_to_creator")
    kb.adjust(1)
    
    try:
        await cq.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    except Exception:
        try:
            await cq.message.edit_reply_markup(reply_markup=kb.as_markup())
        except Exception:
            pass
    
    await cq.answer()

@dp.callback_query(F.data == "mev:my_drafts")
async def show_my_drafts(cq: CallbackQuery):
    """Показать черновики пользователя - ОБНОВЛЕННАЯ ВЕРСИЯ"""
    uid = cq.from_user.id
    async with session_scope() as s:
        res = await s.execute(stext(
            "SELECT id, internal_title FROM giveaways "
            "WHERE owner_user_id = :u AND status = 'draft' "
            "ORDER BY id DESC"
        ), {"u": uid})
        giveaways = res.all()

    if not giveaways:
        text = "👑 <b>Я - создатель</b>\n\nНиже указаны все розыгрыши, которые вы создали, но <b>не запустили</b>.\n\n\nВыберите из списка ниже розыгрыш для управления им.\n\nПока пусто."
        kb = InlineKeyboardBuilder()
        kb.button(text="⬅️ Назад", callback_data="mev:back_to_creator")
        
        try:
            await cq.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
        except Exception:
            try:
                await cq.message.edit_reply_markup(reply_markup=kb.as_markup())
            except Exception:
                pass
                
        await cq.answer()
        return

    text = "👑 <b>Я - создатель</b>\n\nНиже указаны все розыгрыши, которые вы создали, но <b>не запустили</b>.\n\n\nВыберите из списка ниже розыгрыш для управления им."
    kb = InlineKeyboardBuilder()
    
    for gid, title in giveaways:
        kb.button(text=title, callback_data=f"mev:view_my_draft:{gid}")
    
    kb.button(text="⬅️ Назад", callback_data="mev:back_to_creator")
    kb.adjust(1)
    
    try:
        await cq.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    except Exception:
        try:
            await cq.message.edit_reply_markup(reply_markup=kb.as_markup())
        except Exception:
            pass
    
    await cq.answer()


@dp.callback_query(F.data == "mev:my_finished")
async def show_my_finished_giveaways(cq: CallbackQuery):
    """Показать завершенные розыгрыши пользователя - ОБНОВЛЕННАЯ ВЕРСИЯ"""
    uid = cq.from_user.id
    async with session_scope() as s:
        res = await s.execute(stext(
            "SELECT id, internal_title FROM giveaways "
            "WHERE owner_user_id = :u AND status = 'finished' "
            "ORDER BY id DESC"
        ), {"u": uid})
        giveaways = res.all()

    if not giveaways:
        text = "👑 <b>Я - создатель</b>\n\nНиже указаны все <b>завершённые розыгрыши</b>, которые вы ранее запускали.\n\nПока пусто."
        kb = InlineKeyboardBuilder()
        kb.button(text="⬅️ Назад", callback_data="mev:back_to_creator")
        await cq.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
        await cq.answer()
        return

    text = "👑 <b>Я - создатель</b>\n\nНиже указаны все <b>завершённые розыгрыши</b>, которые вы ранее запускали."
    kb = InlineKeyboardBuilder()
    
    for gid, title in giveaways:
        kb.button(text=title, callback_data=f"mev:view_my_finished:{gid}")
    
    kb.button(text="⬅️ Назад", callback_data="mev:back_to_creator")
    kb.adjust(1)
    
    await cq.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    await cq.answer()


# --- Обработчики для просмотра конкретных розыгрышей ---

@dp.callback_query(F.data.startswith("mev:view_involved:"))
async def view_involved_giveaway(cq: CallbackQuery):
    """Просмотр АКТИВНОГО розыгрыша, в котором участвует пользователь"""
    gid = int(cq.data.split(":")[2])
    
    # Получаем данные розыгрыша
    async with session_scope() as s:
        gw = await s.get(Giveaway, gid)
        if not gw or gw.status != GiveawayStatus.ACTIVE:
            await cq.answer("Розыгрыш не найден или не активен.", show_alert=True)
            return
    
    # Показываем пост розыгрыша с кнопкой "Участвовать" (как в канале)
    await show_participant_giveaway_post(cq.message, gid, "active")
    await cq.answer()

@dp.callback_query(F.data.startswith("mev:view_finished_part:"))
async def view_finished_participated_giveaway(cq: CallbackQuery):
    """Просмотр ЗАВЕРШЕННОГО розыгрыша, в котором участвовал пользователь"""
    gid = int(cq.data.split(":")[2])
    
    # Получаем данные розыгрыша
    async with session_scope() as s:
        gw = await s.get(Giveaway, gid)
        if not gw or gw.status != GiveawayStatus.FINISHED:
            await cq.answer("Розыгрыш не найден или не завершен.", show_alert=True)
            return
    
    # Показываем пост розыгрыша с кнопкой "Результаты" (завершенная версия)
    await show_participant_giveaway_post(cq.message, gid, "finished")
    await cq.answer()

# --- ОБРАБОТЧИКИ ДЛЯ БЛОКА "Я - СОЗДАТЕЛЬ" ---
@dp.callback_query(F.data.startswith("mev:view_my_active:"))
async def view_my_active_giveaway(cq: CallbackQuery):
    """Просмотр активного розыгрыша организатора - ИСПРАВЛЕННАЯ ВЕРСИЯ"""
    gid = int(cq.data.split(":")[2])
    
    await show_event_card(cq.from_user.id, gid)
    await cq.answer()

@dp.callback_query(F.data.startswith("mev:view_my_draft:"))
async def view_my_draft_giveaway(cq: CallbackQuery):
    """Просмотр черновика организатора - ИСПРАВЛЕННАЯ ВЕРСИЯ"""
    gid = int(cq.data.split(":")[2])
    
    await show_event_card(cq.from_user.id, gid)
    await cq.answer()

@dp.callback_query(F.data.startswith("mev:view_my_finished:"))
async def view_my_finished_giveaway(cq: CallbackQuery):
    """Просмотр завершенного розыгрыша организатора - ИСПРАВЛЕННАЯ ВЕРСИЯ"""
    gid = int(cq.data.split(":")[2])
    
    await show_event_card(cq.from_user.id, gid)
    await cq.answer()


# --- Обработчик с кнопками в меню ---

@dp.message(Command("giveaways"))
async def cmd_events(m: Message):
    """Команда /giveaways - меню с разделением по ролям"""
    await show_my_giveaways_menu(m)

# --- Показывает карточку розыгрыша с УСИЛЕННЫМ link-preview если есть медиа ---
async def show_event_card(chat_id:int, giveaway_id:int):
    async with session_scope() as s:
        gw = await s.get(Giveaway, giveaway_id)

    cap = (f"<b>{gw.internal_title}</b>\n\n{gw.public_description}\n\n"
           f"Статус: {gw.status}\nПобедителей: {gw.winners_count}\n"
           f"Дата окончания: {gw.end_at_utc.strftime('%H:%M %d.%m.%Y MSK')}")

    kind, fid = unpack_media(gw.photo_file_id)

    # УСИЛЕННЫЙ LINK-PREVIEW для карточки
    if fid:
        try:
            # Пытаемся использовать link-preview для единообразия
            if kind == "photo":
                suggested = "image.jpg"
            elif kind == "animation":
                suggested = "animation.mp4" 
            elif kind == "video":
                suggested = "video.mp4"
            else:
                suggested = "file.bin"

            key, s3_url = await file_id_to_public_url_via_s3(bot, fid, suggested)
            preview_url = _make_preview_url(key, gw.internal_title or "", gw.public_description or "")

            # УСИЛЕННЫЙ LINK-PREVIEW
            hidden_link = f'<a href="{preview_url}"> </a>'
            full_text = cap + "\n\n" + hidden_link

            lp = LinkPreviewOptions(
                is_disabled=False,
                prefer_large_media=True,
                prefer_small_media=False,
                show_above_text=False,
                url=preview_url  # ЯВНО указываем URL
            )

            # ЕСЛИ ЕСТЬ МЕДИА - НИКОГДА НЕ ОТКЛЮЧАЕМ ПРЕВЬЮ!
            # Используем новую клавиатуру для черновиков
            if gw.status == GiveawayStatus.DRAFT:
                reply_markup = kb_draft_actions(giveaway_id)
            else:
                # Передаем chat_id как user_id для проверки статуса
                reply_markup = kb_event_actions(giveaway_id, gw.status, chat_id)
                
            await bot.send_message(
                chat_id, 
                full_text, 
                link_preview_options=lp,
                parse_mode="HTML",
                reply_markup=reply_markup
            )
            return
            
        except Exception as e:
            print(f"⚠️ Link-preview не сработал для карточки: {e}")
            # Fallback к обычному способу
            pass

    # Fallback: оригинальный код (нативная отправка медиа)
    # Используем новую клавиатуру для черновиков
    if gw.status == GiveawayStatus.DRAFT:
        reply_markup = kb_draft_actions(giveaway_id)
    else:
        # Передаем chat_id как user_id для проверки статуса
        reply_markup = kb_event_actions(giveaway_id, gw.status, chat_id)
    
    if kind == "photo" and fid:
        await bot.send_photo(chat_id, fid, caption=cap, reply_markup=reply_markup)
    elif kind == "animation" and fid:
        await bot.send_animation(chat_id, fid, caption=cap, reply_markup=reply_markup)
    elif kind == "video" and fid:
        await bot.send_video(chat_id, fid, caption=cap, reply_markup=reply_markup)
    else:
        await bot.send_message(chat_id, cap, reply_markup=reply_markup)

# --- ОБРАБОТЧИКИ ДЛЯ ЧЕРНОВИКОВ ---

@dp.callback_query(F.data.startswith("ev:add_channels:"))
async def ev_add_channels(cq: CallbackQuery):
    """Обработчик кнопки 'Добавить канал / группу' в черновике"""
    gid = int(cq.data.split(":")[2])
    
    # Показываем стандартный экран подключения каналов
    await cb_connect_channels(cq)
    await cq.answer()

@dp.callback_query(F.data.startswith("ev:settings:"))
async def ev_settings(cq: CallbackQuery):
    """Обработчик кнопки 'Настройки розыгрыша' в черновике"""
    gid = int(cq.data.split(":")[2])
    
    # Показываем меню настроек с контекстом "settings" (черновик)
    async with session_scope() as s:
        gw = await s.get(Giveaway, gid)
        if not gw:
            await cq.answer("Розыгрыш не найден.", show_alert=True)
            return
    
    text = f"Что вы хотите настроить в розыгрыше <b>{gw.internal_title}</b>"
    await cq.message.answer(text, reply_markup=kb_settings_menu(gid, gw.internal_title, "settings"), parse_mode="HTML")
    await cq.answer()

@dp.callback_query(F.data.startswith("ev:delete_draft:"))
async def ev_delete_draft(cq: CallbackQuery):
    """Обработчик кнопки 'Удалить черновик' - показывает диалог подтверждения"""
    gid = int(cq.data.split(":")[2])
    
    # Получаем название розыгрыша для сообщения
    async with session_scope() as s:
        gw = await s.get(Giveaway, gid)
        if not gw or gw.status != GiveawayStatus.DRAFT:
            await cq.answer("Можно удалять только черновики.", show_alert=True)
            return
    
    # Показываем диалог подтверждения удаления
    text = f"Вы действительно хотите удалить черновик с розыгрышем <b>{gw.internal_title}</b>?"
    
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Да", callback_data=f"ev:confirm_delete:{gid}")
    kb.button(text="❌ Нет", callback_data=f"ev:cancel_delete:{gid}")
    kb.adjust(2)
    
    await cq.message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    await cq.answer()

@dp.callback_query(F.data.startswith("ev:confirm_delete:"))
async def ev_confirm_delete(cq: CallbackQuery):
    """Подтверждение удаления черновика"""
    gid = int(cq.data.split(":")[2])
    
    async with session_scope() as s:
        gw = await s.get(Giveaway, gid)
        if not gw or gw.status != GiveawayStatus.DRAFT:
            await cq.answer("Можно удалять только черновики.", show_alert=True)
            return
        
        title = gw.internal_title
        
        # Удаляем розыгрыш и связанные данные
        await s.execute(stext("DELETE FROM giveaways WHERE id=:gid"), {"gid": gid})
        await s.execute(stext("DELETE FROM giveaway_channels WHERE giveaway_id=:gid"), {"gid": gid})
    
    # Показываем сообщение об успешном удалении
    text = f"Черновик розыгрыша <b>{title}</b> успешно удалён"
    
    kb = InlineKeyboardBuilder()
    kb.button(text="↩️ Вернуться к черновикам", callback_data="mev:my_drafts")
    kb.adjust(1)
    
    # Удаляем сообщение с диалогом подтверждения
    try:
        await cq.message.delete()
    except:
        pass
    
    await cq.message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    await cq.answer()

# --- ОБРАБОТЧИКИ ДЛЯ СТРУКТУРИЗАЦИИ МЕНЮ ---

@dp.callback_query(F.data == "mev:as_participant")
async def show_as_participant(cq: CallbackQuery):
    """Показывает меню 'Я - участник' - ОБНОВЛЕННАЯ ВЕРСИЯ"""
    uid = cq.from_user.id
    
    # Получаем актуальные данные для счетчиков
    async with session_scope() as s:
        # в которых участвую — уникальные активные розыгрыши, где у пользователя есть entries
        res = await s.execute(stext(
            "SELECT COUNT(DISTINCT g.id) "
            "FROM entries e JOIN giveaways g ON g.id=e.giveaway_id "
            "WHERE e.user_id=:u AND g.status='active'"
        ), {"u": uid})
        count_involved = res.scalar_one() or 0

        # завершённые вообще (по системе) где пользователь участвовал
        res = await s.execute(stext(
            "SELECT COUNT(DISTINCT g.id) "
            "FROM entries e JOIN giveaways g ON g.id=e.giveaway_id "
            "WHERE e.user_id=:u AND g.status='finished'"
        ), {"u": uid})
        count_finished = res.scalar_one() or 0

    text = "👤 <b>Я - участник</b>\n\nРозыгрыши, где вы принимаете участие:"
    
    await cq.message.edit_text(
        text,
        reply_markup=kb_participant_menu(count_involved, count_finished),
        parse_mode="HTML"
    )
    await cq.answer()

@dp.callback_query(F.data == "mev:as_creator")
async def show_as_creator(cq: CallbackQuery):
    """Показывает меню 'Я - создатель' - ОБНОВЛЕННАЯ ВЕРСИЯ"""
    uid = cq.from_user.id
    
    # Получаем актуальные данные для счетчиков
    async with session_scope() as s:
        # мои активные, черновики и завершённые
        res = await s.execute(stext(
            "SELECT "
            "SUM(CASE WHEN status='active' THEN 1 ELSE 0 END), "
            "SUM(CASE WHEN status='draft' THEN 1 ELSE 0 END), "
            "SUM(CASE WHEN status='finished' THEN 1 ELSE 0 END) "
            "FROM giveaways WHERE owner_user_id=:u"
        ), {"u": uid})
        row = res.first()
        my_active = int(row[0] or 0)
        my_draft = int(row[1] or 0)
        my_finished = int(row[2] or 0)

    text = "👑 <b>Я - создатель</b>\n\nРозыгрыши, которые вы создали:"
    
    await cq.message.edit_text(
        text,
        reply_markup=kb_creator_menu(my_active, my_draft, my_finished),
        parse_mode="HTML"
    )
    await cq.answer()

@dp.callback_query(F.data == "mev:back_to_main")
async def back_to_main_menu(cq: CallbackQuery):
    """Возврат в главное меню 'Мои розыгрыши' - ОБНОВЛЕННАЯ ВЕРСИЯ"""
    text = "🎯 <b>Мои розыгрыши</b>\n\nВыберите роль для просмотра розыгрышей:"

    await cq.message.edit_text(
        text, 
        reply_markup=kb_my_events_menu(),
        parse_mode="HTML"
    )
    await cq.answer()

# --- ДРУГОЕ ---

@dp.callback_query(F.data.startswith("ev:cancel_delete:"))
async def ev_cancel_delete(cq: CallbackQuery):
    """Отмена удаления черновика"""
    # Просто удаляем сообщение с диалогом подтверждения
    try:
        await cq.message.delete()
    except:
        pass
    await cq.answer("Удаление отменено")

@dp.callback_query(F.data == "draft:back")
async def draft_back(cq: CallbackQuery):
    """Обработчик кнопки 'Назад' в черновике - просто удаляет сообщение"""
    try:
        await cq.message.delete()
    except Exception:
        # Если не удалось удалить, просто убираем кнопки
        try:
            await cq.message.edit_reply_markup()
        except Exception:
            pass
    await cq.answer()

# === ОБРАБОТЧИК ЗАПУСКА РОЗЫГРЫША ===
@dp.callback_query(F.data.startswith("ev:launch:"))
async def event_launch(cq: CallbackQuery):
    """Запуск розыгрыша - ОТДЕЛЬНЫЙ ОБРАБОТЧИК"""
    gid = int(cq.data.split(":")[2])
    
    gw = await _launch_and_publish(gid, cq.message)
    if not gw:
        await cq.answer("Розыгрыш не найден.", show_alert=True)
        return
        
    await cq.message.answer("Розыгрыш запущен.")
    await show_event_card(cq.message.chat.id, gid)
    await cq.answer()

# === ОБРАБОТЧИК СТАТИСТИКИ ===
@dp.callback_query(F.data.startswith("ev:status:"))
async def event_status(cq: CallbackQuery):
    """Статистика розыгрыша - ПОКАЗЫВАЕТСЯ КАК НОВОЕ СООБЩЕНИЕ"""
    gid = int(cq.data.split(":")[2])
    
    async with session_scope() as s:
        gw = await s.get(Giveaway, gid)
        if not gw:
            await cq.answer("Розыгрыш не найден.", show_alert=True)
            return
        
        # Определяем контекст и показываем статистику как новое сообщение
        if gw.status == GiveawayStatus.ACTIVE:
            # Передаем user_id явно
            await show_active_stats(cq.message, gid, cq.from_user.id)
        elif gw.status in (GiveawayStatus.FINISHED, GiveawayStatus.CANCELLED):
            # Передаем user_id явно
            await show_finished_stats(cq.message, gid, cq.from_user.id)
        else:
            await cq.answer("Статистика недоступна для этого статуса.", show_alert=True)
    
    await cq.answer()


# === Полноценный экспорт статистики в CSV файл ===

@dp.callback_query(F.data.startswith("stats:csv:"))
async def cb_csv_export(cq: CallbackQuery):
    """
    Выгрузка статистики в CSV файл - ТОЛЬКО для premium пользователей
    """
    # 🔥 ВСТРОЕННАЯ ПРОВЕРКА ПРЕМИУМ СТАТУСА
    user_id = cq.from_user.id
    status = await get_user_status(user_id)
    
    if status == 'standard':
        await cq.answer(
            "💎 Оформите подписку ПРЕМИУМ для доступа к функционалу",
            show_alert=True
        )
        return
    
    # 🔍 ДИАГНОСТИКА
    giveaway_id = int(cq.data.split(":")[2])
    logging.info(f"🔍 [CSV_EXPORT] Premium доступ подтвержден: user_id={user_id}, giveaway_id={giveaway_id}")
    
    try:
        # 1. Извлекаем ID розыгрыша из callback_data
        giveaway_id = int(cq.data.split(":")[2])
        user_id = cq.from_user.id
        
        # 2. Проверяем, что пользователь - организатор розыгрыша
        if not await is_giveaway_organizer(user_id, giveaway_id):
            await cq.answer("❌ Только организатор может выгрузить статистику", show_alert=True)
            return
        
        # 3. Проверяем наличие участников
        participant_count = await get_participant_count(giveaway_id)
        if participant_count == 0:
            await cq.answer("📭 В этом розыгрыше еще нет участников", show_alert=True)
            return
        
        # 4. Уведомляем пользователя о начале генерации
        await cq.answer(f"📊 Генерирую файл... Участников: {participant_count}", show_alert=False)
        
        # 5. Для больших розыгрышей отправляем отдельное сообщение
        if participant_count > 1000:
            progress_msg = await cq.message.answer(
                f"⏳ Генерация CSV файла...\n"
                f"Участников: {participant_count}\n"
                f"Это займет несколько секунд..."
            )
        
        # 6. Генерируем CSV файл
        csv_file = await generate_csv_in_memory(giveaway_id)
        
        # 7. Получаем название розыгрыша для заголовка
        giveaway_title = await get_giveaway_title(giveaway_id)
        
        # 8. Отправляем файл пользователю
        await cq.message.reply_document(
            csv_file,
            caption=(
                f"📊 <b>Статистика розыгрыша</b>\n"
                f"<b>Название:</b> {giveaway_title}\n"
                f"<b>ID розыгрыша:</b> {giveaway_id}\n"
                f"<b>Участников:</b> {participant_count}\n\n"
                f"<i>Файл в формате CSV. Откройте в Excel или Google Sheets.</i>"
            ),
            parse_mode="HTML"
        )
        
        # 9. Удаляем сообщение о прогрессе (если было)
        if participant_count > 1000:
            try:
                await progress_msg.delete()
            except Exception:
                pass
        
        # 10. Логируем успешную выгрузку
        logging.info(f"✅ CSV экспортирован: giveaway_id={giveaway_id}, user_id={user_id}, участников={participant_count}")
        
    except ValueError as e:
        await cq.answer(f"❌ Ошибка: {str(e)}", show_alert=True)
    except Exception as e:
        logging.error(f"❌ Ошибка экспорта CSV: {e}", exc_info=True)
        await cq.answer(
            "❌ Произошла ошибка при генерации файла\n"
            "Попробуйте позже или обратитесь в поддержку",
            show_alert=True
        )


# ===== Карточка-превью медиа =====

@dp.callback_query(CreateFlow.MEDIA_PREVIEW, F.data == "preview:move:up")
async def preview_move_up(cq: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get("media_url"):
        await cq.answer("Перемещение доступно только в режиме предпросмотра с рамкой.", show_alert=True)
        return
    
    # Сохраняем в state
    await state.update_data(media_top=True)
    
    # Если редактируем существующий розыгрыш, сохраняем в БД
    editing_gid = data.get("editing_giveaway_id")
    if editing_gid:
        async with session_scope() as s:
            gw = await s.get(Giveaway, editing_gid)
            if gw:
                gw.media_position = "top"
                s.add(gw)
    
    await render_link_preview_message(cq.message, state, reedit=True)
    await cq.answer()

@dp.callback_query(CreateFlow.MEDIA_PREVIEW, F.data == "preview:move:down")
async def preview_move_down(cq: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get("media_url"):
        await cq.answer("Перемещение доступно только в режиме предпросмотра с рамкой.", show_alert=True)
        return
    
    # Сохраняем в state
    await state.update_data(media_top=False)
    
    # Если редактируем существующий розыгрыш, сохраняем в БД
    editing_gid = data.get("editing_giveaway_id")
    if editing_gid:
        async with session_scope() as s:
            gw = await s.get(Giveaway, editing_gid)
            if gw:
                gw.media_position = "bottom"
                s.add(gw)
    
    await render_link_preview_message(cq.message, state, reedit=True)
    await cq.answer()

@dp.callback_query(CreateFlow.MEDIA_PREVIEW, F.data == "preview:change")
async def preview_change_media(cq: CallbackQuery, state: FSMContext):
    await state.set_state(CreateFlow.MEDIA_UPLOAD)
    await cq.message.answer(MEDIA_INSTRUCTION, parse_mode="HTML", reply_markup=kb_skip_media())
    await cq.answer()

#--- Обработчик БЕЗ медиа ---
@dp.callback_query(CreateFlow.MEDIA_PREVIEW, F.data == "preview:add_media")
async def preview_add_media(cq: CallbackQuery, state: FSMContext):
    """
    Обработчик кнопки «Добавить изображение/gif/видео»
    из предпросмотра без медиа.
    Возвращает пользователя на шаг загрузки медиафайла.
    """
    # Переводим состояние обратно на шаг загрузки медиа
    await state.set_state(CreateFlow.MEDIA_UPLOAD)

    # Отправляем пользователю инструкцию по загрузке
    await cq.message.answer(
        MEDIA_INSTRUCTION,
        parse_mode="HTML",
        reply_markup=kb_skip_media()  # клавиатура с кнопками «Пропустить» / «Отмена»
    )

    await cq.answer()

#--- Обработчик С мелиа ---
@dp.callback_query(CreateFlow.MEDIA_PREVIEW, F.data == "preview:continue")
async def preview_continue(cq: CallbackQuery, state: FSMContext):
    """
    Сохраняем черновик и сразу показываем экран-приглашение
    с кнопкой «Добавить канал/группу», как в референсе.
    Также обязательно вызываем cq.answer(), чтобы погасить «вертушку».
    """
    # на всякий случай спрячем старые кнопки под предпросмотром
    try:
        await cq.message.edit_reply_markup()
    except Exception:
        pass

    data = await state.get_data()

    owner_id = data.get("owner")
    title    = (data.get("title") or "").strip()
    desc     = (data.get("desc")  or "").strip()
    desc_entities = data.get("desc_entities", [])
    winners  = int(data.get("winners_count") or 1)
    end_at   = data.get("end_at_utc")
    photo_id = data.get("photo")  # pack_media(..) | None

    if not (owner_id and title and end_at):
        await cq.message.answer("Похоже, шаги заполнены не полностью. Наберите /create и начните заново.")
        await state.clear()
        await cq.answer()
        return

    # 1) создаём черновик и получаем его id
    async with session_scope() as s:
        # Получаем позицию медиа из state
        media_top = data.get("media_top", False)
        media_position = "top" if media_top else "bottom"

        gw = Giveaway(
            owner_user_id=owner_id,
            internal_title=title,
            public_description=desc,
            photo_file_id=photo_id,
            media_position=media_position,
            end_at_utc=end_at,
            winners_count=winners,
            status=GiveawayStatus.DRAFT
        )
        s.add(gw)
        await s.flush()
        new_id = gw.id

    # 2) чистим FSM
    await state.clear()

    # 3) отправляем экран-приглашение + кнопку «Добавить канал/группу»
    await cq.message.answer(
        CONNECT_INVITE_TEXT,
        reply_markup=build_connect_invite_kb(new_id)
    )

    # 4) обязательно гасим «вертушку» на кнопке
    await cq.answer()

# ===== Экран подключения каналов (по кнопке "Добавить канал/группу") =====

@dp.callback_query(F.data.startswith("raffle:connect_channels:"))
async def cb_connect_channels(cq: CallbackQuery):
    # data: raffle:connect_channels:<event_id>
    _, _, sid = cq.data.split(":")
    event_id = int(sid)

    # достаём информацию о розыгрыше, все каналы владельца и уже прикреплённые к этому розыгрышу
    async with session_scope() as s:
        gw = await s.get(Giveaway, event_id)
        if not gw:
            await cq.answer("Розыгрыш не найден.", show_alert=True)
            return

        # все каналы/группы, подключённые к боту у владельца
        res = await s.execute(
            stext("SELECT id, title FROM organizer_channels WHERE owner_user_id=:u AND status='ok'"),
            {"u": gw.owner_user_id}
        )
        channels = [(r[0], r[1]) for r in res.fetchall()]

        # набор id каналов, уже прикреплённых к этому розыгрышу
        res = await s.execute(
            stext("SELECT channel_id FROM giveaway_channels WHERE giveaway_id=:g"),
            {"g": event_id}
        )
        attached_ids = {r[0] for r in res.fetchall()}

        # список для текстового блока (с username → делаем ссылку)
        res = await s.execute(
            stext("""
                SELECT gc.title, oc.username, gc.chat_id
                FROM giveaway_channels gc
                LEFT JOIN organizer_channels oc ON oc.id = gc.channel_id
                WHERE gc.giveaway_id = :g
                ORDER BY gc.id
            """),
            {"g": event_id}
        )
        attached_list = [(r[0], r[1], r[2]) for r in res.fetchall()]

    # Убедимся, что attached_list не содержит пустых значений
    clean_attached_list = []
    if attached_list:
        for item in attached_list:
            # item = (title, username, chat_id)
            if item[0] and item[0].strip():  # Проверяем, что title не пустой
                clean_attached_list.append(item)
    
    if not clean_attached_list:
        # Создаем текст без списка подключенных каналов
        text_block = (
            f"🔗 Подключение канала к розыгрышу \"{gw.internal_title}\"\n\n"
            "Подключить канал к розыгрышу сможет только администратор, "
            "который обладает достаточным уровнем прав в прикреплённом канале\n\n"
            "<b>Подключённые каналы:</b>\n"
            "— пока нет"
        )
    else:
        text_block = build_connect_channels_text(gw.internal_title, clean_attached_list)
    
    # Используем clean_attached_list для клавиатуры тоже
    kb = build_channels_menu_kb(event_id, channels, attached_ids)
    
    try:
        await cq.message.edit_text(text_block, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await cq.message.answer(text_block, reply_markup=kb, parse_mode="HTML")
    await cq.answer()

@dp.callback_query(F.data.startswith("raffle:attach:"))
async def cb_attach_channel(cq: CallbackQuery):
    # data: raffle:attach:<event_id>:<organizer_channel_id>
    try:
        _, _, sid, scid = cq.data.split(":")
        event_id = int(sid)
        org_id = int(scid)
    except Exception:
        await cq.answer("Некорректные данные.", show_alert=True)
        return

    # переключаем состояние: если уже прикреплён — снимаем; иначе прикрепляем
    async with session_scope() as s:
        gw = await s.get(Giveaway, event_id)
        if not gw:
            await cq.answer("Розыгрыш не найден.", show_alert=True)
            return

        # берём данные выбранного канала из organizer_channels
        rec = await s.execute(
            stext("SELECT id, chat_id, title FROM organizer_channels WHERE id=:id AND status='ok'"),
            {"id": org_id}
        )
        row = rec.first()
        if not row:
            await cq.answer("Канал/группа не найдены.", show_alert=True)
            return

        oc_id, chat_id, title = row

        # проверим — уже прикреплён?
        exists = await s.execute(
            stext("SELECT id FROM giveaway_channels WHERE giveaway_id=:g AND channel_id=:c"),
            {"g": event_id, "c": oc_id}
        )
        link = exists.first()

        if link:
            # убрать прикрепление
            await s.execute(
                stext("DELETE FROM giveaway_channels WHERE giveaway_id=:g AND channel_id=:c"),
                {"g": event_id, "c": oc_id}
            )
        else:
            # добавить прикрепление
            await s.execute(
                stext("INSERT INTO giveaway_channels(giveaway_id, channel_id, chat_id, title) "
                      "VALUES(:g, :c, :chat, :t)"),
                {"g": event_id, "c": oc_id, "chat": chat_id, "t": title}
            )

        # пересобираем данные для перерисовки
        res = await s.execute(
            stext("SELECT id, title FROM organizer_channels WHERE owner_user_id=:u AND status='ok'"),
            {"u": gw.owner_user_id}
        )
        channels = [(r[0], r[1]) for r in res.fetchall()]

        res = await s.execute(
            stext("SELECT channel_id FROM giveaway_channels WHERE giveaway_id=:g"),
            {"g": event_id}
        )
        attached_ids = {r[0] for r in res.fetchall()}

        res = await s.execute(
            stext("""
                SELECT gc.title, oc.username, gc.chat_id
                FROM giveaway_channels gc
                LEFT JOIN organizer_channels oc ON oc.id = gc.channel_id
                WHERE gc.giveaway_id = :g
                ORDER BY gc.id
            """),
            {"g": event_id}
        )
        attached_list = [(r[0], r[1], r[2]) for r in res.fetchall()]

    # текстовый блок + клавиатура с «галочками»
    new_text = build_connect_channels_text(gw.internal_title, attached_list)
    new_kb = build_channels_menu_kb(event_id, channels, attached_ids)

    # пробуем отредактировать текущее сообщение (если можно), иначе шлём новое
    try:
        await cq.message.edit_text(new_text, reply_markup=new_kb, parse_mode="HTML")
    except Exception:
        await cq.message.answer(new_text, reply_markup=new_kb, parse_mode="HTML")

    await cq.answer("Готово")

@dp.callback_query(F.data.startswith("raffle:add_channel:"))
async def cb_add_channel(cq: CallbackQuery, state: FSMContext):
    _, _, sid = cq.data.split(":")
    await state.update_data(chooser_event_id=int(sid))

    await cq.message.answer(ADD_CHAT_HELP_HTML, parse_mode="HTML", reply_markup=kb_add_cancel())
    await cq.message.answer("👇 Выберите канал или группу ниже", reply_markup=chooser_reply_kb())
    await cq.answer()

@dp.callback_query(F.data.startswith("raffle:add_group:"))
async def cb_add_group(cq: CallbackQuery, state: FSMContext):
    _, _, sid = cq.data.split(":")
    await state.update_data(chooser_event_id=int(sid))

    await cq.message.answer(ADD_CHAT_HELP_HTML, parse_mode="HTML", reply_markup=kb_add_cancel())
    await cq.message.answer("👇 Выберите канал или группу ниже", reply_markup=chooser_reply_kb())
    await cq.answer()

@dp.callback_query(F.data.startswith("raffle:start:"))
async def cb_start_raffle(cq: CallbackQuery):
    """
    Проверяем есть ли подключенные каналы перед показом предпросмотра.
    Если нет - показываем pop-up предупреждение.
    """
    _, _, sid = cq.data.split(":")
    gid = int(sid)

    # Проверяем есть ли подключенные каналы/группы
    async with session_scope() as s:
        # достаём розыгрыш
        gw = await s.get(Giveaway, gid)
        if not gw:
            await cq.answer("Розыгрыш не найден.", show_alert=True)
            return

        # проверяем количество подключенных каналов
        res = await s.execute(
            stext("SELECT COUNT(*) FROM giveaway_channels WHERE giveaway_id=:g"),
            {"g": gid}
        )
        channels_count = res.scalar_one() or 0

    # Если нет подключенных каналов - показываем pop-up предупреждение
    if channels_count == 0:
        await cq.answer("⚠️ Для запуска розыгрыша необходимо подключить хотя бы 1 канал / группу", show_alert=True)
        return

    # Если каналы есть - продолжаем как обычно
    # 1) предпросмотр тем же способом, что и ранее
    await _send_launch_preview_message(cq.message, gw)

    # 2) финальный блок
    await cq.message.answer(
        build_final_check_text(),
        reply_markup=kb_launch_confirm(gid),
        parse_mode="HTML"
    )

    await cq.answer()

async def _publish_to_prime_channel(gid: int, gw: "Giveaway") -> int | None:
    """
    Публикует пост розыгрыша в PRIME-канал.
    Идентично публикации в обычные каналы.
    Возвращает message_id опубликованного поста или None при ошибке.
    Результат сохраняется в таблице prime_channel_posts.
    """
    end_at_msk_dt = gw.end_at_utc.astimezone(MSK_TZ)
    end_at_msk_str = end_at_msk_dt.strftime("%H:%M %d.%m.%Y")
    now_msk = datetime.now(MSK_TZ).date()
    days_left = max(0, (end_at_msk_dt.date() - now_msk).days)

    preview_text = _compose_post_text(
        "",
        gw.winners_count,
        desc_html=(gw.public_description or ""),
        end_at_msk=end_at_msk_str,
        days_left=days_left,
    )

    kind, file_id = unpack_media(gw.photo_file_id)
    sent_message_id: int | None = None

    try:
        if file_id:
            if kind == "photo":
                suggested = "image.jpg"
            elif kind == "animation":
                suggested = "animation.mp4"
            elif kind == "video":
                suggested = "video.mp4"
            else:
                suggested = "file.bin"

            key, _s3_url = await file_id_to_public_url_via_s3(bot, file_id, suggested)
            preview_url = _make_preview_url(key, gw.internal_title or "", gw.public_description or "")
            hidden_link = f'<a href="{preview_url}"> </a>'
            media_position = getattr(gw, "media_position", "bottom")

            if media_position == "top":
                full_text = hidden_link + "\n" + preview_text
            else:
                full_text = preview_text + "\n\n" + hidden_link

            lp = LinkPreviewOptions(
                is_disabled=False,
                prefer_large_media=True,
                prefer_small_media=False,
                show_above_text=(media_position == "top"),
                url=preview_url,
            )

            sent = await bot.send_message(
                chat_id=PRIME_CHANNEL_ID,
                text=full_text,
                parse_mode="HTML",
                link_preview_options=lp,
                reply_markup=kb_public_participate(gid, for_channel=True),
            )
        else:
            cleaned_html, disable_preview = text_preview_cleaner.clean_text_preview(preview_text, has_media=False)
            send_kwargs = {
                "chat_id": PRIME_CHANNEL_ID,
                "text": cleaned_html,
                "parse_mode": "HTML",
                "reply_markup": kb_public_participate(gid, for_channel=True),
            }
            if disable_preview:
                send_kwargs["disable_web_page_preview"] = True
            sent = await bot.send_message(**send_kwargs)

        sent_message_id = sent.message_id
        logging.info("✅ [PRIME] Пост опубликован в PRIME-канале, gid=%s, msg_id=%s", gid, sent_message_id)

    except Exception as e:
        logging.error("❌ [PRIME] Ошибка публикации в PRIME-канале, gid=%s: %s", gid, e)
        return None

    # Сохраняем message_id в БД
    try:
        async with session_scope() as s:
            await s.execute(
                stext("""
                    INSERT INTO prime_channel_posts (giveaway_id, message_id)
                    VALUES (:gid, :msg_id)
                    ON CONFLICT (giveaway_id) DO UPDATE SET message_id = EXCLUDED.message_id
                """),
                {"gid": gid, "msg_id": sent_message_id},
            )
        logging.info("✅ [PRIME] message_id=%s сохранён для gid=%s", sent_message_id, gid)
    except Exception as e:
        logging.error("❌ [PRIME] Ошибка сохранения message_id в БД, gid=%s: %s", gid, e)

    return sent_message_id

async def _check_and_publish_prime(giveaway_id: int) -> None:
    """
    Проверяет кол-во участников розыгрыша.
    Если достигнуто 3 — публикует пост в PRIME-канал (только один раз).
    """
    logging.info(f"[_check_and_publish_prime] ▶️ Вызван для gid={giveaway_id}")
    try:
        async with session_scope() as s:
            # Уже опубликован?
            existing = await s.execute(
                stext("SELECT id FROM prime_channel_posts WHERE giveaway_id = :gid"),
                {"gid": giveaway_id}
            )
            if existing.first():
                return  # уже опубликован, ничего не делаем

            # Считаем участников
            cnt_res = await s.execute(
                stext("SELECT COUNT(DISTINCT user_id) FROM entries WHERE giveaway_id = :gid AND prelim_ok = true"),
                {"gid": giveaway_id}
            )
            cnt = cnt_res.scalar_one() or 0

            if cnt < 3:
                return  # ещё не достигли порога

            # Достигли 3 — публикуем
            gw = await s.get(Giveaway, giveaway_id)
            if not gw or gw.status != GiveawayStatus.ACTIVE:
                return
            # Явно читаем все нужные поля пока сессия открыта
            _ = (gw.id, gw.end_at_utc, gw.winners_count, gw.public_description,
                 gw.photo_file_id, gw.internal_title, gw.media_position, gw.status)
            await s.refresh(gw)

        logging.info("🚀 [PRIME] Достигнуто 3 участника, публикуем в PRIME-канал, gid=%s", giveaway_id)
        await _publish_to_prime_channel(giveaway_id, gw)

    except Exception as e:
        logging.error("❌ [PRIME] Ошибка в _check_and_publish_prime, gid=%s: %s", giveaway_id, e)

async def _edit_prime_channel_post(giveaway_id: int, bot_instance: Bot) -> bool:
    """
    Редактирует пост в PRIME-канале после завершения розыгрыша или перерозыгрыша.
    Логика идентична edit_giveaway_post, но работает с prime_channel_posts.
    """
    try:
        async with session_scope() as s:
            gw = await s.get(Giveaway, giveaway_id)
            if not gw:
                logging.error("[PRIME] edit: розыгрыш %s не найден", giveaway_id)
                return False

            participants_res = await s.execute(
                text("SELECT COUNT(DISTINCT user_id) FROM entries WHERE giveaway_id = :gid AND prelim_ok = true"),
                {"gid": giveaway_id},
            )
            participants_count = participants_res.scalar_one() or 0

            winners_res = await s.execute(
                stext("""
                    SELECT w.rank, COALESCE(u.username, 'Участник') as username, e.ticket_code
                    FROM winners w
                    LEFT JOIN entries e ON e.giveaway_id = w.giveaway_id AND e.user_id = w.user_id
                    LEFT JOIN users u ON u.user_id = w.user_id
                    WHERE w.giveaway_id = :gid
                    ORDER BY w.rank
                """),
                {"gid": giveaway_id},
            )
            winners = winners_res.all()

            post_res = await s.execute(
                stext("SELECT message_id FROM prime_channel_posts WHERE giveaway_id = :gid"),
                {"gid": giveaway_id},
            )
            post_row = post_res.first()

        if not post_row:
            logging.warning("[PRIME] edit: нет поста в PRIME-канале для gid=%s", giveaway_id)
            return False

        message_id = post_row[0]
        new_text = _compose_finished_post_text(gw, winners, participants_count)
        reply_markup = kb_finished_giveaway(giveaway_id, for_channel=True)

        media_type, media_file_id = unpack_media(gw.photo_file_id)
        has_media = bool(media_file_id)
        cleaned_text, disable_preview = text_preview_cleaner.clean_text_preview(new_text, has_media)

        if has_media and media_file_id:
            try:
                if media_type == "photo":
                    suggested = "image.jpg"
                elif media_type == "animation":
                    suggested = "animation.mp4"
                elif media_type == "video":
                    suggested = "video.mp4"
                else:
                    suggested = "file.bin"

                key, _ = await file_id_to_public_url_via_s3(bot_instance, media_file_id, suggested)
                preview_url = _make_preview_url(key, gw.internal_title or "", gw.public_description or "")
                hidden_link = f'<a href="{preview_url}">&#8203;</a>'
                media_position = getattr(gw, "media_position", "bottom")
                full_html = (hidden_link + "\n" + cleaned_text) if media_position == "top" else (cleaned_text + "\n\n" + hidden_link)

                lp = LinkPreviewOptions(
                    is_disabled=False,
                    prefer_large_media=True,
                    prefer_small_media=False,
                    show_above_text=(media_position == "top"),
                    url=preview_url,
                )
                await bot_instance.edit_message_text(
                    chat_id=PRIME_CHANNEL_ID,
                    message_id=message_id,
                    text=full_html,
                    parse_mode="HTML",
                    link_preview_options=lp,
                    reply_markup=reply_markup,
                )
            except Exception:
                await bot_instance.edit_message_caption(
                    chat_id=PRIME_CHANNEL_ID,
                    message_id=message_id,
                    caption=cleaned_text,
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                )
        else:
            send_kwargs = {
                "chat_id": PRIME_CHANNEL_ID,
                "message_id": message_id,
                "text": cleaned_text,
                "parse_mode": "HTML",
                "reply_markup": reply_markup,
            }
            if disable_preview:
                send_kwargs["disable_web_page_preview"] = True
            await bot_instance.edit_message_text(**send_kwargs)

        logging.info("✅ [PRIME] Пост отредактирован в PRIME-канале, gid=%s", giveaway_id)
        return True

    except Exception as e:
        logging.error("❌ [PRIME] Ошибка редактирования поста в PRIME-канале, gid=%s: %s", giveaway_id, e)
        return False


async def _cancel_prime_channel_post(giveaway_id: int, bot_instance: Bot) -> bool:
    """
    Редактирует пост в PRIME-канале при отмене розыгрыша —
    убирает кнопку «Участвовать» и добавляет пометку об отмене.
    """
    try:
        async with session_scope() as s:
            gw = await s.get(Giveaway, giveaway_id)
            post_res = await s.execute(
                stext("SELECT message_id FROM prime_channel_posts WHERE giveaway_id = :gid"),
                {"gid": giveaway_id},
            )
            post_row = post_res.first()

        if not post_row or not gw:
            return False

        message_id = post_row[0]
        cancelled_text = (gw.public_description or "") + "\n\n<b>❌ Розыгрыш отменён.</b>"
        cleaned_text, _ = text_preview_cleaner.clean_text_preview(cancelled_text, has_media=False)

        await bot_instance.edit_message_text(
            chat_id=PRIME_CHANNEL_ID,
            message_id=message_id,
            text=cleaned_text,
            parse_mode="HTML",
            reply_markup=None,
        )
        logging.info("✅ [PRIME] Пост помечен как отменённый в PRIME-канале, gid=%s", giveaway_id)
        return True

    except Exception as e:
        logging.error("❌ [PRIME] Ошибка обновления отменённого поста в PRIME-канале, gid=%s: %s", giveaway_id, e)
        return False

#--- Хелпер ---
async def _launch_and_publish(gid: int, message: types.Message):
    """
    Минимальный рабочий запуск:
      - ставим статус ACTIVE,
      - планируем завершение,
      - публикуем пост С КНОПКАМИ в прикреплённых каналах/группах и сохраняем message_id.
    """
    # 1) читаем розыгрыш и при необходимости активируем
    async with session_scope() as s:
        gw = await s.get(Giveaway, gid)
        if not gw:
            await message.answer("Розыгрыш не найден.")
            logging.error("GW %s not found, abort publish", gid)
            return None
        if getattr(gw, "status", None) != GiveawayStatus.ACTIVE:
            gw.status = GiveawayStatus.ACTIVE
            s.add(gw)
            logging.info("GW %s status -> ACTIVE", gid)

    # 2) планируем завершение - ИСПРАВЛЕННАЯ ВЕРСИЯ
    try:
        run_dt = gw.end_at_utc
        
        # КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: нормализуем timezone
        run_dt = normalize_datetime(run_dt)
        current_utc = datetime.now(timezone.utc)
        time_until_run = run_dt - current_utc
        
        logging.info(f"⏰ SCHEDULER DEBUG: Current UTC: {current_utc}, Run UTC: {run_dt}, Time until: {time_until_run}")

        scheduler.add_job(
            func=finalize_and_draw_job,
            trigger=DateTrigger(run_date=run_dt),
            args=[gid],
            id=f"final_{gid}",
            replace_existing=True,
        )
        logging.info(f"✅ SCHEDULED: giveaway {gid}, time: {run_dt}")
        
        # Проверяем что job добавлен
        job = scheduler.get_job(f"final_{gid}")
        if job:
            logging.info(f"✅ Job confirmed: next_run={job.next_run_time}")
        else:
            logging.error(f"❌ Job NOT found after scheduling!")
            
    except Exception as e:
        logging.error(f"❌ Failed to schedule giveaway {gid}: {e}")
        # Более детальное логирование ошибки
        import traceback
        logging.error(f"Traceback: {traceback.format_exc()}")

    # 3) берём прикреплённые чаты
    async with session_scope() as s:
        res = await s.execute(
            stext("SELECT chat_id FROM giveaway_channels WHERE giveaway_id=:g"),
            {"g": gid}
        )
        chat_ids = [row[0] for row in res.fetchall()]

    logging.info("GW %s: attached chats = %s", gid, chat_ids)

    # 4) если пусто — сообщаем и выходим
    if not chat_ids:
        await message.answer(
            "К этому розыгрышу пока не прикреплено ни одного канала/группы.\n"
            "Нажми «Добавить канал/группу», отметь хотя бы один (должна появиться «✅»), и повтори запуск."
        )
        return None

    # 5) собираем ТОЛЬКО текст (без кнопок)
    # Используем время КАК ЕГО ВВЕЛ ПОЛЬЗОВАТЕЛЬ
    end_at_msk_dt = gw.end_at_utc.astimezone(MSK_TZ)
    end_at_msk_str = end_at_msk_dt.strftime("%H:%M %d.%m.%Y")
    
    # Правильно вычисляем дни
    now_msk = datetime.now(MSK_TZ).date()
    end_at_date = end_at_msk_dt.date()
    days_left = max(0, (end_at_date - now_msk).days)

    # ВАЖНО: _compose_preview_text принимает позиционные аргументы: (title, prizes)
    preview_text = _compose_post_text(
        "",
        gw.winners_count,
        desc_html=(gw.public_description or ""),
        end_at_msk=end_at_msk_str,        # Оригинальное время (17:51) будет скорректировано
        days_left=days_left,
    )

    # 🔍 ДИАГНОСТИКА ПРЕМИУМ-ЭМОДЗИ
    logging.info(f"🔍 [PREMIUM-EMOJI-DEBUG] preview_text содержит <tg-emoji>: {'<tg-emoji' in preview_text}")
    logging.info(f"🔍 [PREMIUM-EMOJI-DEBUG] preview_text первые 200 символов: {preview_text[:200]}")
    logging.info(f"🔍 [PREMIUM-EMOJI-DEBUG] public_description из БД содержит <tg-emoji>: {'<tg-emoji' in (gw.public_description or '')}")

    # 6) публикуем в каждом чате — С клавиатурой «Участвовать» и попыткой link-preview
    kind, file_id = unpack_media(gw.photo_file_id)
    
    # Сохраняем message_id для каждого чата
    message_ids = {}  # {chat_id: message_id}
    publish_text, publish_entities = html_to_text_and_entities(preview_text)

    for chat_id in chat_ids:
        try:
            # DIAG: проверяем, есть ли у чата разрешённый набор custom emoji для ботов
            try:
                chat = await bot.get_chat(chat_id)
                logging.info(
                    "CHAT DEBUG chat_id=%s type=%s custom_emoji_sticker_set_name=%s",
                    chat_id,
                    getattr(chat, "type", None),
                    getattr(chat, "custom_emoji_sticker_set_name", None),
                )
            except Exception as chat_dbg_err:
                logging.warning("CHAT DEBUG failed for chat_id=%s: %s", chat_id, chat_dbg_err)

            # --- Пытаемся отправить «фиолетовую рамку» как в предпросмотре ---
            if file_id:
                # подбираем «имя» (важно для корректного Content-Type)
                if kind == "photo":
                    suggested = "image.jpg"
                elif kind == "animation":
                    suggested = "animation.mp4"
                elif kind == "video":
                    suggested = "video.mp4"
                else:
                    suggested = "file.bin"

                # выгружаем из TG в S3 и собираем наш preview_url
                key, _s3_url = await file_id_to_public_url_via_s3(bot, file_id, suggested)
                preview_url = _make_preview_url(key, gw.internal_title or "", gw.public_description or "")

                # 🔄 КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: Определяем hidden_link ПЕРЕД использованием
                hidden_link = f'<a href="{preview_url}"> </a>'  # Пробел вместо невидимого символа
                
                # 🔄 ИСПРАВЛЕНИЕ: Используем сохраненную позицию медиа
                media_position = getattr(gw, 'media_position', 'bottom')
                
                if media_position == "top":
                    full_text = hidden_link + "\n" + preview_text
                else:
                    full_text = preview_text + "\n\n" + hidden_link

                lp = LinkPreviewOptions(
                    is_disabled=False,
                    prefer_large_media=True,
                    prefer_small_media=False,
                    show_above_text=(media_position == "top"),
                    url=preview_url
                )

                # Сохраняем результат отправки
                # ЕСЛИ ЕСТЬ МЕДИА - НИКОГДА НЕ ОТКЛЮЧАЕМ ПРЕВЬЮ!
                # Отправляем HTML напрямую, чтобы Telegram корректно отрисовал <tg-emoji>
                sent_msg = await bot.send_message(
                    chat_id=chat_id,
                    text=full_text,
                    parse_mode="HTML",
                    link_preview_options=lp,
                    reply_markup=kb_public_participate(gid, for_channel=True),
                )
                message_ids[chat_id] = sent_msg.message_id
                logging.info(
                    "✅ SENT MESSAGE DEBUG chat_id=%s msg_id=%s entities_in_response=%s",
                    chat_id,
                    sent_msg.message_id,
                    getattr(sent_msg, "entities", None),
                )
                logging.info(f"💾 Сохранен message_id {sent_msg.message_id} для чата {chat_id}")

                
            else:
                # медиа нет — обычный текст + кнопка

                cleaned_html, disable_preview = text_preview_cleaner.clean_text_preview(preview_text, has_media=False)

                send_kwargs = {
                    "chat_id": chat_id,
                    "text": cleaned_html,
                    "parse_mode": "HTML",
                    "reply_markup": kb_public_participate(gid, for_channel=True),
                }

                if disable_preview:
                    send_kwargs["disable_web_page_preview"] = True

                sent_msg = await bot_instance.send_message(**send_kwargs)
                message_ids[chat_id] = sent_msg.message_id
                logging.info(
                    "✅ SENT MESSAGE DEBUG chat_id=%s msg_id=%s entities_in_response=%s",
                    chat_id,
                    sent_msg.message_id,
                    getattr(sent_msg, "entities", None),
                )
                logging.info(f"💾 Сохранен message_id {sent_msg.message_id} для чата {chat_id}")

        except Exception as e:
            logging.warning("Link-preview не вышел в чате %s (%s), пробую fallback-медиа...", chat_id, e)
            # --- Fallback: нативное медиа с той же подписью + кнопка ---
            try:
                
                fallback_caption_html = preview_text  # HTML с <tg-emoji>

                if kind == "photo" and file_id:
                    sent_msg = await bot.send_photo(
                        chat_id,
                        file_id,
                        caption=fallback_caption_html,
                        parse_mode="HTML",
                        reply_markup=kb_public_participate(gid, for_channel=True),
                    )
                    message_ids[chat_id] = sent_msg.message_id

                elif kind == "animation" and file_id:
                    sent_msg = await bot.send_animation(
                        chat_id,
                        file_id,
                        caption=fallback_caption_html,
                        parse_mode="HTML",
                        reply_markup=kb_public_participate(gid, for_channel=True),
                    )
                    message_ids[chat_id] = sent_msg.message_id

                elif kind == "video" and file_id:
                    sent_msg = await bot.send_video(
                        chat_id,
                        file_id,
                        caption=fallback_caption_html,
                        parse_mode="HTML",
                        reply_markup=kb_public_participate(gid, for_channel=True),
                    )
                    message_ids[chat_id] = sent_msg.message_id

                else:
                    # НЕТ МЕДИА - ПРОВЕРЯЕМ ПОЛЬЗОВАТЕЛЬСКИЕ ССЫЛКИ
                    has_media = bool(file_id)
                    cleaned_text, disable_preview = text_preview_cleaner.clean_text_preview(preview_text, has_media)
                    send_kwargs = {
                        "chat_id": chat_id,
                        "text": cleaned_text,
                        "parse_mode": "HTML",
                        "reply_markup": kb_public_participate(gid, for_channel=True),
                    }
                    if disable_preview:
                        send_kwargs["disable_web_page_preview"] = True
                    
                    sent_msg = await bot.send_message(**send_kwargs)
                    message_ids[chat_id] = sent_msg.message_id
                    
                logging.info(f"💾 Сохранен message_id {sent_msg.message_id} для чата {chat_id} (fallback)")
                
            except Exception as e2:
                logging.warning("Публикация поста не удалась в чате %s: %s", chat_id, e2)


    # Сохраняем message_id в БД
    if message_ids:
        async with session_scope() as s:
            for chat_id, message_id in message_ids.items():
                await s.execute(
                    stext("UPDATE giveaway_channels SET message_id = :msg_id WHERE giveaway_id = :gid AND chat_id = :chat_id"),
                    {"msg_id": message_id, "gid": gid, "chat_id": chat_id}
                )
        logging.info(f"💾 Сохранено {len(message_ids)} message_id в БД для розыгрыша {gid}")
    else:
        logging.warning(f"⚠️ Не удалось сохранить ни одного message_id для розыгрыша {gid}")

    # PRIME-канал: публикуем только после набора 3 участников (см. _check_and_publish_prime)
    logging.info("ℹ️ [PRIME] Публикация отложена до набора 3 участников, gid=%s", gid)

    return gw


#--- Обработчик для запуска розыгрыша ---
@dp.callback_query(F.data.startswith("launch:do:"))
async def cb_launch_do(cq: CallbackQuery):
    await cq.answer()
    try:
        await cq.message.edit_reply_markup()
    except Exception:
        pass

    try:
        gid = int(cq.data.split(":")[2])
    except Exception:
        await cq.message.answer("Не удалось определить розыгрыш для запуска.")
        return

    gw = await _launch_and_publish(gid, cq.message)
    if not gw:
        return

    from html import escape as _escape
    title_html = _escape(gw.internal_title or "")
    
    # Сообщение с HTML-разметкой
    combined_text = (
        f"✅ <b>Розыгрыш {title_html} запущен!</b>\n\n"
        "👀 <b>Подпишитесь на канал</b>, где команда публикует важные новости о боте и анонсы нового функционала:\n"
        "https://t.me/prizeme_official_news\n\n"
        "🚀 Вы также можете <b>оформить подписку</b>, которая дает продвинутый функционал в сервисе, "
        "нажмите на <b>Подписка</b>, чтобы увидеть все преимущества\n\n"
        "❤️ <b>Спасибо, что выбрали нас!</b> Вы можете поддержать сервис пожертвованием, нажав на кнопку <b>Донат</b>, "
        "оставить можно любую сумму, все деньги идут на развитие сервиса"
    )
    
    kb = InlineKeyboardBuilder()
    kb.button(text="Подписка", url="https://t.me/tribute/app?startapp=sHOW")  # Та же ссылка что и в "Тарифы"
    kb.button(text="Донат", url="https://t.me/tribute/app?startapp=dA1o")    # Та же ссылка что и в "Поддержать"
    kb.adjust(2)  # 2 кнопки в один ряд
    
    # Отправляем одно сообщение
    await cq.message.answer(combined_text, reply_markup=kb.as_markup(), parse_mode="HTML", disable_web_page_preview=True)

#--- Обработчик настройки розыгрыша ---

@dp.callback_query(F.data.startswith("raffle:settings_menu:"))
async def cb_settings_menu(cq: CallbackQuery):
    """Показывает меню настроек розыгрыша для КОНТЕКСТА ЗАПУСКА"""
    _, _, sid = cq.data.split(":")
    gid = int(sid)
    
    async with session_scope() as s:
        gw = await s.get(Giveaway, gid)
        if not gw:
            await cq.answer("Розыгрыш не найден.", show_alert=True)
            return
    
    # Показываем меню настроек с контекстом "launch"
    text = f"Что вы хотите настроить в розыгрыше <b>{gw.internal_title}</b>"
    await cq.message.answer(text, reply_markup=kb_settings_menu(gid, gw.internal_title, "launch"), parse_mode="HTML")
    await cq.answer()


# === Блок "Дополнительные механики" - показывает описание и кнопки ===
@dp.callback_query(F.data.startswith("raffle:mechanics:"))
async def cb_mechanics(cq: CallbackQuery):
    
    # Извлекаем ID розыгрыша
    gid = int(cq.data.split(":")[2])
    
    # ИСПОЛЬЗУЕМ cq.from_user.id - это реальный ID пользователя
    user_id = cq.from_user.id
    
    # Диагностический лог
    logging.info(f"🔍 [DIAGNOSTICS] cb_mechanics: user_id={user_id}, giveaway_id={gid}")
    
    # Используем обновленную функцию
    await update_mechanics_text_with_user(cq.message, gid, user_id)
    
    await cq.answer()

#Обработчик для заблокированной кнопки Captcha
@dp.callback_query(F.data.startswith("mechanics:captcha_blocked:"))
async def cb_mechanics_captcha_blocked(cq: CallbackQuery):
    # Просто показываем pop-up о необходимости премиум-подписки
    await cq.answer(
        "💎 Оформите подписку ПРЕМИУМ для доступа к функционалу",
        show_alert=True
    )

# Обработчик кнопки Captcha для премиум-пользователей
@dp.callback_query(F.data.startswith("mechanics:captcha:"))
async def cb_mechanics_captcha(cq: CallbackQuery):
    
    # ПРОВЕРКА ПРЕМИУМ СТАТУСА
    user_id = cq.from_user.id
    user_status = await get_user_status(user_id)
    
    if user_status == 'standard':
        # Стандартный пользователь - показываем pop-up о необходимости подписки
        await cq.answer(
            "💎 Оформите подписку ПРЕМИУМ для доступа к функционалу",
            show_alert=True
        )
        return
    
    gid = int(cq.data.split(":")[2])

    # ОТЛАДОЧНЫЙ КОД:
    mechanics_logger.info(f"🔍 CAPTCHA BUTTON CLICKED: giveaway_id={gid}")
    await debug_mechanics(gid)  # Вызываем отладку
    
    # Получаем ТЕКУЩЕЕ состояние из БД напрямую, минуя кэш
    async with session_scope() as s:
        # Очищаем кэш SQLAlchemy перед запросом
        s.expire_all()
        
        result = await s.execute(
            text("""
                SELECT is_active 
                FROM giveaway_mechanics 
                WHERE giveaway_id = :gid AND mechanic_type = 'captcha'
            """),
            {"gid": gid}
        )
        row = result.first()
        current_active = bool(row and row[0]) if row else False
    
    # Меняем состояние на противоположное
    new_state = not current_active
    
    # Сохраняем в БД
    success = await save_giveaway_mechanic(gid, "captcha", new_state)
    
    if success:
        if new_state:
            await cq.answer("✅ Captcha подключена", show_alert=True)
        else:
            await cq.answer("❌ Captcha отключена", show_alert=True)
        
        # Используем user_id напрямую для обновления
        await update_mechanics_text_with_user(cq.message, gid, user_id)
    else:
        await cq.answer("❌ Ошибка сохранения настроек Captcha", show_alert=True)


# Обработчик кнопки "🤝🏼 Подключить рефералов" (пока заглушка)
@dp.callback_query(F.data.startswith("mechanics:referral:"))
async def cb_mechanics_referral(cq: CallbackQuery):
    await cq.answer("🛠️ В разработке", show_alert=True)


# Обработчик кнопки "⬅️ Назад" в дополнительных механиках
@dp.callback_query(F.data.startswith("mechanics:back:"))
async def cb_mechanics_back(cq: CallbackQuery):

    gid = int(cq.data.split(":")[2])
    
    # ПЕРЕДАЕМ user_id ДЛЯ КОРРЕКТНОГО ОТОБРАЖЕНИЯ КНОПКИ
    user_id = cq.from_user.id
    
    # Получаем данные розыгрыша для предпросмотра
    async with session_scope() as s:
        gw = await s.get(Giveaway, gid)
        if not gw:
            await cq.answer("Розыгрыш не найден.", show_alert=True)
            return
    
    # 1) Показываем предпросмотр розыгрыша (как при запуске)
    await _send_launch_preview_message(cq.message, gw)
    
    # 2) Создаем финальный текст с проверкой механик
    base_text = (
        "🚀 <b>Остался последний шаг и можно запускать розыгрыш</b>\n\n"
        "Выше показан блок с розыгрышем, убедитесь, что всё указано верно. "
        "Как только это сделаете, можете запускать розыгрыш, нажав на кнопку снизу\n\n"
    )
    
    # Проверяем подключенные механики
    mechanics = await get_giveaway_mechanics(gid)
    active_mechanics = [m for m in mechanics if m.get("is_active")]
    
    if active_mechanics:
        base_text += "<b>Подключенные дополнительные механики:</b>\n"
        for mechanic in active_mechanics:
            if mechanic["type"] == "captcha":
                base_text += "✅ Защита от ботов с Captcha\n"
            elif mechanic["type"] == "referral":
                base_text += "✅ Реферальная система\n"
        base_text += "\n"
    
    base_text += (
        "<b><i>Внимание!</i></b> После запуска пост с розыгрышем будет автоматически опубликован "
        "в подключённых каналах / группах к текущему розыгрышу."
    )
    
    # 3) Отправляем финальный блок с кнопками запуска
    await cq.message.answer(
        base_text,
        reply_markup=kb_launch_confirm(gid),
        parse_mode="HTML"
    )
    
    # 4) Удаляем сообщение с механиками
    try:
        await cq.message.delete()
    except Exception:
        pass
    
    await cq.answer()


#--- Обработчики настройки черновика и розыгрышей ---

@dp.callback_query(F.data.startswith("settings:name:"))
async def cb_settings_name(cq: CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Название' в настройках"""
    gid = int(cq.data.split(":")[2])
    
    # Сохраняем контекст для возврата
    await state.update_data(
        editing_giveaway_id=gid,
        setting_type="title",
        return_context="settings"  # или "launch" в зависимости от контекста
    )
    
    await state.set_state(EditFlow.EDIT_TITLE)
    await cq.message.answer(
        "Введите новое название розыгрыша:\n\n"
        "Максимум — <b>50 символов</b>.\n\n"
        "<i>Пример названия:</i> <b>MacBook Pro от канала PrizeMe</b>",
        parse_mode="HTML"
    )
    await cq.answer()

@dp.callback_query(F.data.startswith("settings:desc:"))
async def cb_settings_desc(cq: CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Описание' в настройках"""
    gid = int(cq.data.split(":")[2])
    
    await state.update_data(
        editing_giveaway_id=gid,
        setting_type="desc", 
        return_context="settings"
    )
    
    await state.set_state(EditFlow.EDIT_DESC)
    await cq.message.answer(DESCRIPTION_PROMPT, parse_mode="HTML")
    await cq.answer()

@dp.callback_query(F.data.startswith("settings:date:"))
async def cb_settings_date(cq: CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Дата окончания' в настройках"""
    gid = int(cq.data.split(":")[2])
    
    await state.update_data(
        editing_giveaway_id=gid,
        setting_type="endat",
        return_context="settings"  
    )
    
    await state.set_state(EditFlow.EDIT_ENDAT)
    await cq.message.answer(format_endtime_prompt(), parse_mode="HTML")
    await cq.answer()


# === Обработчик кнопки 'Медиа' в настройках ===

@dp.callback_query(F.data.startswith("settings:media:"))
async def cb_settings_media(cq: CallbackQuery, state: FSMContext):
    gid = int(cq.data.split(":")[2])
    
    # Получаем текущую позицию медиа из БД
    async with session_scope() as s:
        gw = await s.get(Giveaway, gid)
        current_position = gw.media_position if hasattr(gw, 'media_position') else 'bottom'
    
    await state.update_data(
        editing_giveaway_id=gid,
        setting_type="media",
        return_context="settings",
        current_media_position=current_position  # <-- ДОБАВЬТЕ ЭТУ СТРОКУ
    )
    
    await state.set_state(EditFlow.EDIT_MEDIA)
    
    # Показываем текущую позицию в сообщении
    position_text = "сверху" if current_position == "top" else "снизу"
    await cq.message.answer(
        f"Текущая позиция медиа: <b>{position_text}</b>\n\n{MEDIA_QUESTION}", 
        reply_markup=kb_yes_no(), 
        parse_mode="HTML"
    )
    await cq.answer()

# --- Обработчик кнопки "Количество победителей" в настройках ---
@dp.callback_query(F.data.startswith("settings:winners:"))
async def cb_settings_winners(cq: CallbackQuery, state: FSMContext):
    gid = int(cq.data.split(":")[2])
    user_id = cq.from_user.id
    
    await state.update_data(
        editing_giveaway_id=gid,
        setting_type="winners",
        return_context="settings"
    )
    
    # Получаем лимит для пользователя
    limit, status = await get_winners_limit(user_id)
    
    await state.set_state(EditFlow.EDIT_WINNERS)
    
    if status == 'premium':
        prompt = f"Введите новое количество победителей (от 1 до {limit}):"
    else:
        prompt = f"Введите новое количество победителей (от 1 до {limit}):"
    
    await cq.message.answer(prompt)
    await cq.answer()


#--- Кнопка "назад" ---
@dp.callback_query(F.data.startswith("settings:back:"))
async def cb_settings_back(cq: CallbackQuery):
    """
    Возврат из меню настроек (просто удаляем сообщение с меню)
    """
    try:
        await cq.message.delete()
    except Exception:
        pass
    await cq.answer()

@dp.callback_query(F.data.startswith("raffle:noop:"))
async def cb_noop(cq: CallbackQuery):
    # Просто заглушка для кнопок-«индикаторов» подключённых каналов
    await cq.answer("Это информационная кнопка.")

async def show_stats(chat_id:int, gid:int):
    async with session_scope() as s:
        res = await s.execute(stext("SELECT COUNT(*) FROM entries WHERE giveaway_id=:gid"),{"gid":gid})
        total = res.scalar_one()
        res = await s.execute(stext("SELECT COUNT(*) FROM entries WHERE giveaway_id=:gid AND final_ok=true"),{"gid":gid})
        ok_final = res.scalar_one() or 0
        gw = await s.get(Giveaway, gid)
    text_stat = (f"<b>Статус:</b> {gw.status}\n"
                 f"<b>Участников (всего билетов):</b> {total}\n"
                 f"<b>В пуле финала:</b> {ok_final}\n"
                 f"<b>commit:</b> <code>{gw.commit_hash or '-'}</code>\n")
    await bot.send_message(chat_id, text_stat)

@dp.callback_query(F.data.startswith("u:check:"))
async def user_check(cq:CallbackQuery):
    gid = int(cq.data.split(":")[2])
    ok, details = await check_membership_on_all(bot, cq.from_user.id, gid)
    lines = [("✅ " if okk else "❌ ")+t for t,okk in details]
    await cq.message.answer("Проверка подписки:\n"+"\n".join(lines),
                            reply_markup=kb_participate(gid, allow=ok))

# --- Обработчик участия в розыгрыше с поддержкой Captcha ---
@dp.callback_query(F.data.startswith("u:join:"))
async def user_join(cq: CallbackQuery):
    # Константы
    WEBAPP_BASE_URL = os.getenv("WEBAPP_BASE_URL", "https://prizeme.ru")
    
    gid = int(cq.data.split(":")[2])
    user_id = cq.from_user.id
    
    # ПРОВЕРКА 1: Активен ли розыгрыш
    async with session_scope() as s:
        gw = await s.get(Giveaway, gid)
        if gw.status != GiveawayStatus.ACTIVE:
            await cq.answer("Розыгрыш не активен.", show_alert=True)
            return

    # Проверяем подписки ДО Captcha!
    # Регистрируем пользователя при участии
    try:
        await ensure_bot_user(cq.from_user.id, cq.from_user.username, cq.from_user.first_name)
        # Обновляем Telegram Premium статус и язык в таблице users
        try:
            async with session_scope() as _s:
                await _s.execute(
                    text("""
                        INSERT INTO users(user_id, username, is_premium, language_code, first_name)
                        VALUES (:uid, :uname, :premium, :lang, :fname)
                        ON CONFLICT(user_id) DO UPDATE SET
                            username      = COALESCE(EXCLUDED.username, users.username),
                            is_premium    = EXCLUDED.is_premium,
                            language_code = COALESCE(EXCLUDED.language_code, users.language_code),
                            first_name    = COALESCE(EXCLUDED.first_name, users.first_name)
                    """),
                    {
                        "uid":     cq.from_user.id,
                        "uname":   cq.from_user.username,
                        "premium": bool(getattr(cq.from_user, 'is_premium', False)),
                        "lang":    getattr(cq.from_user, 'language_code', None),
                        "fname":   cq.from_user.first_name,
                    }
                )
                await _s.commit()
        except Exception as _e:
            logging.warning(f"[user_join] users upsert failed: {_e}")

        # Записываем клик (уникальный на пользователя)
        try:
            async with session_scope() as _s:
                await _s.execute(
                    text("""
                        INSERT INTO giveaway_clicks(giveaway_id, user_id, clicked_at)
                        VALUES (:gid, :uid, NOW())
                        ON CONFLICT(giveaway_id, user_id) DO NOTHING
                    """),
                    {"gid": gid, "uid": user_id}
                )
                await _s.commit()
        except Exception as _e:
            logging.warning(f"[user_join] click insert failed: {_e}")

        logging.info(f"✅ Пользователь {cq.from_user.id} зарегистрирован при участии в розыгрыше")
    except Exception as e:
        logging.error(f"❌ Ошибка регистрации при участии: {e}")

    # Проверяем подписки
    ok, details = await check_membership_on_all(bot, cq.from_user.id, gid)
    if not ok:
        await cq.answer("Подпишитесь на все каналы и попробуйте снова.", show_alert=True)
        return

    # ПРОВЕРКА 2: Есть ли активная механика Captcha?
    has_captcha = await is_mechanic_active(gid, 'captcha')
    
    if has_captcha:
        # ЕСТЬ CAPTCHA: отправляем пользователя в WebApp с простой Captcha
        
        # Генерируем Captcha и получаем цифры
        captcha_data = await generate_simple_captcha(gid, user_id)
        captcha_digits = captcha_data["digits"]
        captcha_token = captcha_data["token"]
        
        # Используем start_param для Telegram WebApp
        start_param = f"captcha_{gid}_{user_id}_{captcha_digits}_{captcha_token}"
        
        # Правильный URL с .html
        webapp_url = f"{WEBAPP_BASE_URL}/miniapp/captcha.html?tgWebAppStartParam={start_param}"
        
        # Логирование для отладки
        logging.info(f"📱 [CAPTCHA] Generated start_param: {start_param}")
        logging.info(f"📱 [CAPTCHA] WebApp URL: {webapp_url}")

        # Открываем WebApp
        await cq.message.answer(
            "🛡️ <b>Для участия в этом розыгрыше необходимо пройти проверку безопасности.</b>\n\n"
            "Нажмите кнопку ниже чтобы открыть страницу проверки и продолжить участие.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[
                    InlineKeyboardButton(
                        text="🔐 Пройти проверку безопасности",
                        web_app=WebAppInfo(url=webapp_url)
                    )
                ]]
            ),
            parse_mode="HTML"
        )
        
        await cq.answer(f"Открываю проверку безопасности...")
        return
    
    # НЕТ CAPTCHA: стандартный процесс участия
    # Выдаем билет
    async with session_scope() as s:
        res = await s.execute(
            text("SELECT ticket_code FROM entries WHERE giveaway_id=:gid AND user_id=:u"),
            {"gid": gid, "u": user_id}
        )
        row = res.first()
        
        if row:
            code = row[0]
            await cq.message.answer(f"✅ Вы уже участвуете в этом розыгрыше!\n\nВаш билет: <b>{code}</b>", disable_notification=False)
        else:
            for _ in range(5):
                code = gen_ticket_code()
                try:
                    # Определяем source_channel — берём первый канал розыгрыша из которого пришёл пост
                    src_ch_res = await s.execute(
                        text("SELECT chat_id FROM giveaway_channels WHERE giveaway_id=:gid ORDER BY id LIMIT 1"),
                        {"gid": gid}
                    )
                    src_ch_row = src_ch_res.first()
                    source_channel_id = src_ch_row[0] if src_ch_row else None

                    await s.execute(
                        text("""
                            INSERT INTO entries(giveaway_id, user_id, ticket_code, prelim_ok, prelim_checked_at, source_channel_id)
                            VALUES (:gid, :u, :code, :prelim_ok, :ts, :src)
                            ON CONFLICT DO NOTHING
                        """),
                        {"gid": gid, "u": user_id, "code": code, "prelim_ok": True,
                         "ts": datetime.utcnow(), "src": source_channel_id}
                    )

                    # Записываем статус подписки ПЕРЕД выдачей билета (was_subscribed = был ли подписан ДО нажатия)
                    # Для user_join подписка уже проверена и ОК, поэтому смотрим историю через entry_subscriptions
                    # Если записи нет — значит подписался специально ради розыгрыша (новый подписчик)
                    try:
                        channels_res = await s.execute(
                            text("SELECT chat_id FROM giveaway_channels WHERE giveaway_id=:gid"),
                            {"gid": gid}
                        )
                        all_channels = [r[0] for r in channels_res.fetchall()]
                        for ch_id in all_channels:
                            # was_subscribed = False означает: подписался ради розыгрыша (новый подписчик)
                            # Мы не можем знать был ли подписан раньше, поэтому:
                            # - если это первое участие → записываем was_subscribed=False (новый подписчик)
                            # - дубликаты игнорируются через ON CONFLICT DO NOTHING
                            await s.execute(
                                text("""
                                    INSERT INTO entry_subscriptions(giveaway_id, user_id, channel_id, was_subscribed)
                                    VALUES (:gid, :uid, :chid, false)
                                    ON CONFLICT(giveaway_id, user_id, channel_id) DO NOTHING
                                """),
                                {"gid": gid, "uid": user_id, "chid": ch_id}
                            )
                    except Exception as _e:
                        logging.warning(f"[user_join] entry_subscriptions insert failed: {_e}")

                    await cq.message.answer(f"✅ Вы успешно участвуете в розыгрыше!\n\nВаш билет: <b>{code}</b>", disable_notification=False, parse_mode="HTML")
                    # Проверяем порог для публикации в PRIME
                    asyncio.create_task(_check_and_publish_prime(gid))
                    break

                except Exception as e:
                    logging.error(f"❌ Ticket insert failed (gid={gid}, uid={user_id}): {e}", exc_info=True)
                    continue
    
    await cq.answer()


async def finalize_and_draw_job(giveaway_id: int):
    """
    ФИКСИРОВАННАЯ ВЕРСИЯ: убрана передача bot как параметра
    """
    print(f"🎯 FINALIZE_AND_DRAW_JOB ► старт для розыгрыша {giveaway_id}")

    # Получаем бот из глобального контекста
    from bot import bot  # Импортируем глобальный экземпляр бота
    
    async with Session() as s:
        # ---------- 1. Загружаем розыгрыш ----------
        # ФИКС: передаем giveaway_id как число, а не bot object
        gw = await s.get(Giveaway, giveaway_id)
        if not gw:
            print(f"❌ Розыгрыш {giveaway_id} не найден в БД")
            return

        if gw.status in (GiveawayStatus.CANCELLED, GiveawayStatus.FINISHED):
            print(f"⚠️ Розыгрыш {giveaway_id} уже в статусе {gw.status}, повторная финализация не нужна")
            return

        print(f"🔍 Финализируем розыгрыш {gw.id} «{gw.internal_title}»")

        # ---------- 2. Все, у кого есть билет (prelim_ok = true) ----------
        res = await s.execute(
            text("""
                SELECT user_id, ticket_code
                FROM entries
                WHERE giveaway_id = :gid
                  AND prelim_ok = true
            """),
            {"gid": gw.id}
        )
        all_entries = res.fetchall()
        print(f"📋 Найдено предварительных билетов (prelim_ok=true): {len(all_entries)}")

        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)

        # Если вообще нет билетов — сразу фиксируем "без победителей"
        if not all_entries:
            print(f"⚠️ Для розыгрыша {gw.id} нет ни одного предварительного билета")
            # Чистим winners на всякий случай
            await s.execute(
                text("DELETE FROM winners WHERE giveaway_id = :gid"),
                {"gid": gw.id}
            )
            # Обновляем final_ok
            await s.execute(
                text("""
                    UPDATE entries
                    SET final_ok = false,
                        final_checked_at = :ts
                    WHERE giveaway_id = :gid
                """),
                {"gid": gw.id, "ts": now_utc}
            )
            gw.status = GiveawayStatus.FINISHED
            await s.commit()
            print(f"✅ Розыгрыш {gw.id} завершён без победителей (не было участников)")
            return

        # ---------- 3. Финальная проверка подписок для КАЖДОГО участника ----------
        eligible_entries = []  # [(user_id, ticket_code)]
        for row in all_entries:
            user_id = row[0]
            ticket_code = row[1]
            is_ok, debug_reason = await check_membership_on_all(bot, user_id, gw.id)
            print(
                f"   • user={user_id} ticket={ticket_code} -> "
                f"{'OK' if is_ok else 'FAIL'} ({debug_reason})"
            )

            if is_ok:
                eligible_entries.append((user_id, ticket_code))

        print(f"✅ Подтверждено участников после финальной проверки: {len(eligible_entries)}")

        # ---------- 4. Если никто не прошёл финальную проверку ----------
        if not eligible_entries:
            print(f"⚠️ Для розыгрыша {gw.id} не осталось участников, подписанных на все каналы — победителей нет")

            # Чистим winners
            await s.execute(
                text("DELETE FROM winners WHERE giveaway_id = :gid"),
                {"gid": gw.id}
            )
            # Все final_ok = false
            await s.execute(
                text("""
                    UPDATE entries
                    SET final_ok = false,
                        final_checked_at = :ts
                    WHERE giveaway_id = :gid
                """),
                {"gid": gw.id, "ts": now_utc}
            )

            gw.status = GiveawayStatus.FINISHED
            await s.commit()
            print(f"✅ Розыгрыш {gw.id} завершён без победителей (никто не прошёл финальную проверку)")
            return

        # ---------- 5. Определяем победителей из прошедших проверку ----------
        user_ids = [u for (u, _) in eligible_entries]
        winners_to_pick = min(gw.winners_count or 1, len(user_ids))
        print(f"🎲 Определяем {winners_to_pick} победителей из {len(user_ids)} участников")

        winners_tuples = deterministic_draw("giveaway_secret", gw.id, user_ids, winners_to_pick)

        # ---------- 6. Перезаписываем таблицу winners ----------
        await s.execute(
            text("DELETE FROM winners WHERE giveaway_id = :gid"),
            {"gid": gw.id}
        )

        for winner_tuple in winners_tuples:
            # ✅ РАСПАКОВЫВАЕМ КОРТЕЖ: (user_id, rank, hash_used_from_draw)
            user_id = winner_tuple[0]
            rank = winner_tuple[1] 
            hash_used_from_draw = winner_tuple[2]
            
            # Используем хэш из deterministic_draw вместо генерации нового
            await s.execute(
                text("""
                    INSERT INTO winners (giveaway_id, user_id, rank, hash_used)
                    VALUES (:gid, :uid, :rank, :hash_used)
                """),
                {"gid": gw.id, "uid": user_id, "rank": rank, "hash_used": hash_used_from_draw}
            )
            print(f"   🏅 Победитель #{rank}: user_id={user_id}")

        # ---------- 7. Обновляем final_ok: false для всех, true только для победителей ----------
        await s.execute(
            text("""
                UPDATE entries
                SET final_ok = false,
                    final_checked_at = :ts
                WHERE giveaway_id = :gid
            """),
            {"gid": gw.id, "ts": now_utc}
        )

        for winner_tuple in winners_tuples:
            user_id = winner_tuple[0]  # Извлекаем user_id из кортежа
            await s.execute(
                text("""
                    UPDATE entries
                    SET final_ok = true,
                        final_checked_at = :ts
                    WHERE giveaway_id = :gid
                    AND user_id = :uid
                """),
                {"gid": gw.id, "uid": user_id, "ts": now_utc}
            )

        # ---------- 8. Фиксируем статус розыгрыша и коммит ----------
        gw.status = GiveawayStatus.FINISHED
        await s.commit()

        print(f"✅ Розыгрыш {gw.id} успешно завершён, победителей: {len(winners_tuples)}")

    # ---------- 9. После коммита — уведомления и правки постов ----------
    try:
        await notify_organizer(giveaway_id, winners_tuples, len(eligible_entries), bot)
        print(f"✅ Организатор уведомлен для розыгрыша {giveaway_id}")
    except Exception as e:
        print(f"❌ Ошибка уведомления организатора: {e}")

    try:
        await notify_participants(giveaway_id, winners_tuples, eligible_entries, bot)
        print(f"✅ Участники уведомлены для розыгрыша {giveaway_id}")
    except Exception as e:
        print(f"❌ Ошибка уведомления участников: {e}")

    try:
        await edit_giveaway_post(giveaway_id, bot)
        print(f"✅ Посты в каналах обновлены для розыгрыша {giveaway_id}")
    except Exception as e:
        print(f"❌ Ошибка обновления постов: {e}")

    try:
        await _edit_prime_channel_post(giveaway_id, bot)
    except Exception as e:
        logging.error("❌ [PRIME] Ошибка обновления поста в PRIME-канале при финализации gid=%s: %s", giveaway_id, e)

    print(f"✅✅✅ FINALIZE_AND_DRAW_JOB ЗАВЕРШЕНА для розыгрыша {giveaway_id}")


#--- ПЕРЕОПРЕДЕЛЕНИЕ победителей для завершенного розыгрыша ---
async def redraw_winners(giveaway_id: int):
    """
    Адаптированная версия finalize_and_draw_job() без изменения статуса
    """
    print(f"🎲 REDRAW_WINNERS ► старт для розыгрыша {giveaway_id}")

    # Получаем бот из глобального контекста
    from bot import bot  # Импортируем глобальный экземпляр бота
    
    async with Session() as s:
        # ---------- 1. Загружаем розыгрыш ----------
        gw = await s.get(Giveaway, giveaway_id)
        if not gw or gw.status != GiveawayStatus.FINISHED:
            print(f"❌ Розыгрыш {giveaway_id} не найден или не завершен")
            return False

        print(f"🔍 Переопределяем победителей для розыгрыша {gw.id} «{gw.internal_title}»")

        # ---------- 2. Все участники с prelim_ok = true ----------
        res = await s.execute(
            text("""
                SELECT user_id, ticket_code
                FROM entries
                WHERE giveaway_id = :gid
                  AND prelim_ok = true
            """),
            {"gid": gw.id}
        )
        all_entries = res.fetchall()
        print(f"📋 Найдено участников для перерозыгрыша: {len(all_entries)}")

        if not all_entries:
            print(f"⚠️ Для розыгрыша {gw.id} нет участников")
            return False

        # ---------- 3. Финальная проверка подписок для КАЖДОГО участника ----------
        eligible_entries = []  # [(user_id, ticket_code)]
        for row in all_entries:
            user_id = row[0]
            ticket_code = row[1]
            is_ok, debug_reason = await check_membership_on_all(bot, user_id, gw.id)
            print(f"   • user={user_id} ticket={ticket_code} -> {'OK' if is_ok else 'FAIL'}")

            if is_ok:
                eligible_entries.append((user_id, ticket_code))

        print(f"✅ Подтверждено участников после проверки: {len(eligible_entries)}")

        if not eligible_entries:
            print(f"⚠️ Для розыгрыша {gw.id} не осталось участников, подписанных на все каналы")
            return False

        # ---------- 4. Определяем НОВЫХ победителей ----------
        user_ids = [u for (u, _) in eligible_entries]
        winners_to_pick = min(gw.winners_count or 1, len(user_ids))
        print(f"🎲 Определяем {winners_to_pick} НОВЫХ победителей из {len(user_ids)} участников")

        # Используем новый секрет для перерозыгрыша
        winners_tuples = deterministic_draw("redraw_secret_" + str(gw.id), gw.id, user_ids, winners_to_pick)

        # ---------- 5. УДАЛЯЕМ старых победителей и добавляем НОВЫХ ----------
        await s.execute(
            text("DELETE FROM winners WHERE giveaway_id = :gid"),
            {"gid": gw.id}
        )

        for winner_tuple in winners_tuples:
            user_id = winner_tuple[0]
            rank = winner_tuple[1] 
            hash_used_from_draw = winner_tuple[2]
            
            await s.execute(
                text("""
                    INSERT INTO winners (giveaway_id, user_id, rank, hash_used)
                    VALUES (:gid, :uid, :rank, :hash_used)
                """),
                {"gid": gw.id, "uid": user_id, "rank": rank, "hash_used": hash_used_from_draw}
            )
            print(f"   🏅 НОВЫЙ победитель #{rank}: user_id={user_id}")

        # ---------- 6. Обновляем final_ok: false для всех, true только для НОВЫХ победителей ----------
        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        
        await s.execute(
            text("""
                UPDATE entries
                SET final_ok = false,
                    final_checked_at = :ts
                WHERE giveaway_id = :gid
            """),
            {"gid": gw.id, "ts": now_utc}
        )

        for winner_tuple in winners_tuples:
            user_id = winner_tuple[0]
            await s.execute(
                text("""
                    UPDATE entries
                    SET final_ok = true,
                        final_checked_at = :ts
                    WHERE giveaway_id = :gid
                    AND user_id = :uid
                """),
                {"gid": gw.id, "uid": user_id, "ts": now_utc}
            )

        await s.commit()
        print(f"✅ Перерозыгрыш {gw.id} успешно выполнен, новых победителей: {len(winners_tuples)}")

    # ---------- 7. После коммита — обновляем посты и уведомления ----------
    try:
        await edit_giveaway_post(giveaway_id, bot)
        print(f"✅ Посты в каналах обновлены с новыми победителями для розыгрыша {giveaway_id}")
    except Exception as e:
        print(f"❌ Ошибка обновления постов: {e}")

    try:
        await _edit_prime_channel_post(giveaway_id, bot)
    except Exception as e:
        logging.error("❌ [PRIME] Ошибка обновления поста в PRIME-канале при перерозыгрыше gid=%s: %s", giveaway_id, e)

    try:
        await notify_redraw_organizer(giveaway_id, winners_tuples, len(eligible_entries), bot)
        print(f"✅ Организатор уведомлен о перерозыгрыше для {giveaway_id}")
    except Exception as e:
        print(f"❌ Ошибка уведомления организатора: {e}")

    try:
        await notify_redraw_participants(giveaway_id, winners_tuples, eligible_entries, bot)
        print(f"✅ Участники уведомлены о перерозыгрыше для {giveaway_id}")
    except Exception as e:
        print(f"❌ Ошибка уведомления участников: {e}")

    return True


# --- Уведомление организатора о результатах розыгрыша ---
async def notify_organizer(gid: int, winners: list, eligible_count: int, bot_instance: Bot):
    try:
        print(f"📨 Уведомляем организатора розыгрыша {gid}")
        
        async with session_scope() as s:
            gw = await s.get(Giveaway, gid)
            if not gw:
                print(f"❌ Розыгрыш {gid} не найден для уведомления организатора")
                return
            
            # Получаем username победителей
            winner_usernames = []
            for winner in winners:
                uid = winner[0]  # (uid, rank, hash)
                try:
                    user = await bot_instance.get_chat(uid)
                    username = f"@{user.username}" if user.username else f"ID: {uid}"
                    winner_usernames.append(f"{username}")
                except Exception as e:
                    winner_usernames.append(f"ID: {uid}")
                    print(f"⚠️ Не удалось получить username для {uid}: {e}")
            
            # Формируем сообщение
            if winner_usernames:
                winners_text = "\n".join([f"{i+1}. {name}" for i, name in enumerate(winner_usernames)])
                message_text = (
                    f"🎉 Розыгрыш \"{gw.internal_title}\" завершился!\n\n"
                    f"📊 Участников в финале: {eligible_count}\n"
                    f"🏆 Победителей: {len(winners)}\n\n"
                    f"Список победителей:\n{winners_text}\n\n"
                    f"Свяжитесь с победителями для вручения призов."
                )
            else:
                message_text = (
                    f"🎉 Розыгрыш \"{gw.internal_title}\" завершился!\n\n"
                    f"📊 Участников в финале: {eligible_count}\n"
                    f"🏆 Победителей: {len(winners)}\n\n"
                    "К сожалению, не удалось определить победителей."
                )
            
            # Улучшенная клавиатура с проверкой премиум-статуса
            kb = InlineKeyboardBuilder()
            
            # Проверяем статус пользователя
            user_status = await get_user_status(gw.owner_user_id)
            
            if user_status == 'premium':
                # Премиум пользователи: обе кнопки доступны
                kb.button(text="💎📥 Выгрузить CSV", callback_data=f"stats:csv:{gid}")
                kb.button(text="💎🎲 Перерозыгрыш", callback_data=f"ev:redraw:{gid}")
            else:
                # Стандартные пользователи: CSV заблокирован, перерозыгрыш тоже
                kb.button(text="🔒📥 Выгрузить CSV", callback_data=f"premium_required:{gid}")
                kb.button(text="🔒🎲 Перерозыгрыш", callback_data=f"premium_required:{gid}")
            
            kb.adjust(1)
            
            print(f"📤 Отправляем уведомление организатору {gw.owner_user_id}")
            await bot_instance.send_message(
                gw.owner_user_id, 
                message_text,
                reply_markup=kb.as_markup(),
                disable_notification=False,
            )
            print(f"✅ Организатор уведомлен")
            
    except Exception as e:
        print(f"❌ Ошибка уведомления организатора для розыгрыша {gid}: {e}")


# --- Уведомление организатора о результатах ПЕРЕРОЗЫГРЫША ---
async def notify_redraw_organizer(gid: int, winners: list, eligible_count: int, bot_instance: Bot):
    try:
        print(f"📨 Уведомляем организатора о ПЕРЕРОЗЫГРЫШЕ {gid}")
        
        async with session_scope() as s:
            gw = await s.get(Giveaway, gid)
            gw_title_link = await format_giveaway_title_link(gid, gw.internal_title)
            
            if not gw:
                print(f"❌ Розыгрыш {gid} не найден")
                return
            
            # Получаем username НОВЫХ победителей
            winner_usernames = []
            for winner in winners:
                uid = winner[0]  # (uid, rank, hash)
                try:
                    user = await bot_instance.get_chat(uid)
                    username = f"@{user.username}" if user.username else f"ID: {uid}"
                    winner_usernames.append(f"{username}")
                except Exception as e:
                    winner_usernames.append(f"ID: {uid}")
            
            # Формируем сообщение о ПЕРЕРОЗЫГРЫШЕ
            if winner_usernames:
                winners_text = "\n".join([f"{i+1}. {name}" for i, name in enumerate(winner_usernames)])
                message_text = (
                    f"🔄 <b>Перерозыгрыш завершён!</b>\n\n"
                    f'Розыгрыш: "{gw_title_link}"\n\n'
                    f"📊 Участников: {eligible_count}\n"
                    f"🏆 Новых победителей: {len(winners)}\n\n"
                    f"<b>НОВЫЙ список победителей:</b>\n{winners_text}\n\n"
                    f"<i>Свяжитесь с новыми победителями для вручения призов.</i>"
                )
            else:
                message_text = (
                    f"🔄 <b>Перерозыгрыш завершён!</b>\n\n"
                    f'Розыгрыш: "{gw_title_link}"\n\n'
                    f"📊 Участников: {eligible_count}\n"
                    f"🏆 Победителей: {len(winners)}\n\n"
                    "К сожалению, не удалось определить новых победителей."
                )
            
            # Клавиатура с проверкой премиум-статуса
            kb = InlineKeyboardBuilder()
            
            # Проверяем статус пользователя
            user_status = await get_user_status(gw.owner_user_id)
            
            if user_status == 'premium':
                # Премиум пользователи: обе кнопки доступны
                kb.button(text="💎📥 Выгрузить CSV", callback_data=f"stats:csv:{gid}")
                kb.button(text="💎🎲 Перерозыгрыш", callback_data=f"ev:redraw:{gid}")
            else:
                # Стандартные пользователи: CSV заблокирован, перерозыгрыш тоже
                kb.button(text="🔒📥 Выгрузить CSV", callback_data=f"premium_required:{gid}")
                kb.button(text="🔒🎲 Перерозыгрыш", callback_data=f"premium_required:{gid}")
            
            kb.adjust(1)
            
            await bot_instance.send_message(
                gw.owner_user_id, 
                message_text,
                reply_markup=kb.as_markup(),
                disable_notification=False,
                parse_mode="HTML",
                disable_web_page_preview=True
            )
            
    except Exception as e:
        print(f"❌ Ошибка уведомления организатора о перерозыгрыше: {e}")


# --- Уведомление всех участников о результатах розыгрыша ---
async def notify_participants(gid: int, winners: list, eligible_entries: list, bot_instance: Bot):
    try:
        print(f"📨 Уведомляем участников розыгрыша {gid}")
        
        # 🔄 ПОЛУЧАЕМ BOT_USERNAME из бота
        bot_info = await bot_instance.get_me()
        BOT_USERNAME = bot_info.username
        print(f"🔍 DEBUG: BOT_USERNAME получен: @{BOT_USERNAME}")
        
        async with session_scope() as s:
            gw = await s.get(Giveaway, gid)
            gw_title_link = await format_giveaway_title_link(gid, gw.internal_title)
            if not gw:
                print(f"❌ Розыгрыш {gid} не найден для уведомления участников")
                return
            
            winner_ids = [winner[0] for winner in winners]  # winner[0] = user_id

            print(f"🔍 Получаем билеты участников для розыгрыша {gid}")
            participant_tickets = {}
            res = await s.execute(
                text("SELECT user_id, ticket_code FROM entries WHERE giveaway_id = :gid"),
                {"gid": gid}
            )
            for row in res.all():
                participant_tickets[row[0]] = row[1]
            print(f"🔍 Найдено билетов в базе: {len(participant_tickets)}")

            # Список билетов победителей (без ников — для приватности)
            winner_tickets = []
            for winner_id in winner_ids:
                ticket = participant_tickets.get(winner_id)
                if ticket:
                    winner_tickets.append(f"🎟 <b>{ticket}</b>")
            winners_list_text = "\n".join(winner_tickets) if winner_tickets else "билеты не определены"
            
            # Уведомляем всех участников
            notified_count = 0
            for user_id, _ in eligible_entries:
                try:
                    ticket_code = participant_tickets.get(user_id, "неизвестен")
                    print(f"🔍 Участник {user_id}, билет: {ticket_code}")
                    
                    if user_id in winner_ids:
                        # Победитель
                        message_text = (
                            f"🎉 Поздравляем! Вы стали победителем в розыгрыше \"{gw_title_link}\".\n\n"
                            f"Ваш билет <b>{ticket_code}</b> оказался выбранным случайным образом.\n\n"
                            f"Организатор свяжется с вами для вручения приза."
                        )
                        
                        # 🔄 ДОБАВЛЕНО: Кнопка "Результаты" и для победителей для consistency
                        kb = InlineKeyboardBuilder()
                        url = f"https://t.me/{BOT_USERNAME}?startapp=results_{gid}"
                        kb.button(text="🎲 Результаты", url=url)
                        kb.adjust(1)
                        
                        print(f"🔍 DEBUG: Создана кнопка 'Результаты' для победителя с URL: {url}")
                        
                        await bot_instance.send_message(
                            user_id, 
                            message_text, 
                            parse_mode="HTML",
                            reply_markup=kb.as_markup(),
                            disable_notification=False,
                            disable_web_page_preview=True
                        )
                        
                    else:
                        # Участник (не победитель)
                        message_text = (
                            f"🏁 Завершился розыгрыш \"{gw_title_link}\".\n\n"
                            f"Ваш билет: <b>{ticket_code}</b>\n\n"
                            f"Мы случайным образом определили победителей и, к сожалению, "
                            f"Ваш билет не был выбран.\n\n"
                            f"Билеты победителей:\n{winners_list_text}\n\n"
                            f"Участвуйте в других розыгрышах!"
                        )
                        
                        # Кнопка "Результаты" ДЛЯ УВЕДОМЛЕНИЯ
                        # Используем ТОЧНО ТУ ЖЕ кнопку что и в опубликованном посте в каналах
                        # В уведомлениях в боте мы можем использовать URL кнопку как в каналах
                        kb = InlineKeyboardBuilder()
                        url = f"https://t.me/{BOT_USERNAME}?startapp=results_{gid}"
                        kb.button(text="🎲 Результаты", url=url)
                        kb.adjust(1)
                        
                        print(f"🔍 DEBUG: Создана кнопка 'Результаты' с URL: {url}")
                        
                        print(f"📤 Отправляем уведомление пользователю {user_id}")
                        await bot_instance.send_message(
                            user_id, 
                            message_text, 
                            parse_mode="HTML",
                            reply_markup=kb.as_markup(),
                            disable_notification=False,
                            disable_web_page_preview=True
                        )

                    notified_count += 1
                    print(f"✅ Пользователь {user_id} уведомлен")
                    
                    # Небольшая задержка чтобы не превысить лимиты Telegram
                    await asyncio.sleep(0.1)
                    
                except Exception as e:
                    print(f"⚠️ Не удалось уведомить пользователя {user_id}: {e}")
                    continue
                    
        print(f"✅ Уведомлено {notified_count} участников розыгрыша {gid}")
        
    except Exception as e:
        print(f"❌ Ошибка уведомления участников для розыгрыша {gid}: {e}")


# --- Уведомление участников о ПЕРЕРОЗЫГРЫШЕ ---
async def notify_redraw_participants(gid: int, winners: list, eligible_entries: list, bot_instance: Bot):
    try:
        print(f"📨 Уведомляем участников о ПЕРЕРОЗЫГРЫШЕ {gid}")
        
        # Получаем BOT_USERNAME
        bot_info = await bot_instance.get_me()
        BOT_USERNAME = bot_info.username
        
        async with session_scope() as s:
            gw = await s.get(Giveaway, gid)
            gw_title_link = await format_giveaway_title_link(gid, gw.internal_title)
            if not gw:
                return
            
            winner_ids = [winner[0] for winner in winners]

            # Получаем билеты участников
            participant_tickets = {}
            res = await s.execute(
                text("SELECT user_id, ticket_code FROM entries WHERE giveaway_id = :gid"),
                {"gid": gid}
            )
            for row in res.all():
                participant_tickets[row[0]] = row[1]

            # Список билетов победителей (без ников — для приватности)
            winner_tickets = []
            for winner_id in winner_ids:
                ticket = participant_tickets.get(winner_id)
                if ticket:
                    winner_tickets.append(f"🎟 <b>{ticket}</b>")
            winners_list_text = "\n".join(winner_tickets) if winner_tickets else "билеты не определены"
            
            # Уведомляем всех участников
            notified_count = 0
            for user_id, _ in eligible_entries:
                try:
                    ticket_code = participant_tickets.get(user_id, "неизвестен")
                    
                    if user_id in winner_ids:
                        # НОВЫЙ победитель
                        message_text = (
                            f"🔄 <b>Проведён перерозыгрыш!</b>\n\n"
                            f'Розыгрыш: "{gw_title_link}"\n\n'
                            f"🎉 <b>ПОЗДРАВЛЯЕМ!</b> Вы стали победителем в перерозыгрыше!\n\n"
                            f"Ваш билет <b>{ticket_code}</b> оказался выбранным случайным образом.\n\n"
                            f"Организатор свяжется с вами для вручения приза."
                        )
                    else:
                        # Участник (не победитель в перерозыгрыше)
                        message_text = (
                            f"🔄 <b>Проведён перерозыгрыш!</b>\n\n"
                            f'Розыгрыш: "{gw_title_link}"\n\n'
                            f"Ваш билет: <b>{ticket_code}</b>\n\n"
                            f"Мы случайным образом определили НОВЫХ победителей и, к сожалению, "
                            f"Ваш билет не был выбран.\n\n"
                            f"<b>Билеты победителей:</b>\n{winners_list_text}\n\n"
                            f"Участвуйте в других розыгрышах!"
                        )
                    
                    # Кнопка "Результаты"
                    kb = InlineKeyboardBuilder()
                    url = f"https://t.me/{BOT_USERNAME}?startapp=results_{gid}"
                    kb.button(text="🎲 Результаты", url=url)
                    kb.adjust(1)
                    
                    await bot_instance.send_message(
                        user_id, 
                        message_text, 
                        parse_mode="HTML",
                        reply_markup=kb.as_markup(),
                        disable_notification=False,
                        disable_web_page_preview=True
                    )
                    
                    notified_count += 1
                    await asyncio.sleep(0.1)
                    
                except Exception as e:
                    print(f"⚠️ Не удалось уведомить пользователя {user_id} о перерозыгрыше: {e}")
                    continue
                    
        print(f"✅ Уведомлено {notified_count} участников о перерозыгрыше {gid}")
        
    except Exception as e:
        print(f"❌ Ошибка уведомления участников о перерозыгрыше: {e}")


async def cancel_giveaway(gid:int, by_user_id:int, reason:str|None):
    async with session_scope() as s:
        gw = await s.get(Giveaway, gid)
        if not gw or gw.status!=GiveawayStatus.ACTIVE: return
        gw.status = GiveawayStatus.CANCELLED
        gw.cancelled_at = datetime.now(timezone.utc)
        gw.cancelled_by = by_user_id
    try:
        scheduler.remove_job(f"final_{gid}")
    except Exception:
        pass

    try:
        await _cancel_prime_channel_post(gid, bot)
    except Exception as e:
        logging.error("❌ [PRIME] Ошибка обновления поста при отмене gid=%s: %s", gid, e)


# --- Функции для редактирования постов ---
def _compose_finished_post_text(gw: Giveaway, winners: list, participants_count: int) -> str:

    lines = []

    # Добавляем описание розыгрыша если оно есть
    # ВАЖНО: public_description уже содержит HTML с премиум-эмодзи
    # НЕ используем f-string чтобы не экранировать HTML
    if gw.public_description and gw.public_description.strip():
        lines.append(gw.public_description)
        lines.append("")

    # Заголовок победителей (жирный текст)
    lines.append("<b>🎲 Розыгрыш завершен, билеты победителей определены:</b>")

    # ТОЛЬКО билеты победителей с нумерацией
    if winners:
        for winner in winners:
            rank, username, ticket_code = winner
            # Показываем номер и билет
            lines.append(f"{rank}. {ticket_code}")
    else:
        lines.append("Победители не определены, так как никто не принял участие.")

    return "\n".join(lines)


async def edit_giveaway_post(giveaway_id: int, bot_instance: Bot):
    """
    Редактирует пост розыгрыша после завершения с сохранением медиа
    УЛУЧШЕННАЯ ВЕРСИЯ: сохранение link-preview с фиолетовой рамкой
    """
    print(f"🔍 edit_giveaway_post ВХОД: giveaway_id={giveaway_id}")
    
    try:
        async with session_scope() as s:
            # Получаем данные розыгрыша
            print(f"🔍 Ищем розыгрыш {giveaway_id} в БД")
            gw = await s.get(Giveaway, giveaway_id)
            if not gw:
                print(f"❌ Розыгрыш {giveaway_id} не найден")
                return False
            
            print(f"🔍 Розыгрыш найден: '{gw.internal_title}', статус: {gw.status}")

            # Получаем количество участников
            print(f"🔍 Ищем количество участников для розыгрыша {giveaway_id}")
            # 🔧 ИСПРАВЛЕНИЕ: Используем prelim_ok вместо final_ok
            participants_res = await s.execute(
                text("SELECT COUNT(DISTINCT user_id) FROM entries WHERE giveaway_id = :gid AND prelim_ok = true"),
                {"gid": giveaway_id}
            )
            participants_count = participants_res.scalar_one() or 0
            print(f"🔍 Участников в финале: {participants_count}")

            # Получаем победителей
            print(f"🔍 Ищем победителей для розыгрыша {giveaway_id}")
            winners_res = await s.execute(
                stext("""
                    SELECT w.rank, COALESCE(u.username, 'Участник') as username, e.ticket_code 
                    FROM winners w
                    LEFT JOIN entries e ON e.giveaway_id = w.giveaway_id AND e.user_id = w.user_id
                    LEFT JOIN users u ON u.user_id = w.user_id
                    WHERE w.giveaway_id = :gid
                    ORDER BY w.rank
                """),
                {"gid": giveaway_id}
            )
            winners = winners_res.all()
            print(f"🔍 Найдено победителей: {len(winners)}")

            # Получаем прикрепленные каналы и message_id постов
            print(f"🔍 Ищем посты для редактирования (chat_id + message_id)")
            channels_res = await s.execute(
                stext("SELECT chat_id, message_id FROM giveaway_channels WHERE giveaway_id = :gid AND message_id IS NOT NULL"),
                {"gid": giveaway_id}
            )
            channels = channels_res.all()
            
            print(f"🔍 Найдено каналов с постами: {len(channels)}")
            for chat_id, message_id in channels:
                print(f"   - Чат {chat_id}, message_id {message_id}")
            
            if not channels:
                print(f"⚠️ Нет постов для редактирования у розыгрыша {giveaway_id}")
                return False
            
            # Формируем новый текст поста с жирным форматированием
            new_text = _compose_finished_post_text(gw, winners, participants_count)
            print(f"🔍 Сформирован новый текст поста (длина: {len(new_text)} символов)")
            
            # Определяем тип медиа для розыгрыша
            media_type, media_file_id = unpack_media(gw.photo_file_id)
            has_media = media_file_id is not None
            print(f"🔍 Тип медиа в розыгрыше: {media_type}, file_id: {media_file_id is not None}, has_media: {has_media}")
            
            # Подготавливаем link-preview URL для медиа
            preview_url = None
            if has_media and media_file_id:
                try:
                    print(f"🔍 Подготавливаем link-preview URL для медиа...")
                    # Подбираем имя файла под тип
                    if media_type == "photo":
                        suggested = "image.jpg"
                    elif media_type == "animation":
                        suggested = "animation.mp4"
                    elif media_type == "video":
                        suggested = "video.mp4"
                    else:
                        suggested = "file.bin"

                    # Выгружаем из TG в S3 и собираем наш preview_url (как при публикации)
                    key, s3_url = await file_id_to_public_url_via_s3(bot_instance, media_file_id, suggested)
                    preview_url = _make_preview_url(key, gw.internal_title or "", gw.public_description or "")
                    print(f"🔍 Link-preview URL подготовлен: {preview_url}")
                    
                except Exception as url_error:
                    print(f"❌ Ошибка подготовки link-preview URL: {url_error}")
                    preview_url = None
            
            # Редактируем посты во всех каналах
            success_count = 0
            for chat_id, message_id in channels:
                try:
                    print(f"🔍 Редактируем пост в чате {chat_id}, message_id {message_id}")
                    
                    # Определяем тип чата для правильной кнопки
                    is_channel = str(chat_id).startswith("-100")
                    print(f"🔍 Тип чата: {'канал' if is_channel else 'группа/личный чат'}")
                    
                    # Используем ПРАВИЛЬНУЮ клавиатуру
                    reply_markup = kb_finished_giveaway(giveaway_id, for_channel=is_channel)
                    print(f"🔍 Клавиатура: {reply_markup}")
                    
                    # ОЧИСТКА ТЕКСТА ОТ ПОЛЬЗОВАТЕЛЬСКИХ ПРЕВЬЮ
                    has_media = bool(media_file_id)
                    cleaned_text, disable_preview = text_preview_cleaner.clean_text_preview(new_text, has_media)
                    
                    # РАЗДЕЛЕНИЕ ЛОГИКИ с link-preview
                    if has_media and preview_url:
                        print(f"🔍 Розыгрыш ИМЕЕТ медиа, используем link-preview с рамкой")
                        try:
                            # cleaned_text — это HTML после clean_text_preview
                            hidden_link = f'<a href="{preview_url}">&#8203;</a>'

                            media_position = gw.media_position if hasattr(gw, "media_position") else "bottom"
                            if media_position == "top":
                                full_html_with_preview = hidden_link + "\n" + cleaned_text
                            else:
                                full_html_with_preview = cleaned_text + "\n\n" + hidden_link

                            lp = LinkPreviewOptions(
                                is_disabled=False,
                                prefer_large_media=True,
                                prefer_small_media=False,
                                show_above_text=(media_position == "top"),
                                url=preview_url,
                            )

                            await bot_instance.edit_message_text(
                                chat_id=chat_id,
                                message_id=message_id,
                                text=full_html_with_preview,
                                parse_mode="HTML",
                                link_preview_options=lp,
                                reply_markup=reply_markup,
                            )

                            print(f"✅ Пост С LINK-PREVIEW отредактирован в чате {chat_id}")
                            success_count += 1
                            
                        except Exception as preview_error:
                            print(f"❌ Ошибка edit_message_text с link-preview: {preview_error}")
                            
                            # 🔄 Fallback: переотправляем весь пост с link-preview
                            print(f"🔍 Переотправляем пост с link-preview...")
                            try:
                                # Удаляем старый пост
                                try:
                                    await bot_instance.delete_message(chat_id=chat_id, message_id=message_id)
                                    print(f"🔍 Старый пост удален")
                                except Exception as delete_error:
                                    print(f"⚠️ Не удалось удалить старый пост: {delete_error}")
                                
                                # Формируем текст с hidden link для link-preview
                                hidden_link = f'<a href="{preview_url}">&#8203;</a>'
                                full_text_with_preview = cleaned_text + "\n\n" + hidden_link
                                
                                # Настройки link-preview
                                lp = LinkPreviewOptions(
                                    is_disabled=False,
                                    prefer_large_media=True,
                                    prefer_small_media=False,
                                    show_above_text=False,
                                )
                                
                                # Отправляем новый пост с link-preview
                                # ЕСЛИ ЕСТЬ МЕДИА - НИКОГДА НЕ ОТКЛЮЧАЕМ ПРЕВЬЮ!
                                await bot_instance.send_message(
                                    chat_id=chat_id,
                                    text=full_text_with_preview,
                                    parse_mode="HTML",
                                    link_preview_options=lp,
                                    reply_markup=reply_markup
                                )
                                
                                print(f"✅ Пост С LINK-PREVIEW переотправлен в чате {chat_id}")
                                success_count += 1
                                
                            except Exception as resend_error:
                                print(f"❌ Ошибка переотправки поста с link-preview: {resend_error}")
                    
                    elif has_media and not preview_url:
                        print(f"🔍 Розыгрыш ИМЕЕТ медиа, но нет preview_url, пробуем edit_message_caption")
                        try:
                            send_kwargs = {
                                "chat_id": chat_id,
                                "message_id": message_id,
                                "caption": cleaned_text,
                                "parse_mode": "HTML",
                                "reply_markup": reply_markup,
                            }
                            await bot_instance.edit_message_caption(**send_kwargs)
                            print(f"✅ Пост С МЕДИА отредактирован (caption) в чате {chat_id}")
                            success_count += 1
                            
                        except Exception as caption_error:
                            print(f"❌ Ошибка edit_message_caption: {caption_error}")
                    
                    else:
                        print(f"🔍 Розыгрыш БЕЗ медиа, используем edit_message_text")
                        send_kwargs = {
                            "chat_id": chat_id,
                            "message_id": message_id,
                            "text": cleaned_text,
                            "parse_mode": "HTML",
                            "reply_markup": reply_markup,
                        }

                        if disable_preview:
                            send_kwargs["disable_web_page_preview"] = True

                        await bot_instance.edit_message_text(**send_kwargs)
                        print(f"✅ Пост БЕЗ МЕДИА отредактирован в чате {chat_id}")
                        success_count += 1
                    
                except Exception as e:
                    print(f"❌ Ошибка редактирования поста в {chat_id}: {e}")
                    # ... существующий код обработки ошибок ...
            
            print(f"📊 Итог: успешно отредактировано {success_count} из {len(channels)} постов")
            return success_count > 0
                    
    except Exception as e:
        print(f"🚨 Критическая ошибка в edit_giveaway_post: {e}")
        import traceback
        print(f"TRACEBACK: {traceback.format_exc()}")
        return False
    
# ============================================================================
# CSV EXPORT FUNCTIONS
# ============================================================================

async def is_giveaway_organizer(user_id: int, giveaway_id: int) -> bool:
    """Проверяет, является ли пользователь организатором розыгрыша"""
    try:
        async with session_scope() as s:
            gw = await s.get(Giveaway, giveaway_id)
            return gw and gw.owner_user_id == user_id
    except Exception as e:
        logging.error(f"Ошибка проверки организатора: {e}")
        return False

async def get_participant_count(giveaway_id: int) -> int:
    """Получает количество участников розыгрыша"""
    try:
        async with session_scope() as s:
            result = await s.execute(
                text("SELECT COUNT(*) FROM entries WHERE giveaway_id = :gid"),
                {"gid": giveaway_id}
            )
            return result.scalar_one() or 0
    except Exception as e:
        logging.error(f"Ошибка получения количества участников: {e}")
        return 0

async def get_giveaway_title(giveaway_id: int) -> str:
    """Получает название розыгрыша для имени файла"""
    try:
        async with session_scope() as s:
            gw = await s.get(Giveaway, giveaway_id)
            if gw:
                # Очищаем название от недопустимых символов
                title = gw.internal_title
                # Заменяем пробелы на подчеркивания и удаляем спецсимволы
                safe_title = "".join(c if c.isalnum() or c in " _-" else "_" for c in title)
                safe_title = safe_title.replace(" ", "_")
                return safe_title[:50]  # Ограничиваем длину
    except Exception as e:
        logging.error(f"Ошибка получения названия розыгрыша: {e}")
    return f"розыгрыш_{giveaway_id}"

async def fetch_csv_data(giveaway_id: int):
    """Получает данные для CSV из PostgreSQL"""
    try:
        async with session_scope() as s:
            # 🔧 ИСПРАВЛЕННЫЙ SQL ДЛЯ POSTGRESQL
            query = text("""
                SELECT 
                    ROW_NUMBER() OVER (ORDER BY e.prelim_checked_at) as participant_number,
                    e.ticket_code,
                    e.user_id,
                    COALESCE(u.username, 'нет_никнейма') as username,
                    CASE 
                        WHEN w.user_id IS NOT NULL THEN 'победитель' 
                        ELSE 'участник' 
                    END as status,
                    COALESCE(w.rank::text, '') as winner_rank
                FROM entries e
                LEFT JOIN users u ON u.user_id = e.user_id
                LEFT JOIN winners w ON w.giveaway_id = e.giveaway_id 
                    AND w.user_id = e.user_id
                WHERE e.giveaway_id = :gid
                ORDER BY e.prelim_checked_at
            """)
            
            result = await s.execute(query, {"gid": giveaway_id})
            return result.fetchall()
            
    except Exception as e:
        logging.error(f"Ошибка получения данных для CSV: {e}")
        return []

async def generate_csv_in_memory(giveaway_id: int):
    """
    Генерирует CSV файл в памяти с потоковой записью.
    Возвращает BufferedInputFile для отправки через Telegram.
    """
    import csv
    import io
    import asyncio
    
    output = None
    writer = None
    
    try:
        # 1. Получаем данные
        data = await fetch_csv_data(giveaway_id)
        if not data:
            raise ValueError("Нет данных для экспорта")
        
        # 2. Создаем StringIO буфер
        output = io.StringIO()
        writer = csv.writer(output, delimiter=';', quoting=csv.QUOTE_MINIMAL)
        
        # 3. Заголовки (используем русские, Excel поймет с BOM)
        writer.writerow(['№ участника', 'Номер билета', 'ID пользователя', 'Никнейм', 'Статус', 'Место'])
        
        # 4. Потоковая запись данных
        rows_written = 0
        for row in data:
            writer.writerow([
                row.participant_number,
                row.ticket_code,
                row.user_id,
                row.username,
                row.status,
                row.winner_rank
            ])
            rows_written += 1
            
            # Периодически даем контроль другим задачам
            if rows_written % 100 == 0:
                await asyncio.sleep(0.001)
        
        # 5. Конвертируем в bytes с BOM для корректного открытия в Excel
        csv_content = output.getvalue()
        # UTF-8 с BOM для Excel
        csv_bytes = csv_content.encode('utf-8-sig')
        
        # 6. Получаем имя файла
        title = await get_giveaway_title(giveaway_id)
        filename = f"{title}_{giveaway_id}.csv"
        
        # 7. Создаем BufferedInputFile для Telegram
        from aiogram.types import BufferedInputFile
        return BufferedInputFile(csv_bytes, filename=filename)
        
    except Exception as e:
        logging.error(f"Ошибка генерации CSV: {e}")
        raise
    finally:
        # КРИТИЧЕСКИ ВАЖНО: Явная очистка памяти
        if output:
            output.close()
        if writer:
            del writer
        
        # Принудительная сборка мусора
        import gc
        gc.collect()

#--- Обработчик членов канала / группы ---
@dp.my_chat_member()
async def on_my_chat_member(event: ChatMemberUpdated):
    """
    Срабатывает, когда бота добавили или удалили из чата/канала.
    Ключевое изменение: сохраняем канал ТОЛЬКО для пользователя, который добавил бота.
    """
    chat = event.chat
    bot_id = event.new_chat_member.user.id
    if bot_id != (await bot.get_me()).id:
        return  # событие не для нас

    # Важно: используем from_user.id - того, кто совершил действие с ботом
    user_id = event.from_user.id if event.from_user else 0
    if user_id == 0:
        return  # не можем определить кто добавил бота

    status = event.new_chat_member.status
    title = chat.title or getattr(chat, "full_name", None) or "Без названия"
    username = getattr(chat, "username", None)
    
    # ПРАВИЛЬНОЕ ОПРЕДЕЛЕНИЕ ТИПА ЧАТА
    if chat.type == "channel":
        is_private = 0 if username else 1
    else:
        # Для групп и супергрупп
        is_private = 1  # Группы всегда считаем приватными

    async with Session() as s:
        async with s.begin():
            if status in ("administrator", "member"):
                # Используем единую функцию сохранения
                await save_channel_for_user(
                    user_id=user_id,
                    chat_id=chat.id,
                    title=title,
                    username=username,
                    chat_type=chat.type,
                    bot_role=status
                )
            else:
                # если бота удалили из чата - помечаем только для этого пользователя
                async with Session() as s:
                    async with s.begin():
                        await s.execute(
                            stext("UPDATE organizer_channels SET status='gone' WHERE owner_user_id=:user_id AND chat_id=:chat_id"),
                            {"user_id": user_id, "chat_id": chat.id},  # ✅ ИСПРАВЛЕНО
                        )

    logging.info(f"🔁 my_chat_member: user={user_id}, chat={chat.title} ({chat.id}) -> {status}")

# ── Telegram Stars: pre-checkout ─────────────────────────────────────────
@dp.pre_checkout_query()
async def handle_pre_checkout(pcq: PreCheckoutQuery):
    """
    Telegram требует ответа в течение 10 секунд.
    Всегда подтверждаем — финальная проверка будет в successful_payment.
    """
    await pcq.answer(ok=True)


# ── Telegram Stars: successful_payment ───────────────────────────────────
@dp.message(F.successful_payment)
async def handle_successful_payment(message: Message):
    """
    Активирует топ-размещение после успешной оплаты Stars.
    """
    payment     = message.successful_payment
    raw_payload = payment.invoice_payload

    try:
        payload = json.loads(raw_payload)
    except Exception:
        logging.error(f"[STARS] Невалидный payload: {raw_payload}")
        return

    payload_type = payload.get("type")

    # ── bot_promotion ─────────────────────────────────────────────────────
    if payload_type == "bot_promotion":
        giveaway_id  = payload["giveaway_id"]
        publish_type = payload.get("publish_type", "immediate")
        scheduled_at = payload.get("scheduled_at")  # ISO string или None
        user_id      = payload["user_id"]
        charge_id    = payment.telegram_payment_charge_id
        stars_amount = payment.total_amount

        scheduled_dt = None
        if publish_type == "scheduled" and scheduled_at:
            try:
                scheduled_dt = datetime.fromisoformat(scheduled_at.replace("Z", "+00:00"))
            except Exception:
                scheduled_dt = None

        async with Session() as s:
            await s.execute(
                stext("""
                    INSERT INTO bot_promotions
                        (giveaway_id, owner_user_id, status, payment_method,
                         payment_status, price_stars, publish_type, scheduled_at)
                    VALUES (:gid, :uid, 'pending', 'stars', 'paid', :stars, :ptype, :sched)
                """),
                {
                    "gid":   giveaway_id,
                    "uid":   user_id,
                    "stars": stars_amount,
                    "ptype": publish_type,
                    "sched": scheduled_dt,
                }
            )
            await s.commit()

        # Уведомляем владельца бота о новой заявке
        try:
            time_label_owner = (
                "сразу после утверждения"
                if publish_type == "immediate"
                else f"в {scheduled_dt.strftime('%d.%m.%Y %H:%M')} (МСК)"
                if scheduled_dt else "сразу после утверждения"
            )
            await bot.send_message(
                chat_id=BOT_OWNER_ID,
                text=(
                    f"📣 <b>Новая заявка на продвижение!</b>\n\n"
                    f"Розыгрыш: <b>#{giveaway_id}</b>\n"
                    f"От пользователя: <b>{user_id}</b>\n"
                    f"Оплата: Stars ⭐ ({stars_amount})\n"
                    f"Время публикации: {time_label_owner}\n\n"
                    f"Перейди в /admin → Управление сервисами → 📣 Продвижение в боте → Заявки на продвижение"
                ),
                parse_mode="HTML"
            )
        except Exception as e:
            logging.warning(f"[STARS] Не удалось уведомить владельца: {e}")

        logging.info(
            f"[STARS] bot_promotion создан: giveaway={giveaway_id}, "
            f"publish_type={publish_type}, scheduled_at={scheduled_at}, "
            f"user={user_id}, charge_id={charge_id}"
        )

        time_label = (
            "сразу после утверждения администратором (до 8 часов)"
            if publish_type == "immediate"
            else f"в запланированное время: {scheduled_dt.strftime('%d.%m.%Y %H:%M')} (МСК)"
            if scheduled_dt else "сразу после утверждения"
        )

        try:
            await bot.send_message(
                chat_id=user_id,
                text=(
                    f"✅ <b>Заявка на продвижение принята!</b>\n\n"
                    f"Розыгрыш <b>#{giveaway_id}</b> будет опубликован в боте {time_label}.\n\n"
                    f"Ожидайте уведомления после публикации."
                ),
                parse_mode="HTML"
            )
        except Exception as e:
            logging.warning(f"[STARS] Не удалось уведомить пользователя {user_id}: {e}")
        return

    if payload_type != "top_placement":
        return

    giveaway_id = payload["giveaway_id"]
    period      = payload["period"]
    user_id     = payload["user_id"]
    charge_id   = payment.telegram_payment_charge_id

    now_utc = datetime.now(timezone.utc)
    days    = 1 if period == "day" else 7
    ends_at = now_utc + timedelta(days=days)

    async with Session() as s:
        await s.execute(
            stext("UPDATE top_placements SET is_active = false WHERE giveaway_id = :gid"),
            {"gid": giveaway_id}
        )
        order_result = await s.execute(
            stext("""
                INSERT INTO service_orders
                    (giveaway_id, owner_user_id, service_type, status, price_rub)
                VALUES (:gid, :uid, 'top_placement', 'paid', 0)
                RETURNING id
            """),
            {"gid": giveaway_id, "uid": user_id}
        )
        order_id = order_result.scalar_one()
        await s.execute(
            stext("""
                INSERT INTO top_placements
                    (giveaway_id, order_id, starts_at, ends_at, placement_type, is_active)
                VALUES (:gid, :oid, :starts, :ends, :ptype, true)
            """),
            {
                "gid":    giveaway_id,
                "oid":    order_id,
                "starts": now_utc,
                "ends":   ends_at,
                "ptype":  period,
            }
        )
        await s.commit()

    logging.info(
        f"[STARS] Топ активирован: giveaway={giveaway_id}, period={period}, "
        f"user={user_id}, charge_id={charge_id}"
    )

    period_label = "1 день" if period == "day" else "1 неделю"
    ends_str     = ends_at.strftime("%d.%m.%Y %H:%M")
    try:
        await bot.send_message(
            chat_id=user_id,
            text=(
                f"✅ <b>Топ-размещение активировано!</b>\n\n"
                f"Розыгрыш <b>#{giveaway_id}</b> добавлен в топ на {period_label}.\n"
                f"Размещение действует до <b>{ends_str} UTC</b>.\n\n"
                f"Участники увидят его в разделе «Главная»."
            ),
            parse_mode="HTML"
        )
    except Exception as e:
        logging.warning(f"[STARS] Не удалось уведомить пользователя {user_id}: {e}")

# --- Обработчик для любых сообщений для диагностики ---
@dp.message()
async def catch_all_messages(m: Message):
    """Перехватывает все сообщения для диагностики"""
    # Логируем неперехваченные сообщения
    logging.info(f"🔍 UNHANDLED MESSAGE: text={m.text}, chat_type={m.chat.type}, user_id={m.from_user.id}")
    
    # Если это сообщение с кнопками выбора чата, но не обработано
    if m.text in [BTN_ADD_CHANNEL, BTN_ADD_GROUP]:
        logging.info(f"🔍 CHAT_SELECTION_BUTTON_PRESSED: {m.text}")
        await m.answer(f"Кнопка '{m.text}' нажата, но не обработана. Показываю выбор...")
        await m.answer("Выберите чат:", reply_markup=chooser_reply_kb())

# --- Функции показа постов в "Мои розыгрыши" ---
async def show_participant_giveaway_post(message: Message, giveaway_id: int, giveaway_type: str):
    """
    Показывает пост розыгрыша для участника
    giveaway_type: "active" - активный, "finished" - завершенный
    """
    async with session_scope() as s:
        gw = await s.get(Giveaway, giveaway_id)
        if not gw:
            await message.answer("Розыгрыш не найден.")
            return

    # Формируем текст поста
    if giveaway_type == "active":
        # Для активного розыгрыша - текст как при публикации
        end_at_msk_dt = gw.end_at_utc.astimezone(MSK_TZ)
        end_at_msk_str = end_at_msk_dt.strftime("%H:%M %d.%m.%Y")
        
        # Вычисляем дни
        now_msk = datetime.now(MSK_TZ).date()
        end_at_date = end_at_msk_dt.date()
        days_left = max(0, (end_at_date - now_msk).days)

        post_text = _compose_post_text(
            "",
            gw.winners_count,
            desc_html=(gw.public_description or ""),
            end_at_msk=end_at_msk_str,
            days_left=days_left,
        )
        
        # 🔄 ИСПРАВЛЕНИЕ: Используем ТОЧНО ТАКУЮ ЖЕ клавиатуру как в каналах
        # В каналах используется URL кнопка с startapp параметром
        reply_markup = kb_public_participate(giveaway_id, for_channel=True)
        
    else:  # finished
        # Для завершенного розыгрыша - текст как после редактирования
        # Получаем количество участников и победителей
        async with session_scope() as s:
            participants_res = await s.execute(
                stext("SELECT COUNT(DISTINCT user_id) FROM entries WHERE giveaway_id = :gid AND final_ok = true"),
                {"gid": giveaway_id}
            )
            participants_count = participants_res.scalar_one() or 0

            winners_res = await s.execute(
                stext("""
                    SELECT w.rank, COALESCE(u.username, 'Участник') as username, e.ticket_code 
                    FROM winners w
                    LEFT JOIN entries e ON e.giveaway_id = w.giveaway_id AND e.user_id = w.user_id
                    LEFT JOIN users u ON u.user_id = w.user_id
                    WHERE w.giveaway_id = :gid
                    ORDER BY w.rank
                """),
                {"gid": giveaway_id}
            )
            winners = winners_res.all()

        # Формируем текст завершенного поста
        post_text = _compose_finished_post_text(gw, winners, participants_count)
        
        # 🔄 ИСПРАВЛЕНИЕ: Используем ТОЧНО ТАКУЮ ЖЕ клавиатуру как в каналах
        # В каналах используется URL кнопка с startapp параметром
        reply_markup = kb_finished_giveaway(giveaway_id, for_channel=True)

    # Добавляем кнопку "Назад"
    reply_markup = add_back_button(reply_markup, "close_message")

    # Определяем тип медиа
    kind, fid = unpack_media(gw.photo_file_id)

    # Пытаемся отправить с link-preview (как в каналах)
    if fid:
        try:
            # Подготавливаем link-preview URL
            if kind == "photo":
                suggested = "image.jpg"
            elif kind == "animation":
                suggested = "animation.mp4"
            elif kind == "video":
                suggested = "video.mp4"
            else:
                suggested = "file.bin"

            key, s3_url = await file_id_to_public_url_via_s3(bot, fid, suggested)
            preview_url = _make_preview_url(key, gw.internal_title or "", gw.public_description or "")

            # 🔄 ИСПРАВЛЕНИЕ: Определяем hidden_link ПЕРЕД использованием
            hidden_link = f'<a href="{preview_url}"> </a>'
            
            # Используем сохраненную позицию медиа
            media_position = gw.media_position if hasattr(gw, 'media_position') else 'bottom'
            
            if media_position == "top":
                full_text = hidden_link + "\n" + post_text
            else:
                full_text = post_text + "\n\n" + hidden_link

            lp = LinkPreviewOptions(
                is_disabled=False,
                prefer_large_media=True,
                prefer_small_media=False,
                show_above_text=(media_position == "top"),
                url=preview_url
            )

            # Отправляем с link-preview
            await message.answer(
                full_text,
                link_preview_options=lp,
                parse_mode="HTML",
                reply_markup=reply_markup
            )
            return

        except Exception as e:
            print(f"⚠️ Link-preview не сработал: {e}")
            # Fallback к обычному способу

    # Fallback: отправляем нативно
    if kind == "photo" and fid:
        await message.answer_photo(fid, caption=post_text, reply_markup=reply_markup, parse_mode="HTML")
    elif kind == "animation" and fid:
        await message.answer_animation(fid, caption=post_text, reply_markup=reply_markup, parse_mode="HTML")
    elif kind == "video" and fid:
        await message.answer_video(fid, caption=post_text, reply_markup=reply_markup, parse_mode="HTML")
    else:
        # Для постов без медиа - проверяем пользовательские ссылки
        has_media = bool(fid)
        cleaned_text, disable_preview = text_preview_cleaner.clean_text_preview(post_text, has_media)
        
        send_kwargs = {
            "text": cleaned_text,
            "parse_mode": "HTML",
            "reply_markup": reply_markup
        }
        if disable_preview:
            send_kwargs["disable_web_page_preview"] = True
            
        await message.answer(**send_kwargs)


# --- ФУНКЦИИ СТАТИСТИКИ ДЛЯ СОЗДАТЕЛЯ (Показывает статистику завершенного розыгрыша КАК НОВОЕ СООБЩЕНИЕ) ---

async def show_finished_stats(message: Message, giveaway_id: int, user_id: int | None = None):
    # Явно передаем user_id или используем из message
    if user_id is None:
        user_id = message.from_user.id
    
    logging.info(f"🔍 [DIAGNOSTICS] show_finished_stats: user_id={user_id}, giveaway_id={giveaway_id}")
    
    async with session_scope() as s:
        # Получаем данные розыгрыша
        gw = await s.get(Giveaway, giveaway_id)
        if not gw:
            await message.answer("Розыгрыш не найден.")
            return

        # Проверяем статус пользователя НАПРЯМУЮ из БД
        bot_user = await s.get(BotUser, user_id)  # 🔥 Используем переданный user_id
        if bot_user:
            logging.info(f"🔍 [DIAGNOSTICS] Статус из БД напрямую: {bot_user.user_status}")
        else:
            logging.info(f"🔍 [DIAGNOSTICS] Пользователь не найден в bot_users")

        # Количество уникальных участников, прошедших предварительную проверку
        participants_res = await s.execute(
            stext("SELECT COUNT(DISTINCT user_id) FROM entries WHERE giveaway_id = :gid AND prelim_ok = true"),
            {"gid": giveaway_id}
        )
        participants_count = participants_res.scalar_one() or 0

        # Общее количество выданных билетов
        tickets_res = await s.execute(
            stext("SELECT COUNT(*) FROM entries WHERE giveaway_id=:gid"),
            {"gid": giveaway_id}
        )
        tickets_count = tickets_res.scalar_one() or 0

        # Количество победителей
        winners_count = gw.winners_count

        # Список победителей
        winners_res = await s.execute(
            stext("""
                SELECT w.rank, COALESCE(u.username, 'Участник') as username, e.ticket_code 
                FROM winners w
                LEFT JOIN entries e ON e.giveaway_id = w.giveaway_id AND e.user_id = w.user_id
                LEFT JOIN users u ON u.user_id = w.user_id
                WHERE w.giveaway_id = :gid
                ORDER BY w.rank
            """),
            {"gid": giveaway_id}
        )
        winners = winners_res.all()

    # Формируем текст статистики
    text = (
        f"📊 <b>Статистика розыгрыша</b>\n\n"
        f"<b>Количество участников:</b> <code>{participants_count}</code>\n"
        f"<b>Число выданных билетов:</b> <code>{tickets_count}</code>\n"
        f"<b>Число победителей:</b> <code>{winners_count}</code>\n\n"
        f"<b>Список победителей:</b>\n"
    )

    if winners:
        for rank, username, ticket_code in winners:
            display_name = f"@{username}" if username and username != "Участник" else "Участник"
            text += f"{rank}. {display_name} - {ticket_code}\n"
    else:
        text += "Победители не определены\n"

    # Создаем клавиатуру с кнопкой "Назад" которая удаляет сообщение
    kb = InlineKeyboardBuilder()
    
    # Получаем статус пользователя для динамической кнопки
    user_status = await get_user_status(user_id)
    
    # ДОБАВЛЯЕМ ДИАГНОСТИКУ
    logging.info(f"🔍 [DIAGNOSTICS] get_user_status вернул: {user_status}")
    logging.info(f"🔍 [DIAGNOSTICS] giveaway_id для кнопки: {giveaway_id}")
    
    if user_status == 'premium':
        # Premium пользователи видят кнопку с алмазом
        callback_data = f"stats:csv:{giveaway_id}"
        kb.button(text="💎📥 Выгрузить CSV", callback_data=callback_data)
        logging.info(f"🔍 [DIAGNOSTICS] Создана PREMIUM кнопка: {callback_data}")
    else:
        # Standard пользователи видят заблокированную кнопку
        callback_data = f"premium_required:{giveaway_id}"
        kb.button(text="🔒📥 Выгрузить CSV", callback_data=callback_data)
        logging.info(f"🔍 [DIAGNOSTICS] Создана STANDARD кнопка: {callback_data}")
    
    kb.button(text="⬅️ Назад", callback_data="close_message")
    kb.adjust(1)

    # Отправляем как новое сообщение
    await message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")

# --- Показывает статистику активного розыгрыша КАК НОВОЕ СООБЩЕНИЕ ---
async def show_active_stats(message: Message, giveaway_id: int, user_id: int | None = None):
    # Явно передаем user_id или используем из message
    if user_id is None:
        user_id = message.from_user.id
    
    logging.info(f"🔍 [DIAGNOSTICS] show_active_stats: user_id={user_id}, giveaway_id={giveaway_id}")
    
    async with session_scope() as s:
        # Получаем данные розыгрыша
        gw = await s.get(Giveaway, giveaway_id)
        if not gw:
            await message.answer("Розыгрыш не найден.")
            return

        # Проверяем статус пользователя НАПРЯМУЮ из БД
        bot_user = await s.get(BotUser, user_id)
        if bot_user:
            logging.info(f"🔍 [DIAGNOSTICS] Статус из БД напрямую: {bot_user.user_status}")
        else:
            logging.info(f"🔍 [DIAGNOSTICS] Пользователь не найден в bot_users")

        # Количество уникальных участников, прошедших предварительную проверку
        participants_res = await s.execute(
            stext("SELECT COUNT(DISTINCT user_id) FROM entries WHERE giveaway_id = :gid AND prelim_ok = true"),
            {"gid": giveaway_id}
        )
        participants_count = participants_res.scalar_one() or 0

        # Общее количество выданных билетов
        tickets_res = await s.execute(
            stext("SELECT COUNT(*) FROM entries WHERE giveaway_id=:gid"),
            {"gid": giveaway_id}
        )
        tickets_count = tickets_res.scalar_one() or 0

        # Количество победителей (планируемое)
        winners_count = gw.winners_count

        # Подключенные каналы/группы
        channels_res = await s.execute(
            stext("""
                SELECT gc.title, oc.username, gc.chat_id
                FROM giveaway_channels gc
                LEFT JOIN organizer_channels oc ON oc.id = gc.channel_id
                WHERE gc.giveaway_id = :gid
                ORDER BY gc.id
            """),
            {"gid": giveaway_id}
        )
        channels = channels_res.all()

    # Формируем текст статистики
    text = (
        f"📊 <b>Статистика розыгрыша</b>\n\n"
        f"<b>Количество участников:</b> <code>{participants_count}</code>\n"
        f"<b>Число выданных билетов:</b> <code>{tickets_count}</code>\n"
        f"<b>Число победителей:</b> <code>{winners_count}</code>\n\n"
        f"<b>Подключенные каналы / группы к розыгрышу:</b>\n"
    )

    if channels:
        for title, username, chat_id in channels:
            if username:
                text += f"• <a href=\"https://t.me/{username}\">{title}</a>\n"
            else:
                text += f"• {title}\n"
    else:
        text += "Нет подключенных каналов\n"

    # Создаем клавиатуру с кнопкой "Назад" которая удаляет сообщение
    kb = InlineKeyboardBuilder()
    
    # Получаем статус пользователя для динамической кнопки
    user_status = await get_user_status(user_id)
    
    # ДИАГНОСТИКА
    logging.info(f"🔍 [DIAGNOSTICS] get_user_status вернул: {user_status}")
    logging.info(f"🔍 [DIAGNOSTICS] giveaway_id для кнопки: {giveaway_id}")
    
    if user_status == 'premium':
        # Premium пользователи видят кнопку с алмазом
        callback_data = f"stats:csv:{giveaway_id}"
        kb.button(text="💎📥 Выгрузить CSV", callback_data=callback_data)
        logging.info(f"🔍 [DIAGNOSTICS] Создана PREMIUM кнопка: {callback_data}")
    else:
        # Standard пользователи видят заблокированную кнопку
        callback_data = f"premium_required:{giveaway_id}"
        kb.button(text="🔒📥 Выгрузить CSV", callback_data=callback_data)
        logging.info(f"🔍 [DIAGNOSTICS] Создана STANDARD кнопка: {callback_data}")
    
    kb.button(text="⬅️ Назад", callback_data="close_message")
    kb.adjust(1)

    # Отправляем как новое сообщение
    await message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")


# --- ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ДЛЯ ДОБАВЛЕНИЯ КНОПКИ "НАЗАД" в "Мои розыгрыши" ---
def add_back_button(existing_markup: InlineKeyboardMarkup, back_callback: str) -> InlineKeyboardMarkup:
    # Создаем новый билдер
    kb = InlineKeyboardBuilder()
    # Копируем существующие кнопки
    for row in existing_markup.inline_keyboard:
        kb.row(*row)
    # Добавляем кнопку "Назад" (всегда close_message)
    kb.button(text="⬅️ Назад", callback_data="close_message")
    
    return kb.as_markup()


# --- ОБРАБОТЧИКИ КНОПОК "НАЗАД" в "Мои розыгрыши" ---

@dp.callback_query(F.data == "mev:back_to_involved")
async def back_to_involved_list(cq: CallbackQuery):
    """Возврат из просмотра розыгрыша к списку 'В которых участвую'"""
    await show_involved_giveaways(cq)

@dp.callback_query(F.data == "mev:back_to_finished")
async def back_to_finished_list(cq: CallbackQuery):
    """Возврат из просмотра розыгрыша к списку 'Завершённые розыгрыши'"""
    await show_finished_participated_giveaways(cq)

@dp.callback_query(F.data == "mev:back_to_participant")
async def back_to_participant_menu(cq: CallbackQuery):
    """Возврат из списков участника в меню 'Я - участник'"""
    await show_participant_menu(cq)

@dp.callback_query(F.data == "mev:back_to_creator")
async def back_to_creator_menu(cq: CallbackQuery):
    """Возврат из списков создателя в меню 'Я - создатель'"""
    await show_creator_menu(cq)

#--- Обработчик для заблокированных кнопок standard пользователей ---
@dp.callback_query(F.data.startswith("premium_required:"))
async def handle_premium_required(cq: CallbackQuery):
    """Показывает pop-up с предложением подписки"""
    await cq.answer(
        "💎 Оформите подписку ПРЕМИУМ для доступа к функционалу",
        show_alert=True
    )


# --- Мониторинг состояния механик (Возвращает статистику по механикам для мониторинга) ---
async def get_mechanics_stats() -> dict:

    stats = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'cache_size': 0,
        'cache_hits': 0,
        'cache_misses': 0,
        'total_mechanics': 0,
        'active_captcha': 0,
        'active_referral': 0,
        'errors_last_hour': 0
    }
    
    try:
        # Статистика кэша
        async with _cache_lock:
            stats['cache_size'] = len(_mechanics_cache)
        
        # Статистика из БД
        async with session_scope() as s:
            # Общее количество механик
            result = await s.execute(
                text("SELECT COUNT(*) FROM giveaway_mechanics")
            )
            stats['total_mechanics'] = result.scalar_one() or 0
            
            # Активные механики по типам
            result = await s.execute(
                text("""
                    SELECT mechanic_type, COUNT(*) 
                    FROM giveaway_mechanics 
                    WHERE is_active = true 
                    GROUP BY mechanic_type
                """)
            )
            for mechanic_type, count in result.fetchall():
                if mechanic_type == 'captcha':
                    stats['active_captcha'] = count
                elif mechanic_type == 'referral':
                    stats['active_referral'] = count
            
            # Ошибки за последний час
            result = await s.execute(
                text("""
                    SELECT COUNT(*) 
                    FROM giveaway_mechanics 
                    WHERE created_at > NOW() - INTERVAL '1 hour'
                    AND config::text LIKE '%error%'
                """)
            )
            stats['errors_last_hour'] = result.scalar_one() or 0
        
        return stats
        
    except Exception as e:
        mechanics_logger.error(f"❌ Ошибка получения статистики механик: {e}")
        stats['error'] = str(e)
        return stats

# --- Логирует операцию с механиками для аудита ---
async def log_mechanics_operation(operation: str, giveaway_id: int, mechanic_type: str = None, 
                                 success: bool = True, details: dict = None):
    audit_log = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'operation': operation,
        'giveaway_id': giveaway_id,
        'mechanic_type': mechanic_type,
        'success': success,
        'details': details or {},
        'user_agent': 'bot_system'  # Можно добавить информацию о вызывающем
    }
    
    mechanics_logger.info(f"📋 АУДИТ: {json.dumps(audit_log, ensure_ascii=False)}")

# ---------------- ENTRYPOINT ----------------
async def main():
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    # 1) инициализация БД
    await init_db()
    await ensure_schema()
    logging.info("✅ База данных инициализирована")
    logging.info("✅ База данных PostgreSQL инициализирована")

    # Автодеактивация истёкших топ-размещений — каждые 30 минут
    scheduler.add_job(
        deactivate_expired_top_placements,
        trigger='interval',
        minutes=30,
        id='deactivate_top_placements',
        replace_existing=True,
    )
    # Публикация запланированных продвижений — каждую минуту
    scheduler.add_job(
        check_scheduled_promotions,
        trigger='interval',
        minutes=1,
        id='check_scheduled_promotions',
        replace_existing=True,
    )

    # 2) запускаем планировщик
    scheduler.start()
    logging.info("✅ Планировщик запущен")

    # 2.5) ВОССТАНАВЛИВАЕМ активные розыгрыши в планировщике
    try:
        async with session_scope() as s:
            active_giveaways = await s.execute(
                stext("SELECT id, end_at_utc FROM giveaways WHERE status='active'")
            )
            active_rows = active_giveaways.all()
            
            restored_count = 0
            for gid, end_at_str in active_rows:
                try:
                    # КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: парсим строку в datetime
                    if isinstance(end_at_str, str):
                        # Парсим строку из базы в datetime
                        if '.' in end_at_str:
                            # Формат с микросекундами: 2025-11-19 10:22:00.000000
                            end_at_dt = datetime.strptime(end_at_str, "%Y-%m-%d %H:%M:%S.%f")
                        else:
                            # Формат без микросекунд: 2025-11-19 10:22:00
                            end_at_dt = datetime.strptime(end_at_str, "%Y-%m-%d %H:%M:%S")
                    else:
                        # Уже datetime объект
                        end_at_dt = end_at_str
                    
                    # Нормализуем timezone
                    end_at_normalized = normalize_datetime(end_at_dt)
                    
                    # Проверяем что время еще не прошло
                    if end_at_normalized > datetime.now(timezone.utc):
                        scheduler.add_job(
                            func=finalize_and_draw_job,
                            trigger=DateTrigger(run_date=end_at_normalized),
                            args=[gid],
                            id=f"final_{gid}",
                            replace_existing=True,
                        )
                        restored_count += 1
                        logging.info(f"🔄 Restored scheduler job for giveaway {gid} at {end_at_normalized}")
                    else:
                        # Время прошло - запускаем немедленно
                        asyncio.create_task(finalize_and_draw_job(gid))
                        logging.info(f"🚨 Time passed, immediate finalize for {gid}")
                        
                except Exception as e:
                    logging.error(f"❌ Failed to restore job for {gid}: {e}")
                    logging.error(f"❌ end_at value: {end_at_str}, type: {type(end_at_str)}")
            
            logging.info(f"✅ Restored {restored_count} giveaway jobs")
            
    except Exception as e:
        logging.error(f"❌ Error restoring scheduler jobs: {e}")

    # 3) Проверяем токен и подключение к Telegram
    me = await bot.get_me()
    # запомним username для deeplink-кнопок в каналах
    global BOT_USERNAME
    BOT_USERNAME = me.username
    logging.info(f"🤖 Бот запущен как @{me.username} (ID: {me.id})")

    # 4) Устанавливаем команды бота
    await set_bot_commands(bot)
    logging.info("✅ Команды установлены")

    # 5) Снимаем возможный старый вебхук
    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("🔁 Webhook удалён, включаю polling...")

    # 6) Стартуем внутренний HTTP для preview_service
    asyncio.create_task(run_internal_server())

    # 7) Запускаем polling
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

# --- Внутренний HTTP для preview_service ---

async def _internal_get_giveaway_info(gid: str, user_id: int):
    """
    Возвращает данные для мини-апа:
      - список каналов розыгрыша с флагом подписки текущего пользователя
      - дату окончания (UTC) и уже выданный билет (если есть)
    Формат ответа под фронт:
      {
        "ok": true,
        "ends_at": "2025-11-11T19:20:00Z",
        "channels": [
            {"title": "...", "username": "mychannel", "link": "https://t.me/mychannel", "is_member": true}
        ],
        "ticket": "ABC123" | null
      }
    """
    # приводим gid к int
    try:
        giveaway_id = int(gid)
    except Exception:
        return {"ok": False, "error": "bad_gid"}

    # читаем розыгрыш и прикрепленные каналы
    async with session_scope() as s:
        gw = await s.get(Giveaway, giveaway_id)
        if not gw:
            return {"ok": False, "error": "not_found"}

        res = await s.execute(stext("""
            SELECT gc.chat_id, gc.title, oc.username
            FROM giveaway_channels gc
            LEFT JOIN organizer_channels oc ON oc.id = gc.channel_id
            WHERE gc.giveaway_id = :g
            ORDER BY gc.id
        """), {"g": giveaway_id})
        rows = res.fetchall()

        # есть ли уже билет у пользователя
        res = await s.execute(
            stext("SELECT ticket_code FROM entries WHERE giveaway_id=:g AND user_id=:u"),
            {"g": giveaway_id, "u": user_id}
        )
        row_ticket = res.first()
        ticket = row_ticket[0] if row_ticket else None

    # проверяем подписку пользователя на каждом канале
    channels = []
    all_ok = True
    for chat_id, title, username in rows:
        try:
            m = await bot.get_chat_member(chat_id, user_id)
            is_member = m.status in {"member", "administrator", "creator"}
        except Exception:
            is_member = False
        all_ok = all_ok and is_member
        link = f"https://t.me/{username}" if username else None
        channels.append({
            "title": title,
            "username": username,
            "link": link,
            "is_member": is_member,
        })

    return {
        "ok": True,
        "ends_at": gw.end_at_utc.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "channels": channels,
        "ticket": ticket
    }

async def _internal_claim_ticket(gid: str, user_id: int):
    """
    Выдаёт билет, если пользователь подписан на все каналы розыгрыша.
    Возвращает {ok, ticket} или {ok:false, need=[список каналов без подписки]}.
    """
    try:
        giveaway_id = int(gid)
    except Exception:
        return {"ok": False, "error": "bad_gid"}

    # проверяем, что розыгрыш активен
    async with session_scope() as s:
        gw = await s.get(Giveaway, giveaway_id)
        if not gw or gw.status != GiveawayStatus.ACTIVE:
            return {"ok": False, "error": "not_active"}

    # проверяем подписку на все каналы (используем уже готовый хелпер)
    all_ok, details = await check_membership_on_all(bot, user_id, giveaway_id)
    if not all_ok:
        # вернём список тех, где нет подписки
        need = [title for (title, ok) in details if not ok]
        return {"ok": False, "need": need}

    # если подписка ок — выдаём (или возвращаем существующий) билет
    async with session_scope() as s:
        # есть уже билет?
        res = await s.execute(
            stext("SELECT ticket_code FROM entries WHERE giveaway_id=:g AND user_id=:u"),
            {"g": giveaway_id, "u": user_id}
        )
        row = res.first()
        if row:
            ticket = row[0]
        else:
            # генерируем и сохраняем
            is_new_entry = False
            for _ in range(5):
                ticket = gen_ticket_code()
                try:
                    # source_channel
                    src_res = await s.execute(
                        stext("SELECT chat_id FROM giveaway_channels WHERE giveaway_id=:gid ORDER BY id LIMIT 1"),
                        {"gid": giveaway_id}
                    )
                    src_row = src_res.first()
                    source_channel_id = src_row[0] if src_row else None

                    await s.execute(stext(
                        "INSERT INTO entries(giveaway_id,user_id,ticket_code,prelim_ok,prelim_checked_at,source_channel_id) "
                        "VALUES (:g,:u,:code,true,:ts,:src)"
                    ), {
                        "g": giveaway_id,
                        "u": user_id,
                        "code": ticket,
                        "ts": datetime.now(timezone.utc),
                        "src": source_channel_id
                    })

                    # entry_subscriptions
                    try:
                        ch_res = await s.execute(
                            stext("SELECT chat_id FROM giveaway_channels WHERE giveaway_id=:gid"),
                            {"gid": giveaway_id}
                        )
                        for (ch_id,) in ch_res.fetchall():
                            await s.execute(stext("""
                                INSERT INTO entry_subscriptions(giveaway_id, user_id, channel_id, was_subscribed)
                                VALUES (:gid, :uid, :chid, false)
                                ON CONFLICT(giveaway_id, user_id, channel_id) DO NOTHING
                            """), {"gid": giveaway_id, "uid": user_id, "chid": ch_id})
                    except Exception as _e:
                        logging.warning(f"[claim_ticket] entry_subscriptions failed: {_e}")

                    is_new_entry = True
                    break
                except Exception:
                    continue

        logging.info(f"[claim_ticket] is_new_entry={is_new_entry}, giveaway_id={giveaway_id}")
        if is_new_entry:
            logging.info(f"[claim_ticket] 🚀 Запускаем _check_and_publish_prime для gid={giveaway_id}")
            asyncio.create_task(_check_and_publish_prime(giveaway_id))
    return {"ok": True, "ticket": ticket}

def make_internal_app():
    app = web.Application()

    async def giveaway_info(request: web.Request):
        data = await request.json()
        gid = str(data.get("gid") or "")
        user_id = int(data.get("user_id") or 0)
        if not (gid and user_id):
            return web.json_response({"ok": False}, status=400)
        info = await _internal_get_giveaway_info(gid, user_id)
        return web.json_response(info)

    async def claim_ticket(request: web.Request):
        data = await request.json()
        gid = str(data.get("gid") or "")
        user_id = int(data.get("user_id") or 0)
        if not (gid and user_id):
            return web.json_response({"ok": False}, status=400)
        result = await _internal_claim_ticket(gid, user_id)
        return web.json_response(result)

    async def giveaway_results(request: web.Request):
        """
        Получение результатов розыгрыша для Mini App
        """
        data = await request.json()
        gid = str(data.get("gid") or "")
        user_id = int(data.get("user_id") or 0)
        
        if not (gid and user_id):
            return web.json_response({"ok": False, "error": "bad_params"}, status=400)

        try:
            giveaway_id = int(gid)
        except Exception:
            return web.json_response({"ok": False, "error": "bad_gid"}, status=400)

        # Используем существующую сессию вместо session_scope()
        async with Session() as s:
            try:
                # 1) Получаем информацию о розыгрыше
                gw = await s.get(Giveaway, giveaway_id)
                if not gw:
                    return web.json_response({"ok": False, "error": "not_found"}, status=404)

                # 2) Получаем участников и победителей
                participants_res = await s.execute(
                    stext("SELECT COUNT(DISTINCT user_id) FROM entries WHERE giveaway_id = :gid AND final_ok = true"),
                    {"gid": giveaway_id}
                )
                participants_count = participants_res.scalar_one() or 0

                # 3) Получаем список победителей с их билетами
                winners_res = await s.execute(
                    stext("""
                        SELECT w.rank, COALESCE(u.username, 'Участник') as username, e.ticket_code, w.user_id
                        FROM winners w
                        LEFT JOIN entries e ON e.giveaway_id = w.giveaway_id AND e.user_id = w.user_id
                        LEFT JOIN users u ON u.user_id = w.user_id
                        WHERE w.giveaway_id = :gid
                        ORDER BY w.rank
                    """),
                    {"gid": giveaway_id}
                )
                winners = winners_res.all()

                # 4) Проверяем, является ли текущий пользователь победителем
                user_is_winner = False
                user_winner_rank = None
                user_ticket = None

                for winner in winners:
                    if winner[3] == user_id:
                        user_is_winner = True
                        user_winner_rank = winner[0]
                        user_ticket = winner[2]
                        break

                # 5) Получаем билет пользователя (если участвовал)
                if not user_ticket:
                    ticket_res = await s.execute(
                        stext("SELECT ticket_code FROM entries WHERE giveaway_id=:gid AND user_id=:uid"),
                        {"gid": giveaway_id, "uid": user_id}
                    )
                    ticket_row = ticket_res.first()
                    user_ticket = ticket_row[0] if ticket_row else None

                # 6) Формируем список победителей для отображения
                winners_list = []
                for winner in winners:
                    # Безопасное извлечение атрибутов из строки результата
                    winner_data = {
                        "rank": winner[0], 
                        "username": winner[1], 
                        "ticket_code": winner[2], 
                        "user_id": winner[3], 
                        "is_current_user": winner[3] == user_id  
                    }
                    winners_list.append(winner_data)

                response_data = {
                    "ok": True,
                    "giveaway": {
                        "id": giveaway_id,
                        "title": gw.internal_title,
                        "description": gw.public_description,
                        "end_at_utc": gw.end_at_utc.isoformat() if hasattr(gw.end_at_utc, 'isoformat') else str(gw.end_at_utc),
                        "winners_count": gw.winners_count,
                        "participants_count": participants_count,
                        "status": gw.status
                    },
                    "user": {
                        "is_winner": user_is_winner,
                        "winner_rank": user_winner_rank,
                        "ticket_code": user_ticket
                    },
                    "winners": winners_list
                }

                return web.json_response(response_data)

            except Exception as e:
                logging.error(f"Error in giveaway_results: {e}")
                return web.json_response({"ok": False, "error": "server_error"}, status=500)
            finally:
                await s.close()


    async def verify_simple_captcha_and_participate(request: web.Request):
        """
        Internal API endpoint для проверки простой Captcha и регистрации участия
        Вызывается из Node.js API (preview_service)
        """
        try:
            data = await request.json()
            user_id = int(data.get("user_id") or 0)
            giveaway_id = int(data.get("giveaway_id") or 0)
            captcha_answer = data.get("captcha_answer") or ""  # Введенные пользователем цифры
            captcha_token = data.get("captcha_token") or ""    # Токен для проверки
            
            logging.info(f"🔍 [SIMPLE-CAPTCHA-API] Request: user_id={user_id}, giveaway_id={giveaway_id}")
            
            if not all([user_id, giveaway_id, captcha_answer, captcha_token]):
                logging.error(f"❌ [SIMPLE-CAPTCHA-API] Missing required parameters")
                return web.json_response({
                    "ok": False,
                    "error": "missing_parameters",
                    "message": "Отсутствуют обязательные параметры"
                }, status=400)
            
            # 🔥 ИСПОЛЬЗУЕМ НОВУЮ ФУНКЦИЮ ДЛЯ ПРОСТОЙ CAPTCHA
            result = await process_simple_captcha_participation(
                user_id=user_id,
                giveaway_id=giveaway_id,
                captcha_answer=captcha_answer,
                captcha_token=captcha_token
            )
            
            logging.info(f"🔍 [SIMPLE-CAPTCHA-API] Result: ok={result['ok']}, has_ticket={bool(result['ticket_code'])}")
            
            return web.json_response(result)
            
        except Exception as e:
            logging.error(f"❌ [SIMPLE-CAPTCHA-API] Error: {e}", exc_info=True)
            return web.json_response({
                "ok": False,
                "error": "server_error",
                "message": "❌ Ошибка при проверке. Попробуйте еще раз."
            }, status=500)

    async def create_simple_captcha_session(request: web.Request):
        """
        Internal API: создать captcha-сессию и вернуть digits+token
        """
        try:
            data = await request.json()
            user_id = int(data.get("user_id") or 0)
            giveaway_id = int(data.get("giveaway_id") or 0)

            if not user_id or not giveaway_id:
                return web.json_response(
                    {"ok": False, "error": "missing_parameters", "message": "user_id и giveaway_id обязательны"},
                    status=400
                )

            captcha_data = await generate_simple_captcha(giveaway_id, user_id)

            return web.json_response({
                "ok": True,
                "giveaway_id": giveaway_id,
                "user_id": user_id,
                "digits": captcha_data["digits"],
                "token": captcha_data["token"],
                "expires_in": captcha_data.get("expires_in", 600),
            })

        except Exception as e:
            logging.error(f"❌ [SIMPLE-CAPTCHA-API] create_session error: {e}", exc_info=True)
            return web.json_response(
                {"ok": False, "error": "server_error", "message": "Ошибка генерации captcha"},
                status=500
            )

    async def csv_export(request: web.Request):
        """
        Вызывается из Node.js: генерирует и отправляет CSV файл пользователю прямо в бот
        """
        try:
            data        = await request.json()
            user_id     = int(data.get("user_id") or 0)
            giveaway_id = int(data.get("giveaway_id") or 0)

            if not user_id or not giveaway_id:
                return web.json_response({"ok": False, "reason": "bad_params"}, status=400)

            # Проверяем владельца
            if not await is_giveaway_organizer(user_id, giveaway_id):
                return web.json_response({"ok": False, "reason": "forbidden"}, status=403)

            # Проверяем участников
            participant_count = await get_participant_count(giveaway_id)
            if participant_count == 0:
                return web.json_response({"ok": False, "reason": "no_participants"})

            # Генерируем CSV в памяти
            csv_file      = await generate_csv_in_memory(giveaway_id)
            giveaway_title = await get_giveaway_title(giveaway_id)

            # Отправляем файл пользователю
            await bot.send_document(
                chat_id=user_id,
                document=csv_file,
                caption=(
                    f"📊 <b>Статистика розыгрыша</b>\n"
                    f"<b>Название:</b> {giveaway_title}\n"
                    f"<b>ID розыгрыша:</b> {giveaway_id}\n"
                    f"<b>Участников:</b> {participant_count}\n\n"
                    f"<i>Файл в формате CSV. Откройте в Excel или Google Sheets.</i>"
                ),
                parse_mode="HTML"
            )

            # Возвращаем username бота для редиректа из mini app
            bot_info = await bot.get_me()
            return web.json_response({"ok": True, "bot_username": bot_info.username})

        except Exception as e:
            logging.error(f"[internal/csv_export] error: {e}", exc_info=True)
            return web.json_response({"ok": False, "reason": str(e)}, status=500)

    async def top_placement_paid(request: web.Request):
        try:
            data = await request.json()
            logging.info(f"[top_placement_paid] received: {data}")
            user_id     = int(data.get("user_id", 0))
            period_label = data.get("period_label", "")
            payment_type = data.get("payment_type", "")
            logging.info(f"[top_placement_paid] user_id={user_id}, payment_type={payment_type}, period_label={period_label}")
            
            if user_id and payment_type == "card":
                miniapp_url = f"{WEBAPP_BASE_URL}/miniapp/?tgWebAppStartParam=page_services"
                kb = InlineKeyboardBuilder()
                kb.button(text="🚀 К сервисам", web_app=WebAppInfo(url=miniapp_url))
                kb.adjust(1)
                price_map = {"1 день": "149", "1 неделю": "499"}
                price = price_map.get(period_label, "—")
                await bot.send_message(
                    user_id,
                    f"✅ <b>Оплата прошла успешно!</b>\n\n"
                    f"Услуга: Включение в топ-розыгрыши\n"
                    f"Цена: {price} ₽\n\n"
                    f"<i>Вы можете вернуться обратно в mini-app и выбрать ещё сервисы для продвижения.</i>",
                    parse_mode="HTML",
                    reply_markup=kb.as_markup()
                )
            return web.json_response({"ok": True})
        except Exception as e:
            logging.error(f"[internal/top_placement_paid] error: {e}", exc_info=True)
            return web.json_response({"ok": False, "reason": str(e)}, status=500)

    async def notify_prime(request: web.Request):
        data = await request.json()
        gid = int(data.get("giveaway_id") or 0)
        if gid:
            asyncio.create_task(_check_and_publish_prime(gid))
        return web.json_response({"ok": True})

    app.router.add_post("/api/giveaway_info", giveaway_info)
    app.router.add_post("/api/claim_ticket", claim_ticket)
    app.router.add_post("/internal/notify_prime", notify_prime)
    app.router.add_post("/internal/top_placement_paid", top_placement_paid)
    app.router.add_post("/api/giveaway_results", giveaway_results)
    app.router.add_post("/api/verify_simple_captcha_and_participate", verify_simple_captcha_and_participate)
    app.router.add_post("/api/create_simple_captcha_session", create_simple_captcha_session)
    app.router.add_post("/internal/csv_export", csv_export)

    return app


async def run_internal_server():
    runner = web.AppRunner(make_internal_app())
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 8088)   # ← локальный порт
    await site.start()
    print("📡 Internal API running on http://127.0.0.1:8088")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())