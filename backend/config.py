"""Загрузка конфигурации приложения из переменных окружения (.env)."""

import os
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "google/gemini-2.0-flash-exp:free")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-secret-key-change-me")
PORT = int(os.getenv("PORT", "5000"))

if not OPENROUTER_API_KEY:
    print(
        "[ВНИМАНИЕ] OPENROUTER_API_KEY не найден в переменных окружения. "
        "Создайте файл .env на основе .env.example и укажите свой ключ."
    )
