# Protocol Diff

Веб-приложение: протокол разногласий и сопроводительное письмо по договору (OCR → маскирование → LLM → Word).

## Stack

- Python, FastAPI, Uvicorn, Jinja2, Bootstrap
- Внешний OCR API (сервис Qwen3-VL)
- Natasha + словари маскирования
- OpenRouter (default `anthropic/claude-sonnet-4.5`)
- python-docx, Docker, порт `8087`

## Pipeline

1. Выбор типа договора (6 шаблонов в `prompts/`).
2. Upload PDF/DOCX/изображения → OCR.
3. Маскирование ПДн.
4. LLM → протокол + письмо; экспорт `.docx`.

## Run

```bash
pip install -r requirements.txt
export OPENROUTER_API_KEY=... OCR_BASE_URL=http://localhost:8081
python run.py   # :8087
```

## Config

| Variable | Required | Notes |
|----------|----------|-------|
| `OPENROUTER_API_KEY` | yes | |
| `OPENROUTER_MODEL` | no | Claude Sonnet 4.5 |
| `OCR_BASE_URL` | yes | |
| `PORT` | no | `8087` |

## Notes

- Нужен доступный OCR-сервис.
- Типы: тепло / вода / электричество / газ / ТКО / содержание и ремонт.
