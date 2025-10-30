import os
import asyncio
import logging
from typing import Final

from fastapi import FastAPI, Request, HTTPException
from aiogram import Bot, Dispatcher, F
from aiogram.types import Update, Message, BotCommand
from aiogram.filters import CommandStart

# ---------- Конфиг из переменных окружения ----------
BOT_TOKEN: Final[str] = os.getenv("BOT_TOKEN", "")
APP_BASE_URL: Final[str] = os.getenv("APP_BASE_URL", "").rstrip("/")
WEBHOOK_SECRET: Final[str] = os.getenv("WEBHOOK_SECRET", "")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

# ---------- Логирование ----------
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("tgbot")

# ---------- Aiogram ----------
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message(CommandStart())
async def on_start(message: Message):
    await message.answer("Бот запущен! ✨")

@dp.message(F.text == "/help")
async def on_help(message: Message):
    await message.answer("Команды: /start, /help")

# ---------- FastAPI ----------
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

# ----- Фоновая установка вебхука с ретраями -----
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
            # Повторная попытка чуть позже
            await asyncio.sleep(30)

@app.on_event("startup")
async def on_startup():
    # запускаем фоновую задачу, чтобы не падать, если домен еще не готов
    asyncio.create_task(_set_webhook_with_retry())
    logger.info("Startup complete. HTTP server is up; waiting for webhook setup…")

@app.on_event("shutdown")
async def on_shutdown():
    try:
        await bot.delete_webhook(drop_pending_updates=False)
        logger.info("Webhook removed")
    except Exception as e:
        logger.warning("Failed to delete webhook: %s", e)
