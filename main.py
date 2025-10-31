import os
import math
import asyncio
import logging
import re
from typing import Final, Dict, Optional, Tuple
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
USE_WEBHOOK: bool = os.getenv("USE_WEBHOOK", "true").lower() in ("1", "true", "yes")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "7039409310") or 7039409310)

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{APP_BASE_URL}{WEBHOOK_PATH}" if USE_WEBHOOK else ""

# ================== LOGGING ==================
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger("tgbot")

# ================== AIOGRAM CORE ==================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ================== ТАРИФЫ ==================
TARIFFS = {
    "econom":  {"title": "Легковой", "per_km": 30},
    "camry":   {"title": "Camry", "per_km": 40},
    "minivan": {"title": "Минивэн", "per_km": 50},
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
    "эльбрус": (5500, 7500, 8500),
    "теберда": (5500, 7500, 8500),
    "чегет": (5500, 7500, 9000),
    "ставрополь": (5400, 7200, 9000),
    "черкесск": (3000, 4000, 5000),
    "нальчик": (3300, 4400, 5500),
    "владикавказ": (6600, 8800, 11000),
    "грозный": (9300, 12400, 15500),
    "адлер": (17400, 23200, 29000),
}

# ================== КЛАВИАТУРЫ ==================
def start_big_button_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="▶️ Старт")]],
        resize_keyboard=True,
        is_persistent=True,
    )

def main_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🧮 Калькулятор стоимости")],
            [KeyboardButton(text="📝 Сделать заказ")],
            [KeyboardButton(text="☎️ Диспетчер")],
            [KeyboardButton(text="ℹ️ Информация")],
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

# ================== СОСТОЯНИЯ ==================
class CalcStates(StatesGroup):
    from_city = State()
    to_city = State()

# ================== УТИЛИТЫ ==================
def normalize_key(text: str) -> str:
    s = text.strip().lower().replace("ё", "е")
    s = re.sub(r"\s*-\s*", "-", s)
    return s

def normalize_city(text: str) -> str:
    return " ".join(text.strip().split())

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlmb/2)**2
    return R * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))

async def geocode_city(session: aiohttp.ClientSession, city: str) -> Optional[Dict[str, float]]:
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": city, "format": "json", "limit": 1}
    headers = {"User-Agent": "TransferAir-Bot/1.0"}
    try:
        async with session.get(url, params=params, headers=headers) as r:
            data = await r.json()
            if data:
                return {"lat": float(data[0]["lat"]), "lon": float(data[0]["lon"])}
    except Exception as e:
        logger.warning(f"Geocode error: {e}")
    return None

def get_fixed_price(city: str) -> Optional[Tuple[int, int, int]]:
    key = normalize_key(city)
    return FIXED_PRICES.get(key)

def format_prices_block(e: int, c: int, m: int, dist: Optional[float] = None) -> str:
    text = ""
    if dist:
        text += f"Расстояние: ~{round(dist,1)} км\n\n"
    text += f"💰 Стоимость:\n• Легковой — ~{e} ₽\n• Camry — ~{c} ₽\n• Минивэн — ~{m} ₽"
    return text

# ================== ХЕНДЛЕРЫ ==================
@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    text = (
        "*Здравствуйте!*\n"
        "Это бот междугороднего такси\n"
        "*TransferAir Кавказские Минеральные Воды*.\n\n"
        "Нажмите *Старт*, чтобы продолжить."
    )
    await message.answer(text, parse_mode="Markdown", reply_markup=start_big_button_kb())

@dp.message(F.text == "▶️ Старт")
async def start_menu(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Выберите действие:", reply_markup=main_menu_kb())

@dp.message(F.text.in_(["ℹ️ Информация", "Информация"]))
async def info_handler(message: Message):
    await message.answer(
        "TransferAir междугороднее такси (Трансфер) из Минеральных Вод. "
        "Можете заказать трансфер через бота, позвонить нам +79340241414, "
        "или посетить наш сайт: https://transferkmw.ru",
        disable_web_page_preview=True
    )

# ---- ДИСПЕТЧЕР ----
@dp.message(F.text == "☎️ Диспетчер")
async def dispatcher(message: Message):
    await message.answer(
        "☎️ *Связаться с диспетчером*\n\n"
        "Нажмите кнопку ниже, чтобы написать диспетчеру в Telegram\n"
        "или получить номер телефона для звонка.",
        parse_mode="Markdown",
        reply_markup=dispatcher_inline_kb()
    )

@dp.callback_query(F.data == "dispatcher_phone")
async def phone_callback(cb: CallbackQuery):
    await cb.message.answer(
        "📱 Телефон диспетчера:\n`+7 934 024-14-14`\n\nСкопируйте номер и позвоните вручную.",
        parse_mode="Markdown",
    )
    await cb.answer()

# ---- КАЛЬКУЛЯТОР ----
@dp.message(F.text == "🧮 Калькулятор стоимости")
async def calc_start(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(CalcStates.from_city)
    await message.answer("Введите *город отправления*:", parse_mode="Markdown")

@dp.message(CalcStates.from_city, F.text)
async def calc_from(message: Message, state: FSMContext):
    await state.update_data(from_city=normalize_city(message.text))
    await state.set_state(CalcStates.to_city)
    await message.answer("Введите *город прибытия*:", parse_mode="Markdown")

@dp.message(CalcStates.to_city, F.text)
async def calc_to(message: Message, state: FSMContext):
    data = await state.get_data()
    from_city = data.get("from_city")
    to_city = normalize_city(message.text)

    fixed = get_fixed_price(to_city)
    if fixed:
        e, c, m = fixed
        txt = (
            "⚠️ *Стоимость предварительная, окончательная цена оговаривается диспетчером!*\n\n"
            f"Из: *{from_city}*\nВ: *{to_city}*\n\n{format_prices_block(e, c, m)}"
        )
        await message.answer(txt, parse_mode="Markdown", reply_markup=main_menu_kb())
        await state.clear()
        return

    async with aiohttp.ClientSession() as session:
        a = await geocode_city(session, from_city)
        b = await geocode_city(session, to_city)

    if not a or not b:
        await message.answer("❌ Не удалось определить города. Попробуйте ещё раз.")
        return

    dist = haversine_km(a["lat"], a["lon"], b["lat"], b["lon"])
    e = int(round(dist * 30))
    c = int(round(dist * 40))
    m = int(round(dist * 50))
    txt = (
        "⚠️ *Стоимость предварительная, окончательная цена оговаривается диспетчером!*\n\n"
        f"Из: *{from_city}*\nВ: *{to_city}*\n\n{format_prices_block(e, c, m, dist)}"
    )
    await message.answer(txt, parse_mode="Markdown", reply_markup=main_menu_kb())
    await state.clear()

# ================== FASTAPI ==================
app = FastAPI()

@app.get("/")
async def root():
    return {"status": "ok"}

@app.post("/webhook")
async def telegram_webhook(request: Request):
    if USE_WEBHOOK:
        token = request.headers.get("x-telegram-bot-api-secret-token")
        if token != WEBHOOK_SECRET:
            raise HTTPException(status_code=403)
    data = await request.json()
    update = Update.model_validate(data)
    await dp.feed_update(bot, update)
    return {"ok": True}

@app.on_event("startup")
async def on_startup():
    if USE_WEBHOOK:
        try:
            await bot.set_webhook(WEBHOOK_URL, secret_token=WEBHOOK_SECRET)
            logger.info(f"Webhook set: {WEBHOOK_URL}")
        except Exception as e:
            logger.warning(f"Webhook error: {e}")
    else:
        asyncio.create_task(dp.start_polling(bot))
