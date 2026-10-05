# Автоматический пайплайн новостей n8n

**Видео №04** канала «ByteAutomate | Код и AI» — https://t.me/ByteAutomate_AI.

Шаблон n8n: RSS → рерайтинг и фактчекинг локальной моделью Qwen (Ollama) → Telegram-канал.

## Что нужно

- Работающий n8n (см. ролик 01)
- Ollama с моделью `qwen2.5:3b`
- Telegram-бот от @BotFather

## Быстрый запуск

1. Поднимите Ollama рядом с n8n: `docker run -d --name ollama --restart unless-stopped --network n8n_default -v ollama_data:/root/.ollama ollama/ollama`
2. Скачайте модель: `docker exec ollama ollama pull qwen2.5:3b`
3. В n8n: Workflows → Import from File → `news_workflow.json`.
4. Подключите свои Credentials Telegram, впишите свою RSS-ссылку и ID канала.
5. В узле «Ollama Qwen» укажите `http://ollama:11434/api/generate`, затем запустите вручную для теста.

## Состав

- `news_workflow.json`
- `Инструкция.txt`

Подробная пошаговая инструкция и ограничения — в `Инструкция.txt`.

## Важно

- Набор даётся как есть, без гарантий: сначала проверьте на тестовых данных и сделайте копию своих.
- Токены, ключи и пароли в репозиторий не входят — подставляйте свои и не публикуйте их.

## Канал

Новые материалы и разборы: Telegram [@ByteAutomate_AI](https://t.me/ByteAutomate_AI).
