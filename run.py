# -*- coding: utf-8 -*-
"""
Точка входа: настраивает логирование (скрываем частый опрос GET /api/status/) и запускает uvicorn.
"""
import logging
import uvicorn
from app.config import DEFAULT_PORT


class NoStatusPollingFilter(logging.Filter):
    """Не логировать запросы GET /api/status/{id} (опрос статуса с фронта)."""
    def filter(self, record):
        msg = record.getMessage()
        if "GET" in msg and "/api/status/" in msg:
            return False
        return True


def main():
    logging.getLogger("uvicorn.access").addFilter(NoStatusPollingFilter())
    uvicorn.run(
        "app.api:app",
        host="0.0.0.0",
        port=DEFAULT_PORT,
    )


if __name__ == "__main__":
    main()
