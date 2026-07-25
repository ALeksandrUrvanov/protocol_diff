"""
Основной модуль для маскирования чувствительных данных.
Используем гибридный подход: словарное + NER.
"""

import re
import logging
from typing import Dict, Tuple

# Импорты словарей
from .dictionaries.persons import PERSON_NAMES, PERSON_PATRONYMS, PERSON_SURNAMES
from .dictionaries.locations import LOCATION_ENTITIES
from .dictionaries.organizations import ORGANIZATION_ENTITIES

try:
    from natasha import (
        Segmenter,
        MorphVocab,
        NewsEmbedding,
        NewsMorphTagger,
        NewsNERTagger,
        Doc
    )
    NATASHA_AVAILABLE = True
except ImportError:
    NATASHA_AVAILABLE = False
    Segmenter = None
    MorphVocab = None
    NewsEmbedding = None
    NewsMorphTagger = None
    NewsNERTagger = None
    Doc = None

# Глобальные переменные для моделей (singleton)
natasha_components = None
_natasha_initialized = False

# Импорт функций нормализации
from .normalizer import (
    preprocess_text_lines,
    deduplicate_entities,
    sort_entities_by_priority,
    normalize_region_name
)

logger = logging.getLogger(__name__)


class EntityMasker:
    """Маскирование чувствительных данных с гибридным подходом."""

    MASK_LABELS = {
        'NAME': 'ИМЯ',
        'PATRONYM': 'ОТЧЕСТВО',
        'SURNAME': 'ФАМИЛИЯ',
        'LOC': 'ЛОКАЦИЯ',
        'ORG': 'ОРГАНИЗАЦИЯ'
    }

    def __init__(self):
        # Базовые словари для маскирования
        self.all_entities = {
            'NAME': PERSON_NAMES,
            'PATRONYM': PERSON_PATRONYMS,
            'SURNAME': PERSON_SURNAMES,
            'LOC': LOCATION_ENTITIES,
            'ORG': ORGANIZATION_ENTITIES
        }
        
        # Инициализация Natasha NER
        global natasha_components, _natasha_initialized
        
        if not _natasha_initialized:
            if NATASHA_AVAILABLE:
                try:
                    logger.info("Инициализация Natasha NER...")
                    
                    segmenter = Segmenter()
                    morph_vocab = MorphVocab()
                    emb = NewsEmbedding()
                    morph_tagger = NewsMorphTagger(emb)
                    ner_tagger = NewsNERTagger(emb)
                    
                    natasha_components = {
                        'segmenter': segmenter,
                        'morph_vocab': morph_vocab,
                        'morph_tagger': morph_tagger,
                        'emb': emb,
                        'ner_tagger': ner_tagger
                    }
                    
                    _natasha_initialized = True
                    logger.info("Natasha NER инициализирован успешно")
                except Exception as e:
                    logger.warning(f"Ошибка инициализации Natasha NER: {e}")
                    natasha_components = None
                    _natasha_initialized = True
            else:
                natasha_components = None
                _natasha_initialized = True
                logger.info("Natasha не установлена, используем словарное маскирование")

    
    def mask(self, text: str) -> Tuple[str, Dict[str, str]]:
        """Маскирует чувствительные данные."""
        logger.debug("Начало маскирования текста")
        
        processed_lines = preprocess_text_lines(text)
        logger.debug(f"Обработано {len(processed_lines)} строк")
        
        entities_to_mask = self._collect_entities(processed_lines)
        logger.debug(f"Найдено {len(entities_to_mask)} уникальных сущностей")
        
        entities_to_mask = deduplicate_entities(entities_to_mask)
        logger.debug(f"После дедупликации: {len(entities_to_mask)} сущностей")
        
        masked_text, mapping = self._apply_masking(text, entities_to_mask)
        
        logger.debug(f"Маскирование завершено: создано {len(mapping)} масок")
        return masked_text, mapping
    
    @staticmethod
    def unmask(text: str, mapping: Dict[str, str]) -> str:
        """Демаскирует текст."""
        result = text
        for mask, original in mapping.items():
            result = result.replace(mask, original)
        return result
    
    def _collect_entities(self, text_lines: list[str]) -> Dict[str, str]:
        """Собирает все сущности для маскирования: сначала словари формируют маппинг, потом NER проверяет."""
        entities = {}
        
        # Объединяем обработанные строки в текст
        full_text = ' '.join(text_lines)

        # 1. СЛОВАРНЫЙ ПОИСК (основной источник - формирует первоочередной маппинг)
        full_text_lower = full_text.lower()
        for entity_type, entity_dict in self.all_entities.items():
            for normalized, variants in entity_dict.items():
                for variant in variants:
                    pattern = r'\b' + re.escape(variant.lower()) + r'\b'
                    if re.search(pattern, full_text_lower):
                        # Используем нормализованную форму
                        if entity_type == 'LOC':
                            normalized = normalize_region_name(normalized)
                        entities[normalized] = entity_type
                        break

        logger.debug(f"Словарный поиск: найдено {len(entities)} сущностей, маппинг сформирован")

        # 2. NER - только проверка найденных сущностей против маппинга словарей
        if natasha_components is not None:
            try:
                segmenter = natasha_components['segmenter']
                morph_vocab = natasha_components['morph_vocab']
                morph_tagger = natasha_components['morph_tagger']
                ner_tagger = natasha_components['ner_tagger']
                
                sentences = [line.strip() for line in text_lines if len(line.strip()) > 10]
                ner_found_count = 0
                ner_duplicates_count = 0
                ner_new_count = 0
                
                for sentence in sentences:
                    
                    try:
                        doc = Doc(sentence)
                        doc.segment(segmenter)
                        doc.tag_morph(morph_tagger)
                        doc.tag_ner(ner_tagger)
                        
                        for span in doc.spans:
                            entity_text = span.text
                            entity_type = span.type
                            
                            # Ищем только нужные типы: PER (имена, фамилии, отчества), LOC, ORG
                            if entity_type not in ['PER', 'LOC', 'ORG']:
                                continue
                            
                            if not self._is_valid_entity(entity_text, entity_type):
                                continue
                            
                            # Приводим к именительному падежу
                            span.normalize(morph_vocab)
                            entity_normalized = span.normal if hasattr(span, 'normal') and span.normal else entity_text
                            
                            ner_found_count += 1
                            
                            # Сравниваем с маппингом словарей
                            if entity_normalized in entities:
                                ner_duplicates_count += 1
                                logger.debug(f"NER нашел '{entity_normalized}' ({entity_type}) - дубликат, есть в маппинге словарей")
                            else:
                                ner_new_count += 1
                                logger.debug(f"NER нашел '{entity_normalized}' ({entity_type}) - новая сущность, нет в маппинге словарей")
                    
                    except (ValueError, IndexError, AttributeError, KeyError) as e:
                        logger.debug(f"Ошибка обработки предложения: {e}")
                        continue
                
                logger.debug(f"NER проверка: найдено {ner_found_count} сущностей, из них {ner_duplicates_count} дубликатов (есть в маппинге), {ner_new_count} новых (информационно)")
            except (ValueError, RuntimeError, AttributeError) as e:
                logger.error(f"Ошибка в Natasha NER: {e}")

        return entities
    
    @staticmethod
    def _is_valid_entity(entity_text: str, entity_type: str) -> bool:
        """Простая валидация сущности."""
        if not entity_text or len(entity_text.strip()) < 3:
            return False
        
        words = entity_text.lower().strip().split()
        if len(words) > 5:
            return False
        
        stop_words = {'подожди', 'подождите', 'да', 'нет', 'ну', 'так', 'что', 'это', 'вот', 'давай', 'давайте'}
        if entity_text.lower() in stop_words:
            return False
        
        return any(c.isalpha() for c in entity_text)
    
    def _apply_masking(self, text: str, entities: Dict[str, str]) -> Tuple[str, Dict[str, str]]:
        """Применяет маскирование к тексту."""
        result = text
        mapping = {}
        reverse_mapping = {}
        counters = {'NAME': 0, 'PATRONYM': 0, 'SURNAME': 0, 'LOC': 0, 'ORG': 0}
        
        sorted_entities = sort_entities_by_priority(entities)
        
        for entity_text, entity_type in sorted_entities:
            if entity_text in reverse_mapping:
                continue
            
            counters[entity_type] += 1
            label = self.MASK_LABELS[entity_type]
            mask = f"[{label}_{counters[entity_type]}]"
            
            mapping[mask] = entity_text
            reverse_mapping[entity_text] = mask
            
            variants = self._get_all_variants(entity_text, entity_type)
            
            for variant in variants:
                result = self._replace_variant(result, variant, mask)
        
        return result, mapping
    
    def _get_all_variants(self, entity_text: str, entity_type: str) -> list[str]:
        """Получает все варианты написания сущности."""
        variants = []
        entity_dict = self.all_entities.get(entity_type, {})
        
        if entity_text in entity_dict:
            variants.extend(entity_dict[entity_text])
        
        variants.append(entity_text)
        variants.append(entity_text.lower())
        variants.append(entity_text.capitalize())
        variants.append(entity_text.upper())
        
        seen = set()
        unique_variants = []
        for v in variants:
            if v not in seen:
                seen.add(v)
                unique_variants.append(v)
        
        unique_variants.sort(key=len, reverse=True)
        
        return unique_variants
    
    @staticmethod
    def _replace_variant(text: str, variant: str, mask: str) -> str:
        """Заменяет вариант сущности на маску."""
        escaped = re.escape(variant)
        
        # Обрабатываем пробелы (могут быть множественными)
        if ' ' in variant:
            pattern = escaped.replace(r'\ ', r'\s+')
        else:
            pattern = escaped
        
        # Word boundary для точного совпадения
        pattern = r'\b' + pattern + r'\b'
        
        # Заменяем (case-insensitive)
        result = re.sub(pattern, mask, text, flags=re.IGNORECASE)
        
        return result



