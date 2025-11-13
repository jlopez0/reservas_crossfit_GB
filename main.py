# reservation_bot/main.py
from datetime import date
import time as time_module

from dates import today_madrid, compute_target_date
from crosshero_client import (
    get_session,
    fetch_classes_html_for_date,
    get_class_id_and_token_for_time,
    reserve_class_with_retries,
    is_login_page,
)
from scheduler import wait_until_target_time
from config import TARGET_TIME_STR, get_program_id_for_weekday


def fetch_class_id_with_retries(session, target_date: date, program_id: str,
                                max_attempts: int = 4, delay_seconds: int = 4):
    """
    Intenta obtener el class_id y authenticity_token para la hora objetivo,
    con reintentos cada pocos segundos.

    Se usa después de haber esperado hasta la hora objetivo, para cubrir
    el caso en que la clase aparezca justo al abrirse la reserva.
    """
    for attempt in range(1, max_attempts + 1):
        print(f"[INFO] Intento {attempt}/{max_attempts} de obtener clase para {target_date} "
              f"(program_id={program_id}, hora={TARGET_TIME_STR})")

        try:
            html = fetch_classes_html_for_date(session, target_date, program_id)
        except Exception as e:
            print(f"[WARN] Error al obtener HTML de clases (intento {attempt}): {e}")
            if attempt == max_attempts:
                print("[ERROR] No se pudo obtener la lista de clases tras varios intentos.")
                return None, None
            time_module.sleep(delay_seconds)
            continue

        if is_login_page(html):
            print("[ERROR] Parece que la sesión es inválida o ha caducado.")
            print("[ERROR] Actualiza SESSION_COOKIE con una cookie de sesión válida.")
            return None, None

        class_id, token = get_class_id_and_token_for_time(html, TARGET_TIME_STR)
        print(f"[DEBUG] class_id encontrado: {class_id}, token presente: {bool(token)}")

        if class_id and token:
            return class_id, token

        print(f"[WARN] No se encontró clase a la hora objetivo en el intento {attempt}. "
              f"Reintentando en {delay_seconds} segundos...")
        if attempt < max_attempts:
            time_module.sleep(delay_seconds)

    print("[ERROR] No se encontró clase a la hora objetivo tras varios intentos.")
    return None, None


def main():
    # 1) Decidir si hoy toca reservar
    today = today_madrid()
    print(f"[INFO] Hoy (Madrid): {today}")

    target_date: date | None = compute_target_date(today)
    if target_date is None:
        print("[INFO] Hoy no toca reservar (el día objetivo no es uno de los días configurados).")
        return

    weekday = target_date.weekday()
    program_id = get_program_id_for_weekday(weekday)

    print(f"[INFO] Hoy toca reservar para la fecha objetivo: {target_date} (weekday={weekday})")
    print(f"[INFO] Usando program_id={program_id} para esa fecha.")
    print(f"[INFO] Hora de clase objetivo: {TARGET_TIME_STR}")

    # 2) Crear sesión autenticada
    session = get_session()

    # 3) Esperar hasta las 20:00 (o la hora que hayas configurado)
    wait_until_target_time()

    # 4) Justo después de la hora objetivo, intentar obtener la clase concreta (con reintentos)
    class_id, authenticity_token = fetch_class_id_with_retries(session, target_date, program_id)

    if not class_id:
        print("[ERROR] No se encontró class_id para la hora objetivo, no se realiza reserva.")
        return

    if not authenticity_token:
        print("[ERROR] No se encontró authenticity_token, no se realiza reserva.")
        return

    # 5) Lanzar reserva con reintentos
    resp = reserve_class_with_retries(session, class_id, authenticity_token)

    if resp is None:
        print("[ERROR] No se obtuvo respuesta válida del servidor al intentar reservar.")
        return

    status = resp.status_code
    body_preview = resp.text[:500]

    print(f"[DEBUG] Status HTTP de la reserva: {status}")
    print(f"[DEBUG] URL final: {resp.url}")
    
    if 200 <= status < 400:
        print(f"[SUCCESS] Reserva lanzada con éxito aparente para fecha {target_date} "
              f"a las {TARGET_TIME_STR}. Status HTTP: {status}")
        print("[DEBUG] Respuesta (primeros 500 chars):")
        print(body_preview)
        
        # Buscar indicadores de éxito/error en el HTML
        if "reserva" in resp.text.lower() or "reservation" in resp.text.lower():
            print("[DEBUG] ✓ La respuesta menciona 'reserva'")
        if "error" in resp.text.lower():
            print("[WARN] ⚠ La respuesta contiene 'error'")
        if "éxito" in resp.text.lower() or "success" in resp.text.lower():
            print("[DEBUG] ✓ La respuesta contiene palabras de éxito")
    else:
        print(f"[ERROR] La reserva devolvió un status HTTP no exitoso: {status}")
        print("[ERROR] Respuesta (primeros 500 chars):")
        print(body_preview)


if __name__ == "__main__":
    main()
