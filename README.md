# Sistema de Gestión de Resultados (SGR)

Aplicación web desarrollada con Django para apoyar el seguimiento de la gestión de funcionarios y delegaciones municipales de La Serena. Permite administrar información del personal, registrar actividades y evidencias, gestionar compromisos y consultar indicadores de avance.

Este proyecto fue desarrollado para la asignatura Programación Back End (TI3041), INACAP, sede La Serena.

## Funcionalidades

- Administración de funcionarios, delegaciones, cargos, roles y asignaciones de roles.
- Registro y seguimiento de actividades y sus evidencias, con un flujo de validación.
- Gestión de compromisos y sus fechas.
- Seguimiento de cartas de Oficina de Partes, con derivaciones, responsables y estados.
- Control de eventos comunitarios informativos o con inscripción, con imagen de portada, ficha modal de detalles, cupos y tutores de menores.
- Configuración de períodos, mediciones y metas.
- Registro e historial de atención ciudadana con tipo y subatención dependiente.
- Paneles de seguimiento con indicadores para administración y funcionarios.
- Actualización en tiempo real de las páginas abiertas cuando se modifican datos.
- Inicio de sesión y permisos según la cuenta y el rol.
- Páginas personalizadas para errores HTTP 400, 403, 404 y 500, también en desarrollo.

## Tecnologías

- Python
- Django 5.2
- MySQL o MariaDB
- `mysqlclient` para la conexión a la base de datos
- Bootstrap 5 y `django-crispy-forms` para los formularios

## Requisitos

- Python compatible con Django 5.2.
- MySQL o MariaDB en ejecución, con una base de datos creada para el proyecto.
- Git.

## Instalación local en Windows

1. Clona el repositorio y entra a su carpeta:

   ```powershell
   git clone https://github.com/devbritos/Django_Back.git
   cd Django_Back
   ```

2. Crea y activa un entorno virtual:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

3. Instala las dependencias:

   ```powershell
   python -m pip install -r requirements.txt
   ```

4. Copia el archivo de ejemplo y configura `.env` con los valores de tu entorno:

   ```powershell
   Copy-Item .env.example .env
   ```

   Genera una clave secreta fuerte con `python -c "import secrets; print(secrets.token_urlsafe(50))"` y copia el resultado en `SECRET_KEY`. Completa las variables de base de datos. En desarrollo puedes dejar `DEBUG=True`; en AWS debe quedar `DEBUG=False`. `CUSTOM_ERROR_PAGES_IN_DEBUG=True` muestra las páginas del proyecto incluso en desarrollo; define `False` temporalmente si necesitas las páginas técnicas de Django. Los detalles de errores 500 permanecen en la consola del servidor y no se muestran al usuario. Para cargar las cuentas de prueba, define `SEED_USER_PASSWORD` con una contraseña robusta de al menos 16 caracteres. No compartas ni subas `.env` al repositorio.

   En desarrollo (`DEBUG=True`) las actualizaciones en tiempo real usan un canal en memoria. Para producción, configura `REDIS_URL` con la dirección de un Redis accesible por la aplicación, por ejemplo `redis://localhost:6379/0`.

### Semillas de prueba

Con `DEBUG=True` y `SEED_USER_PASSWORD` configurada, ejecuta:

```powershell
python manage.py poblar_bd
```

El comando crea hasta 2.000 registros marcados y reproducibles: 1.000 atenciones, 400 compromisos, 400 actividades y 200 evidencias. Al repetirlo, conserva los registros existentes y solo agrega los que faltan; no elimina datos. También deja seis cuentas locales listas: `admin@sgr.cl`, `coordinador@sgr.cl`, `delegado@sgr.cl`, `funcionario@sgr.cl`, `verificador@sgr.cl` y `consulta@sgr.cl`. Las seis usan el valor configurado en `SEED_USER_PASSWORD`. El comando se niega a ejecutarse con `DEBUG=False` y no contiene una contraseña predeterminada.

5. Comprueba la configuración y crea las tablas:

   ```powershell
   python manage.py check
   python manage.py migrate
   ```

6. Crea una cuenta administradora para acceder al sistema:

   ```powershell
   python manage.py createsuperuser
   ```

7. Inicia el servidor de desarrollo:

   ```powershell
   python manage.py runserver
   ```

Abre `http://127.0.0.1:8000/` para entrar al sistema o `http://127.0.0.1:8000/admin/` para usar el administrador de Django.

## Recuperación de contraseña por correo

La pantalla `¿Olvidaste tu contraseña?` mantiene la recuperación estándar de Django mediante enlace seguro. También está disponible el flujo de código temporal de seis dígitos desde el inicio de sesión. El código vence según `PASSWORD_RESET_CODE_TIMEOUT` (600 segundos por defecto), es de un solo uso y se bloquea después de cinco intentos. La respuesta de solicitud es genérica para no revelar si una dirección está registrada.

- Sin `EMAIL_HOST`, Django usa el backend de consola y muestra el mensaje/enlace en la terminal; no llega a una bandeja de entrada.
- Para enviar correo real, configura en `.env` `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, `EMAIL_USE_SSL` y `DEFAULT_FROM_EMAIL`. El backend SMTP se selecciona automáticamente al configurar `EMAIL_HOST`.
- Para Gmail usa `smtp.gmail.com`, puerto `587`, TLS activado y una contraseña de aplicación de Google. No uses la contraseña normal de la cuenta. Otra opción es usar un proveedor SMTP transaccional.
- Reinicia Django/Gunicorn después de modificar `.env`. No publiques credenciales de correo.
- Las inscripciones a eventos verifican el correo con un enlace de 24 horas. En desarrollo el enlace aparece en la consola; en producción debe configurarse un SMTP real. El RUT se valida por formato y dígito verificador, y el teléfono solo por formato (no se envían SMS).
- La cartelera pública está separada del menú interno y del inicio de sesión en `/eventos/`. Cada evento puede tener una imagen JPG, PNG o WebP de hasta 5 MiB, y una sección “Qué habrá”; el modal público muestra descripción, actividades, fecha, lugar, delegación, cupos y plazo de inscripción.
- Cada evento puede ser “Requiere inscripción” o “Solo informativo”. Los informativos aparecen en la cartelera y en su modal, pero no muestran opciones para inscribirse; el servidor también rechaza el acceso directo al formulario.

## Seguimiento de atenciones ciudadanas

En `/atenciones/`, los accesos **Abiertas**, **Para hoy**, **Vencidas** y **Sin clasificar** permiten organizar las gestiones. La búsqueda y los filtros también se aplican al exportar a Excel.

Desde **Ver ficha** se registra una gestión, se asigna un responsable de la misma delegación y se programa la próxima acción. El historial conserva el autor, la fecha y los acuerdos de cada registro. Quien registró la atención conserva acceso y el responsable asignado también puede continuar su seguimiento.

Para cerrar se exige indicar un resultado y su detalle: solicitud resuelta, orientación entregada, derivación informada u otro resultado. El cierre elimina la próxima acción pendiente y deja el historial disponible para consulta. Si otra persona actualiza la atención mientras se completa el formulario, se conserva el texto y se solicita revisar los cambios antes de guardar nuevamente.

La ficha también permite **Crear compromiso** con solicitante, descripción y responsable precargados. Revisa los datos, indica el sector y la fecha de cumplimiento. Al guardar vuelve a la atención, muestra el compromiso vinculado y agrega una constancia al historial. Cada formulario evita duplicados si se reenvía; pueden crearse otros compromisos desde un formulario nuevo. Solo pueden asignarse funcionarios activos de la delegación de origen. Tanto quien registró la atención como los responsables vinculados pueden consultar la gestión. Cumplir el compromiso no cierra la atención automáticamente.

Esta vinculación requiere aplicar `python manage.py migrate agenda` antes de utilizarla. La migración `agenda.0004` agrega campos opcionales y conserva los compromisos existentes sin atención asociada.

### Cartas vinculadas a atenciones

El formulario de carta separa los datos de ingreso, remitente y asunto, y responsable. La recepción se completa con la fecha local de hoy y es editable; las nuevas cartas comienzan **En proceso**. Los datos de derivación, respuesta, fecha de actividad y observaciones están en **Información adicional (opcional)**, que se abre si tiene datos o errores. Los responsables se filtran por delegación con el catálogo incluido en el formulario, sin solicitudes adicionales. Cuando la delegación está fijada por la cuenta o por una atención vinculada, se muestra como contexto. Al registrar o editar se abre la ficha de la carta.

En **Seguimiento de cartas → Ver carta**, puedes **Crear atención desde esta carta** con remitente, contacto y asunto precargados, o **Vincular atención existente** mediante una búsqueda de las solicitudes de la misma delegación a las que tienes acceso. La clasificación y el responsable de seguimiento se confirman antes de crear la atención. Una carta tiene una atención principal; varias cartas del mismo asunto pueden vincularse a una atención existente.

Las dos fichas muestran el vínculo y la acción queda registrada en el historial de la atención. Los estados son independientes: finalizar la carta no cierra la atención ni viceversa. Las cartas informativas pueden mantenerse sin atención. Reenviar el formulario conserva la primera vinculación y evita crear duplicados. Las atenciones archivadas conservan su vínculo histórico.

Aplica `python manage.py migrate correspondence` antes de utilizar esta funcionalidad. La migración `correspondence.0002` agrega un vínculo opcional y conserva las cartas anteriores sin atención asociada.

La migración `atenciones.0002` conserva las atenciones anteriores como **Sin clasificar**; las nuevas comienzan **Pendientes**, con quien las registra como responsable inicial. Aplica la migración en la base de datos del entorno antes de utilizar esta funcionalidad:

```powershell
python manage.py migrate atenciones
```

## Secciones principales

Al iniciar sesión se activa el tema blanco y rojo y, en escritorio, el menú queda fijado. Puedes desfijarlo o cambiar el tema; la elección se conserva al navegar durante esa sesión. Un nuevo inicio de sesión restablece la presentación inicial. En pantallas pequeñas el menú permanece deslizable y no modifica la preferencia de escritorio. Las tarjetas del dashboard usan fondos blancos y acentos suaves en rojo, conservando los colores de alerta en los indicadores.

| Sección | Ruta local | Descripción |
|---|---|---|
| Personal | `/personal/` | Funcionarios, delegaciones, cargos y roles |
| Actividades | `/activities/` | Actividades, evidencias y validación |
| Agenda | `/agenda/` | Compromisos |
| Seguimiento de cartas | `/correspondencia/` | Cartas ingresadas por Oficina de Partes y su resolución |
| Eventos públicos | `/eventos/` | Eventos publicados e inscripción de personas y familias |
| Gestión de eventos | `/eventos/gestion/` | Eventos, padrón de personas e inscripciones de la delegación |
| Configuración | `/configuration/` | Ítems de medición, metas y períodos |
| Atención ciudadana | `/atenciones/` | Registro y consulta de atenciones y catálogos |
| Paneles | `/dashboard/` | Redirección al panel correspondiente al usuario |
| Administración Django | `/admin/` | Administración interna de Django |

## Aplicaciones Django

| Aplicación | Responsabilidad |
|---|---|
| `core` | Modelos y utilidades compartidas, incluidos los permisos |
| `personal` | Funcionarios, delegaciones, cargos, roles y sus asignaciones |
| `activities` | Actividades y evidencias |
| `agenda` | Compromisos |
| `correspondence` | Seguimiento de cartas de Oficina de Partes |
| `events` | Eventos comunitarios, padrón de personas e inscripciones |
| `configuration` | Períodos, mediciones y metas |
| `analytics` | Paneles e indicadores de seguimiento |
| `atenciones` | Tipos, subatenciones y transacciones de atención ciudadana |

## Pruebas

Ejecuta la suite de pruebas con:

```powershell
python manage.py test
```

Las pruebas específicas de cartas y eventos se pueden ejecutar con:

```powershell
python manage.py test correspondence
python manage.py test events
```

El plan, los resultados y las limitaciones conocidas están en
[`docs/plan_pruebas.md`](docs/plan_pruebas.md); la relación entre la rúbrica y
la evidencia disponible está en [`docs/alineacion_rubrica.md`](docs/alineacion_rubrica.md).

## Configuración y despliegue

La aplicación carga sus variables desde `.env`. `SECRET_KEY` es obligatoria; por compatibilidad, también se reconoce el nombre antiguo `SECRETKEY`. Usa una clave aleatoria larga y secreta, y cámbiala manualmente antes de desplegar porque la clave configurada actualmente no pasa la comprobación de seguridad de Django. Cambiarla invalida las sesiones y firmas existentes.

Para desarrollo local, si no se configura un host de base de datos real o si el puerto apunta a un servicio web (por ejemplo, 8000), el proyecto usa SQLite por defecto (`db.sqlite3`). Si se define una configuración válida de MySQL/MariaDB con `DB_HOST`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` y `DB_PORT` (3306 por defecto), entonces se usará esa conexión.

`DEBUG` está desactivado por defecto. `ALLOWED_HOSTS` acepta una lista separada por comas y por defecto contempla la IP usada actualmente y las direcciones locales. Si el servidor usa un dominio, configura ese dominio en `ALLOWED_HOSTS` y su origen completo (incluyendo `https://`) en `CSRF_TRUSTED_ORIGINS`.

Las páginas autenticadas reciben avisos por WebSocket cuando se modifican datos de las aplicaciones principales. El navegador solicita la página actual de forma asíncrona para mostrar los cambios y pospone la actualización si hay cambios sin guardar o un formulario modal abierto. Si un aviso se pierde o la conexión en tiempo real no está disponible, la página visible vuelve a sincronizarse automáticamente cada 15 segundos.

### Preparar el servidor AWS

En el servidor, instala las dependencias, configura un `.env` con los valores privados del entorno (incluido `REDIS_URL`), y luego ejecuta:

```bash
python manage.py check --deploy
python manage.py migrate
python manage.py collectstatic --noinput
daphne -b 0.0.0.0 -p 8000 config.asgi:application
```

Ejecuta Daphne como servicio ASGI (no `gunicorn config.wsgi:application`) detrás de un proxy web, por ejemplo Nginx. Si Nginx termina TLS y reenvía el tráfico a Daphne en el puerto 8000, configura tanto el sitio HTTP como la actualización de WebSocket:

```nginx
location /ws/ {
    proxy_pass http://127.0.0.1:8000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_read_timeout 86400;
}

location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

La regla `/ws/` debe estar en el mismo `server` que sirve la aplicación y llegar al mismo servicio Daphne que las páginas HTTP. No expongas Daphne directamente a Internet: permite el tráfico público solo al proxy en el grupo de seguridad. Redis debe estar disponible para todas las instancias de la aplicación; en AWS puedes usar un servicio administrado y mantenerlo en una red privada. WhiteNoise sirve los archivos estáticos recopilados por `collectstatic`, incluidos los logos y recursos de la interfaz. Las evidencias, fotos de perfil y demás archivos subidos se guardan en `MEDIA_ROOT`; en AWS configura almacenamiento persistente o un servicio de objetos como S3. La base de datos solo conserva la ruta de cada foto, por lo que conservar o migrar la base de datos sin los archivos de `MEDIA_ROOT` deja fotos guardadas que no se pueden mostrar. Publica únicamente las imágenes de eventos desde `MEDIA_ROOT/event_images/`; no expongas el directorio completo de medios, porque contiene evidencias y otros archivos que requieren acceso controlado.

No actives `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` ni HSTS mientras el sitio solo use HTTP. Una vez configurado y probado HTTPS, habilita esas opciones en el `.env` y aumenta `SECURE_HSTS_SECONDS` gradualmente.

## Estructura del repositorio

```text
config/          Configuración y rutas principales de Django
core/            Componentes compartidos
personal/        Gestión del personal municipal
activities/      Actividades y evidencias
agenda/          Compromisos
correspondence/   Seguimiento de cartas de Oficina de Partes
events/           Eventos comunitarios, padrón e inscripciones
configuration/   Períodos, mediciones y metas
analytics/       Paneles e indicadores
atenciones/      Atención ciudadana y sus catálogos
templates/       Plantillas HTML compartidas y páginas de error
static/          Archivos estáticos
docs/             Plan de pruebas y alineación con la rúbrica
```
