import os
import asyncio
import base64
import re
from telegram import BotCommandScopeAllPrivateChats, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from io import BytesIO
from dotenv import load_dotenv

import aiohttp
import requests
from telegram import Update, BotCommand
from telegram.ext import (
    ApplicationBuilder, CommandHandler,
    MessageHandler, ContextTypes, filters
)

# === КОНСТАНТЫ ===
MAX_HISTORY_MESSAGES = 4
MAX_RETRIES = 3
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://your-webapp-domain.com")
# ===============================

# === Настройки окружения ===
load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN")
GAS_PROXY_URL = os.getenv("GAS_PROXY_URL")

TOKEN = TOKEN.strip() if TOKEN else None
GAS_PROXY_URL = GAS_PROXY_URL.strip() if GAS_PROXY_URL else None

if not TOKEN or not GAS_PROXY_URL:
    print("Ошибка: Убедитесь, что TELEGRAM_TOKEN и GAS_PROXY_URL установлены в файле .env")
    exit(1)


# ... (остальной код бота без изменений до функций) ...

# === ДОБАВЛЯЕМ КОМАНДУ ДЛЯ MINI APP ===
async def webapp_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для открытия Mini App"""
    keyboard = [[
        InlineKeyboardButton(
            "📱 Открыть Web App",
            web_app=WebAppInfo(url=WEBAPP_URL)
        )
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "Откройте Web App для удобной работы с Gemini AI в полноэкранном режиме:",
        reply_markup=reply_markup
    )


# === ОБНОВЛЯЕМ ФУНКЦИЮ help_command ===
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет список команд."""
    keyboard = [[
        InlineKeyboardButton(
            "📱 Открыть Web App",
            web_app=WebAppInfo(url=WEBAPP_URL)
        )
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "📘 Команды:\n"
        "/start — начать\n"
        "/help — список команд\n"
        "/reset — очистить историю диалога\n"
        "/app — открыть Web App\n\n"
        "💬 В группе используй **@**, чтобы бот ответил. Бот помнит контекст последних сообщений.\n"
        "🖼️ Анализ: Отправьте фото или документ (PDF, TXT) с подписью, **упомянув бота (@ваш_бот)**, для анализа.",
        reply_markup=reply_markup
    )


# === Запуск ===
def main():
    """Основная функция запуска бота."""
    app = ApplicationBuilder().token(TOKEN).concurrent_updates(True).read_timeout(30).build()

    # === Регистрация обработчиков ===
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("reset", reset_command))
    app.add_handler(CommandHandler("app", webapp_command))  # <-- НОВАЯ КОМАНДА

    # Обработчик для фотографий и документов
    file_handler = MessageHandler(
        (filters.PHOTO | filters.Document.ALL) & filters.UpdateType.MESSAGE,
        handle_files
    )
    app.add_handler(file_handler)

    # Обработчик для текстовых сообщений
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    app.post_init = set_bot_commands

    print("✅ Бот запущен на Amvera. Работает в чатах и группах.")

    # Запуск polling (для Amvera)
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()