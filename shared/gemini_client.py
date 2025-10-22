import os
import aiohttp
import asyncio
from typing import List, Dict, Optional

MAX_RETRIES = 3
GAS_PROXY_URL = os.getenv("GAS_PROXY_URL")


class GeminiClient:
    def __init__(self):
        self.gas_url = GAS_PROXY_URL

    async def query_gemini(self, prompt: str, file_data: str = None,
                           mime_type: str = None, history: List[Dict] = None) -> str:
        """Общая функция для запросов к Gemini (из вашего бота)"""
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
                    async with s.post(self.gas_url, json=payload, timeout=60) as r:
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
                    return f"Ошибка сетевого запроса: {e}"
            except Exception as e:
                return f"Общая ошибка: {e}"

        return "Не удалось получить ответ после всех попыток."


gemini_client = GeminiClient()