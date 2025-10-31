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
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger

import aiohttp
from aiohttp import web
from aiohttp import ClientSession, ClientTimeout, FormData

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
load_dotenv()

MEDIA_BASE_URL = os.getenv("MEDIA_BASE_URL", "https://media.prizeme.ru")
WEBAPP_BASE_URL = os.getenv("WEBAPP_BASE_URL", "https://prizeme.ru")


DESCRIPTION_PROMPT = (
    "<b>Введите текст подробного описания розыгрыша:</b>\n\n"
    "Можно использовать не более 2500 символов.\n\n"
    "<i>Подробно опишите условия розыгрыша для ваших подписчиков.\n"
    "После начала розыгрыша введённый текст будет опубликован\n"
    "на всех связанных с ним каналах.</i>")

MEDIA_QUESTION = "Хотите ли добавить изображение / gif / видео для текущего розыгрыша?"

MEDIA_INSTRUCTION = (
    "<b>Отправьте изображение / <i>gif</i> / видео для текущего розыгрыша.</b>\n\n"
    "<i>Используйте стандартную доставку. Не отправляйте \"несжатым\" способом (НЕ как документ).</i>\n\n"
    "<b>Внимание!</b> Видео должно быть в формате MP4, а его размер не должен превышать 5 МБ."
)

BTN_EVENTS = "Мои розыгрыши"
BTN_CREATE = "Создать розыгрыш"
BTN_ADD_CHANNEL = "Добавить канал"
BTN_ADD_GROUP = "Добавить группу"
BTN_SUBSCRIPTIONS = "Подписки"
BOT_USERNAME: str | None = None

# === callbacks for draft flow ===
CB_PREVIEW_CONTINUE = "preview:continue"
CB_TO_CHANNELS_MENU = "draft:to_channels"
CB_OPEN_CHANNELS    = "channels:open"
CB_CHANNEL_ADD      = "channels:add"          # уже используется у тебя? оставь свой
CB_CHANNEL_START    = "raffle:start"          # заглушка на будущее
CB_CHANNEL_SETTINGS = "raffle:settings"       # пока неактивна

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

def kb_add_cancel() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Отмена", callback_data="add:cancel")
    kb.adjust(1)
    return kb.as_markup()

# ---- Другое ----

if not all([S3_ENDPOINT, S3_BUCKET, S3_KEY, S3_SECRET]):
    logging.warning("S3 env not fully set — uploads will fail.")


# Тексты экранов_2

def build_connect_invite_kb(event_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    # NB: в callback передаём id розыгрыша, чтобы потом понимать, к какому событию подключаем каналы
    kb.button(text="Добавить канал/группу", callback_data=f"raffle:connect_channels:{event_id}")
    return kb.as_markup()

# Экран с уже подключенными каналами и действиями
def build_connect_channels_text(
    event_title: str | None = None,
    attached: list[tuple[str, str | None, int]] | None = None,  # (title, username, chat_id)
) -> str:
    """
    Собирает "серый" текстовый блок.
    attached — список уже прикреплённых к текущему розыгрышу каналов/групп:
               (title, username_or_None, chat_id)
    Если есть username — делаем кликабельную ссылку, иначе просто название.
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
            if uname:
                lines.append(f"{i}. <a href=\"https://t.me/{uname}\">{t}</a>")
            else:
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
    kb.row(InlineKeyboardButton(text="Настройки розыгрыша", callback_data=f"raffle:settings_disabled:{event_id}"))
    kb.row(InlineKeyboardButton(text="Запустить розыгрыш", callback_data=f"raffle:start:{event_id}"))

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
    kb.button(text="Настройки розыгрыша", callback_data=f"raffle:settings_disabled:{gid}")
    kb.adjust(1)
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
        msg = await m.answer_photo(fid, caption=caption, reply_markup=kb_media_preview(media_on_top=False))
    elif kind == "animation":
        msg = await m.answer_animation(fid, caption=caption, reply_markup=kb_media_preview(media_on_top=False))
    else:
        msg = await m.answer_video(fid, caption=caption, reply_markup=kb_media_preview(media_on_top=False))

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
    - title показываем обычным текстом (без <b>), чтобы не навязывать жирный.
    - desc_html вставляем как есть (пользовательское оформление сохраняется).
    - дата берётся из введённой пользователем + "(N дней)" по-русски.
    """
    lines = []
    if title:
        # без <b> — не навязываем жирный
        lines.append(escape(title))
        lines.append("")

    if desc_html:
        # ВАЖНО: это уже «HTML», не оборачиваем в <b>, не экранируем повторно.
        # Если хочешь жёстко ограничить теги — сделай лёгкую валидацию выше.
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
    media     = data.get("media_url")
    media_top = bool(data.get("media_top") or False)

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
        await m.answer(txt)
        return

    hidden_link = f'<a href="{media}">&#8203;</a>'
    full = f"{hidden_link}\n\n{txt}" if media_top else f"{txt}\n\n{hidden_link}"

    lp = LinkPreviewOptions(
        is_disabled=False,
        prefer_large_media=True,
        prefer_small_media=False,
        show_above_text=media_top,
    )

    old_id = data.get("media_preview_msg_id")
    if reedit and old_id:
        try:
            await m.bot.edit_message_text(
                chat_id=m.chat.id,
                message_id=old_id,
                text=full,
                link_preview_options=lp,
                reply_markup=kb_media_preview(media_top),
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

    msg = await m.answer(
        full,
        link_preview_options=lp,
        reply_markup=kb_media_preview(media_top),
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

    # если до этого уже рисовали предпросмотр — аккуратно удалим
    prev_id = data.get("media_preview_msg_id")
    if prev_id and not reedit:
        try:
            await m.bot.delete_message(chat_id=m.chat.id, message_id=prev_id)
        except Exception:
            pass

    msg = await m.answer(txt, reply_markup=kb_preview_no_media(), parse_mode="HTML")
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
    # 1) считаем дату и "N дней", собираем текст предпросмотра
    end_at_msk_dt = gw.end_at_utc.astimezone(MSK_TZ)
    end_at_msk_str = end_at_msk_dt.strftime("%H:%M %d.%m.%Y")
    days_left = max(0, (end_at_msk_dt.date() - datetime.now(MSK_TZ).date()).days)

    preview_text = _compose_preview_text(
        "",                               # заголовок в предпросмотре не используем
        gw.winners_count,
        desc_html=(gw.public_description or ""),
        end_at_msk=end_at_msk_str,
        days_left=days_left,
    )

    # 2) если медиа нет — просто текст
    kind, fid = unpack_media(gw.photo_file_id)
    if not fid:
        await m.answer(preview_text)
        return

    # 3) пробуем сделать link-preview как в обычном предпросмотре
    #    (повторная выгрузка в S3 допустима; если не получится — fallback)
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

        # скрытая ссылка + опции link preview (медиа показываем СНИЗУ — как в дефолте предпросмотра)
        hidden_link = f'<a href="{preview_url}">&#8203;</a>'
        full_text = f"{preview_text}\n\n{hidden_link}"

        lp = LinkPreviewOptions(
            is_disabled=False,
            prefer_large_media=True,
            prefer_small_media=False,
            show_above_text=False,  # как в нашем обычном предпросмотре "медиа снизу" по умолчанию
        )

        await m.answer(full_text, link_preview_options=lp, parse_mode="HTML")

    except Exception:
        # 4) fallback — отдать нативно (фото/гиф/видео) с той же подписью
        try:
            if kind == "photo":
                await m.answer_photo(fid, caption=preview_text)
            elif kind == "animation":
                await m.answer_animation(fid, caption=preview_text)
            elif kind == "video":
                await m.answer_video(fid, caption=preview_text)
            else:
                await m.answer(preview_text)
        except Exception:
            await m.answer(preview_text)

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

# путь к bot.db строго рядом с bot.py (один файл для всех)
DB_PATH = Path(os.getenv("DB_PATH") or Path(__file__).with_name("bot.db")).resolve()
DB_URL  = f"sqlite+aiosqlite:///{DB_PATH.as_posix()}"

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
engine = create_async_engine(DB_URL, echo=True, future=True)
Session = async_sessionmaker(engine, expire_on_commit=False)

async def mark_membership(chat_id: int, user_id: int) -> None:
    async with Session() as s:
        async with s.begin():
            await s.execute(
                _sqltext(
                    "INSERT OR IGNORE INTO channel_memberships(chat_id, user_id) "
                    "VALUES (:c, :u)"
                ),
                {"c": chat_id, "u": user_id},
            )

async def is_member_local(chat_id: int, user_id: int) -> bool:
    async with Session() as s:
        r = await s.execute(
            _sqltext(
                "SELECT 1 FROM channel_memberships WHERE chat_id=:c AND user_id=:u"
            ),
            {"c": chat_id, "u": user_id},
        )
        return r.first() is not None

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
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_user_id BIGINT   NOT NULL,
            chat_id       BIGINT   NOT NULL,
            username      TEXT,
            title         TEXT     NOT NULL,
            is_private    BOOLEAN  NOT NULL DEFAULT 0,
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
        res = await s.execute(text("SELECT title, chat_id FROM giveaway_channels WHERE giveaway_id=:gid"),{"gid":giveaway_id})
        rows = res.all()
    details=[]; all_ok=True
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
def kb_media_preview(media_on_top: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Изменить изображение/gif/видео", callback_data="preview:change")
    if media_on_top:
        kb.button(text="Показывать медиа снизу", callback_data="preview:move:down")
    else:
        kb.button(text="Показывать медиа сверху", callback_data="preview:move:up")
    kb.button(text="Продолжить", callback_data="preview:continue")
    kb.adjust(1)
    return kb.as_markup()

#--- Клавиатура для предпросмотра БЕЗ медиа ---
def kb_preview_no_media() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Добавить изображение/gif/видео", callback_data="preview:add_media")
    kb.button(text="Продолжить", callback_data="preview:continue")
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

async def save_shared_chat(
    *,
    owner_user_id: int,
    chat_id: int,
    title: str,
    chat_type: str,
    bot_role: str
) -> bool:
    """
    Возвращает True, если вставка сделана впервые; False, если такой канал уже был.
    """
    # is_private = True для групп/супергрупп, False для каналов
    is_private = chat_type in (ChatType.GROUP, ChatType.SUPERGROUP)

    async with Session() as s:
        async with s.begin():
            # пробуем вставить; если дубликат — просто игнор
            await s.execute(
                """
                INSERT OR IGNORE INTO organizer_channels
                    (owner_user_id, chat_id, title, is_private, bot_role)
                VALUES (?, ?, ?, ?, ?)
                """,
                (owner_user_id, chat_id, title, int(is_private), bot_role)
            )
        # проверим, появилась ли запись
        res = await s.execute(
            "SELECT 1 FROM organizer_channels WHERE owner_user_id=? AND chat_id=?",
            (owner_user_id, chat_id)
        )
        return res.scalar() is not None

# ----------------- FSM -----------------
from aiogram.fsm.state import StatesGroup, State

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
    can_manage_chat=True,
    can_post_messages=True,
    can_edit_messages=True,
    can_delete_messages=True,
    can_invite_users=True,
    can_restrict_members=True,
    can_promote_members=True,
    can_change_info=True,
    can_pin_messages=True,
    can_manage_topics=True,
    can_post_stories=False,
    can_edit_stories=False,
    can_delete_stories=False,
    can_manage_video_chats=True,
)

async def set_bot_commands(bot: Bot):
    commands = [
        BotCommand(command="start", description="перезапустить бота"),
        BotCommand(command="create", description="создать розыгрыш"),
        BotCommand(command="events", description="мои розыгрыши"),
        BotCommand(command="subscriptions", description="подписки"),
        # можно позже добавить: help, menu и др.
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

    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_EVENTS), KeyboardButton(text=BTN_CREATE)],
            [btn_add_channel, btn_add_group],
            [KeyboardButton(text=BTN_SUBSCRIPTIONS)],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Сообщение",
    )

def chooser_reply_kb() -> ReplyKeyboardMarkup:
    btn_add_channel = KeyboardButton(
        text=BTN_ADD_CHANNEL,
        request_chat=KeyboardButtonRequestChat(
            request_id=101,  # любое число
            chat_is_channel=True,
            bot_administrator_rights=CHAN_ADMIN_RIGHTS,
            user_administrator_rights=CHAN_ADMIN_RIGHTS,
        )
    )
    btn_add_group = KeyboardButton(
        text=BTN_ADD_GROUP,
        request_chat=KeyboardButtonRequestChat(
            request_id=102,
            chat_is_channel=False,
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
    is_private = 0 if username else 1  # каналы с @username считаем публичными

    # 1) upsert (вставка/обновление без дублей по (owner_user_id, chat_id))
    async with Session() as s:
        async with s.begin():
            await s.execute(
                stext(
                    "INSERT OR REPLACE INTO organizer_channels("
                    "owner_user_id, chat_id, username, title, is_private, bot_role, status, added_at"
                    ") VALUES (:o, :cid, :u, :t, :p, :r, 'ok', :ts)"
                ),
                {
                    "o": m.from_user.id,
                    "cid": chat.id,
                    "u": username,
                    "t": title,
                    "p": int(is_private),
                    "r": role,
                    "ts": datetime.now(timezone.utc),
                },
            )

        # 2) сразу читаем ту же запись (той же сессией)
        res = await s.execute(
            stext(
                "SELECT id, owner_user_id, chat_id, title, status "
                "FROM organizer_channels "
                "WHERE owner_user_id=:o AND chat_id=:cid"
            ),
            {"o": m.from_user.id, "cid": chat.id},
        )
        row = res.first()

    logging.info("📦 saved channel row=%s", row)

    kind = "канал" if chat.type == "channel" else "группа"
    await m.answer(
        f"{kind.capitalize()} <b>{title}</b> подключён к боту.",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove(),
    )

    # Если запись не нашлась — сразу подсветим проблему пользователю и выйдем
    if not row:
        return

    # Если сейчас идёт привязка к конкретному розыгрышу — перерисуем экран привязки
    data = await state.get_data()
    event_id = data.get("chooser_event_id")
    if event_id:
        async with session_scope() as s:
            gw = await s.get(Giveaway, event_id)
            res = await s.execute(stext("SELECT id, title FROM organizer_channels WHERE owner_user_id=:u"),
                                  {"u": gw.owner_user_id})
            channels = [(r[0], r[1]) for r in res.all()]
            res = await s.execute(stext("SELECT channel_id FROM giveaway_channels WHERE giveaway_id=:g"),
                                  {"g": event_id})
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
    if status==GiveawayStatus.DRAFT:
        kb.button(text="Подключить каналы", callback_data=f"ev:channels:{gid}")
        kb.button(text="Запустить (Launch)", callback_data=f"ev:launch:{gid}")
        kb.button(text="Удалить", callback_data=f"ev:delete:{gid}")
    elif status==GiveawayStatus.ACTIVE:
        kb.button(text="Отменить (Cancel)", callback_data=f"ev:cancel:{gid}")
        kb.button(text="Статус", callback_data=f"ev:status:{gid}")
    elif status in (GiveawayStatus.FINISHED, GiveawayStatus.CANCELLED):
        kb.button(text="Отчёт", callback_data=f"ev:status:{gid}")
    kb.button(text="Назад", callback_data="my_events")
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
def kb_my_events_menu(count_involved:int, count_finished:int, my_draft:int, my_finished:int):
    kb = InlineKeyboardBuilder()
    kb.button(text=f"В которых участвую ({count_involved})", callback_data="mev:involved")
    kb.button(text=f"Завершённые розыгрыши ({count_finished})", callback_data="mev:finished")
    kb.button(text=f"Мои незапущенные ({my_draft})", callback_data="mev:my_drafts")
    kb.button(text=f"Мои завершённые ({my_finished})", callback_data="mev:my_finished")
    kb.button(text="Создать розыгрыш", callback_data="create")
    kb.button(text="Мои каналы", callback_data="my_channels")
    kb.adjust(1)
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

async def show_my_events_menu(m: Message):
    """Собираем счётчики и показываем 6 кнопок-меню."""
    uid = m.from_user.id
    async with session_scope() as s:
        # в которых участвую — уникальные активные/завершённые, где у пользователя есть entries
        res = await s.execute(stext(
            "SELECT COUNT(DISTINCT g.id) "
            "FROM entries e JOIN giveaways g ON g.id=e.giveaway_id "
            "WHERE e.user_id=:u"
        ), {"u": uid})
        count_involved = res.scalar_one() or 0

        # завершённые вообще (по системе)
        res = await s.execute(stext(
            "SELECT COUNT(*) FROM giveaways WHERE status='finished'"
        ))
        count_finished = res.scalar_one() or 0

        # мои незапущенные (черновики) и мои завершённые
        res = await s.execute(stext(
            "SELECT "
            "SUM(CASE WHEN status='draft' THEN 1 ELSE 0 END), "
            "SUM(CASE WHEN status='finished' THEN 1 ELSE 0 END) "
            "FROM giveaways WHERE owner_user_id=:u"
        ), {"u": uid})
        row = res.first()
        my_draft = int(row[0] or 0)
        my_finished = int(row[1] or 0)

    text = "Розыгрыши:"
    await m.answer(text, reply_markup=kb_my_events_menu(count_involved, count_finished, my_draft, my_finished))

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

# "Мои розыгрыши" -> используем ваш cmd_events
@dp.message(F.text == BTN_EVENTS)
async def on_btn_events(m: Message, state: FSMContext):
    await show_my_events_menu(m)

# "Новый розыгрыш" -> ваш create_giveaway_start
@dp.message(F.text == BTN_CREATE)
async def on_btn_create(m: Message, state: FSMContext):
    await create_giveaway_start(m, state)

# "Подписки" -> ваш cmd_subs
@dp.message(F.text == BTN_SUBSCRIPTIONS)
async def on_btn_subs(m: Message, state: FSMContext):
    await cmd_subs(m)

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
    text = (m.text or "").strip()
    if len(text) > 2500:
        await m.answer("⚠️ Слишком длинно. Укороти до 2500 символов и пришли ещё раз.")
        return

    # сохраняем описание
    await state.update_data(desc=text)

    # показываем предпросмотр + кнопки
    preview = f"<b>Предпросмотр описания:</b>\n\n{escape(text)}"
    await m.answer(preview, parse_mode="HTML", reply_markup=kb_confirm_description())

    # переходим в состояние подтверждения
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


# Пользователь всё равно может прислать текст «пропустить»
@dp.message(CreateFlow.MEDIA_UPLOAD, F.text.casefold() == "пропустить")
async def media_skip_by_text(m: Message, state: FSMContext):
    await state.set_state(CreateFlow.ENDAT)
    await m.answer(format_endtime_prompt(), parse_mode="HTML")

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
    ВРЕМЕННЫЙ УПРОЩЁННЫЙ ХЕЛПЕР.
    Берём по одной последней записи на каждый chat_id со статусом 'ok'
    и просто возвращаем (row_id, title) — без проверок админств.
    Задача: убедиться, что список вообще рисуется в боте.
    """
    async with Session() as s:
        res = await s.execute(
            stext(
                """
                SELECT oc.id, oc.title
                FROM organizer_channels oc
                JOIN (
                    SELECT chat_id, MAX(id) AS max_id
                    FROM organizer_channels
                    WHERE status='ok'
                    GROUP BY chat_id
                ) last ON last.max_id = oc.id
                ORDER BY oc.id DESC
                """
            )
        )
        rows = res.all()
    # rows -> [(id, title)]
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

# -----------------

@dp.message(Command("events"))
async def cmd_events(m: Message):
    async with session_scope() as s:
        res = await s.execute(
            text("SELECT id, internal_title, status FROM giveaways "
                 "WHERE owner_user_id=:u ORDER BY id DESC"),
            {"u": m.from_user.id}
        )
        row = res.first()

    if not row:
        await m.answer(
            "У вас пока нет розыгрышей. Вы можете создать новый розыгрыш и он появится здесь.",
            reply_markup=reply_main_kb()
        )
        return  # <- ВНУТРИ if

    # сюда попадём только если row есть
    await show_event_card(m.chat.id, row[0])

async def show_event_card(chat_id:int, giveaway_id:int):
    async with session_scope() as s:
        gw = await s.get(Giveaway, giveaway_id)

    cap = (f"<b>{gw.internal_title}</b>\n\n{gw.public_description}\n\n"
           f"Статус: {gw.status}\nПобедителей: {gw.winners_count}\n"
           f"Дата окончания: {(gw.end_at_utc+timedelta(hours=3)).strftime('%H:%M %d.%m.%Y MSK')}")

    kind, fid = unpack_media(gw.photo_file_id)

    if kind == "photo" and fid:
        await bot.send_photo(chat_id, fid, caption=cap, reply_markup=kb_event_actions(giveaway_id, gw.status))
    elif kind == "animation" and fid:
        await bot.send_animation(chat_id, fid, caption=cap, reply_markup=kb_event_actions(giveaway_id, gw.status))
    elif kind == "video" and fid:
        await bot.send_video(chat_id, fid, caption=cap, reply_markup=kb_event_actions(giveaway_id, gw.status))
    else:
        await bot.send_message(chat_id, cap, reply_markup=kb_event_actions(giveaway_id, gw.status))

@dp.message(Command("subscriptions"))
async def cmd_subs(m:Message):
    await m.answer("Чтобы подключить канал, добавьте бота в канал (в приватном — админом), "
                   "затем перешлите сюда любой пост канала или отправьте @username канала.")


from aiogram.utils.keyboard import InlineKeyboardBuilder

@dp.callback_query(F.data.startswith("ev:"))
async def event_cb(cq:CallbackQuery):
    _, action, sid = cq.data.split(":")
    gid = int(sid)
    if action=="channels":
        async with session_scope() as s:
            gw = await s.get(Giveaway, gid)
            res = await s.execute(stext("SELECT id, title, chat_id FROM organizer_channels WHERE owner_user_id=:u"),{"u":gw.owner_user_id})
            channels = res.all()
            if not channels:
                await cq.message.answer("Нет каналов. Сначала подключите через пересылку поста или @username."); return
            await s.execute(stext("DELETE FROM giveaway_channels WHERE giveaway_id=:gid"),{"gid":gid})
            for cid, title, chat_id in channels:
                await s.execute(stext("INSERT INTO giveaway_channels(giveaway_id,channel_id,chat_id,title) VALUES(:g,:c,:chat,:t)"),
                                {"g":gid,"c":cid,"chat":chat_id,"t":title})
        await cq.message.answer("Каналы привязаны. Теперь можно запускать.")
        await show_event_card(cq.message.chat.id, gid)

    elif action=="launch":
        gw = await _launch_and_publish(gid, cq.message)
        if not gw:
            await cq.answer("Розыгрыш не найден.", show_alert=True)
            return
        await cq.message.answer("Розыгрыш запущен.")
        await show_event_card(cq.message.chat.id, gid)

    elif action=="delete":
        async with session_scope() as s:
            gw = await s.get(Giveaway, gid)
            if gw.status != GiveawayStatus.DRAFT:
                await cq.answer("Удалять можно только черновик.", show_alert=True); return
            await s.execute(stext("DELETE FROM giveaways WHERE id=:gid"),{"gid":gid})
            await s.execute(stext("DELETE FROM giveaway_channels WHERE giveaway_id=:gid"),{"gid":gid})
        await cq.message.answer("Черновик удалён.")

    elif action=="status":
        await show_stats(cq.message.chat.id, gid)

    elif action=="cancel":
        await cancel_giveaway(gid, cq.from_user.id, reason=None)
        await cq.message.answer("Розыгрыш отменён.")
        await show_event_card(cq.message.chat.id, gid)

# ===== Карточка-превью медиа =====

@dp.callback_query(CreateFlow.MEDIA_PREVIEW, F.data == "preview:move:up")
async def preview_move_up(cq: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get("media_url"):
        await cq.answer("Перемещение доступно только в режиме предпросмотра с рамкой.", show_alert=True)
        return
    await state.update_data(media_top=True)
    await render_link_preview_message(cq.message, state, reedit=True)
    await cq.answer()

@dp.callback_query(CreateFlow.MEDIA_PREVIEW, F.data == "preview:move:down")
async def preview_move_down(cq: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get("media_url"):
        await cq.answer("Перемещение доступно только в режиме предпросмотра с рамкой.", show_alert=True)
        return
    await state.update_data(media_top=False)
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
        gw = Giveaway(
            owner_user_id=owner_id,
            internal_title=title,
            public_description=desc,
            photo_file_id=photo_id,
            end_at_utc=end_at,
            winners_count=winners,
            status=GiveawayStatus.DRAFT
        )
        s.add(gw)
        await s.flush()          # чтобы сразу появился gw.id
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
    Ничего пока не запускаем — показываем два блока:
      1) предпросмотр (точь-в-точь как при обычном предпросмотре, с link-preview или без медиа);
      2) финальный текст с кнопками «Запустить розыгрыш» / «Настройки розыгрыша».
    """
    _, _, sid = cq.data.split(":")
    gid = int(sid)

    # достаём розыгрыш
    async with session_scope() as s:
        gw = await s.get(Giveaway, gid)
        if not gw:
            await cq.answer("Розыгрыш не найден.", show_alert=True)
            return

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
      - публикуем пост БЕЗ КНОПОК в прикреплённых каналах/группах.
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

    # 2) планируем завершение
    try:
        run_dt = gw.end_at_utc  # UTC
        scheduler.add_job(
            func=finalize_and_draw_job,
            trigger=DateTrigger(run_date=run_dt),
            args=[gid],
            id=f"final_{gid}",
            replace_existing=True,
        )
        logging.info("Scheduled finalize job id=final_%s at %s (UTC)", gid, run_dt)
    except Exception as e:
        logging.warning("Не удалось запланировать завершение розыгрыша %s: %s", gid, e)

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
    end_at_msk_dt = gw.end_at_utc.astimezone(MSK_TZ)
    end_at_msk_str = end_at_msk_dt.strftime("%H:%M %d.%m.%Y")
    days_left = max(0, (end_at_msk_dt.date() - datetime.now(MSK_TZ).date()).days)

    # ВАЖНО: _compose_preview_text принимает позиционные аргументы: (title, prizes)
    preview_text = _compose_preview_text(
        "",
        gw.winners_count,
        desc_html=(gw.public_description or ""),
        end_at_msk=end_at_msk_str,
        days_left=days_left,
    )

    # 6) публикуем в каждом чате — С клавиатурой «Участвовать» и попыткой link-preview
    kind, file_id = unpack_media(gw.photo_file_id)
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

                hidden_link = f'<a href="{preview_url}">&#8203;</a>'
                full_text = f"{preview_text}\n\n{hidden_link}"

                lp = LinkPreviewOptions(
                    is_disabled=False,
                    prefer_large_media=True,
                    prefer_small_media=False,
                    show_above_text=False,  # медиа снизу, как в нашем дефолтном предпросмотре
                )

                await bot.send_message(
                    chat_id,
                    full_text,
                    link_preview_options=lp,
                    parse_mode="HTML",
                    reply_markup=kb_public_participate(gid, for_channel=True),
                )
            else:
                # медиа нет — обычный текст + кнопка
                await bot.send_message(
                    chat_id,
                    preview_text,
                    reply_markup=kb_public_participate(gid, for_channel=True),
                )

        except Exception as e:
            logging.warning("Link-preview не вышел в чате %s (%s), пробую fallback-медиа...", chat_id, e)
            # --- Fallback: нативное медиа с той же подписью + кнопка ---
            try:
                if kind == "photo" and file_id:
                    await bot.send_photo(chat_id, file_id, caption=preview_text, reply_markup=kb_public_participate(gid, for_channel=True))
                elif kind == "animation" and file_id:
                    await bot.send_animation(chat_id, file_id, caption=preview_text, reply_markup=kb_public_participate(gid, for_channel=True))
                elif kind == "video" and file_id:
                    await bot.send_video(chat_id, file_id, caption=preview_text, reply_markup=kb_public_participate(gid, for_channel=True))
                else:
                    await bot.send_message(
                        chat_id,
                        preview_text,
                        reply_markup=kb_public_participate(gid, for_channel=True),
                    )
            except Exception as e2:
                logging.warning("Публикация поста не удалась в чате %s: %s", chat_id, e2)

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

#--- Что=-то другое (узнать потом) ---

@dp.callback_query(F.data.startswith("raffle:settings_disabled:"))
async def cb_settings_disabled(cq: CallbackQuery):
    await cq.answer("Раздел «Настройки розыгрыша» скоро появится ✅", show_alert=True)


@dp.callback_query(F.data.startswith("raffle:noop:"))
async def cb_noop(cq: CallbackQuery):
    # Просто заглушка для кнопок-«индикаторов» подключённых каналов
    await cq.answer("Это информационная кнопка.")

async def show_stats(chat_id:int, gid:int):
    async with session_scope() as s:
        res = await s.execute(stext("SELECT COUNT(*) FROM entries WHERE giveaway_id=:gid"),{"gid":gid})
        total = res.scalar_one()
        res = await s.execute(stext("SELECT COUNT(*) FROM entries WHERE giveaway_id=:gid AND final_ok=1"),{"gid":gid})
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

async def finalize_and_draw_job(gid: int):
    """
    Финальная обработка розыгрыша: проверка подписок, определение победителей, уведомления
    """
    logging.info(f"🎯 Starting finalization for giveaway {gid}")
    
    try:
        # 1) Получаем данные розыгрыша
        async with session_scope() as s:
            gw = await s.get(Giveaway, gid)
            if not gw or gw.status != GiveawayStatus.ACTIVE:
                logging.warning(f"Giveaway {gid} not found or not active")
                return
            
            # 2) Получаем всех участников с prelim_ok=1
            res = await s.execute(stext(
                "SELECT user_id, id, ticket_code FROM entries WHERE giveaway_id=:gid AND prelim_ok=1"
            ), {"gid": gid})
            entries = res.all()
        
        logging.info(f"📊 Found {len(entries)} preliminary entries for giveaway {gid}")
        
        # 3) Финальная проверка подписок
        eligible = []
        eligible_entries = []
        
        for uid, entry_id, ticket_code in entries:
            ok, details = await check_membership_on_all(bot, uid, gid)
            async with session_scope() as s:
                await s.execute(stext(
                    "UPDATE entries SET final_ok=:ok, final_checked_at=:ts WHERE id=:eid"
                ), {"ok": 1 if ok else 0, "ts": datetime.now(timezone.utc), "eid": entry_id})
            
            if ok:
                eligible.append(uid)
                eligible_entries.append((uid, ticket_code))
                logging.info(f"✅ User {uid} eligible with ticket {ticket_code}")
            else:
                logging.info(f"❌ User {uid} not eligible")
        
        logging.info(f"🎯 Eligible users: {len(eligible)}")
        
        # 4) Детерминированный выбор победителей
        winners = []
        if eligible and gw.winners_count > 0:
            winners = deterministic_draw(gw.secret, gid, eligible, min(gw.winners_count, len(eligible)))
        
        # 5) Сохраняем победителей в базу
        async with session_scope() as s:
            rank = 1
            for uid, r, h in winners:
                await s.execute(stext(
                    "INSERT INTO winners(giveaway_id, user_id, rank, hash_used) VALUES(:g, :u, :r, :h)"
                ), {"g": gid, "u": uid, "r": rank, "h": h})
                rank += 1
            
            # Обновляем статус розыгрыша
            gw.status = GiveawayStatus.FINISHED
            s.add(gw)
        
        logging.info(f"🏆 Saved {len(winners)} winners for giveaway {gid}")
        
        # 6) Уведомление организатора
        await notify_organizer(gid, winners, len(eligible))
        
        # 7) Уведомление участников
        await notify_participants(gid, winners, eligible_entries)
        
        logging.info(f"✅ Giveaway {gid} finalized successfully")
        
    except Exception as e:
        logging.error(f"❌ Error finalizing giveaway {gid}: {e}")
        # Пытаемся уведомить организатора об ошибке
        try:
            async with session_scope() as s:
                gw = await s.get(Giveaway, gid)
                if gw:
                    await bot.send_message(
                        gw.owner_user_id,
                        f"❌ Произошла ошибка при завершении розыгрыша \"{gw.internal_title}\". "
                        f"Обратитесь в поддержку."
                    )
        except Exception as notify_error:
            logging.error(f"Failed to notify organizer about error: {notify_error}")

async def notify_organizer(gid: int, winners: list, eligible_count: int):
    """Уведомление организатора о результатах розыгрыша"""
    try:
        async with session_scope() as s:
            gw = await s.get(Giveaway, gid)
            if not gw:
                return
            
            # Получаем username победителей
            winner_usernames = []
            for winner in winners:
                uid = winner[0]  # (uid, rank, hash)
                try:
                    user = await bot.get_chat(uid)
                    username = f"@{user.username}" if user.username else f"ID: {uid}"
                    winner_usernames.append(f"{username}")
                except Exception as e:
                    winner_usernames.append(f"ID: {uid}")
                    logging.warning(f"Could not get username for {uid}: {e}")
            
            # Формируем сообщение
            if winner_usernames:
                winners_text = "\n".join([f"{i+1}. {name}" for i, name in enumerate(winner_usernames)])
                message = (
                    f"🎉 Розыгрыш \"{gw.internal_title}\" завершился!\n\n"
                    f"📊 Участников в финале: {eligible_count}\n"
                    f"🏆 Победителей: {len(winners)}\n\n"
                    f"Список победителей:\n{winners_text}\n\n"
                    f"Свяжитесь с победителями для вручения призов."
                )
            else:
                message = (
                    f"🎉 Розыгрыш \"{gw.internal_title}\" завершился!\n\n"
                    f"📊 Участников в финале: {eligible_count}\n"
                    f"🏆 Победителей: {len(winners)}\n\n"
                    "К сожалению, не удалось определить победителей."
                )
            
            await bot.send_message(gw.owner_user_id, message)
            logging.info(f"📨 Notified organizer about giveaway {gid}")
            
    except Exception as e:
        logging.error(f"❌ Error notifying organizer for giveaway {gid}: {e}")

async def notify_participants(gid: int, winners: list, eligible_entries: list):
    """Уведомление всех участников о результатах розыгрыша"""
    try:
        async with session_scope() as s:
            gw = await s.get(Giveaway, gid)
            if not gw:
                return
            
            winner_ids = [winner[0] for winner in winners]  # winner[0] = user_id
            
            # Получаем username победителей для списка
            winner_usernames = []
            for winner_id in winner_ids:
                try:
                    user = await bot.get_chat(winner_id)
                    username = f"@{user.username}" if user.username else f"победитель (ID: {winner_id})"
                    winner_usernames.append(username)
                except Exception:
                    winner_usernames.append(f"победитель (ID: {winner_id})")
            
            winners_list_text = ", ".join(winner_usernames) if winner_usernames else "победители не определены"
            
            # Уведомляем всех участников
            for user_id, ticket_code in eligible_entries:
                try:
                    if user_id in winner_ids:
                        # Победитель
                        message = (
                            f"🎉 Поздравляем! Вы стали победителем в розыгрыше \"{gw.internal_title}\".\n\n"
                            f"Ваш билет <b>{ticket_code}</b> оказался выбранным случайным образом.\n\n"
                            f"Организатор свяжется с вами для вручения приза."
                        )
                    else:
                        # Участник (не победитель)
                        message = (
                            f"🏁 Завершился розыгрыш \"{gw.internal_title}\".\n\n"
                            f"Ваш билет: <b>{ticket_code}</b>\n\n"
                            f"Мы случайным образом определили победителей и, к сожалению, "
                            f"Ваш билет не был выбран.\n\n"
                            f"Победители: {winners_list_text}\n\n"
                            f"Участвуйте в других розыгрышах!"
                        )
                    
                    await bot.send_message(user_id, message, parse_mode="HTML")
                    logging.info(f"📨 Notified user {user_id} about giveaway results")
                    
                    # Небольшая задержка чтобы не превысить лимиты Telegram
                    await asyncio.sleep(0.1)
                    
                except Exception as e:
                    logging.warning(f"Could not notify user {user_id}: {e}")
                    continue
                    
        logging.info(f"📨 Notified all participants of giveaway {gid}")
        
    except Exception as e:
        logging.error(f"❌ Error notifying participants for giveaway {gid}: {e}")

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

#--- Обработчик членов канала / группы ---
@dp.my_chat_member()
async def on_my_chat_member(event: ChatMemberUpdated):
    """
    Срабатывает, когда бота добавили или удалили из чата/канала.
    Обновляем базу, чтобы бот знал, где он админ.
    """
    chat = event.chat
    bot_id = event.new_chat_member.user.id
    if bot_id != (await bot.get_me()).id:
        return  # событие не для нас

    # обновлённый статус
    status = event.new_chat_member.status
    user = event.from_user
    title = chat.title or getattr(chat, "full_name", None) or "Без названия"
    username = getattr(chat, "username", None)
    is_private = 0 if username else 1

    async with Session() as s:
        async with s.begin():
            if status in ("administrator", "member"):
                # сохраняем или обновляем
                await s.execute(
                    stext("INSERT OR REPLACE INTO organizer_channels("
                            "owner_user_id, chat_id, username, title, is_private, bot_role, status, added_at"
                            ") VALUES (:o, :cid, :u, :t, :p, :r, 'ok', :ts)"),
                    {
                        "o": user.id if user else 0,
                        "cid": chat.id,
                        "u": username,
                        "t": title,
                        "p": int(is_private),
                        "r": status,
                        "ts": datetime.now(timezone.utc),
                    }
                )
            else:
                # если бота удалили из чата
                await s.execute(
                    stext("UPDATE organizer_channels SET status='gone' WHERE chat_id=:cid"),
                    {"cid": chat.id},
                )

    logging.info(f"🔁 my_chat_member: {chat.title} ({chat.id}) -> {status}")

# ---------------- ENTRYPOINT ----------------
async def main():
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    # 1) инициализация БД
    await init_db()
    await ensure_schema()
    logging.info("✅ База данных инициализирована")
    logging.info(f"DB file in use: {DB_PATH.resolve()}")

    # 2) запускаем планировщик
    scheduler.start()
    logging.info("✅ Планировщик запущен")

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

    app.router.add_post("/api/giveaway_info", giveaway_info)
    app.router.add_post("/api/claim_ticket", claim_ticket)
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