import os
import math
import asyncio
import logging
import re
from typing import Final, Dict, Optional

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

class OrderStates(StatesGroup):
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

# ================== ХЕНДЛЕРЫ ==================
@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    text = (
        " \n"
        "*Здравствуйте!* \n"
        "Это бот междугороднего такси \n"
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
class OrderForm(StatesGroup):
    from_city = State()
    to_city = State()
    date = State()
    time = State()
    phone = State()
    comment = State()
    confirm = State()

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
