import logging
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    FSInputFile,
)
from aiogram.filters import CommandStart, Command
from aiogram.enums import ParseMode
import asyncio
import aiohttp
import os

# ============ НАСТРОЙКИ ============
TOKEN = os.getenv("BOT_TOKEN")  # токен бота из .env
ADMIN_CHAT_ID = 7039409310      # твой Telegram ID

# тарифы
TARIFFS = {
    "Легковой": 30,
    "Camry": 40,
    "Минивэн": 50,
}

# Фото в приветствии (можно поменять ссылку)
PHOTO_URL = "https://i.imgur.com/1D0mI0Q.jpeg"

# ============ ЛОГИРОВАНИЕ ============
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============ ИНИЦИАЛИЗАЦИЯ ============
bot = Bot(token=TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()


# ============ КЛАВИАТУРЫ ============
def main_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Калькулятор стоимости")],
            [KeyboardButton(text="Сделать заказ")],
            [KeyboardButton(text="Диспетчер")],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите действие…",
        selective=True,
    )


# ============ СТАРТ ============
@dp.message(CommandStart())
async def cmd_start(message: Message):
    caption = (
        "<b>Здравствуйте!</b>\n"
        "Это бот междугороднего такси <b>TransferAir</b> Кавказские Минеральные Воды.\n\n"
        "Выберите нужный раздел ниже 👇"
    )

    try:
        await message.answer_photo(
            photo=PHOTO_URL,
            caption=caption,
            reply_markup=main_menu_kb(),
        )
    except Exception:
        await message.answer(caption, reply_markup=main_menu_kb())


# ============ КАЛЬКУЛЯТОР ============
@dp.message(F.text.lower() == "калькулятор стоимости")
async def calc_start(message: Message):
    await message.answer("Введите город отправления:")
    await dp.storage.set_data(chat=message.chat.id, data={"step": "from"})


@dp.message()
async def handle_text(message: Message):
    data = await dp.storage.get_data(chat=message.chat.id)
    step = data.get("step")

    # Шаг 1 — город отправления
    if step == "from":
        await dp.storage.set_data(chat=message.chat.id, data={"from_city": message.text, "step": "to"})
        await message.answer("Введите город прибытия:")

    # Шаг 2 — город прибытия
    elif step == "to":
        from_city = data.get("from_city")
        to_city = message.text
        await dp.storage.set_data(chat=message.chat.id, data={"step": None})

        # Рассчитываем расстояние (через OpenRouteService)
        try:
            distance_km = await get_distance(from_city, to_city)
        except Exception as e:
            logger.error(e)
            await message.answer("Не удалось определить расстояние, попробуйте позже.")
            return

        text = f"Расстояние между <b>{from_city}</b> и <b>{to_city}</b> — примерно {distance_km:.1f} км.\n\n"
        text += "Выберите тариф:"
        buttons = [
            [InlineKeyboardButton(text=f"{name} ({price} ₽/км)", callback_data=f"tariff:{name}:{distance_km}")]
            for name, price in TARIFFS.items()
        ]
        await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

    else:
        await message.answer("Пожалуйста, выберите пункт меню ниже.", reply_markup=main_menu_kb())


@dp.callback_query(F.data.startswith("tariff:"))
async def calc_price(callback):
    _, name, distance = callback.data.split(":")
    price = TARIFFS[name] * float(distance)
    await callback.message.answer(f"💰 Стоимость поездки по тарифу <b>{name}</b>: <b>{price:.0f} ₽</b>.")
    await callback.answer()


# ============ API расчёта расстояния ============
async def get_distance(from_city, to_city):
    url = f"https://router.project-osrm.org/route/v1/driving/{from_city};{to_city}"
    params = {"overview": "false"}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as response:
            if response.status == 200:
                data = await response.json()
                return data["routes"][0]["distance"] / 1000
            else:
                raise ValueError(f"Ошибка при получении маршрута: {response.status}")


# ============ ЗАКАЗ ============
@dp.message(F.text.lower() == "сделать заказ")
async def order_start(message: Message):
    text = (
        "🚕 Для оформления заказа, пожалуйста, введите данные в следующем порядке:\n\n"
        "1️⃣ Город отправления\n"
        "2️⃣ Город прибытия\n"
        "3️⃣ Дата поездки (например, 31.10.2025)\n"
        "4️⃣ Время подачи (например, 14:30)\n"
        "5️⃣ Номер телефона\n"
        "6️⃣ Комментарий (опционально)\n\n"
        "Отправьте всё одним сообщением."
    )
    await message.answer(text)
    await dp.storage.set_data(chat=message.chat.id, data={"step": "order"})


@dp.message(F.text & (F.text.lower() != "сделать заказ"))
async def order_receive(message: Message):
    data = await dp.storage.get_data(chat=message.chat.id)
    if data.get("step") == "order":
        order_text = (
            f"📦 Новый заказ от @{message.from_user.username or 'пользователя'}:\n\n"
            f"{message.text}"
        )
        await bot.send_message(ADMIN_CHAT_ID, order_text)
        await message.answer("✅ Спасибо! Ваша заявка принята. В ближайшее время с вами свяжется диспетчер!")
        await dp.storage.set_data(chat=message.chat.id, data={})


# ============ ДИСПЕТЧЕР ============
@dp.message(F.text.lower() == "диспетчер")
async def dispatcher_info(message: Message):
    phone_number = "+79340241414"
    text = (
        f"📞 Связаться с диспетчером:\n<b>{phone_number}</b>\n\n"
        "Нажмите кнопку ниже, чтобы позвонить или написать."
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📲 Позвонить", url=f"tel:{phone_number}"),
                InlineKeyboardButton(text="💬 Написать в Telegram", url="https://t.me/TransferAirBot"),
            ]
        ]
    )
    await message.answer(text, reply_markup=kb)


# ============ ЗАПУСК ============
async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
