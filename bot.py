import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

import asyncio, os, hashlib, random, string
from datetime import datetime, timezone, timedelta
from contextlib import asynccontextmanager

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, StateFilter
from aiogram.types import (Message, CallbackQuery, InlineKeyboardMarkup,
                           InlineKeyboardButton, InputMediaPhoto)
from aiogram.types import BotCommand
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, KeyboardButtonRequestChat, ChatAdministratorRights
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.utils.keyboard import InlineKeyboardBuilder

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger

from sqlalchemy import (text, String, Integer, BigInteger,
                        Boolean, DateTime, ForeignKey)
from sqlalchemy.ext.asyncio import (create_async_engine, async_sessionmaker)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from html import escape
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
DEFAULT_TZ = os.getenv("TZ", "Europe/Moscow")
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

BTN_EVENTS = "Розыгрыши"
BTN_CREATE = "Создать розыгрыш"
BTN_ADD_CHANNEL = "Добавить канал"
BTN_ADD_GROUP = "Добавить группу"
BTN_SUBSCRIPTIONS = "Подписки"

MSK_TZ = ZoneInfo("Europe/Moscow")

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
    secret: Mapped[str|None] = mapped_column(String(128), nullable=True)   # хранится до раскрытия
    status: Mapped[str] = mapped_column(String(16), default=GiveawayStatus.DRAFT)
    tz: Mapped[str] = mapped_column(String(64), default=DEFAULT_TZ)
    cancelled_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_by: Mapped[int|None] = mapped_column(BigInteger, nullable=True)

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

# ----------------- DB INIT -----------------
DB_URL = "sqlite+aiosqlite:///./bot.db"
create_engine = create_async_engine = None  # placeholder to avoid confusion in this snippet
from sqlalchemy.ext.asyncio import create_async_engine
engine = create_async_engine(DB_URL, echo=False, future=True)
Session = async_sessionmaker(engine, expire_on_commit=False)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

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

async def check_membership_on_all(bot, user_id:int, giveaway_id:int):
    async with session_scope() as s:
        res = await s.execute(text("SELECT title, chat_id FROM giveaway_channels WHERE giveaway_id=:gid"),{"gid":giveaway_id})
        rows = res.all()
    details=[]; all_ok=True
    for title, chat_id in rows:
        try:
            m = await bot.get_chat_member(chat_id, user_id)
            ok = m.status in {"member","administrator","creator"}
        except Exception:
            ok = False
        details.append((title, ok))
        all_ok = all_ok and ok
    return all_ok, details

def commit_hash(secret:str, gid:int)->str:
    return hashlib.sha256((secret+str(gid)).encode()).hexdigest()

def deterministic_draw(secret:str, gid:int, user_ids:list[int], k:int):
    import hashlib
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

# ----------------- FSM -----------------
from aiogram.fsm.state import StatesGroup, State

class CreateFlow(StatesGroup):
    TITLE = State()
    DESC = State()
    CONFIRM_DESC = State()   # подтверждение описания
    MEDIA_DECIDE = State()   # новый шаг: задать вопрос Да/Нет
    MEDIA_UPLOAD = State()   # новый шаг: ожидать файл (photo/animation/video)
    PHOTO = State()          # больше не используется, но пусть останется если где-то ссылаешься
    ENDAT = State()

# ----------------- BOT -----------------
from aiogram import Bot, Dispatcher, F
bot = Bot(BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher()
scheduler = AsyncIOScheduler()

async def set_bot_commands(bot: Bot):
    commands = [
        BotCommand(command="start", description="перезапустить бота"),
        BotCommand(command="create", description="создать розыгрыш"),
        BotCommand(command="events", description="розыгрыши"),
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
    # Какие права хотим запросить у пользователя для канала
    chan_rights = ChatAdministratorRights(
        is_anonymous=False,
        can_manage_chat=True,
        can_post_messages=True,
        can_edit_messages=True,
        can_delete_messages=False,
        can_invite_users=True,
        can_restrict_members=False,
        can_promote_members=True,
        can_change_info=True,
        can_pin_messages=False,
        can_manage_topics=False,
        can_post_stories=False,
        can_edit_stories=False,
        can_delete_stories=False,
        can_manage_video_chats=False,
    )

    # Минимальные права для группы/супергруппы (можете скорректировать)
    group_rights = ChatAdministratorRights(
        is_anonymous=False,
        can_manage_chat=True,
        can_post_messages=False,
        can_edit_messages=False,
        can_delete_messages=True,
        can_invite_users=True,
        can_restrict_members=True,
        can_promote_members=False,
        can_change_info=True,
        can_pin_messages=True,
        can_manage_topics=True,
        can_post_stories=False,
        can_edit_stories=False,
        can_delete_stories=False,
        can_manage_video_chats=True,
    )

    btn_add_channel = KeyboardButton(
        text=BTN_ADD_CHANNEL,
        request_chat=KeyboardButtonRequestChat(
            request_id=1,             # любой целый id (вернётся в chat_shared)
            chat_is_channel=True,     # именно канал
            bot_administrator_rights=chan_rights
        )
    )

    btn_add_group = KeyboardButton(
        text=BTN_ADD_GROUP,
        request_chat=KeyboardButtonRequestChat(
            request_id=2,
            chat_is_channel=False,              # группы/супергруппы
            bot_administrator_rights=group_rights
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
        input_field_placeholder="Сообщение"
    )

# === СИСТЕМНОЕ окно выбора канала/группы (chat_shared) ===
@dp.message(F.chat_shared)
async def on_chat_shared(m: Message):
    """
    Вызывается, когда пользователь выбрал канал/группу в нативном окне Telegram.
    """
    shared = m.chat_shared
    chat_id = shared.chat_id

    try:
        chat = await bot.get_chat(chat_id)
        me = await bot.get_me()
        cm = await bot.get_chat_member(chat_id, me.id)
        role = "administrator" if cm.status == "administrator" else (
            "member" if cm.status == "member" else "none"
        )
    except Exception as e:
        await m.answer(f"Не удалось получить данные чата. Попробуйте ещё раз. ({e})")
        return

    # сохраняем как раньше
    from sqlalchemy import text as stext
    async with session_scope() as s:
        await s.execute(
            stext(
                "INSERT OR IGNORE INTO organizer_channels("
                "owner_user_id, chat_id, username, title, is_private, bot_role"
                ") VALUES (:o, :cid, :u, :t, :p, :r)"
            ),
            {
                "o": m.from_user.id,
                "cid": chat.id,
                "u": getattr(chat, "username", None),
                "t": chat.title or (getattr(chat, "first_name", None) or "Без названия"),
                "p": 0 if getattr(chat, "username", None) else 1,
                "r": "admin" if role == "administrator" else "member",
            }
        )

    kind = "канал" if chat.type == "channel" else "группа"
    await m.answer(
        f"{kind.capitalize()} <b>{chat.title}</b> подключён. Теперь откройте /events и нажмите «Подключить каналы».",
        parse_mode="HTML",
        reply_markup=reply_main_kb()
    )

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
        "<b>/events</b> – розыгрыши\n"
        "<b>/subscriptions</b> – подписки"
    )
    await m.answer(text, parse_mode="HTML", reply_markup=reply_main_kb())

# ===== Команда /menu чтобы вернуть/показать клавиатуру внизу =====
@dp.message(Command("menu"))
async def cmd_menu(m: Message):
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

# "Розыгрыши" -> используем ваш cmd_events
@dp.message(F.text == BTN_EVENTS)
async def on_btn_events(m: Message, state: FSMContext):
    await cmd_events(m)   # вызываем ваш уже написанный обработчик

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

    # Переходим к следующему шагу — описание
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
    # идём дальше — к шагу с фото
    await state.set_state(CreateFlow.MEDIA_DECIDE)
    await cq.message.answer(MEDIA_QUESTION, reply_markup=kb_yes_no())
    await cq.answer()

@dp.callback_query(CreateFlow.MEDIA_DECIDE, F.data == "media:yes")
async def media_yes(cq: CallbackQuery, state: FSMContext):
    try:
        await cq.message.edit_reply_markup()  # убираем старые кнопки Да/Нет
    except Exception:
        pass
    await state.set_state(CreateFlow.MEDIA_UPLOAD)
    # ВАЖНО: показываем инструкцию И клавиатуру "Пропустить"
    await cq.message.answer(MEDIA_INSTRUCTION, parse_mode="HTML", reply_markup=kb_skip_media())
    await cq.answer()

@dp.callback_query(CreateFlow.MEDIA_DECIDE, F.data == "media:no")
async def media_no(cq: CallbackQuery, state: FSMContext):
    try:
        await cq.message.edit_reply_markup()
    except Exception:
        pass
    await state.set_state(CreateFlow.ENDAT)
    await cq.message.answer(format_endtime_prompt(), parse_mode="HTML")
    await cq.answer()

@dp.callback_query(CreateFlow.MEDIA_UPLOAD, F.data == "media:skip")
async def media_skip_btn(cq: CallbackQuery, state: FSMContext):
    try:
        await cq.message.edit_reply_markup()  # убираем кнопку "Пропустить" под инструкцией
    except Exception:
        pass
    await state.set_state(CreateFlow.ENDAT)
    await cq.message.answer(format_endtime_prompt(), parse_mode="HTML")
    await cq.answer()

MAX_VIDEO_BYTES = 5 * 1024 * 1024  # 5 МБ

# Пользователь всё равно может прислать текст «пропустить»
@dp.message(CreateFlow.MEDIA_UPLOAD, F.text.casefold() == "пропустить")
async def media_skip_by_text(m: Message, state: FSMContext):
    await state.set_state(CreateFlow.ENDAT)
    await m.answer(format_endtime_prompt(), parse_mode="HTML")

# Фото
@dp.message(CreateFlow.MEDIA_UPLOAD, F.photo)
async def got_photo(m: Message, state: FSMContext):
    file_id = m.photo[-1].file_id
    await state.update_data(photo=pack_media("photo", file_id))
    await state.set_state(CreateFlow.ENDAT)
    await m.answer(format_endtime_prompt(), parse_mode="HTML")


# GIF (Telegram шлёт как animation — это mp4-клип)
@dp.message(CreateFlow.MEDIA_UPLOAD, F.animation)
async def got_animation(m: Message, state: FSMContext):
    anim = m.animation
    if anim.file_size and anim.file_size > MAX_VIDEO_BYTES:
        await m.answer(
            "⚠️ Слишком большой файл. Ограничение — 5 МБ. Пришлите меньший gif/видео или нажмите «Пропустить».",
            reply_markup=kb_skip_media()
        )
        return
    await state.update_data(photo=pack_media("animation", anim.file_id))
    await state.set_state(CreateFlow.ENDAT)
    await m.answer(format_endtime_prompt(), parse_mode="HTML")


# Видео
@dp.message(CreateFlow.MEDIA_UPLOAD, F.video)
async def got_video(m: Message, state: FSMContext):
    v = m.video
    if v.mime_type and v.mime_type != "video/mp4":
        await m.answer(
            "⚠️ Видео должно быть в формате MP4. Пришлите другое или нажмите «Пропустить».",
            reply_markup=kb_skip_media()
        )
        return
    if v.file_size and v.file_size > MAX_VIDEO_BYTES:
        await m.answer(
            "⚠️ Слишком большой файл. Ограничение — 5 МБ. Пришлите меньший файл или нажмите «Пропустить».",
            reply_markup=kb_skip_media()
        )
        return
    await state.update_data(photo=pack_media("video", v.file_id))
    await state.set_state(CreateFlow.ENDAT)
    await m.answer(format_endtime_prompt(), parse_mode="HTML")

@dp.message(CreateFlow.ENDAT, F.text)
async def step_endat(m: Message, state: FSMContext):
    """
    Финальный шаг мастера: получаем дату окончания,
    достаём из state все ранее введённые поля и создаём черновик розыгрыша.
    """
    txt = (m.text or "").strip()
    try:
        # формат HH:MM DD.MM.YYYY по МСК
        dt_msk = datetime.strptime(txt, "%H:%M %d.%m.%Y")
        dt_utc = dt_msk - timedelta(hours=3)  # сохраняем в UTC

        # дедлайн должен быть хотя бы через 5 минут
        if dt_utc <= datetime.now(timezone.utc) + timedelta(minutes=5):
            await m.answer("Дедлайн должен быть минимум через 5 минут. Введите ещё раз:")
            return

        # достаём всё, что мы сохраняли на предыдущих шагах
        data = await state.get_data()
        owner_id = data.get("owner")
        title     = (data.get("title") or "").strip()          # наше ЕДИНОЕ название
        desc      = (data.get("desc")  or "").strip()          # описание (может быть пустым)
        photo_id  = data.get("photo")

        # минимальные проверки (чтоб не получить KeyError)
        if not owner_id or not title:
            await m.answer("Похоже, шаги заполнены не полностью. Наберите /create и начните заново.")
            await state.clear()
            return

        # сохраняем черновик в БД
        async with session_scope() as s:
            gw = Giveaway(
                owner_user_id=owner_id,
                internal_title=title,           # <-- кладём наше единое название
                public_description=desc,        # <-- текст описания
                photo_file_id=photo_id,
                end_at_utc=dt_utc,
                winners_count=1,
                status=GiveawayStatus.DRAFT
            )
            s.add(gw)

        await state.clear()
        await m.answer(
            "Черновик сохранён.\n"
            "Откройте /events, чтобы привязать каналы и запустить розыгрыш.",
            reply_markup=reply_main_kb()
        )
    except ValueError:
        await m.answer("Неверный формат. Пример: 13:58 06.10.2025")

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
            "У вас пока нет розыгрышей. Вы можете создать новый роыгрыш и он появится здесь.",
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

@dp.message(F.forward_from_chat | F.text.regexp(r"^@[\w\d_]+$"))
async def add_channel(m:Message):
    owner = m.from_user.id
    chat = None
    if m.forward_from_chat:
        chat = m.forward_from_chat
    else:
        username = m.text.strip()
        chat = await bot.get_chat(username)
    try:
        cm = await bot.get_chat_member(chat.id, (await bot.me()).id)
        role = "administrator" if cm.status=="administrator" else ("member" if cm.status=="member" else "none")
    except Exception:
        role="none"
    if role=="none":
        await m.answer("Добавьте бота в канал (в приватном — админом), затем повторите."); return
    from sqlalchemy import text as stext
    async with session_scope() as s:
        await s.execute(stext("INSERT INTO organizer_channels(owner_user_id,chat_id,username,title,is_private,bot_role) "
                              "VALUES(:o,:cid,:u,:t,:p,:r)"),
                        {"o":owner,"cid":chat.id,"u":getattr(chat,'username',None),"t":chat.title,
                         "p":0 if getattr(chat,'username',None) else 1,"r":"admin" if role=='administrator' else 'member'})
    await m.answer(f"Канал <b>{chat.title}</b> подключён. Теперь /events → «Подключить каналы».")

from aiogram.utils.keyboard import InlineKeyboardBuilder

@dp.callback_query(F.data.startswith("ev:"))
async def event_cb(cq:CallbackQuery):
    _, action, sid = cq.data.split(":")
    gid = int(sid)
    if action=="channels":
        from sqlalchemy import text as stext
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
        from sqlalchemy import text as stext
        async with session_scope() as s:
            gw = await s.get(Giveaway, gid)
            if gw.status != GiveawayStatus.DRAFT:
                await cq.answer("Уже запущен или завершён.", show_alert=True); return
            res = await s.execute(stext("SELECT COUNT(*) FROM giveaway_channels WHERE giveaway_id=:gid"),{"gid":gid})
            cnt = res.scalar_one()
            if cnt==0:
                await cq.answer("Сначала привяжите хотя бы 1 канал.", show_alert=True); return
            secret = gen_ticket_code()+gen_ticket_code()
            gw.secret = secret
            gw.commit_hash = commit_hash(secret, gid)
            gw.status = GiveawayStatus.ACTIVE
        when = await get_end_at(gid)
        scheduler.add_job(finalize_and_draw_job, DateTrigger(run_date=when), args=[gid], id=f"final_{gid}", replace_existing=True)
        await cq.message.answer("Розыгрыш запущен.")
        await show_event_card(cq.message.chat.id, gid)

    elif action=="delete":
        from sqlalchemy import text as stext
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

async def get_end_at(gid:int)->datetime:
    from sqlalchemy import text as stext
    async with session_scope() as s:
        res = await s.execute(stext("SELECT end_at_utc FROM giveaways WHERE id=:gid"),{"gid":gid})
        return res.scalar_one()

async def show_stats(chat_id:int, gid:int):
    from sqlalchemy import text as stext
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
    from sqlalchemy import text as stext
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

async def finalize_and_draw_job(gid:int):
    from sqlalchemy import text as stext
    async with session_scope() as s:
        gw = await s.get(Giveaway, gid)
        if not gw or gw.status!=GiveawayStatus.ACTIVE: return
        res = await s.execute(stext("SELECT user_id,id FROM entries WHERE giveaway_id=:gid AND prelim_ok=1"),{"gid":gid})
        entries = res.all()
    eligible=[]
    for uid, entry_id in entries:
        ok,_ = await check_membership_on_all(bot, uid, gid)
        from sqlalchemy import text as stext
        async with session_scope() as s:
            await s.execute(stext("UPDATE entries SET final_ok=:ok, final_checked_at=:ts WHERE id=:eid"),
                            {"ok":1 if ok else 0, "ts":datetime.now(timezone.utc), "eid":entry_id})
        if ok: eligible.append(uid)
    async with session_scope() as s:
        gw = await s.get(Giveaway, gid)
        winners = deterministic_draw(gw.secret, gid, eligible, gw.winners_count)
        rank=1
        for uid, r, h in winners:
            await s.execute(stext("INSERT INTO winners(giveaway_id,user_id,rank,hash_used) VALUES(:g,:u,:r,:h)"),
                            {"g":gid,"u":uid,"r":rank,"h":h}); rank+=1
        gw.status = GiveawayStatus.FINISHED
    if winners:
        ids = [w[0] for w in winners]
        textw = "\n".join([f"{i+1}) <a href='tg://user?id={uid}'>победитель</a>" for i,uid in enumerate(ids)])
    else:
        textw = "Победителей нет."
    async with session_scope() as s:
        gw = await s.get(Giveaway, gid)
    await bot.send_message(gw.owner_user_id,
                           f"Финальный пул: {len(eligible)}\n"
                           f"Победителей: {len(winners)}\n"
                           f"secret: <code>{gw.secret}</code>\n"
                           f"commit: <code>{gw.commit_hash}</code>\n\n{textw}")

async def cancel_giveaway(gid:int, by_user_id:int, reason:str|None):
    from sqlalchemy import text as stext
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

# ---------------- ENTRYPOINT ----------------
async def main():
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    # 1) инициализация БД
    await init_db()
    logging.info("✅ База данных инициализирована")

    # 2) запускаем планировщик
    scheduler.start()
    logging.info("✅ Планировщик запущен")

    # 3) Проверяем токен и подключение к Telegram
    me = await bot.get_me()
    logging.info(f"🤖 Бот запущен как @{me.username} (ID: {me.id})")

    # 4) Устанавливаем команды бота
    await set_bot_commands(bot)
    logging.info("✅ Команды установлены")

    # 5) Снимаем возможный старый вебхук
    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("🔁 Webhook удалён, включаю polling...")

    # 6) Запускаем polling
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
