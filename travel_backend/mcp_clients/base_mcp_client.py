"""
Базовый клиент для работы с удалёнными MCP-серверами по протоколу
"Streamable HTTP" (JSON-RPC 2.0 поверх HTTP POST, с поддержкой SSE-ответов).

Реализует минимально необходимый набор методов MCP:
    - initialize            -> получение mcp-session-id
    - notifications/initialized
    - tools/list             (опционально, для отладки)
    - tools/call

Документация протокола: https://modelcontextprotocol.io
"""

import json
import uuid
import httpx
from typing import Any, Optional

from travel_backend.logger_bus import log_bus


class MCPError(Exception):
    """Ошибка взаимодействия с MCP-сервером."""
    pass


class BaseMCPClient:
    """
    Универсальный клиент для удалённого MCP-сервера, работающего по
    Streamable HTTP транспорту (POST на единый /mcp эндпоинт,
    Content-Type: application/json, ответы могут быть как обычным JSON,
    так и text/event-stream).
    """

    def __init__(self, endpoint: str, server_name: str, timeout: float = 30.0):
        self.endpoint = endpoint
        self.server_name = server_name  # для логов, например "Kiwi" / "Trivago"
        self.timeout = timeout
        self.session_id: Optional[str] = None
        self._request_id = 0
        self._client = httpx.Client(timeout=timeout)

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _base_headers(self) -> dict:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.session_id:
            headers["mcp-session-id"] = self.session_id
        return headers

    def _parse_response(self, response: httpx.Response) -> dict:
        """
        Streamable HTTP может вернуть либо чистый JSON, либо
        text/event-stream с событиями вида:
            event: message
            data: {...}
        Здесь разбираем оба варианта.
        """
        content_type = response.headers.get("content-type", "")

        if "text/event-stream" in content_type:
            data_payload = None
            for raw_line in response.text.splitlines():
                line = raw_line.strip()
                if line.startswith("data:"):
                    chunk = line[len("data:"):].strip()
                    if not chunk:
                        continue
                    try:
                        data_payload = json.loads(chunk)
                    except json.JSONDecodeError:
                        continue
            if data_payload is None:
                raise MCPError(
                    f"[{self.server_name}] Не удалось разобрать SSE-ответ: {response.text[:500]}"
                )
            return data_payload

        try:
            return response.json()
        except json.JSONDecodeError as exc:
            raise MCPError(
                f"[{self.server_name}] Невалидный JSON в ответе: {response.text[:500]}"
            ) from exc

    def _send_rpc(self, method: str, params: Optional[dict] = None, is_notification: bool = False) -> Optional[dict]:
        """Отправляет один JSON-RPC запрос/уведомление на MCP-сервер."""
        payload: dict = {
            "jsonrpc": "2.0",
            "method": method,
        }
        if params is not None:
            payload["params"] = params
        if not is_notification:
            payload["id"] = self._next_id()

        log_bus.emit(
            server=self.server_name,
            direction="outgoing",
            title=f"-> {method}",
            payload=payload,
        )

        try:
            response = self._client.post(
                self.endpoint,
                headers=self._base_headers(),
                json=payload,
            )
        except httpx.RequestError as exc:
            log_bus.emit(
                server=self.server_name,
                direction="error",
                title="Сетевая ошибка",
                payload={"error": str(exc), "method": method},
            )
            raise MCPError(f"[{self.server_name}] Сетевая ошибка при вызове {method}: {exc}") from exc

        # Сохраняем mcp-session-id, если сервер его прислал (обычно при initialize)
        returned_session_id = response.headers.get("mcp-session-id")
        if returned_session_id:
            self.session_id = returned_session_id

        if response.status_code >= 400:
            log_bus.emit(
                server=self.server_name,
                direction="error",
                title=f"HTTP {response.status_code}",
                payload={"body": response.text[:1000], "method": method},
            )
            raise MCPError(
                f"[{self.server_name}] HTTP {response.status_code} при вызове {method}: {response.text[:300]}"
            )

        if is_notification:
            log_bus.emit(
                server=self.server_name,
                direction="incoming",
                title=f"<- {method} (notification ok, status {response.status_code})",
                payload={},
            )
            return None

        result = self._parse_response(response)

        log_bus.emit(
            server=self.server_name,
            direction="incoming",
            title=f"<- ответ на {method}",
            payload=result,
        )

        if "error" in result:
            raise MCPError(f"[{self.server_name}] MCP error на {method}: {result['error']}")

        return result

    def initialize(self) -> None:
        """
        Инициализирует MCP-сессию: выполняет 'initialize',
        сохраняет mcp-session-id и отправляет уведомление 'notifications/initialized'.
        """
        log_bus.emit(
            server=self.server_name,
            direction="status",
            title="Инициализация сессии...",
            payload={},
        )

        result = self._send_rpc(
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {
                    "name": "ai-travel-agent",
                    "version": "1.0.0",
                },
            },
        )

        if self.session_id:
            log_bus.emit(
                server=self.server_name,
                direction="status",
                title="Сессия установлена",
                payload={"mcp-session-id": self.session_id},
            )
        else:
            log_bus.emit(
                server=self.server_name,
                direction="status",
                title="Сервер не вернул mcp-session-id (возможно stateless-режим)",
                payload={},
            )

        # Уведомляем сервер, что клиент готов (часть handshake протокола MCP)
        try:
            self._send_rpc("notifications/initialized", {}, is_notification=True)
        except MCPError:
            # Некоторые серверы не требуют этого шага строго — не фатально
            pass

        return result

    def list_tools(self) -> list:
        result = self._send_rpc("tools/list", {})
        return (result or {}).get("result", {}).get("tools", [])

    def call_tool(self, tool_name: str, arguments: dict) -> dict:
        """Вызывает конкретный инструмент (tool) на MCP-сервере."""
        log_bus.emit(
            server=self.server_name,
            direction="status",
            title=f"Вызов инструмента: {tool_name}",
            payload=arguments,
        )
        result = self._send_rpc(
            "tools/call",
            {
                "name": tool_name,
                "arguments": arguments,
            },
        )
        return (result or {}).get("result", {})

    def close(self):
        try:
            self._client.close()
        except Exception:
            pass
