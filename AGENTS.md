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

- **`ADMIN_OLB`**: Propietario del sistema. Acceso total a los 4 módulos (`Mis Finanzas`, `OLB_BYTE`, `Resumen de Deudas`, `Trabajos Extras`) y bloque exclusivo de **Chancucos** dentro de `Mis Finanzas`. La administración de cuentas se abre desde `Mi Perfil`.
- **`USER_FINANZAS`**: Usuario público. Acceso a `Mis Finanzas` (incluye sus submódulos), `Resumen de Deudas` y `Trabajos Extras`, con anuncios no invasivos. `OLB_BYTE` y `Chancucos` están bloqueados a nivel de UI **y** de endpoint (403).
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
    ├── tests/                          # Suite completa (478 pruebas)
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
        │   ├── consejero.py            # Bola de nieve, avalancha y metas (v1.7)
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
- **Deudas (SRS v1.5, ADR-21):** seis datos (acreedor, descripción, saldo, cuota, cuotas pendientes y periodicidad quincenal/mensual). Sin tasa capturada ni fecha límite: la tasa se deriva por bisección de `saldo = cuota × (1 − (1+r)^−n) / r` con 10 decimales. Al abrir el módulo se aplican las cuotas vencidas en `pagos_deuda` (idempotente por `UNIQUE(id_deuda, numero_cuota)`) y la última cuota deja el saldo exacto en cero. No existe abono manual.
- **Metas con «Ambas quincenas» (ADR-22):** `quincena = 3` guarda la cuota mensual y la reparte entre los dos pagos (`valor_por_pago`). Sigue siendo planificación: no se resta del saldo libre.
- **Capacidad de endeudamiento y consejero (SRS v1.7, ADR-44 y ADR-45):** el ingreso del mes (quincenas + extras cobrados) se reparte entre gastos fijos, cuota mensual de deudas y libre; el semáforo usa el porcentaje de deuda (≤ 20 % verde, ≤ 35 % ámbar, más rojo). El consejero solo se activa con un excedente **mayor** que $300.000 y compara bola de nieve (saldo menor) contra avalancha (tasa mayor) a 12 meses; sin deudas dirige el excedente a las metas.
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
.\.venv\Scripts\python -m pytest -q          # suite completa (478 pruebas)
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
- [x] **SRS v1.2 — Bloque 2 (navegación y RBAC):** header reducido a `Inicio`, `Mi Perfil` y `Salir`; dashboard con las 4 tarjetas principales; `OLB_BYTE` exclusivo de `ADMIN_OLB`; `Resumen de Deudas` y `Trabajos Extras` pasan a acceso general; Chancucos y Usuarios salen del dashboard (Usuarios accesible desde el perfil del administrador).
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
- [x] **Logo oficial en la factura:** la cabecera usa `assets/Logotipo OLB Byte de Alta Tecnología.png` (modo de mezcla `screen` para quitar su fondo negro). `base.html` tiene el bloque `estilos` y la factura carga su CSS ahí. Los logos se cachean en memoria (`logo_como_data_uri`). Prueba en `tests/test_factura_pdf.py` (480 pruebas en verde).
- [ ] **Pendiente de revisión:** el PDF impreso con el modo de mezcla del logo; conviene una prueba de descarga en tu equipo.
- [x] **Botones de regreso en OLB_BYTE:** cada pantalla tiene «← Volver» (Ventas vuelve al inicio; Pendientes, Cartera, Garantías, Analítica y Factura vuelven a Ventas; Cobro vuelve a Pendientes). Prueba en `tests/test_olb_ui.py` (454 pruebas en verde).
- [x] **Decisión (propietario):** Analítica y Cartera muestran ganancia y saldos sin protección adicional; el módulo es de uso exclusivo del administrador, por lo que no se requiere ocultarlos. La tabla de órdenes del panel sí oculta ganancia y saldo (ADR-43).
- [ ] **OLB_BYTE — revisión visual pendiente:** Android con Chrome en HTTPS (contactos y compartir PDF) y la impresión de la factura.
- [ ] **Fase 3 (opcional)** — Migración a PostgreSQL con Alembic y despliegue multi-instancia (ver `DESPLIEGUE.md` §11).
