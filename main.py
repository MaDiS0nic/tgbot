import os
import math
import asyncio
import logging
import re
from typing import Final, Dict, Any, Optional

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

# ================== CONSTANTS ==================
TARIFFS = {
    "econom":  {"title": "Легковой", "per_km": 30},
    "camry":   {"title": "Camry",    "per_km": 40},
    "minivan": {"title": "Минивэн",  "per_km": 50},
}

# ================== KEYBOARDS ==================
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
    # на мобильных Telegram корректно открывает набор номера по tel:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Позвонить диспетчеру", url="tel:+79340241414")
    ]])

def confirm_order_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Подтвердить", callback_data="order_confirm"),
        InlineKeyboardButton(text="✏️ Изменить", callback_data="order_edit"),
        InlineKeyboardButton(text="❌ Отменить", callback_data="order_cancel"),
    ]])

# ================== STATES ==================
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

# ================== HELPERS ==================
def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi/2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb/2) ** 2
    return R * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))

async def geocode_city(session: aiohttp.ClientSession, city: str) -> Optional[Dict[str, float]]:
    # Nominatim требует User-Agent
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": city,
        "format": "json",
        "limit": 1,
    }
    headers = {"User-Agent": "TransferAir-KMV-TelegramBot/1.0 (contact: admin@example.com)"}
    try:
        async with session.get(url, params=params, headers=headers, timeout=20) as r:
            if r.status != 200:
                return None
            data = await r.json()
            if not data:
                return None
            lat = float(data[0]["lat"]); lon = float(data[0]["lon"])
            return {"lat": lat, "lon": lon}
    except Exception as e:
        logger.warning("Geocode failed for %s: %s", city, e)
        return None

def format_prices_km(distance_km: float) -> str:
    d = round(distance_km, 1)
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

def normalize_city(text: str) -> str:
    return " ".join(text.strip().split())

PHONE_RE = re.compile(r"^\+?\d[\d\-\s]{8,}$")

# ================== HANDLERS ==================
@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    # "центр" в Telegram нельзя задать, сделаем визуально с пустыми строками
    text = (
        " \n"
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
    await message.answer("Связаться с диспетчером: +7 934 024-14-14",
                         reply_markup=main_menu_kb())
    await message.answer("Нажмите кнопку ниже, чтобы позвонить:",
                         reply_markup=None)
    await bot.send_message(message.chat.id, "☎️", reply_markup=dispatcher_inline_kb())

# ---- КАЛЬКУЛЯТОР ----
@dp.message(F.text == "🧮 Калькулятор стоимости")
async def calc_start(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(CalcStates.from_city)
    await message.answer("Введите *город отправления*:", parse_mode="Markdown", reply_markup=main_menu_kb())

@dp.message(CalcStates.from_city, F.text)
async def calc_from_city(message: Message, state: FSMContext):
    city = normalize_city(message.text)
    if not city:
        await message.answer("Пожалуйста, введите город отправления текстом.")
        return
    await state.update_data(from_city=city)
    await state.set_state(CalcStates.to_city)
    await message.answer("Введите *город прибытия*:", parse_mode="Markdown")

@dp.message(CalcStates.to_city, F.text)
async def calc_to_city(message: Message, state: FSMContext):
    to_city = normalize_city(message.text)
    data = await state.get_data()
    from_city = data.get("from_city")

    # геокодим обе точки и считаем км
    async with aiohttp.ClientSession() as session:
        a = await geocode_city(session, from_city)
        b = await geocode_city(session, to_city)

    if not a or not b:
        await message.answer(
            "Не удалось определить один из городов. Попробуйте указать полное название (например: "
            "`Кисловодск`, `Ставрополь`, `Минеральные Воды`).",
            parse_mode="Markdown"
        )
        return

    dist = haversine_km(a["lat"], a["lon"], b["lat"], b["lon"])
    # очень грубо, но для межгорода ок; минимум 1 км
    dist = max(dist, 1.0)

    txt = (
        f"🧮 Калькулятор стоимости\n\n"
        f"Из: *{from_city}*\n"
        f"В: *{to_city}*\n\n"
        f"{format_prices_km(dist)}"
    )
    await message.answer(txt, parse_mode="Markdown", reply_markup=main_menu_kb())
    await state.clear()

# ---- СДЕЛАТЬ ЗАКАЗ ----
@dp.message(F.text == "📝 Сделать заказ")
async def order_start(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(OrderStates.from_city)
    await state.update_data(order={})
    await message.answer("Город *отправления*:", parse_mode="Markdown")

@dp.message(OrderStates.from_city, F.text)
async def order_from_city(message: Message, state: FSMContext):
    city = normalize_city(message.text)
    if not city:
        await message.answer("Введите город отправления текстом.")
        return
    data = await state.get_data(); order = data.get("order", {})
    order["from_city"] = city
    await state.update_data(order=order)
    await state.set_state(OrderStates.to_city)
    await message.answer("Город *прибытия*:", parse_mode="Markdown")

@dp.message(OrderStates.to_city, F.text)
async def order_to_city(message: Message, state: FSMContext):
    city = normalize_city(message.text)
    if not city:
        await message.answer("Введите город прибытия текстом.")
        return
    data = await state.get_data(); order = data.get("order", {})
    order["to_city"] = city
    await state.update_data(order=order)
    await state.set_state(OrderStates.date)
    await message.answer("Дата *подачи* (например, 31.10.2025):", parse_mode="Markdown")

@dp.message(OrderStates.date, F.text)
async def order_date(message: Message, state: FSMContext):
    date_text = normalize_city(message.text)
    if not date_text:
        await message.answer("Дата обязательна. Пример: 31.10.2025")
        return
    data = await state.get_data(); order = data.get("order", {})
    order["date"] = date_text
    await state.update_data(order=order)
    await state.set_state(OrderStates.time)
    await message.answer("Время *подачи* (например, 14:30):", parse_mode="Markdown")

@dp.message(OrderStates.time, F.text)
async def order_time(message: Message, state: FSMContext):
    time_text = normalize_city(message.text)
    if not time_text:
        await message.answer("Время обязательно. Пример: 14:30")
        return
    data = await state.get_data(); order = data.get("order", {})
    order["time"] = time_text
    await state.update_data(order=order)
    await state.set_state(OrderStates.phone)
    await message.answer("Номер *телефона* (например, +7 999 123-45-67):", parse_mode="Markdown")

@dp.message(OrderStates.phone, F.text)
async def order_phone(message: Message, state: FSMContext):
    phone = message.text.strip()
    if not PHONE_RE.match(phone):
        await message.answer("Укажите корректный номер телефона (например, +7 999 123-45-67)")
        return
    data = await state.get_data(); order = data.get("order", {})
    order["phone"] = phone
    await state.update_data(order=order)
    await state.set_state(OrderStates.comment)
    await message.answer("Комментарий к заказу (необязательно). Если нет — напишите «-».", parse_mode="Markdown")

@dp.message(OrderStates.comment, F.text)
async def order_comment(message: Message, state: FSMContext):
    comment = message.text.strip()
    if comment == "-":
        comment = ""
    data = await state.get_data(); order = data.get("order", {})
    order["comment"] = comment

    # Подтверждение
    txt = (
        "Проверьте данные заказа:\n\n"
        f"Город отправления: *{order['from_city']}*\n"
        f"Город прибытия: *{order['to_city']}*\n"
        f"Дата: *{order['date']}*\n"
        f"Время подачи: *{order['time']}*\n"
        f"Телефон: *{order['phone']}*\n"
        f"Комментарий: {order['comment'] or '—'}\n\n"
        "Подтвердить?"
    )
    await state.set_state(OrderStates.confirm)
    await message.answer(txt, parse_mode="Markdown", reply_markup=confirm_order_kb())

@dp.callback_query(F.data.in_(["order_confirm", "order_edit", "order_cancel"]))
async def order_finish(cb: CallbackQuery, state: FSMContext):
    action = cb.data
    if action == "order_cancel":
        await state.clear()
        await cb.message.edit_text("Заказ отменён.")
        await cb.answer()
        await bot.send_message(cb.message.chat.id, "Вы в главном меню:", reply_markup=main_menu_kb())
        return

    if action == "order_edit":
        # простой вариант: начать заново
        await state.clear()
        await cb.message.edit_text("Изменим заказ. Заполните ещё раз, пожалуйста.")
        await bot.send_message(cb.message.chat.id, "Город *отправления*:", parse_mode="Markdown")
        await state.set_state(OrderStates.from_city)
        await cb.answer()
        return

    # confirm
    data = await state.get_data()
    order = data.get("order", {})
    await state.clear()

    await cb.message.edit_text("✅ Спасибо, Ваша заявка принята!\nВ ближайшее время с Вами свяжется диспетчер.")
    await bot.send_message(cb.message.chat.id, "Вы в главном меню:", reply_markup=main_menu_kb())
    await cb.answer("Заявка отправлена")

    # уведомление админу
    if ADMIN_CHAT_ID:
        try:
            user = cb.from_user
            header = f"👤 {user.full_name} (id={user.id})"
            if user.username:
                header += f" — @{user.username}"
            txt = (
                f"{header}\n\n"
                "🆕 *Заявка на заказ*\n"
                f"Откуда: *{order.get('from_city','')}*\n"
                f"Куда: *{order.get('to_city','')}*\n"
                f"Дата: *{order.get('date','')}*\n"
                f"Время: *{order.get('time','')}*\n"
                f"Телефон: *{order.get('phone','')}*\n"
                f"Комментарий: {order.get('comment') or '—'}"
            )
            await bot.send_message(ADMIN_CHAT_ID, txt, parse_mode="Markdown")
        except Exception as e:
            logger.warning("Failed to notify admin: %s", e)

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
            await bot.set_my_commands([
                BotCommand(command="start", description="Запуск"),
            ])
            await bot.set_webhook(
                url=url,
                secret_token=WEBHOOK_SECRET if WEBHOOK_SECRET else None,
                drop_pending_updates=True,
            )
            logger.info("Webhook set to %s", url)
            break
        except Exception as e:
            logger.warning("Webhook not set yet (%s). Retrying soon…", e)
            await asyncio.sleep(30)

@app.on_event("startup")
async def on_startup():
    asyncio.create_task(_set_webhook_with_retry())
    logger.info("Startup complete. HTTP server is up; waiting for webhook setup…")

@app.on_event("shutdown")
async def on_shutdown():
    try:
        await bot.delete_webhook(drop_pending_updates=False)
        logger.info("Webhook removed")
    except Exception as e:
        logger.warning("Failed to delete webhook: %s", e)
