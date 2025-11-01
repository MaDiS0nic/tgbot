import os
import math
import asyncio
import logging
import re
import calendar as pycal
from datetime import date, timedelta
from typing import Final, Dict, Optional, Tuple, List

from fastapi import FastAPI, Request, HTTPException
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Update, Message, BotCommand, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
import aiohttp

# ================== CONFIG ==================
BOT_TOKEN: Final[str] = os.getenv("BOT_TOKEN", "")
APP_BASE_URL: Final[str] = os.getenv("APP_BASE_URL", "").rstrip("/")
WEBHOOK_SECRET: Final[str] = os.getenv("WEBHOOK_SECRET", "")

ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "7039409310") or 7039409310)
DISPATCHER_PHONE = "+79340241414"
DISPATCHER_NAME = "Диспетчер TransferAir"

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

# ================== LOGGING ==================
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("tgbot")

# ================== AIOGRAM CORE ==================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ================== ЛЕЙБЛЫ КНОПОК ==================
BTN_CALC = "🧮 Калькулятор стоимости"
BTN_ORDER = "📝 Сделать заказ"
BTN_DISPATCHER = "☎️ Диспетчер"
BTN_INFO = "ℹ️ Информация"

MENU_BUTTONS = [BTN_CALC, BTN_ORDER, BTN_DISPATCHER, BTN_INFO]

# ================== ТАРИФЫ ==================
TARIFFS = {
    "econom":  {"title": "Легковой",            "per_km": 30},
    "camry":   {"title": "Camry",               "per_km": 40},
    "minivan": {"title": "Минивэн (5-6 чел)",   "per_km": 50},
}

# ================== ФИКСИРОВАННЫЕ ЦЕНЫ ==================
FIXED_PRICES: Dict[str, Tuple[int, int, int]] = {
    "железноводск": (800, 1500, 2000),
    "пятигорск": (1200, 1500, 1900),
    "ессентуки": (1300, 2000, 2500),
    "кисловодск": (1800, 2500, 3000),

    "архыз": (6500, 8000, 10000),
    "архыз романтик": (7000, 9000, 11000),
    "домбай": (6500, 8000, 10000),
    "азау": (5500, 7500, 9000),
    "терскол": (5500, 7500, 9000),
    "эльбрус": (5500, 7500, 9000),
    "теберда": (5500, 7500, 9000),
    "нейтрино": (5000, 7500, 9000),
    "тегенекли": (5000, 7500, 9000),
    "байдаево": (5000, 7500, 9000),
    "чегет": (5500, 7500, 9000),

    "ставрополь": (5400, 7200, 9000),
    "черкесск": (3000, 4000, 5000),
    "нальчик": (3300, 4400, 5500),
    "владикавказ": (6600, 8800, 11000),
    "грозный": (9300, 12400, 15500),
    "назрань": (6600, 8800, 11000),
    "магас": (6600, 8800, 11000),

    "адлер": (17400, 23200, 29000),
    "алагир": (6000, 8000, 10000),
    "александровское село": (2100, 2800, 3500),
    "ардон": (5500, 7400, 9200),
    "арзгир": (6000, 8000, 10000),
    "армавир": (5700, 7600, 9500),
    "астрахань": (18900, 25000, 31500),
    "аушигер": (4000, 5400, 6700),
    "ачикулак село": (5500, 7400, 9200),
    "баксан": (2500, 3300, 4000),
    "батуми": (30000, 40000, 50000),
    "беломечетская станица": (3600, 4800, 6000),
    "беслан": (6000, 8000, 10000),
    "благодарный": (4000, 5400, 6700),
    "будёновск": (4000, 5400, 6700),
    "витязево поселок": (18000, 24000, 30000),
    "волгоград": (18000, 24000, 30000),
    "галюгаевская станица": (6000, 8000, 10000),
    "геленджик": (18000, 24000, 30000),
    "георгиевск": (1300, 2000, 2500),
    "горнозаводское село": (3000, 4000, 5000),
    "грушевское село": (3300, 4400, 5500),
    "гудаури": (15000, 20000, 25000),
    "дербент": (18000, 24000, 30000),
    "джубга": (14000, 19000, 23000),
    "екатеринбург": (72000, 96000, 120000),
    "елизаветинское село": (3700, 5000, 6200),
    "зеленокумск": (2400, 3200, 4000),
    "зеленчукская станица": (5000, 7500, 8500),
    "зольская станица": (1500, 2000, 2500),
    "иконхалк": (3400, 4500, 5600),
    "кабардинка": (16500, 22000, 27500),
    "камата село (осетия)": (6000, 8000, 10000),
    "карчаевск": (4600, 6100, 7700),
    "каратюбе": (5400, 7200, 9000),
    "каспийск": (14500, 19000, 24000),
    "кизляр": (11400, 15200, 19000),
    "кочубеевское село": (3700, 5000, 6200),
    "краснодар": (12000, 16000, 20000),
    "курская": (4300, 5700, 7100),
    "лабинск": (7000, 9300, 11600),
    "лазаревское": (14500, 19200, 24000),
    "левокумское село": (5200, 7000, 8700),
    "майкоп": (8800, 11700, 14500),
    "майский кбр": (4300, 5700, 7000),
    "марьинская станица": (2100, 2800, 3500),
    "махачкала": (13900, 18500, 23100),
    "моздок": (4900, 6500, 8100),
    "нарткала": (3700, 5000, 6200),
    "невинномысск": (3000, 4000, 5000),
    "незлобная станица": (1500, 2000, 2500),
    "нефтекумск": (6400, 8500, 10700),
    "новоалександровск": (7400, 9800, 12200),
    "новопавловск": (2500, 3400, 4200),
    "новороссийск": (17000, 22600, 28200),
    "новоселицкое село": (3000, 4000, 5000),
    "прохладный": (3600, 4800, 6000),
    "псебай": (9000, 12000, 15000),
    "псыгансу село": (3900, 5200, 6500),
    "ростов- на- дону": (16000, 21000, 26000),
    "светлоград": (5100, 6800, 8500),
    "сочи": (16500, 22000, 27500),
    "степанцминда": (13000, 17000, 22000),
    "степное село": (4400, 5800, 7300),
    "сунжа": (7500, 10000, 12500),
    "тбилиси": (20000, 25000, 30000),
    "терек": (4700, 6200, 7800),
    "туапсе": (13000, 17300, 21700),
    "урус-мартан": (9000, 12000, 15000),
    "учкулан аул": (6000, 8000, 10000),
    "хадыженск": (10700, 14200, 17800),
    "хасавюрт": (11400, 15200, 19000),
    "хурзук аул": (6500, 9000, 11500),
    "цей": (7300, 9700, 12000),
    "элиста": (9400, 12500, 15600),
}

# ================== АЛИАСЫ/СИНОНИМЫ ==================
FROM_ALIASES = {
    "минводы": "Минеральные Воды",
    "минеральные воды": "Минеральные Воды",
    "минеральные воды аэропорт": "Минеральные Воды",
    "аэропорт минеральные воды": "Минеральные Воды",
    "аэропорт мв": "Минеральные Воды",
    "аэропорт mrv": "Минеральные Воды",
    "мв": "Минеральные Воды",
    "мвр": "Минеральные Воды",
    "mrv": "Минеральные Воды",
}
DEST_ALIASES = {
    "железка": "железноводск",
    "жв": "железноводск",
    "пятиг": "пятигорск",
    "ессы": "ессентуки",
    "кислов": "кисловодск",
    "романтик": "архыз романтик",
    "архыз-романтик": "архыз романтик",
    "приэльбрусье": "эльбрус",
    "поляна азау": "азау",
    "мир азау": "азау",
    "чегет поляна": "чегет",
    "ставрик": "ставрополь",
    "владикавк": "владикавказ",
    "гроз": "грозный",
    "маг": "магас",
    "налчик": "нальчик",
    "черек": "черкесск",
    "адл": "адлер",
    "сочи адлер": "адлер",
    "крд": "краснодар",
    "крдн": "краснодар",
}

def normalize_city(text: str) -> str:
    return " ".join((text or "").strip().split())

def _norm_key(text: str) -> str:
    return normalize_city(text).lower()

def resolve_from_city(text: str) -> str:
    key = _norm_key(text)
    return FROM_ALIASES.get(key, normalize_city(text))

def guess_from_display(text: str) -> str:
    key = _norm_key(text)
    if "аэропорт" in key or "mrv" in key:
        return "Аэропорт MRV"
    if key in {"аэропорт mrv", "аэропорт мв"}:
        return "Аэропорт MRV"
    return "Минеральные Воды"

def resolve_dest_key(text: str) -> str:
    key = _norm_key(text)
    if key in FIXED_PRICES:
        return key
    return DEST_ALIASES.get(key, key)

# ================== ПОДСКАЗКИ ГОРОДОВ ==================
DEST_OPTIONS: List[Tuple[str, str]] = [
    ("Железноводск", "железноводск"),
    ("Пятигорск", "пятигорск"),
    ("Ессентуки", "ессентуки"),
    ("Кисловодск", "кисловодск"),
    ("Архыз", "архыз"),
    ("Архыз Романтик", "архыз романтик"),
    ("Домбай", "домбай"),
    ("Азау", "азау"),
    ("Терскол", "терскол"),
    ("Чегет", "чегет"),
    ("Эльбрус", "эльбрус"),
    ("Теберда", "теберда"),
    ("Ставрополь", "ставрополь"),
    ("Нальчик", "нальчик"),
    ("Черкесск", "черкесск"),
    ("Владикавказ", "владикавказ"),
    ("Адлер", "адлер"),
    ("Сочи", "сочи"),
    ("Краснодар", "краснодар"),
    ("Грозный", "грозный"),
    ("Махачкала", "махачкала"),
    ("Беслан", "беслан"),
    ("Алагир", "алагир"),
    ("Екатеринбург", "екатеринбург"),
    ("Туапсе", "туапсе"),
    ("Кабардинка", "кабардинка"),
    ("Лазаревское", "лазаревское"),
    ("Каспийск", "каспийск"),
    ("Кизляр", "кизляр"),
    ("Дербент", "дербент"),
]

# ---- компактные callback'и для from_pick ----
FROM_CHOICES = {
    "mv":  ("Минеральные Воды", "Минеральные Воды"),
    "mrv": ("Минеральные Воды", "Аэропорт MRV"),
}

def from_suggestions_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Минеральные Воды", callback_data="fp:mv"),
        InlineKeyboardButton(text="Аэропорт MRV",    callback_data="fp:mrv"),
    ]])

def dest_suggestions_kb(page: int = 0, per_page: int = 10) -> InlineKeyboardMarkup:
    start = page * per_page
    items = DEST_OPTIONS[start:start + per_page]
    rows = []
    for i in range(0, len(items), 2):
        pair = items[i:i+2]
        row = []
        for disp, key in pair:
            row.append(InlineKeyboardButton(text=disp, callback_data=f"dest_pick:{key}"))
        rows.append(row)
    max_page = (len(DEST_OPTIONS) - 1) // per_page
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⏮️ Назад", callback_data=f"dest_page:{page-1}"))
    if page < max_page:
        nav.append(InlineKeyboardButton(text="Вперёд ⏭️", callback_data=f"dest_page:{page+1}"))
    if nav:
        rows.append(nav)
    return InlineKeyboardMarkup(inline_keyboard=rows)

# ================== КАЛЕНДАРЬ ==================
RU_MONTHS = [
    "", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
]

def date_calendar_kb(y: int, m: int) -> InlineKeyboardMarkup:
    pycal.setfirstweekday(pycal.MONDAY)
    month_cal = pycal.monthcalendar(y, m)
    header = [
        [InlineKeyboardButton(text=f"{RU_MONTHS[m]} {y}", callback_data="noop")],
        [
            InlineKeyboardButton(text="Сегодня", callback_data="calpick:today"),
            InlineKeyboardButton(text="Завтра", callback_data="calpick:tomorrow"),
        ],
        [
            InlineKeyboardButton(text="Пн", callback_data="noop"),
            InlineKeyboardButton(text="Вт", callback_data="noop"),
            InlineKeyboardButton(text="Ср", callback_data="noop"),
            InlineKeyboardButton(text="Чт", callback_data="noop"),
            InlineKeyboardButton(text="Пт", callback_data="noop"),
            InlineKeyboardButton(text="Сб", callback_data="noop"),
            InlineKeyboardButton(text="Вс", callback_data="noop"),
        ],
    ]
    rows = []
    for week in month_cal:
        row = []
        for d in week:
            if d == 0:
                row.append(InlineKeyboardButton(text=" ", callback_data="noop"))
            else:
                row.append(InlineKeyboardButton(text=str(d), callback_data=f"calpick:{y}:{m}:{d}"))
        rows.append(row)
    prev_y, prev_m = (y - 1, 12) if m == 1 else (y, m - 1)
    next_y, next_m = (y + 1, 1) if m == 12 else (y, m + 1)
    nav = [[
        InlineKeyboardButton(text="⏮️", callback_data=f"calnav:{prev_y}:{prev_m}"),
        InlineKeyboardButton(text="Отмена", callback_data="calcancel"),
        InlineKeyboardButton(text="⏭️", callback_data=f"calnav:{next_y}:{next_m}"),
    ]]
    return InlineKeyboardMarkup(inline_keyboard=header + rows + nav)

# ================== ВРЕМЯ ==================
def time_hours_kb() -> InlineKeyboardMarkup:
    rows = []
    for base in range(0, 24, 6):
        row = []
        for h in range(base, base + 6):
            row.append(InlineKeyboardButton(text=f"{h:02d}", callback_data=f"timeh:{h:02d}"))
        rows.append(row)
    rows.append([InlineKeyboardButton(text="Отмена", callback_data="timecancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def time_minutes_kb(hour: str) -> InlineKeyboardMarkup:
    row = [
        InlineKeyboardButton(text="00", callback_data=f"timem:{hour}:00"),
        InlineKeyboardButton(text="15", callback_data=f"timem:{hour}:15"),
        InlineKeyboardButton(text="30", callback_data=f"timem:{hour}:30"),
        InlineKeyboardButton(text="45", callback_data=f"timem:{hour}:45"),
    ]
    ctrl = [
        InlineKeyboardButton(text="⬅️ Часы", callback_data="timeback"),
        InlineKeyboardButton(text="Отмена", callback_data="timecancel"),
    ]
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"Часы: {hour}", callback_data="noop")], row, ctrl])

# ================== ПАССАЖИРЫ ==================
def pax_kb() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="1", callback_data="pax:1"),
            InlineKeyboardButton(text="2", callback_data="pax:2"),
            InlineKeyboardButton(text="3", callback_data="pax:3"),
        ],
        [
            InlineKeyboardButton(text="4", callback_data="pax:4"),
            InlineKeyboardButton(text="5", callback_data="pax:5"),
            InlineKeyboardButton(text="6", callback_data="pax:6"),
        ],
        [
            InlineKeyboardButton(text="7 и более", callback_data="pax:7+"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)

# ================== КОММЕНТАРИЙ? ==================
def comment_choice_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Да", callback_data="comment_yes"),
        InlineKeyboardButton(text="Нет", callback_data="comment_no"),
    ]])

# ================== КЛАВИАТУРА ГЛАВНОГО МЕНЮ ==================
def main_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_CALC)],
            [KeyboardButton(text=BTN_ORDER)],
            [KeyboardButton(text=BTN_DISPATCHER)],
            [KeyboardButton(text=BTN_INFO)],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )

def dispatcher_inline_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="💬 Написать диспетчеру в Telegram",
            url="https://t.me/zhelektown"
        )
    ], [
        InlineKeyboardButton(
            text="📱 Телефон диспетчера",
            callback_data="dispatcher_phone"
        )
    ]])

def confirm_order_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Подтвердить", callback_data="order_confirm"),
        InlineKeyboardButton(text="✏️ Изменить", callback_data="order_edit"),
        InlineKeyboardButton(text="❌ Отменить", callback_data="order_cancel"),
    ]])

# ================== СОСТОЯНИЯ ==================
class CalcStates(StatesGroup):
    from_city = State()
    to_city = State()

class OrderForm(StatesGroup):
    from_city = State()
    to_city = State()
    date = State()
    time = State()
    pax = State()
    comment_choice = State()
    phone = State()
    comment = State()
    confirm = State()

# ================== ХЕЛПЕРЫ (гео/цены) ==================
def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi/2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb/2) ** 2
    return R * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))

async def geocode_city(session: aiohttp.ClientSession, city: str) -> Optional[Dict[str, float]]:
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": city, "format": "json", "limit": 1}
    headers = {"User-Agent": "TransferAir-KMV-Bot/1.0 (admin@example.com)"}
    try:
        async with session.get(url, params=params, headers=headers, timeout=20) as r:
            if r.status != 200:
                return None
            data = await r.json()
            if not data:
                return None
            return {"lat": float(data[0]["lat"]), "lon": float(data[0]["lon"])}
    except Exception as e:
        logger.warning(f"Geocode failed for {city}: {e}")
        return None

def prices_text_total_only(econom: int, camry: int, minivan: int) -> str:
    return (
        f"💰 Стоимость:\n"
        f"• {TARIFFS['econom']['title']} — ~{econom} ₽\n"
        f"• {TARIFFS['camry']['title']} — ~{camry} ₽\n"
        f"• {TARIFFS['minivan']['title']} — ~{minivan} ₽"
    )

def per_km_prices(distance_km: float) -> Tuple[int, int, int]:
    d = max(1.0, round(distance_km, 1))
    p_e = int(round(d * TARIFFS["econom"]["per_km"]))
    p_c = int(round(d * TARIFFS["camry"]["per_km"]))
    p_m = int(round(d * TARIFFS["minivan"]["per_km"]))
    return p_e, p_c, p_m

async def compute_prices_for_order(from_city: str, to_city: str) -> Optional[Tuple[int, int, int, str]]:
    from_key = _norm_key(from_city)
    to_key = resolve_dest_key(to_city)
    if from_key == "минеральные воды" and to_key in FIXED_PRICES:
        e, c, m = FIXED_PRICES[to_key]
        return e, c, m, "fixed"

    async with aiohttp.ClientSession() as session:
        a = await geocode_city(session, from_city)
        b = await geocode_city(session, to_city)
    if not a or not b:
        return None
    dist = haversine_km(a["lat"], a["lon"], b["lat"], b["lon"])
    e, c, m = per_km_prices(dist)
    return e, c, m, "distance"

PHONE_RE = re.compile(r"^\+?\d[\d\-\s]{8,}$")

# ================== ГЛОБАЛЬНЫЙ РОУТЕР МЕНЮ ==================
@dp.message(F.text.in_(MENU_BUTTONS))
async def menu_router(message: Message, state: FSMContext):
    await state.clear()
    text = message.text

    if text == BTN_CALC:
        await state.set_state(CalcStates.from_city)
        await message.answer("Введите *город отправления* (или выберите ниже):", parse_mode="Markdown")
        await message.answer("Быстрый выбор:", reply_markup=from_suggestions_kb())
        return

    if text == BTN_ORDER:
        await state.set_state(OrderForm.from_city)
        await state.update_data(order={})
        await message.answer("Введите *город отправления* (или выберите ниже):", parse_mode="Markdown")
        await message.answer("Быстрый выбор:", reply_markup=from_suggestions_kb())
        return

    if text == BTN_DISPATCHER:
        info = (
            "☎️ *Связаться с диспетчером*\n\n"
            "Нажмите кнопку ниже, чтобы написать диспетчеру в Telegram\n"
            "или получить номер телефона для звонка."
        )
        await message.answer(info, parse_mode="Markdown", reply_markup=dispatcher_inline_kb())
        return

    if text == BTN_INFO:
        await message.answer(
            "🚕 TransferAir междугороднее такси (Трансфер) из Минеральных Вод.\n\n"
            "🤖 Вы можете заказать трансфер через бота.\n\n"
            "📞 Позвонить нам: +79340241414\n\n"
            "🌐 Посетить наш сайт: https://transferkmw.ru/",
        )
        return

# ================== START ==================
@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    # Без приветствия и без кнопки «Старт». Сразу показываем главное меню.
    await state.clear()
    await message.answer("Выберите действие:", reply_markup=main_menu_kb())

# ---- ДИСПЕТЧЕР ----
@dp.message(F.text == BTN_DISPATCHER)
async def on_dispatcher(message: Message):
    text = (
        "☎️ *Связаться с диспетчером*\n\n"
        "Нажмите кнопку ниже, чтобы написать диспетчеру в Telegram\n"
        "или получить номер телефона для звонка."
    )
    await message.answer(text, parse_mode="Markdown", reply_markup=dispatcher_inline_kb())

@dp.callback_query(F.data == "dispatcher_phone")
async def dispatcher_phone_cb(cb: CallbackQuery):
    # Просто текст с номером — Telegram делает его кликабельным
    await cb.message.answer(f"📞 Телефон диспетчера: {DISPATCHER_PHONE}\nНажмите на номер, чтобы позвонить.")
    await cb.answer("Номер отправлен")

# ================== ПОДХВАТ FROM/TO ПОДСКАЗОК ==================
@dp.callback_query(F.data.startswith("fp:"))
async def pick_from(cb: CallbackQuery, state: FSMContext):
    key = cb.data.split(":", 1)[1]  # mv | mrv
    canonical, display = FROM_CHOICES.get(key, ("Минеральные Воды", "Минеральные Воды"))

    current = await state.get_state()
    if current and current.endswith("from_city"):
        if current.startswith("CalcStates"):
            await state.update_data(from_city=canonical, from_display=display)
            await state.set_state(CalcStates.to_city)
            await cb.message.edit_text(
                f"Отправление: *{display}* ✅\nВведите *город прибытия* (или выберите ниже):",
                parse_mode="Markdown"
            )
            await cb.message.answer("Быстрый выбор:", reply_markup=dest_suggestions_kb(0))
        else:
            order = {"from_city": canonical, "from_display": display}
            await state.update_data(order=order)
            await state.set_state(OrderForm.to_city)
            await cb.message.edit_text(
                f"Отправление: *{display}* ✅\nВведите *город прибытия* (или выберите ниже):",
                parse_mode="Markdown"
            )
            await cb.message.answer("Быстрый выбор:", reply_markup=dest_suggestions_kb(0))
    await cb.answer()

@dp.callback_query(F.data.startswith("dest_page:"))
async def dest_page(cb: CallbackQuery):
    page = int(cb.data.split(":", 1)[1])
    try:
        await cb.message.edit_reply_markup(reply_markup=dest_suggestions_kb(page))
    except Exception:
        await cb.message.answer("Ещё варианты:", reply_markup=dest_suggestions_kb(page))
    await cb.answer()

@dp.callback_query(F.data.startswith("dest_pick:"))
async def dest_pick(cb: CallbackQuery, state: FSMContext):
    key = cb.data.split(":", 1)[1]
    display_dest = next((d for d, k in DEST_OPTIONS if k == key), key.title())

    try:
        current = await state.get_state()
        if current and current.endswith("to_city"):
            # ---- КАЛЬКУЛЯТОР ----
            if current.startswith("CalcStates"):
                data = await state.get_data()
                from_city = data.get("from_city") or "Минеральные Воды"
                from_display = data.get("from_display") or "Минеральные Воды"
                await state.clear()

                if key in FIXED_PRICES and _norm_key(from_city) == "минеральные воды":
                    e, c, m = FIXED_PRICES[key]
                    txt = (
                        "⚠️ *Стоимость предварительная, окончательная цена оговаривается с диспетчером!*\n\n"
                        f"🧮 *Калькулятор стоимости*\n\n"
                        f"Из: *{from_display}*\nВ: *{display_dest}*\n\n"
                        f"{prices_text_total_only(e, c, m)}"
                    )
                    await cb.message.edit_text(txt, parse_mode="Markdown")
                    await bot.send_message(cb.message.chat.id, "Вы в главном меню:", reply_markup=main_menu_kb())
                    await cb.answer()
                    return

                async with aiohttp.ClientSession() as session:
                    a = await geocode_city(session, from_city)
                    b = await geocode_city(session, display_dest)
                if not a or not b:
                    await cb.message.answer("❌ Не удалось определить города. Попробуйте ещё раз.")
                    await cb.answer()
                    return
                dist = haversine_km(a["lat"], a["lon"], b["lat"], b["lon"])
                p_e, p_c, p_m = per_km_prices(dist)
                txt = (
                    "⚠️ *Стоимость предварительная, окончательная цена оговаривается с диспетчером!*\n\n"
                    f"🧮 *Калькулятор стоимости*\n\n"
                    f"Из: *{from_display}*\nВ: *{display_dest}*\n\n"
                    f"{prices_text_total_only(p_e, p_c, p_m)}"
                )
                await cb.message.edit_text(txt, parse_mode="Markdown")
                await bot.send_message(cb.message.chat.id, "Вы в главном меню:", reply_markup=main_menu_kb())
                await cb.answer()
                return

            # ---- ЗАКАЗ ----
            else:
                data = await state.get_data()
                order = data.get("order", {})
                order["to_city"] = display_dest
                await state.update_data(order=order)
                await state.set_state(OrderForm.date)

                today = date.today()
                await cb.message.edit_text(
                    f"Направление: *{display_dest}* ✅\n\nВыберите *дату подачи*:",
                    parse_mode="Markdown"
                )
                await cb.message.answer("Календарь:", reply_markup=date_calendar_kb(today.year, today.month))
        await cb.answer()
    except Exception as e:
        logger.exception(f"dest_pick handler failed: {e}")
        await cb.message.answer("Произошла ошибка при расчёте. Попробуйте ещё раз.")
        await cb.answer()

# ---- КАЛЕНДАРЬ: обработчики ----
@dp.callback_query(F.data == "calcancel")
async def cal_cancel(cb: CallbackQuery, state: FSMContext):
    await cb.message.delete()
    await cb.answer("Выбор даты отменён")
    await bot.send_message(cb.message.chat.id, "Выберите *дату подачи*:", parse_mode="Markdown")
    await state.set_state(OrderForm.date)

@dp.callback_query(F.data.startswith("calnav:"))
async def cal_nav(cb: CallbackQuery):
    _, y, m = cb.data.split(":")
    y, m = int(y), int(m)
    try:
        await cb.message.edit_reply_markup(reply_markup=date_calendar_kb(y, m))
    except Exception:
        await cb.message.answer("Календарь:", reply_markup=date_calendar_kb(y, m))
    await cb.answer()

@dp.callback_query(F.data.startswith("calpick:"))
async def cal_pick(cb: CallbackQuery, state: FSMContext):
    parts = cb.data.split(":")
    if parts[1] in ("today", "tomorrow"):
        d = date.today() if parts[1] == "today" else date.today() + timedelta(days=1)
    else:
        y, m, d_ = map(int, parts[1:4])
        d = date(y, m, d_)
    data = await state.get_data()
    order = data.get("order", {})
    order["date"] = d.strftime("%d.%m.%Y")
    await state.update_data(order=order)

    await cb.message.edit_text(f"Дата подачи: *{order['date']}* ✅", parse_mode="Markdown")
    await bot.send_message(cb.message.chat.id, "Выберите *время подачи* — сначала выберите час:", parse_mode="Markdown", reply_markup=time_hours_kb())
    await state.set_state(OrderForm.time)
    await cb.answer("Дата выбрана")

# ---- ВРЕМЯ: обработчики ----
@dp.callback_query(F.data == "timecancel")
async def time_cancel(cb: CallbackQuery, state: FSMContext):
    await cb.message.delete()
    await cb.answer("Выбор времени отменён")
    await bot.send_message(cb.message.chat.id, "Выберите *время подачи* (сначала час):", parse_mode="Markdown", reply_markup=time_hours_kb())
    await state.set_state(OrderForm.time)

@dp.callback_query(F.data == "timeback")
async def time_back(cb: CallbackQuery, state: FSMContext):
    try:
        await cb.message.edit_text("Выберите *время подачи* — сначала выберите час:", parse_mode="Markdown")
    except Exception:
        pass
    await cb.message.answer("Часы:", reply_markup=time_hours_kb())
    await cb.answer()

@dp.callback_query(F.data.startswith("timeh:"))
async def time_pick_hour(cb: CallbackQuery, state: FSMContext):
    hour = cb.data.split(":", 1)[1]
    try:
        await cb.message.edit_text(f"Час: *{hour}* — теперь выберите минуты:", parse_mode="Markdown")
    except Exception:
        pass
    await cb.message.answer("Минуты:", reply_markup=time_minutes_kb(hour))
    await cb.answer()

@dp.callback_query(F.data.startswith("timem:"))
async def time_pick_minutes(cb: CallbackQuery, state: FSMContext):
    _, hour, minute = cb.data.split(":")
    tm = f"{hour}:{minute}"
    data = await state.get_data()
    order = data.get("order", {})
    order["time"] = tm
    await state.update_data(order=order)

    await cb.message.edit_text(f"Время подачи: *{order['time']}* ✅", parse_mode="Markdown")
    await bot.send_message(cb.message.chat.id, "Укажите *количество человек*:", parse_mode="Markdown", reply_markup=pax_kb())
    await state.set_state(OrderForm.pax)
    await cb.answer("Время выбрано")

# ---- КАЛЬКУЛЯТОР (ручной ввод) ----
async def geocode_pair(from_city: str, to_city: str) -> Optional[Tuple[Dict[str, float], Dict[str, float]]]:
    async with aiohttp.ClientSession() as session:
        a = await geocode_city(session, from_city)
        b = await geocode_city(session, to_city)
    if not a or not b:
        return None
    return a, b

@dp.message(CalcStates.from_city, F.text)
async def calc_from_city(message: Message, state: FSMContext):
    from_city_input = normalize_city(message.text)
    from_city_canon = resolve_from_city(from_city_input)
    from_display = guess_from_display(from_city_input) if _norm_key(from_city_canon) == "минеральные воды" else from_city_canon
    await state.update_data(from_city=from_city_canon, from_display=from_display)
    await state.set_state(CalcStates.to_city)
    await message.answer("Введите *город прибытия* (или выберите ниже):", parse_mode="Markdown")
    await message.answer("Быстрый выбор:", reply_markup=dest_suggestions_kb(0))

@dp.message(CalcStates.to_city, F.text)
async def calc_to_city(message: Message, state: FSMContext):
    try:
        to_raw = normalize_city(message.text)
        data = await state.get_data()
        from_city = data.get("from_city") or "Минеральные Воды"
        from_display = data.get("from_display") or "Минеральные Воды"

        to_key = resolve_dest_key(to_raw)

        if to_key in FIXED_PRICES and _norm_key(from_city) == "минеральные воды":
            e, c, m = FIXED_PRICES[to_key]
            txt = (
                "⚠️ *Стоимость предварительная, окончательная цена оговаривается с диспетчером!*\n\n"
                f"🧮 *Калькулятор стоимости*\n\n"
                f"Из: *{from_display}*\nВ: *{to_raw}*\n\n"
                f"{prices_text_total_only(e, c, m)}"
            )
            await message.answer(txt, parse_mode="Markdown", reply_markup=main_menu_kb())
            await state.clear()
            return

        pair = await geocode_pair(from_city, to_raw)
        if not pair:
            await message.answer("❌ Не удалось определить города. Попробуйте ещё раз.")
            return
        a, b = pair
        dist = haversine_km(a["lat"], a["lon"], b["lat"], b["lon"])
        p_e, p_c, p_m = per_km_prices(dist)

        txt = (
            "⚠️ *Стоимость предварительная, окончательная цена оговаривается с диспетчером!*\n\n"
            f"🧮 *Калькулятор стоимости*\n\n"
            f"Из: *{from_display}*\nВ: *{to_raw}*\n\n"
            f"{prices_text_total_only(p_e, p_c, p_m)}"
        )
        await message.answer(txt, parse_mode="Markdown", reply_markup=main_menu_kb())
        await state.clear()
    except Exception as e:
        logger.exception(f"calc_to_city failed: {e}")
        await message.answer("Произошла ошибка при расчёте. Попробуйте ещё раз.", reply_markup=main_menu_kb())
        await state.clear()

# ---- СДЕЛАТЬ ЗАКАЗ ----
@dp.message(OrderForm.from_city, F.text)
async def order_from_city(message: Message, state: FSMContext):
    from_city_input = normalize_city(message.text)
    from_city_canon = resolve_from_city(from_city_input)
    from_display = guess_from_display(from_city_input) if _norm_key(from_city_canon) == "минеральные воды" else from_city_canon
    order = {"from_city": from_city_canon, "from_display": from_display}
    await state.update_data(order=order)
    await state.set_state(OrderForm.to_city)
    await message.answer("Введите *город прибытия* (или выберите ниже):", parse_mode="Markdown")
    await message.answer("Быстрый выбор:", reply_markup=dest_suggestions_kb(0))

@dp.message(OrderForm.to_city, F.text)
async def order_to_city(message: Message, state: FSMContext):
    data = await state.get_data(); order = data.get("order", {})
    order["to_city"] = normalize_city(message.text)
    await state.update_data(order=order)
    await state.set_state(OrderForm.date)

    today = date.today()
    await message.answer("Выберите *дату подачи*:", parse_mode="Markdown", reply_markup=date_calendar_kb(today.year, today.month))

@dp.message(OrderForm.date, F.text)
async def order_date_text_fallback(message: Message, state: FSMContext):
    order = (await state.get_data()).get("order", {})
    order["date"] = normalize_city(message.text)
    await state.update_data(order=order)
    await state.set_state(OrderForm.time)
    await message.answer("Выберите *время подачи* — сначала выберите час:", parse_mode="Markdown", reply_markup=time_hours_kb())

@dp.message(OrderForm.time, F.text)
async def order_time_text_fallback(message: Message, state: FSMContext):
    order = (await state.get_data()).get("order", {})
    order["time"] = normalize_city(message.text)
    await state.update_data(order=order)
    await state.set_state(OrderForm.pax)
    await message.answer("Укажите *количество человек*:", parse_mode="Markdown", reply_markup=pax_kb())

@dp.callback_query(F.data.startswith("pax:"))
async def pax_pick(cb: CallbackQuery, state: FSMContext):
    value = cb.data.split(":", 1)[1]  # "1".."6" или "7+"
    data = await state.get_data()
    order = data.get("order", {})
    order["pax"] = "7 и более" if value == "7+" else value
    await state.update_data(order=order)

    await cb.message.edit_text(f"Пассажиров: *{order['pax']}* ✅", parse_mode="Markdown")
    await bot.send_message(cb.message.chat.id, "Хотите оставить комментарий к заказу?", reply_markup=comment_choice_kb())
    await state.set_state(OrderForm.comment_choice)
    await cb.answer("Количество пассажиров указано")

@dp.message(OrderForm.pax, F.text)
async def pax_text_fallback(message: Message, state: FSMContext):
    raw = message.text.strip().lower()
    mapped = None
    if raw in {"1","2","3","4","5","6"}:
        mapped = raw
    elif raw in {"7","7+","7 и более","7 или больше","семь","семь и более"}:
        mapped = "7 и более"
    if mapped is None:
        await message.answer("Пожалуйста, укажите количество кнопкой или числом 1–6, либо «7 и более».", reply_markup=pax_kb())
        return

    order = (await state.get_data()).get("order", {})
    order["pax"] = mapped
    await state.update_data(order=order)
    await state.set_state(OrderForm.comment_choice)
    await message.answer("Хотите оставить комментарий к заказу?", reply_markup=comment_choice_kb())

# ---- КОММЕНТАРИЙ? Да/Нет ----
@dp.callback_query(F.data == "comment_yes")
async def comment_yes(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_text("Оставьте комментарий к заказу (или «-», если передумали):")
    await state.set_state(OrderForm.comment)
    await cb.answer()

@dp.callback_query(F.data == "comment_no")
async def comment_no(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data(); order = data.get("order", {})
    order["comment"] = ""
    await state.update_data(order=order)
    await cb.answer("Без комментария")
    await bot.send_message(cb.message.chat.id, "Введите *номер телефона* (+7 ...):", parse_mode="Markdown")
    await state.set_state(OrderForm.phone)

@dp.message(OrderForm.comment, F.text)
async def order_comment(message: Message, state: FSMContext):
    data = await state.get_data(); order = data.get("order", {})
    comment = message.text.strip()
    order["comment"] = "" if comment == "-" else comment
    await state.update_data(order=order)
    await state.set_state(OrderForm.phone)
    await message.answer("Введите *номер телефона* (+7 ...):", parse_mode="Markdown")

@dp.message(OrderForm.phone, F.text)
async def order_phone(message: Message, state: FSMContext):
    phone = message.text.strip()
    if not PHONE_RE.match(phone):
        await message.answer("❗ Укажите корректный номер телефона (+7 999 123-45-67)")
        return
    data = await state.get_data(); order = data.get("order", {})
    order["phone"] = phone
    await state.update_data(order=order)

    prices = await compute_prices_for_order(order.get("from_city",""), order.get("to_city",""))
    if prices is None:
        price_block = "💰 Стоимость: не удалось ориентировочно рассчитать (уточнит диспетчер)."
    else:
        e, c, m, _ = prices
        price_block = prices_text_total_only(e, c, m)

    txt = (
        f"Проверьте данные заказа:\n\n"
        f"Откуда: *{order.get('from_display', order.get('from_city',''))}*\n"
        f"Куда: *{order.get('to_city','')}*\n"
        f"Дата: *{order.get('date','')}*\n"
        f"Время: *{order.get('time','')}*\n"
        f"Пассажиров: *{order.get('pax','')}*\n"
        f"Телефон: *{order.get('phone','')}*\n"
        f"Комментарий: {order.get('comment') or '—'}\n\n"
        "⚠️ *Стоимость предварительная, окончательная цена оговаривается с диспетчером!*\n\n"
        f"{price_block}\n\n"
        "Подтвердить?"
    )
    await state.set_state(OrderForm.confirm)
    await message.answer(txt, parse_mode="Markdown", reply_markup=confirm_order_kb())

@dp.callback_query(F.data.in_(["order_confirm", "order_edit", "order_cancel"]))
async def order_finish(cb: CallbackQuery, state: FSMContext):
    action = cb.data
    if action == "order_cancel":
        await state.clear()
        await cb.message.edit_text("❌ Заказ отменён.")
        await cb.answer()
        await bot.send_message(cb.message.chat.id, "Вы в главном меню:", reply_markup=main_menu_kb())
        return
    if action == "order_edit":
        await state.clear()
        await cb.message.edit_text("Изменим заказ. Введите снова город отправления (или выберите ниже):")
        await state.set_state(OrderForm.from_city)
        await bot.send_message(cb.message.chat.id, "Быстрый выбор:", reply_markup=from_suggestions_kb())
        await cb.answer()
        return

    data = await state.get_data(); order = data.get("order", {})
    await state.clear()

    await cb.message.edit_text("✅ Спасибо, Ваша заявка принята! В ближайшее время с Вами свяжется диспетчер.")
    await bot.send_message(cb.message.chat.id, "Вы в главном меню:", reply_markup=main_menu_kb())
    await cb.answer("Заявка отправлена")

    price_text = ""
    prices = await compute_prices_for_order(order.get("from_city",""), order.get("to_city",""))
    if prices is not None:
        e, c, m, _ = prices
        price_text = "\n\nОриентировочно:\n" + prices_text_total_only(e, c, m)

    if ADMIN_CHAT_ID:
        try:
            user = cb.from_user
            txt = (
                f"🆕 *Заявка на заказ*\n\n"
                f"От: *{order.get('from_display', order.get('from_city',''))}* → *{order.get('to_city','')}*\n"
                f"Дата: *{order.get('date','')}*, Время: *{order.get('time','')}*\n"
                f"Пассажиров: *{order.get('pax','')}*\n"
                f"Телефон: *{order.get('phone','')}*\n"
                f"Комментарий: {order.get('comment') or '—'}"
                f"{price_text}\n\n"
                f"👤 {user.full_name} (id={user.id})"
            )
            await bot.send_message(ADMIN_CHAT_ID, txt, parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"Failed to notify admin: {e}")

# ---- ИНФОРМАЦИЯ ----
@dp.message(F.text == BTN_INFO)
async def info_handler(message: Message):
    await message.answer(
        "🚕 TransferAir междугороднее такси (Трансфер) из Минеральных Вод.\n\n"
        "🤖 Вы можете заказать трансфер через бота.\n\n"
        "📞 Позвонить нам: +79340241414\n\n"
        "🌐 Посетить наш сайт: https://transferkmw.ru",
    )

# ================== FASTAPI + WEBHOOK ==================
app = FastAPI()

@app.get("/")
async def healthcheck():
    return {"status": "ok"}

@app.post(f"/webhook/{{secret}}")
async def telegram_webhook(secret: str, request: Request):
    if WEBHOOK_SECRET and secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="forbidden")
    data = await request.json()
    update = Update.model_validate(data)
    await dp.feed_update(bot, update)
    return {"ok": True}

async def _set_webhook_with_retry():
    if not APP_BASE_URL:
        logger.warning("APP_BASE_URL не задан — вебхук не будет установлен")
        return
    url = f"{APP_BASE_URL}/webhook/{WEBHOOK_SECRET or ''}".rstrip("/")
    while True:
        try:
            await bot.set_my_commands([BotCommand(command="start", description="Запуск")])
            await bot.set_webhook(url=url, secret_token=WEBHOOK_SECRET or None, drop_pending_updates=True)
            logger.info("Webhook set to %s", url)
            break
        except Exception as e:
            logger.warning("Webhook not set yet (%s). Retrying soon…", e)
            await asyncio.sleep(30)

@app.on_event("startup")
async def on_startup():
    asyncio.create_task(_set_webhook_with_retry())
    logger.info("Startup complete. Waiting for webhook setup…")

@app.on_event("shutdown")
async def on_shutdown():
    try:
        await bot.delete_webhook(drop_pending_updates=False)
        logger.info("Webhook removed")
    except Exception as e:
        logger.warning(f"Failed to delete webhook: {e}")
