"""
Парсинг относительных дат на русском языке ("следующая пятница",
"на выходные", "через 3 дня") в абсолютные даты.

Используется библиотека dateparser с локалью 'ru', плюс несколько
ручных правил для случаев, которые dateparser обрабатывает не идеально
(например "на выходные" -> ближайшая субботы-воскресенье).
"""

from datetime import datetime, timedelta
import dateparser


WEEKDAYS_RU = {
    "понедельник": 0, "вторник": 1, "среда": 2, "четверг": 3,
    "пятница": 4, "суббота": 5, "воскресенье": 6,
}


def parse_relative_date(text: str, base_date: datetime | None = None) -> datetime | None:
    """
    Пытается распарсить дату из произвольного текста на русском.
    Возвращает datetime или None, если не удалось распознать.
    """
    base_date = base_date or datetime.now()

    settings = {
        "RELATIVE_BASE": base_date,
        "PREFER_DATES_FROM": "future",
    }

    result = dateparser.parse(text, languages=["ru"], settings=settings)
    return result


def next_weekend(base_date: datetime | None = None) -> tuple[datetime, datetime]:
    """Возвращает (субботу, воскресенье) ближайших выходных от base_date."""
    base_date = base_date or datetime.now()
    days_until_saturday = (5 - base_date.weekday()) % 7
    if days_until_saturday == 0 and base_date.weekday() == 5:
        days_until_saturday = 0
    saturday = base_date + timedelta(days=days_until_saturday)
    sunday = saturday + timedelta(days=1)
    return saturday, sunday


def next_weekday(weekday_name_ru: str, base_date: datetime | None = None) -> datetime | None:
    """Возвращает дату следующего вхождения дня недели (например 'пятница')."""
    base_date = base_date or datetime.now()
    weekday_name_ru = weekday_name_ru.lower().strip()
    if weekday_name_ru not in WEEKDAYS_RU:
        return None
    target = WEEKDAYS_RU[weekday_name_ru]
    days_ahead = (target - base_date.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7  # "следующая пятница" = через неделю, если сегодня пятница
    return base_date + timedelta(days=days_ahead)


def to_kiwi_format(date_obj: datetime) -> str:
    """Kiwi требует формат dd/mm/yyyy."""
    return date_obj.strftime("%d/%m/%Y")


def to_iso_date(date_obj: datetime) -> str:
    """Trivago и большинство API используют YYYY-MM-DD."""
    return date_obj.strftime("%Y-%m-%d")
