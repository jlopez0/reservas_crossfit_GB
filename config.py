# reservation_bot/config.py
import os
from zoneinfo import ZoneInfo

# === Configuración general ===

# Cookie de sesión de CrossHero (_crosshero_session)
# La leerás de un secreto en GitHub Actions.
SESSION_COOKIE = os.getenv("SESSION_COOKIE", "4642d41292807393281b44ddb65ca414")

# Nombre de la cookie de sesión (por si cambiara algún día)
SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "_crosshero_session")

# URL base
BASE_URL = os.getenv("BASE_URL", "https://crosshero.com")

# Program IDs:
# - Lunes, martes y jueves -> program_id "principal"
# - Miércoles -> otro program_id
PROGRAM_ID_MTT = os.getenv("PROGRAM_ID_MTT", "5a6f2ebea8efdc0006f8656a")
PROGRAM_ID_WED = os.getenv("PROGRAM_ID_WED", "5c3cce31ab433d003b87a6f9")


def get_program_id_for_weekday(weekday: int) -> str:
    """
    Devuelve el program_id en función del día de la semana de la CLASE (no de hoy):
    weekday: 0 = lunes, 1 = martes, ..., 6 = domingo
    """
    if weekday == 2:  # miércoles
        return PROGRAM_ID_WED
    # lunes, martes, jueves (y resto si quisieras)
    return PROGRAM_ID_MTT


# Hora objetivo de reserva (20:00 hora Madrid)
TZ_MADRID = ZoneInfo("Europe/Madrid")
TARGET_HOUR = int(os.getenv("TARGET_HOUR", "20"))
TARGET_MINUTE = int(os.getenv("TARGET_MINUTE", "0"))

# Hora como string para buscar la clase en el select ("20:00")
TARGET_TIME_STR = f"{TARGET_HOUR:02d}:{TARGET_MINUTE:02d}"

# Días de semana en los que quieres clases:
# 0 = lunes, 1 = martes, 2 = miércoles, 3 = jueves
TARGET_CLASS_WEEKDAYS = {0, 1, 2, 3}
