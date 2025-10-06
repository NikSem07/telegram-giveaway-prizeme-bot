import asyncio, os, hashlib, random, string
from datetime import datetime, timezone, timedelta
from contextlib import asynccontextmanager

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, StateFilter
from aiogram.types import (Message, CallbackQuery, InlineKeyboardMarkup,
                           InlineKeyboardButton, InputMediaPhoto)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.utils.keyboard import InlineKeyboardBuilder

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger

from sqlalchemy import (text, String, Integer, BigInteger,
                        Boolean, DateTime, ForeignKey)
from sqlalchemy.ext.asyncio import (create_async_engine, async_sessionmaker)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from aiogram.types import BotCommand

from dotenv import load_dotenv
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
DEFAULT_TZ = os.getenv("TZ", "Europe/Moscow")

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
    PHOTO = State()
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
    await m.answer(text, parse_mode="HTML")

@dp.message(Command("create"))
async def create_giveaway_start(message: Message, state: FSMContext):
    await state.clear()
    await state.update_data(owner=message.from_user.id)  # <-- сохраняем владельца сразу
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
    await state.set_state("giveaway_name")

@dp.message(StateFilter("giveaway_name"))
async def handle_giveaway_name(m: Message, state: FSMContext):
    name = (m.text or "").strip()
    if not name:
        await m.answer("Введите название розыгрыша:")
        return
    if len(name) > 50:
        await m.answer("Название не должно превышать 50 символов. Попробуйте снова.")
        return

    # Сохраняем название
    await state.update_data(title=name)

    # Переходим к следующему шагу — описание
    await state.set_state(CreateFlow.DESC)
    await m.answer("Введите текст описания розыгрыша (до 2500 символов):")

@dp.message(CreateFlow.TITLE)
async def step_title_too_long(m:Message, state:FSMContext):
    await m.answer("Слишком длинно. Введите до 50 символов.")

@dp.message(CreateFlow.DESC, F.text)
async def step_desc(m:Message, state:FSMContext):
    await state.update_data(desc=m.text.strip())
    await state.set_state(CreateFlow.PHOTO)
    await m.answer("Пришлите <b>картинку</b> (или напишите «пропустить»):")

@dp.message(CreateFlow.PHOTO, F.text.casefold() == "пропустить")
async def step_photo_skip(m:Message, state:FSMContext):
    await state.update_data(photo=None)
    await state.set_state(CreateFlow.ENDAT)
    await m.answer("Укажите время окончания: <b>HH:MM DD.MM.YYYY</b> (MSK):")

@dp.message(CreateFlow.PHOTO, F.photo)
async def step_photo(m:Message, state:FSMContext):
    file_id = m.photo[-1].file_id
    await state.update_data(photo=file_id)
    await state.set_state(CreateFlow.ENDAT)
    await m.answer("Ок. Теперь дата окончания: <b>HH:MM DD.MM.YYYY</b> (MSK):")

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
            "Откройте /events, чтобы привязать каналы и запустить розыгрыш."
        )
    except ValueError:
        await m.answer("Неверный формат. Пример: 13:58 06.10.2025")

@dp.message(Command("events"))
async def cmd_events(m:Message):
    async with session_scope() as s:
        res = await s.execute(text("SELECT id, internal_title, status FROM giveaways WHERE owner_user_id=:u ORDER BY id DESC"), {"u":m.from_user.id})
        row = res.first()
    if not row:
        await m.answer("У вас нет розыгрышей. Нажмите «Создать розыгрыш».", reply_markup=kb_main()); return
    await show_event_card(m.chat.id, row[0])

async def show_event_card(chat_id:int, giveaway_id:int):
    async with session_scope() as s:
        gw = await s.get(Giveaway, giveaway_id)
    cap = (f"<b>{gw.internal_title}</b>\n\n{gw.public_description}\n\n"
           f"Статус: {gw.status}\nПобедителей: {gw.winners_count}\n"
           f"Дата окончания: {(gw.end_at_utc+timedelta(hours=3)).strftime('%H:%M %d.%m.%Y MSK')}")
    if gw.photo_file_id:
        await bot.send_photo(chat_id, gw.photo_file_id, caption=cap, reply_markup=kb_event_actions(giveaway_id, gw.status))
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

# ----------------- ENTRYPOINT -----------------
async def main():
    # 1) инициализация БД
    await init_db()
    # 2) запускаем планировщик ПОСЛЕ создания event loop (мы внутри main)
    scheduler.start()
    # 3) Вызвать установку команд при старте бота
    await set_bot_commands(bot)
    # 4) Снимаем вебхук
    await bot.delete_webhook(drop_pending_updates=True)
    # 5) запускаем бота
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
