# reservation_bot/scheduler.py
from datetime import datetime, time
import time as time_module

from config import TZ_MADRID, TARGET_HOUR, TARGET_MINUTE


def wait_until_target_time():
    """
    Espera hasta la hora objetivo (20:00 hora Madrid) del día actual.
    Si ya se ha pasado la hora, no espera.
    """
    now = datetime.now(TZ_MADRID)
    target = datetime.combine(
        now.date(),
        time(TARGET_HOUR, TARGET_MINUTE, tzinfo=TZ_MADRID),
    )

    if now >= target:
        print("[WARN] Ya hemos pasado la hora objetivo, no espero.")
        return

    delta = (target - now).total_seconds()
    print(f"[INFO] Esperando {delta:.1f} segundos hasta la hora objetivo ({target}).")
    time_module.sleep(delta)
