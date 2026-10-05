# Приватный AI-помощник по учёту чеков

**Видео №08** канала «ByteAutomate | Код и AI» — https://t.me/ByteAutomate_AI.

Шаблон n8n: фото чека в Telegram → распознавание моделью Qwen-VL (Ollama) → CSV-таблица расходов.

## Что нужно

- n8n в Docker
- Ollama с моделью `qwen2.5vl:7b` (или `:3b`)
- Telegram-бот от @BotFather

## Быстрый запуск

1. Установите Ollama и выполните `ollama pull qwen2.5vl:7b`.
2. Запустите n8n (команда `docker run` в `Инструкция.txt`).
3. Импортируйте `receipt_parser_workflow.json`.
4. Подключите свои Credentials Telegram.
5. Отправьте боту фото чека; результат пишется в `expenses.csv` (шаблон: `expenses_template.csv`).

## Состав

- `expenses_template.csv`
- `model_prompt_ru.txt`
- `receipt_parser_workflow.json`
- `test_receipts/README.txt`
- `Инструкция.txt`

Подробная пошаговая инструкция и ограничения — в `Инструкция.txt`.

## Важно

- Набор даётся как есть, без гарантий: сначала проверьте на тестовых данных и сделайте копию своих.
- Токены, ключи и пароли в репозиторий не входят — подставляйте свои и не публикуйте их.

## Канал

Новые материалы и разборы: Telegram [@ByteAutomate_AI](https://t.me/ByteAutomate_AI).
