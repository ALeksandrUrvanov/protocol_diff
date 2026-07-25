"""Модуль нормализации текста для маскирования."""

import re
from typing import Dict


def preprocess_text_lines(text: str) -> list[str]:
    """Предобработка текста: удаление временных меток и разделение на строки."""
    lines = text.split('\n')
    processed_lines = []
    
    for line in lines:
        line = re.sub(r'\[\d{2}:\d{2}\s*-\s*\d{2}:\d{2}]', '', line)
        line = re.sub(r'Спикер\s+\d+:', '', line)
        line = re.sub(r'\s+', ' ', line).strip()
        
        if line and len(line) > 5:
            processed_lines.append(line)
    
    return processed_lines


def normalize_region_name(text: str) -> str:
    """Нормализует названия регионов: 'Область' → 'область'."""
    if ' Область' in text:
        return text.replace(' Область', ' область')
    return text


def sort_entities_by_priority(entities: Dict[str, str]) -> list[tuple[str, str]]:
    """Сортирует сущности по приоритету: длинные первыми."""
    return sorted(
        entities.items(),
        key=lambda x: (-len(x[0]), x[0])
    )


def deduplicate_entities(entities: Dict[str, str]) -> Dict[str, str]:
    """Удаляет дубликаты сущностей."""
    result = {}
    
    sorted_entities = sorted(
        entities.items(), 
        key=lambda x: (len(x[0].split()), len(x[0])), 
        reverse=True
    )
    
    for entity_text, entity_type in sorted_entities:
        is_substring_of_added = False
        entity_lower = entity_text.lower()
        entity_words = set(entity_lower.split())
        
        for added_text, added_type in result.items():
            added_lower = added_text.lower()
            added_words = set(added_lower.split())
            
            if entity_type in {'NAME', 'PATRONYM', 'SURNAME'}:
                continue
            
            if entity_type == added_type and entity_type in {'LOC', 'ORG'}:
                if entity_lower != added_lower and entity_lower in added_lower:
                    is_substring_of_added = True
                    break
                
                if entity_words.issubset(added_words) and entity_lower != added_lower:
                    is_substring_of_added = True
                    break
        
        if not is_substring_of_added:
            result[entity_text] = entity_type
    
    return result

