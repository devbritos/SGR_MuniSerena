# Sistema de Gestión de Resultados (SGR)

Aplicación web desarrollada con Django para apoyar el seguimiento de la gestión de funcionarios y delegaciones municipales de La Serena. Permite administrar información del personal, registrar actividades y evidencias, gestionar compromisos y consultar indicadores de avance.

Este proyecto fue desarrollado para la asignatura Programación Back End (TI3041), INACAP, sede La Serena.

## Funcionalidades

- Administración de funcionarios, delegaciones, cargos, roles y asignaciones de roles.
- Registro y seguimiento de actividades y sus evidencias, con un flujo de validación.
- Gestión de compromisos y sus fechas.
- Configuración de períodos, mediciones y metas.
- Registro e historial de atención ciudadana con tipo y subatención dependiente.
- Paneles de seguimiento con indicadores para administración y funcionarios.
- Inicio de sesión y permisos según la cuenta y el rol.
- Páginas personalizadas para errores 403 y 404.

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

   Genera una clave secreta fuerte con `python -c "import secrets; print(secrets.token_urlsafe(50))"` y copia el resultado en `SECRET_KEY`. Completa las variables de base de datos. En desarrollo puedes poner `DEBUG=True`; en AWS debe quedar `DEBUG=False`. No compartas ni subas `.env` al repositorio.

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

## Secciones principales

| Sección | Ruta local | Descripción |
|---|---|---|
| Personal | `/personal/` | Funcionarios, delegaciones, cargos y roles |
| Actividades | `/activities/` | Actividades, evidencias y validación |
| Agenda | `/agenda/` | Compromisos |
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
| `configuration` | Períodos, mediciones y metas |
| `analytics` | Paneles e indicadores de seguimiento |
| `atenciones` | Tipos, subatenciones y transacciones de atención ciudadana |

## Pruebas

Ejecuta la suite de pruebas con:

```powershell
python manage.py test
```

## Configuración y despliegue

La aplicación carga sus variables desde `.env`. `SECRET_KEY` es obligatoria; por compatibilidad, también se reconoce el nombre antiguo `SECRETKEY`. Usa una clave aleatoria larga y secreta, y cámbiala manualmente antes de desplegar porque la clave configurada actualmente no pasa la comprobación de seguridad de Django. Cambiarla invalida las sesiones y firmas existentes. La conexión requiere `DB_NAME`, `DB_USER` y `DB_HOST`; `DB_PASSWORD` puede quedar vacío si el servidor local no usa contraseña y `DB_PORT` usa `3306` por defecto.

`DEBUG` está desactivado por defecto. `ALLOWED_HOSTS` acepta una lista separada por comas y por defecto contempla la IP usada actualmente y las direcciones locales. Si el servidor usa un dominio, configura ese dominio en `ALLOWED_HOSTS` y su origen completo (incluyendo `https://`) en `CSRF_TRUSTED_ORIGINS`.

### Preparar el servidor AWS

En el servidor, instala las dependencias, configura un `.env` con los valores privados del entorno, y luego ejecuta:

```bash
python manage.py check --deploy
python manage.py migrate
python manage.py collectstatic --noinput
gunicorn config.wsgi:application --bind 0.0.0.0:8000
```

Ejecuta Gunicorn como servicio detrás de un proxy web (por ejemplo, Nginx) y permite en el grupo de seguridad solo el tráfico necesario. WhiteNoise sirve los archivos estáticos recopilados por `collectstatic`, incluidos los logos y recursos de la interfaz. Las evidencias subidas se guardan en `MEDIA_ROOT`; en AWS configura almacenamiento persistente o un servicio de objetos como S3 y sirve esos archivos de forma segura.

No actives `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` ni HSTS mientras el sitio solo use HTTP. Una vez configurado y probado HTTPS, habilita esas opciones en el `.env` y aumenta `SECURE_HSTS_SECONDS` gradualmente.

## Estructura del repositorio

```text
config/          Configuración y rutas principales de Django
core/            Componentes compartidos
personal/        Gestión del personal municipal
activities/      Actividades y evidencias
agenda/          Compromisos
configuration/   Períodos, mediciones y metas
analytics/       Paneles e indicadores
atenciones/      Atención ciudadana y sus catálogos
templates/       Plantillas HTML compartidas y páginas de error
static/          Archivos estáticos
```
