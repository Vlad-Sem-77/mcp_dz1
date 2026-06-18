"""
Клиент для Kiwi.com MCP-сервера (поиск авиабилетов).

Официальный эндпоинт: https://mcp.kiwi.com
Сервер транспортного типа Streamable HTTP, без аутентификации.
Экспонирует единственный инструмент: search-flight.

Важно: Kiwi не поддерживает аэропорты Российской Федерации —
агент обязан знать об этом ограничении и не пытаться искать рейсы
из/в РФ (это контролируется на уровне system prompt и agent.py).
"""

from backend.mcp_clients.base_mcp_client import BaseMCPClient, MCPError

KIWI_MCP_ENDPOINT = "https://mcp.kiwi.com"


class KiwiClient:
    def __init__(self):
        self._client = BaseMCPClient(KIWI_MCP_ENDPOINT, server_name="Kiwi")
        self._initialized = False

    def ensure_initialized(self):
        if not self._initialized:
            self._client.initialize()
            self._initialized = True

    def search_flight(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        return_date: str | None = None,
        adults: int = 1,
    ) -> dict:
        """
        origin / destination: название города или IATA-код на английском языке.
        departure_date / return_date: строго в формате dd/mm/yyyy.
        """
        self.ensure_initialized()

        arguments = {
            "flyFrom": origin,
            "flyTo": destination,
            "departureDate": departure_date,
            "adults": adults,
        }
        if return_date:
            arguments["returnDate"] = return_date

        try:
            return self._client.call_tool("search-flight", arguments)
        except MCPError as exc:
            return {"error": str(exc)}

    def close(self):
        self._client.close()
