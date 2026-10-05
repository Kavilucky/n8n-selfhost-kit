# Бот-коллектор дебиторки

**Видео №14** канала «ByteAutomate | Код и AI» — https://t.me/ByteAutomate_AI.

Шаблон n8n: напоминания должникам по таблице Excel, тексты сообщений и шаблон трекера.

## Что нужно

- Работающий n8n (см. ролик 01)
- Telegram-бот от @BotFather

## Быстрый запуск

1. Скопируйте `debts_tracker_template.xlsx` как `debts_tracker.xlsx` в папку данных n8n.
2. В n8n: Workflows → Import from File → `debt_collector_n8n.json` (импортируется выключенным).
3. Подключите свои Credentials, проверьте пути и webhook.
4. Протестируйте на вымышленных данных, затем активируйте.
5. Тексты сообщений — в `scripts_collection.md`.

## Состав

- `debt_collector_n8n.json`
- `debts_tracker_template.xlsx`
- `scripts_collection.md`
- `Инструкция.txt`

Подробная пошаговая инструкция и ограничения — в `Инструкция.txt`.

## Важно

- Набор даётся как есть, без гарантий: сначала проверьте на тестовых данных и сделайте копию своих.
- Токены, ключи и пароли в репозиторий не входят — подставляйте свои и не публикуйте их.

## Канал

Новые материалы и разборы: Telegram [@ByteAutomate_AI](https://t.me/ByteAutomate_AI).
