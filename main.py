import os
import math
import asyncio
import logging
import re
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

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

# ================== LOGGING ==================
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("tgbot")

# ================== AIOGRAM CORE ==================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ================== ЛЕЙБЛЫ КНОПОК ==================
BTN_START = "▶️ Старт"
BTN_CALC = "🧮 Калькулятор стоимости"
BTN_ORDER = "📝 Сделать заказ"
BTN_DISPATCHER = "☎️ Диспетчер"
BTN_INFO = "ℹ️ Информация"

MENU_BUTTONS = [BTN_CALC, BTN_ORDER, BTN_DISPATCHER, BTN_INFO]

# ================== ТАРИФЫ (пер.км для городов без фикса) ==================
TARIFFS = {
    "econom":  {"title": "Легковой", "per_km": 30},
    "camry":   {"title": "Camry",    "per_km": 40},
    "minivan": {"title": "Минивэн",  "per_km": 50},
}

# ================== ФИКСИРОВАННЫЕ ЦЕНЫ ==================
# Ключи – нормализованные названия ПУНКТА НАЗНАЧЕНИЯ (из Минеральных Вод).
# Значения – (легковой, camry, минивэн)
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
    "эльбрус": (5500, 7500, 8500),
    "теберда": (5500, 7500, 8500),
    "нейтрино": (5000, 7500, 8500),
    "тегенекли": (5000, 7500, 8500),
    "байдаево": (5000, 7500, 8500),
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
# from-синонимы (все приводим к «Минеральные Воды»)
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

# dest-алиасы: ключ – вариант ввода (нормализованный), значение – КЛЮЧ из FIXED_PRICES
DEST_ALIASES = {
    # курортные
    "железка": "железноводск",
    "жв": "железноводск",
    "пятиг": "пятигорск",
    "ессы": "ессентуки",
    "кислов": "кисловодск",

    # эльбрус/домбай
    "романтик": "архыз романтик",
    "архыз-романтик": "архыз романтик",
    "приэльбрусье": "эльбрус",
    "поляна азау": "азау",
    "мир азау": "азау",
    "чегет поляна": "чегет",

    # города
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

def resolve_dest_key(text: str) -> str:
    key = _norm_key(text)
    if key in FIXED_PRICES:
        return key
    return DEST_ALIASES.get(key, key)

# ================== ПРЕДУСТАНОВЛЕННЫЕ ПОДСКАЗКИ ДЛЯ ВЫБОРА ГОРОДА ==================
# список «красивое название», «ключ FIXED_PRICES»
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

def from_suggestions_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Минеральные Воды", callback_data="from_pick:Минеральные Воды"),
        InlineKeyboardButton(text="Минеральные Воды (аэропорт)", callback_data="from_pick:Минеральные Воды"),
    ]])
    return kb

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
    # пагинация
    max_page = (len(DEST_OPTIONS) - 1) // per_page
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⏮️ Назад", callback_data=f"dest_page:{page-1}"))
    if page < max_page:
        nav.append(InlineKeyboardButton(text="Вперёд ⏭️", callback_data=f"dest_page:{page+1}"))
    if nav:
        rows.append(nav)
    return InlineKeyboardMarkup(inline_keyboard=rows)

# ================== КЛАВИАТУРЫ ОСНОВНОГО МЕНЮ ==================
def start_big_button_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_START)]],
        resize_keyboard=True,
        is_persistent=True,
    )

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
            url="https://t.me/sergeomoscarpone"
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
    phone = State()
    comment = State()
    confirm = State()

# ================== ХЕЛПЕРЫ ==================
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
        f"• Легковой — ~{econom} ₽\n"
        f"• Camry — ~{camry} ₽\n"
        f"• Минивэн — ~{minivan} ₽"
    )

def per_km_prices(distance_km: float) -> Tuple[int, int, int]:
    d = max(1.0, round(distance_km, 1))
    p_e = int(round(d * TARIFFS["econom"]["per_km"]))
    p_c = int(round(d * TARIFFS["camry"]["per_km"]))
    p_m = int(round(d * TARIFFS["minivan"]["per_km"]))
    return p_e, p_c, p_m

PHONE_RE = re.compile(r"^\+?\d[\d\-\s]{8,}$")

# ================== ГЛОБАЛЬНЫЙ РОУТЕР МЕНЮ (работает в ЛЮБОМ состоянии) ==================
@dp.message(F.text.in_(MENU_BUTTONS))
async def menu_router(message: Message, state: FSMContext):
    await state.clear()
    text = message.text

    if text == BTN_CALC:
        await state.set_state(CalcStates.from_city)
        await message.answer(
            "Введите *город отправления* (или выберите ниже):",
            parse_mode="Markdown",
            reply_markup=None
        )
        await message.answer("Быстрый выбор:", reply_markup=from_suggestions_kb())
        return

    if text == BTN_ORDER:
        await state.set_state(OrderForm.from_city)
        await state.update_data(order={})
        await message.answer(
            "Введите *город отправления* (или выберите ниже):",
            parse_mode="Markdown"
        )
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
            "TransferAir междугороднее такси (Трансфер) из Минеральных Вод.\n\n"
            "Вы можете заказать трансфер через бота, позвонить нам: +7 934 024-14-14,\n"
            "или посетить сайт: https://transferkmw.ru",
        )
        return

# ================== START ==================
@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    text = (
        " \n"
        "*Здравствуйте!* \n"
        "Это бот междугороднего такси \n"
        "*TransferAir Кавказские Минеральные Воды*.\n"
        " \n"
        f"Нажмите *{BTN_START.split()[0]} Старт*, чтобы продолжить."
    )
    await message.answer(text, parse_mode="Markdown", reply_markup=start_big_button_kb())

@dp.message(F.text == BTN_START)
async def on_big_start(message: Message, state: FSMContext):
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
    await cb.message.answer(
        "📱 Телефон диспетчера:\n"
        "`+7 934 024-14-14`\n\n"
        "Скопируйте номер и позвоните вручную.",
        parse_mode="Markdown",
    )
    await cb.answer("Номер отправлен")

# ================== ПОДХВАТ КЛИКОВ-ПОДСКАЗОК (from/to) ==================
@dp.callback_query(F.data.startswith("from_pick:"))
async def pick_from(cb: CallbackQuery, state: FSMContext):
    from_city = cb.data.split(":", 1)[1]
    # Куда дальше направлять – зависит от сценария
    current = await state.get_state()
    if current and current.endswith("from_city"):
        if current.startswith("CalcStates"):
            await state.update_data(from_city=from_city)
            await state.set_state(CalcStates.to_city)
            await cb.message.edit_text(f"Отправление: *{from_city}* ✅\nВведите *город прибытия* (или выберите ниже):", parse_mode="Markdown")
            await cb.message.answer("Быстрый выбор:", reply_markup=dest_suggestions_kb(0))
        else:
            # OrderForm
            order = {"from_city": from_city}
            await state.update_data(order=order)
            await state.set_state(OrderForm.to_city)
            await cb.message.edit_text(f"Отправление: *{from_city}* ✅\nВведите *город прибытия* (или выберите ниже):", parse_mode="Markdown")
            await cb.message.answer("Быстрый выбор:", reply_markup=dest_suggestions_kb(0))
    await cb.answer()

@dp.callback_query(F.data.startswith("dest_page:"))
async def dest_page(cb: CallbackQuery):
    page = int(cb.data.split(":", 1)[1])
    try:
        await cb.message.edit_reply_markup(reply_markup=dest_suggestions_kb(page))
    except Exception:
        # если сообщение без разметки – отправим новое
        await cb.message.answer("Ещё варианты:", reply_markup=dest_suggestions_kb(page))
    await cb.answer()

@dp.callback_query(F.data.startswith("dest_pick:"))
async def dest_pick(cb: CallbackQuery, state: FSMContext):
    key = cb.data.split(":", 1)[1]  # ключ FIXED_PRICES
    display = next((d for d, k in DEST_OPTIONS if k == key), key.title())

    current = await state.get_state()
    if current and current.endswith("to_city"):
        if current.startswith("CalcStates"):
            # завершаем калькулятор – либо фикс, либо расстояние
            data = await state.get_data()
            from_city = data.get("from_city") or "Минеральные Воды"
            await state.clear()

            if key in FIXED_PRICES and _norm_key(from_city) in {"минеральные воды"}:
                e, c, m = FIXED_PRICES[key]
                txt = (
                    "⚠️ *Стоимость предварительная, окончательная цена оговаривается с диспетчером!*\n\n"
                    f"🧮 *Калькулятор стоимости*\n\n"
                    f"Из: *Минеральные Воды*\nВ: *{display}*\n\n"
                    f"{prices_text_total_only(e, c, m)}"
                )
                await cb.message.edit_text(txt, parse_mode="Markdown")
                await bot.send_message(cb.message.chat.id, "Вы в главном меню:", reply_markup=main_menu_kb())
                await cb.answer()
                return
            # fallback: считаем по расстоянию
            async with aiohttp.ClientSession() as session:
                a = await geocode_city(session, from_city)
                b = await geocode_city(session, display)
            if not a or not b:
                await cb.message.answer("❌ Не удалось определить города. Попробуйте ещё раз.")
                await cb.answer()
                return
            dist = haversine_km(a["lat"], a["lon"], b["lat"], b["lon"])
            p_e, p_c, p_m = per_km_prices(dist)
            txt = (
                "⚠️ *Стоимость предварительная, окончательная цена оговаривается с диспетчером!*\n\n"
                f"🧮 *Калькулятор стоимости*\n\n"
                f"Из: *{from_city}*\nВ: *{display}*\n\n"
                f"{prices_text_total_only(p_e, p_c, p_m)}"
            )
            await cb.message.edit_text(txt, parse_mode="Markdown")
            await bot.send_message(cb.message.chat.id, "Вы в главном меню:", reply_markup=main_menu_kb())
            await cb.answer()
            return

        else:
            # OrderForm: подставляем «to_city» и продолжаем форму
            data = await state.get_data()
            order = data.get("order", {})
            order["to_city"] = display
            await state.update_data(order=order)
            await state.set_state(OrderForm.date)
            await cb.message.edit_text(f"Направление: *{display}* ✅", parse_mode="Markdown")
            await cb.message.answer("Введите *дату подачи* (например, 31.10.2025):", parse_mode="Markdown")
    await cb.answer()

# ---- КАЛЬКУЛЯТОР (ручной ввод) ----
@dp.message(CalcStates.from_city, F.text)
async def calc_from_city(message: Message, state: FSMContext):
    from_city = resolve_from_city(message.text)
    await state.update_data(from_city=from_city)
    await state.set_state(CalcStates.to_city)
    await message.answer("Введите *город прибытия* (или выберите ниже):", parse_mode="Markdown")
    await message.answer("Быстрый выбор:", reply_markup=dest_suggestions_kb(0))

@dp.message(CalcStates.to_city, F.text)
async def calc_to_city(message: Message, state: FSMContext):
    to_raw = normalize_city(message.text)
    data = await state.get_data()
    from_city = data.get("from_city") or "Минеральные Воды"

    # алиас → ключ
    to_key = resolve_dest_key(to_raw)

    # 1) если фикс и отправление МинВоды
    if to_key in FIXED_PRICES and _norm_key(from_city) in {"минеральные воды"}:
        e, c, m = FIXED_PRICES[to_key]
        txt = (
            "⚠️ *Стоимость предварительная, окончательная цена оговаривается с диспетчером!*\n\n"
            f"🧮 *Калькулятор стоимости*\n\n"
            f"Из: *Минеральные Воды*\nВ: *{to_raw}*\n\n"
            f"{prices_text_total_only(e, c, m)}"
        )
        await message.answer(txt, parse_mode="Markdown", reply_markup=main_menu_kb())
        await state.clear()
        return

    # 2) иначе считаем по расстоянию (но показываем только суммы)
    async with aiohttp.ClientSession() as session:
        a = await geocode_city(session, from_city)
        b = await geocode_city(session, to_raw)

    if not a or not b:
        await message.answer("❌ Не удалось определить города. Попробуйте ещё раз.")
        return

    dist = haversine_km(a["lat"], a["lon"], b["lat"], b["lon"])
    p_e, p_c, p_m = per_km_prices(dist)

    txt = (
        "⚠️ *Стоимость предварительная, окончательная цена оговаривается с диспетчером!*\n\n"
        f"🧮 *Калькулятор стоимости*\n\n"
        f"Из: *{from_city}*\nВ: *{to_raw}*\n\n"
        f"{prices_text_total_only(p_e, p_c, p_m)}"
    )
    await message.answer(txt, parse_mode="Markdown", reply_markup=main_menu_kb())
    await state.clear()

# ---- СДЕЛАТЬ ЗАКАЗ ----
@dp.message(OrderForm.from_city, F.text)
async def order_from_city(message: Message, state: FSMContext):
    order = {"from_city": resolve_from_city(message.text)}
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
    await message.answer("Введите *дату подачи* (например, 31.10.2025):", parse_mode="Markdown")

@dp.message(OrderForm.date, F.text)
async def order_date(message: Message, state: FSMContext):
    data = await state.get_data(); order = data.get("order", {})
    order["date"] = normalize_city(message.text)
    await state.update_data(order=order)
    await state.set_state(OrderForm.time)
    await message.answer("Введите *время подачи* (например, 14:30):", parse_mode="Markdown")

@dp.message(OrderForm.time, F.text)
async def order_time(message: Message, state: FSMContext):
    data = await state.get_data(); order = data.get("order", {})
    order["time"] = normalize_city(message.text)
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
    await state.set_state(OrderForm.comment)
    await message.answer("Комментарий к заказу (если нет — напишите «-»):", parse_mode="Markdown")

@dp.message(OrderForm.comment, F.text)
async def order_comment(message: Message, state: FSMContext):
    data = await state.get_data(); order = data.get("order", {})
    comment = message.text.strip()
    order["comment"] = "" if comment == "-" else comment
    await state.update_data(order=order)
    txt = (
        f"Проверьте данные заказа:\n\n"
        f"Откуда: *{order['from_city']}*\n"
        f"Куда: *{order['to_city']}*\n"
        f"Дата: *{order['date']}*\n"
        f"Время: *{order['time']}*\n"
        f"Телефон: *{order['phone']}*\n"
        f"Комментарий: {order['comment'] or '—'}\n\n"
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
        await cb.message.edit_text("Изменим заказ. Введите снова город отправления:")
        await state.set_state(OrderForm.from_city)
        await cb.answer()
        return

    data = await state.get_data(); order = data.get("order", {})
    await state.clear()

    await cb.message.edit_text("✅ Спасибо, Ваша заявка принята! В ближайшее время с Вами свяжется диспетчер.")
    await bot.send_message(cb.message.chat.id, "Вы в главном меню:", reply_markup=main_menu_kb())
    await cb.answer("Заявка отправлена")

    if ADMIN_CHAT_ID:
        try:
            user = cb.from_user
            txt = (
                f"🆕 *Заявка на заказ*\n\n"
                f"От: *{order['from_city']}* → *{order['to_city']}*\n"
                f"Дата: *{order['date']}*, Время: *{order['time']}*\n"
                f"Телефон: *{order['phone']}*\n"
                f"Комментарий: {order['comment'] or '—'}\n\n"
                f"👤 {user.full_name} (id={user.id})"
            )
            await bot.send_message(ADMIN_CHAT_ID, txt, parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"Failed to notify admin: {e}")

# ---- ИНФОРМАЦИЯ ----
@dp.message(F.text == BTN_INFO)
async def info_handler(message: Message):
    await message.answer(
        "TransferAir междугороднее такси (Трансфер) из Минеральных Вод.\n\n"
        "Вы можете заказать трансфер через бота, позвонить нам: +7 934 024-14-14,\n"
        "или посетить сайт: https://transferkmw.ru",
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
