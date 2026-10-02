# n8n-selfhost-kit

Скрипт установки своего сервера n8n (Docker Compose, Postgres, Caddy с автоматическим HTTPS) и 5 шаблонов автоматизаций. Материалы к ролику канала ByteAutomate | Код и AI (@ByteAutomate_AI).

## Запуск одной строкой

Нужен чистый сервер с Ubuntu или Debian, вход под root (например, через веб-консоль хостинга) и домен, у которого A-запись уже указывает на IP сервера.

```bash
curl -fsSL https://raw.githubusercontent.com/Kavilucky/n8n-selfhost-kit/main/deploy_n8n.sh -o deploy_n8n.sh && bash deploy_n8n.sh
```

Если нет curl:

```bash
wget -qO deploy_n8n.sh https://raw.githubusercontent.com/Kavilucky/n8n-selfhost-kit/main/deploy_n8n.sh && bash deploy_n8n.sh
```

Скрипт задаст четыре вопроса: домен, email для сертификата Let's Encrypt, логин и пароль. Команда сначала скачивает файл, а потом запускает его, поэтому вопросы работают как обычно. Перед запуском скрипт можно открыть и прочитать: он небольшой.

## Что внутри

- `deploy_n8n.sh`: ставит Docker (если его нет), поднимает n8n, Postgres и Caddy, пишет ключи в `/opt/n8n/.env`.
- `templates/`: шаблоны для импорта в n8n (Import from File):
  - `2_google_sheets_log.json` и `3_manager_notification.json`: блоки, которые вызываются из других сценариев нодой Execute Workflow;
  - `4_webhook_form.json`: приём формы с сайта;
  - `1_telegram_leadgen.json`: сбор заявок из Telegram-бота;
  - `5_autoresponder.json`: автоответчик по ключевым словам.

## Важно

- Сразу после установки откройте адрес и создайте учётную запись владельца n8n: пока она не создана, регистрацию может пройти любой, кто знает адрес.
- Сохраните `/opt/n8n/.env`: там ключ шифрования данных.
- В шаблонах 1 и 5 стоит Telegram Trigger: на одном боте держите активным один из них.
- Подробный гайд для новичков (аренда сервера, домен, импорт шаблонов) лежит в файле `Инструкция.txt` из архива в закреплённом посте канала.

## Внедрение под ключ

Установка и настройка n8n, отказоустойчивость, интеграция с amoCRM, Битрикс24, 1С: @konstantin_100.
