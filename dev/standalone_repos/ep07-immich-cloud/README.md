# Приватное облако фото Immich

**Видео №07** канала «ByteAutomate | Код и AI» — https://t.me/ByteAutomate_AI.

Инструкция по развёртыванию Immich и скрипты резервного копирования библиотеки (Windows и Linux).

## Что нужно

- Docker (Docker Desktop или Docker Engine)
- Внешний диск для второй копии

## Быстрый запуск

1. Следуйте `Инструкция.txt`: скачайте `docker-compose.yml` и `.env` Immich, задайте пароль БД.
2. Запустите: `docker compose up -d`.
3. Откройте `http://localhost:2283` и создайте администратора.
4. Резервная копия: Windows — `backup_windows.bat`, Linux — `bash backup_linux.sh`.

## Состав

- `backup_linux.sh`
- `backup_windows.bat`
- `Инструкция.txt`

Подробная пошаговая инструкция и ограничения — в `Инструкция.txt`.

## Важно

- Набор даётся как есть, без гарантий: сначала проверьте на тестовых данных и сделайте копию своих.
- Токены, ключи и пароли в репозиторий не входят — подставляйте свои и не публикуйте их.

## Канал

Новые материалы и разборы: Telegram [@ByteAutomate_AI](https://t.me/ByteAutomate_AI).
