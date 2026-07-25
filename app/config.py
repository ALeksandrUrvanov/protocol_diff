# -*- coding: utf-8 -*-
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(_env_path)
except ImportError:
    pass

def _env(key: str, default=None, cast=lambda x: x):
    value = os.getenv(key)
    if value is None:
        return default
    try:
        return cast(value)
    except (ValueError, TypeError):
        return default


# Порт приложения
DEFAULT_PORT = _env("PORT", 8087, int)

# Лимит размера файла (байты): 200 MB
MAX_FILE_SIZE_MB = 200
MAX_FILE_SIZE = MAX_FILE_SIZE_MB * 1024 * 1024

# Допустимые расширения для загрузки договоров
ALLOWED_EXTENSIONS = {
    ".png", ".jpg", ".jpeg",
    ".tiff", ".tif", ".bmp",
    ".pdf", ".docx",
}
# OCR API (Docker). На том же хосте: общая сеть и OCR_BASE_URL=http://ocr_qwen3vl:8088
OCR_BASE_URL = _env("OCR_BASE_URL", "http://localhost:8088")
OCR_POLL_INTERVAL = _env("OCR_POLL_INTERVAL", 2.0, float)
OCR_MAX_WAIT_SEC = _env("OCR_MAX_WAIT_SEC", 3000, int)
# Режим OCR: full_text — полный текст постранично
OCR_MODE = _env("OCR_MODE", "full_text")
OCR_TEMPERATURE = _env("OCR_TEMPERATURE", 0.1, float)
OCR_PROMPT = _env(
    "OCR_PROMPT",
    (
        "Прочитай весь текст на этом изображении документа дословно и полностью. "
        "Сохраняй структуру: заголовки, абзацы, нумерацию, списки. "
        "Таблицы передавай построчно, колонки разделяй символом |. "
        "Не пропускай строки, не сокращай и не перефразируй текст. "
        "Верни только текст без пояснений и комментариев."
    ),
)

# Директории
BASE_DIR = Path(__file__).resolve().parent.parent
PROMPTS_DIR = BASE_DIR / "prompts"
FRONTEND_STATIC_DIR = BASE_DIR / "frontend" / "static"
FRONTEND_TEMPLATES_DIR = BASE_DIR / "frontend" / "templates"
CACHE_DIR = BASE_DIR / "cache"
os.makedirs(CACHE_DIR, exist_ok=True)

# Плейсхолдер в промптах для подстановки текста договора
CONTRACT_PLACEHOLDER = "{{СЮДА_ВСТАВИТЬ_ВЕСЬ_ТЕКСТ_ДОГОВОРА}}"

# OpenRouter API (единым текстом, без чанков)
OPENROUTER_BASE_URL = _env("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_MODEL = _env("OPENROUTER_MODEL", "anthropic/claude-sonnet-4.5")
OPENROUTER_API_KEY = _env("OPENROUTER_API_KEY", "")
OPENROUTER_TIMEOUT = _env("OPENROUTER_TIMEOUT", 300.0, float)
OPENROUTER_TEMPERATURE = _env("OPENROUTER_TEMPERATURE", 0.3, float)  # Низкая температура для стабильности (0.0-1.0)
# Опционально: для ранжинга на openrouter.ai
OPENROUTER_HTTP_REFERER = _env("OPENROUTER_HTTP_REFERER", "")
OPENROUTER_X_TITLE = _env("OPENROUTER_X_TITLE", "")

# Список служб (ключ = имя файла промпта без .md, название для UI)
SERVICES = [
    {"id": "heat_supply", "title": "Теплоснабжение"},
    {"id": "water_supply", "title": "Водоснабжение и водоотведение"},
    {"id": "electricity_supply", "title": "Электроснабжение"},
    {"id": "gas_supply", "title": "Поставка газа"},
    {"id": "waste_management", "title": "Обращение с ТКО"},
    {"id": "content_and_repair", "title": "Содержание и ремонт"},
]
