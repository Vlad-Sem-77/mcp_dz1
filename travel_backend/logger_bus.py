"""
Простая шина событий (pub/sub) для передачи технических логов MCP
в правую панель UI в реальном времени через WebSocket.

Поток: MCP-клиент -> log_bus.emit(...) -> подписчики (WebSocket-соединения)
получают событие и тут же отправляют его в браузер.
"""

import json
import threading
import time
from datetime import datetime, timezone
from typing import Callable


class LogBus:
    def __init__(self):
        self._subscribers: list[Callable[[dict], None]] = []
        self._lock = threading.Lock()

    def subscribe(self, callback: Callable[[dict], None]):
        with self._lock:
            self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[dict], None]):
        with self._lock:
            if callback in self._subscribers:
                self._subscribers.remove(callback)

    def emit(self, server: str, direction: str, title: str, payload: dict):
        """
        server: 'Kiwi' | 'Trivago' | 'LLM' | 'Agent'
        direction: 'outgoing' | 'incoming' | 'status' | 'error'
        title: короткое описание события
        payload: произвольные данные (запрос/ответ/ошибка)
        """
        event = {
            "timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3],
            "server": server,
            "direction": direction,
            "title": title,
            "payload": self._safe_payload(payload),
        }
        with self._lock:
            subscribers = list(self._subscribers)
        for callback in subscribers:
            try:
                callback(event)
            except Exception:
                # Не даём упасть основному потоку из-за сбоя одного подписчика
                pass

    @staticmethod
    def _safe_payload(payload: dict) -> str:
        try:
            return json.dumps(payload, ensure_ascii=False, indent=2)[:4000]
        except Exception:
            return str(payload)[:4000]


# Единственный экземпляр на процесс (singleton)
log_bus = LogBus()
