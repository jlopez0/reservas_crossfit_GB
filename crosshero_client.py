# reservation_bot/crosshero_client.py
from datetime import date
from typing import Optional, Tuple, Dict

import requests
from requests.exceptions import RequestException
from bs4 import BeautifulSoup

from config import (
    BASE_URL,
    SESSION_COOKIE,
    SESSION_COOKIE_NAME,
    TARGET_TIME_STR,
)


def get_session() -> requests.Session:
    """Crea una sesión de requests con la cookie de CrossHero configurada."""
    if not SESSION_COOKIE:
        raise RuntimeError(
            "SESSION_COOKIE no está definida. "
            "Configura la variable de entorno SESSION_COOKIE con el valor de _crosshero_session."
        )

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Reservation Bot)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-ES,es;q=0.9",
    })
    # Ajusta el dominio si fuera necesario, aquí vale "crosshero.com"
    session.cookies.set(SESSION_COOKIE_NAME, SESSION_COOKIE, domain="crosshero.com")
    return session


def format_date_for_crosshero(d: date) -> str:
    """
    Formato que usa CrossHero en el parámetro 'date':
    Ejemplo: 'Vie 14/11/2025'
    """
    dias_cortos_es = {
        0: "Lun",
        1: "Mar",
        2: "Mié",
        3: "Jue",
        4: "Vie",
        5: "Sáb",
        6: "Dom",
    }
    dow = d.weekday()
    dow_str = dias_cortos_es[dow]
    return f"{dow_str} {d:%d/%m/%Y}"


def fetch_classes_html_for_date(
    session: requests.Session,
    d: date,
    program_id: str,
) -> str:
    """
    Hace el GET a /dashboard/classes para una fecha concreta y un program_id concreto.
    NO tiene reintentos aquí; se gestionan en el nivel superior.
    """
    date_str = format_date_for_crosshero(d)
    params = {
        "date": date_str,
        "program_id": program_id,
    }
    url = f"{BASE_URL}/dashboard/classes"
    print(f"[INFO] GET {url} params={params}")
    resp = session.get(url, params=params, timeout=10)
    print(f"[DEBUG] Status clases: {resp.status_code}")
    print(f"[DEBUG] Longitud HTML: {len(resp.text)} caracteres")
    
    # Guardar HTML para debug (útil para inspección manual)
    with open("debug_classes.html", "w", encoding="utf-8") as f:
        f.write(resp.text)
    print(f"[DEBUG] HTML guardado en debug_classes.html")
    
    resp.raise_for_status()
    return resp.text


def parse_classes_and_token(html: str) -> Tuple[Dict[str, str], Optional[str]]:
    """
    Parsea el HTML devuelto por /dashboard/classes y devuelve:
      - dict de horas -> id de clase
      - authenticity_token
    """
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        # Fallback to built-in parser if lxml is not available
        soup = BeautifulSoup(html, "html.parser")

    # authenticity_token (hidden típico de Rails)
    token_input = soup.find("input", attrs={"name": "authenticity_token"})
    authenticity_token = token_input["value"] if token_input and token_input.has_attr("value") else None

    # Mapa de horas -> ID
    classes_by_time: Dict[str, str] = {}
    select = soup.find("select", id="class_reservation_single_class_id")
    if select:
        for option in select.find_all("option"):
            value = option.get("value")
            text = (option.text or "").strip()
            if not value or not text:
                continue
            classes_by_time[text] = value

    return classes_by_time, authenticity_token


def get_class_id_and_token_for_time(
    html: str,
    target_time: str = TARGET_TIME_STR,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Dado el HTML de /dashboard/classes, devuelve:
      - ID de la clase para la hora target_time (ej. "20:00")
      - authenticity_token
    """
    classes_by_time, token = parse_classes_and_token(html)
    return classes_by_time.get(target_time), token


def is_login_page(html: str) -> bool:
    """
    Intenta detectar si el HTML corresponde a la página de login
    (sesión caducada / cookie inválida).
    """
    # Comprobaciones simples; se pueden ajustar si cambia el texto
    markers = [
        "Iniciar sesión",
        "/athletes/sign_in",
        "athlete[email]",
        "athlete[password]",
    ]
    lowered = html.lower()
    return any(m.lower() in lowered for m in markers)


def reserve_class_with_retries(
    session: requests.Session,
    class_id: str,
    authenticity_token: str,
    max_attempts: int = 3,
    timeout: int = 10,
) -> Optional[requests.Response]:
    """
    Hace el POST a /dashboard/class_reservations con reintentos en caso de timeout/5xx.
    Devuelve la última Response exitosa o None si todas fallan.
    """
    url = f"{BASE_URL}/dashboard/class_reservations"
    data = {
        "authenticity_token": authenticity_token,
        "redirect_to": "",
        "fullscreen": "",
        "class_reservation[single_class_id]": class_id,
    }

    for attempt in range(1, max_attempts + 3):
        print(f"[INFO] POST intento {attempt}/{max_attempts} {url}")
        print(f"[DEBUG] Datos enviados: {data}")
        print(f"[DEBUG] Timeout configurado: {timeout}s")
        
        try:
            resp = session.post(url, data=data, timeout=timeout)
        except RequestException as e:
            print(f"[WARN] Error de red en POST (intento {attempt}): {e}")
            if attempt == max_attempts:
                print("[ERROR] No se pudo completar la reserva tras varios intentos.")
                return None
            continue

        status = resp.status_code
        print(f"[DEBUG] Status reserva intento {attempt}: {status}")
        print(f"[DEBUG] Tiempo de respuesta: {resp.elapsed.total_seconds():.2f}s")
        
        # Mostrar solo una vista previa de la respuesta
        body_preview = resp.text[:300]
        print(f"[DEBUG] Vista previa respuesta intento {attempt}: {body_preview}")

        # Si es 5xx, reintento
        if 500 <= status <= 599:
            print(f"[WARN] Respuesta 5xx del servidor (intento {attempt}).")
            if attempt == max_attempts:
                print("[ERROR] No se pudo completar la reserva tras varios intentos (5xx).")
                return resp
            continue

        # Para 2xx-4xx devolvemos la respuesta tal cual (no reintento más)
        return resp

    # Teóricamente no llegamos aquí, pero por si acaso:
    return None
