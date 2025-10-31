import os
import math
import asyncio
import logging
import re
from functools import lru_cache
from datetime import datetime
from typing import Final, Dict, Optional

from fastapi import FastAPI, Request, HTTPException
from starlette.responses import JSONResponse
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Update, Message, BotCommand, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
import aiohttp

# --------- .env (необязательно, но удобно) ---------
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    pass

# ================== CONFIG ==================
BOT_TOKEN: Final[str] = os.getenv("BOT_TOKEN", "")
APP_BASE_URL: Final[str] = os.getenv("APP_BASE_URL", "").rstrip("/")
WEBHOOK_SECRET: Final[str] = os.getenv("WEBHOOK_SECRET", "")
USE_WEBHOOK: bool = os.getenv("USE_WEBHOOK", "true").lower() in ("1", "true", "yes")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "7039409310") or 7039409310)

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

if USE_WEBHOOK:
    # Для режима вебхука нужен base URL + secret
    if not APP_BASE_URL:
        raise RuntimeError("APP_BASE_URL is not set (required in webhook mode)")
    if not WEBHOOK_SECRET:
        raise RuntimeError("WEBHOOK_SECRET is not set (required in webhook mode)")

WEBHOOK_PATH = "/webhook"  # фиксированный путь
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
    "camry":   {"title": "Camry",    "per_km": 40},
    "minivan": {"title": "Минивэн",  "per_km": 50},
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

@lru_cache(maxsize=512)
def _cached_city_key(city: str) -> str:
    # Нормализованный ключ для кэша
    return " ".join(city.strip().split()).lower()

@lru_cache(maxsize=512)
def _geocode_cached(city_norm_key: str) -> Optional[Dict[str, float]]:
    # Пустышка для сигнатуры кэша — реальный http идёт в async-обёртке
    return None

async def geocode_city(session: aiohttp.ClientSession, city: str) -> Optional[Dict[str, float]]:
    key = _cached_city_key(city)
    cached = _geocode_cached(key)
    if cached:
        return cached

    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": city, "format": "json", "limit": 1}
    headers = {"User-Agent": "TransferAir-KMV-Bot/1.1 (admin@example.com)"}
    try:
        async with session.get(url, params=params, headers=headers, timeout=20) as r:
            if r.status != 200:
                return None
            data = await r.json()
            if not data:
                return None
            result = {"lat": float(data[0]["lat"]), "lon": float(data[0]["lon"])}
            # Прокладываем в LRU-кэш через хак: сохраняем из async-функции
            _geocode_cached.cache_clear()  # на случай коллизий ключей
            @lru_cache(maxsize=512)
            def _store(k: str, v: tuple) -> tuple:
                return v
            _store(key, (result["lat"], result["lon"]))
            # Обратно читаем, чтобы следующий вызов был мгновенным
            return {"lat": _store(key, (result["lat"], result["lon"]))[0],
                    "lon": _store(key, (result["lat"], result["lon"]))[1]}
    except Exception as e:
        logger.warning(f"Geocode failed for {city}: {e}")
        return None

def normalize_city(text: str) -> str:
    return " ".join(text.strip().split())

def prices_block(distance_km: float) -> str:
    d = max(1.0, round(distance_km, 1))
    p_e = int(round(d * TARIFFS["econom"]["per_km"]))
    p_c = int(round(d * TARIFFS["camry"]["per_km"]))
    p_m = int(round(d * TARIFFS["minivan"]["per_km"]))
    return (
        f"Расстояние: ~{d} км\n\n"
        f"💰 Стоимость:\n"
        f"• Легковой — ~{p_e} ₽ (30 ₽/км)\n"
        f"• Camry — ~{p_c} ₽ (40 ₽/км)\n"
        f"• Минивэн — ~{p_m} ₽ (50 ₽/км)"
    )

PHONE_RE = re.compile(r"^\+?\d[\d\-\s]{8,}$")
DATE_FMT = "%d.%m.%Y"
TIME_FMT = "%H:%M"

def _parse_date(text: str) -> Optional[str]:
    try:
        dt = datetime.strptime(text.strip(), DATE_FMT)
        return dt.strftime(DATE_FMT)
    except Exception:
        return None

def _parse_time(text: str) -> Optional[str]:
    try:
        tm = datetime.strptime(text.strip(), TIME_FMT)
        return tm.strftime(TIME_FMT)
    except Exception:
        return None

# ================== ХЕНДЛЕРЫ ==================
@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    text = (
        " \n"
        "*Здравствуйте!*\n"
        "Это бот междугороднего такси\n"
        "*TransferAir Кавказские Минеральные Воды*.\n"
        " \n"
        "Нажмите *Старт*, чтобы продолжить."
    )
    await message.answer(text, parse_mode="Markdown", reply_markup=start_big_button_kb())

@dp.message(F.text == "▶️ Старт")
async def on_big_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Выберите действие:", reply_markup=main_menu_kb())

# ---- ДИСПЕТЧЕР ----
@dp.message(F.text == "☎️ Диспетчер")
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

# ---- КАЛЬКУЛЯТОР ----
@dp.message(F.text == "🧮 Калькулятор стоимости")
async def calc_start(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(CalcStates.from_city)
    await message.answer("Введите *город отправления*:", parse_mode="Markdown")

@dp.message(CalcStates.from_city, F.text)
async def calc_from_city(message: Message, state: FSMContext):
    city = normalize_city(message.text)
    await state.update_data(from_city=city)
    await state.set_state(CalcStates.to_city)
    await message.answer("Введите *город прибытия*:", parse_mode="Markdown")

@dp.message(CalcStates.to_city, F.text)
async def calc_to_city(message: Message, state: FSMContext):
    to_city = normalize_city(message.text)
    data = await state.get_data()
    from_city = data.get("from_city")

    async with aiohttp.ClientSession() as session:
        a = await geocode_city(session, from_city)
        b = await geocode_city(session, to_city)

    if not a or not b:
        await message.answer(
            "❌ Не удалось определить города. Попробуйте полные названия (например: `Кисловодск`, `Минеральные Воды`).",
            parse_mode="Markdown",
        )
        return

    dist = haversine_km(a["lat"], a["lon"], b["lat"], b["lon"])
    txt = (
        f"🧮 *Калькулятор стоимости*\n\n"
        f"Из: *{from_city}*\nВ: *{to_city}*\n\n"
        f"{prices_block(dist)}"
    )
    await message.answer(txt, parse_mode="Markdown", reply_markup=main_menu_kb())
    await state.clear()

# ---- СДЕЛАТЬ ЗАКАЗ ----
@dp.message(F.text == "📝 Сделать заказ")
async def order_start(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(OrderForm.from_city)
    await state.update_data(order={})
    await message.answer("Введите *город отправления*:", parse_mode="Markdown")

@dp.message(OrderForm.from_city, F.text)
async def order_from_city(message: Message, state: FSMContext):
    order = {"from_city": normalize_city(message.text)}
    await state.update_data(order=order)
    await state.set_state(OrderForm.to_city)
    await message.answer("Введите *город прибытия*:", parse_mode="Markdown")

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
    maybe_date = _parse_date(message.text)
    if not maybe_date:
        await message.answer("❗ Укажите дату в формате ДД.ММ.ГГГГ (например, 31.10.2025)")
        return
    order["date"] = maybe_date
    await state.update_data(order=order)
    await state.set_state(OrderForm.time)
    await message.answer("Введите *время подачи* (например, 14:30):", parse_mode="Markdown")

@dp.message(OrderForm.time, F.text)
async def order_time(message: Message, state: FSMContext):
    data = await state.get_data(); order = data.get("order", {})
    maybe_time = _parse_time(message.text)
    if not maybe_time:
        await message.answer("❗ Укажите время в формате ЧЧ:ММ (например, 14:30)")
        return
    order["time"] = maybe_time
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

# ================== FASTAPI + WEBHOOK/POLLING ==================
app = FastAPI()

@app.get("/")
async def healthcheck():
    return {"status": "ok", "mode": "webhook" if USE_WEBHOOK else "polling"}

def _validate_telegram_secret(request: Request):
    # Telegram присылает секрет в заголовке X-Telegram-Bot-Api-Secret-Token
    header = request.headers.get("x-telegram-bot-api-secret-token")
    if not header or header != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="forbidden")

@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    if USE_WEBHOOK:
        _validate_telegram_secret(request)
    data = await request.json()
    update = Update.model_validate(data)
    await dp.feed_update(bot, update)
    return {"ok": True}

async def _set_webhook_with_retry():
    if not USE_WEBHOOK:
        return
    url = WEBHOOK_URL
    while True:
        try:
            await bot.set_my_commands([BotCommand(command="start", description="Запуск")])
            await bot.set_webhook(
                url=url,
                secret_token=WEBHOOK_SECRET,
                drop_pending_updates=True
            )
            logger.info("Webhook set to %s", url)
            break
        except Exception as e:
            logger.warning("Webhook not set yet (%s). Retrying soon…", e)
            await asyncio.sleep(30)

async def _start_polling():
    # локальный режим (без вебхука)
    await bot.set_my_commands([BotCommand(command="start", description="Запуск")])
    logger.info("Starting polling…")
    await dp.start_polling(bot)

@app.on_event("startup")
async def on_startup():
    if USE_WEBHOOK:
        asyncio.create_task(_set_webhook_with_retry())
        logger.info("Startup complete. Waiting for webhook setup…")
    else:
        # В polling нельзя блокировать ивент-луп — стартуем в фоне.
        asyncio.create_task(_start_polling())

@app.on_event("shutdown")
async def on_shutdown():
    try:
        if USE_WEBHOOK:
            await bot.delete_webhook(drop_pending_updates=False)
            logger.info("Webhook removed")
    except Exception as e:
        logger.warning(f"Failed to delete webhook: {e}")

# --------- Глобальный ловец ошибок FastAPI (красивее 500) ---------
@app.exception_handler(Exception)
async def on_error(request: Request, exc: Exception):
    logger.exception("Unhandled error: %s", exc)
    return JSONResponse({"ok": False, "error": "internal"}, status_code=500)
