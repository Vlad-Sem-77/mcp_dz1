"""
Клиент для OpenRouter (https://openrouter.ai) — провайдера, через который
мы обращаемся к бесплатным LLM-моделям, поддерживающим tool calling
(function calling) в формате, совместимом с OpenAI Chat Completions API.
"""

import json
import httpx

from backend import config
from backend.logger_bus import log_bus


class OpenRouterClient:
    def __init__(self):
        self.api_key = config.OPENROUTER_API_KEY
        self.model = config.OPENROUTER_MODEL
        self._client = httpx.Client(timeout=60.0)

    def chat(self, messages: list, tools: list | None = None) -> dict:
        """
        Отправляет запрос в OpenRouter Chat Completions API.
        Возвращает message-объект ответа модели (dict), как в OpenAI API:
        {"role": "assistant", "content": "...", "tool_calls": [...]}
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/ai-travel-agent",
            "X-Title": "AI Travel Agent (MCP)",
        }

        body: dict = {
            "model": self.model,
            "messages": messages,
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"

        log_bus.emit(
            server="LLM",
            direction="outgoing",
            title=f"-> OpenRouter ({self.model})",
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
                title="Сетевая ошибка при обращении к OpenRouter",
                payload={"error": str(exc)},
            )
            raise

        if response.status_code >= 400:
            log_bus.emit(
                server="LLM",
                direction="error",
                title=f"OpenRouter HTTP {response.status_code}",
                payload={"body": response.text[:1000]},
            )
            raise RuntimeError(f"OpenRouter API error {response.status_code}: {response.text[:500]}")

        data = response.json()

        if "error" in data:
            log_bus.emit(
                server="LLM",
                direction="error",
                title="OpenRouter вернул ошибку",
                payload=data["error"],
            )
            raise RuntimeError(f"OpenRouter error: {data['error']}")

        message = data["choices"][0]["message"]

        log_bus.emit(
            server="LLM",
            direction="incoming",
            title="<- ответ модели",
            payload={
                "content_preview": (message.get("content") or "")[:300],
                "tool_calls": [
                    tc.get("function", {}).get("name") for tc in (message.get("tool_calls") or [])
                ],
            },
        )

        return message

    def close(self):
        self._client.close()
