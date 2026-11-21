# AGENTS.md — Configuración Técnica y Estado del Agente AI

> Proyecto: **OLB_BYTE & Finanzas Personales**
> Este archivo es la fuente de verdad operativa para cualquier agente AI que trabaje en el repositorio.
> Se actualiza **obligatoriamente** en cada avance (ver `constitution.md`, principio 5).

---

## 1. Descripción General

Plataforma web/móvil híbrida (PWA) con backend y frontend **100% Python**, arquitectura **RBAC** (Control de Acceso Basado en Roles). Combina un módulo público de finanzas personales y liquidación salarial colombiana, monetizado con anuncios no invasivos, con un módulo privado de gestión comercial y cartera para la tienda de gadgets **OLB_BYTE**.

---

## 2. Stack Tecnológico Oficial (decisión innegociable)

| Capa | Tecnología | Justificación |
| --- | --- | --- |
| Lenguaje | **Python 3.11+** | Único lenguaje permitido en backend, lógica de negocio y renderizado. |
| Framework web | **FastAPI** | Tipado, inyección de dependencias, RBAC por dependencias y OpenAPI automático. |
| Renderizado de vistas | **Jinja2** (templates server-side) | Evita duplicar lógica de negocio en JavaScript; HTML como componente visual. |
| Reactividad de UI | **HTMX + JavaScript mínimo** | Cálculo reactivo (<100 ms) sin recargar página, manteniendo Python como cerebro. |
| Estilos | **CSS puro** con variables (paleta oficial) | Sin dependencias de build; PWA ligera. |
| Datos (fase actual) | **SQLite + SQLAlchemy 2.x** | Persistencia real; PostgreSQL/Alembic en el despliegue. |
| Datos (fase posterior) | **PostgreSQL + Alembic** | Según `diccionario_datos.md`; solo cambia `DATABASE_URL`. |
| Pruebas | **pytest** | Cobertura obligatoria del motor financiero y de los flujos HTTP. |

> ⚠️ **Prohibido** introducir React, Vite, Node.js o cualquier stack JS como núcleo del proyecto. JavaScript se admite únicamente como mejora progresiva de UI (HTMX, portapapeles, atajos).

---

## 3. Roles & Control de Acceso

- **`ADMIN_OLB`**: Propietario del sistema. Acceso total a los 4 módulos (`Mis Finanzas`, `OLB_BYTE`, `Registro y Detalles de deudas`, `Trabajos Extras`) y bloque exclusivo de **Chancucos** dentro de `Mis Finanzas`. La administración de cuentas se abre desde `Mi Perfil`.
- **`USER_FINANZAS`**: Usuario público. Acceso a `Mis Finanzas` (incluye sus submódulos), `Registro y Detalles de deudas` y `Trabajos Extras`, con anuncios no invasivos. `OLB_BYTE` y `Chancucos` están bloqueados a nivel de UI **y** de endpoint (403).
- **Navegación (SRS v1.2):** el header contiene únicamente `Inicio`, `Mi Perfil` y `Salir`. El dashboard muestra 4 tarjetas; `OLB_BYTE` se omite por completo para `USER_FINANZAS`.

---

## 4. Estructura del Repositorio

```
/
├── constitution.md                     # Principios innegociables
├── plan.md                             # Plan por fases
├── spec.md                             # Spec activa (corto alcance)
├── tasks.md                            # Backlog atómico activo
├── MEMORY.md                           # ADRs, decisiones y bitácora
├── Guia.md                             # Manual por archivo y función (se regenera)
├── AGENTS.md                           # Este archivo
├── DESPLIEGUE.md                       # Guía de producción, respaldos y rollback
├── diccionario_datos.md                # Diccionario de datos (fuente para BD)
├── especificaci_n_de_requisitos_de_software_srs.md   # SRS v1.1.0
├── .github/workflows/ci.yml            # compileall + pytest + prueba de respaldo
└── backend/
    ├── requirements.txt
    ├── requirements-dev.txt            # pytest + httpx (solo desarrollo)
    ├── datos/finanzas.db               # Base SQLite local (no versionar)
    ├── scripts/respaldo.py             # Respaldo consistente y rotación
    ├── scripts/generar_guia.py        # Inventario de Guia.md + --verificar
    ├── tests/                          # Suite completa (559 pruebas)
    └── app/
        ├── main.py                     # Punto de entrada FastAPI (fábrica de app)
        ├── dependencias.py             # Sesión, `SesionRequerida` y RBAC por rol
        ├── modelos.py                  # Tablas SQLAlchemy del diccionario
        ├── core/
        │   ├── base_datos.py           # Motor, sesión por petición y siembra
        │   ├── config.py               # Parámetros de negocio y entorno
        │   ├── limitador.py            # Ventana de intentos fallidos de login
        │   ├── middleware.py           # CSRF por origen + cabeceras de seguridad
        │   ├── numeros.py              # Conversión segura a `Decimal`
        │   ├── seguridad.py            # Hash PBKDF2 y JWT HS256
        │   └── texto.py                # Formato COP / fechas y parseo de entradas
        ├── routers/
        │   ├── vistas.py               # Dashboard y `/salud`
        │   ├── auth.py                 # Login, registro, salida, rate limit y auditoría
        │   ├── perfil.py               # Onboarding y cambio de contraseña
        │   ├── admin.py                # Roles y estado de las cuentas
        │   ├── finanzas.py             # Calculadora, quincenas, historial y CSV
        │   ├── incapacidades.py        # Formulario y liquidación de incapacidades
        │   ├── gastos.py               # Gastos fijos y quincena asignada
        │   ├── presupuesto.py          # Planificador de ahorro y metas (v1.3)
        │   ├── chancucos.py            # Referencias de pago (panel embebido)
        │   ├── deudas.py               # Pasivos y abonos
        │   ├── trabajos.py             # Trabajos extras
        │   ├── olb_byte.py             # Inventario, ventas, cartera y factura
        │   └── pwa.py                  # Manifest, service worker y favicon
        ├── servicios/                  # Lógica pura (sin HTTP)
        │   ├── nomina.py               # Motor salarial
        │   ├── auxilio.py              # Tope de 2 SMMLV
        │   ├── incapacidad.py          # Incapacidades y rollover
        │   ├── perfiles.py             # Perfil financiero 1:1 y quincenas
        │   ├── periodos.py             # Historial y rollover persistido
        │   ├── quincenas.py            # Saldo libre por pago (layout v1.2)
        │   ├── ahorro.py               # Metas de ahorro y alerta de liquidez (v1.3)
        │   ├── registro_incapacidades.py
        │   ├── gastos.py
        │   ├── chancucos.py
        │   ├── deudas.py
        │   ├── trabajos.py
        │   ├── capacidad.py            # Dona y proyección de endeudamiento (v1.7)
        │   ├── consejero.py            # Liberación de flujo de caja y metas (v1.8)
        │   ├── comercial.py            # Inventario, ventas y cartera
        │   ├── auditoria.py
        │   └── usuarios.py             # Repositorio de usuarios sobre BD
        ├── templates/                  # Vistas Jinja2
        │   ├── base.html
        │   ├── login.html
        │   ├── registro.html
        │   ├── dashboard.html
        │   ├── perfil/index.html
        │   ├── admin/usuarios.html
        │   ├── gastos/index.html
        │   ├── presupuesto/index.html  # Planificador de ahorro (v1.3)
        │   ├── historial/index.html    # Historial cronológico + versión imprimible
        │   ├── incapacidades/index.html
        │   ├── finanzas/index.html     # Layout de dos columnas + Chancucos
        │   ├── finanzas/_subnav.html   # Subnavegación interna del módulo
        │   ├── finanzas/_gasto_fijo.html # Fila de gasto y check compartida
        │   ├── finanzas/_capacidad.html # Dona de endeudamiento compartida
        │   ├── chancucos/index.html
        │   ├── deudas/index.html
        │   ├── trabajos/index.html
        │   └── olb_byte/               # Panel comercial y factura
        └── static/
            ├── css/estilos.css         # Paleta oficial, componentes e impresión
            ├── js/finanzas.js          # Fetch + debounce, plantillas y aviso
            ├── js/app.js               # Portapapeles, filas y service worker
            ├── js/perfil.js            # Modalidad quincenal y avisos
            ├── js/presupuesto.js       # Total proyectado y duración de la meta
            ├── js/sw.js                # Caché solo de estáticos
            ├── manifest.webmanifest
            └── img/                    # Favicon e íconos PWA
```

---

## 5. Reglas de Documentación (nuevas, obligatorias)

1. **Todo el código en español**: nombres de variables, funciones, clases, módulos, comentarios y docstrings.
2. **Cada función, método y clase debe llevar docstring** con: propósito, parámetros (`Args`), retorno (`Returns`) y excepciones (`Raises`) cuando aplique.
3. **Comentarios explícitos** en toda regla de negocio (por qué, no solo qué).
4. **Cada módulo** inicia con un docstring de cabecera que describe su responsabilidad.
5. **Trazabilidad**: todo cambio relevante se registra en `MEMORY.md` (bitácora + ADR si aplica) y en este archivo (estado verificado).
6. **El diccionario de datos (`diccionario_datos.md`) es la fuente única** para crear la base de datos. Ninguna tabla se crea sin estar documentada allí.
7. **`Guia.md` es obligatoria y viva**: se reescribe en cada cambio con una ficha por archivo (propósito, reglas, dependencias) y el inventario automático de clases, funciones y métodos. Antes de cerrar cualquier bloque se ejecuta `python scripts\generar_guia.py` y `python scripts\generar_guia.py --verificar`; el verificador falla si un módulo, clase, función o método no tiene docstring, o si un archivo carece de ficha. Nunca se edita a mano el bloque entre `<!-- INVENTARIO:INICIO -->` y `<!-- INVENTARIO:FIN -->`.

---

## 6. Reglas del Motor Financiero (Colombia)

- **Base mensual legal:** 210 horas laborales (jornada de 42h semanales).
- **Deducciones de ley (sólo lectura):** 4% Salud + 4% Pensión sobre el **salario devengado** del periodo: sueldo básico + horas extras y recargos − descuento por incapacidad (SRS v1.4, ADR-19). Esta regla reemplaza la anterior, que usaba solo el sueldo básico.
- **Factores de recargos:**
  - Extra Diurna Normal: `1.25`
  - Extra Nocturna: `1.75`
  - Extra Diurna Dominical/Festiva: `2.00`
  - Extra Nocturna Dominical/Festiva: `2.50`
  - Recargo Nocturno: `0.35`
  - Recargo Dominical/Festivo: `1.90`
- **Auxilio de Transporte:** se anula ($0) si `Sueldo Básico + Recargos` > 2 SMMLV (**COP 3.501.810**, parametrizable).
- **Incapacidades (origen común):** días 1–2 al 100% (empleador); días 3+ al 66.67% (descuento del 33.33% a cargo de EPS). Los días son **calendario** (`fin − inicio + 1`) y no se digitan; la regla 100 %/66,67 % se aplica una sola vez sobre la incapacidad completa. Si el rango cruza de mes, cada mes descuenta **solo su tramo** (`registro_incapacidades.tramos_del_mes`); **no hay rollover** (ADR-20). La incapacidad entra en la caja única de deducciones de ley.
- **Deudas (SRS v1.8, ADR-53):** seis datos (acreedor, descripción, total adeudado, cuota, cuotas pendientes y periodicidad quincenal/mensual). **Sin intereses:** la tasa se retira del modelo y `cuota × cuotas` debe reconstruir el total adeudado con tolerancia de **$1 por cuota** (si no cuadra, se pide revisar y reingresar). Al abrir el módulo se aplican las cuotas vencidas en `pagos_deuda` (idempotente por `UNIQUE(id_deuda, numero_cuota)`); cada cuota abona capital completo y la última deja el saldo exacto en cero. No existe abono manual.
- **Metas con «Ambas quincenas» (ADR-22):** `quincena = 3` guarda la cuota mensual y la reparte entre los dos pagos (`valor_por_pago`). Sigue siendo planificación: no se resta del saldo libre.
- **Capacidad de endeudamiento y consejero (SRS v1.8, ADR-53):** el ingreso del mes (quincenas + extras cobrados) se reparte entre gastos fijos, cuota mensual de deudas y libre; el semáforo usa el porcentaje de deuda (≤ 20 % verde, ≤ 35 % ámbar, más rojo). Del libre se reserva una **base mínima de liquidez de $300.000** (`BASE_MINIMA_LIQUIDEZ`, compartida con `ahorro.py`): la dona muestra «Base mínima de liquidez» y «Disponible para abonar», y solo el remanente alimenta el consejero. Si el libre no supera la base, el consejo se apaga con un mensaje que invita a crear una meta de emergencia. Con deudas, el orden es de **flujo de caja**: si el excedente cancela una deuda completa, primero la de más cuotas por delante (12 meses antes que 5); si no, la de menor saldo. Sin deudas dirige el excedente a las metas.
- **Onboarding obligatorio (SRS v1.2):** ninguna ruta de negocio se abre sin perfil financiero; `UsuarioSesion.perfil_configurado` se calcula por petición y `OnboardingRequerido` redirige a `/perfil?bienvenida=1` (303 HTML / 409 JSON).
- **Quincenas independientes:** en modalidad `QUINCENAL`, `porcentaje_quincena_1 + porcentaje_quincena_2 = 100 %`. Las deducciones de ley se aplican **solo** a la quincena indicada en `quincena_deducciones`. Si el usuario no conoce los porcentajes, informa el neto de la quincena sin descuentos y el sistema deriva ambos porcentajes por descarte.
- **Obligaciones fijas por quincena:** `gastos.quincena` (`1`, `2` o `NULL`) decide de qué pago se resta el gasto fijo. Los gastos sin quincena se muestran en la quincena 1 como «todo el mes» para conservar el total.

---

## 7. Cómo Ejecutar el Proyecto

```bash
# Backend / Frontend (FastAPI sirve las vistas Jinja2)
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- Dashboard (requiere sesión): <http://127.0.0.1:8000/>
- Login: <http://127.0.0.1:8000/login>
- Documentación API: <http://127.0.0.1:8000/docs>

**Cuentas de demostración** (sembradas en SQLite solo si `usuarios` está vacía):

| Rol | Correo | Contraseña |
| --- | --- | --- |
| `ADMIN_OLB` | `admin@olbbyte.co` | `Admin123*` |
| `USER_FINANZAS` | `usuario@finanzas.co` | `Usuario123*` |

> La sesión se guarda en la cookie `sesion` (`HttpOnly`, `SameSite=Lax`, 480 min) firmada con `CLAVE_SECRETA`. En producción, definir `CLAVE_SECRETA` (≥ 32 caracteres) y `ENTORNO=produccion`: la cookie se marca `Secure`, `/docs` se cierra y el arranque falla si la clave es débil. Ver `DESPLIEGUE.md`.

### Pruebas y respaldo

```bash
cd backend
.\.venv\Scripts\python -m pytest -q          # suite completa (559 pruebas)
.\.venv\Scripts\python scripts\respaldo.py   # copia consistente en backend/respaldos
.\.venv\Scripts\python scripts\generar_guia.py --verificar  # docstrings y fichas de Guia.md
```

### Ejecutar desde VS Code (F5)

El proyecto **no tiene `index.html`**: las páginas las genera FastAPI en `backend/app/routers/` y las plantillas viven en `backend/app/templates/`. El único archivo que se "ejecuta" es `backend/app/main.py`.

1. Abrir la carpeta raíz del proyecto en VS Code.
2. Panel **Run and Debug** (`Ctrl+Shift+D`) → elegir **Plataforma (FastAPI :8000)** → `F5`.
3. Esperar el mensaje `Uvicorn running on http://127.0.0.1:8000` y abrir <http://127.0.0.1:8000/login>.

La configuración vive en `.vscode/launch.json`. También existe **Pruebas (pytest)** para correr la suite con `F5` y puntos de interrupción.

---

## 8. Paleta Visual (no modificar sin ADR)

```css
:root {
  --bg-primary: #0F172A;      /* Slate Oscuro */
  --bg-card: #1E293B;         /* Tarjetas de Módulo */
  --accent-blue: #0284C7;     /* OLB_BYTE Brand Blue */
  --accent-green: #10B981;    /* Indicador Positivo / Bolsillo */
  --accent-amber: #F59E0B;    /* Alertas SMMLV / Incapacidades */
  --accent-red: #EF4444;      /* Deducciones / Gastos */
  --text-primary: #F8FAFC;
  --text-muted: #94A3B8;
}
```

---

## 9. Estado Verificado

- [x] SRS v1.1.0 leída y validada.
- [x] Constitución, plan, spec, tasks y memorias sincronizadas.
- [x] Decisión de stack: **Python puro (FastAPI + Jinja2 + JavaScript mínimo)**.
- [x] Política de documentación de código y diccionario de datos incorporada.
- [x] `diccionario_datos.md` creado (modelo lógico completo).
- [x] **Tarea 1** — Estructura base de componentes (FastAPI + plantillas + paleta + RBAC visual en dashboard).
- [x] Verificación: `python -m compileall` OK y **4 pruebas de humo** con `pytest` en verde (RBAC visual, parámetros legales y endpoint `/salud`).
- [x] **Tarea 2** — Motor de nómina puro: hora ordinaria (210 h), deducciones 4% + 4%, matriz de recargos y `liquidar_periodo`, con **22 pruebas unitarias**.
- [x] Verificación: `python -m compileall` OK y **26 pruebas** con `pytest` en verde (4 de vistas + 22 del motor).
- [x] **Tarea 3** — Validador del tope de 2 SMMLV (`servicios/auxilio.py`), con mensaje del SRS, diferencia hasta el tope e integración en la liquidación.
- [x] Verificación: **37 pruebas** con `pytest` en verde (4 vistas + 22 motor + 11 auxilio).
- [x] **Tarea 4** — Motor de incapacidades: días 1–2 al 100%, días 3+ al 66.67%, reparto mensual y rollover (`servicios/incapacidad.py`), con **17 pruebas**.
- [x] Verificación: **54 pruebas** con `pytest` en verde (4 vistas + 22 motor + 11 auxilio + 17 incapacidades).
- [x] **Tarea 4b** — Formulario de incapacidades en `/incapacidades` con descuento del mes y saldo arrastrado visibles, **10 pruebas de vista** (9 originales + 1 de sesión requerida al migrar al login real).
- [x] Verificación: **74 pruebas** con `pytest` en verde (54 de dominio + 11 de helpers + 9 de vista de incapacidades).
- [x] **Tarea 5** — RBAC real: PBKDF2 + JWT HS256, cookie `HttpOnly`, login/registro/salida y **403** en los cuatro módulos privados para `USER_FINANZAS`.
- [x] **Tarea 6** — Calculadora de "Mis Finanzas": POST clásico sin JS + `POST /finanzas/calcular` (JSON) con debounce de 150 ms y panel de resultados en vivo.
- [x] Verificación: `python -m compileall` OK y **111 pruebas** con `pytest` en verde (22 nómina + 11 auxilio + 17 incapacidades + 11 helpers de texto + 10 vista de incapacidades + 11 seguridad + 11 auth/RBAC + 12 finanzas + 6 vistas generales).
- [x] **Bloque A** — Persistencia SQLite + SQLAlchemy, onboarding de perfil, gastos, historial con rollover persistido y auditoría.
- [x] **Bloque B** — Chancucos, OLB_BYTE (productos, clientes, ventas multipartida, abonos, cartera, factura y WhatsApp), Deudas y Trabajos Extras.
- [x] **Bloque C** — Exportación CSV, impresión de historial, PWA (manifest, service worker, íconos), favicon, publicidad por rol y aviso de cambios sin guardar.
- [x] **Bloque D** — CSRF por origen, cabeceras CSP, rate limiting de login, administración de cuentas, `/docs` cerrado en producción, `CLAVE_SECRETA` obligatoria, respaldo SQLite, CI y `DESPLIEGUE.md`.
- [x] Verificación final (SRS v1.1.0): `python -m compileall` OK y **185 pruebas** con `pytest` en verde.
- [x] **SRS v1.2 — Bloque 1 (onboarding y perfil):** `perfilConfigurado` por petición, `OnboardingRequerido` con 303/409, formulario de bienvenida con alias, contraseña, sueldo, modalidad, caso A (porcentajes Q1/Q2 + quincena de deducciones) y caso B (neto sin deducciones → porcentajes por descarte). Migración ligera de `perfiles_financieros` y guardado con redirección a `/?guardado=1`.
- [x] Verificación bloque 1: `python -m compileall` OK y **193 pruebas** con `pytest` en verde (185 previas + 8 netas del onboarding y las quincenas).
- [x] **SRS v1.2 — Bloque 2 (navegación y RBAC):** header reducido a `Inicio`, `Mi Perfil` y `Salir`; dashboard con las 4 tarjetas principales; `OLB_BYTE` exclusivo de `ADMIN_OLB`; `Registro y Detalles de deudas` y `Trabajos Extras` pasan a acceso general; Chancucos y Usuarios salen del dashboard (Usuarios accesible desde el perfil del administrador).
- [x] Verificación bloque 2: `python -m compileall` OK y **194 pruebas** con `pytest` en verde (incluye pruebas de las tres opciones de navegación y del RBAC por módulo).
- [x] **SRS v1.2 — Bloque 3 (layout de Mis Finanzas):** `rejilla-finanzas` de dos columnas (izquierda con quincenas, gastos fijos y saldo libre; derecha con liquidación, resultado y desglose), `servicios/quincenas.py`, `Gasto.quincena` con migración idempotente, deducciones imputadas a la quincena del perfil, subnavegación interna y Chancucos embebidos para `ADMIN_OLB`. Se retira la plantilla «Semana típica».
- [x] Verificación bloque 3: `python -m compileall` OK y **203 pruebas** con `pytest` en verde (194 previas + 9 netas del layout y las quincenas).
- [x] **Cierre SRS v1.2:** los tres bloques validados por el usuario; onboarding obligatorio, navegación mínima con RBAC y layout de Mis Finanzas con quincenas, gastos fijos y Chancucos embebidos.
- [x] **SRS v1.3 — Bloque 1 (navegación y subnavegación):** Header principal interactivo (`base.html`) con indicador de pestaña activa, subnavegación interna de 4 pestañas (`_subnav.html`) en Mis Finanzas (`Calculadora y Nómina`, `Gastos Fijos`, `Incapacidades`, `Configurar Atajos de Pago`), y 206 pruebas en verde.
- [x] **SRS v1.3 — Bloque 2 (layout 50/50 y reactividad):** `rejilla-finanzas--5050` con dos columnas iguales; columna izquierda en tres sub-contenedores (Quincena 1, Quincena 2 y Atajos de pago en solo lectura con copiado rápido «¡Copiado!»); columna derecha reordenada (sueldo → deducciones de ley en pesos → horas extras en cuadrícula 2 × 3 → Calcular/Limpiar/Guardar → auxilio de transporte → incapacidades compactas → resultado → desglose). Año/mes/quincena pasan a campos ocultos y el descuento de incapacidad sale de la cabecera. Edición de gastos fijos con `actualizar_gasto()` en `servicios/gastos.py` y `POST /gastos/{id_gasto}/editar` (auditoría `GASTO_ACTUALIZADO`). Reactividad en `finanzas.js` con `pintarDeduccion()`, `pintarValorAuxilio()`, copiado con delegación y cálculo inicial automático. Registrado en `MEMORY.md` (bitácora + ADR-15).
- [x] **Verificación Bloque 2 (SRS v1.3):** `python -m compileall` sin errores y **206 pruebas en verde**. Dos correcciones necesarias durante la verificación: (a) la ruta `editar_gasto` declara `response_model=None` porque su anotación de retorno es la unión `HTMLResponse | RedirectResponse`, igual que `crear_gasto`; (b) `tests/test_quincenas.py` se actualizó a los rótulos nuevos («🔗 Configurar atajos de pago» y «🔗 Atajos de pago») y ahora comprueba el botón `data-copiar`. También se confirmó que `parsear_periodo_mes` resuelve el mes actual cuando el campo llega vacío (`_entero(..., hoy.month, ...)` en `routers/finanzas.py:150`).
- [x] **SRS v1.3 — Bloque 2.1 (atajos de pago con 3 campos):** `entidad` + `tipo_servicio` se fusionan en `descripcion`; `url_pago` queda opcional. Actualizados `diccionario_datos.md` §9, `modelos.py`, `servicios/chancucos.py`, `routers/chancucos.py`, `templates/chancucos/index.html` y `templates/finanzas/index.html`. Migración `_migrar_chancucos()` en `core/base_datos.py` que **reconstruye** la tabla (`chancucos_v13` → copia con fusión `entidad · tipo_servicio` → `DROP` → `RENAME`) porque `tipo_servicio` era `NOT NULL` sin default. Verificado: **206 pruebas en verde** y migración probada sobre copia de `finanzas.db` (idempotente). Registrado en `MEMORY.md` (bitácora + ADR-16).
- [x] **SRS v1.3 — Bloque 3 (planificador de ahorro):** nuevas tablas `proyecciones_ahorro` y `abonos_proyeccion` (§9.1 y §9.2 del diccionario), `servicios/ahorro.py` con `diagnostico()` y `UMBRAL_ALERTA = Decimal("300000")`, router `/presupuesto` (crear meta, registrar/corregir abono y eliminar), plantilla con banner de liquidez, alerta crítica y cuadrícula de abonos, y `presupuesto.js` para el total proyectado. `/gastos` queda como registro secundario enlazado desde el planificador. 18 pruebas nuevas (bitácora + ADR-17 en `MEMORY.md`).
- [x] Verificación bloque 3: `python -m compileall` OK y **224 pruebas** con `pytest` en verde (206 previas + 18 netas).
- [x] **SRS v1.3 — Bloque 4 (Mi Perfil):** configuración quincenal oculta en modalidad `MENSUAL` con aviso explicativo, radios apilados, etiqueta «Escribe el valor neto que recibes en la quincena donde NO te realizan deducciones de ley ni pago de horas extras.» y pregunta «¿En qué quincena te realizan todas las deducciones y pago de recargos?». 3 pruebas nuevas.
- [x] Verificación bloque 4: **227 pruebas** con `pytest` en verde (224 + 3 netas).
- [x] **SRS v1.3 — Bloque 5 (Historial de Registros):** `_filas_historial` expone `fecha_guardado` y `total_extras`; tabla cronológica con fecha de guardado, periodo, sueldo base, total extras, total deducciones, gastos quincenales, saldo neto final (con variación frente al anterior) y acciones. 1 prueba nueva.
- [x] Verificación bloque 5 y cierre SRS v1.3: `python -m compileall` OK y **228 pruebas** con `pytest` en verde (227 + 1 neta).
- [x] **SRS v1.4 — Layout, navegación y deducciones fijas:** submenú en botones con scroll móvil (REQ-03), columnas alineadas y liquidación primero en móvil (REQ-01, REQ-02), desglose bajo la liquidación (REQ-06), atajos solo en consulta (REQ-07), filas de gastos compactas (REQ-09), tabla `deducciones_fijas` y gestión en «Gastos y Presupuesto» (REQ-08), y recálculo en vivo de quincenas con recargos e incapacidad (REQ-04, REQ-05). Registrado en `MEMORY.md` (bitácora + ADR-18). Verificado: **238 pruebas** en verde.
- [x] **Cálculo en vivo de incapacidades y sueldo proyectado:** el descuento sale del motor legal (días 1–2 al 100 %; desde el día 3, 33,33 %), el sueldo proyectado suma horas extras y resta la incapacidad, y las quincenas se recalculan al instante. Verificado: **244 pruebas** en verde (`MEMORY.md`, bitácora).
- [x] **SRS v1.4 — Salud y pensión sobre el devengado (ADR-19):** la base es sueldo + extras − incapacidad, en el motor de nómina y en el panel de quincenas. Horas extras e incapacidad se ven en vivo en el sueldo proyectado, en salud/pensión y en las quincenas.
- [x] **SRS v1.5 — Bloque 1 (caja única de deducciones):** salud + pensión + incapacidad + deducciones fijas se presentan y suman juntas; subtítulo con los conceptos, cifras en rojo sin signo menos y total final con la caja completa. Helpers `_fijas_del_periodo`, `_total_fijas` y `_total_deducciones_ley` en `routers/finanzas.py` (ADR-20).
- [x] **SRS v1.5 — Bloque 2 (incapacidades por tramo):** días calendario automáticos, regla 100 %/66,67 % una sola vez, corte por mes calendario y **sin rollover**; `tramos_del_mes()`/`descuento_del_mes()` y `static/js/incapacidades.js`. Migración `_migrar_saldos_incapacidad` (ADR-20).
- [x] **SRS v1.5 — Bloque 3 (sueldo de solo lectura):** el sueldo del periodo se edita solo en Mi Perfil; la liquidación lo muestra destacado con enlace de cambio.
- [x] **SRS v1.5 — Bloque 4 (desglose compacto):** tabla sin columna Factor (Concepto, Horas, Valor), sin `min-width` ni `nowrap` y sin scroll horizontal.
- [x] **SRS v1.5 — Bloque 5 (móvil y botones):** submenú 2 × 2 a 640 px, campos a una columna en Gastos y Presupuesto, paneles a 16 px y «Agregar deducción fija» con el mismo peso visual que «Crear meta», sin `+`. `sw.js` en `olb-finanzas-v7`.
- [x] **SRS v1.5 — Bloque 6 (metas «Ambas quincenas»):** `quincena = 3`, reparto entre los dos pagos, migración por reconstrucción de `proyecciones_ahorro` + `abonos_proyeccion` y diccionario §9.1 (ADR-22).
- [x] **SRS v1.5 — Bloque 7 (deudas con amortización automática):** seis campos, tasa implícita por bisección con 10 decimales, tabla `pagos_deuda`, aplicación de cuotas al abrir el módulo, última cuota en cero y `pagos_deuda` en `MODELOS_TRANSACCIONALES`; se retira el abono manual (ADR-21).
- [x] **SRS v1.5 — Bloque 9 (documentación):** `Guia.md` con arquitectura, 70 fichas por archivo e inventario automático; `scripts/generar_guia.py` con `--verificar`. Obligación registrada en §5 y en `MEMORY.md`.
- [x] Verificación SRS v1.5: `python -m compileall` OK, **260 pruebas** con `pytest` en verde y `generar_guia.py --verificar` sin problemas (70 archivos con ficha, sin docstrings pendientes). Migraciones de metas y deudas probadas dos veces sobre bases con datos.
- [ ] **SRS v1.4/v1.5 — Revisión visual pendiente:** alineación de columnas y móvil (submenú 2 × 2, campos apilados); verificar en navegador.
- [x] **SRS v1.6 — Metas como gastos fijos (ADR-24, ADR-25):** cada meta genera su gasto por quincena; el ✔ registra el abono; «Limpiar checks» conserva el pago; la × inhabilita 15 días sin borrar la meta; el abono manual solo aplica en pagos saltados. Resuelve la decisión pendiente de ADR-22: las metas sí restan del saldo, a través de sus gastos fijos.
- [x] **SRS v1.6 — Montos sin centavos (ADR-23)** e **incapacidades: Enter y «Limpiar» (ADR-26).**
- [x] Verificación SRS v1.6: `python -m compileall` OK, **289 pruebas** con `pytest` en verde, `generar_guia.py --verificar` sin problemas (71 archivos con ficha) y migración de `gastos` probada sobre una base con el esquema anterior.
- [ ] **SRS v1.6 — Revisión visual pendiente:** botones ✔/× del mismo tamaño, meses centrados en «Gastos y Presupuesto» y «Valor:» retirado en el celular; verificar en navegador.
- [x] **SRS v1.7 — Bloque A (UI móvil):** rejillas con `minmax(min(...),100%)`, `min-width:0`, fechas sin desborde y alturas homologadas (ADR-30).
- [x] **SRS v1.7 — Bloque B (metas):** selector Quincena 1 / Quincena 2 / Ambas y modo `DIVIDIR`/`DUPLICAR` para «Ambas» (ADR-31).
- [x] **SRS v1.7 — Bloque C (checks):** desmarcar revierte pago y abono; la limpieza masiva solo oculta los ✔; lápiz, «Cancelar» y × en la fila compartida (ADR-32).
- [x] **SRS v1.7 — Bloque D (atajos):** pregunta «¿Es un único pago mensual?», uno o dos días (1–31) y distintivo «Día 15 · Día 30» (ADR-33).
- [x] **SRS v1.7 — Bloque E (Trabajos Extras):** contratos indefinidos o a término fijo, frecuencia mensual/quincenal, pagos con check reutilizado y neto al diagnóstico del mes (ADR-34).
- [x] **SRS v1.7 — Bloque F (capacidad):** dona de gastos fijos, deudas y libre con semáforo, deudas con tres cuotas o menos y proyección a 12 meses, instanciada en Gastos y Presupuesto y en Trabajos Extras (ADR-44).
- [x] **SRS v1.7 — Bloque G (consejero):** se activa sobre $300.000, recomienda bola de nieve o avalancha, sugiere metas cuando no hay deudas y compara base frente a optimizado a 12 meses (ADR-45).
- [x] Verificación SRS v1.7: `python -m compileall` OK, **478 pruebas** con `pytest` en verde, `generar_guia.py --verificar` sin problemas (88 archivos con ficha). `sw.js` en `olb-finanzas-v16`.
- [x] **Chancucos (Atajos de Pago) para todos los usuarios (2026-11-19):** rutas con `obtener_usuario_actual`, enlace del submenú visible a todos, cada usuario ve solo sus atajos. 521 pruebas en verde.
- [x] **Acceso a OLB_BYTE por correo e inicio con Gmail (ADR-48, 2026-11-18):** `CORREOS_OLB_BYTE` y `exigir_olb_byte`; OAuth con Google sin dependencias nuevas.
- [ ] **Despliegue en Render:** faltan variables de producción (`ENTORNO=produccion`, `CLAVE_SECRETA`, credenciales de Google) y migrar a PostgreSQL (Neon).
- [x] **Ajuste móvil de la edición de gastos (ADR-30):** en pantallas de 640 px o menos el lápiz abre la edición como **ventana centrada** (fondo oscuro, scroll propio, cierre al tocar el fondo o con Escape) en vez del desplegable pegado a la derecha que se cortaba; `edicion-gasto--modal` en la macro `fila_gasto` y en las deducciones fijas, `sw.js` en `olb-finanzas-v17`. Medido en Chromium a 360/390/768/1280 px.
- [ ] **SRS v1.7 — Revisión visual pendiente:** bloques A a G en 360/390/768/escritorio, incluida la gráfica del consejero en celular.
- [x] **SRS OLB_BYTE v1.0 — Fase 0 (decisiones):** modelo sin inventario, anulación con devolución y sin reversa de deuda con proveedor, consecutivo desde 1, productos escritos a mano y motor PDF Playwright (ADR-35 y ADR-36, `diccionario_datos.md` §10).
- [x] **SRS OLB_BYTE v1.0 — Fase 1 (modelo y servicio):** tablas `ventas`, `venta_detalle`, `movimientos_proveedor`, `garantias_proveedor` y `devoluciones_clientes`; `productos` sin `stock`; reconstrucción `_reconstruir_comercial_sin_stock` que se detiene si hay datos; `servicios/comercial.py` reescrito (consecutivo, deuda con proveedor, abonos con fecha y hora, anulación con devolución, cartera y caja).
- [x] Verificación Fase 1: `pytest` en verde (**345 pruebas**, incluidas 3 de migración en `tests/test_migracion_olb.py`).
- [x] **SRS OLB_BYTE v1.0 — Fase 2 (venta multi-producto, RF-01 a RF-05):** formulario con mini-tabla (lápiz, Actualizar/Cancelar, ×, «+ Agregar otro producto»), totales en vivo (`static/js/olb_byte.js`), autocompletado de clientes, Contact Picker como mejora progresiva, semáforo de garantía y cobros, anulación y devolución desde el panel. Las rutas de productos y stock se retiran. `sw.js` en `olb-finanzas-v14`.
- [x] Verificación Fase 2: `pytest` en verde (**361 pruebas**, incluidas 13 HTTP en `tests/test_olb_vistas.py`); `node --check` del JavaScript sin errores.
- [x] **SRS OLB_BYTE v1.0 — Fase 3 (cobros y recibos, RF-06 y RF-07):** vista `/olb-byte/pendientes` con búsqueda por cliente, celular o número, abono con fecha y hora que redirige a su recibo, recibo compacto `/olb-byte/recibos/{id}` con desglose e insignia de saldo total, y cobro y recibo por WhatsApp. Fechas comerciales en hora de la tienda (ADR-37).
- [x] Verificación Fase 3: `pytest` en verde (**374 pruebas**, incluidas 13 en `tests/test_cobros_vistas.py`); `generar_guia.py` regenerado.
- [x] **SRS OLB_BYTE v1.0 — Fase 4 (cartera y liquidez, RF-08 a RF-11):** vista `/olb-byte/cartera` con balance (cartera, deuda, balance, caja, efectivo libre), signos y colores solo en este módulo (ADR-38), dona SVG de cartera frente a deuda, pago al proveedor con validación y libro de movimientos.
- [x] Verificación Fase 4: `pytest` en verde (**385 pruebas**, incluidas 10 en `tests/test_cartera.py`); `generar_guia.py` regenerado.
- [x] **SRS OLB_BYTE v1.0 — Fase 5 (garantías y fallas, RF-05):** reclamos sobre líneas de órdenes activas, trámite `ABIERTA → EN_TRAMITE → RESUELTA | RECHAZADA` con cierre final, vigencia frente a la fecha de fin de garantía y ranking por tasa de fallas (ADR-39). Vista `/olb-byte/garantias`.
- [x] Verificación Fase 5: `pytest` en verde (**399 pruebas**, incluidas 14 en `tests/test_garantias.py`); `generar_guia.py` regenerado.
- [x] **SRS OLB_BYTE v1.0 — Fase 6 (analítica, RF-12 a RF-14):** `servicios/analitica.py` con reportes mensual y anual (variación, rentabilidad), ranking de clientes VIP y alertas de subida de costo con margen y umbral de 15 % (ADR-40). Vista `/olb-byte/analitica`.
- [x] Verificación Fase 6: `pytest` en verde (**411 pruebas**, incluidas 13 en `tests/test_analitica.py`); `generar_guia.py` regenerado.
- [ ] **OLB_BYTE Fase 6 — revisión visual pendiente:** las barras mensuales y las tablas en móvil.
- [ ] **OLB_BYTE Fase 5 — revisión visual pendiente:** los selectores de trámite en móvil.
- [ ] **OLB_BYTE Fase 4 — revisión visual pendiente:** la dona en móvil y el contraste de «−» en rojo sobre fondo oscuro.
- [ ] **OLB_BYTE Fase 3 — revisión visual pendiente:** recibo en celular y su impresión (`no-imprimir`), y el orden de los campos de abono en la vista de pendientes.
- [ ] **OLB_BYTE Fase 2 — revisión visual pendiente:** mini-tabla en móvil, Contact Picker en un celular con HTTPS, y comportamiento de Cancelar en filas nuevas y guardadas; verificar en navegador.
- [x] **Deuda de documentación resuelta:** `Guia.md` incorpora las fichas de `templates/chancucos/_dias.html` y `templates/finanzas/_gasto_fijo.html`; `generar_guia.py --verificar` queda en verde (85 archivos con ficha).
- [x] **SRS OLB_BYTE v1.0 — Fase 7 (factura PDF, RF-18 y RF-19):** PDF Carta de una página con Playwright y Chromium (ADR-36 y ADR-41), logos de `assets/`, medios de pago, vista previa, descarga y compartir. Límite de diez productos por factura. Instalación del navegador en `DESPLIEGUE.md` §13.
- [x] Verificación Fase 7: `pytest` en verde (**425 pruebas**, incluidas 14 en `tests/test_factura_pdf.py`); revisión visual de la factura de muestra.
- [x] **Ajustes de validación (ADR-42):** botón de contactos corregido (regla global `[hidden]` y nota explicativa), submenú de OLB_BYTE arriba, formulario de venta v2 con panel de producto, tabla de detalle y cuadro de edición, `referencia` renombrada a `categoria`, vista de tarjetas en celular.
- [x] Verificación ADR-42: `pytest` en verde (**434 pruebas**); recorrido en Chromium con 19 comprobaciones en verde (escritorio y celular).
- [x] **Ajustes de validación 3 (ADR-43):** pago de contado o a crédito con anticipo en la venta; página de cobro con dos opciones; pendientes con una acción por cliente; órdenes sin ganancia ni saldo; WhatsApp envía el PDF adjunto; barras del balance; submenú sin borde cortado; «Nuevo cliente» retirado; factura personalizable (`Guia.md` §10).
- [x] Verificación ajustes 3: `pytest` en verde (**453 pruebas**); recorrido en Chromium con 35 comprobaciones en verde.
- [x] **Diseño de la factura (ADR-46):** la pantalla, la vista previa, la descarga y el PDF enviado por WhatsApp usan el mismo diseño (`_hoja_factura.html` + `factura-olb.css`). PDF de una hoja Carta con escala 0,75. Datos de empresa y cuenta en `factura_pdf.py`. Personalización en `Guia.md` §10.
- [x] Verificación diseño de factura: `pytest` en verde (**479 pruebas**); capturas en escritorio y celular sin desbordamiento.
- [x] **Ajustes del 18/11/2026:** logo de la factura revertido a texto; recibo de abono compartido como imagen PNG (`/olb-byte/recibos/{id}/imagen`, `servicios/recibo_imagen.py`, `_recibo.html` compartido con la página); buscador de pendientes separado de la tabla; cliente se reconoce por celular **y** nombre (dos personas con un mismo número ya no se mezclan en VIP); Factura, WhatsApp y Anular con el mismo ancho. CSS de factura y recibo se incrusta sin escapar (`| safe`). 490 pruebas en verde.
- [ ] **Pendiente de revisión:** el ancho de los botones de acciones y el espacio sobre la tabla de pendientes, en escritorio y celular.
- [x] **Logo oficial en la factura (revertido el 18/11):** la cabecera usa `assets/Logotipo OLB Byte de Alta Tecnología.png` (modo de mezcla `screen` para quitar su fondo negro). `base.html` tiene el bloque `estilos` y la factura carga su CSS ahí. Los logos se cachean en memoria (`logo_como_data_uri`). Prueba en `tests/test_factura_pdf.py` (480 pruebas en verde).
- [ ] **Pendiente de revisión:** el PDF impreso con el modo de mezcla del logo; conviene una prueba de descarga en tu equipo.
- [x] **Botones de regreso en OLB_BYTE:** cada pantalla tiene «← Volver» (Ventas vuelve al inicio; Pendientes, Cartera, Garantías, Analítica y Factura vuelven a Ventas; Cobro vuelve a Pendientes). Prueba en `tests/test_olb_ui.py` (454 pruebas en verde).
- [x] **Decisión (propietario):** Analítica y Cartera muestran ganancia y saldos sin protección adicional; el módulo es de uso exclusivo del administrador, por lo que no se requiere ocultarlos. La tabla de órdenes del panel sí oculta ganancia y saldo (ADR-43).
- [x] **SRS v1.8 — Bloque 8 (recuperación de contraseña por correo, ADR-51):** `/olvide-contrasena` con respuesta neutra, `/restablecer-contrasena` con enlace de 15 minutos de un solo uso, SMTP con `smtplib` (`SMTP_*`, `APP_URL`) y auditoría. Verificación: `pytest` en verde (525) y `generar_guia.py --verificar` sin problemas (98 archivos con ficha).
- [x] **PostgreSQL en Neon y Render (ADR-52):** `DATABASE_URL` de Neon en `backend/.env` (no versionado), `psycopg` 3, motor con `pool_pre_ping` y `pool_recycle=300`, `scripts/migrar_a_neon.py` (idempotente) con la base cargada y `/salud` respondiendo 200 contra Neon. Pruebas sobre SQLite temporal.
- [x] **Formato de pesos al escribir (2026-11-20):** los campos de dinero (`data-moneda`) muestran separadores de miles mientras se escriben o pegan (`static/js/moneda.js`); porcentajes y cantidades no cambian. Sueldo del perfil como «3.484.000». `sw.js` en `olb-finanzas-v47`. Verificación: prueba en Chromium y **621 pruebas** en verde.
- [x] **Movimientos con el proveedor en móvil (2026-11-20):** lista vertical con fecha sin hora, concepto, monto y saldo; detalle completo en diálogo al tocar la fila. Fecha de órdenes registradas más pequeña. `sw.js` en `olb-finanzas-v44`. Verificación: **618 pruebas** en verde.
- [x] **Donas interactivas, dona centrada en celular y banner de café más delgado (2026-11-20):** `static/js/dona.js` muestra el detalle de cada arco al pasar, tocar o enfocar; la dona se centra en celular; el banner del café es más delgado. Neon migrado con la URL nueva. `sw.js` en `olb-finanzas-v43`. Verificación: **616 pruebas** en verde y `generar_guia.py --verificar` sin problemas.
- [ ] **Donas y café — revisión visual pendiente:** dona en celular y banner en 360/390/1280 px. **Neon:** clave rotada y `DATABASE_URL` actualizada en `backend/.env` con migraciones aplicadas; falta actualizar la variable de entorno en Render.
- [x] **Deducción vinculada a la deuda que paga (ADR-56):** una libranza se vincula a una deuda mensual activa desde Gastos y Presupuesto; su valor es la cuota de la deuda, se cuenta una sola vez, muestra las cuotas que faltan y deja de descontarse al pagarse. Presupuesto aplica las cuotas vencidas al abrirse. `sw.js` en `olb-finanzas-v42`. Verificación: **613 pruebas** en verde y `generar_guia.py --verificar` sin problemas.
- [ ] **Deducción vinculada — pendiente:** revisión visual del selector en 360/390 px; vincular deudas quincenales queda para más adelante. (Migración de `id_deuda` ya aplicada y verificada en Neon.)
- [x] **Analítica con filtros y CSV (Bloque 3, ADR-55):** filtros de año, mes, cliente y producto compartidos por todas las tablas; clic en una fila activa o quita el filtro; «Descargar CSV» por tabla con la selección de pantalla; tabla de ventas por producto (No. de orden, cliente, categoría, producto, costo, total, saldo pendiente, abonos, ganancia y garantía Activa/Vencida por línea). `venta_detalle.garantia_fecha_fin` nuevo. `sw.js` en `olb-finanzas-v38`. Verificación: **604 pruebas** en verde y `generar_guia.py --verificar` sin problemas.
- [ ] **Analítica — verificación pendiente:** migración de `venta_detalle` sobre una copia de `finanzas.db` antigua y sobre Neon; revisión visual de la tabla de ventas y los chips en 360/390/1280 px.
- [x] **Día de cada quincena (Bloque 2, ADR-54):** el perfil quincenal pide «Día de la quincena 1» y «Día de la quincena 2» (1 a 31; la 2 debe ser posterior). Metas, deducciones fijas, gastos y el panel de quincenas muestran esos días. Perfiles previos: 15 y 30. En PostgreSQL se agregan las columnas al arrancar. `sw.js` en `olb-finanzas-v37`. Verificación: **589 pruebas** en verde.
- [ ] **Día de quincena — verificación pendiente:** migración sobre una copia de `finanzas.db` con perfiles antiguos y sobre Neon antes de desplegar; revisión visual del formulario de perfil en 360/390 px. Trabajos Extras conserva «día 15/30» (pendiente de decisión).
- [x] **Colores de la dona (Bloque 1 de la ronda de analítica):** capacidad de endeudamiento y trabajos extras pintan las cifras en verde (a favor) o rojo (gastos, deudas, saldo negativo); cartera frente a deuda en OLB_BYTE usa verde para la cartera y rojo para la deuda, y muestra el balance con color en el centro. `sw.js` en `olb-finanzas-v36`. Verificación: **561 pruebas** en verde y `generar_guia.py --verificar` sin problemas.
- [ ] **Colores de la dona — revisión visual pendiente:** leyenda y centro de la dona en 360/390/1280 px.
- [x] **SRS v1.8 — Base mínima de liquidez, deudas sin intereses y blindaje de entradas (ADR-53):** `BASE_MINIMA_LIQUIDEZ = $300.000` compartida por la dona, el consejero y el planificador; la dona muestra «Base mínima de liquidez» y «Disponible para abonar», y el consejo solo usa el remanente (por debajo se apaga con el mensaje de emergencia). Deudas sin tasa ni intereses: `cuota × cuotas` debe cuadrar con el total adeudado (tolerancia $1 por cuota). Orden por flujo de caja (más cuotas por delante si se cancela completa; si no, menor saldo). `parsear_porcentaje()` acepta «60», «60 %» y «60,5»; manejador global de `ValueError` y guardia numérica en `app.js`; abono de OLB_BYTE con saldo pendiente en el mensaje. Metas: «Quincena donde aplicaremos los pagos», selector de modo alineado y cinco abonos con scroll. Verificación: `compileall` OK y **559 pruebas** en verde. `sw.js` en `olb-finanzas-v35`.
- [ ] **SRS v1.8 — Revisión visual pendiente:** alineación del selector de modo de «Ambas quincenas» y la caja de cinco abonos en 360/390/768/escritorio.
- [x] **Neon — clave rotada y migraciones aplicadas (2026-11-20):** nueva `DATABASE_URL` guardada en `backend/.env` (no versionada); `aplicar_migraciones()` ejecutado contra Neon con conexión verificada y columnas `gastos.id_deuda`, `deducciones_fijas.categoria` e `id_deuda` confirmadas en `information_schema`. **[ ] Pendiente:** actualizar la variable `DATABASE_URL` en Render.
- [ ] **Recuperación de contraseña — configuración pendiente:** definir en Render `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `SMTP_FROM` y `APP_URL`; probar el correo real.
- [ ] **OLB_BYTE — revisión visual pendiente:** Android con Chrome en HTTPS (contactos y compartir PDF) y la impresión de la factura.
- [ ] **Fase 3 (opcional)** — Migración a PostgreSQL con Alembic y despliegue multi-instancia (ver `DESPLIEGUE.md` §11).
- [x] **SRS v1.9 — Paso 1 (backend y base de datos, ADR-57):** catálogo cerrado de 8 categorías con colores exactos en `core/categorias.py`; columnas `gastos.id_deuda` y `deducciones_fijas.categoria`; migración idempotente en SQLite y PostgreSQL (`aplicar_migraciones()`, también usada por `migrar_a_neon.py`); esquemas Pydantic en `app/esquemas.py`; tasa implícita **simulada** por bisección sin cambiar la amortización (matizado después por ADR-58); dona agrupada por categorías con la categoría 8 alimentada por deudas activas y anti-duplicación de cuotas vinculadas; base mínima de $300.000 intacta en dona y consejero. Migraciones ejecutadas y verificadas en Neon con la URL nueva. Verificación: `compileall` OK, **630 pruebas** en verde y `generar_guia.py --verificar` sin problemas (103 archivos con ficha).
- [x] **SRS v1.9 — Paso 2 (frontend, secciones 1.2 y 1.3):** selector cerrado de 8 categorías con colores exactos en Mis Finanzas, Gastos, Trabajos Extras y Deducciones Fijas (`_categorias.html` + `js/categorias.js`); entrada de solo lectura que pega el nombre exacto; flujo «¿Es la cuota de una deuda registrada?» con `id_deuda` y preservación de valores en `sessionStorage` al volver con error; dona dibujada con `arcos_categoria` y leyenda de las 8 categorías, marcando la 8 como automática. `sw.js` en `olb-finanzas-v50`. Verificación: `node --check` OK y **638 pruebas** en verde.
- [x] **SRS v1.9 — Sección 2.1 (renombramiento y alineación):** el módulo se llama «Registro y Detalles de deudas» en tarjeta del dashboard, `<title>`, `<h1>`, contextos, docstrings, diccionario, SRS, guía y bitácora. En escritorio, los paneles «Nueva deuda» y «Deudas registradas» arrancan a la misma altura: `.rejilla-paneles--deudas` anula el `margin-top` genérico de `.panel--tabla` y fija `align-items: start`. Verificación: **641 pruebas** en verde y `generar_guia.py --verificar` sin problemas.
- [x] **SRS v1.9 — Sección 2.2 (interés implícito simulado, ADR-58):** `cuota × cuotas > total` se acepta al registrar y editar; el único error es `cuota × cuotas < total`, con el mensaje fijo «El número de cuotas por el valor de cuota no alcanza a cubrir el valor total de la deuda, revisa los datos y digítalos nuevamente». `amortizacion_simulada()` cuadra el modelo en privado (tasa ficticia, última cuota en cero) sin persistirla ni mostrarla; los pagos reales siguen con `interes = 0`. Nuevo `actualizar_deuda()` y `POST /deudas/{id}/editar` sin reescribir el historial. Verificación: **647 pruebas** en verde.
- [x] **SRS v1.9 — Sección 2.3 (tabla tipo Excel y edición responsiva):** se retira «Próximas cuotas» y cualquier campo de interés; columnas Acreedor | Total Adeudado | Cuota | No. Cuotas Pendientes | Periodicidad | Estado. En escritorio, lápiz y × al final de cada fila; el lápiz abre el modal centrado con Total, Cuota y No. Cuotas más «Actualizar»/«Cancelar». En móvil se ocultan los iconos y la fila completa abre el mismo modal (`js/deudas.js`, CSS `edicion-gasto--modal`). `sw.js` en `olb-finanzas-v51`. Verificación: `node --check` OK y **650 pruebas** en verde.
- [x] **SRS v1.9 — Sección 3.1 (deducciones fijas):** formulario en dos filas: superior de tres columnas Concepto | Categoría (selector cerrado de 8 opciones) | Valor Descontado (COP), e inferior «Quincena donde aplican los pagos». La etiqueta «Valor por pago (COP)» desaparece; en edición se usa el mismo nombre. CSS `.fila-campos--deducciones` (3 columnas desde 641 px, apilado en móvil). Verificación: **651 pruebas** en verde.
- [x] **SRS v1.9 — Sección 3.2 (vinculación condicional):** al elegir «Créditos y Obligaciones» en Deducciones Fijas, Gastos de Finanzas o Gastos de Trabajos Extras aparece la pregunta SI/NO con el texto propio de cada módulo; SI habilita «Deudas registradas» con **todas** las deudas activas (también quincenales, ADR-58 matizado); NO inhabilita guardar y muestra el mensaje exacto más el enlace «Ve a registrar la deuda». El enlace guarda campos y módulo en `sessionStorage`; al volver se restauran, se marca SI y se preselecciona la deuda recién creada desde el botón «Volver al formulario de origen». Backend exige `id_deuda` con la categoría 8. `sw.js` en `olb-finanzas-v52`. Verificación: `node --check` OK y **656 pruebas** en verde.
- [x] **SRS v1.9 — Sección 3.3 (acciones de deducciones):** en escritorio los botones Editar y Eliminar se alinean al extremo derecho de cada fila; en móvil se ocultan y al tocar la fila se abre el modal centrado con la información de la deducción y tres botones: Actualizar, Eliminar (vía `formaction`) y Cancelar. `deudas.js` atiende también `li[data-deduccion-fila]`; `sw.js` en `olb-finanzas-v53`. Verificación: `node --check` OK y **659 pruebas** en verde.
- [x] **SRS v1.9 — Bloque 4:** 4.1 Regla global `.modal-centrado` (`position: fixed; inset: 0; display: flex; align-items: center; justify-content: center; z-index: 50; padding: 1rem`) aplicada también a `details.edicion-gasto--modal[open]`, con la tarjeta como elemento flex centrado; se anula el antiguo anclaje `right:0`/`left:50%`. 4.2 Campo «Valor a pagar (COP)» en atajos (`chancucos.valor_pago`, migrado en SQLite y Neon) mostrado en la tabla y en la tarjeta de Mis Finanzas antes de «Pagar». 4.3 Recibo estilo Nequi: fondo `#f8fafc`, texto `#111827`, montos y estados `#16A34A`, cabecera azul intacta. `sw.js` en `olb-finanzas-v54`. Verificación: **663 pruebas** en verde.
- [x] **Ajuste visual SRS v1.9 (post Step 3):** la leyenda de la dona solo pinta categorías con `valor > 0` (las de cero ya no aparecen); se retiró el detalle de la deuda vinculada en la fila de deducciones porque ocupaba una cuarta celda de la grid y desplazaba Editar/Eliminar — ahora los botones quedan fijos en `grid-column: 3; justify-self: end`. `sw.js` en `olb-finanzas-v55`. Verificación: **663 pruebas** en verde.
- [x] **Ajuste de modales (SRS v1.9):** en móvil se ocultan con `!important` el lápiz y la × laterales de las deducciones (la fila sigue abriendo el modal al tocarse). En todos los modales de edición (deudas, gasto fijo y deducciones) el cierre pasa a un botón sutil `×` en la cabecera con `data-cancelar-edicion`, y se elimina «Cancelar» inferior; en deducciones el orden es Actualizar → Eliminar. `sw.js` en `olb-finanzas-v56`. Verificación: **663 pruebas** en verde.
- [x] **Leyenda única de la dona:** se eliminó el segundo `<ul>` que duplicaba las categorías; la leyenda de los arcos ya muestra nombre, color, valor y porcentaje de cada categoría con valor > 0. Se retiró también la insignia «automática · deudas» y el CSS huérfano `.dona__leyenda--categorias`. `sw.js` en `olb-finanzas-v57`. Verificación: **663 pruebas** en verde.
- [x] **Centrado directo de modales y espaciado:** la tarjeta de los modales de edición se centra por sí misma con `position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%)`, sin depender del flex del contenedor (corrige el modal de la libranza desplazado a la izquierda). Las alertas llevan `margin-bottom: 12px` y el alta de deducciones `formulario--deducciones` / `lista-gastos--deducciones` con separación, para que no queden dos avisos o paneles pegados. `sw.js` en `olb-finanzas-v58`. Verificación: **665 pruebas** en verde.
- [x] **Corrector móvil de deducciones:** el lápiz es el `<summary>` del `<details>`, no hijo directo del contenedor de acciones; se ajustó el selector a `> .lista-gastos__acciones > details > summary` con `display: none !important`. Ya no aparece ningún icono en la fila y el toque sigue abriendo el modal. `sw.js` en `olb-finanzas-v59`. Verificación: **665 pruebas** en verde.
- [x] **Selector sin cuadrito de color:** el desplegable de categorías sustituye el `<span class="dona__muestra" style="background: …">` por un punto neutro `•` (`.selector-categoria__punto`); los colores exactos se conservan solo en los arcos y la leyenda de la dona, y en el catálogo del backend. `sw.js` en `olb-finanzas-v60`. Verificación: **665 pruebas** en verde.
- [x] **Atajos guardados (SRS v1.9):** en escritorio Copiar, Pagar y Eliminar usan la clase `.atajo-accion` con altura/padding/tipografía idénticos. En móvil la tabla se convierte en filas tipo Excel con solo Descripción | Valor a pagar | Día de pago; al tocar la fila se abre un modal centrado con toda la información (referencia con Copiar al lado), cierre sutil arriba y botones abajo Pagar → Eliminar. Solo aplica a `/chancucos`, no a los atajos embebidos. `sw.js` en `olb-finanzas-v61`. Verificación: `node --check` OK y **668 pruebas** en verde.
- [x] **Atajos embebidos de Mis Finanzas en móvil:** la tarjeta muestra solo descripción y día de pago; se ocultan valor, referencia y botón Pagar. Al tocar la fila (`li[data-atajo-fila]`) se abre un modal centrado con toda la información (referencia con Copiar al lado, valor, días, enlace, favorito) y Pagar abajo. `sw.js` en `olb-finanzas-v62`. Verificación: `node --check` OK y **669 pruebas** en verde.
- [x] **Modal de atajos en Mis Finanzas sin enlace visible:** se eliminó la fila «Enlace de pago» del modal (la URL sigue solo en el `href` del botón) y Pagar queda centrado a ancho natural. `sw.js` en `olb-finanzas-v63`. Verificación: **669 pruebas** en verde.
- [x] **Edición de atajos y ajustes de modales:** los dos modales de atajos pierden las líneas divisorias; en móvil «Atajos guardados» recupera una cabecera compacta y columnas `max-content` para que los datos queden cerca de la descripción. El modal de `/chancucos` pasa a **editar** (descripción, referencia, valor, días, URL en input, favorito) con Actualizar → Eliminar y sin Copiar/Pagar; nuevo `actualizar_chancuco()` y `POST /chancucos/{id}/editar`. El modal de Mis Finanzas sigue solo lectura + Pagar. `sw.js` en `olb-finanzas-v64`. Verificación: **670 pruebas** en verde.
- [x] **Sin «Ver» en atajos de escritorio:** se eliminó el `<summary>Ver</summary>` de los dos modales de atajos; la apertura sigue siendo solo por clic/toque en la fila mediante `deudas.js`. `sw.js` en `olb-finanzas-v65`. Verificación: **670 pruebas** en verde.
- [x] **Copiado de atajos con estado temporal:** se eliminó el manejador duplicado de `finanzas.js`; `app.js` es el único que gestiona `[data-copiar]`, muestra «¡Copiado!» solo en el botón pulsado, restaura los demás y vuelve a «Copiar» a los **5 segundos**. `sw.js` en `olb-finanzas-v66`. Verificación: `node --check` OK y **671 pruebas** en verde.
- [x] **Tabla de deudas compacta:** se eliminó la fila de detalle con «Cuotas aplicadas» y el mensaje «Esta deuda no tiene cuotas aplicadas»; ahora hay una sola fila por deuda. `.tabla-contenedor--deudas` limita la altura a 280 px (≈4 deudas) con scroll vertical, cabecera fija y scroll horizontal para el resto de columnas. `sw.js` en `olb-finanzas-v67`. Verificación: **671 pruebas** en verde.
- [x] **Alineación de acciones y columna de cuotas en deudas:** el lápiz y la × van dentro de `.deudas__acciones-contenido` (flex) y la celda conserva `vertical-align: middle`, para que queden centrados con la línea divisoria en móvil y escritorio. El encabezado «No. de cuotas pendientes» va en tres líneas y la columna se limita a 92 px centrada. `sw.js` en `olb-finanzas-v68`. Verificación: **671 pruebas** en verde.
- [x] **Paneles de deudas a la misma altura:** `.rejilla-paneles--deudas` usa `align-items: stretch` en escritorio, de modo que «Nueva deuda» y «Deudas registradas» comparten altura y top exactos; se conserva `margin-top: 0` del panel de tabla. `sw.js` en `olb-finanzas-v69`. Verificación: **671 pruebas** en verde.
- [x] **Tipografía de atajos embebidos:** `.lista-atajos__descripcion` y `.lista-atajos__referencia code` usan ambos `font-size: 0.85rem`, para que la descripción no destaque sobre el número de referencia en Mis Finanzas. `sw.js` en `olb-finanzas-v70`. Verificación: **671 pruebas** en verde.
- [x] **Atajos guardados sin texto «Details» y letra menor:** los `<details>` llevan un `<summary class="sr-only">` para evitar la etiqueta por defecto del navegador sobre la descripción; la tabla usa `font-size: 0.8rem`; y el modal de edición ya no muestra «Segundo día (opcional)» (el valor se conserva en un campo oculto). `sw.js` en `olb-finanzas-v71`. Verificación: **671 pruebas** en verde.
- [x] **Actualizar en lugar de Pagar en Atajos guardados (escritorio):** la fila ya no ofrece «Pagar»; el botón «Actualizar» (`data-abrir-atajo`) abre el modal de edición con el mismo grosor que Copiar/Eliminar. El enlace sigue en un input `type="url"` con ancho controlado para no romper el modal. Solo aplica a `/chancucos`. `sw.js` en `olb-finanzas-v72`. Verificación: `node --check` OK y **671 pruebas** en verde.
- [x] **Mis metas y abonos — ajustes visuales:** en escritorio `.abonos-scroll` baja a `max-height: 180px` (dos filas visibles, scroll interno, sin opacity ni desbordamiento); en móvil `.meta__cabecera` usa `flex-wrap: nowrap` para que «Eliminar» quede arriba a la derecha junto al nombre de la meta. Texto de ayuda actualizado. `sw.js` en `olb-finanzas-v73`. Verificación: **674 pruebas** en verde.
- [x] **Corrector móvil de atajos guardados:** «Actualizar» sigue existiendo solo en escritorio; en móvil se oculta junto a los demás controles de la celda de acciones (la regla ahora incluye `> button`). El toque en la fila sigue abriendo el modal. `sw.js` en `olb-finanzas-v74`. Verificación: **674 pruebas** en verde.
- [ ] **SRS v1.9 — Paso 3 (verificación final) pendiente:** revisión visual en navegador de dona, consejero, modales de deudas/deducciones, formulario de deducciones, flujo SI/NO y recibo en 360/390/768/escritorio. La comprobación programática ya está cubierta: dona y consejero suman egresos sin duplicar `id_deuda` y respetan el colchón de $300.000 (`test_categorias_cerradas.py`, `test_selector_categoria_ui.py`).
