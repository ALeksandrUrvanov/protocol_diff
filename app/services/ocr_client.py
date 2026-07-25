# -*- coding: utf-8 -*-
"""Клиент к Docker OCR API: загрузка документа, опрос статуса, получение результата."""
import time
import logging
from pathlib import Path
import requests

logger = logging.getLogger(__name__)


class OCRClient:
    def __init__(
        self,
        base_url: str,
        poll_interval: float = 2.0,
        max_wait_sec: int = 3000,
        mode: str = "full_text",
        prompt: str = "",
        temperature: float = 0.1,
    ):
        self.base_url = base_url.rstrip("/")
        self.poll_interval = poll_interval
        self.max_wait_sec = max_wait_sec
        self.mode = mode
        self.prompt = prompt
        self.temperature = temperature

    def upload(self, file_path: Path, original_filename: str, content_type: str = "application/octet-stream") -> str:
        """Загрузить файл, вернуть task_id."""
        with open(file_path, "rb") as f:
            r = requests.post(
                f"{self.base_url}/api/documents/upload",
                files={"file": (original_filename, f, content_type)},
                data={
                    "mode": self.mode,
                    "prompt": self.prompt,
                    "temperature": str(self.temperature),
                },
                timeout=60,
            )
        if r.status_code != 202:
            raise RuntimeError(f"OCR upload failed {r.status_code}: {r.text}")
        data = r.json()
        return data["task_id"]

    def get_status(self, task_id: str) -> dict:
        """Получить статус задачи: status, processed_pages, total_pages."""
        r = requests.get(f"{self.base_url}/api/documents/{task_id}/status", timeout=10)
        if r.status_code == 404:
            raise ValueError("Задача не найдена")
        r.raise_for_status()
        return r.json()

    def get_queue_info(self) -> dict:
        """Состояние очереди OCR: queued (число в очереди), active_results."""
        r = requests.get(f"{self.base_url}/api/documents/queue/info", timeout=10)
        r.raise_for_status()
        return r.json()

    def wait_completion(self, task_id: str, status_callback=None) -> dict:
        """
        Ожидать завершения OCR, опрашивая статус.
        status_callback(processed_pages, total_pages, status, queue_position=None) вызывается при каждом опросе.
        При status=='queued' queue_position — число задач в очереди (из GET /api/documents/queue/info).
        Возвращает итоговый status_data (с total_pages, processed_pages, status).
        """
        elapsed = 0
        while elapsed < self.max_wait_sec:
            data = self.get_status(task_id)
            status = data.get("status", "")
            total = data.get("total_pages", 0)
            processed = data.get("processed_pages", 0)
            queue_position = None
            if status == "queued":
                try:
                    info = self.get_queue_info()
                    queue_position = info.get("queued", 0)
                except Exception as e:
                    logger.debug("Queue info unavailable: %s", e)

            if status_callback:
                try:
                    status_callback(processed, total, status, queue_position=queue_position)
                except Exception as e:
                    logger.warning("OCR status_callback error: %s", e)

            if status == "completed":
                return data
            if status == "failed":
                raise RuntimeError("OCR обработка завершилась с ошибкой")

            time.sleep(self.poll_interval)
            elapsed += int(self.poll_interval)

        raise TimeoutError("Превышено время ожидания OCR")

    def get_result(self, task_id: str) -> dict:
        """Получить результат распознавания: full_text, pages, status, processed_pages, total_pages."""
        r = requests.get(f"{self.base_url}/api/documents/{task_id}/result", timeout=60)
        r.raise_for_status()
        return r.json()
