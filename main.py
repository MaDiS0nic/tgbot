import os
import logging

from fastapi import FastAPI, Request
from starlette.responses import JSONResponse

from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Update, Message

# ----------------- Конфиг -----------------
# Обязательные переменные окружения:
#   TELEGRAM_TOKEN   — токен бота от @BotFather
#   PUBLIC_BASE_URL  — публичный HTTPS-домен/URL без слеша в конце
# Необязательная:
#   WEBHOOK_SECRET   — секретная часть пути вебхука (по умолчанию: "CHANGE_ME_SECRET")
TELEGRAM_TOKEN = os.getenv("8402271440:AAH_76pBTaHSD-q7T8I4TG1ZP1qqrSyTkA0")
PUBLIC_BASE_URL = os.getenv("https://f7ey-7apd-gkb0.gw-1a.dockhost.net")  # напр.: https://abcd-1234.ngrok-free.app
WEBHOOK_SECRET = os.getenv("ADjMLxwEpTZsdSUCHfgoakJ16mi5WNeQBz9IKXP7OlRbY2Vy", "CHANGE_ME_SECRET")

if not TELEGRAM_TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN is not set")
if not PUBLIC_BASE_URL:
    raise RuntimeError("PUBLIC_BASE_URL is not set")

WEBHOOK_PATH = f"/webhook/{WEBHOOK_SECRET}"
WEBHOOK_URL = f"{PUBLIC_BASE_URL}{WEBHOOK_PATH}"

# ----------------- Логирование -----------------
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("app")

# ----------------- Приложение и бот -----------------
app = FastAPI()
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# Небольшой пример-роутер, чтобы апдейты было куда отправлять (можно удалить)
router = Router()

@router.message(F.text)
async def echo_text(msg: Message):
    # простой эхо-хэндлер (можешь заменить своими)
    await msg.answer(msg.text)

dp.include_router(router)


# ----------------- Жизненный цикл -----------------
@app.on_event("startup")
async def on_startup():
    await bot.set_webhook(WEBHOOK_URL)
    log.info(f"Webhook set: {WEBHOOK_URL}")

@app.on_event("shutdown")
async def on_shutdown():
    # сохраняем входящие апдейты в очереди Telegram (False) — можешь поставить True,
    # если хочешь очистить очередь при выключении
    await bot.delete_webhook(drop_pending_updates=False)
    log.info("Webhook deleted")


# ----------------- Хэндпоинты -----------------
@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    """
    Приём апдейтов от Telegram.
    ВАЖНО: здесь НЕ использовать никаких приватных методов бота вида _parse_update.
    Для aiogram 3.x корректно: Update.model_validate(...) + dp.feed_update(...)
    """
    body = await request.json()
    update = Update.model_validate(body)         # парсинг/валидация апдейта (Pydantic v2)
    await dp.feed_update(bot, update)            # кормим диспетчер
    return JSONResponse({"status": "ok"})

@app.get("/")
async def healthcheck():
    return {"status": "alive", "webhook_path": WEBHOOK_PATH}
