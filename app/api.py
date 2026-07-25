# -*- coding: utf-8 -*-
"""
FastAPI-приложение: протоколы разногласий.
Маршруты: /api/prompts, /api/process, /api/status/{id}, /api/result/{id}, /api/export-word.
Пайплайн запускается в отдельном потоке, чтобы статусы отвечали без блокировки (OCR — синхронный).
"""
import asyncio
import logging
import threading
import uuid
from pathlib import Path

from pydantic import BaseModel
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from . import config as _config
from .config import (
    CACHE_DIR,
    CONTRACT_PLACEHOLDER,
    FRONTEND_STATIC_DIR,
    FRONTEND_TEMPLATES_DIR,
    PROMPTS_DIR,
    SERVICES,
    OCR_BASE_URL,
    OCR_POLL_INTERVAL,
    OCR_MAX_WAIT_SEC,
    OCR_MODE,
    OCR_PROMPT,
    OCR_TEMPERATURE,
)
from .services.file_validator import FileValidator
from .services.ocr_client import OCRClient
from .services import natasha_client
from .services.openrouter_client import analyze_contract_with_prompt, split_protocol_and_letter
from .services.word_export import export_protocol_and_letter

logger = logging.getLogger(__name__)

app = FastAPI(title="Protocol Diff")

validator = FileValidator(
    max_size=_config.MAX_FILE_SIZE,
    supported_extensions=_config.ALLOWED_EXTENSIONS,
)

# Отдельные хранилища и блокировки (как в старом API) — статусы читаются пока пайплайн крутится в потоке
processing_status: dict = {}
status_lock = threading.Lock()
processing_results: dict = {}
results_lock = threading.Lock()


def _update_status(
    request_id: str,
    status: str,
    message: str,
    progress: int,
    total_pages: int = None,
    processed_pages: int = None,
    queue_position: int = None,
):
    with status_lock:
        processing_status[request_id] = {
            "status": status,
            "message": message,
            "progress": progress,
            "total_pages": total_pages,
            "processed_pages": processed_pages,
            "queue_position": queue_position,
        }


def _read_prompt(prompt_id: str) -> str:
    """Прочитать текст промпта по id (имя файла без .md)."""
    path = PROMPTS_DIR / f"{prompt_id}.md"
    if not path.is_file():
        raise HTTPException(status_code=400, detail=f"Промпт {prompt_id} не найден")
    return path.read_text(encoding="utf-8")


async def _run_pipeline(request_id: str, file_path: Path, original_filename: str, prompt_id: str):
    """Фоновая обработка: OCR → маскирование → OpenRouter → размаскирование → разбиение. Вызывается из потока через asyncio.run."""
    try:
        ocr = OCRClient(
            OCR_BASE_URL,
            poll_interval=OCR_POLL_INTERVAL,
            max_wait_sec=OCR_MAX_WAIT_SEC,
            mode=OCR_MODE,
            prompt=OCR_PROMPT,
            temperature=OCR_TEMPERATURE,
        )

        def _progress_cb(processed: int, total: int, status: str, queue_position: int = None):
            if status == "queued":
                # Число показываем только когда в очереди 2 и более (не показываем 0 или «1» — следующий на очереди)
                if queue_position is not None and queue_position > 1:
                    msg = f"Запрос в очереди... {queue_position}"
                else:
                    msg = "Запрос в очереди..."
                _update_status(request_id, "ocr_queued", msg, 5, queue_position=queue_position)
                return
            if total and total > 0:
                # OCR занимает 5-75% (диапазон 70%)
                pct = 5 + int(70 * processed / total)
            else:
                pct = 5
            _update_status(request_id, "ocr", "Распознавание страниц", pct, total_pages=total, processed_pages=processed)

        task_id = ocr.upload(file_path, original_filename)
        ocr.wait_completion(task_id, status_callback=_progress_cb)
        _update_status(request_id, "ocr", "Получение текста...", 75)
        ocr_result = ocr.get_result(task_id)
        full_text = ocr_result.get("full_text", "") or ""

        if not full_text.strip():
            _update_status(request_id, "error", "OCR не вернул текст", 0)
            with results_lock:
                processing_results[request_id] = {"success": False, "error": "Пустой текст после OCR"}
            return

        prompt_template = _read_prompt(prompt_id)
        _update_status(request_id, "masking", "Маскировка данных...", 77)
        masked_text, mapping = natasha_client.mask_sensitive_text(full_text)
        full_prompt = prompt_template.replace(CONTRACT_PLACEHOLDER, masked_text)

        _update_status(request_id, "analysis", "Формируем протокол разногласий и сопроводительное письмо...", 80)
        analysis_text = await analyze_contract_with_prompt(full_prompt)
        if not analysis_text.strip():
            analysis_text = "[Ожидается подключение OpenRouter]"

        _update_status(request_id, "unmasking", "Восстановление данных...", 95)
        unmasked = natasha_client.unmask_sensitive_text(analysis_text, mapping)
        protocol_text, letter_text = split_protocol_and_letter(unmasked)

        _update_status(request_id, "complete", "Готово", 100)
        with results_lock:
            processing_results[request_id] = {
                "success": True,
                "protocol_text": protocol_text,
                "letter_text": letter_text,
            }

    except (ConnectionError, OSError):
        logger.exception("OCR connection error")
        _update_status(
            request_id,
            "error",
            "Не удалось подключиться к сервису OCR. Проверьте доступность OCR (OCR_BASE_URL) с этого сервера.",
            0,
        )
        with results_lock:
            processing_results[request_id] = {"success": False, "error": "Ошибка подключения к OCR"}
    except Exception as e:
        logger.exception("Pipeline error: %s", e)
        _update_status(request_id, "error", str(e) if str(e) else "Ошибка обработки", 0)
        with results_lock:
            processing_results[request_id] = {"success": False, "error": str(e) if str(e) else "Ошибка обработки"}
    finally:
        if file_path.exists():
            try:
                file_path.unlink()
            except OSError:
                pass


def _run_pipeline_sync(request_id: str, file_path: Path, original_filename: str, prompt_id: str):
    """Запуск async-пайплайна в отдельном потоке (чтобы не блокировать ответы /api/status)."""
    asyncio.run(_run_pipeline(request_id, file_path, original_filename, prompt_id))


@app.get("/")
async def index(request: Request):
    """Главная страница."""
    templates = Jinja2Templates(directory=str(FRONTEND_TEMPLATES_DIR))
    return templates.TemplateResponse("index.html", {"request": request})


app.mount("/static", StaticFiles(directory=str(FRONTEND_STATIC_DIR)), name="static")


@app.get("/api/prompts")
async def api_prompts():
    """Список служб (промптов) для выбора."""
    return {"services": SERVICES}


@app.post("/api/process")
async def api_process(
    file: UploadFile = File(...),
    prompt_id: str = Form(...),
):
    """Запуск обработки: загрузка файла, OCR, маскирование, OpenRouter, разбиение. Возвращает request_id."""
    content, size, ext = await validator.validate(file)
    request_id = str(uuid.uuid4())
    cache_path = CACHE_DIR / f"{request_id}{ext}"
    cache_path.write_bytes(content)
    original_filename = file.filename or f"document{ext}"

    prompt_path = PROMPTS_DIR / f"{prompt_id}.md"
    if not prompt_path.exists():
        if cache_path.exists():
            cache_path.unlink()
        raise HTTPException(status_code=400, detail=f"Неизвестная служба: {prompt_id}")

    _update_status(request_id, "processing", "Загрузка...", 0)

    thread = threading.Thread(
        target=_run_pipeline_sync,
        args=(request_id, cache_path, original_filename, prompt_id),
    )
    thread.start()

    return {"request_id": request_id, "message": "Обработка запущена"}


@app.get("/api/status/{request_id}")
async def api_status(request_id: str):
    """Статус обработки: progress, message, processed_pages, total_pages, status."""
    with status_lock:
        if request_id in processing_status:
            return processing_status[request_id]
    return {"status": "unknown", "message": "Запрос не найден", "progress": 0}


@app.get("/api/result/{request_id}")
async def api_result(request_id: str):
    """Результат: protocol_text, letter_text, success, error."""
    with results_lock:
        if request_id not in processing_results:
            raise HTTPException(status_code=404, detail="Результат не найден или ещё не готов")
        r = processing_results[request_id]
    return {
        "success": r.get("success", False),
        "protocol_text": r.get("protocol_text") or "",
        "letter_text": r.get("letter_text") or "",
        "error": r.get("error"),
    }


class WordExportBody(BaseModel):
    protocol_text: str = ""
    letter_text: str = ""
    filename: str = "protocol"
    part: str = "both"


@app.post("/api/export-word")
async def api_export_word(body: WordExportBody):
    """Экспорт в Word: protocol_text, letter_text, filename, part (both|protocol|letter)."""
    part = body.part if body.part in ("both", "protocol", "letter") else "both"
    return export_protocol_and_letter(
        body.protocol_text, body.letter_text, (body.filename or "protocol").strip() or "protocol", part=part
    )
