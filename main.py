# reservation_bot/main.py
from datetime import date
import time as time_module
from typing import Optional

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


def analyze_reservation_response(response_text: str, status_code: int) -> tuple[bool, str]:
    """
    Analiza la respuesta del servidor para determinar si la reserva fue exitosa.
    
    Returns:
        tuple[bool, str]: (is_success, message)
    """
    text_lower = response_text.lower()
    
    # Indicadores de éxito específicos de CrossHero
    success_indicators = [
        "éxito", "success", "reserva realizada", "reservation confirmed",
        "reserva confirmada", "booking confirmed", "tu reserva ha sido",
        "reserva completada", "booking successful"
    ]
    
    # Indicadores de error específicos
    error_indicators = [
        "error", "no se pudo", "failed", "unable", "problema",
        "no disponible", "not available", "ya reservado", "already booked",
        "cupo completo", "full capacity", "sin disponibilidad"
    ]
    
    has_success = any(indicator in text_lower for indicator in success_indicators)
    has_error = any(indicator in text_lower for indicator in error_indicators)
    
    # Priorizar éxito sobre error - si hay indicadores de éxito, es éxito
    if has_success:
        if has_error:
            return True, "Reserva confirmada - encontrados indicadores de éxito (ignorando menciones de 'error' en el HTML)"
        else:
            return True, "Reserva confirmada - encontrados indicadores de éxito"
    elif has_error:
        return False, "Error detectado en la respuesta"
    elif 200 <= status_code < 400:
        return None, "Status HTTP exitoso pero sin indicadores claros de éxito/error"
    else:
        return False, f"Status HTTP de error: {status_code}"


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

    target_date: Optional[date] = compute_target_date(today)
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

    print(f"[DEBUG] Status HTTP de la reserva: {status}")
    print(f"[DEBUG] URL final: {resp.url}")
    
    # Analizar el contenido de la respuesta para determinar éxito real
    is_success, message = analyze_reservation_response(resp.text, status)
    
    # Solo mostrar contenido útil de la respuesta
    response_lower = resp.text.lower()
    relevant_content = []
    
    # Buscar líneas que contengan palabras clave relevantes
    for line in resp.text.split('\n'):
        line_lower = line.strip().lower()
        if any(keyword in line_lower for keyword in ['éxito', 'success', 'reserva', 'error', 'problema', 'confirmad']):
            if line.strip() and not line.strip().startswith('<script') and not line.strip().startswith('<!--'):
                relevant_content.append(line.strip()[:100])  # Máximo 100 chars por línea
    
    if relevant_content:
        print("[DEBUG] Contenido relevante de la respuesta:")
        for content in relevant_content[:5]:  # Máximo 5 líneas relevantes
            print(f"  {content}")
    else:
        print("[DEBUG] No se encontró contenido textual relevante en la respuesta")
    
    if is_success is True:
        print("[SUCCESS] ✅ ¡RESERVA CONFIRMADA!")
        print(f"[SUCCESS] {message}")
        print(f"[SUCCESS] Reserva exitosa para fecha {target_date} a las {TARGET_TIME_STR}")
        print("[DEBUG] ✓ La respuesta contiene palabras de éxito")
        
        # Solo mostrar logs adicionales si es útil para debugging
        if "reserva" in resp.text.lower() or "reservation" in resp.text.lower():
            print("[DEBUG] ✓ La respuesta menciona 'reserva'")
        
    elif is_success is False:
        print("[ERROR] ❌ RESERVA FALLIDA")
        print(f"[ERROR] {message}")
        if 200 <= status < 400:
            print("[ERROR] Aunque el status HTTP sea exitoso, el contenido indica fallo")
            
        # Mostrar logs adicionales para debugging de errores
        if "error" in resp.text.lower():
            print("[DEBUG] La respuesta contiene 'error'")
            
    else:  # is_success is None
        print("[WARN] ⚠️ RESULTADO INCIERTO")
        print(f"[WARN] {message}")
        print("[WARN] Revisa manualmente si la reserva fue exitosa")
        
        # Log adicional para debugging de casos inciertos
        if "reserva" in resp.text.lower() or "reservation" in resp.text.lower():
            print("[DEBUG] ✓ La respuesta menciona 'reserva'")
        if "error" in resp.text.lower():
            print("[WARN] ⚠ La respuesta contiene 'error'")


if __name__ == "__main__":
    main()
