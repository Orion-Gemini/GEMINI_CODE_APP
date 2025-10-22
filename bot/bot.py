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
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://your-domain.com")
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


# === УТИЛИТА: ЭКРАНИРОВАНИЕ MARKDOWNV2 ===
def escape_markdown_v2(text: str) -> str:
    """Экранирует специальные символы MarkdownV2, кроме тех, что внутри блоков кода."""
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    code_blocks = re.findall(r"```.*?```", text, re.DOTALL)
    placeholder = "___CODE_BLOCK___"

    text_processed = re.sub(r"```.*?```", placeholder, text, flags=re.DOTALL)
    text_escaped = re.sub(f"([{re.escape(escape_chars)}])", r'\\\1', text_processed)

    for block in code_blocks:
        text_escaped = text_escaped.replace(placeholder, block, 1)

    return text_escaped


# === Gemini-прокси ===
async def query_gemini(prompt: str, file_data: str = None, mime_type: str = None, history: list = None) -> str:
    """Отправляет запрос к Gemini через прокси."""
    system_instruction_text = (
        "Отвечай всегда на русском языке, если вопрос не содержит другого указания. "
        "Если есть прикрепленный файл, внимательно его проанализируй. "
        "Если ответ содержит программный код, **обязательно форматируй его в блок с подсветкой синтаксиса** "
        "(например, ```python\\nваш_код\\n```). "
        "**Перед блоком кода** добавь краткое вводное предложение."
    )

    contents = history if history else []

    if not history:
        contents.append({
            "role": "user",
            "parts": [{"text": system_instruction_text}]
        })

    current_user_parts = []

    if file_data and mime_type:
        current_user_parts.append({
            "inlineData": {
                "mimeType": mime_type,
                "data": file_data
            }
        })

    current_user_parts.append({"text": prompt})

    contents.append({
        "role": "user",
        "parts": current_user_parts
    })

    payload = {
        "model": "gemini-2.5-flash",
        "args": {
            "contents": contents
        }
    }

    for attempt in range(MAX_RETRIES):
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(GAS_PROXY_URL, json=payload, timeout=60) as r:
                    if r.status >= 500:
                        if attempt < MAX_RETRIES - 1:
                            await asyncio.sleep(1)
                            continue
                        else:
                            r.raise_for_status()

                    r.raise_for_status()
                    data = await r.json()

                    text = (
                        data.get("candidates", [{}])[0]
                        .get("content", {})
                        .get("parts", [{}])[0]
                        .get("text", "")
                    )
                    return text or data.get("error", "Нет текста в ответе.")

        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(1)
                continue
            else:
                return f"Ошибка сетевого запроса к прокси после {MAX_RETRIES} попыток: {e}"
        except Exception as e:
            return f"Общая ошибка при запросе к Gemini: {e}"

    return "Не удалось получить ответ от модели после всех повторных попыток."


# === Утилита для загрузки файла ===
async def _download_file_as_base64(context: ContextTypes.DEFAULT_TYPE, file_id: str) -> str:
    """Загружает файл из Telegram и возвращает его содержимое в Base64."""
    try:
        file_obj = await context.bot.get_file(file_id)
        download_url = file_obj.file_path

        if not download_url:
            raise ValueError("Не удалось получить URL для скачивания файла.")

        async with aiohttp.ClientSession() as s:
            async with s.get(download_url) as r:
                r.raise_for_status()
                file_bytes = await r.read()

        return base64.b64encode(file_bytes).decode('utf-8')
    except Exception as e:
        raise Exception(f"Ошибка при загрузке или кодировании файла: {e}")


# === КОМАНДЫ БОТА ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет приветственное сообщение."""
    await update.message.reply_text(
        "👋 Привет! Я — Gemini Proxy Bot, сфокусированный на анализе текста и файлов.\n"
        "Задавай вопросы или прикрепи фото/документ (PDF, TXT) с вопросом для анализа!"
    )


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


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Очищает историю диалога для текущего чата."""
    chat_id = update.message.chat_id
    if 'history' in context.user_data and chat_id in context.user_data['history']:
        context.user_data['history'][chat_id] = []
        await update.message.reply_text("✅ История диалога была очищена. Начните новый разговор.")
    else:
        await update.message.reply_text("⚠️ История диалога уже пуста.")


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
        "Откройте Web App для удобной работы с Gemini AI:",
        reply_markup=reply_markup
    )


# === ОБРАБОТЧИКИ СООБЩЕНИЙ ===
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает текстовые сообщения и запросы в чатах/группах."""
    if not update.message or not update.message.text:
        return

    chat_id = update.message.chat_id

    if 'history' not in context.user_data:
        context.user_data['history'] = {}

    chat_history = context.user_data['history'].get(chat_id, [])

    bot_username = (await context.bot.get_me()).username.lower()
    text = update.message.text

    # В группе отвечаем только по упоминанию
    if update.message.chat.type in ("group", "supergroup"):
        if f"@{bot_username}" not in text.lower():
            return
        text = text.replace(f"@{bot_username}", "").strip()

    if not text:
        if update.message.chat.type in ("group", "supergroup"):
            await update.message.reply_text(
                "💬 Задайте свой вопрос сразу после упоминания меня!"
            )
        return

    await update.message.chat.send_action(action="TYPING")
    status_message = await update.message.reply_text("⌛ Думаю...")

    # Используем query_gemini с историей
    answer = await query_gemini(text, history=chat_history)

    # Обновляем историю
    chat_history.append({
        "role": "user",
        "parts": [{"text": text}]
    })
    chat_history.append({
        "role": "model",
        "parts": [{"text": answer}]
    })

    # Обрезаем историю
    chat_history = chat_history[-(MAX_HISTORY_MESSAGES):]
    context.user_data['history'][chat_id] = chat_history

    # Отправляем ответ
    escaped_answer = escape_markdown_v2(answer)

    try:
        await status_message.edit_text(escaped_answer, parse_mode='MarkdownV2')
    except Exception as e:
        print(f"Ошибка при edit_text (MarkdownV2): {e}")
        for chunk in [escaped_answer[i:i + 4000] for i in range(0, len(escaped_answer), 4000)]:
            try:
                await update.message.reply_text(chunk, parse_mode='MarkdownV2')
            except Exception as e_reply:
                print(f"Критическая ошибка при reply_text (MarkdownV2): {e_reply}")
                await update.message.reply_text(
                    "❌ Извините, произошла ошибка форматирования. Вот текст без форматирования:\n\n" + answer)


async def handle_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает фото, документы и их подписи с помощью Gemini."""
    if not update.message:
        return

    is_group = update.message.chat.type in ("group", "supergroup")
    bot_username = (await context.bot.get_me()).username
    user_prompt = update.message.caption or update.message.text

    if is_group:
        if not user_prompt or f"@{bot_username}" not in user_prompt:
            return
        user_prompt = user_prompt.replace(f"@{bot_username}", "").strip()

    file_id = None
    mime_type = None

    # Определяем файл
    if update.message.photo:
        largest_photo = update.message.photo[-1]
        file_id = largest_photo.file_id
        mime_type = "image/jpeg"
    elif update.message.document:
        document = update.message.document
        supported_mimes = [
            "image/jpeg",
            "image/png",
            "application/pdf",
            "text/plain",
        ]
        if document.mime_type in supported_mimes:
            file_id = document.file_id
            mime_type = document.mime_type
        else:
            await update.message.reply_text(
                f"Извините, я не могу обработать файл типа: `{document.mime_type}`. "
                f"Поддерживаются только изображения, PDF и TXT."
            )
            return
    else:
        return

    # Получаем текст запроса
    if not user_prompt:
        user_prompt = "Опиши этот файл и ответь, что на нём изображено, или что в нём содержится."

    # Начинаем процесс
    await update.message.chat.send_action(action="TYPING")
    status_message = await update.message.reply_text(f"1️⃣ Загружаю и анализирую ваш файл ({mime_type})...")

    try:
        # Загрузка файла и кодирование в base64
        base64_data = await _download_file_as_base64(context, file_id)

        # Анализ Gemini
        await update.message.chat.send_action(action="TYPING")
        await status_message.edit_text("2️⃣ Анализирую файл с помощью Gemini...")

        answer = await query_gemini(user_prompt, base64_data, mime_type, history=[])

        # Ответ
        escaped_answer = escape_markdown_v2(answer)
        await status_message.edit_text(escaped_answer, parse_mode='MarkdownV2')

    except Exception as e:
        error_msg = f"❌ Произошла ошибка при обработке файла. Подробнее: {str(e)}"
        print(f"File handling error: {e}")
        try:
            await status_message.edit_text(error_msg)
        except Exception:
            await update.message.reply_text(error_msg)


# === УСТАНОВКА КОМАНД ===
async def set_bot_commands(app):
    """Устанавливает подсказки для команд в меню бота."""
    commands = [
        BotCommand("start", "Начать работу с ботом"),
        BotCommand("help", "Показать список команд"),
        BotCommand("reset", "Очистить историю диалога"),
        BotCommand("app", "Открыть Web App"),
    ]

    await app.bot.set_my_commands(
        commands,
        scope=BotCommandScopeAllPrivateChats()
    )


# === ЗАПУСК ===
def main():
    """Основная функция запуска бота."""
    app = ApplicationBuilder().token(TOKEN).concurrent_updates(True).read_timeout(30).build()

    # === Регистрация обработчиков ===
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("reset", reset_command))
    app.add_handler(CommandHandler("app", webapp_command))

    # Обработчик для фотографий и документов
    file_handler = MessageHandler(
        filters.PHOTO | filters.Document.ALL,
        handle_files
    )
    app.add_handler(file_handler)

    # Обработчик для текстовых сообщений
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    app.post_init = set_bot_commands

    print("✅ Бот запущен. Работает в чатах и группах.")
    app.run_polling()


if __name__ == "__main__":
    main()