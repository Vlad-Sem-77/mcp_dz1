"""
Клиент для Trivago MCP-сервера (поиск отелей).

Официальный эндпоинт: https://mcp.trivago.com/mcp

Алгоритм двухшаговый, согласно ТЗ:
    1) trivago-search-suggestions(query=<город на английском>)
       -> получаем список вариантов, из каждого извлекаем id и ns.
    2) trivago-accommodation-search(id, ns, checkin, checkout, ...)
       -> получаем список отелей.
"""

from travel_backend.mcp_clients.base_mcp_client import BaseMCPClient, MCPError

TRIVAGO_MCP_ENDPOINT = "https://mcp.trivago.com/mcp"


class TrivagoClient:
    def __init__(self):
        self._client = BaseMCPClient(TRIVAGO_MCP_ENDPOINT, server_name="Trivago")
        self._initialized = False

    def ensure_initialized(self):
        if not self._initialized:
            self._client.initialize()
            self._initialized = True

    def search_suggestions(self, query_en: str) -> dict:
        """Шаг 1: получить варианты локаций (city/region) по названию на английском."""
        self.ensure_initialized()
        try:
            return self._client.call_tool(
                "trivago-search-suggestions",
                {"query": query_en},
            )
        except MCPError as exc:
            return {"error": str(exc)}

    def accommodation_search(
        self,
        location_id: str,
        ns: str,
        checkin: str,
        checkout: str,
        adults: int = 1,
    ) -> dict:
        """
        Шаг 2: поиск отелей по id/ns, полученным на шаге 1.
        checkin / checkout: формат YYYY-MM-DD.
        """
        self.ensure_initialized()
        try:
            return self._client.call_tool(
                "trivago-accommodation-search",
                {
                    "id": location_id,
                    "ns": ns,
                    "checkin": checkin,
                    "checkout": checkout,
                    "adults": adults,
                },
            )
        except MCPError as exc:
            return {"error": str(exc)}

    @staticmethod
    def extract_id_ns(suggestions_result: dict) -> tuple[str | None, str | None]:
        """
        Достаёт первый подходящий (id, ns) из ответа trivago-search-suggestions.
        Структура ответа MCP tool-результата обычно содержит content -> text (JSON-строка)
        либо structuredContent — пробуем оба варианта для надёжности.
        """
        if not suggestions_result:
            return None, None

        # Вариант 1: structuredContent с готовым списком
        structured = suggestions_result.get("structuredContent")
        candidates = None
        if isinstance(structured, dict):
            candidates = structured.get("suggestions") or structured.get("results") or structured.get("items")
        elif isinstance(structured, list):
            candidates = structured

        # Вариант 2: content[0].text содержит JSON-строку
        if not candidates:
            content_blocks = suggestions_result.get("content", [])
            for block in content_blocks:
                if block.get("type") == "text":
                    import json
                    try:
                        parsed = json.loads(block["text"])
                        if isinstance(parsed, list):
                            candidates = parsed
                        elif isinstance(parsed, dict):
                            candidates = parsed.get("suggestions") or parsed.get("results") or [parsed]
                    except (json.JSONDecodeError, KeyError, TypeError):
                        continue
                    if candidates:
                        break

        if not candidates:
            return None, None

        first = candidates[0]
        if not isinstance(first, dict):
            return None, None

        location_id = first.get("id") or first.get("itemId")
        ns = first.get("ns") or first.get("namespace")
        return location_id, ns

    def close(self):
        self._client.close()
