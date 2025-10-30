import os
import re
import json
import asyncio
import logging
from typing import Tuple, Optional, Dict

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.client.bot import DefaultBotProperties
from aiogram.filters import CommandStart
from aiogram.types import (
    Update,
    Message,
    CallbackQuery,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.fsm.storage.memory import MemoryStorage
import aiohttp

############################
# ====== НАСТРОЙКИ ====== #
############################

# Твой токен (после тестов лучше вынести в переменные окружения и перевыпустить в BotFather)
TOKEN = "8402271440:AAH_76pBTaHSD-q7T8I4TG1ZP1qqrSyTkA0"

ADMIN_CHAT_ID = 7039409310

# Фото в приветствии (Camry). Можно заменить на свою ссылку.
PHOTO_URL = "https://i.imgur.com/1D0mI0Q.jpeg"

# Кнопки тарифов и динамические цены (км) — используются, если город не из списка фиксированных
TARIFFS_ORDER = ["Легковой", "Camry", "Минивэн"]
DYNAMIC_PER_KM = {"Легковой": 30, "Camry": 40, "Минивэн": 50}

# Гео-API
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_HEADERS = {"User-Agent": "TransferAirBot/1.0 (admin@transferair.ru)"}
OSRM_URL = "https://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}"

DISCLAIMER = "⚠️ Стоимость приблизительная. Итоговая цена согласуется с диспетчером."

# Вебхук: базовый домен бери из переменной окружения WEBHOOK_BASE, например:
#   https://f7ey-7apd-gkb0.gw-1a.dockhost.net
# Dockhost обычно проксирует 443 -> 8000, поэтому HTTPS обязателен.
WEBHOOK_BASE = os.getenv("WEBHOOK_BASE", "").rstrip("/")
# Секрет вебхука — можно оставить дефолтным или задать через окружение
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "Y2VpcmEtc2VjdXJl")
WEBHOOK_PATH = f"/webhook/{WEBHOOK_SECRET}"
WEBHOOK_URL = f"{WEBHOOK_BASE}{WEBHOOK_PATH}" if WEBHOOK_BASE else None

############################
# ====== ЛОГИ / БОТ ====== #
############################

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("transferair")

# Правильная инициализация бота для aiogram ≥ 3.7
bot = Bot(
    TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher(storage=MemoryStorage())

app = FastAPI()


##############################
# ====== ФИКС. ТАРИФЫ ====== #
##############################

def norm_city(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"\s*-\s*", "-", s)
    s = re.sub(r"\s+", " ", s)
    return s

FIXED_FARES: Dict[str, Dict[str, int]] = {
    # --- сюда вставлен твой полный список ---
    norm_city("Железноводск"): {"Легковой": 800, "Camry": 1500, "Минивэн": 2000},
    norm_city("Пятигорск"): {"Легковой": 1200, "Camry": 1500, "Минивэн": 1900},
    norm_city("Ессентуки"): {"Легковой": 1300, "Camry": 2000, "Минивэн": 2500},
    norm_city("Кисловодск"): {"Легковой": 1800, "Camry": 2500, "Минивэн": 3000},
    norm_city("Архыз"): {"Легковой": 6500, "Camry": 8000, "Минивэн": 10000},
    norm_city("Архыз Романтик"): {"Легковой": 7000, "Camry": 9000, "Минивэн": 11000},
    norm_city("Домбай"): {"Легковой": 6500, "Camry": 8000, "Минивэн": 10000},
    norm_city("Азау"): {"Легковой": 5500, "Camry": 7500, "Минивэн": 9000},
    norm_city("Терскол"): {"Легковой": 5500, "Camry": 7500, "Минивэн": 9000},
    norm_city("Эльбрус"): {"Легковой": 5500, "Camry": 7500, "Минивэн": 8500},
    norm_city("Теберда"): {"Легковой": 5500, "Camry": 7500, "Минивэн": 8500},
    norm_city("Нейтрино"): {"Легковой": 5000, "Camry": 7500, "Минивэн": 8500},
    norm_city("Тегенекли"): {"Легковой": 5000, "Camry": 7500, "Минивэн": 8500},
    norm_city("Байдаево"): {"Легковой": 5000, "Camry": 7500, "Минивэн": 8500},
    norm_city("Чегет"): {"Легковой": 5500, "Camry": 7500, "Минивэн": 9000},
    norm_city("Ставрополь"): {"Легковой": 5400, "Camry": 7200, "Минивэн": 9000},
    norm_city("Черкесск"): {"Легковой": 3000, "Camry": 4000, "Минивэн": 5000},
    norm_city("Нальчик"): {"Легковой": 3300, "Camry": 4400, "Минивэн": 5500},
    norm_city("Владикавказ"): {"Легковой": 6600, "Camry": 8800, "Минивэн": 11000},
    norm_city("Грозный"): {"Легковой": 9300, "Camry": 12400, "Минивэн": 15500},
    norm_city("Назрань"): {"Легковой": 6600, "Camry": 8800, "Минивэн": 11000},
    norm_city("Адлер"): {"Легковой": 17400, "Camry": 23200, "Минивэн": 29000},
    norm_city("Алагир"): {"Легковой": 6000, "Camry": 8000, "Минивэн": 10000},
    norm_city("Александровское село"): {"Легковой": 2100, "Camry": 2800, "Минивэн": 3500},
    norm_city("Ардон"): {"Легковой": 5500, "Camry": 7400, "Минивэн": 9200},
    norm_city("Арзгир"): {"Легковой": 6000, "Camry": 8000, "Минивэн": 10000},
    norm_city("Армавир"): {"Легковой": 5700, "Camry": 7600, "Минивэн": 9500},
    norm_city("Астрахань"): {"Легковой": 18900, "Camry": 25000, "Минивэн": 31500},
    norm_city("Аушигер"): {"Легковой": 4000, "Camry": 5400, "Минивэн": 6700},
    norm_city("Ачикулак село"): {"Легковой": 5500, "Camry": 7400, "Минивэн": 9200},
    norm_city("Баксан"): {"Легковой": 2500, "Camry": 3300, "Минивэн": 4000},
    norm_city("Батуми"): {"Легковой": 30000, "Camry": 40000, "Минивэн": 50000},
    norm_city("Беломечетская станица"): {"Легковой": 3600, "Camry": 4800, "Минивэн": 6000},
    norm_city("Беслан"): {"Легковой": 6000, "Camry": 8000, "Минивэн": 10000},
    norm_city("Благодарный"): {"Легковой": 4000, "Camry": 5400, "Минивэн": 6700},
    norm_city("Будёновск"): {"Легковой": 4000, "Camry": 5400, "Минивэн": 6700},
    norm_city("Витязево поселок"): {"Легковой": 18000, "Camry": 24000, "Минивэн": 30000},
    norm_city("Волгоград"): {"Легковой": 18000, "Camry": 24000, "Минивэн": 30000},
    norm_city("Галюгаевская станица"): {"Легковой": 6000, "Camry": 8000, "Минивэн": 10000},
    norm_city("Геленджик"): {"Легковой": 18000, "Camry": 24000, "Минивэн": 30000},
    norm_city("Георгиевск"): {"Легковой": 1300, "Camry": 2000, "Минивэн": 2500},
    norm_city("Горнозаводское село"): {"Легковой": 3000, "Camry": 4000, "Минивэн": 5000},
    norm_city("Грушевское село"): {"Легковой": 3300, "Camry": 4400, "Минивэн": 5500},
    norm_city("Гудаури"): {"Легковой": 15000, "Camry": 20000, "Минивэн": 25000},
    norm_city("Дербент"): {"Легковой": 18000, "Camry": 24000, "Минивэн": 30000},
    norm_city("Джубга"): {"Легковой": 14000, "Camry": 19000, "Минивэн": 23000},
    norm_city("Екатеринбург"): {"Легковой": 72000, "Camry": 96000, "Минивэн": 120000},
    norm_city("Елизаветинское село"): {"Легковой": 3700, "Camry": 5000, "Минивэн": 6200},
    norm_city("Зеленокумск"): {"Легковой": 2400, "Camry": 3200, "Минивэн": 4000},
    norm_city("Зеленчукская станица"): {"Легковой": 5000, "Camry": 7500, "Минивэн": 8500},
    norm_city("Зольская станица"): {"Легковой": 1500, "Camry": 2000, "Минивэн": 2500},
    norm_city("Иконхалк"): {"Легковой": 3400, "Camry": 4500, "Минивэн": 5600},
    norm_city("Кабардинка"): {"Легковой": 16500, "Camry": 22000, "Минивэн": 27500},
    norm_city("Камата село (Осетия)"): {"Легковой": 6000, "Camry": 8000, "Минивэн": 10000},
    norm_city("Карчаевск"): {"Легковой": 4600, "Camry": 6100, "Минивэн": 7700},
    norm_city("Каратюбе"): {"Легковой": 5400, "Camry": 7200, "Минивэн": 9000},
    norm_city("Каспийск"): {"Легковой": 14500, "Camry": 19000, "Минивэн": 24000},
    norm_city("Кизляр"): {"Легковой": 11400, "Camry": 15200, "Минивэн": 19000},
    norm_city("Кочубеевское село"): {"Легковой": 3700, "Camry": 5000, "Минивэн": 6200},
    norm_city("Краснодар"): {"Легковой": 12000, "Camry": 16000, "Минивэн": 20000},
    norm_city("Курская"): {"Легковой": 4300, "Camry": 5700, "Минивэн": 7100},
    norm_city("Лабинск"): {"Легковой": 7000, "Camry": 9300, "Минивэн": 11600},
    norm_city("Лазаревское"): {"Легковой": 14500, "Camry": 19200, "Минивэн": 24000},
    norm_city("Левокумское село"): {"Легковой": 5200, "Camry": 7000, "Минивэн": 8700},
    norm_city("Магас"): {"Легковой": 6600, "Camry": 8800, "Минивэн": 11000},
    norm_city("Майкоп"): {"Легковой": 8800, "Camry": 11700, "Минивэн": 14500},
    norm_city("Майский КБР"): {"Легковой": 4300, "Camry": 5700, "Минивэн": 7000},
    norm_city("Марьинская станица"): {"Легковой": 2100, "Camry": 2800, "Минивэн": 3500},
    norm_city("Махачкала"): {"Легковой": 13900, "Camry": 18500, "Минивэн": 23100},
    norm_city("Моздок"): {"Легковой": 4900, "Camry": 6500, "Минивэн": 8100},
    norm_city("Нарткала"): {"Легковой": 3700, "Camry": 5000, "Минивэн": 6200},
    norm_city("Невинномысск"): {"Легковой": 3000, "Camry": 4000, "Минивэн": 5000},
    norm_city("Незлобная станица"): {"Легковой": 1500, "Camry": 2000, "Минивэн": 2500},
    norm_city("Нефтекумск"): {"Легковой": 6400, "Camry": 8500, "Минивэн": 10700},
    norm_city("Новоалександровск"): {"Легковой": 7400, "Camry": 9800, "Минивэн": 12200},
    norm_city("Новопавловск"): {"Легковой": 2500, "Camry": 3400, "Минивэн": 4200},
    norm_city("Новороссийск"): {"Легковой": 17000, "Camry": 22600, "Минивэн": 28200},
    norm_city("Новоселицкое село"): {"Легковой": 3000, "Camry": 4000, "Минивэн": 5000},
    norm_city("Прохладный"): {"Легковой": 3600, "Camry": 4800, "Минивэн": 6000},
    norm_city("Псебай"): {"Легковой": 9000, "Camry": 12000, "Минивэн": 15000},
    norm_city("Псыгансу село"): {"Легковой": 3900, "Camry": 5200, "Минивэн": 6500},
    norm_city("Ростов-на-Дону"): {"Легковой": 16000, "Camry": 21000, "Минивэн": 26000},
    norm_city("Светлоград"): {"Легковой": 5100, "Camry": 6800, "Минивэн": 8500},
    norm_city("Сочи"): {"Легковой": 16500, "Camry": 22000, "Минивэн": 27500},
    norm_city("Степанцминда"): {"Легковой": 13000, "Camry": 17000, "Минивэн": 22000},
    norm_city("Степное село"): {"Легковой": 4400, "Camry": 5800, "Минивэн": 7300},
    norm_city("Сунжа"): {"Легковой": 7500, "Camry": 10000, "Минивэн": 12500},
    norm_city("Тбилиси"): {"Легковой": 20000, "Camry": 25000, "Минивэн": 30000},
    norm_city("Терек"): {"Легковой": 4700, "Camry": 6200, "Минивэн": 7800},
    norm_city("Туапсе"): {"Легковой": 13000, "Camry": 17300, "Минивэн": 21700},
    norm_city("Урус-Мартан"): {"Легковой": 9000, "Camry": 12000, "Минивэн": 15000},
    norm_city("Учкулан аул"): {"Легковой": 6000, "Camry": 8000, "Минивэн": 10000},
    norm_city("Хадыженск"): {"Легковой": 10700, "Camry": 14200, "Минивэн": 17800},
    norm_city("Хасавюрт"): {"Легковой": 11400, "Camry": 15200, "Минивэн": 19000},
    norm_city("Хурзук аул"): {"Легковой": 6500, "Camry": 9000, "Минивэн": 11500},
    norm_city("Цей"): {"Легковой": 7300, "Camry": 9700, "Минивэн": 12000},
    norm_city("Элиста"): {"Легковой": 9400, "Camry": 12500, "Минивэн": 15600},
}


##############################
# ====== КЛАВИАТУРЫ ======= #
##############################

def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Калькулятор стоимости")],
            [KeyboardButton(text="Сделать заказ")],
            [KeyboardButton(text="Диспетчер")],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите действие…",
    )

def dispatcher_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💬 Написать диспетчеру", url="https://t.me/sergeomoscarpone")],
            [InlineKeyboardButton(text="📞 Показать номер", callback_data="show_phone")],
        ]
    )

def tariff_buttons(prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=name, callback_data=f"{prefix}:{i}")]
            for i, name in enumerate(TARIFFS_ORDER)
        ]
    )


##############################
# ====== ГЕО / ДИСТ ======= #
##############################

async def geocode(session: aiohttp.ClientSession, name: str) -> Optional[Tuple[float, float]]:
    params = {"q": name, "format": "json", "limit": 1, "addressdetails": 0, "accept-language": "ru"}
    async with session.get(NOMINATIM_URL, params=params, headers=NOMINATIM_HEADERS) as r:
        if r.status != 200:
            raise RuntimeError(f"Nominatim HTTP {r.status}")
        data = await r.json()
        if not data:
            return None
        return float(data[0]["lat"]), float(data[0]["lon"])

async def route_distance_km(a_name: str, b_name: str) -> float:
    async with aiohttp.ClientSession() as session:
        a = await geocode(session, a_name)
        b = await geocode(session, b_name)
        if not a or not b:
            raise ValueError("Не удалось определить координаты одного из городов.")
        lat1, lon1 = a
        lat2, lon2 = b
        url = OSRM_URL.format(lon1=lon1, lat1=lat1, lon2=lon2, lat2=lat2)
        async with session.get(url, params={"overview": "false"}) as r:
            if r.status != 200:
                raise RuntimeError(f"OSRM HTTP {r.status}")
            data = await r.json()
            if not data.get("routes"):
                raise ValueError("OSRM не вернул маршруты.")
            return data["routes"][0]["distance"] / 1000.0


##############################
# ====== ХЕНДЛЕРЫ ========= #
##############################

@dp.message(CommandStart())
async def on_start(message: Message):
    caption = (
        "<b>Здравствуйте!</b>\n"
        "Это бот междугороднего такси <b>TransferAir</b> Кавказские Минеральные Воды.\n\n"
        "Выберите нужный раздел ниже 👇"
    )
    try:
        await message.answer_photo(photo=PHOTO_URL, caption=caption, reply_markup=main_menu())
    except Exception:
        await message.answer(caption, reply_markup=main_menu())

@dp.message(F.text.casefold() == "диспетчер")
async def on_dispatcher(message: Message):
    phone = "+7 934 024-14-14"
    text = (
        f"📞 Связаться с диспетчером:\n<b>{phone}</b>\n\n"
        "Нажмите кнопку ниже, чтобы написать диспетчеру или показать номер для копирования."
    )
    await message.answer(text, reply_markup=dispatcher_kb())

@dp.callback_query(F.data == "show_phone")
async def on_show_phone(cb: CallbackQuery):
    await cb.answer("Номер диспетчера: +7 934 024-14-14", show_alert=True)

# Калькулятор
@dp.message(F.text.casefold() == "калькулятор стоимости")
async def calc_begin(message: Message):
    await dp.storage.set_data(chat=message.chat.id, data={"calc_step": "from"})
    await message.answer("Введите город отправления:")

@dp.message()
async def calc_steps_or_fallback(message: Message):
    data = await dp.storage.get_data(chat=message.chat.id)
    step = data.get("calc_step")

    if step == "from":
        await dp.storage.update_data(chat=message.chat.id, data={"from_city": message.text, "calc_step": "to"})
        await message.answer("Введите город прибытия:")
        return

    if step == "to":
        from_raw = data.get("from_city", "")
        to_raw = message.text

        from_norm = norm_city(from_raw)
        to_norm = norm_city(to_raw)

        await dp.storage.update_data(chat=message.chat.id, data={"calc_step": None})

        fixed_key = to_norm if to_norm in FIXED_FARES else (from_norm if from_norm in FIXED_FARES else None)
        if fixed_key:
            text = (
                f"Маршрут: <b>{from_raw}</b> ↔️ <b>{to_raw}</b>\n\n"
                f"{DISCLAIMER}\n\n"
                "Выберите тариф:"
            )
            await dp.storage.update_data(chat=message.chat.id, data={"_calc_ctx": {"kind": "fix", "fixed_key": fixed_key}})
            await message.answer(text, reply_markup=tariff_buttons("price:fix"))
            return

        try:
            dist = await route_distance_km(from_raw, to_raw)
        except Exception:
            await message.answer("Не удалось определить расстояние. Проверьте города и попробуйте ещё раз.")
            return

        await dp.storage.update_data(chat=message.chat.id, data={"_calc_ctx": {"kind": "dyn", "distance": dist}})
        text = (
            f"Расстояние между <b>{from_raw}</b> и <b>{to_raw}</b> ≈ <b>{dist:.1f} км</b>\n\n"
            f"{DISCLAIMER}\n\n"
            "Выберите тариф:"
        )
        await message.answer(text, reply_markup=tariff_buttons("price:dyn"))
        return

# Выбор тарифа
@dp.callback_query(F.data.startswith("price:"))
async def on_price(cb: CallbackQuery):
    parts = cb.data.split(":")
    if len(parts) != 3:
        return await cb.answer()

    _, kind, idx = parts
    try:
        idx = int(idx)
    except ValueError:
        return await cb.answer()

    tariff = TARIFFS_ORDER[idx]
    st = await dp.storage.get_data(chat=cb.message.chat.id)
    ctx = st.get("_calc_ctx", {})

    if ctx.get("kind") == "fix":
        fares = FIXED_FARES.get(ctx.get("fixed_key"), {})
        price = fares.get(tariff)
        if price is None:
            await cb.message.answer("Для выбранного тарифа цена не задана.")
        else:
            await cb.message.answer(f"{DISCLAIMER}\n\n💰 Тариф <b>{tariff}</b>: <b>{price} ₽</b>.")
        return await cb.answer()

    if ctx.get("kind") == "dyn":
        dist = float(ctx.get("distance", 0.0))
        price = round(DYNAMIC_PER_KM.get(tariff, 0) * dist)
        await cb.message.answer(f"{DISCLAIMER}\n\n💰 Тариф <b>{tariff}</b>: <b>{price} ₽</b>.")
        return await cb.answer()

    await cb.answer()

# Заказ
@dp.message(F.text.casefold() == "сделать заказ")
async def order_start(message: Message):
    text = (
        "🚕 Для оформления заказа отправьте одним сообщением данные в таком формате:\n\n"
        "1) Город отправления\n"
        "2) Город прибытия\n"
        "3) Дата (напр., 31.10.2025)\n"
        "4) Время подачи (напр., 14:30)\n"
        "5) Телефон\n"
        "6) Комментарий (опционально)\n\n"
        "Ждём сообщение 👇"
    )
    await dp.storage.update_data(chat=message.chat.id, data={"order_mode": True})
    await message.answer(text)

@dp.message(F.text)
async def order_collect(message: Message):
    data = await dp.storage.get_data(chat=message.chat.id)
    if not data.get("order_mode"):
        return
    text = (
        f"📦 <b>Новый заказ</b>\n"
        f"От: @{message.from_user.username or message.from_user.id}\n\n"
        f"{message.text}"
    )
    try:
        await bot.send_message(ADMIN_CHAT_ID, text)
    except Exception:
        pass
    await dp.storage.update_data(chat=message.chat.id, data={"order_mode": False})
    await message.answer("✅ Спасибо! Ваша заявка принята. В ближайшее время с вами свяжется диспетчер.")


########################################
# ====== FASTAPI / ВЕБХУКИ / ХП ====== #
########################################

@app.get("/", response_class=PlainTextResponse)
async def root():
    return "status ok"

@app.on_event("startup")
async def on_startup():
    if not WEBHOOK_URL:
        log.warning("WEBHOOK_BASE не задан — вебхук не будет установлен. Укажи переменную окружения WEBHOOK_BASE (https://<твой_домен>).")
        return
    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception:
        pass
    await bot.set_webhook(WEBHOOK_URL, allowed_updates=["message", "callback_query"])
    log.info(f"Webhook set to {WEBHOOK_URL}")

@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    data = await request.json()
    update = Update.model_validate(data)
    await dp.feed_update(bot, update)
    return {"ok": True}
