# Свой сервер n8n вместо подписок

**Видео №01** канала «ByteAutomate | Код и AI» — https://t.me/ByteAutomate_AI.

Скрипт установки n8n (Docker Compose, Postgres, Caddy с HTTPS) и 5 готовых шаблонов автоматизаций.

## Что нужно

- Чистый сервер Ubuntu/Debian с root-доступом
- Домен с A-записью на IP сервера

## Быстрый запуск

1. Зайдите на сервер под root (например, через веб-консоль хостинга).
2. Выполните: `curl -fsSL https://raw.githubusercontent.com/Kavilucky/ep01-n8n-selfhost/main/deploy_n8n.sh -o deploy_n8n.sh && bash deploy_n8n.sh`
3. Ответьте на четыре вопроса: домен, email для сертификата, логин, пароль.
4. Откройте `https://ваш-домен` и сразу создайте учётную запись владельца.
5. Сохраните `/opt/n8n/.env` (там ключ шифрования).
6. В n8n: Workflows → Import from File → файлы из папки `templates/`.

## Состав

- `deploy_n8n.sh`
- `templates/1_telegram_leadgen.json`
- `templates/2_google_sheets_log.json`
- `templates/3_manager_notification.json`
- `templates/4_webhook_form.json`
- `templates/5_autoresponder.json`
- `Инструкция.txt`

Подробная пошаговая инструкция и ограничения — в `Инструкция.txt`.

## Важно

- Набор даётся как есть, без гарантий: сначала проверьте на тестовых данных и сделайте копию своих.
- Токены, ключи и пароли в репозиторий не входят — подставляйте свои и не публикуйте их.

## Канал

Новые материалы и разборы: Telegram [@ByteAutomate_AI](https://t.me/ByteAutomate_AI).
