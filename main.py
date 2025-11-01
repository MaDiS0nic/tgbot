import os
import math
import asyncio
import logging
import re
import calendar as pycal
from datetime import date, timedelta
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
DISPATCHER_PHONE = "+79340241414"
DISPATCHER_NAME = "Диспетчер TransferAir"

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

# ================== LOGGING ==================
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("tgbot")

# ================== CORE ==================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ================== BUTTONS ==================
BTN_START = "▶️ Старт"
BTN_CALC = "🧮 Калькулятор стоимости"
BTN_ORDER = "📝 Сделать заказ"
BTN_DISPATCHER = "☎️ Диспетчер"
BTN_INFO = "ℹ️ Информация"

MENU_BUTTONS = [BTN_CALC, BTN_ORDER, BTN_DISPATCHER, BTN_INFO]

# ================== MENU ==================
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
            url="https://t.me/zhelektown"
        )
    ], [
        InlineKeyboardButton(
            text="📱 Телефон диспетчера",
            callback_data="dispatcher_phone"
        )
    ]])

# ================== STATES ==================
class DummyStates(StatesGroup):
    pass

# ================== COMMANDS ==================
@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "*Здравствуйте!*\n"
        "Это бот междугороднего такси TransferAir Кавказские Минеральные Воды.\n\n"
        "Нажмите *Старт*, чтобы продолжить.",
        parse_mode="Markdown",
        reply_markup=start_big_button_kb(),
    )

@dp.message(F.text == BTN_START)
async def main_menu(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Выберите действие:", reply_markup=main_menu_kb())

# ================== HANDLERS ==================
@dp.message(F.text == BTN_DISPATCHER)
async def dispatcher_menu(message: Message):
    text = (
        "☎️ *Связаться с диспетчером*\n\n"
        "Нажмите кнопку ниже, чтобы написать диспетчеру в Telegram\n"
        "или получить номер телефона для звонка."
    )
    await message.answer(text, parse_mode="Markdown", reply_markup=dispatcher_inline_kb())

@dp.callback_query(F.data == "dispatcher_phone")
async def dispatcher_phone_cb(cb: CallbackQuery):
    # Отправляем контакт (номер станет кликабельным)
    await bot.send_contact(
        chat_id=cb.message.chat.id,
        phone_number=DISPATCHER_PHONE,
        first_name=DISPATCHER_NAME,
    )
    # Дополнительно продублируем номер в отдельном сообщении
    await bot.send_message(cb.message.chat.id, DISPATCHER_PHONE)
    await cb.answer("Контакт отправлен")

@dp.message(F.text == BTN_INFO)
async def info_section(message: Message):
    await message.answer(
        "🚕 TransferAir междугороднее такси (Трансфер) из Минеральных Вод.\n\n"
        "🤖 Вы можете заказать трансфер через этого бота.\n\n"
        "📞 Позвонить нам: +79340241414\n\n"
        "🌐 Посетить наш сайт: https://transferkmw.ru/",
    )
    # После текста отправляем контакт (номер кликабелен)
    await bot.send_contact(message.chat.id, DISPATCHER_PHONE, DISPATCHER_NAME)
    await bot.send_message(message.chat.id, DISPATCHER_PHONE)

# ================== FASTAPI ==================
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
