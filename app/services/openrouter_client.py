# -*- coding: utf-8 -*-
"""
Сервис OpenRouter API для анализа договора по промпту.
Единым текстом, без разбиения на чанки (по образцу conference_analysis openrouter_service.py).
"""
import logging
import re
import asyncio
from openai import OpenAI

from ..config import (
    OPENROUTER_BASE_URL,
    OPENROUTER_MODEL,
    OPENROUTER_API_KEY,
    OPENROUTER_TIMEOUT,
    OPENROUTER_TEMPERATURE,
    OPENROUTER_HTTP_REFERER,
    OPENROUTER_X_TITLE,
)

logger = logging.getLogger(__name__)


def _build_client() -> OpenAI:
    return OpenAI(
        base_url=OPENROUTER_BASE_URL,
        api_key=OPENROUTER_API_KEY or "dummy",
        timeout=OPENROUTER_TIMEOUT,
    )


def _extra_headers() -> dict:
    """Заголовки для ранжинга на openrouter.ai (опционально)."""
    h = {}
    if OPENROUTER_HTTP_REFERER:
        h["HTTP-Referer"] = OPENROUTER_HTTP_REFERER
    if OPENROUTER_X_TITLE:
        h["X-Title"] = OPENROUTER_X_TITLE
    return h


async def _call_openrouter(system_prompt: str | None, user_content: str) -> str:
    """Один запрос в OpenRouter: system (опционально) + user content (текст)."""
    client = _build_client()
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_content})

    kwargs = {
        "model": OPENROUTER_MODEL,
        "messages": messages,
        "temperature": OPENROUTER_TEMPERATURE,  # Низкая температура для стабильных ответов (0.0-1.0)
        "extra_body": {},
    }
    extra = _extra_headers()
    if extra:
        kwargs["extra_headers"] = extra

    response = await asyncio.to_thread(
        client.chat.completions.create,
        **kwargs,
    )

    if response is None:
        logger.error("OpenRouter вернул None response")
        raise ValueError("OpenRouter API вернул пустой ответ")

    if not response.choices or len(response.choices) == 0:
        logger.error("OpenRouter вернул пустой choices")
        raise ValueError("OpenRouter API вернул пустой список choices")

    assistant_message = response.choices[0].message
    if assistant_message.content is None:
        logger.warning("OpenRouter вернул пустой content")
        return ""

    return assistant_message.content.strip()


async def analyze_contract_with_prompt(full_prompt: str) -> str:
    """
    Отправить в OpenRouter полный промпт (промпт + текст договора) единым текстом.
    Без чанков. Возвращает ответ модели (протокол разногласий + сопроводительное письмо).
    """
    if not OPENROUTER_API_KEY:
        logger.warning("OPENROUTER_API_KEY не задан — возвращаем пустой результат")
        return ""

    try:
        logger.info("Отправка запроса в OpenRouter (модель: %s), размер: %s символов", OPENROUTER_MODEL, len(full_prompt))
        analysis_text = await _call_openrouter(None, full_prompt)
        logger.info("Получен ответ от OpenRouter: %s символов", len(analysis_text))
        return analysis_text
    except Exception as e:
        logger.exception("Ошибка OpenRouter: %s", e)
        raise


def _normalize_line_for_check(s: str) -> str:
    """Убрать в начале строки markdown # и пробелы для сравнения."""
    return re.sub(r"^#+\s*", "", s).strip()


def _is_protocol_part_heading(line: str) -> bool:
    """Строка — заголовок «Часть 1» / «Протокол разногласий», который не показываем в вебе и в Word."""
    n = _normalize_line_for_check(line)
    if not n:
        return False
    u = n.upper()
    if u.startswith("ЧАСТЬ 1") or u.startswith("ЧАСТЬ 1."):
        return True
    if u == "ПРОТОКОЛ РАЗНОГЛАСИЙ" or (u.startswith("ПРОТОКОЛ РАЗНОГЛАСИЙ") and len(n) < 50):
        return True
    return False


def _strip_protocol_headings(text: str) -> str:
    """
    Убрать из начала протокола строки «Протокол разногласий», «# ЧАСТЬ 1. ПРОТОКОЛ РАЗНОГЛАСИЙ» и т.п.
    Один раз заголовок добавим в вебе/Word сами. Оставляем только основной текст (с «к Договору...» и далее).
    """
    lines = text.split("\n")
    result = []
    for line in lines:
        s = line.strip()
        if _is_protocol_part_heading(s):
            continue
        result.append(line)
    return "\n".join(result).strip()


def _strip_letter_part_heading(text: str) -> str:
    """Убрать «Часть 2» / «Сопроводительное письмо» в начале письма."""
    lines = text.split("\n")
    result = []
    skip_leading = True
    for line in lines:
        s = line.strip()
        n = _normalize_line_for_check(s)
        if skip_leading and n:
            u = n.upper()
            if u.startswith("ЧАСТЬ 2") or u.startswith("ЧАСТЬ 2.") or u == "СОПРОВОДИТЕЛЬНОЕ ПИСЬМО":
                continue
            if u.startswith("СОПРОВОДИТЕЛЬНОЕ ПИСЬМО") and len(n) < 50:
                continue
            skip_leading = False
        result.append(line)
    return "\n".join(result).strip()


def split_protocol_and_letter(llm_response: str) -> tuple[str, str]:
    """
    Разделить ответ LLM на «Протокол разногласий» и «Сопроводительное письмо».
    Убираем «Часть 1» / «# ЧАСТЬ 1. ПРОТОКОЛ РАЗНОГЛАСИЙ» и дубли заголовка: в вебе и Word — один заголовок, затем текст.
    """
    protocol = ""
    letter = ""
    part2_markers = ("ЧАСТЬ 2", "СОПРОВОДИТЕЛЬНОЕ ПИСЬМО", "Сопроводительное письмо")

    text = llm_response
    i2 = -1
    for m in part2_markers:
        idx = text.find(m)
        if idx != -1:
            i2 = idx
            break
    if i2 != -1:
        protocol = text[:i2].strip()
        letter = text[i2:].strip()
    else:
        protocol = text.strip()

    # Убрать все строки-заголовки в начале протокола (# ЧАСТЬ 1, Протокол разногласий и т.д.)
    # В вебе заголовок секции уже есть в HTML; в Word его добавляет word_export. Храним только тело.
    protocol = _strip_protocol_headings(protocol)

    letter = _strip_letter_part_heading(letter)

    return protocol, letter
