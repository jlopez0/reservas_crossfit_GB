# reservation_bot/dates.py
from datetime import datetime, date, timedelta
from typing import Optional

from config import TZ_MADRID, TARGET_CLASS_WEEKDAYS


def today_madrid() -> date:
    """Devuelve la fecha de hoy en zona horaria de Madrid."""
    now = datetime.now(TZ_MADRID)
    return now.date()


def compute_target_date(today: Optional[date] = None) -> Optional[date]:
    """
    Calcula la fecha para la que se debe reservar:
    - Día objetivo = hoy + 3 días.
    - Solo se reserva si ese día objetivo es uno de TARGET_CLASS_WEEKDAYS.

    Si no toca reservar hoy, devuelve None.
    """
    if today is None:
        today = today_madrid()

    target_date = today + timedelta(days=0)
    if target_date.weekday() in TARGET_CLASS_WEEKDAYS:
        return target_date
    return None
