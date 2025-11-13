# CrossHero Auto Reservation Bot

Este proyecto es un bot en Python pensado para automatizar reservas de clases en CrossHero usando solo peticiones HTTP (`requests`), sin Selenium.

## Objetivo funcional

- El bot se ejecuta **una vez al día** (normalmente mediante GitHub Actions).
- Calcula una **fecha objetivo = hoy + 3 días**.
- Solo intenta reservar si la fecha objetivo cae en **lunes, martes, miércoles o jueves**:
  - Lunes (0), martes (1), jueves (3) → usa `PROGRAM_ID_MTT = 5a6f2ebea8efdc0006f8656a`.
  - Miércoles (2) → usa `PROGRAM_ID_WED = 5c3cce31ab433d003b87a6f9`.
- Intenta reservar la clase de la **hora objetivo** (por defecto `20:00` hora Madrid).
- A nivel de negocio: por ejemplo, el viernes a las 20:00 se reservaría el lunes, el sábado el martes, el domingo el miércoles, etc.

## Flujo principal del bot

1. **Determinar si toca reservar hoy**
   - Se obtiene la fecha actual en zona horaria `Europe/Madrid`.
   - Se calcula la fecha objetivo como `hoy + 3 días`.
   - Si el `weekday` de la fecha objetivo no está en `{0,1,2,3}` (lunes, martes, miércoles, jueves), el bot termina sin hacer nada.

2. **Seleccionar `program_id` según el día objetivo**
   - Según el `weekday` de la fecha objetivo:
     - Si es miércoles → `PROGRAM_ID_WED`.
     - En otro caso (lunes, martes, jueves) → `PROGRAM_ID_MTT`.

3. **Crear sesión autenticada**
   - Se usa un `requests.Session()` configurado con:
     - Cabeceras tipo navegador.
     - Cookie de sesión `_crosshero_session` leída de la variable de entorno `SESSION_COOKIE`.
   - No se hace login ni se bypassea el CAPTCHA; se reutiliza una sesión legítima creada manualmente en el navegador y copiada al bot.

4. **Esperar hasta la hora objetivo**
   - La función `wait_until_target_time()` espera hasta las **20:00 hora Madrid** (o la hora configurada vía `TARGET_HOUR` / `TARGET_MINUTE`).
   - Esto permite lanzar el workflow antes (p. ej. 18:50 UTC) y que el script se quede “en stand-by” hasta la hora real de apertura de reservas.

5. **Obtener la clase concreta justo en el momento de apertura**
   - Después de llegar a la hora objetivo, el bot llama a:
     `GET /dashboard/classes?date=<fecha_formateada>&program_id=<program_id>`
   - El parámetro `date` va en formato tipo: `Vie 14/11/2025`.
   - La respuesta es un HTML que contiene:
     - Un `<select id="class_reservation_single_class_id">` con `<option value="<id_clase>">HH:MM</option>` para cada horario.
     - Un `<input type="hidden" name="authenticity_token" value="...">` típico de Rails.

6. **Reintentos al obtener la clase**
   - Hay una función que intenta varias veces (con pequeños delays) extraer:
     - El `class_id` para la hora objetivo (por defecto `"20:00"`).
     - El `authenticity_token`.
   - Entre intentos se vuelve a hacer `GET /dashboard/classes` para cubrir el caso de que la clase aparezca justo en el momento de apertura.
   - Además:
     - Se detecta si el HTML recibido parece ser la página de login (`Iniciar sesión`, `athlete[email]`, etc.).
     - En ese caso se loguea claramente que la **sesión ha caducado** y se pide actualizar `SESSION_COOKIE`.

7. **Reserva de la clase**
   - Una vez obtenidos `class_id` y `authenticity_token`, se hace:
     `POST /dashboard/class_reservations`
     con un body `application/x-www-form-urlencoded` equivalente al curl original:
     - `authenticity_token=<token>`
     - `redirect_to=`
     - `fullscreen=`
     - `class_reservation[single_class_id]=<class_id>`

8. **Reintentos en el POST**
   - El POST tiene una pequeña lógica de reintentos:
     - Si hay errores de red (timeout, etc) o respuestas 5xx, se reintenta hasta un número máximo de intentos.
     - Para respuestas 2xx–4xx, se devuelve tal cual para que el código superior decida.
   - Se loguean claramente:
     - `[SUCCESS]` si la reserva parece correcta (status 2xx/3xx).
     - `[ERROR]` si no se ha podido reservar.

## Módulos principales

- `config.py`
  - Configuración global: cookies, URL base, zona horaria, hora objetivo, mapping de `weekday -> program_id`.
  - `get_program_id_for_weekday(weekday)` selecciona el `program_id` adecuado.

- `dates.py`
  - Funciones relacionadas con fechas.
  - `today_madrid()` devuelve la fecha actual en zona `Europe/Madrid`.
  - `compute_target_date()` devuelve `hoy + 3 días` si ese día es uno de los días objetivo (L/M/X/J), o `None` si hoy no toca reservar.

- `scheduler.py`
  - `wait_until_target_time()` espera hasta la hora objetivo (por defecto 20:00 Madrid).

- `crosshero_client.py`
  - `get_session()` crea la sesión autenticada con `requests` y la cookie `_crosshero_session`.
  - `format_date_for_crosshero(date)` formatea la fecha como la necesita CrossHero (`"Vie 14/11/2025"`).
  - `fetch_classes_html_for_date(session, date, program_id)` hace el GET a `/dashboard/classes`.
  - `parse_classes_and_token(html)` parsea el HTML y devuelve:
    - Un diccionario `{ "HH:MM": "<class_id>" }`.
    - El `authenticity_token`.
  - `get_class_id_and_token_for_time(html, target_time)` devuelve `(class_id, authenticity_token)` para la hora objetivo.
  - `is_login_page(html)` intenta detectar si el HTML es la página de login (sesión caducada).
  - `reserve_class_with_retries(session, class_id, authenticity_token)` hace el POST a `/dashboard/class_reservations` con reintentos.

- `main.py`
  - Punto de entrada del bot.
  - Flujo:
    1. Calcula `target_date` = hoy + 3 días (si no toca reservar, sale).
    2. Determina el `program_id` para esa fecha.
    3. Crea la sesión autenticada.
    4. Espera hasta la hora objetivo.
    5. Llama a una función que intenta varias veces (GET + parseo) obtener `class_id` y `authenticity_token`.
    6. Llama a `reserve_class_with_retries` para realizar la reserva.
    7. Loguea resultado final con `[SUCCESS]` o `[ERROR]`.

## Integración con GitHub Actions

- Existe un workflow en `.github/workflows/reservation.yml` que:
  - Se ejecuta diariamente a una hora fija en UTC (por ejemplo `18:50 UTC` ≈ `19:50 Madrid` en invierno).
  - Instala dependencias (`requirements.txt`).
  - Ejecuta `python -m reservation_bot.main`.
  - Pasa la cookie de sesión como secreto (`SESSION_COOKIE`) y otros parámetros (`BASE_URL`, `PROGRAM_ID_MTT`, `PROGRAM_ID_WED`, etc.).

## Consideraciones importantes

- El bot **no hace login ni resuelve captchas**. Depende de que el usuario:
  - Se loguee en CrossHero en el navegador.
  - Copie el valor de la cookie `_crosshero_session` a la variable de entorno `SESSION_COOKIE` (o al secreto de GitHub).
- Si la sesión caduca o la cookie deja de ser válida:
  - El HTML de `/dashboard/classes` se convertirá en la página de login.
  - El bot detectará esto y lo indicará en los logs para renovar la cookie.
- El sistema es frágil ante cambios de:
  - HTML de la web (IDs de elementos, nombres de campos).
  - Endpoints (`/dashboard/classes`, `/dashboard/class_reservations`).
  - Formato de la hora (`"20:00"`).

Este contexto describe la intención del proyecto, sus módulos principales, el flujo de reserva y cómo se integra todo, para que cualquier herramienta de autocompletado (como GitHub Copilot) pueda sugerir código coherente y alineado con el diseño actual.
