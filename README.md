# AI Travel Agent — MCP

Учебный проект: чат-агент для поиска авиабилетов и отелей через реальные MCP-серверы Kiwi.com и Trivago.

## Стек

| Компонент | Технология |
|---|---|
| Backend | Python 3.12 · Flask · flask-sock |
| LLM | OpenRouter API (google/gemini-2.0-flash-exp или другая с tool calling) |
| Билеты | [Kiwi.com MCP](https://mcp.kiwi.com) — Streamable HTTP, без авторизации |
| Отели | [Trivago MCP](https://mcp.trivago.com/mcp) — Streamable HTTP, без авторизации |
| Frontend | HTML · CSS · Vanilla JS · WebSocket |

## Как работает

```
Пользователь → Flask (POST /api/chat) → TravelAgent
  → OpenRouter LLM (tool calling)
      → search_flights  → KiwiClient   → MCP initialize → tools/call search-flight
      → search_hotels   → TrivagoClient → MCP initialize → trivago-search-suggestions
                                                         → trivago-accommodation-search
  → Ответ на русском пользователю
  
Параллельно: LogBus → WebSocket (/ws/logs) → правая панель UI (real-time)
```

## Локальный запуск

```bash
# 1. Клонируй репозиторий
git clone <repo-url>
cd ai-travel-agent

# 2. Установи зависимости
pip install -r requirements.txt

# 3. Скопируй .env.example в .env и вставь ключ OpenRouter
cp .env.example .env
# отредактируй .env: вставь свой OPENROUTER_API_KEY

# 4. Запуск
python app.py
# → http://localhost:5000
```

## Деплой в Replit

1. **Создай** новый Replit → "Import from GitHub" → вставь URL репозитория.
2. Перейди в **Secrets** (замок слева) и добавь секрет:
   - ключ: `OPENROUTER_API_KEY`
   - значение: твой ключ
3. В файле `.replit` (создастся автоматически или вручную) убедись:
   ```toml
   run = "python app.py"
   ```
4. Нажми **Run** — Replit сам выполнит `pip install -r requirements.txt` если настроен packager, или добавь в `.replit`:
   ```toml
   [nix]
   channel = "stable-24_05"
   
   [deployment]
   run = ["sh", "-c", "pip install -r requirements.txt && python app.py"]
   ```
5. Приложение откроется во встроенном браузере Replit.

## Структура проекта

```
ai-travel-agent/
├── app.py                       # Flask + WebSocket, точка входа
├── requirements.txt
├── .env.example                 # шаблон переменных окружения
├── .gitignore
├── backend/
│   ├── config.py                # загрузка .env
│   ├── llm_client.py            # клиент OpenRouter
│   ├── agent.py                 # агент: system prompt + tool calling loop
│   ├── date_utils.py            # парсинг относительных дат на русском
│   ├── logger_bus.py            # шина событий для WebSocket логов
│   └── mcp_clients/
│       ├── base_mcp_client.py   # базовый MCP JSON-RPC клиент
│       ├── kiwi_client.py       # Kiwi.com (search-flight)
│       └── trivago_client.py    # Trivago (suggestions + accommodation-search)
└── frontend/
    ├── templates/index.html
    └── static/
        ├── style.css
        └── app.js
```

## Важные ограничения

- **Kiwi.com не поддерживает аэропорты России** — агент знает об этом через system prompt.
- Trivago MCP использует двухшаговый поиск (suggestions → accommodation) — реализован автоматически внутри `search_hotels`.
- Для Kiwi даты передаются в формате `dd/mm/yyyy`, для Trivago — `YYYY-MM-DD`.

## Примеры запросов

- «Найди билет из Berlin в Rome на следующую пятницу»
- «Подбери отель в Prague на выходные, 2 взрослых»
- «Спланируй поездку в Barcelona: вылет из Vienna 15 июля, назад 22 июля»
