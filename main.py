import os
import logging
from fastapi import FastAPI, Request, HTTPException
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Update, Message, BotCommand
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
APP_BASE_URL = os.getenv("APP_BASE_URL")  # e.g. https://your-app.dockhost.ru
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "change_me_secret")

if not BOT_TOKEN:
    raise RuntimeError("Missing BOT_TOKEN in environment")
if not APP_BASE_URL:
    raise RuntimeError("Missing APP_BASE_URL in environment")

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

@dp.message(CommandStart())
async def start(msg: Message):
    await msg.answer("Привет! Я работаю через webhook 24/7 🤖")

@dp.message(Command("help"))
async def help_cmd(msg: Message):
    await msg.answer("Это webhook-бот на aiogram 3 + FastAPI.")

@dp.message(F.text)
async def echo(msg: Message):
    await msg.reply(msg.text)

app = FastAPI()

@app.on_event("startup")
async def on_startup():
    commands = [
        BotCommand(command="start", description="Запустить бота"),
        BotCommand(command="help", description="Помощь"),
    ]
    await bot.set_my_commands(commands)

    url = APP_BASE_URL.rstrip("/") + "/webhook/" + WEBHOOK_SECRET
    await bot.set_webhook(
        url=url,
        secret_token=WEBHOOK_SECRET,
        drop_pending_updates=True,
    )
    logging.info("Webhook set to %s", url)

@app.on_event("shutdown")
async def on_shutdown():
    await bot.delete_webhook(drop_pending_updates=False)
    logging.info("Webhook removed")

@app.post("/webhook/{token}")
async def telegram_webhook(request: Request, token: str):
    if token != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="forbidden")
    data = await request.json()
    update = Update.model_validate(data)
    await dp.feed_update(bot, update)
    return {"ok": True}

@app.get("/")
async def root():
    return {"status": "ok"}
