# -*- coding: utf-8 -*-
"""Валидация загруженных файлов договоров."""
from pathlib import Path
from fastapi import HTTPException, UploadFile


class FileValidator:
    """Валидация файлов документов (PDF, DOCX, изображения)."""

    def __init__(self, max_size: int, supported_extensions: set | list):
        self.max_size = max_size
        self.supported_extensions = set(supported_extensions)

    async def validate(self, file: UploadFile) -> tuple[bytes, int, str]:
        """
        Валидация файла.
        Returns:
            tuple: (content, file_size, file_extension)
        """
        if not file.filename:
            raise HTTPException(status_code=400, detail="Имя файла не указано")

        content = await file.read()
        file_size = len(content)

        if file_size > self.max_size:
            raise HTTPException(
                status_code=413,
                detail=f"Файл слишком большой. Максимальный размер: {self.max_size // (1024*1024)} МБ",
            )

        if file_size == 0:
            raise HTTPException(status_code=400, detail="Файл пуст")

        file_extension = Path(file.filename).suffix.lower()
        if file_extension not in self.supported_extensions:
            raise HTTPException(
                status_code=400,
                detail=f"Неподдерживаемый формат. Разрешены: {', '.join(sorted(self.supported_extensions))}",
            )

        return content, file_size, file_extension
