import asyncio
import hashlib
import json
import os
from typing import Dict, Optional

import aiohttp
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from aiogram import F, Router
from aiogram.client.bot import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    FSInputFile,
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.dispatcher.dispatcher import Dispatcher

# ========= НАСТРОЙКИ =========

# Токен — по твоей просьбе жёстко в коде
TOKEN = "8402271440:AAH_76pBTaHSD-q7T8I4TG1ZP1qqrSyTkA0"

# Контакты диспетчера
DISPATCHER_TG = "zhelektown"  # ник без @ (проверь и поправь при необходимости)
DISPATCHER_PHONE = "+79340241414"

# Базовый URL для вебхука (через переменную окружения)
WEBHOOK_BASE = os.getenv("WEBHOOK_BASE", "").strip()  # например: https://bot.example.com
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "").strip()  # опционально, иначе сгенерим

# Резервный расчёт по километражу (если город не в списке фикс-тарифов)
# Тарифы РУБ/КМ — используются ТОЛЬКО для вычисления, в сообщение не выводятся.
RATES_PER_KM = {
    "легковой": 25,
    "камри": 35,
    "минивэн": 45,
}

# ========= ФИКСИРОВАННЫЕ ТАРИФЫ (ГОРОДА) =========
# Ключи — нормализованные названия городов (строчные, дефисы/пробелы как обычно).
FIXED_PRICES: Dict[str, Dict[str, int]] = {
    # КМВ базовые
    "железноводск": {"легковой": 800, "камри": 1500, "минивэн": 2000},
    "пятигорск": {"легковой": 1200, "камри": 1500, "минивэн": 1900},
    "ессентуки": {"легковой": 1300, "камри": 2000, "минивэн": 2500},
    "кисловодск": {"легковой": 1800, "камри": 2500, "минивэн": 3000},

    "архыз": {"легковой": 6500, "камри": 8000, "минивэн": 10000},
    "архыз романтик": {"легковой": 7000, "камри": 9000, "минивэн": 11000},
    "домбай": {"легковой": 6500, "камри": 8000, "минивэн": 10000},
    "азау": {"легковой": 5500, "камри": 7500, "минивэн": 9000},
    "терскол": {"легковой": 5500, "камри": 7500, "минивэн": 9000},
    "эльбрус": {"легковой": 5500, "камри": 7500, "минивэн": 8500},
    "теберда": {"легковой": 5500, "камри": 7500, "минивэн": 8500},
    "нейтрино": {"легковой": 5000, "камри": 7500, "минивэн": 8500},
    "тегенекли": {"легковой": 5000, "камри": 7500, "минивэн": 8500},
    "байдаево": {"легковой": 5000, "камри": 7500, "минивэн": 8500},
    "чегет": {"легковой": 5500, "камри": 7500, "минивэн": 9000},

    "ставрополь": {"легковой": 5400, "камри": 7200, "минивэн": 9000},
    "черкесск": {"легковой": 3000, "камри": 4000, "минивэн": 5000},
    "нальчик": {"легковой": 3300, "камри": 4400, "минивэн": 5500},
    "владикавказ": {"легковой": 6600, "камри": 8800, "минивэн": 11000},
    "грозный": {"легковой": 9300, "камри": 12400, "минивэн": 15500},
    "назрань": {"легковой": 6600, "камри": 8800, "минивэн": 11000},
    "адлер": {"легковой": 17400, "камри": 23200, "минивэн": 29000},

    "алагир": {"легковой": 6000, "камри": 8000, "минивэн": 10000},
    "александровское село": {"легковой": 2100, "камри": 2800, "минивэн": 3500},
    "ардон": {"легковой": 5500, "камри": 7400, "минивэн": 9200},
    "арзгир": {"легковой": 6000, "камри": 8000, "минивэн": 10000},
    "армавир": {"легковой": 5700, "камри": 7600, "минивэн": 9500},
    "астрахань": {"легковой": 18900, "камри": 25000, "минивэн": 31500},
    "аушигер": {"легковой": 4000, "камри": 5400, "минивэн": 6700},
    "ачикулак село": {"легковой": 5500, "камри": 7400, "минивэн": 9200},
    "баксан": {"легковой": 2500, "камри": 3300, "минивэн": 4000},
    "батуми": {"легковой": 30000, "камри": 40000, "минивэн": 50000},
    "беломечетская станица": {"легковой": 3600, "камри": 4800, "минивэн": 6000},
    "беслан": {"легковой": 6000, "камри": 8000, "минивэн": 10000},
    "благодарный": {"легковой": 4000, "камри": 5400, "минивэн": 6700},
    "будёновск": {"легковой": 4000, "камри": 5400, "минивэн": 6700},
    "витязево поселок": {"легковой": 18000, "камри": 24000, "минивэн": 30000},
    "волгоград": {"легковой": 18000, "камри": 24000, "минивэн": 30000},
    "галюгаевская станица": {"легковой": 6000, "камри": 8000, "минивэн": 10000},
    "геленджик": {"легковой": 18000, "камри": 24000, "минивэн": 30000},
    "георгиевск": {"легковой": 1300, "камри": 2000, "минивэн": 2500},
    "горнозаводское село": {"легковой": 3000, "камри": 4000, "минивэн": 5000},
    "грушевское село": {"легковой": 3300, "камри": 4400, "минивэн": 5500},
    "гудаури": {"легковой": 15000, "камри": 20000, "минивэн": 25000},
    "дербент": {"легковой": 18000, "камри": 24000, "минивэн": 30000},
    "джубга": {"легковой": 14000, "камри": 19000, "минивэн": 23000},
    "екатеринбург": {"легковой": 72000, "камри": 96000, "минивэн": 120000},
    "елизаветинское село": {"легковой": 3700, "камри": 5000, "минивэн": 6200},
    "зеленокумск": {"легковой": 2400, "камри": 3200, "минивэн": 4000},
    "зеленчукская станица": {"легковой": 5000, "камри": 7500, "минивэн": 8500},
    "зольская станица": {"легковой": 1500, "камри": 2000, "минивэн": 2500},
    "иконхалк": {"легковой": 3400, "камри": 4500, "минивэн": 5600},
    "кабардинка": {"легковой": 16500, "камри": 22000, "минивэн": 27500},
    "камата село (осетия)": {"легковой": 6000, "камри": 8000, "минивэн": 10000},
    "карчаевск": {"легковой": 4600, "камри": 6100, "минивэн": 7700},
    "каратюбе": {"легковой": 5400, "камри": 7200, "минивэн": 9000},
    "каспийск": {"легковой": 14500, "камри": 19000, "минивэн": 24000},
    "кизляр": {"легковой": 11400, "камри": 15200, "минивэн": 19000},
    "кочубеевское село": {"легковой": 3700, "камри": 5000, "минивэн": 6200},
    "краснодар": {"легковой": 12000, "камри": 16000, "минивэн": 20000},
    "курская": {"легковой": 4300, "камри": 5700, "минивэн": 7100},
    "лабинск": {"легковой": 7000, "камри": 9300, "минивэн": 11600},
    "лазаревское": {"легковой": 14500, "камри": 19200, "минивэн": 24000},
    "левокумское село": {"легковой": 5200, "камри": 7000, "минивэн": 8700},
    "магас": {"легковой": 6600, "камри": 8800, "минивэн": 11000},
    "майкоп": {"легковой": 8800, "камри": 11700, "минивэн": 14500},
    "майский кбр": {"легковой": 4300, "камри": 5700, "минивэн": 7000},
    "марьинская станица": {"легковой": 2100, "камри": 2800, "минивэн": 3500},
    "махачкала": {"легковой": 13900, "камри": 18500, "минивэн": 23100},
    "моздок": {"легковой": 4900, "камри": 6500, "минивэн": 8100},
    "нарткала": {"легковой": 3700, "камри": 5000, "минивэн": 6200},
    "невинномысск": {"легковой": 3000, "камри": 4000, "минивэн": 5000},
    "незлобная станица": {"легковой": 1500, "камри": 2000, "минивэн": 2500},
    "нефтекумск": {"легковой": 6400, "камри": 8500, "минивэн": 10700},
    "новоалександровск": {"легковой": 7400, "камри": 9800, "минивэн": 12200},
    "новопавловск": {"легковой": 2500, "камри": 3400, "минивэн": 4200},
    "новороссийск": {"легковой": 17000, "камри": 22600, "минивэн": 28200},
    "новоселицкое село": {"легковой": 3000, "камри": 4000, "минивэн": 5000},
    "прохладный": {"легковой": 3600, "камри": 4800, "минивэн": 6000},
    "псебай": {"легковой": 9000, "камри": 12000, "минивэн": 15000},
    "псыгансу село": {"легковой": 3900, "камри": 5200, "минивэн": 6500},
    "ростов-на-дону": {"легковой": 16000, "камри": 21000, "минивэн": 26000},
    "светлоград": {"легковой": 5100, "камри": 6800, "минивэн": 8500},
    "сочи": {"легковой": 16500, "камри": 22000, "минивэн": 27500},
    "степанцминда": {"легковой": 13000, "камри": 17000, "минивэн": 22000},
    "степное село": {"легковой": 4400, "камри": 5800, "минивэн": 7300},
    "сунжа": {"легковой": 7500, "камри": 10000, "минивэн": 12500},
    "тбилиси": {"легковой": 20000, "камри": 25000, "минивэн": 30000},
    "терек": {"легковой": 4700, "камри": 6200, "минивэн": 7800},
    "туапсе": {"легковой": 13000, "камри": 17300, "минивэн": 21700},
    "урус-мартан": {"легковой": 9000, "камри": 12000, "минивэн": 15000},
    "учкулан аул": {"легковой": 6000, "камри": 8000, "минивэн": 10000},
    "хадыженск": {"легковой": 10700, "камри": 14200, "минивэн": 17800},
    "хасавюрт": {"легковой": 11400, "камри": 15200, "минивэн": 19000},
    "хурзук аул": {"легковой": 6500, "камри": 9000, "минивэн": 11500},
    "цей": {"легковой": 7300, "камри": 9700, "минивэн": 12000},
    "элиста": {"легковой": 9400, "камри": 12500, "минивэн": 15600},
}

# ========= УТИЛИТЫ =========

def norm_city(s: str) -> str:
    return " ".join(s.strip().lower().replace("ё", "е").replace("  ", " ").split())

def get_fixed_price(city: str, car_key: str) -> Optional[int]:
    city_key = norm_city(city)
    data = FIXED_PRICES.get(city_key)
    if not data:
        return None
    return data.get(car_key)

async def geocode_nominatim(session: aiohttp.ClientSession, query: str) -> Optional[tuple[float, float]]:
    """
    Простой геокодер на Nominatim (публичный).
    Возвращает (lat, lon) или None.
    """
    url = "https://nominatim.openstreetmap.org/search"
    params = {"format": "json", "q": query, "limit": 1, "accept-language": "ru"}
    headers = {"User-Agent": "kmv-transfer-bot/1.0"}
    try:
        async with session.get(url, params=params, headers=headers, timeout=15) as r:
            if r.status != 200:
                return None
            payload = await r.json()
            if not payload:
                return None
            lat = float(payload[0]["lat"])
            lon = float(payload[0]["lon"])
            return (lat, lon)
    except Exception:
        return None

async def route_distance_km(session: aiohttp.ClientSession, start: str, finish: str) -> Optional[int]:
    """
    Считает расстояние по дороге с помощью OSRM (публичный сервер),
    если удалось геокодировать обе точки.
    """
    p1 = await geocode_nominatim(session, start)
    p2 = await geocode_nominatim(session, finish)
    if not p1 or not p2:
        return None
    (lat1, lon1), (lat2, lon2) = p1, p2
    # OSRM ждёт lon,lat
    url = f"https://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}"
    params = {"overview": "false"}
    try:
        async with session.get(url, params=params, timeout=20) as r:
            if r.status != 200:
                return None
            data = await r.json()
            routes = data.get("routes") or []
            if not routes:
                return None
            dist_m = routes[0].get("distance", 0)
            km = int(round(dist_m / 1000))
            return km if km > 0 else None
    except Exception:
        return None

def compute_by_rates(km: int, car_key: str) -> int:
    rate = RATES_PER_KM.get(car_key, 30)
    return int(km * rate)

def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🧮 Рассчитать стоимость", callback_data="calc")],
            [InlineKeyboardButton(text="💬 Написать диспетчеру", url=f"https://t.me/{DISPATCHER_TG}")],
            [
                InlineKeyboardButton(text="📞 Позвонить диспетчеру", url=f"tel:{DISPATCHER_PHONE}"),
                InlineKeyboardButton(text="📋 Телефон диспетчера", callback_data="show_phone"),
            ],
        ]
    )

def car_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Легковой", callback_data="car_легковой"),
                InlineKeyboardButton(text="Камри", callback_data="car_камри"),
                InlineKeyboardButton(text="Минивэн", callback_data="car_минивэн"),
            ],
            [InlineKeyboardButton(text="↩️ Сначала", callback_data="calc_restart")],
        ]
    )

# ========= FSM =========

class Calc(StatesGroup):
    waiting_from = State()
    waiting_to = State()
    waiting_car = State()

# ========= AIOGRAM И FASTAPI =========

router = Router()
storage = MemoryStorage()
bot = Bot(TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=storage)
dp.include_router(router)

app = FastAPI()


# ------- ХЭНДЛЕРЫ -------

@router.message(CommandStart())
async def on_start(message: Message):
    txt = (
        "👋 <b>Добро пожаловать!</b>\n"
        "Я помогу рассчитать стоимость трансфера из/в аэропорт Минеральные Воды и по КМВ.\n\n"
        "Нажмите «Рассчитать стоимость», чтобы начать."
    )
    await message.answer(txt, reply_markup=main_menu_kb())


@router.callback_query(F.data == "show_phone")
async def show_phone(cb: CallbackQuery):
    await cb.answer(DISPATCHER_PHONE, show_alert=True)


@router.callback_query(F.data == "calc")
async def calc_begin(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(Calc.waiting_from)
    await cb.message.answer("🏁 Введите <b>пункт отправления</b> (город/посёлок):")
    await cb.answer()


@router.message(Calc.waiting_from)
async def calc_from(message: Message, state: FSMContext):
    await state.update_data(from_city=message.text.strip())
    await state.set_state(Calc.waiting_to)
    await message.answer("📍 Теперь введите <b>пункт назначения</b>:")


@router.message(Calc.waiting_to)
async def calc_to(message: Message, state: FSMContext):
    await state.update_data(to_city=message.text.strip())
    await state.set_state(Calc.waiting_car)
    await message.answer("🚘 Выберите <b>класс авто</b>:", reply_markup=car_kb())


@router.callback_query(F.data == "calc_restart")
async def calc_restart(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(Calc.waiting_from)
    await cb.message.answer("🏁 Давайте заново. Введите <b>пункт отправления</b>:")
    await cb.answer()


@router.callback_query(F.data.startswith("car_"))
async def calc_car(cb: CallbackQuery, state: FSMContext):
    car_key = cb.data.split("_", 1)[1]  # 'легковой' | 'камри' | 'минивэн'
    await state.update_data(car=car_key)
    data = await state.get_data()
    from_city = data.get("from_city", "").strip()
    to_city = data.get("to_city", "").strip()

    # Сначала — фиксированный тариф по пункту назначения
    price = get_fixed_price(to_city, car_key)
    details = ""
    if price is None:
        # Пытаемся посчитать по километражу
        async with aiohttp.ClientSession() as session:
            km = await route_distance_km(session, from_city, to_city)
        if km is not None:
            price = compute_by_rates(km, car_key)
            details = f"\n📏 Расстояние: ~{km} км"
        else:
            price = None

    disclaimer = "⚠️ <i>Цены являются приблизительными, окончательная стоимость оговаривается с диспетчером.</i>\n"

    if price is not None:
        text = (
            f"{disclaimer}"
            f"Маршрут: <b>{from_city}</b> → <b>{to_city}</b>\n"
            f"Класс авто: <b>{car_key.capitalize()}</b>\n"
            f"💰 Предварительная стоимость: <b>{price} ₽</b>{details}"
        )
    else:
        text = (
            f"{disclaimer}"
            f"Маршрут: <b>{from_city}</b> → <b>{to_city}</b>\n"
            f"Класс авто: <b>{car_key.capitalize()}</b>\n"
            "Не удалось автоматически оценить стоимость — напишите диспетчеру."
        )

    await cb.message.answer(text, reply_markup=main_menu_kb())
    await cb.answer()
    await state.clear()


# ------- FASTAPI РОУТЫ ДЛЯ ВЕБХУКА -------

def make_webhook_path(token: str) -> str:
    if WEBHOOK_SECRET:
        suffix = WEBHOOK_SECRET.strip()
    else:
        # Генерим стабильный “секрет” из токена (безопаснее, чем голый токен)
        suffix = hashlib.sha256(token.encode()).hexdigest()[:32]
    return f"/webhook/{suffix}"

WEBHOOK_PATH = make_webhook_path(TOKEN)


@app.on_event("startup")
async def on_startup():
    if not WEBHOOK_BASE:
        # Запустимся без вебхука (можно опрашивать вручную или настроить позже)
        print("WARNING:WEBHOOK_BASE не задан — вебхук не будет установлен. Укажи WEBHOOK_BASE.")
        return
    url = WEBHOOK_BASE.rstrip("/") + WEBHOOK_PATH
    try:
        await bot.set_webhook(url)
        print(f"Webhook set: {url}")
    except Exception as e:
        print(f"Failed set webhook: {e}")


@app.on_event("shutdown")
async def on_shutdown():
    try:
        await bot.delete_webhook(drop_pending_updates=False)
    except Exception:
        pass
    await bot.session.close()


@app.get("/health")
async def health():
    return PlainTextResponse("ok")


@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    body = await request.json()
    update = bot._parse_update(body)  # внутренний парсер aiogram
    await dp.feed_update(bot, update)
    return JSONResponse({"status": "ok"})


# ------- ЛОКАЛЬНЫЙ СТАРТ (для docker/cmd) -------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        reload=False,
    )
