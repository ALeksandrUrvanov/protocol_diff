FROM python:3.10-slim

WORKDIR /app

# Python зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Код приложения
COPY app/ ./app/
COPY frontend/ ./frontend/
COPY prompts/ ./prompts/

# Переменные окружения
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8087

# Рабочая директория для временных загрузок
RUN mkdir -p /app/cache

EXPOSE 8087

COPY run.py .
CMD ["python", "run.py"]
