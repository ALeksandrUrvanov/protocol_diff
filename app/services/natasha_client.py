# -*- coding: utf-8 -*-
"""
Маскирование чувствительных данных через EntityMasker (словари + Natasha NER).
По образцу conference_analysis/app/masking.
"""
import logging

logger = logging.getLogger(__name__)

_entity_masker = None


def _get_masker():
    """Ленивая инициализация EntityMasker (тяжёлые модели Natasha)."""
    global _entity_masker
    if _entity_masker is None:
        try:
            from app.masking import EntityMasker
            _entity_masker = EntityMasker()
            logger.info("EntityMasker (Natasha + словари) инициализирован")
        except Exception as e:
            logger.warning("Не удалось загрузить EntityMasker: %s. Маскирование отключено.", e)
    return _entity_masker


def mask_sensitive_text(text: str) -> tuple[str, dict]:
    """
    Маскировать чувствительные данные в тексте (ФИО, организации, локации).
    Returns:
        (masked_text, mapping) — замаскированный текст и словарь маска -> оригинал для размаскировки.
    """
    masker = _get_masker()
    if masker is None:
        return text, {}
    try:
        masked_text, mapping = masker.mask(text)
        return masked_text, mapping
    except Exception as e:
        logger.warning("Ошибка маскирования: %s. Возвращаем исходный текст.", e)
        return text, {}


def unmask_sensitive_text(text: str, mapping: dict) -> str:
    """Восстановить чувствительные данные в тексте по mapping (маска -> оригинал)."""
    if not mapping:
        return text
    try:
        masker = _get_masker()
        if masker is not None:
            return masker.unmask(text, mapping)
    except Exception as e:
        logger.warning("Ошибка размаскирования: %s", e)
    # Fallback: простая подстановка
    result = text
    for mask, original in mapping.items():
        result = result.replace(mask, original)
    return result
