# Деплой на Dockhost (Docker)

## Шаги
1) Залей проект в GitHub (корнем репо должна быть папка с Dockerfile, main.py, requirements.txt).
2) В Dockhost создай контейнерное веб-приложение из Git.
3) Build context: `/`, Dockerfile path: `Dockerfile`.
4) Port: **8000**; Health check path: `/` (опционально).
5) Environment Variables:
   - BOT_TOKEN = токен из @BotFather
   - APP_BASE_URL = https://your-project.dockhost.ru
   - WEBHOOK_SECRET = длинная случайная строка (40+ символов)
6) Запусти деплой и смотри логи: должна появиться строка `Webhook set to https://.../webhook/...`.

## Локальная проверка Docker
```bash
docker build -t tg-bot-webhook .
docker run --rm -p 8000:8000 \
  -e BOT_TOKEN=... \
  -e APP_BASE_URL=https://<публичный_url> \
  -e WEBHOOK_SECRET=your_secret \
  tg-bot-webhook
```
> Для обработки апдейтов Telegram нужен публичный HTTPS-URL.
