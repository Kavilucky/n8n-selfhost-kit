# Офлайн-ассистент замеров и смет для мастеров

**Видео №13** канала «ByteAutomate | Код и AI» — https://t.me/ByteAutomate_AI.

Голос/текст → смета по вашему прайс-листу (Excel) → печатная HTML-смета.

## Что нужно

- Python 3.10+
- `pip install -r requirements.txt`

## Быстрый запуск

1. Установите пакеты: `pip install -r requirements.txt`.
2. Заполните `price_list_template.xlsx` своими ценами.
3. Проверка текстом: `python smeta_calc.py --text "стена три двадцать, розеток пять"`.
4. С голосом: `python smeta_calc.py запись.ogg`.

## Состав

- `estimate.html`
- `price_list_template.xlsx`
- `requirements.txt`
- `smeta_calc.py`
- `Инструкция.txt`

Подробная пошаговая инструкция и ограничения — в `Инструкция.txt`.

## Важно

- Набор даётся как есть, без гарантий: сначала проверьте на тестовых данных и сделайте копию своих.
- Токены, ключи и пароли в репозиторий не входят — подставляйте свои и не публикуйте их.

## Канал

Новые материалы и разборы: Telegram [@ByteAutomate_AI](https://t.me/ByteAutomate_AI).
