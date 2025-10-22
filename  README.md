# Gemini Telegram Bot + Web App

Бот и веб-приложение для работы с Gemini AI через Telegram.

## Структура проекта

- `bot/` - Telegram бот
- `server/` - API сервер для Web App
- `webapp/` - Telegram Mini App фронтенд

## Деплой

1. Бот деплоится на Amvera как worker
2. Frontend деплоится на Netlify/Vercel
3. API сервер работает на Amvera

## Переменные окружения

- `TELEGRAM_TOKEN` - токен бота
- `GAS_PROXY_URL` - URL Gemini прокси
- `WEBAPP_URL` - URL фронтенда