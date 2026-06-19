"""
Оркестрация AI-агента: системный промпт, описание инструментов (tools)
для LLM в формате OpenAI function calling, и цикл обработки ответа модели
(в т.ч. множественные шаги tool calling, например для Trivago: сначала
suggestions, потом accommodation-search).
"""

import json
from datetime import datetime

from travel_backend.llm_client import OpenRouterClient
from travel_backend.mcp_clients.kiwi_client import KiwiClient
from travel_backend.mcp_clients.trivago_client import TrivagoClient
from travel_backend.date_utils import parse_relative_date, next_weekend, next_weekday, to_kiwi_format, to_iso_date
from travel_backend.logger_bus import log_bus


SYSTEM_PROMPT = """Ты — профессиональный AI-агент для планирования путешествий. Твоя задача — помогать пользователю находить авиабилеты и отели, используя предоставленные тебе инструменты (tools).

Правила:
1. Всегда отвечай пользователю на русском языке.
2. Перед поиском отелей (Trivago) или билетов (Kiwi) переводи названия городов с русского на английский самостоятельно (например: "Вена" -> "Vienna", "Прага" -> "Prague", "Барселона" -> "Barcelona") — передавай в инструменты только английские названия городов.
3. Если в запросе есть относительная дата ("следующая пятница", "на выходные", "через 3 дня", "на 3 дня") — используй инструмент resolve_date, чтобы получить точную дату, прежде чем вызывать поиск билетов или отелей. Сегодняшняя дата будет указана в начале диалога.
4. Для Kiwi (search_flights) даты передавай в формате dd/mm/yyyy. Помни: Kiwi НЕ поддерживает аэропорты России — если пользователь просит рейс из/в город РФ, вежливо объясни это ограничение и не вызывай инструмент.
5. Для Trivago (search_hotels) передавай английское название города и даты заезда/выезда в формате YYYY-MM-DD.
6. Если пользователь просит "поездку целиком" — последовательно вызови и search_flights (туда-обратно), и search_hotels на эти же даты.
7. Если в запросе не указаны даты, а они необходимы для поиска — сначала уточни их у пользователя, не вызывая инструменты.
8. При ошибках инструментов вежливо сообщи об этом пользователю и предложи альтернативы (например, проверить названия городов или попробовать другие даты).
9. Когда получишь результаты от инструментов, перескажи их пользователю кратко и понятно на русском языке: основные варианты, цены, время в пути / звёздность, не вываливай сырой JSON.
"""

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "resolve_date",
            "description": (
                "Преобразует относительное упоминание даты на русском языке "
                "(например 'следующая пятница', 'на выходные', 'через 3 дня') "
                "в точную календарную дату. Используй это ПЕРЕД вызовом поиска "
                "билетов или отелей, если пользователь не назвал точную дату."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "phrase": {
                        "type": "string",
                        "description": "Фраза с относительной датой на русском, например 'следующая пятница' или 'через 3 дня'",
                    }
                },
                "required": ["phrase"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_flights",
            "description": (
                "Ищет авиабилеты через Kiwi MCP. Города должны быть на английском языке. "
                "Даты в формате dd/mm/yyyy. ВАЖНО: Kiwi не поддерживает аэропорты России — "
                "не вызывай этот инструмент для рейсов из/в города РФ."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "origin": {"type": "string", "description": "Город или аэропорт отправления, на английском, например 'Berlin'"},
                    "destination": {"type": "string", "description": "Город или аэропорт прибытия, на английском, например 'Rome'"},
                    "departure_date": {"type": "string", "description": "Дата вылета в формате dd/mm/yyyy"},
                    "return_date": {"type": "string", "description": "Дата обратного вылета в формате dd/mm/yyyy (если поездка туда-обратно)"},
                    "adults": {"type": "integer", "description": "Количество взрослых пассажиров", "default": 1},
                },
                "required": ["origin", "destination", "departure_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_hotels",
            "description": (
                "Ищет отели через Trivago MCP. Город должен быть на английском. "
                "Даты заезда/выезда в формате YYYY-MM-DD."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "Город на английском, например 'Prague'"},
                    "checkin": {"type": "string", "description": "Дата заезда в формате YYYY-MM-DD"},
                    "checkout": {"type": "string", "description": "Дата выезда в формате YYYY-MM-DD"},
                    "adults": {"type": "integer", "description": "Количество взрослых гостей", "default": 1},
                },
                "required": ["city", "checkin", "checkout"],
            },
        },
    },
]


class TravelAgent:
    """
    Держит в себе клиентов к MCP-серверам и LLM, обрабатывает одно
    сообщение пользователя за раз (с собственной историей диалога на сессию).
    """

    def __init__(self):
        self.llm = OpenRouterClient()
        self.kiwi = KiwiClient()
        self.trivago = TrivagoClient()

    def _execute_tool(self, name: str, arguments: dict) -> dict:
        if name == "resolve_date":
            return self._resolve_date(arguments.get("phrase", ""))

        if name == "search_flights":
            return self.kiwi.search_flight(
                origin=arguments.get("origin", ""),
                destination=arguments.get("destination", ""),
                departure_date=arguments.get("departure_date", ""),
                return_date=arguments.get("return_date"),
                adults=arguments.get("adults", 1),
            )

        if name == "search_hotels":
            return self._search_hotels(
                city=arguments.get("city", ""),
                checkin=arguments.get("checkin", ""),
                checkout=arguments.get("checkout", ""),
                adults=arguments.get("adults", 1),
            )

        return {"error": f"Неизвестный инструмент: {name}"}

    def _resolve_date(self, phrase: str) -> dict:
        now = datetime.now()
        phrase_lower = phrase.lower()

        if "выходн" in phrase_lower:
            saturday, sunday = next_weekend(now)
            return {
                "type": "weekend",
                "checkin": to_iso_date(saturday),
                "checkout": to_iso_date(sunday),
                "kiwi_departure": to_kiwi_format(saturday),
                "kiwi_return": to_kiwi_format(sunday),
            }

        for weekday_name in ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]:
            if weekday_name in phrase_lower:
                resolved = next_weekday(weekday_name, now)
                if resolved:
                    return {
                        "type": "weekday",
                        "date_iso": to_iso_date(resolved),
                        "date_kiwi": to_kiwi_format(resolved),
                    }

        parsed = parse_relative_date(phrase, base_date=now)
        if parsed:
            return {
                "type": "parsed",
                "date_iso": to_iso_date(parsed),
                "date_kiwi": to_kiwi_format(parsed),
            }

        return {"error": f"Не удалось распознать дату из фразы: '{phrase}'"}

    def _search_hotels(self, city: str, checkin: str, checkout: str, adults: int) -> dict:
        return self.trivago.search_hotels(
            city=city,
            checkin=checkin,
            checkout=checkout,
            adults=adults,
        )

    def handle_message(self, conversation_history: list, user_message: str) -> tuple[str, list]:
        """
        conversation_history: список сообщений в формате OpenAI messages
                               (без системного — он добавляется здесь).
        Возвращает (текст_ответа_ассистента, обновлённая_история).
        """
        today_str = datetime.now().strftime("%d.%m.%Y (%A)")

        messages = [{"role": "system", "content": SYSTEM_PROMPT + f"\n\nСегодняшняя дата: {today_str}."}]
        messages.extend(conversation_history)
        messages.append({"role": "user", "content": user_message})

        log_bus.emit(server="Agent", direction="status", title="Новое сообщение от пользователя", payload={"text": user_message})

        max_tool_rounds = 6
        for _ in range(max_tool_rounds):
            assistant_message = self.llm.chat(messages, tools=TOOLS_SCHEMA)
            messages.append(assistant_message)

            tool_calls = assistant_message.get("tool_calls")
            if not tool_calls:
                final_text = assistant_message.get("content") or ""
                updated_history = messages[1:]  # без системного сообщения
                return final_text, updated_history

            for tool_call in tool_calls:
                function_info = tool_call.get("function", {})
                tool_name = function_info.get("name")
                try:
                    tool_args = json.loads(function_info.get("arguments") or "{}")
                except json.JSONDecodeError:
                    tool_args = {}

                log_bus.emit(
                    server="Agent",
                    direction="status",
                    title=f"LLM запросила инструмент: {tool_name}",
                    payload=tool_args,
                )

                tool_result = self._execute_tool(tool_name, tool_args)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.get("id"),
                    "name": tool_name,
                    "content": json.dumps(tool_result, ensure_ascii=False)[:6000],
                })

        # Если за max_tool_rounds не пришёл финальный текстовый ответ
        fallback_text = "Извините, не получилось завершить обработку запроса. Попробуйте переформулировать или уточнить детали."
        return fallback_text, messages[1:]

    def close(self):
        self.llm.close()
        self.kiwi.close()
        self.trivago.close()
