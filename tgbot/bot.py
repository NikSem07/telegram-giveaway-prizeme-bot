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
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from urllib.parse import urlencode
import time

from aiogram.enums import ChatType
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import ChatMemberUpdated, ChatJoinRequest
from aiogram import Bot, Dispatcher, F
import aiogram.types as types
from aiogram.filters import Command, StateFilter
from aiogram.types import (Message, CallbackQuery, InlineKeyboardMarkup,
                           InlineKeyboardButton, InputMediaPhoto)
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
from sqlalchemy.ext.asyncio import (create_async_engine, async_sessionmaker)

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

MEDIA_BASE_URL = os.getenv("MEDIA_BASE_URL", "https://media.prizeme.ru")
WEBAPP_BASE_URL = os.getenv("WEBAPP_BASE_URL", "https://prizeme.ru")

DESCRIPTION_PROMPT = (
    "<b>Введите текст подробного описания розыгрыша:</b>\n\n"
    "Можно использовать не более 2500 символов.\n\n"
    "<i>Подробно опишите условия розыгрыша для ваших подписчиков.\n"
    "</i>После начала розыгрыша введённый текст будет опубликован на всех связанных с ним каналах.")

MEDIA_QUESTION = "Хотите ли добавить изображение / gif / видео для текущего розыгрыша?"

MEDIA_INSTRUCTION = (
    "<b>Отправьте изображение / <i>gif</i> / видео для текущего розыгрыша.</b>\n\n"
    "<i>Используйте стандартную доставку. Не отправляйте \"несжатым\" способом (НЕ как документ).</i>\n\n"
    "<b>Внимание!</b> Видео должно быть в формате MP4, а его размер не должен превышать 5 МБ."
)

BTN_GIVEAWAYS = "Мои розыгрыши"
BTN_CREATE = "Создать розыгрыш"
BTN_ADD_CHANNEL = "Добавить канал"
BTN_ADD_GROUP = "Добавить группу"
BTN_SUBSCRIPTIONS = "Премиум"
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
    "⭐️ Ваш розыгрыш создан, осталось только запустить!\n\n"
    "Подключите минимум 1 канал/группу, чтобы можно было запустить розыгрыш.\n\n"
    "Нажмите на кнопку ниже, чтобы сделать это."
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

# ---- Другое ----
def kb_add_cancel() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Отмена", callback_data="add:cancel")
    kb.adjust(1)
    return kb.as_markup()

if not all([S3_ENDPOINT, S3_BUCKET, S3_KEY, S3_SECRET]):
    logging.warning("S3 env not fully set — uploads will fail.")

# ============================================================================
# PREMIUM ACCESS CONTROL SYSTEM
# ============================================================================

def premium_only(func):
    """
    ДЕКОРАТОР ДЛЯ PREMIUM-ДОСТУПА
    Использование: @premium_only перед async def функции
    
    Для standard пользователей показывает pop-up с предложением подписки
    Для premium пользователей выполняет оригинальную функцию
    """
    async def wrapper(cq: CallbackQuery, *args, **kwargs):
        user_id = cq.from_user.id
        
        # Получаем статус пользователя
        status = await get_user_status(user_id)
        
        if status == 'standard':
            # Показываем pop-up для standard пользователей
            await cq.answer(
                "💎 Оформите подписку ПРЕМИУМ для доступа к функционалу",
                show_alert=True
            )
            return
        
        # Если premium - выполняем оригинальную функцию
        return await func(cq, *args, **kwargs)
    
    return wrapper

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
    
    @staticmethod
    def clean_text_preview(html_text: str, has_media: bool = False) -> tuple[str, bool]:
        """
        УЛУЧШЕННАЯ ВЕРСИЯ: учитывает наличие медиа в розыгрыше
        Возвращает (очищенный_текст, нужно_ли_отключить_превью)
        
        КРИТИЧЕСКОЕ ПРАВИЛО:
        - ЕСТЬ медиа: НИКОГДА не отключаем превью (чтобы работала фиолетовая рамка)
        - НЕТ медиа: отключаем превью только если есть пользовательские ссылки
        """
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
    """
    title = (
        f"🔗 Подключение канала к розыгрышу \"{event_title}\""
        if event_title else
        "🔗 Подключение канала к розыгрышу"
    )

    lines = [
        title,
        "",
        "Подключить канал к розыгрышу сможет только администратор, "
        "который обладает достаточным уровнем прав в прикреплённом канале.",
        "",
        "Подключённые каналы:",
    ]

    if attached:
        for i, (t, uname, _cid) in enumerate(attached, start=1):
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
        "Как только это сделаете, можете запускать розыгрыш, нажав на кнопку снизу.\n\n"
        "<b><i>Внимание!</i></b> После запуска пост с розыгрышем будет автоматически опубликован "
        "в подключённых каналах / группах к текущему розыгрышу."
    )

def kb_launch_confirm(gid: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Запустить розыгрыш", callback_data=f"launch:do:{gid}")
    kb.button(text="Настройки розыгрыша", callback_data=f"raffle:settings_menu:{gid}")  # 🔄 ИЗМЕНЕНИЕ: callback_data
    kb.button(text="Дополнительные механики", callback_data=f"raffle:mechanics_disabled:{gid}")  # 🔄 НОВАЯ КНОПКА
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

    lines.append("Число участников: 0")
    lines.append(f"Количество призов: {max(0, prizes)}")

    if end_at_msk:
        tail = f" ({days_left} дней)" if isinstance(days_left, int) and days_left >= 0 else ""
        lines.append(f"Дата розыгрыша: {end_at_msk}{tail}")
    else:
        lines.append("Дата розыгрыша: 00:00, 00.00.0000 (0 дней)")

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

    lines.append("Число участников: 0")
    lines.append(f"Количество призов: {max(0, prizes)}")

    if end_at_msk:
        tail = f" ({days_left} дней)" if isinstance(days_left, int) and days_left >= 0 else ""
        lines.append(f"Дата розыгрыша: {end_at_msk}{tail}")
    else:
        lines.append("Дата розыгрыша: 00:00, 00.00.0000 (0 дней)")

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
        full = f"{hidden_link}\n\n{txt}"
    else:
        full = f"{txt}\n\n{hidden_link}"

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
            full_text = f"{hidden_link}\n\n{preview_text}"
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

# ---- DB INIT ----

# ID закрытой группы
PREMIUM_GROUP_ID = -1003320639276

# 🔧 ПРИНУДИТЕЛЬНО УКАЗЫВАЕМ ASYNCPG ДРАЙВЕР
DB_URL = "postgresql+asyncpg://prizeme_user:Akinneket19!@localhost/prizeme_prod"

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

async def ensure_user(user_id:int, username:str|None):
    async with session_scope() as s:
        u = await s.get(User, user_id)
        if not u:
            u = User(user_id=user_id, username=username)
            s.add(u)
    
    # Регистрируем пользователя и в bot_users
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
        
        # Проверяем членство в премиум-группе
        await check_and_update_premium_status(bot_user, s)
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
        # ✅ ПРАВИЛЬНО: aware datetime с timezone (UTC)
        added_at_aware = datetime.now(timezone.utc)
        
        async with session_scope() as s:
            # Сначала проверяем существование
            existing = await s.execute(
                text("SELECT id FROM organizer_channels WHERE owner_user_id = :user_id AND chat_id = :chat_id"),
                {"user_id": owner_user_id, "chat_id": chat_id}
            )
            existing_row = existing.first()
            
            if existing_row:
                # Обновляем существующую запись
                await s.execute(
                    text("""
                    UPDATE organizer_channels 
                    SET title = :title, is_private = :is_private, bot_role = :role, status = 'ok'
                    WHERE owner_user_id = :user_id AND chat_id = :chat_id
                    """),
                    {
                        "title": title,
                        "is_private": is_private,
                        "role": bot_role,
                        "user_id": owner_user_id,
                        "chat_id": chat_id
                    }
                )
                logging.info(f"✅ Канал обновлен: {title} (chat_id={chat_id}) для user_id={owner_user_id}")
                return False  # Не новая запись
            else:
                # ✅ ПРАВИЛЬНО: Вставляем с aware datetime
                await s.execute(
                    text("""
                    INSERT INTO organizer_channels
                        (owner_user_id, chat_id, title, is_private, bot_role, status, added_at)
                    VALUES (:user_id, :chat_id, :title, :is_private, :role, 'ok', :added_at)
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
                logging.info(f"✅ Новый канал добавлен: {title} (chat_id={chat_id}) для user_id={owner_user_id}")
                return True  # Новая запись
                
    except Exception as e:
        logging.error(f"❌ Error in save_shared_chat: {e}")
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
    commands = [
        BotCommand(command="start", description="перезапустить бота"),
        BotCommand(command="create", description="создать розыгрыш"),
        BotCommand(command="giveaways", description="мои розыгрыши"),  
        BotCommand(command="subscriptions", description="мои подписки"),
    ]
    await bot.set_my_commands(commands)

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
    shared = m.chat_shared
    chat_id = shared.chat_id

    try:
        chat = await bot.get_chat(chat_id)
        me = await bot.get_me()
        cm = await bot.get_chat_member(chat_id, me.id)
        role = "admin" if cm.status == "administrator" else ("member" if cm.status == "member" else "none")
    except Exception as e:
        await m.answer(f"Не удалось получить данные чата. Попробуйте ещё раз. ({e})")
        return

    title = chat.title or getattr(chat, "first_name", None) or "Без названия"
    username = getattr(chat, "username", None)
    
    is_new = await save_shared_chat(
        owner_user_id=m.from_user.id,
        chat_id=chat.id,
        title=title,
        chat_type=chat.type,
        bot_role=role
    )

    kind = "канал" if chat.type == "channel" else "группа"
    action_text = "подключён" if is_new else "обновлён"
    await m.answer(
        f"{kind.capitalize()} <b>{title}</b> {action_text} к боту.",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove(),
    )

    # Если сейчас идёт привязка к конкретному розыгрышу — перерисуем экран привязки
    data = await state.get_data()
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
    else:
        # Обычный кейс: показать «Мои каналы»
        rows = await get_user_org_channels(m.from_user.id)
        label = "Ваши каналы:\n\n" + ("" if rows else "Пока пусто.")
        await m.answer(label, reply_markup=kb_my_channels(rows))


def kb_event_actions(gid:int, status:str):

    kb = InlineKeyboardBuilder()
    
    if status == GiveawayStatus.DRAFT:
        # Для черновиков используем новую клавиатуру kb_draft_actions
        return kb_draft_actions(gid)
    elif status == GiveawayStatus.ACTIVE:
        # Для активных розыгрышей - только статистика
        kb.button(text="📊 Статистика", callback_data=f"ev:status:{gid}")
    elif status in (GiveawayStatus.FINISHED, GiveawayStatus.CANCELLED):
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
    await ensure_user(m.from_user.id, m.from_user.username)
    text = (
        "Добро пожаловать в Бот с розыгрышами <b>PrizeMe!</b>\n\n"
        "Бот способен запускать розыгрыши среди участников одного "
        "или нескольких Telegram-каналов и самостоятельно выбирать "
        "победителей в назначенное время.\n\n"
        "Команды бота:\n"
        "<b>/create</b> – создать розыгрыш\n"
        "<b>/events</b> – мои розыгрыши\n"
        "<b>/subscriptions</b> – подписки"
    )
    await m.answer(text, parse_mode="HTML", reply_markup=reply_main_kb())

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

@dp.message(Command("admin_draw"))
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
    await message.answer(
        "Введите название розыгрыша:\n\n"
        "Максимум — <b>50 символов</b>.\n\n"
        "Это название будет отображаться пользователям в списке розыгрышей "
        "в боте. Подойдите к выбору названия как можно более ответственно, "
        "чтобы участники могли легко идентифицировать ваш розыгрыш среди всех "
        "остальных в разделе <b>«Активные розыгрыши»</b>.\n\n"
        "<i>Пример названия:</i> <b>MacBook Pro от канала PrizeMe</b>",
        parse_mode="HTML"
    )
    await state.set_state(CreateFlow.TITLE)   # <-- ставим состояние титула

# ===== Reply-кнопки: перенаправляем на готовые сценарии =====

# "Мои розыгрыши" -> используем cmd_events
@dp.message(F.text == BTN_GIVEAWAYS)
async def on_btn_giveaways(m: Message, state: FSMContext):
    await show_my_giveaways_menu(m)

# "Новый розыгрыш" -> create_giveaway_start
@dp.message(F.text == BTN_CREATE)
async def on_btn_create(m: Message, state: FSMContext):
    await create_giveaway_start(m, state)

@dp.message(Command("premium"))
@dp.message(F.text == "Премиум")
async def cmd_premium(m: Message):
    """Раздел Премиум с подпиской, бустом и донатом"""
    
    text = (
        "<b>Добро пожаловать в раздел Премиум:</b>\n\n"
        "- <b>Вы можете получить доступ к уникальному функционалу</b>, оформив подписку, для этого нажмите на кнопку \"Подписка\", чтобы узнать о ее преимуществах и тарифах\n"
        "- <b>Вы также можете получить доступ к отдельным функциям</b> сервиса внутри mini-app, для подробной информации нажмите на кнопку \"Буст\"\n\n"
        "Если хотите <b>поддержать проект</b>, будем признательны за донат, оформить его можно, нажав на кнопку \"Донат\""
    )
    
    # Клавиатура с тремя кнопками
    kb = InlineKeyboardBuilder()
    kb.button(text="Подписка", callback_data="premium:subscribe")
    kb.button(text="Буст", callback_data="premium:boost")
    kb.button(text="Донат", callback_data="premium:donate")
    kb.adjust(3)  # 3 кнопки в ряд
    
    await m.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())

# --- Обработчики кнопок премиум-раздела ---

@dp.callback_query(F.data == "premium:subscribe")
async def cb_premium_subscribe(cq: CallbackQuery):
    """Обработчик кнопки 'Подписка' - информационный блок о подписке"""
    # Текст с HTML разметкой (жирный, курсив, эмодзи)
    text = (
        "<b>Подписка дает доступ к уникальному функционалу бота:</b>\n\n"
        "🥇 Увеличенные лимиты числа победителей\n"
        "🤖 Защита от накрутки и ботов через Captcha\n"
        "📊 Продвинутая статистика и выгрузка CSV\n"
        "🔥 И другие механики\n\n"
        "Вы можете ознакомиться с тарифами и условиями, нажав на кнопку \"Тарифы\" "
        "или вернуться обратно по кнопке \"Назад\"\n\n"
        "<i>После оплаты тарифа для активации подписки Вам потребуется перезапустить бота "
        "с помощью команды /start, Вы также будете добавлены в приватный канал (не выходите из него)</i>"
    )
    
    # Создаем клавиатуру с двумя кнопками
    kb = InlineKeyboardBuilder()
    kb.button(text="💵 Тарифы", url="https://t.me/tribute/app?startapp=sHOW")
    kb.button(text="⬅️ Назад", callback_data="premium:back")  # Та же логика что и в блоке "Донат"
    kb.adjust(1)  # Кнопки в один столбец
    
    # Пытаемся отредактировать существующее сообщение
    try:
        await cq.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    except Exception:
        # Если не удалось отредактировать (старое сообщение), отправляем новое
        await cq.message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")
        try:
            await cq.message.delete()
        except Exception:
            pass
    
    await cq.answer()

@dp.callback_query(F.data == "premium:boost")
async def cb_premium_boost(cq: CallbackQuery):
    """Обработчик кнопки 'Буст'"""
    await cq.answer("🚀 Разрабатываем", show_alert=True)

@dp.callback_query(F.data == "premium:donate")
async def cb_premium_donate(cq: CallbackQuery):
    """Обработчик кнопки 'Донат' - показывает информацию о донате"""
    text = (
        "<b>❤️ Спасибо за интерес к сервису</b>\n\n"
        "Лучшая поддержка на свете дарует лучший сервис, проект будет развиваться, а донат способствовать этому 🙌🏻"
    )
    
    kb = InlineKeyboardBuilder()
    kb.button(text="💰 Поддержать", url="https://t.me/tribute/app?startapp=dA1o")
    kb.button(text="⬅️ Назад", callback_data="premium:back")
    kb.adjust(1)
    
    # Редактируем сообщение чтобы показать информацию о донате
    try:
        await cq.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    except Exception:
        # Если не удалось отредактировать (например, сообщение слишком старое), отправляем новое
        await cq.message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())
        try:
            await cq.message.delete()
        except Exception:
            pass
    
    await cq.answer()

@dp.callback_query(F.data == "premium:back")
async def cb_premium_back(cq: CallbackQuery):
    """Обработчик кнопки 'Назад' в премиум-разделе"""
    text = (
        "<b>Добро пожаловать в раздел Премиум:</b>\n\n"
        "- <b>Вы можете получить доступ к уникальному функционалу</b>, оформив подписку, для этого нажмите на кнопку \"Подписка\", чтобы узнать о ее преимуществах и тарифах\n"
        "- <b>Вы также можете получить доступ к отдельным функциям</b> сервиса внутри mini-app, для подробной информации нажмите на кнопку \"Буст\"\n\n"
        "Если хотите <b>поддержать проект</b>, будем признательны за донат, оформить его можно, нажав на кнопку \"Донат\""
    )
    
    kb = InlineKeyboardBuilder()
    kb.button(text="Подписка", callback_data="premium:subscribe")
    kb.button(text="Буст", callback_data="premium:boost")
    kb.button(text="Донат", callback_data="premium:donate")
    kb.adjust(3)
    
    try:
        await cq.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    except Exception:
        await cq.message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())
        try:
            await cq.message.delete()
        except Exception:
            pass
    
    await cq.answer()


# Обработчик для новой кнопки "Мои каналы"
@dp.message(F.text == BTN_CHANNELS)
async def on_btn_my_channels(m: Message):
    rows = await get_user_org_channels(m.from_user.id)
    text = "Ваши каналы / группы:\n\n" + ("" if rows else "Пока пусто.")
    await m.answer(text, reply_markup=kb_my_channels(rows))

@dp.message(CreateFlow.TITLE)
async def handle_giveaway_name(m: Message, state: FSMContext):
    name = (m.text or "").strip()
    if not name:
        await m.answer("Введите название розыгрыша:")
        return
    if len(name) > 50:
        await m.answer("Название не должно превышать 50 символов. Попробуйте снова.")
        return

    await state.update_data(title=name)

    # ➜ Новый следующий шаг: спросить количество победителей
    await state.set_state(CreateFlow.WINNERS)
    await m.answer(
        "Укажите количество победителей в этом розыгрыше от 1 до 50 "
        "(введите только число, не указывая других символов):"
    )

@dp.message(CreateFlow.WINNERS)
async def handle_winners_count(m: Message, state: FSMContext):
    raw = (m.text or "").strip()
    if not raw.isdigit():
        await m.answer("Нужно целое число от 1 до 50. Введите ещё раз:")
        return

    winners = int(raw)
    if not (1 <= winners <= 50):
        await m.answer("Число должно быть от 1 до 50. Введите ещё раз:")
        return

    await state.update_data(winners_count=winners)

    # ➜ дальше идём к описанию (как и раньше)
    await state.set_state(CreateFlow.DESC)
    await m.answer(DESCRIPTION_PROMPT, parse_mode="HTML")

# --- пользователь прислал описание ---
@dp.message(CreateFlow.DESC, F.text)
async def step_desc(m: Message, state: FSMContext):
    # УПРОЩЕННАЯ ВЕРСИЯ: используем только html_text как раньше
    html_text = m.html_text
    
    if len(html_text) > 2500:
        await m.answer("⚠️ Слишком длинно. Укороти до 2500 символов и пришли ещё раз.")
        return

    # Сохраняем описание как HTML
    await state.update_data(desc=html_text)

    # Показываем предпросмотр с отключенным превью ссылок
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
        confirm_text = (
            f"🗓 Время окончания установлено: <b>{dt_msk.strftime('%H:%M %d.%m.%Y')}</b>\n"
            f"Осталось: <b>{days_left}</b> дн."
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
        await m.answer("Введите название розыгрыша:")
        return
    if len(new_title) > 50:
        await m.answer("Название не должно превышать 50 символов. Попробуйте снова.")
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
    
    raw = (m.text or "").strip()
    if not raw.isdigit():
        await m.answer("Нужно целое число от 1 до 50. Введите ещё раз:")
        return

    winners = int(raw)
    if not (1 <= winners <= 50):
        await m.answer("Число должно быть от 1 до 50. Введите ещё раз:")
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

@dp.callback_query(EditFlow.CONFIRM_EDIT, F.data == "edit:fix")
async def edit_fix(cq: CallbackQuery, state: FSMContext):
    """Исправить - вернуться к вводу"""
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
        await cq.message.answer("Введите новое количество победителей (от 1 до 50):")
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

async def show_event_card(chat_id:int, giveaway_id:int):
    """
    Показывает карточку розыгрыша с УСИЛЕННЫМ link-preview если есть медиа
    """
    async with session_scope() as s:
        gw = await s.get(Giveaway, giveaway_id)

    cap = (f"<b>{gw.internal_title}</b>\n\n{gw.public_description}\n\n"
           f"Статус: {gw.status}\nПобедителей: {gw.winners_count}\n"
           f"Дата окончания: {gw.end_at_utc.strftime('%H:%M %d.%m.%Y MSK')}")

    kind, fid = unpack_media(gw.photo_file_id)

    # 🔄 УСИЛЕННЫЙ LINK-PREVIEW для карточки
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

            # 🔄 УСИЛЕННЫЙ LINK-PREVIEW
            hidden_link = f'<a href="{preview_url}"> </a>'
            full_text = f"{cap}\n\n{hidden_link}"

            lp = LinkPreviewOptions(
                is_disabled=False,
                prefer_large_media=True,
                prefer_small_media=False,
                show_above_text=False,
                url=preview_url  # 🔄 ЯВНО указываем URL
            )

            # ЕСЛИ ЕСТЬ МЕДИА - НИКОГДА НЕ ОТКЛЮЧАЕМ ПРЕВЬЮ!
            # 🔄 КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: используем новую клавиатуру для черновиков
            if gw.status == GiveawayStatus.DRAFT:
                reply_markup = kb_draft_actions(giveaway_id)
            else:
                reply_markup = kb_event_actions(giveaway_id, gw.status)
                
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
    # 🔄 КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: используем новую клавиатуру для черновиков
    if gw.status == GiveawayStatus.DRAFT:
        reply_markup = kb_draft_actions(giveaway_id)
    else:
        reply_markup = kb_event_actions(giveaway_id, gw.status)
    
    if kind == "photo" and fid:
        await bot.send_photo(chat_id, fid, caption=cap, reply_markup=reply_markup)
    elif kind == "animation" and fid:
        await bot.send_animation(chat_id, fid, caption=cap, reply_markup=reply_markup)
    elif kind == "video" and fid:
        await bot.send_video(chat_id, fid, caption=cap, reply_markup=reply_markup)
    else:
        await bot.send_message(chat_id, cap, reply_markup=reply_markup)

@dp.message(Command("subscriptions"))
async def cmd_subs(m:Message):
    await m.answer("Чтобы подключить канал, добавьте бота в канал (в приватном — админом), "
                   "затем перешлите сюда любой пост канала или отправьте @username канала.")


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
            await show_active_stats(cq.message, gid)  # Передаем message вместо cq
        elif gw.status in (GiveawayStatus.FINISHED, GiveawayStatus.CANCELLED):
            await show_finished_stats(cq.message, gid)  # Передаем message вместо cq
        else:
            await cq.answer("Статистика недоступна для этого статуса.", show_alert=True)
    
    await cq.answer()


# === Полноценный экспорт статистики в CSV файл ===

@dp.callback_query(F.data.startswith("stats:csv:"))
@premium_only
async def cb_csv_export(cq: CallbackQuery):
    """
    Выгрузка статистики в CSV файл - ТОЛЬКО для premium пользователей
    Для standard пользователей показывается pop-up через декоратор
    """
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

    text_block = build_connect_channels_text(gw.internal_title, attached_list)
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
    INVISIBLE = "\u2060"
    await cq.message.answer(INVISIBLE, reply_markup=chooser_reply_kb())
    await cq.answer()

@dp.callback_query(F.data.startswith("raffle:add_group:"))
async def cb_add_group(cq: CallbackQuery, state: FSMContext):
    _, _, sid = cq.data.split(":")
    await state.update_data(chooser_event_id=int(sid))

    await cq.message.answer(ADD_CHAT_HELP_HTML, parse_mode="HTML", reply_markup=kb_add_cancel())
    INVISIBLE = "\u2060"
    await cq.message.answer(INVISIBLE, reply_markup=chooser_reply_kb())
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
    # 🔄 КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: используем время КАК ЕГО ВВЕЛ ПОЛЬЗОВАТЕЛЬ
    end_at_msk_dt = gw.end_at_utc.astimezone(MSK_TZ)
    end_at_msk_str = end_at_msk_dt.strftime("%H:%M %d.%m.%Y")
    
    # 🔄 ИСПРАВЛЕНИЕ: правильно вычисляем дни
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

    # 6) публикуем в каждом чате — С клавиатурой «Участвовать» и попыткой link-preview
    kind, file_id = unpack_media(gw.photo_file_id)
    
    # 🔄 ДОБАВЛЕНО: сохраняем message_id для каждого чата
    message_ids = {}  # {chat_id: message_id}
    
    for chat_id in chat_ids:
        try:
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
                    full_text = f"{hidden_link}\n\n{preview_text}"
                else:
                    full_text = f"{preview_text}\n\n{hidden_link}"

                lp = LinkPreviewOptions(
                    is_disabled=False,
                    prefer_large_media=True,
                    prefer_small_media=False,
                    show_above_text=(media_position == "top"),
                    url=preview_url
                )

                # Сохраняем результат отправки
                # ЕСЛИ ЕСТЬ МЕДИА - НИКОГДА НЕ ОТКЛЮЧАЕМ ПРЕВЬЮ!
                sent_msg = await bot.send_message(
                    chat_id,
                    full_text,
                    link_preview_options=lp,
                    parse_mode="HTML",
                    reply_markup=kb_public_participate(gid, for_channel=True),
                )
                message_ids[chat_id] = sent_msg.message_id
                logging.info(f"💾 Сохранен message_id {sent_msg.message_id} для чата {chat_id}")

                
            else:
                # медиа нет — обычный текст + кнопка
                # 🔄 ИЗМЕНЕНО: сохраняем результат отправки
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
                logging.info(f"💾 Сохранен message_id {sent_msg.message_id} для чата {chat_id}")

        except Exception as e:
            logging.warning("Link-preview не вышел в чате %s (%s), пробую fallback-медиа...", chat_id, e)
            # --- Fallback: нативное медиа с той же подписью + кнопка ---
            try:
                if kind == "photo" and file_id:
                    # ЕСЛИ ЕСТЬ МЕДИА - НИКОГДА НЕ ОТКЛЮЧАЕМ ПРЕВЬЮ!
                    sent_msg = await bot.send_photo(chat_id, file_id, caption=preview_text, reply_markup=kb_public_participate(gid, for_channel=True))
                    message_ids[chat_id] = sent_msg.message_id
                elif kind == "animation" and file_id:
                    sent_msg = await bot.send_animation(chat_id, file_id, caption=preview_text, reply_markup=kb_public_participate(gid, for_channel=True))
                    message_ids[chat_id] = sent_msg.message_id
                elif kind == "video" and file_id:
                    sent_msg = await bot.send_video(chat_id, file_id, caption=preview_text, reply_markup=kb_public_participate(gid, for_channel=True))
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


    # 🔄 ДОБАВЛЕНО: Сохраняем message_id в БД
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
    await cq.message.answer(f"✅ Розыгрыш <b>{title_html}</b> запущен!")
    await cq.message.answer(
    "Подпишитесь на канал, где команда публикует важные новости о боте и анонсы нового функционала:\n"
    "https://t.me/prizeme_official_news"
)

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

@dp.callback_query(F.data.startswith("raffle:mechanics_disabled:"))
async def cb_mechanics_disabled(cq: CallbackQuery):
    """
    Pop-up для кнопки "Дополнительные механики"
    """
    await cq.answer("В разработке", show_alert=True)

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

@dp.callback_query(F.data.startswith("settings:winners:"))
async def cb_settings_winners(cq: CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Количество победителей' в настройках"""
    gid = int(cq.data.split(":")[2])
    
    await state.update_data(
        editing_giveaway_id=gid,
        setting_type="winners",
        return_context="settings"
    )
    
    await state.set_state(EditFlow.EDIT_WINNERS)
    await cq.message.answer(
        "Укажите новое количество победителей в этом розыгрыше от 1 до 50 "
        "(введите только число, не указывая других символов):"
    )
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

@dp.callback_query(F.data.startswith("u:join:"))
async def user_join(cq:CallbackQuery):
    gid = int(cq.data.split(":")[2])
    async with session_scope() as s:
        gw = await s.get(Giveaway, gid)
        if gw.status != GiveawayStatus.ACTIVE:
            await cq.answer("Розыгрыш не активен.", show_alert=True); return
    
    #Регистрируем пользователя при участии
    try:
        await ensure_bot_user(cq.from_user.id, cq.from_user.username, cq.from_user.first_name)
        logging.info(f"✅ Пользователь {cq.from_user.id} зарегистрирован при участии в розыгрыше")
    except Exception as e:
        logging.error(f"❌ Ошибка регистрации при участии: {e}")

    ok, details = await check_membership_on_all(bot, cq.from_user.id, gid)
    if not ok:
        await cq.answer("Подпишитесь на все каналы и попробуйте снова.", show_alert=True); return
    async with session_scope() as s:
        res = await s.execute(stext("SELECT ticket_code FROM entries WHERE giveaway_id=:gid AND user_id=:u"),
                              {"gid":gid, "u":cq.from_user.id})
        row = res.first()
        if row: code = row[0]
        else:
            for _ in range(5):
                code = gen_ticket_code()
                try:
                    await s.execute(stext(
                        "INSERT INTO entries(giveaway_id,user_id,ticket_code,prelim_ok,prelim_checked_at) "
                        "VALUES (:gid,:u,:code,1,:ts)"
                    ),{"gid":gid,"u":cq.from_user.id,"code":code,"ts":datetime.now(timezone.utc)})
                    break
                except Exception:
                    continue
    await cq.message.answer(f"Ваш билет на розыгрыш: <b>{code}</b>")

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

    print(f"✅✅✅ FINALIZE_AND_DRAW_JOB ЗАВЕРШЕНА для розыгрыша {giveaway_id}")


async def notify_organizer(gid: int, winners: list, eligible_count: int, bot_instance: Bot):
    """Уведомление организатора о результатах розыгрыша"""
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
            
            # Кнопка "Выгрузить CSV" для организатора            
            kb = InlineKeyboardBuilder()
            kb.button(text="📥 Выгрузить CSV", callback_data=f"stats:csv:{gid}")
            kb.adjust(1)
            
            print(f"📤 Отправляем уведомление организатору {gw.owner_user_id}")
            await bot_instance.send_message(
                gw.owner_user_id, 
                message_text,
                reply_markup=kb.as_markup()
            )
            print(f"✅ Организатор уведомлен")
            
    except Exception as e:
        print(f"❌ Ошибка уведомления организатора для розыгрыша {gid}: {e}")
    

async def notify_participants(gid: int, winners: list, eligible_entries: list, bot_instance: Bot):
    """Уведомление всех участников о результатах розыгрыша"""
    try:
        print(f"📨 Уведомляем участников розыгрыша {gid}")
        
        # 🔄 ПОЛУЧАЕМ BOT_USERNAME из бота
        bot_info = await bot_instance.get_me()
        BOT_USERNAME = bot_info.username
        print(f"🔍 DEBUG: BOT_USERNAME получен: @{BOT_USERNAME}")
        
        async with session_scope() as s:
            gw = await s.get(Giveaway, gid)
            if not gw:
                print(f"❌ Розыгрыш {gid} не найден для уведомления участников")
                return
            
            winner_ids = [winner[0] for winner in winners]  # winner[0] = user_id
            
            # Получаем username победителей для списка
            winner_usernames = []
            for winner_id in winner_ids:
                try:
                    user = await bot_instance.get_chat(winner_id)
                    username = f"@{user.username}" if user.username else f"победитель (ID: {winner_id})"
                    winner_usernames.append(username)
                except Exception:
                    winner_usernames.append(f"победитель (ID: {winner_id})")
            
            winners_list_text = ", ".join(winner_usernames) if winner_usernames else "победители не определены"
            
            print(f"🔍 Получаем билеты участников для розыгрыша {gid}")
            participant_tickets = {}
            res = await s.execute(
                text("SELECT user_id, ticket_code FROM entries WHERE giveaway_id = :gid"),
                {"gid": gid}
            )
            for row in res.all():
                participant_tickets[row[0]] = row[1]
            print(f"🔍 Найдено билетов в базе: {len(participant_tickets)}")
            
            # Уведомляем всех участников
            notified_count = 0
            for user_id, _ in eligible_entries:
                try:
                    ticket_code = participant_tickets.get(user_id, "неизвестен")
                    print(f"🔍 Участник {user_id}, билет: {ticket_code}")
                    
                    if user_id in winner_ids:
                        # Победитель
                        message_text = (
                            f"🎉 Поздравляем! Вы стали победителем в розыгрыше \"{gw.internal_title}\".\n\n"
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
                            reply_markup=kb.as_markup()
                        )
                        
                    else:
                        # Участник (не победитель)
                        message_text = (
                            f"🏁 Завершился розыгрыш \"{gw.internal_title}\".\n\n"
                            f"Ваш билет: <b>{ticket_code}</b>\n\n"
                            f"Мы случайным образом определили победителей и, к сожалению, "
                            f"Ваш билет не был выбран.\n\n"
                            f"Победители: {winners_list_text}\n\n"
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
                            reply_markup=kb.as_markup()
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


# --- Функции для редактирования постов ---
def _compose_finished_post_text(gw: Giveaway, winners: list, participants_count: int) -> str:
    """
    Формирует текст поста после завершения розыгрыша с жирным форматированием
    ИСПРАВЛЕННАЯ ВЕРСИЯ: правильное отображение времени БЕЗ ДВОЙНОЙ КОНВЕРТАЦИИ
    """
    # Правильная обработка времени
    end_at_utc = gw.end_at_utc
    if end_at_utc:
        print(f"🔍 ВРЕМЯ В _compose_finished_post_text:")
        print(f"🔍 - Исходное значение из БД: {end_at_utc}")
        
        # Время УЖЕ хранится в MSK - используем как есть БЕЗ конвертации
        end_at_str = end_at_utc.strftime("%H:%M, %d.%m.%Y")
        
        print(f"🔍 - Используем как есть (уже MSK): {end_at_str}")
    else:
        end_at_str = "не указана"
        print(f"🔍 ВРЕМЯ: не указано")

    lines = []
    
    # Добавляем описание розыгрыша если оно есть
    if gw.public_description and gw.public_description.strip():
        lines.append(f"{gw.public_description}")
        lines.append("")
    
    # Ключевые параметры с жирным форматированием
    lines.extend([
        f"Участников: <b>{participants_count}</b>",
        f"Призовых мест: <b>{gw.winners_count}</b>", 
        f"Дата розыгрыша: <b>{end_at_str} MSK (завершён)</b>",
        "",
        "<b>Победители розыгрыша:</b>"
    ])
    
    # Добавляем победителей
    if winners:
        for winner in winners:
            rank, username, ticket_code = winner
            display_name = f"@{username}" if username else f"Участник"
            lines.append(f"{rank}. {display_name} - {ticket_code}")
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
            
            # 🔄 КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: Подготавливаем link-preview URL для медиа
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
                    
                    # 🔄 КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: ОЧИСТКА ТЕКСТА ОТ ПОЛЬЗОВАТЕЛЬСКИХ ПРЕВЬЮ
                    has_media = bool(media_file_id)
                    cleaned_text, disable_preview = text_preview_cleaner.clean_text_preview(new_text, has_media)
                    
                    # 🔄 КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: РАЗДЕЛЕНИЕ ЛОГИКИ с link-preview
                    if has_media and preview_url:
                        print(f"🔍 Розыгрыш ИМЕЕТ медиа, используем link-preview с рамкой")
                        try:
                            # 🔄 ИСПРАВЛЕНИЕ: Определяем hidden_link ПЕРЕД использованием
                            hidden_link = f'<a href="{preview_url}"> </a>'
                            
                            # Используем сохраненную позицию медиа
                            media_position = gw.media_position if hasattr(gw, 'media_position') else 'bottom'
                            
                            if media_position == "top":
                                full_text_with_preview = f"{hidden_link}\n\n{cleaned_text}"
                            else:
                                full_text_with_preview = f"{cleaned_text}\n\n{hidden_link}"
                            
                            # Настройки link-preview (как при публикации)
                            lp = LinkPreviewOptions(
                                is_disabled=False,
                                prefer_large_media=True,
                                prefer_small_media=False,
                                show_above_text=(media_position == "top"),
                                url=preview_url
                            )
                            
                            # Пробуем отредактировать через edit_message_text с link-preview
                            # ЕСЛИ ЕСТЬ МЕДИА - НИКОГДА НЕ ОТКЛЮЧАЕМ ПРЕВЬЮ!
                            await bot_instance.edit_message_text(
                                chat_id=chat_id,
                                message_id=message_id,
                                text=full_text_with_preview,
                                parse_mode="HTML",
                                link_preview_options=lp,
                                reply_markup=reply_markup
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
                                full_text_with_preview = f"{cleaned_text}\n\n{hidden_link}"
                                
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
                            # Для постов с медиа редактируем только подпись с reply_markup
                            send_kwargs = {
                                "chat_id": chat_id,
                                "message_id": message_id,
                                "caption": cleaned_text,
                                "parse_mode": "HTML",
                                "reply_markup": reply_markup,
                            }
                            if disable_preview:
                                send_kwargs["disable_web_page_preview"] = True
                                
                            await bot_instance.edit_message_caption(**send_kwargs)
                            print(f"✅ Пост С МЕДИА отредактирован (caption) в чате {chat_id}")
                            success_count += 1
                            
                        except Exception as caption_error:
                            print(f"❌ Ошибка edit_message_caption: {caption_error}")
                    
                    else:
                        print(f"🔍 Розыгрыш БЕЗ медиа, используем edit_message_text")
                        # Для постов без медиа редактируем весь текст с reply_markup
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
        # 🔥 КРИТИЧЕСКИ ВАЖНО: Явная очистка памяти
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
                # КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: проверяем существование записи для ЭТОГО пользователя
                existing = await s.execute(
                    stext("SELECT id FROM organizer_channels WHERE owner_user_id=:user_id AND chat_id=:chat_id"),
                    {"user_id": user_id, "chat_id": chat.id}  # ✅ ИСПРАВЛЕНО: именованные параметры
                )
                existing_row = existing.first()
                
                if existing_row:
                    # Обновляем существующую запись
                    await s.execute(
                        stext("""
                            UPDATE organizer_channels 
                            SET title=:title, username=:username, is_private=:is_private, bot_role=:role, status='ok', added_at=:added_at
                            WHERE owner_user_id=:user_id AND chat_id=:chat_id
                        """),
                        {
                            "title": title, 
                            "username": username, 
                            "is_private": int(is_private), 
                            "role": status, 
                            "added_at": datetime.now(timezone.utc),
                            "user_id": user_id, 
                            "chat_id": chat.id
                        }  # ✅ ИСПРАВЛЕНО: именованные параметры
                    )
                else:
                    # Создаем новую запись для этого пользователя
                    await s.execute(
                        stext("""
                            INSERT INTO organizer_channels(
                                owner_user_id, chat_id, username, title, is_private, bot_role, status, added_at
                            ) VALUES (:user_id, :chat_id, :username, :title, :is_private, :role, 'ok', :added_at)
                        """),
                        {
                            "user_id": user_id,
                            "chat_id": chat.id, 
                            "username": username, 
                            "title": title, 
                            "is_private": int(is_private), 
                            "role": status,
                            "added_at": datetime.now(timezone.utc)
                        }  # ✅ ИСПРАВЛЕНО: именованные параметры
                    )
            else:
                # если бота удалили из чата - помечаем только для этого пользователя
                await s.execute(
                    stext("UPDATE organizer_channels SET status='gone' WHERE owner_user_id=:user_id AND chat_id=:chat_id"),
                    {"user_id": user_id, "chat_id": chat_id},
                )

    logging.info(f"🔁 my_chat_member: user={user_id}, chat={chat.title} ({chat.id}) -> {status}")

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
                full_text = f"{hidden_link}\n\n{post_text}"
            else:
                full_text = f"{post_text}\n\n{hidden_link}"

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


# --- ФУНКЦИИ СТАТИСТИКИ ДЛЯ СОЗДАТЕЛЯ ---

async def show_finished_stats(message: Message, giveaway_id: int):
    """Показывает статистику завершенного розыгрыша КАК НОВОЕ СООБЩЕНИЕ"""
    async with session_scope() as s:
        # Получаем данные розыгрыша
        gw = await s.get(Giveaway, giveaway_id)
        if not gw:
            await message.answer("Розыгрыш не найден.")
            return

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
    user_status = await get_user_status(message.from_user.id)
    
    if user_status == 'premium':
        # Premium пользователи видят кнопку с алмазом
        kb.button(text="💎📥 Выгрузить CSV", callback_data=f"stats:csv:{giveaway_id}")
    else:
        # Standard пользователи видят заблокированную кнопку
        kb.button(text="🔒📥 Выгрузить CSV", callback_data=f"premium_required:{giveaway_id}")
    
    kb.button(text="⬅️ Назад", callback_data="close_message")
    kb.adjust(1)

    # Отправляем как новое сообщение
    await message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")

async def show_active_stats(message: Message, giveaway_id: int):
    """Показывает статистику активного розыгрыша КАК НОВОЕ СООБЩЕНИЕ"""
    async with session_scope() as s:
        # Получаем данные розыгрыша
        gw = await s.get(Giveaway, giveaway_id)
        if not gw:
            await message.answer("Розыгрыш не найден.")
            return

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
    user_status = await get_user_status(message.from_user.id)
    
    if user_status == 'premium':
        # Premium пользователи видят кнопку с алмазом
        kb.button(text="💎📥 Выгрузить CSV", callback_data=f"stats:csv:{giveaway_id}")
    else:
        # Standard пользователи видят заблокированную кнопку
        kb.button(text="🔒📥 Выгрузить CSV", callback_data=f"premium_required:{giveaway_id}")
    
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
    """
    Показывает pop-up с предложением оформить подписку
    """
    await cq.answer(
        "💎 Оформите подписку ПРЕМИУМ для доступа к функционалу",
        show_alert=True
    )


# ---------------- ENTRYPOINT ----------------
async def main():
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    # 1) инициализация БД
    await init_db()
    await ensure_schema()
    logging.info("✅ База данных инициализирована")
    logging.info("✅ База данных PostgreSQL инициализирована")

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
            for _ in range(5):
                ticket = gen_ticket_code()
                try:
                    await s.execute(stext(
                        "INSERT INTO entries(giveaway_id,user_id,ticket_code,prelim_ok,prelim_checked_at) "
                        "VALUES (:g,:u,:code,1,:ts)"
                    ), {
                        "g": giveaway_id,
                        "u": user_id,
                        "code": ticket,
                        "ts": datetime.now(timezone.utc)
                    })
                    break
                except Exception:
                    # коллизия кода — попробуем ещё раз
                    continue

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

    app.router.add_post("/api/giveaway_info", giveaway_info)
    app.router.add_post("/api/claim_ticket", claim_ticket)
    app.router.add_post("/api/giveaway_results", giveaway_results)
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