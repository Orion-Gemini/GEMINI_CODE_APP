from flask import Flask, request, jsonify
from flask_cors import CORS
import base64
import os
import asyncio
import aiohttp

app = Flask(__name__)
CORS(app)

# Простая in-memory база (для продакшена используйте Redis)
user_sessions = {}


class GeminiClient:
    def __init__(self):
        self.gas_url = os.getenv("GAS_PROXY_URL")

    async def query_gemini(self, prompt: str, file_data: str = None,
                           mime_type: str = None, history: list = None) -> str:
        """Адаптированная версия из вашего бота"""
        system_instruction_text = (
            "Отвечай всегда на русском языке, если вопрос не содержит другого указания. "
            "Если есть прикрепленный файл, внимательно его проанализируй. "
            "Если ответ содержит программный код, **обязательно форматируй его в блок с подсветкой синтаксиса**."
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

        for attempt in range(3):
            try:
                async with aiohttp.ClientSession() as s:
                    async with s.post(self.gas_url, json=payload, timeout=60) as r:
                        if r.status >= 500:
                            if attempt < 2:
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

            except Exception as e:
                if attempt < 2:
                    await asyncio.sleep(1)
                    continue
                else:
                    return f"Ошибка: {e}"

        return "Не удалось получить ответ."


gemini_client = GeminiClient()


@app.route('/api/chat', methods=['POST'])
def chat():
    """Обработка текстовых сообщений"""
    data = request.json
    user_id = data.get('user_id')
    message = data.get('message')

    if not user_id or not message:
        return jsonify({'error': 'Missing user_id or message'}), 400

    history = user_sessions.get(user_id, [])

    # Запускаем асинхронную функцию
    response = asyncio.run(gemini_client.query_gemini(message, history=history))

    # Обновляем историю
    history.append({"role": "user", "parts": [{"text": message}]})
    history.append({"role": "model", "parts": [{"text": response}]})
    user_sessions[user_id] = history[-4:]

    return jsonify({'response': response})


@app.route('/api/upload', methods=['POST'])
def upload_file():
    """Обработка загрузки файлов"""
    try:
        data = request.json
        user_id = data.get('user_id')
        file_data = data.get('file_data')
        mime_type = data.get('mime_type')
        prompt = data.get('prompt', 'Опиши этот файл')

        if not all([user_id, file_data, mime_type]):
            return jsonify({'error': 'Missing required fields'}), 400

        response = asyncio.run(gemini_client.query_gemini(
            prompt,
            file_data=file_data,
            mime_type=mime_type
        ))

        return jsonify({'response': response})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/reset', methods=['POST'])
def reset_history():
    """Сброс истории"""
    data = request.json
    user_id = data.get('user_id')

    if user_id in user_sessions:
        user_sessions[user_id] = []

    return jsonify({'success': True})


@app.route('/health', methods=['GET'])
def health():
    """Health check для Amvera"""
    return jsonify({'status': 'ok'})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)