# reservation_bot/scheduler.py
from datetime import datetime, time
import time as time_module
import os
import sys

from config import TZ_MADRID, TARGET_HOUR, TARGET_MINUTE


def wait_until_target_time():
    """
    Espera hasta la hora objetivo (por defecto 20:00 hora Madrid) del día actual.
    - Si ya se ha pasado la hora, retorna inmediatamente.
    - Para evitar que CI/CD parezca 'colgado', hace `heartbeats` periódicos (print)
      cada HEARTBEAT_INTERVAL segundos mientras espera.
    - Si el tiempo a esperar excede MAX_WAIT_SECONDS (por defecto 2h), se
      aborta pronto y deja que el workflow/usuario lo reprograme.

    Comportamiento configurable vía variables de entorno:
    - MAX_WAIT_SECONDS (int): máximo número de segundos a esperar (por defecto 7200).
    - HEARTBEAT_INTERVAL (int): intervalo de heartbeat en segundos (por defecto 60).
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

    # Configurables por entorno
    try:
        MAX_WAIT = int(os.getenv("MAX_WAIT_SECONDS", "7200"))
    except Exception:
        MAX_WAIT = 7200
    try:
        HEARTBEAT = int(os.getenv("HEARTBEAT_INTERVAL", "60"))
    except Exception:
        HEARTBEAT = 60

    if delta > MAX_WAIT:
        print(f"[WARN] Tiempo hasta la hora objetivo demasiado largo ({delta:.0f}s) > MAX_WAIT_SECONDS={MAX_WAIT}.\n" \
              "Para ejecuciones manuales en CI evita sleeps largos: reprograma el workflow o ajusta la hora de inicio.")
        # Salimos sin esperar para evitar jobs largos en CI.
        return

    remaining = delta
    print(f"[INFO] Esperando {remaining:.1f} segundos hasta la hora objetivo ({target}). Heartbeat cada {HEARTBEAT}s.")
    # Espera en trozos pequeños e imprime heartbeats para que CI muestre actividad
    while remaining > 0:
        sleep_for = min(HEARTBEAT, remaining)
        print(f"[INFO] Faltan {remaining:.0f}s hasta la hora objetivo. Durmiendo {int(sleep_for)}s...")
        try:
            time_module.sleep(sleep_for)
        except KeyboardInterrupt:
            print("[WARN] Sleep interrumpido por KeyboardInterrupt, continuando.")
            return
        remaining -= sleep_for

    print("[INFO] Hora objetivo alcanzada, continuando con el flujo de reserva.")
