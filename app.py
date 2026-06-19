"""
Точка входа приложения. Flask отдаёт фронтенд и обрабатывает чат через
обычный HTTP POST (/api/chat). Параллельно поднят WebSocket-эндпоинт
(/ws/logs), который в реальном времени стримит технические логи работы
MCP-серверов и LLM в правую панель UI.

Запуск:
    python app.py
"""

import json
import uuid
import threading

from flask import Flask, request, jsonify, render_template, session
from flask_sock import Sock

from travel_backend import config
from travel_backend.agent import TravelAgent
from travel_backend.logger_bus import log_bus

app = Flask(
    __name__,
    template_folder="frontend/templates",
    static_folder="frontend/static",
)
app.secret_key = config.FLASK_SECRET_KEY
sock = Sock(app)

# Храним по одному экземпляру агента (и истории диалога) на сессию пользователя.
# Для учебного/демо-проекта этого достаточно (in-memory, без БД).
_agents_by_session: dict[str, TravelAgent] = {}
_history_by_session: dict[str, list] = {}
_lock = threading.Lock()


def get_or_create_session_id() -> str:
    if "session_id" not in session:
        session["session_id"] = str(uuid.uuid4())
    return session["session_id"]


def get_agent(session_id: str) -> TravelAgent:
    with _lock:
        if session_id not in _agents_by_session:
            _agents_by_session[session_id] = TravelAgent()
            _history_by_session[session_id] = []
        return _agents_by_session[session_id]


@app.route("/")
def index():
    get_or_create_session_id()
    return render_template("index.html")


@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(force=True) or {}
    user_message = (data.get("message") or "").strip()

    if not user_message:
        return jsonify({"error": "Пустое сообщение"}), 400

    session_id = get_or_create_session_id()
    agent = get_agent(session_id)
    history = _history_by_session[session_id]

    try:
        reply_text, updated_history = agent.handle_message(history, user_message)
        _history_by_session[session_id] = updated_history
        return jsonify({"reply": reply_text})
    except Exception as exc:
        log_bus.emit(server="Agent", direction="error", title="Необработанная ошибка", payload={"error": str(exc)})
        return jsonify({"error": f"Произошла ошибка при обработке запроса: {exc}"}), 500


@app.route("/api/reset", methods=["POST"])
def reset():
    session_id = get_or_create_session_id()
    with _lock:
        if session_id in _agents_by_session:
            _agents_by_session[session_id].close()
            del _agents_by_session[session_id]
        _history_by_session[session_id] = []
    return jsonify({"status": "ok"})


@sock.route("/ws/logs")
def ws_logs(ws):
    """
    WebSocket-эндпоинт для правой панели логов.
    Каждое новое событие из log_bus тут же пересылается клиенту в виде JSON.
    """
    event_queue: list[dict] = []
    new_event = threading.Event()

    def on_event(event: dict):
        event_queue.append(event)
        new_event.set()

    log_bus.subscribe(on_event)
    try:
        ws.send(json.dumps({"type": "connected", "message": "Соединение с логами установлено"}))
        while True:
            new_event.wait(timeout=30)
            new_event.clear()
            while event_queue:
                event = event_queue.pop(0)
                ws.send(json.dumps(event, ensure_ascii=False))
    except Exception:
        pass
    finally:
        log_bus.unsubscribe(on_event)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=config.PORT, debug=True)
