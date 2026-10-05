# Умный дом без облаков на Home Assistant

**Видео №11** канала «ByteAutomate | Код и AI» — https://t.me/ByteAutomate_AI.

Docker Compose: Home Assistant + Mosquitto + Zigbee2MQTT с готовыми конфигами.

## Что нужно

- Linux-хост, Docker и Docker Compose
- Zigbee-координатор (USB)

## Быстрый запуск

1. `cp env.example .env`, впишите путь координатора (`ls -l /dev/serial/by-id/`), часовой пояс и пароль MQTT.
2. Создайте пользователей MQTT: `docker compose run --rm mosquitto mosquitto_passwd -c /mosquitto/config/passwd zigbee2mqtt` (и второго — `homeassistant`).
3. Запуск: `docker compose up -d`, проверка: `docker compose ps`.
4. Home Assistant: `http://адрес-компьютера:8123`, Zigbee2MQTT: `http://адрес-компьютера:8080`.

## Состав

- `docker-compose.yml`
- `env.example`
- `homeassistant/automations.yaml`
- `homeassistant/configuration.yaml`
- `mosquitto/config/mosquitto.conf`
- `zigbee2mqtt/data/configuration.yaml`
- `Инструкция.txt`

Подробная пошаговая инструкция и ограничения — в `Инструкция.txt`.

## Важно

- Набор даётся как есть, без гарантий: сначала проверьте на тестовых данных и сделайте копию своих.
- Токены, ключи и пароли в репозиторий не входят — подставляйте свои и не публикуйте их.

## Канал

Новые материалы и разборы: Telegram [@ByteAutomate_AI](https://t.me/ByteAutomate_AI).
