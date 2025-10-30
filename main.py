import os
import math
import asyncio
import logging
from typing import Final, Dict, Any

from fastapi import FastAPI, Request, HTTPException
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Update, Message, BotCommand, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

# ================== CONFIG ==================
BOT_TOKEN: Final[str] = os.getenv("BOT_TOKEN", "")
APP_BASE_URL: Final[str] = os.getenv("APP_BASE_URL", "").rstrip("/")
WEBHOOK_SECRET: Final[str] = os.getenv("WEBHOOK_SECRET", "")

# твой админ-ID:
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "7039409310") or 7039409310)

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

# ================== LOGGING ==================
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("tgbot")

# ================== AIOGRAM CORE ==================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ================== FSM STATES ==================
class OrderStates(StatesGroup):
    waiting_from = State()
    waiting_to = State()
    waiting_distance_km = State()
    choose_tariff = State()
    confirm = State()

# ================== TARIFFS (₽/км) ==================
TARIFFS = {
    "econom":  {"title": "Легковой", "per_km": 30},
    "camry":   {"title": "Camry",    "per_km": 40},
    "minivan": {"title": "Минивэн",  "per_km": 50},
}

# ================== KEYBOARDS ==================
def main_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📝 Сделать заказ")],
            [KeyboardButton(text="ℹ️ Тарифы"), KeyboardButton(text="☎️ Поддержка")],
        ],
        resize_keyboard=True,
    )

def share_location_kb(prompt_text: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=prompt_text, request_location=True)],
            [KeyboardButton(text="Пропустить и ввести адрес")],
            [KeyboardButton(text="⬅️ Назад в меню")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )

def back_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="⬅️ Назад в меню")]],
        resize_keyboard=True,
    )

def tariffs_inline_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="Легковой (30 ₽/км)", callback_data="tariff:econom")],
        [InlineKeyboardButton(text="Camry (40 ₽/км)",    callback_data="tariff:camry")],
        [InlineKeyboardButton(text="Минивэн (50 ₽/км)",  callback_data="tariff:minivan")],
        [InlineKeyboardButton(text="⬅️ Отменить",        callback_data="cancel")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)

def confirm_inline_kb() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm:yes"),
            InlineKeyboardButton(text="❌ Отменить",    callback_data="confirm:no"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)

# ================== HELPERS ==================
def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi/2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb/2) ** 2
    return R * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))

def estimate_price(distance_km: float, tariff_key: str) -> Dict[str, Any]:
    per_km = TARIFFS[tariff_key]["per_km"]
    price = int(round(max(distance_km, 0) * per_km))
    return {"distance_km": round(distance_km, 2), "price": price}

def fmt_order_summary(data: dict) -> str:
    parts = []
    parts.append("🚕 *Новый заказ*")
    parts.append(f"Тариф: *{TARIFFS[data['tariff']]['title']}*")
    parts.append(f"Откуда: {data.get('from_text', '—')}")
    parts.append(f"Куда: {data.get('to_text', '—')}")
    if "from_geo" in data and "to_geo" in data:
        fgeo = data["from_geo"]; tgeo = data["to_geo"]
        parts.append(f"Гео откуда: {fgeo['lat']:.5f},{fgeo['lon']:.5f}")
        parts.append(f"Гео куда: {tgeo['lat']:.5f},{tgeo['lon']:.5f}")
    if "calc" in data:
        c = data["calc"]
        parts.append(f"Расстояние: ~{c['distance_km']} км")
        parts.append(f"Цена: *~{c['price']} ₽*")
    return "\n".join(parts)

# ================== HANDLERS ==================
@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Привет! Я помогу оформить заказ такси 🚕\nВыбери действие:",
        reply_markup=main_menu_kb(),
    )

@dp.message(F.text == "ℹ️ Тарифы")
async def on_tariffs(message: Message):
    text = (
        "Тарифы:\n"
        "• Легковой — 30 ₽/км\n"
        "• Camry — 40 ₽/км\n"
        "• Минивэн — 50 ₽/км\n\n"
        "Цена = километры × цена за км."
    )
    await message.answer(text, reply_markup=main_menu_kb())

@dp.message(F.text == "☎️ Поддержка")
async def on_support(message: Message):
    await message.answer("Напишите нам: @your_support (пример)", reply_markup=main_menu_kb())

@dp.message(F.text == "📝 Сделать заказ")
async def start_order(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(OrderStates.waiting_from)
    await state.update_data(order={})
    await message.answer(
        "📍 Откуда подать машину?\n— Поделитесь геопозицией или введите адрес текстом.",
        reply_markup=share_location_kb("Отправить геолокацию «Откуда»"),
    )

@dp.message(OrderStates.waiting_from, F.location)
async def got_from_geo(message: Message, state: FSMContext):
    data = await state.get_data(); order = data.get("order", {})
    order["from_geo"] = {"lat": message.location.latitude, "lon": message.location.longitude}
    order["from_text"] = "Геолокация пользователя"
    await state.update_data(order=order)
    await state.set_state(OrderStates.waiting_to)
    await message.answer(
        "📍 Куда едем? Геопозиция или адрес.",
        reply_markup=share_location_kb("Отправить геолокацию «Куда»"),
    )

@dp.message(OrderStates.waiting_from, F.text & (F.text.lower() == "пропустить и ввести адрес"))
async def from_prompt_address(message: Message):
    await message.answer("Введите адрес отправления текстом:", reply_markup=back_menu_kb())

@dp.message(OrderStates.waiting_from, F.text)
async def got_from_text(message: Message, state: FSMContext):
    if message.text == "⬅️ Назад в меню":
        await cmd_start(message, state); return
    data = await state.get_data(); order = data.get("order", {})
    order["from_text"] = message.text.strip()
    await state.update_data(order=order)
    await state.set_state(OrderStates.waiting_to)
    await message.answer(
        "📍 Куда едем? Геопозиция или адрес.",
        reply_markup=share_location_kb("Отправить геолокацию «Куда»"),
    )

@dp.message(OrderStates.waiting_to, F.location)
async def got_to_geo(message: Message, state: FSMContext):
    data = await state.get_data(); order = data.get("order", {})
    order["to_geo"] = {"lat": message.location.latitude, "lon": message.location.longitude}
    order["to_text"] = "Геолокация пользователя"
    await state.update_data(order=order)

    if "from_geo" in order and "to_geo" in order:
        dist = haversine_km(order["from_geo"]["lat"], order["from_geo"]["lon"],
                            order["to_geo"]["lat"], order["to_geo"]["lon"])
        order["distance_km"] = max(dist, 0.5)
        await state.update_data(order=order)
        await state.set_state(OrderStates.choose_tariff)
        await message.answer("Выберите тариф:", reply_markup=tariffs_inline_kb())
        return

    await state.set_state(OrderStates.waiting_distance_km)
    await message.answer(
        "Если обе геоточки не отправляли — укажите *примерное расстояние* в км (числом).",
        reply_markup=back_menu_kb(),
    )

@dp.message(OrderStates.waiting_to, F.text & (F.text.lower() == "пропустить и ввести адрес"))
async def to_prompt_address(message: Message):
    await message.answer("Введите адрес назначения текстом:", reply_markup=back_menu_kb())

@dp.message(OrderStates.waiting_to, F.text)
async def got_to_text(message: Message, state: FSMContext):
    if message.text == "⬅️ Назад в меню":
        await cmd_start(message, state); return
    data = await state.get_data(); order = data.get("order", {})
    order["to_text"] = message.text.strip()
    await state.update_data(order=order)
    await state.set_state(OrderStates.waiting_distance_km)
    await message.answer(
        "Укажите *примерное расстояние* в км (числом), например `7.5`.",
        reply_markup=back_menu_kb(),
    )

@dp.message(OrderStates.waiting_distance_km, F.text)
async def got_distance_text(message: Message, state: FSMContext):
    if message.text == "⬅️ Назад в меню":
        await cmd_start(message, state); return
    try:
        km = float(message.text.replace(",", "."))
        if km <= 0: raise ValueError
    except Exception:
        await message.answer("Пожалуйста, отправьте расстояние *числом*, например: `6.2`")
        return
    data = await state.get_data(); order = data.get("order", {})
    order["distance_km"] = km
    await state.update_data(order=order)
    await state.set_state(OrderStates.choose_tariff)
    await message.answer("Выберите тариф:", reply_markup=tariffs_inline_kb())

@dp.callback_query(F.data.startswith("tariff:"))
async def choose_tariff(cb: CallbackQuery, state: FSMContext):
    key = cb.data.split(":", 1)[1]
    if key not in TARIFFS:
        await cb.answer("Неизвестный тариф", show_alert=True); return
    data = await state.get_data(); order = data.get("order", {})
    order["tariff"] = key

    dist = order.get("distance_km", 0.0)
    if dist <= 0:
        await cb.answer("Не удалось определить расстояние", show_alert=True); return
    calc = estimate_price(dist, key)
    order["calc"] = calc
    await state.update_data(order=order)

    text = (
        f"🚕 *Предзаказ*\n"
        f"Тариф: *{TARIFFS[key]['title']}*\n"
        f"Откуда: {order.get('from_text', '—')}\n"
        f"Куда: {order.get('to_text', '—')}\n"
        f"Расстояние: ~{calc['distance_km']} км\n"
        f"К оплате: *~{calc['price']} ₽*\n\n"
        f"Подтвердить заказ?"
    )
    await cb.message.edit_text(text, parse_mode="Markdown")
    await cb.message.edit_reply_markup(reply_markup=confirm_inline_kb())
    await state.set_state(OrderStates.confirm)
    await cb.answer()

@dp.callback_query(F.data == "cancel")
async def cancel_cb(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text("Отменено.")
    await cb.message.edit_reply_markup()
    await cb.message.answer("Вы в меню:", reply_markup=main_menu_kb())
    await cb.answer()

@dp.callback_query(F.data.startswith("confirm:"))
async def confirm_order(cb: CallbackQuery, state: FSMContext):
    decision = cb.data.split(":", 1)[1]
    if decision == "no":
        await state.clear()
        await cb.message.edit_text("Заказ отменён.")
        await cb.message.edit_reply_markup()
        await cb.message.answer("Вы в меню:", reply_markup=main_menu_kb())
        await cb.answer(); return

    data = await state.get_data(); order = data.get("order", {})
    order_text = fmt_order_summary(order)

    await cb.message.edit_text("✅ Заказ подтверждён! Спасибо 🙌")
    await cb.message.edit_reply_markup()
    await cb.message.answer("Водитель скоро свяжется с вами. Вы в меню:", reply_markup=main_menu_kb())
    await state.clear()

    if ADMIN_CHAT_ID:
        try:
            user = cb.from_user
            header = f"👤 Пользователь: {user.full_name} (id={user.id})"
            if user.username:
                header += f"\nUsername: @{user.username}"
            await bot.send_message(ADMIN_CHAT_ID, header + "\n\n" + order_text, parse_mode="Markdown")
        except Exception as e:
            logger.warning("Failed to notify admin: %s", e)

    await cb.answer("Заказ отправлен!")

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
                BotCommand(command="help", description="Помощь"),
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
