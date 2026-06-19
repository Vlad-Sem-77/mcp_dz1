"""
Клиент для OpenRouter (https://openrouter.ai) — провайдера, через который
мы обращаемся к бесплатным LLM-моделям, поддерживающим tool calling
(function calling) в формате, совместимом с OpenAI Chat Completions API.
"""

import json
import httpx

from travel_backend import config
from travel_backend.logger_bus import log_bus


class OpenRouterClient:
    def __init__(self):
        self.api_key = config.OPENROUTER_API_KEY
        self._client = httpx.Client(timeout=60.0)

    def chat(self, messages: list, tools: list | None = None) -> dict:
        """
        Отправляет запрос в OpenRouter Chat Completions API.
        Возвращает message-объект ответа модели (dict), как в OpenAI API:
        {"role": "assistant", "content": "...", "tool_calls": [...]}

        При ошибке (404, 429, 500) автоматически перебирает
        OPENROUTER_FREE_FALLBACKS, пока одна не ответит.
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/ai-travel-agent",
            "X-Title": "AI Travel Agent (MCP)",
        }

        models_to_try = config.OPENROUTER_FREE_FALLBACKS
        last_error = ""

        for model in models_to_try:
            body: dict = {
                "model": model,
                "messages": messages,
            }
            if tools:
                body["tools"] = tools
                body["tool_choice"] = "auto"

            log_bus.emit(
                server="LLM",
                direction="outgoing",
                title=f"-> OpenRouter ({model})",
                payload={"messages_count": len(messages), "tools_count": len(tools or [])},
            )

            try:
                response = self._client.post(
                    config.OPENROUTER_BASE_URL,
                    headers=headers,
                    json=body,
                )
            except httpx.RequestError as exc:
                log_bus.emit(
                    server="LLM",
                    direction="error",
                    title=f"Сеть — {model}",
                    payload={"error": str(exc)},
                )
                last_error = str(exc)
                continue

            if response.status_code == 429:
                log_bus.emit(
                    server="LLM",
                    direction="error",
                    title=f"429 — {model}",
                    payload={"body": "Too Many Requests"},
                )
                last_error = f"429 Too Many Requests ({model})"
                continue

            if response.status_code >= 400:
                text = response.text[:500]
                log_bus.emit(
                    server="LLM",
                    direction="error",
                    title=f"OpenRouter HTTP {response.status_code} — {model}",
                    payload={"body": text[:1000]},
                )
                last_error = f"OpenRouter {response.status_code}: {text}"
                # 404 и 500 — перебираем, другое — вылетаем
                if response.status_code in (404, 500, 502, 503, 504):
                    continue
                raise RuntimeError(f"OpenRouter API error {response.status_code}: {text}")

            data = response.json()

            if "error" in data:
                err_msg = data.get("error", "")
                log_bus.emit(
                    server="LLM",
                    direction="error",
                    title=f"OpenRouter error — {model}",
                    payload={"error": str(err_msg)[:500]},
                )
                last_error = str(err_msg)
                # No endpoints found и т.п. — перебираем
                if "No endpoints found" in str(err_msg) or "not available" in str(err_msg).lower():
                    continue
                raise RuntimeError(f"OpenRouter error: {err_msg}")

            if not data.get("choices"):
                last_error = f"Empty choices from {model}"
                continue

            message = data["choices"][0]["message"]

            log_bus.emit(
                server="LLM",
                direction="incoming",
                title=f"<- ответ ({model})",
                payload={
                    "content_preview": (message.get("content") or "")[:300],
                    "tool_calls": [
                        tc.get("function", {}).get("name") for tc in (message.get("tool_calls") or [])
                    ],
                },
            )

            return message

        raise RuntimeError(f"Нет доступных бесплатных моделей OpenRouter. Последняя ошибка: {last_error}")

    def close(self):
        self._client.close()
