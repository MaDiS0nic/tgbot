# main.py
import os
import math
import asyncio
import logging
import re
import calendar
from datetime import datetime, date, timedelta
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
# Базовые тарифы (для расчёта по километражу, если нет фиксированного города)
TARIFFS = {
    "econom":  {"title": "Легковой",          "per_km": 30},
    "camry":   {"title": "Camry",             "per_km": 40},
    "minivan": {"title": "Минивэн (5-6 чел)", "per_km": 50},
}

# ================== ФИКСИРОВАННЫЕ ГОРОДА ==================
# Вводите здесь любые обновления цен. Ключи — каноническое название города.
FIXED: Dict[str, Dict[str, int]] = {
    # Ближние
    "Железноводск": {"econom": 800, "camry": 1500, "minivan": 2000},
    "Пятигорск": {"econom": 1200, "camry": 1500, "minivan": 1900},
    "Ессентуки": {"econom": 1300, "camry": 2000, "minivan": 2500},
    "Георгиевск": {"econom": 1300, "camry": 2000, "minivan": 2500},
    "Кисловодск": {"econom": 1800, "camry": 2500, "minivan": 3000},

    # Обновлённые направления (горный кластер)
    "Архыз": {"econom": 6500, "camry": 8000, "minivan": 10000},
    "Архыз Романтик": {"econom": 7000, "camry": 9000, "minivan": 11000},
    "Домбай": {"econom": 6500, "camry": 8000, "minivan": 10000},
    "Азау": {"econom": 5500, "camry": 7500, "minivan": 9000},
    "Терскол": {"econom": 5500, "camry": 7500, "minivan": 9000},
    "Эльбрус": {"econom": 5500, "camry": 7500, "minivan": 9000},
    "Теберда": {"econom": 5500, "camry": 7500, "minivan": 9000},
    "Нейтрино": {"econom": 5000, "camry": 7500, "minivan": 9000},
    "Тегенекли": {"econom": 5000, "camry": 7500, "minivan": 9000},
    "Байдаево": {"econom": 5000, "camry": 7500, "minivan": 9000},
    "Чегет": {"econom": 5500, "camry": 7500, "minivan": 9000},

    # Примеры дальних (оставил часть списка; при необходимости дополняйте)
    "Ставрополь": {"econom": 5400, "camry": 7200, "minivan": 9000},
    "Черкесск": {"econom": 3000, "camry": 4000, "minivan": 5000},
    "Нальчик": {"econom": 3300, "camry": 4400, "minivan": 5500},
    "Владикавказ": {"econom": 6600, "camry": 8800, "minivan": 11000},
    "Назрань": {"econom": 6600, "camry": 8800, "minivan": 11000},
    "Магас": {"econom": 6600, "camry": 8800, "minivan": 11000},
    "Светлоград": {"econom": 5100, "camry": 6800, "minivan": 8500},
    "Краснодар": {"econom": 12000, "camry": 16000, "minivan": 20000},
    "Сочи": {"econom": 16500, "camry": 22000, "minivan": 27500},
    "Адлер": {"econom": 17400, "camry": 23200, "minivan": 29000},
    "Новороссийск": {"econom": 17000, "camry": 22600, "minivan": 28200},
}

# ================== СИНОНИМЫ ГОРОДОВ ==================
# Ключ — то, как пользователь пишет; значение — каноническое имя из FIXED
CITY_SYNONYMS: Dict[str, str] = {
    "мвр": "Аэропорт MRV",
    "аэропорт мрв": "Аэропорт MRV",
    "минводы аэропорт": "Аэропорт MRV",
    "минеральные воды аэропорт": "Аэропорт MRV",
    "минеральные воды (аэропорт)": "Аэропорт MRV",
    "минеральные воды": "Железноводск",  # частая путаница, можно сменить при желании
    "минводы": "Железноводск",
    # Горный кластер
    "эльбрус азау": "Азау",
    "глк эльбрус": "Азау",
    "чегет поляна": "Чегет",
    # и т.п. — можно расширять
}

# Быстрые подсказки городов (на клавиатуре)
QUICK_CITIES = [
    "Аэропорт MRV", "Железноводск", "Пятигорск",
    "Ессентуки", "Кисловодск", "Архыз", "Домбай",
]

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
            url="https://t.me/zhelektown"   # обновлённый юзернейм
        )
    ], [
        InlineKeyboardButton(
            text="📱 Позвонить диспетчеру",
            url="tel:+79340241414"
        )
    ]])

def quick_cities_kb() -> ReplyKeyboardMarkup:
    rows = []
    row = []
    for name in QUICK_CITIES:
        row.append(KeyboardButton(text=name))
        if len(row) == 2:
            rows.append(row); row = []
    if row: rows.append(row)
    rows.append([KeyboardButton(text="⬅️ В меню")])
    return ReplyKeyboardMarkup(resize_keyboard=True, keyboard=rows)

def confirm_order_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Подтвердить", callback_data="order_confirm"),
        InlineKeyboardButton(text="✏️ Изменить", callback_data="order_edit"),
        InlineKeyboardButton(text="❌ Отменить", callback_data="order_cancel"),
    ]])

def yes_no_kb(prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Да", callback_data=f"{prefix}:yes"),
        InlineKeyboardButton(text="Нет", callback_data=f"{prefix}:no"),
    ]])

def people_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=str(i), callback_data=f"ppl:{i}") for i in (1,2,3)],
        [InlineKeyboardButton(text=str(i), callback_data=f"ppl:{i}") for i in (4,5,6)],
        [InlineKeyboardButton(text="7 и более", callback_data="ppl:7+")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)

# ================== СОСТОЯНИЯ ==================
class CalcStates(StatesGroup):
    from_city = State()
    to_city = State()

class OrderStates(StatesGroup):
    from_city = State()
    to_city = State()
    date = State()
    time_hour = State()
    time_min = State()
    people = State()
    ask_comment = State()
    comment = State()
    confirm = State()

# ================== ХЕЛПЕРЫ ==================
def norm(s: str) -> str:
    return " ".join((s or "").strip().split()).lower()

def canon_city(name: str) -> str:
    key = norm(name)
    if key in CITY_SYNONYMS:
        return CITY_SYNONYMS[key]
    # точное совпадение из FIXED
    for city in list(FIXED.keys()) + QUICK_CITIES:
        if norm(city) == key:
            return city
    # иначе вернуть исходник с нормализацией регистра
    return name.strip()

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
    headers = {"User-Agent": "TransferAir-KMV-Bot/1.1 (admin@example.com)"}
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

async def estimate_prices(from_city: str, to_city: str) -> Optional[Dict[str, int]]:
    """
    Возвращает словарь с ценами по тарифам (econom, camry, minivan).
    Если есть фикс — используем его; иначе считаем по расстоянию.
    """
    to_c = canon_city(to_city)
    if to_c in FIXED:
        return FIXED[to_c].copy()

    # расчёт по километражу
    async with aiohttp.ClientSession() as session:
        a = await geocode_city(session, from_city)
        b = await geocode_city(session, to_city)
    if not a or not b:
        return None
    dist = max(1.0, round(haversine_km(a["lat"], a["lon"], b["lat"], b["lon"]), 1))
    return {
        "econom": int(round(dist * TARIFFS["econom"]["per_km"])),
        "camry": int(round(dist * TARIFFS["camry"]["per_km"])),
        "minivan": int(round(dist * TARIFFS["minivan"]["per_km"])),
    }

def prices_text(prices: Dict[str, int]) -> str:
    return (
        "Стоимость предварительная, окончательная цена оговаривается диспетчером!\n\n"
        f"💰 Стоимость:\n"
        f"• {TARIFFS['econom']['title']} — ~{prices['econom']} ₽\n"
        f"• {TARIFFS['camry']['title']} — ~{prices['camry']} ₽\n"
        f"• {TARIFFS['minivan']['title']} — ~{prices['minivan']} ₽"
    )

PHONE_RE = re.compile(r"^\+?\d[\d\-\s]{8,}$")

# ================== КАЛЕНДАРЬ (Inline) ==================
def calendar_kb(target: date) -> InlineKeyboardMarkup:
    y, m = target.year, target.month
    month_name = calendar.month_name[m]
    cal = calendar.monthcalendar(y, m)
    buttons = [[InlineKeyboardButton(text=f"📅 {month_name} {y}", callback_data="noop")]]
    week_days = ["Пн","Вт","Ср","Чт","Пт","Сб","Вс"]
    buttons.append([InlineKeyboardButton(text=d, callback_data="noop") for d in week_days])
    for week in cal:
        row = []
        for d in week:
            if d == 0:
                row.append(InlineKeyboardButton(text=" ", callback_data="noop"))
            else:
                day_date = date(y, m, d)
                if day_date < date.today():
                    row.append(InlineKeyboardButton(text="·", callback_data="noop"))
                else:
                    row.append(InlineKeyboardButton(text=str(d), callback_data=f"cal:{y}-{m:02d}-{d:02d}"))
        buttons.append(row)
    # навигация
    prev_month = (target.replace(day=1) - timedelta(days=1)).replace(day=1)
    next_month = (target.replace(day=28) + timedelta(days=4)).replace(day=1)
    buttons.append([
        InlineKeyboardButton(text="«", callback_data=f"calnav:{prev_month.year}-{prev_month.month:02d}"),
        InlineKeyboardButton(text="Сегодня", callback_data=f"cal:{date.today().isoformat()}"),
        InlineKeyboardButton(text="»", callback_data=f"calnav:{next_month.year}-{next_month.month:02d}")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def time_hour_kb() -> InlineKeyboardMarkup:
    rows = []
    for i in range(0, 24, 6):
        rows.append([InlineKeyboardButton(text=f"{h:02d}", callback_data=f"th:{h:02d}") for h in range(i, i+6)])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def time_min_kb(hour: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=f"{hour}:{m:02d}", callback_data=f"tm:{hour}:{m:02d}")
        for m in (0,15,30,45)
    ]])

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

# ---- ИНФОРМАЦИЯ ----
@dp.message(F.text == "ℹ️ Информация")
async def on_info(message: Message):
    # Телефон как кликабельная ссылка tel:+7..., как вы просили
    html = (
        "<b>TransferAir</b> — междугороднее такси (трансфер) из Минеральных Вод.\n\n"
        "Можете заказать трансфер через бота, "
        "позвонить нам <a href=\"tel:+79340241414\">+7 934 024-14-14</a>, "
        "или посетить наш сайт: <a href=\"https://transferkmw.ru\">transferkmw.ru</a>"
    )
    await message.answer(html, parse_mode="HTML", disable_web_page_preview=True)

# ---- ДИСПЕТЧЕР ----
@dp.message(F.text == "☎️ Диспетчер")
async def on_dispatcher(message: Message):
    text = (
        "☎️ <b>Связаться с диспетчером</b>\n\n"
        "Нажмите кнопку ниже, чтобы написать диспетчеру в Telegram\n"
        "или позвонить по телефону."
    )
    await message.answer(text, parse_mode="HTML", reply_markup=dispatcher_inline_kb())

@dp.callback_query(F.data == "dispatcher_phone")
async def dispatcher_phone_cb(cb: CallbackQuery):
    await cb.message.answer(
        "📱 Телефон диспетчера:\n"
        "<a href=\"tel:+79340241414\">+7 934 024-14-14</a>\n\n"
        "Нажмите, чтобы позвонить.",
        parse_mode="HTML",
    )
    await cb.answer("Номер отправлен")

# ---- КАЛЬКУЛЯТОР ----
class CalcStates(StatesGroup):
    from_city = State()
    to_city = State()

@dp.message(F.text == "🧮 Калькулятор стоимости")
async def calc_start(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(CalcStates.from_city)
    await message.answer("Введите <b>город отправления</b> или выберите из списка:", parse_mode="HTML",
                         reply_markup=quick_cities_kb())

@dp.message(CalcStates.from_city, F.text)
async def calc_from_city(message: Message, state: FSMContext):
    city = canon_city(message.text)
    if message.text == "⬅️ В меню":
        await state.clear()
        await message.answer("Вы в главном меню:", reply_markup=main_menu_kb()); return
    await state.update_data(from_city=city)
    await state.set_state(CalcStates.to_city)
    await message.answer("Введите <b>город прибытия</b> или выберите из списка:", parse_mode="HTML",
                         reply_markup=quick_cities_kb())

@dp.message(CalcStates.to_city, F.text)
async def calc_to_city(message: Message, state: FSMContext):
    if message.text == "⬅️ В меню":
        await state.clear()
        await message.answer("Вы в главном меню:", reply_markup=main_menu_kb()); return
    to_city = canon_city(message.text)
    data = await state.get_data()
    from_city = data.get("from_city")

    prices = await estimate_prices(from_city, to_city)
    if not prices:
        await message.answer(
            "❌ Не удалось определить города. Попробуйте ещё раз.\n"
            "Пример: <code>Кисловодск</code>, <code>Аэропорт MRV</code>.",
            parse_mode="HTML",
        )
        return

    txt = (
        f"🧮 <b>Калькулятор стоимости</b>\n\n"
        f"Из: <b>{from_city}</b>\n"
        f"В: <b>{to_city}</b>\n\n"
        f"{prices_text(prices)}"
    )
    await message.answer(txt, parse_mode="HTML", reply_markup=main_menu_kb())
    await state.clear()

# ---- ОФОРМЛЕНИЕ ЗАКАЗА ----
class OrderForm(StatesGroup):
    from_city = State()
    to_city = State()
    date = State()
    time_hour = State()
    time_min = State()
    people = State()
    ask_comment = State()
    comment = State()
    confirm = State()

@dp.message(F.text == "📝 Сделать заказ")
async def order_start(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(OrderForm.from_city)
    await state.update_data(order={})
    await message.answer("Введите <b>город отправления</b> или выберите:", parse_mode="HTML",
                         reply_markup=quick_cities_kb())

@dp.message(OrderForm.from_city, F.text)
async def order_from_city(message: Message, state: FSMContext):
    if message.text == "⬅️ В меню":
        await state.clear(); await message.answer("Вы в главном меню:", reply_markup=main_menu_kb()); return
    order = {"from_city": canon_city(message.text)}
    await state.update_data(order=order)
    await state.set_state(OrderForm.to_city)
    await message.answer("Введите <b>город прибытия</b> или выберите:", parse_mode="HTML",
                         reply_markup=quick_cities_kb())

@dp.message(OrderForm.to_city, F.text)
async def order_to_city(message: Message, state: FSMContext):
    if message.text == "⬅️ В меню":
        await state.clear(); await message.answer("Вы в главном меню:", reply_markup=main_menu_kb()); return
    data = await state.get_data(); order = data.get("order", {})
    order["to_city"] = canon_city(message.text)
    await state.update_data(order=order)
    await state.set_state(OrderForm.date)
    await message.answer("Выберите <b>дату подачи</b>:", parse_mode="HTML",
                         reply_markup=calendar_kb(date.today()))

@dp.callback_query(F.data.startswith("calnav:") | F.data.startswith("cal:"))
async def calendar_callbacks(cb: CallbackQuery, state: FSMContext):
    if cb.data.startswith("calnav:"):
        y, m = cb.data.split(":")[1].split("-")
        kb = calendar_kb(date(int(y), int(m), 1))
        await cb.message.edit_reply_markup(kb)
        await cb.answer(); return
    if cb.data.startswith("cal:"):
        _, iso = cb.data.split(":")
        await state.update_data(order={(await state.get_data()).get("order", {})} or (await state.get_data()).get("order", {}))
        data = await state.get_data(); order = data.get("order", {})
        order["date"] = iso
        await state.update_data(order=order)
        await state.set_state(OrderForm.time_hour)
        await cb.message.answer("Выберите <b>время подачи</b> — сначала <b>час</b>:", parse_mode="HTML",
                                reply_markup=time_hour_kb())
        await cb.answer()

@dp.callback_query(F.data.startswith("th:"))
async def time_pick_hour(cb: CallbackQuery, state: FSMContext):
    hour = cb.data.split(":")[1]
    await state.set_state(OrderForm.time_min)
    await cb.message.answer("Теперь выберите <b>минуты</b>:", parse_mode="HTML",
                            reply_markup=time_min_kb(hour))
    await cb.answer()

@dp.callback_query(F.data.startswith("tm:"))
async def time_pick_min(cb: CallbackQuery, state: FSMContext):
    _, hour, minute = cb.data.split(":")
    data = await state.get_data(); order = data.get("order", {})
    order["time"] = f"{hour}:{minute}"
    await state.update_data(order=order)
    await state.set_state(OrderForm.people)
    await cb.message.answer("Укажите <b>количество человек</b>:", parse_mode="HTML",
                            reply_markup=people_kb())
    await cb.answer()

@dp.callback_query(F.data.startswith("ppl:"))
async def pick_people(cb: CallbackQuery, state: FSMContext):
    people = cb.data.split(":")[1]
    data = await state.get_data(); order = data.get("order", {})
    order["people"] = people
    await state.update_data(order=order)
    await state.set_state(OrderForm.ask_comment)
    await cb.message.answer("Хотите оставить комментарий к заказу?", reply_markup=yes_no_kb("cmt"))
    await cb.answer()

@dp.callback_query(F.data.startswith("cmt:"))
async def ask_comment_cb(cb: CallbackQuery, state: FSMContext):
    ans = cb.data.split(":")[1]
    if ans == "yes":
        await state.set_state(OrderForm.comment)
        await cb.message.answer("Введите комментарий:")
    else:
        await proceed_to_confirm(cb.message, state)
    await cb.answer()

@dp.message(OrderForm.comment, F.text)
async def order_comment(message: Message, state: FSMContext):
    data = await state.get_data(); order = data.get("order", {})
    comment = message.text.strip()
    order["comment"] = "" if comment == "-" else comment
    await state.update_data(order=order)
    await proceed_to_confirm(message, state)

async def proceed_to_confirm(message_or_cbmsg, state: FSMContext):
    data = await state.get_data(); order = data.get("order", {})
    # Оценим стоимость
    prices = await estimate_prices(order["from_city"], order["to_city"])
    price_txt = prices_text(prices) if prices else "Предварительную стоимость сейчас посчитать не удалось."

    txt = (
        f"{price_txt}\n\n"
        f"Проверьте данные заказа:\n\n"
        f"Откуда: <b>{order['from_city']}</b>\n"
        f"Куда: <b>{order['to_city']}</b>\n"
        f"Дата: <b>{order['date']}</b>\n"
        f"Время: <b>{order['time']}</b>\n"
        f"Пассажиров: <b>{order.get('people','—')}</b>\n"
        f"Комментарий: {order.get('comment') or '—'}\n\n"
        "Подтвердить?"
    )
    await state.set_state(OrderForm.confirm)
    await message_or_cbmsg.answer(txt, parse_mode="HTML", reply_markup=confirm_order_kb())

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
        data = await state.get_data(); order = data.get("order", {})
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
                f"🆕 <b>Заявка на заказ</b>\n\n"
                f"От: <b>{order['from_city']}</b> → <b>{order['to_city']}</b>\n"
                f"Дата: <b>{order['date']}</b>, Время: <b>{order['time']}</b>\n"
                f"Пассажиров: <b>{order.get('people','—')}</b>\n"
                f"Комментарий: {order.get('comment') or '—'}\n\n"
                f"👤 {user.full_name} (id={user.id})"
            )
            await bot.send_message(ADMIN_CHAT_ID, txt, parse_mode="HTML")
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
