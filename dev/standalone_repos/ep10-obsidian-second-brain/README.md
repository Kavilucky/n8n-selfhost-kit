# Второй мозг: голосовые из Telegram в Obsidian

**Видео №10** канала «ByteAutomate | Код и AI» — https://t.me/ByteAutomate_AI.

Скрипт принимает голосовые из Telegram, расшифровывает и кладёт заметки в хранилище Obsidian.

## Что нужно

- Python 3.9+
- `pip install faster-whisper`
- Telegram-бот от @BotFather

## Быстрый запуск

1. Установите пакет: `pip install faster-whisper`.
2. Скопируйте `env.example` в `.env` и впишите свой токен бота и `ALLOWED_CHAT_ID`.
3. Скопируйте `config.example.json` в `config.json` и укажите путь к vault.
4. Запуск: `python telegram_to_obsidian.py --config config.json --poll`.
5. Обработка папки: `--process-inbox`; один файл: `--file запись.ogg`.

## Состав

- `config.example.json`
- `env.example`
- `telegram_to_obsidian.py`
- `vault_template/README.md`
- `vault_template/processed_notes/ПРОЧИТАЙ.txt`
- `vault_template/raw_inbox/ПРОЧИТАЙ.txt`
- `vault_template/templates/voice_note.md`
- `Инструкция.txt`

Подробная пошаговая инструкция и ограничения — в `Инструкция.txt`.

## Важно

- Набор даётся как есть, без гарантий: сначала проверьте на тестовых данных и сделайте копию своих.
- Токены, ключи и пароли в репозиторий не входят — подставляйте свои и не публикуйте их.

## Канал

Новые материалы и разборы: Telegram [@ByteAutomate_AI](https://t.me/ByteAutomate_AI).
