"""Загрузка конфигурации приложения из переменных окружения (.env)."""

import os
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

# Авто-маршрутизатор бесплатных моделей (OpenRouter сам выбирает доступную)
OPENROUTER_FREE_FALLBACKS = [
    "openrouter/free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "meta-llama/llama-3.2-3b-instruct:free",
    "openai/gpt-oss-20b:free",
    "qwen/qwen3-coder:free",
    "google/gemini-2.0-flash-exp:free",
]

FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-secret-key-change-me")
PORT = int(os.getenv("PORT", "5000"))

if not OPENROUTER_API_KEY:
    print(
        "[ВНИМАНИЕ] OPENROUTER_API_KEY не найден в переменных окружения. "
        "Создайте файл .env на основе .env.example и укажите свой ключ."
    )
