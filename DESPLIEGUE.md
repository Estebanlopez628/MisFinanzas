# Despliegue — Finanzas y OLB_BYTE

> Guía operativa para llevar la plataforma de desarrollo a producción.
> Stack: **Python + FastAPI + Jinja2 + SQLite (SQLAlchemy 2.x)**.
> Última revisión: 2026-11-13 · versión de la aplicación **1.0.0**.

---

## 1. Requisitos

| Elemento | Mínimo | Nota |
| --- | --- | --- |
| Python | 3.11 | 3.12 recomendado; el proyecto se probó con 3.11 y 3.12 en CI. |
| Sistema | Linux o Windows Server | Los comandos se muestran para ambos. |
| Disco | 1 GB | La base SQLite parte vacía (~0,2 MB) y crece con el historial. |
| Red | HTTPS | Obligatorio en producción: la cookie de sesión se marca `Secure`. |
| Proxy | Nginx, Caddy o IIS | Uvicorn no debe exponerse directamente a Internet. |

No se necesita Node.js, npm ni ningún empaquetador JavaScript.

---

## 2. Variables de entorno

| Variable | Por defecto | Obligatoria en producción | Descripción |
| --- | --- | --- | --- |
| `ENTORNO` | `desarrollo` | Sí (`produccion`) | Activa `secure` en la cookie, cierra `/docs` y exige clave secreta. |
| `CLAVE_SECRETA` | `cambiar-en-produccion` | **Sí, ≥ 32 caracteres** | Firma los JWT de sesión. Si falta o es corta, la aplicación no arranca. |
| `DATABASE_URL` | `sqlite:///backend/datos/finanzas.db` | No | En esta fase solo se admite SQLite. |
| `COOKIE_SEGURA` | según `ENTORNO` | No | `1` fuerza `Secure` también fuera de producción. |
| `PUBLICIDAD_ACTIVA` | `1` | No | `0` oculta el espacio publicitario. |
| `PUBLICIDAD_TEXTO` | texto por defecto | No | Copy del anuncio. |
| `PUBLICIDAD_URL` | vacío | No | Enlace del anuncio (`rel="sponsored noopener"`). |
| `LIMITE_INTENTOS_LOGIN` | `5` | No | Fallos por IP + correo antes del `429`. |
| `SMMLV` | `1750905` | No | Salario mínimo usado para el tope de 2 SMMLV. |
| `AUXILIO_TRANSPORTE` | `200000` | No | Valor del auxilio vigente. |
| `HORAS_MENSUALES` | `210` | No | Base de la hora ordinaria. |
| `PORCENTAJE_SALUD` | `0.04` | No | Aporte de salud del empleado. |
| `PORCENTAJE_PENSION` | `0.04` | No | Aporte de pensión del empleado. |
| `PORCENTAJE_PAGO_INCAPACIDAD` | `66.67` | No | Porcentaje reconocido por la EPS desde el día 3. |

Genera la clave con Python:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

> **Nunca** guardes `CLAVE_SECRETA` en el repositorio ni en capturas. Usa el
> gestor de secretos del servidor o un archivo `.env` con permisos restringidos.

---

## 3. Instalación

```bash
# 1. Copiar el proyecto al servidor
cd /opt
git clone <url-del-repositorio> olb-finanzas
cd olb-finanzas/backend

# 2. Entorno virtual e dependencias de ejecución (sin pytest)
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt

# 3. Definir variables de entorno (ejemplo Linux)
export ENTORNO=produccion
export CLAVE_SECRETA="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
export DATABASE_URL="sqlite:////opt/olb-finanzas/backend/datos/finanzas.db"

# 4. Primer arranque: crea el esquema y siembra las cuentas demo si la tabla
#    de usuarios está vacía.
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Verifica con `curl http://127.0.0.1:8000/salud`; debe responder
`{"estado":"ok","servicio":"Finanzas y OLB_BYTE"}`.

> ⚠️ **Cuentas demo.** Al primer arranque se crean `admin@olbbyte.co` /
> `Admin123*` y `usuario@finanzas.co` / `Usuario123*`. En producción, entra con
> la cuenta administradora y **cambia la contraseña de inmediato** desde
> *Mi perfil*. La siembra solo ocurre si la tabla `usuarios` está vacía.

---

## 4. Servicio en Linux (systemd)

`/etc/systemd/system/olb-finanzas.service`:

```ini
[Unit]
Description=Finanzas y OLB_BYTE
After=network.target

[Service]
Type=simple
User=olb
Group=olb
WorkingDirectory=/opt/olb-finanzas/backend
EnvironmentFile=/etc/olb-finanzas.env
ExecStart=/opt/olb-finanzas/backend/.venv/bin/python -m uvicorn app.main:app \
    --host 127.0.0.1 --port 8000 --workers 1
Restart=on-failure
RestartSec=5

# Endurecimiento básico
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ReadWritePaths=/opt/olb-finanzas/backend/datos /opt/olb-finanzas/backend/respaldos

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now olb-finanzas
sudo systemctl status olb-finanzas
```

**Un solo worker:** SQLite no admite escrituras concurrentes de varios
procesos. Cuando se migre a PostgreSQL se podrán usar varios workers o
`gunicorn -k uvicorn.workers.UvicornWorker`.

---

## 5. Servicio en Windows (NSSM o Programador de tareas)

Con [NSSM](https://nssm.cc/):

```powershell
nssm install OLBFinanzas "C:\olb-finanzas\backend\.venv\Scripts\python.exe" `
  "-m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1"
nssm set OLBFinanzas AppDirectory "C:\olb-finanzas\backend"
nssm set OLBFinanzas AppEnvironmentExtra ENTORNO=produccion
nssm set OLBFinanzas AppEnvironmentExtra CLAVE_SECRETA=<clave-de-48-caracteres>
nssm set OLBFinanzas Start SERVICE_AUTO_START
nssm start OLBFinanzas
```

Alternativa sin NSSM: crear una tarea en el **Programador de tareas** con
desencadenador *Al iniciar el equipo*, acción *Iniciar un programa* apuntando a
`.venv\Scripts\python.exe` y argumentos
`-m uvicorn app.main:app --host 127.0.0.1 --port 8000`.

---

## 6. Proxy inverso y HTTPS (Nginx)

```nginx
server {
    listen 80;
    server_name finanzas.ejemplo.co;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name finanzas.ejemplo.co;

    ssl_certificate     /etc/letsencrypt/live/finanzas.ejemplo.co/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/finanzas.ejemplo.co/privkey.pem;

    # El middleware CSRF compara `Origin` con el `Host` de la petición.
    # No reescribas el Host ni elimines cabeceras Origin/Sec-Fetch-Site.
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }
}
```

Certificado gratuito:

```bash
sudo certbot --nginx -d finanzas.ejemplo.co
```

---

## 7. Respaldo y restauración

El script `backend/scripts/respaldo.py` usa la API de respaldo de SQLite (copia
consistente aunque el servidor esté atendiendo peticiones), nombra cada copia
con fecha y microsegundos (`finanzas_AAAAMMDD_HHMMSS_microsegundos.db`), verifica
la integridad y rota las copias más antiguas:

```bash
cd /opt/olb-finanzas/backend
.venv/bin/python scripts/respaldo.py --destino /var/respaldos/olb --conservar 30
```

Programación diaria:

```cron
# Linux: todos los días a las 2:00 a. m.
0 2 * * * cd /opt/olb-finanzas/backend && .venv/bin/python scripts/respaldo.py --destino /var/respaldos/olb --conservar 30 >> /var/log/olb-respaldo.log 2>&1
```

Windows (Programador de tareas): acción
`C:\olb-finanzas\backend\.venv\Scripts\python.exe`, argumentos
`scripts\respaldo.py --destino D:\respaldos\olb --conservar 30`, iniciar en
`C:\olb-finanzas\backend`.

**Restauración:** detén el servicio, reemplaza
`backend/datos/finanzas.db` por la copia elegida y vuelve a arrancar. La
aplicación ejecuta `PRAGMA integrity_check` al crear cada respaldo y rechaza los
archivos corruptos.

> Guarda al menos una copia fuera del servidor (almacenamiento en frío o
> cifrado en la nube). Un respaldo en el mismo disco no protege de un fallo de
> hardware.

---

## 8. Verificación posterior al despliegue

1. `GET /salud` → `200` con `{"estado":"ok"}`.
2. `GET /docs` → **404** (en producción la documentación está apagada).
3. `GET /login` → `200` por HTTPS; la cookie de sesión debe incluir
   `Secure`, `HttpOnly` y `SameSite=Lax`.
4. `GET /olb-byte` sin sesión → `303 /login`; con `USER_FINANZAS` → `403`.
5. `GET /manifest.webmanifest` y `GET /sw.js` → `200`.
6. Cabeceras: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
   `Content-Security-Policy` con `frame-ancestors 'none'`.
7. Cambiar la contraseña de las dos cuentas demo.
8. Ejecutar el respaldo una vez y comprobar que el archivo abre con
   `sqlite3 <archivo> "PRAGMA integrity_check;"` → `ok`.

---

## 9. Lista de comprobación de seguridad

- [ ] `ENTORNO=produccion` y `CLAVE_SECRETA` de al menos 32 caracteres.
- [ ] HTTPS terminado en el proxy; sin acceso público directo a Uvicorn.
- [ ] `/docs` devuelve 404.
- [ ] Contraseñas demo cambiadas.
- [ ] `DATABASE_URL` apunta a una ruta con permisos solo para el usuario del servicio.
- [ ] Respaldos programados y copiados fuera del servidor.
- [ ] Registros del proxy y de systemd rotados (`logrotate`).
- [ ] Actualizaciones de dependencias revisadas con `pip list --outdated`.
- [ ] Acceso SSH restringido por clave; sin contraseña.

---

## 10. Integración continua

`.github/workflows/ci.yml` ejecuta en cada push y pull request:

1. `compileall` de `app`, `tests` y `scripts`.
2. `pytest` completo con base de datos temporal aislada.
3. Una prueba real de `scripts/respaldo.py` sobre la base creada por la app.

Para reproducir el CI en local:

```bash
cd backend
python -m compileall -q app tests scripts
python -m pytest -q
```

---

## 11. Migración futura a PostgreSQL

La aplicación ya usa SQLAlchemy 2.x y los identificadores/`Numeric` son
portables. Para migrar:

1. Añadir `alembic` y `psycopg` a `requirements.txt` (nuevo ADR en `MEMORY.md`).
2. Generar la migración inicial desde los modelos actuales (`alembic revision --autogenerate`).
3. Definir `DATABASE_URL=postgresql+psycopg://usuario:clave@host/olb`.
4. Migrar los datos con un script de exportación/importación validado contra
   `diccionario_datos.md`.
5. Solo entonces se podrá subir `--workers` por encima de 1.

---

## 12. Reversión (rollback)

1. Detén el servicio (`systemctl stop olb-finanzas` / `nssm stop OLBFinanzas`).
2. Restaura el código de la versión anterior.
3. Restaura el respaldo de base de datos previo al despliegue.
4. Arranca y repite la verificación de la sección 8.

Los respaldos diarios permiten además recuperar datos concretos sin revertir el
código: abre la copia con `sqlite3` y exporta las filas necesarias.

## 13. Factura y recibo como imagen PNG (ADR-50)

La factura y el recibo de abono se convierten en imagen PNG en el navegador con `html-to-image`, una librería que vive en `backend/app/static/js/vendor/html-to-image.js`. El servidor solo entrega la hoja en HTML. Por eso **ya no hace falta Chromium ni Playwright en el servidor**: el paso de compilación de Render no necesita instalar navegadores.

Para compartir, el navegador usa la hoja de compartir del sistema en móvil (con la imagen adjunta). En escritorio copia la imagen al portapapeles para pegarla en WhatsApp Web con Ctrl+V y además la descarga como respaldo.

Los logos viajan embebidos en el HTML (`data:`), así la captura no depende de la red ni de permisos de origen.

Si cambia el diseño, edite `templates/olb_byte/_hoja_factura.html` y `static/css/factura-olb.css`. Si cambia la librería, reemplace `static/js/vendor/html-to-image.js` y suba la versión de `sw.js`.
