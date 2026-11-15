# Memoria y Contexto del Proyecto: OLB_BYTE & Finanzas Personales

> Documento vivo. Toda decisión técnica, cambio o aprendizaje se registra aquí (ver `constitution.md`, principio 5).

## Contexto e Historia del Proyecto

El proyecto nace de la necesidad de digitalizar un modelo de control financiero personal y comercial previamente gestionado en hojas de cálculo de Google Sheets (`FINANZAS NEW`).

El sistema cumple una **doble función clave**:

1. **Pública & Monetizable:** herramienta intuitiva de finanzas y liquidación de nómina para usuarios en Colombia, monetizada con anuncios no invasivos.
2. **Privada (OLB_BYTE):** centro de control exclusivo del negocio de gadgets del fundador (cartera, cuentas por cobrar, garantías, abonos y facturas enviables por WhatsApp).

---

## Decisiones Críticas de Arquitectura (ADR)

### ADR-01 — Sistema de Roles Dual (RBAC)
- Control de acceso estricto a nivel de endpoint (dependencias FastAPI) y de visibilidad en plantillas Jinja2.
- `ADMIN_OLB`: acceso total (4 tarjetas + Chancucos).
- `USER_FINANZAS`: solo `Mis Finanzas` + anuncios; endpoints de la tienda bloqueados.
- **Estado:** UI preparada en Tarea 1; **sesión real implementada en la Tarea 5** (cookie firmada, bloqueo 403 en servidor).

### ADR-02 — Tablero Principal de 4 Tarjetas
Pantalla limpia con 4 accesos:
- **Mis Finanzas:** nómina, recargos y presupuesto quincenal.
- **OLB_BYTE:** comercial y cartera (privado, deshabilitado/oculto para `USER_FINANZAS`).
- **Resumen de Deudas:** pasivos acumulados.
- **Trabajos Extras:** ingresos independientes al salario base.
Más una sección aparte de **Chancucos** exclusiva de `ADMIN_OLB`.

### ADR-03 — Motor Salarial Reactivo ("Live Update")
Recálculo en tiempo real (<100 ms) sin recargar página. Se implementa con funciones puras en Python y **mejora progresiva**: `fetch` nativo contra un endpoint JSON (`POST /finanzas/calcular`) con debounce de 150 ms. Se descartó HTMX para no depender de un CDN ni de JavaScript de terceros; el POST clásico sigue funcionando como respaldo sin JS.
- **Estado:** implementado en la Tarea 6.

### ADR-04 — Stack 100% Python (reemplaza el supuesto React/Vite)
- **FastAPI** como servidor y capa de reglas de negocio.
- **Jinja2** para renderizado server-side (una sola fuente de verdad de la lógica).
- **HTMX** + JavaScript mínimo para interactividad y PWA.
- **Consecuencia:** la interactividad se resuelve con `fetch` nativo (sin CDN) y el renderizado de resultados en servidor.
- **Motivo:** el usuario definió Python como lenguaje único del proyecto; reduce duplicación de lógica y facilita auditoría contable.
- **Consecuencia:** se elimina la estructura `frontend/src/App.jsx`; las vistas viven en `backend/app/templates`.
- **Estado:** aplicado desde Tarea 1.

### ADR-05 — Documentación obligatoria del código
- Docstring en **todas** las funciones, métodos y clases (propósito, Args, Returns, Raises).
- Comentarios explícitos en cada regla de negocio y en cada bloque no trivial.
- Nombres de dominio en español (`calcular_deducciones_ley`, `dias_incapacidad_rollover`).
- **Motivo:** mantenibilidad y transferencia del proyecto a futuros desarrolladores.

### ADR-06 — Diccionario de datos como contrato previo a la base de datos
- Se creó `diccionario_datos.md` con entidades, campos, tipos sugeridos, obligatoriedad, reglas de negocio e integridad.
- Ninguna tabla se crea sin estar documentada y aprobada allí.
- **Motivo:** evitar migraciones destructivas y asegurar trazabilidad del cálculo salarial.

### ADR-07 — Autenticación sin dependencias externas (Tarea 5)
- Contraseñas con **PBKDF2-HMAC-SHA256** (260.000 iteraciones, sal aleatoria de 16 bytes) usando `hashlib`; formato `pbkdf2_sha256$iteraciones$sal$hash`.
- Sesión con **JWT HS256** implementado con `hmac` + `base64url` de la librería estándar: `sub`, `rol`, `alias`, `iat`, `exp` (480 minutos).
- El token viaja en una cookie **`HttpOnly`**, `SameSite=Lax`, `Path=/`; en producción se marca `Secure` automáticamente (`ENTORNO=produccion`).
- Los usuarios viven en SQLite desde el ADR-09; las cuentas semilla son solo de demostración.
- **Motivo:** evitar `passlib`/`python-jose` y su superficie de dependencias, manteniendo primitivas estándar y auditables.
- **Consecuencia:** al migrar a PostgreSQL solo cambia `DATABASE_URL`; routers y dependencias se mantienen.

### ADR-08 — Respuesta diferenciada para sesión ausente
- HTML: redirección **303 a `/login`** (excepto `/` que también redirige).
- Peticiones JSON (`Accept: application/json`): **401** con `{"ok": false, "errores": [...]}` para que la calculadora no pinte HTML dentro del panel.
- **Motivo:** una sola dependencia (`obtener_usuario_actual`) sirve a vistas y a la UI reactiva.

### ADR-09 — Persistencia con SQLite y SQLAlchemy 2.x (bloques A–B)
- Motor `create_engine` con `DATABASE_URL`; por defecto `backend/datos/finanzas.db`.
- `Base.metadata.create_all` al arrancar (`inicializar_base_datos`) y siembra de cuentas demo solo si `usuarios` está vacía.
- Claves primarias `String(32)` con UUID hexadecimal, dinero `Numeric(14,2)`, enums como texto con `CHECK`; portable a PostgreSQL.
- Los servicios reciben una `Session`, hacen `commit` y devuelven entidades; los routers solo traducen formularios.
- Respaldos con la API `sqlite3.Connection.backup` (`scripts/respaldo.py`), no copiando el archivo.
- **Motivo:** el usuario pidió expresamente **solo SQLite por ahora**; se evita la complejidad operativa de PostgreSQL y Alembic mientras el producto es de un solo administrador.
- **Consecuencia:** un solo proceso Uvicorn (`--workers 1`) y migración a PostgreSQL documentada en `DESPLIEGUE.md` §11.

### ADR-10 — Protección CSRF por origen y cabeceras de seguridad
- Se descartó el token CSRF por formulario (más fricción en Jinja2) a favor de un middleware que, en métodos de escritura, compara el `Origin` con el `Host` de la petición y rechaza `Sec-Fetch-Site: cross-site` con **403**.
- Todas las respuestas añaden `Content-Security-Policy`, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy` y `Permissions-Policy`.
- **Motivo:** la cookie ya es `SameSite=Lax`; la comprobación de origen cubre el caso residual sin introducir estado ni tokens ocultos.
- **Consecuencia:** el proxy inverso debe conservar `Host`, `Origin` y `Sec-Fetch-Site`; está documentado en `DESPLIEGUE.md` §6.

### ADR-11 — Límite de intentos de login y auditoría
- Ventana deslizante en memoria por **IP + correo** (`core/limitador.py`), máximo configurable con `LIMITE_INTENTOS_LOGIN` (5 por defecto).
- Tras el máximo, `POST /login` responde **429** con el tiempo restante; un acceso correcto limpia la clave.
- Cada intento (`LOGIN_OK`, `LOGIN_FALLIDO`) y cada cambio sensible (rol, estado, producto, venta, abono) se guarda en `auditoria`.
- **Motivo:** frenar fuerza bruta sin añadir Redis en esta fase; la bitácora facilita investigar incidentes.
- **Consecuencia:** en un despliegue con varias instancias el limitador debe moverse a Redis; anotado como pendiente en `DESPLIEGUE.md`.

### ADR-12 — Onboarding obligatorio y quincenas independientes (SRS v1.2)
- **Contexto:** el primer login llevaba directo al tablero y el perfil guardaba un único `porcentaje_quincenal`, insuficiente cuando las dos quincenas se pagan con porcentajes distintos.
- **Decisión:**
  - `UsuarioSesion.perfil_configurado` se **calcula por petición** consultando `perfiles_financieros`; no viaja en el token para que el onboarding se libere en el mismo instante en que se guarda.
  - `obtener_usuario_actual` lanza `OnboardingRequerido`; `app.main` lo traduce a **303 a `/perfil?bienvenida=1`** (HTML) o **409 JSON** (fetch). Las rutas del propio perfil usan `obtener_usuario_sin_onboarding` para evitar bucles.
  - El perfil guarda `porcentaje_quincena_1`, `porcentaje_quincena_2` y `quincena_deducciones`. En el caso B (el usuario solo conoce el neto sin descuentos) el servidor calcula ambos porcentajes y deduce por descarte la quincena sujeta a deducciones.
  - El guardado exitoso redirige a `/?guardado=1`, donde el tablero confirma la configuración.
- **Consecuencia:** ningún módulo de negocio es accesible antes de configurar sueldo y modalidad. Las bases existentes se migran con `ALTER TABLE` idempotente en SQLite y el backfill desde `porcentaje_quincenal`; en PostgreSQL/Alembic será una migración versionada.

### ADR-13 — Navegación mínima y RBAC por módulo (SRS v1.2, bloque 2)
- **Contexto:** el header acumulaba 12 pestañas y el dashboard 9 tarjetas que mezclaban módulos principales con submódulos, además de exigir administrador para Deudas y Trabajos.
- **Decisión:**
  - Header con **solo tres opciones**: `Inicio`, `Mi Perfil` y `Salir`. Los módulos se abren desde el dashboard.
  - Dashboard con **cuatro tarjetas**: `Mis Finanzas`, `OLB_BYTE` (solo `ADMIN_OLB`), `Resumen de Deudas` y `Trabajos Extras`.
  - `OLB_BYTE` y `Chancucos` permanecen como rutas exclusivas del administrador (**403** para `USER_FINANZAS`). `Deudas` y `Trabajos Extras` dejan de exigir rol administrador porque el SRS v1.2 los declara de acceso general; los servicios ya filtran por `id_usuario`.
  - La administración de cuentas (`/admin/usuarios`) sale del dashboard y queda enlazada desde `Mi Perfil`, visible solo para el administrador.
- **Consecuencia:** menos ruido visual y un único punto de entrada a los submódulos, que en el bloque 3 pasarán a vivir dentro de `Mis Finanzas`.

### ADR-14 — Layout de dos columnas y submódulos encapsulados (SRS v1.2, bloque 3)
- **Contexto:** "Mis Finanzas" era una sola columna con la calculadora, y Gastos, Historial, Incapacidades y Chancucos vivían como módulos externos. El usuario no veía de un vistazo cuánto le quedaba libre en cada quincena.
- **Decisión:**
  - `templates/finanzas/index.html` se reorganiza en `rejilla-finanzas` de **dos columnas**: izquierda con una tarjeta por pago (ingreso proyectado, gastos fijos, deducciones y saldo libre) y derecha con la liquidación, el resultado y el desglose de recargos. En pantallas angostas las columnas se apilan.
  - `servicios/quincenas.py` calcula el resumen: en `QUINCENAL` hay dos tarjetas; en `MENSUAL`, una sola. Las deducciones de ley del mes se imputan **solo** a `perfil.quincena_deducciones`.
  - `Gasto.quincena` (`1`, `2` o `NULL`) permite asignar obligaciones fijas a un pago. Los gastos antiguos sin quincena se muestran en la quincena 1 marcados como «todo el mes». La migración es un `ALTER TABLE` idempotente en `core/base_datos.py`.
  - La liquidación derecha ajusta las deducciones de ley con `perfil.sueldo_basico` mensual cuando se selecciona una quincena; la otra quincena queda sin aportes. Los gastos que se restan en «Disponible después de gastos» son los del periodo visible, no los del mes completo.
  - Gastos, Historial, Incapacidades y Chancucos se encapsulan con `finanzas/_subnav.html`. Chancucos se embebe al final de `/finanzas` solo para `ADMIN_OLB`; sus POST aceptan `origen=finanzas` y vuelven al ancla correspondiente.
  - Se retira la plantilla «Semana típica» de `static/js/finanzas.js`; queda solo el botón **Limpiar**.
- **Consecuencia:** un único punto de entrada a los submódulos y coherencia visual entre lo que el usuario configura en su perfil y lo que ve en la liquidación.

---

### ADR-15 — Layout 50/50, edición de gastos fijos y reactividad en pesos (SRS v1.3, bloque 2)
- **Contexto:** el layout de dos columnas del v1.2 seguía mostrando el formulario de nómina como una lista larga y plana, con año/mes y descuento de incapacidad en la cabecera; los chancucos ocupaban una sección inferior separada y no era posible corregir un gasto fijo sin borrarlo.
- **Decisión:**
  - La rejilla pasa a `rejilla-finanzas--5050` (dos columnas de igual ancho). En `≤ 900 px` se apila; el modificador se incluye explícitamente en el media query para no ganar por orden de aparición.
  - La columna izquierda se organiza en tres sub-contenedores verticales: **Quincena 1**, **Quincena 2** y **Atajos de pago** (antes *chancucos*) en modo solo lectura.
  - La columna derecha respeta un orden fijo y reactivo: sueldo → deducciones de ley con valor en pesos → horas extras en cuadrícula 2 × 3 → Calcular / Limpiar / Guardar → auxilio de transporte → incapacidades compactas → resultado → desglose.
  - Año, mes y quincena del formulario dejan de mostrarse pero se envían como campos `hidden`, porque el motor los necesita para imputar deducciones y gastos al periodo correcto.
  - El descuento por incapacidad sale de la cabecera: se alimenta del bloque compacto de incapacidades o del rollover pendiente.
  - Las deducciones se pintan con `data-deduccion` (no con `data-campo`) para no colisionar con la tabla de resultados; `pintarDeduccion()` recorre los dos destinos.
  - `actualizar_gasto()` y `POST /gastos/{id_gasto}/editar` permiten corregir monto y descripción conservando la fecha original, con auditoría `GASTO_ACTUALIZADO`.
- **Consecuencia:** la columna izquierda queda para lo que el usuario *paga* y la derecha para lo que *cobra*; la edición de recibos variables ya no obliga a borrar y recrear el gasto, y los valores en pesos acompañan la escritura sin recargar la página.

---

### ADR-16 — Atajos de pago con tres campos y migración por reconstrucción (SRS v1.3, bloque 2.1)
- **Contexto:** el atajo de pago pedía `entidad` (EPM) y `tipo_servicio` (Energía), dos campos que el usuario escribía pensando en una sola cosa. Además, `tipo_servicio` era `NOT NULL`, lo que convertía cualquier simplificación en un problema de migración.
- **Decisión:**
  - El atajo queda en tres datos: `descripcion`, `numero_referencia` y `url_pago`. La descripción absorbe entidad y servicio («EPM energía»).
  - `url_pago` se mantiene **opcional**: hay recibos que solo se pagan en ventanilla y forzar el enlace impediría guardar el atajo, perdiendo igualmente el número copiable.
  - `diccionario_datos.md` se actualiza **antes** que el código (§9), porque es la fuente única del modelo.
  - La migración **reconstruye** la tabla (`chancucos_v13` → copia → `DROP` → `RENAME`) en lugar de renombrar columnas: así desaparece de verdad `tipo_servicio` y no queda una columna obligatoria sin valor que rompería cada `INSERT`.
  - La copia de datos fusiona `entidad · tipo_servicio` con `CASE`, para no dejar el separador colgando cuando no había servicio.
  - La migración es idempotente: si `descripcion` ya existe, no hace nada.
- **Consecuencia:** un formulario de tres campos en ambas vistas (panel propio y bloque embebido) y una tabla más limpia. El coste es una migración destructiva de columna, verificada sobre copia y no sobre la base en uso.

---

### ADR-17 — El presupuesto es un módulo propio, no una pestaña de `/gastos` (SRS v1.3, bloque 3)
- **Contexto:** «Gastos y Presupuesto» mezclaba en una sola pantalla el registro de gastos fijos y la proyección de metas. La proyección necesita tablas, rutas y estados propios (cuota, duración, abonos por mes, alerta de liquidez) que no encajan en el formulario de gastos.
- **Decisión:**
  - Se crean `proyecciones_ahorro` y `abonos_proyeccion` (§9.1 y §9.2 del diccionario) y un router `/presupuesto` con su plantilla, su JavaScript y sus pruebas.
  - `/gastos` **se conserva** como listado secundario de gastos fijos; la pestaña de la subnavegación apunta al planificador y desde allí se llega al registro de gastos.
  - La cuota se descuenta de la quincena elegida (`quincena`), igual que los gastos fijos, para que el saldo libre del resumen siga siendo la fuente de verdad.
  - Un gasto `FIJO` no tiene total cerrado: se compara contra una ventana de 12 meses. Un gasto `LIMITADO` exige `meses` (1–120) y calcula `valor_mensual × meses`.
  - Solo existe **un abono por meta y mes** (`UNIQUE(id_proyeccion, anio, mes)`): volver a registrarlo corrige el monto, nunca duplica.
  - El umbral de alerta de liquidez vive en `ahorro.UMBRAL_ALERTA = Decimal("300000")`, no repartido por la plantilla.
- **Consecuencia:** el diagnóstico («te sobran $X del sueldo») y la alerta crítica son datos del servidor, no texto fijo; el planificador puede crecer (categorías, reportes) sin tocar el formulario de gastos. El coste es una pantalla más y dos tablas nuevas.

---

## Parámetros de Dominio Salarial (Colombia)

| Parámetro | Valor parametrizado | Regla |
| --- | --- | --- |
| Jornada mensual | 210 horas | Sobre 42 h semanales legales. |
| Salud empleado | 4% | Automático, sólo lectura, sobre sueldo básico. |
| Pensión empleado | 4% | Automático, sólo lectura, sobre sueldo básico. |
| Tope auxilio de transporte | 2 SMMLV (**$3.501.810 COP**) | Si `Sueldo + Recargos` > tope → auxilio = $0. |
| Auxilio de transporte (valor) | Parametrizable | Se asigna sólo si no supera el tope. |
| Incapacidad días 1–2 | 100% del salario | A cargo del empleador, sin descuento. |
| Incapacidad días 3+ | 66.67% del salario | Descuento del 33.33% a cargo de EPS. |

> Todos los valores viven en `backend/app/core/config.py` (`ParametrosNomina`) para evitar números mágicos.

---

## Módulo Especial: Cruce de Meses e Incapacidades (Rollover)

- Cuando el rango de una incapacidad abarca días del mes siguiente, el sistema liquida los días del mes activo y **persiste** los días restantes.
- Al iniciar el ciclo fiscal siguiente, la app inyecta ese saldo como **Deducción de Incapacidad Arrastrada**.
- Entidades asociadas: `incapacidades` y `saldos_incapacidad` en `diccionario_datos.md`.

---

## Módulo de Referencias y Accesos de Pago ("Chancucos")

- Lista de referencias frecuentes (vivienda, remodelación, gas, energía, agua, internet, cadenas).
- **Acción 1:** copiar código al portapapeles con un clic.
- **Acción 2:** botón *Pagar* que redirige a la URL oficial.
- **Estado:** exclusivo de `ADMIN_OLB`; proyección a perfiles de usuario.

---

## Bitácora de Cambios

### 2026-11-13 — Cierre de la orden SRS v1.2

Los tres bloques de la orden de corrección y refactorización quedaron implementados, verificados y validados por el usuario:

1. **Onboarding y perfil quincenal:** acceso obligatorio al perfil, caso A y caso B, y migración de `perfiles_financieros`.
2. **Navegación y RBAC:** header con `Inicio`, `Mi Perfil` y `Salir`; dashboard de 4 tarjetas; `OLB_BYTE` y Chancucos exclusivos de `ADMIN_OLB`.
3. **Layout de Mis Finanzas:** dos columnas con quincenas y saldo libre, gastos fijos imputados por pago, deducciones ligadas a la quincena del perfil, subnavegación interna y Chancucos embebidos.

**Estado final:** `python -m compileall` OK y **203 pruebas** con `pytest` en verde. Único pendiente del plan: la fase opcional de PostgreSQL/Alembic.

---

### 2026-11-13 — SRS v1.2, bloque 3: layout de Mis Finanzas y submódulos

**Objetivo:** convertir "Mis Finanzas" en el centro real del módulo, con quincenas visibles, gastos fijos imputados y Chancucos integrados.

**Cambios realizados**
1. `modelos.py` — `Gasto.quincena` (`SMALLINT`, `NULL` = mes completo) con `CHECK (quincena IS NULL OR quincena IN (1,2))`.
2. `core/base_datos.py` — `_migrar_columnas_gastos()` agrega la columna con `ALTER TABLE` idempotente.
3. `servicios/gastos.py` — `crear_gasto(..., quincena=...)`, `listar_gastos(..., quincena=...)`, `total_gastos_quincena` y `total_gastos_periodo` (los gastos sin quincena se imputan a la primera).
4. `servicios/quincenas.py` (nuevo) — `ResumenQuincena` y `resumen_quincenas` con ingreso, gastos, deducciones y saldo libre por pago.
5. `routers/finanzas.py` — contexto con `resumen_quincenas`, `chancucos`, `seccion`, `gasto_periodo` y banderas de gasto/chancuco; `_deducciones_segun_quincena` imputa salud y pensión del mes solo a la quincena del perfil.
6. `routers/gastos.py` — acepta `quincena` y `origen=finanzas`; redirige a `/finanzas?guardado_gasto=1#quincenas` o con `error_gasto`. El formulario de `/gastos` incorpora el selector de quincena y la tabla muestra la imputación.
7. `routers/chancucos.py` — acepta `origen=finanzas` en alta, favorito y eliminación; redirige al panel embebido.
8. `routers/incapacidades.py` y `routers/finanzas.py` (historial) — añaden `seccion` para activar la subnavegación.
9. `templates/finanzas/index.html` — reescrito con `rejilla-finanzas` de dos columnas, tarjetas de quincena, alta/eliminación de gastos fijos y sección inferior de Chancucos; se elimina el bloque «Semana típica».
10. `templates/finanzas/_subnav.html` (nuevo) — subnavegación del módulo incluida en finanzas, gastos, historial e incapacidades.
11. `static/js/finanzas.js` — se retira `PLANTILLA_SEMANA`; **Limpiar** es la única acción de plantilla.
12. `static/css/estilos.css` — estilos de `rejilla-finanzas`, `subnav-finanzas`, `panel--quincena`, `lista-gastos` y `formulario--compacto`.
13. `diccionario_datos.md` §7 — documenta `quincena` y su regla de imputación.
14. `tests/test_quincenas.py` (nuevo) — 9 pruebas de resumen, gastos por quincena, deducciones por perfil, layout y Chancucos embebidos.

**Verificación**
- `python -m compileall` sin errores.
- `pytest` → **203 pruebas en verde** (194 previas + 9 netas del bloque 3).
- Verificación HTTP en vivo: `/finanzas` muestra las dos quincenas, la subnavegación y Chancucos para el administrador; `/gastos`, `/finanzas/historial` e `/incapacidades` activan su pestaña. Con perfil 40/60 y deducciones en Q1, `/finanzas/calcular` devuelve `$139.360` de salud y pensión en Q1 y `$0` en Q2.

---

### 2026-11-13 — SRS v1.2, bloque 2: navegación mínima y RBAC

**Objetivo:** eliminar la dispersión de pestañas y tarjetas, y alinear el control de acceso con los cuatro módulos principales.

**Cambios realizados**
1. `templates/base.html` — el header queda con `Inicio`, `Mi Perfil` y `Salir`; se retiran Mis Finanzas, Gastos, Historial, Incapacidades, OLB_BYTE, Deudas, Trabajos, Chancucos y Usuarios.
2. `routers/vistas.py` — `TARJETAS_DASHBOARD` se reduce a cuatro entradas: Mis Finanzas, OLB_BYTE (`solo_admin`), Resumen de Deudas y Trabajos Extras (ambas de acceso general). El contexto del dashboard deja de exponer `perfil` y `mostrar_chancucos`.
3. `templates/dashboard.html` — se elimina la sección «Accesos exclusivos» (Chancucos y Usuarios) y el aviso de perfil incompleto, ya cubierto por el onboarding.
4. `routers/deudas.py` y `routers/trabajos.py` — se retira `exigir_administrador`; los servicios ya filtran por `id_usuario`, por lo que cada cuenta ve solo sus registros.
5. `templates/perfil/index.html` — panel «Administración de cuentas» visible solo para `ADMIN_OLB`, con enlace a `/admin/usuarios`, para no perder la gestión de roles al retirarla del dashboard.
6. Pruebas: `test_vistas.py` verifica las cuatro tarjetas y las tres opciones del header; `test_auth.py` confirma 403 solo en OLB_BYTE y Chancucos; `test_incapacidades_vistas.py` comprueba el acceso directo de ambos roles.

**Verificación**
- `python -m compileall` sin errores.
- `pytest` → **194 pruebas en verde**.

---

### 2026-11-13 — SRS v1.2, bloque 1: onboarding obligatorio y perfil quincenal

**Objetivo:** impedir el acceso a los módulos sin configuración salarial y modelar quincenas con porcentajes independientes.

**Cambios realizados**
1. `modelos.py` — `PerfilFinanciero` reemplaza `porcentaje_quincenal` por `porcentaje_quincena_1`, `porcentaje_quincena_2` y `quincena_deducciones`, con `CHECK` de rango y de quincena válida.
2. `core/base_datos.py` — `_migrar_columnas_perfil()` agrega las columnas con `ALTER TABLE` (idempotente) y hace backfill desde el campo antiguo: Q1 = valor previo, Q2 = 100 − Q1, deducciones = quincena 1.
3. `servicios/perfiles.py` — nuevas funciones `validar_quincenas`, `calcular_quincenas_desde_neto`, `porcentajes_quincena` y `perfil_configurado`; `guardar_perfil` acepta los dos porcentajes y la quincena de deducciones; `sueldo_del_periodo` prorratea según el porcentaje de cada quincena.
4. `dependencias.py` — `UsuarioSesion.perfil_configurado` (calculado por petición), excepción `OnboardingRequerido` y dependencia `obtener_usuario_sin_onboarding` para las rutas del perfil.
5. `main.py` — handler de onboarding: 303 a `/perfil?bienvenida=1` para navegación y 409 JSON para la UI reactiva.
6. `routers/perfil.py` — formulario de bienvenida con alias, sueldo, modalidad, caso A (porcentajes Q1/Q2 + quincena de deducciones) y caso B (neto de la quincena sin descuentos); el guardado redirige a `/?guardado=1`.
7. `templates/perfil/index.html` y `static/js/perfil.js` — saludo «¡Hola [alias], bienvenido!», bloques condicionales por modalidad y caso, y autocompletado Q2 = 100 − Q1.
8. `static/css/estilos.css` — estilos de `grupo-quincenal`, `subgrupo-quincenal`, `opciones` y `opcion`.
9. `routers/vistas.py` y `templates/dashboard.html` — bandera `guardado` y banner de confirmación.
10. `tests/conftest.py` — siembra de perfil 50/50 para las cuentas demo en cada prueba; `tests/test_perfiles.py` reescrito con 15 pruebas de quincenas, caso B y onboarding.
11. `tests/test_finanzas_vistas.py` — la validación JSON se ejercita con un sueldo no numérico (un sueldo vacío ahora se toma del perfil).
12. `tests/test_seguridad_http.py` — las cuentas desechables reciben perfil para que las pruebas de seguridad no choquen con el onboarding.

**Verificación**
- `python -m compileall` sin errores.
- `pytest` → **193 pruebas en verde** (185 anteriores + 8 netas del bloque 1).

---

### 2026-11-13 — Limpieza de skills instaladas
**Motivo:** el instalador de skills creó una copia de 11 skills de terceros en ~50 carpetas ocultas por agente (`.claude`, `.agents`, `.posit`, `.tabnine`, etc.), además de `skills/`, `data/skills` y `skills-lock.json`.

**Acción:**
- Se eliminaron 50 carpetas ocultas, `skills/`, `data/` y `skills-lock.json`.
- Se conservó únicamente `.opencode/skills/olb-finanzas-workflow.md` (skill propia del proyecto).
- Impacto técnico: ninguno; ninguna de esas skills era usada por el código (el stack es Python puro y no hay despliegue Vercel ni React).

**Estado de la raíz:** `.opencode/`, `backend/` y los 7 documentos de control.

---

### 2026-11-14 — SRS v1.3, bloque 1: navegación general y sub-pestañas estilizadas

**Objetivo:** modernizar visualmente la navegación general (header) y la sub-navegación interna de Mis Finanzas con hover, indicación activa clara y accesibilidad ARIA.

**Cambios realizados:**
1. `templates/base.html` — navegación superior reducida a Inicio y Mi Perfil, con comprobación dinámica de ruta (`request.url.path`) para aplicar la clase `.navegacion__enlace--activo` y `aria-current="page"`.
2. `templates/finanzas/_subnav.html` — sub-navegación interna ajustada a 4 pestañas oficiales: `Resumen / Liquidación`, `Gastos y Presupuesto`, `Configurar Atajos de Pago` e `Historial de Registros`.
3. `routers/chancucos.py` y `templates/chancucos/index.html` — contexto actualizado a `seccion="atajos"`, título "Configurar Atajos de Pago" e inclusión del subnav común.
4. `static/css/estilos.css` — estilos interactivos para `.navegacion__enlace` y `.subnav-finanzas__enlace` con transiciones de hover, elevación ligera (`transform: translateY(-1px)`), degradado de fondo en activo y sombra sutil.
5. `tests/test_vistas.py` y `tests/test_trabajos_chancucos.py` — pruebas actualizadas verificando el resaltado activo y el atributo `aria-current="page"`.

**Verificación:**
- `python -m compileall` sin errores.
- `pytest` → **206 pruebas en verde**.
- Verificación HTTP en vivo comprobada.


---

### 2026-11-15 — SRS v1.3, bloque 2: layout 50/50, edición de gastos y reactividad en pesos

**Objetivo:** reestructurar la vista principal de Mis Finanzas en dos columnas exactas, mover los atajos de pago a modo lectura con copiado rápido, permitir editar el valor de un gasto fijo y recalcular en vivo las deducciones y el auxilio de transporte.

**Cambios realizados:**
1. `templates/finanzas/index.html`
   - Contenedor `rejilla-finanzas rejilla-finanzas--5050` con dos columnas al 50 %.
   - Columna izquierda en tres sub-contenedores verticales: Quincena 1, Quincena 2 y **Atajos de pago** (solo lectura) con `<code>` + botón Copiar + botón Pagar.
   - Cada gasto fijo incorpora **Editar** (formulario en línea dentro de `<details>`) además de Eliminar.
   - Columna derecha reordenada: sueldo básico → deducciones de ley en pesos → horas extras en cuadrícula 2 × 3 → botones Calcular / Limpiar / Guardar → auxilio de transporte → incapacidades compactas → resultado → desglose.
   - Se ocultaron año, mes y quincena del formulario (viajan como `hidden` para conservar el periodo) y se retiró el descuento de incapacidad de la cabecera.
   - El bloque de incapacidades queda reducido a fecha de inicio, fecha de fin y número de días; se eliminaron «número de incapacidad» y «mes a calcular».
2. `static/css/estilos.css`
   - Layout 50/50, sub-bloques de gastos, bloque de deducciones, cuadrícula 2 × 3 de horas, panel de auxilio con aviso rojo cuando `data-aplica="si"`, lista de atajos en grid y estilos de edición en línea.
   - Nuevas clases `.auxilio__monto--anulado` (monto tachado cuando se pierde el auxilio) y `.boton--copiado` (confirmación verde).
3. `static/js/finanzas.js`
   - `pintarDeduccion()` escribe salud y pensión en **todos** los nodos `data-deduccion`.
   - `pintarValorAuxilio()` actualiza el monto y alterna la clase de anulación.
   - `prepararCopiadoRapido()` con delegación en `document`: copia y muestra **«¡Copiado!»** durante 1,2 s, con respaldo `execCommand`.
   - Cálculo inicial automático al entrar a la página (`setTimeout(calcular, 0)`).
4. `servicios/gastos.py` — nueva función `actualizar_gasto()`: valida descripción y monto, conserva la fecha original, renormaliza la quincena y permite cambiar la categoría.
5. `routers/gastos.py` — nueva ruta `POST /gastos/{id_gasto}/editar` (`name="editar_gasto"`) con auditoría `GASTO_ACTUALIZADO`, redirección a `#quincenas` cuando `origen=finanzas` y respuesta neutra si el gasto no existe o es de otro usuario.

**Decisiones:**
- La acción del formulario de edición se escribió como ruta literal (`/gastos/{id}/editar`) mientras la ruta no existía, para no romper el render con `url_for`; al crearse el endpoint queda coherente con `name="editar_gasto"`.
- El año y el mes se conservan como campos ocultos: la vista deja de mostrarlos, pero el motor sigue necesitando el periodo para imputar deducciones y gastos.

**Verificación:**
- `python -m compileall -q app` sin errores.
- `pytest -q` → **206 pruebas en verde** (5,33 s).
- Dos correcciones necesarias al ejecutar la suite:
  1. `routers/gastos.py` — la ruta `editar_gasto` necesita `response_model=None`: su retorno es la unión `HTMLResponse | RedirectResponse` y FastAPI intentaba inferir un modelo Pydantic (`FastAPIError: Invalid args for response field`). Mismo patrón que `crear_gasto`.
  2. `tests/test_quincenas.py` — la prueba de atajos embebidos buscaba el rótulo antiguo «🔗 Chancucos». Se actualizó a «🔗 Configurar atajos de pago» y «🔗 Atajos de pago», y se amplió para comprobar que el botón `data-copiar="123456"` llega al HTML del administrador.
- Duda del periodo resuelta: `routers/finanzas.py:150` usa `_entero(_texto(datos, "mes"), hoy.month, …)`, de modo que un mes vacío cae en el mes actual y la línea 162 lo reescribe en `valores`. El campo oculto nunca viaja vacío.

**Pendiente:**
- Bloques 3, 4 y 5 de la SRS v1.3 (planificador de ahorro con alerta de liquidez, ajustes de Mi Perfil e Historial de Registros).


---

### 2026-11-15 — SRS v1.3, bloque 2.1: atajos de pago con tres campos

**Objetivo:** reducir el atajo de pago a lo mínimo operable —descripción, número de referencia y link— eliminando «Entidad» y «Tipo de servicio», que obligaban a escribir dos veces la misma idea.

**Orden de ejecución (el contrato manda):**
1. `diccionario_datos.md` §9 — se reescribe la tabla: `descripcion VARCHAR(120)` absorbe `entidad` + `tipo_servicio`; `url_pago` queda **opcional y documentado como tal**; se anota la migración.
2. `modelos.py` — `Chancuco.descripcion`; desaparece el mapeo de `tipo_servicio`.
3. `core/base_datos.py` — nueva `_migrar_chancucos()`, llamada desde `inicializar_base_datos()` **después** de `crear_esquema()`.
4. `servicios/chancucos.py` — firma nueva `crear_chancuco(bd, id_usuario, descripcion, numero_referencia, url_pago=None, favorito=False)`; el listado ordena por `descripcion`.
5. `routers/chancucos.py` — parámetros `descripcion` y `numero_referencia`; auditoría con `chancuco.descripcion`.
6. `templates/chancucos/index.html` — formulario de 3 campos y tabla de 4 columnas.
7. `templates/finanzas/index.html` — bloque de lectura con `item.descripcion`, formulario embebido de 3 campos y tabla de 4 columnas.
8. `tests/test_trabajos_chancucos.py` y `tests/test_quincenas.py` — firmas y POST actualizados.

**Decisión sobre la migración:** un `RENAME COLUMN` no bastaba. `tipo_servicio` era `NOT NULL` sin valor por defecto, así que habría quedado como columna huérfana que rompe cada `INSERT`. Se optó por **reconstruir la tabla**: crear `chancucos_v13`, copiar fusionando `entidad · tipo_servicio` con `CASE` para no dejar separadores colgando, y reemplazar la original recreando su índice.

**Verificación:**
- `pytest -q` → **206 pruebas en verde**.
- Migración probada sobre una **copia** de `backend/datos/finanzas.db`, no sobre la base buena:
  - antes: `['id_chancuco', 'id_usuario', 'entidad', 'tipo_servicio', 'numero_referencia', 'url_pago', 'favorito', 'fecha_creacion']`
  - después: `['id_chancuco', 'id_usuario', 'descripcion', 'numero_referencia', 'url_pago', 'favorito', 'fecha_creacion']`
  - segunda ejecución: idéntica → idempotente.
  - `SELECT descripcion, numero_referencia` devolvió `[]`: la tabla estaba vacía, por lo que la fusión de textos no se ejercitó con datos reales.
- El servidor en segundo plano debe reiniciarse para aplicar la migración sobre `finanzas.db`.

**Pendiente:**
- Bloques 3, 4 y 5 de la SRS v1.3.
- Llevar la gestión de atajos por completo a la pestaña «Configurar Atajos de Pago» y dejar la columna izquierda estrictamente en lectura (hoy conviven ambas vistas).


---

### 2026-11-15 — SRS v1.3, bloque 3: planificador de ahorro y alerta de liquidez

**Objetivo:** convertir la pestaña «Gastos y Presupuesto» en un asistente que, partiendo del saldo libre real, permita proyectar metas y registrar sus abonos mes a mes, avisando cuando la liquidez cae por debajo de $300.000.

**Cambios realizados**
1. `diccionario_datos.md` §9.1 y §9.2 — documentan `proyecciones_ahorro` y `abonos_proyeccion` con sus `CHECK`, el `UNIQUE` por mes y la regla del total proyectado.
2. `modelos.py` — `ProyeccionAhorro` (categoría, descripción, cuota, `tipo_duracion` `FIJO`/`LIMITADO`, `meses`, `fecha_inicio`, `quincena`, `activo`) y `AbonoProyeccion` (meta, año, mes, valor, fecha de registro).
3. `servicios/ahorro.py` (nuevo) — `crear_proyeccion`, `listar_proyecciones`, `eliminar_proyeccion`, `registrar_abono`, `resumen_metas` y `diagnostico`; `MesMeta`/`MetaResumen` alimentan la plantilla y `UMBRAL_ALERTA = 300.000`.
4. `routers/presupuesto.py` (nuevo) — `GET /presupuesto`, `POST /presupuesto/metas`, `POST /presupuesto/metas/{id}/abono` y `POST /presupuesto/metas/{id}/eliminar`, con auditoría `META_CREADA`, `ABONO_META` y `META_ELIMINADA`.
5. `main.py` — registra el router `presupuesto`.
6. `templates/presupuesto/index.html` (nuevo) — banner de diagnóstico, alerta crítica con el texto «menos de $300.000 pesos mensuales; te aconsejo disminuir tus deudas…», formulario de meta (categoría, descripción, cuota, duración, meses, fecha y quincena), barra de progreso y cuadrícula de abonos por mes.
7. `static/js/presupuesto.js` (nuevo) — habilita `meses` solo con duración limitada y calcula el total proyectado en vivo; sin JavaScript el servidor valida.
8. `static/css/estilos.css` — estilos de `panel--diagnostico`, `alerta--critica`, `meta`, `barra-progreso`, `cuadricula-abonos` y `mes-abono`.
9. `templates/finanzas/_subnav.html` — la pestaña «Gastos y Presupuesto» apunta a `ver_presupuesto`; `templates/gastos/index.html` sigue siendo el registro secundario y se enlaza desde el planificador y desde el resumen.
10. `tests/conftest.py` — `ProyeccionAhorro` y `AbonoProyeccion` entran en `MODELOS_TRANSACCIONALES` para que cada prueba parta sin metas heredadas.
11. `tests/test_presupuesto.py` (nuevo) — 18 pruebas: creación de metas fijas y limitadas, validaciones, abono único por mes, meta ajena, avance tope 100 %, diagnóstico con y sin alerta, y el recorrido HTTP completo (sesión, error 400, alta, abono, corrección y borrado).

**Verificación**
- `python -m compileall` sin errores.
- `pytest -q` → **224 pruebas en verde** (206 previas + 18 netas).
- El saldo libre sembrado (sueldo $2.960.000, 50/50, deducciones en Q1) da `$2.723.200`; con un arriendo de $2.800.000 en Q1 baja a menos de $300.000 y el banner crítico aparece.

---

### 2026-11-15 — SRS v1.3, bloque 4: ajustes de Mi Perfil

**Objetivo:** que el formulario de perfil no pregunte por quincenas cuando el pago es mensual y que las preguntas usen el lenguaje real del usuario.

**Cambios realizados**
1. `templates/perfil/index.html` — etiqueta del caso B: «Escribe el valor neto que recibes en la quincena donde NO te realizan deducciones de ley ni pago de horas extras.»; pregunta del caso A: «¿En qué quincena te realizan todas las deducciones y pago de recargos?».
2. `templates/perfil/index.html` — nuevo aviso `data-aviso-mensual` que explica la modalidad mensual y ocupa el lugar del bloque de quincenas.
3. `static/js/perfil.js` — alterna el aviso junto con el `hidden`/`disabled` del `fieldset`; en modalidad mensual no se envían porcentajes.
4. `static/css/estilos.css` — `.aviso-modalidad` y regla de `[hidden]` para el aviso; los radios ya se apilaban con `.opciones` en columna.
5. `tests/test_perfiles.py` — 3 pruebas nuevas: textos del SRS v1.3, radios apilados y visibilidad del bloque según la modalidad.

**Verificación**
- `pytest -q` → **227 pruebas en verde** (224 + 3 netas).

---

### 2026-11-15 — SRS v1.3, bloque 5: Historial de Registros cronológico

**Objetivo:** que el historial responda de un vistazo «cuándo guardé, cuánto gané, cuánto me descontaron y con cuánto quedé».

**Cambios realizados**
1. `routers/finanzas.py` — `_filas_historial` añade `fecha_guardado` (formateada desde `fecha_creacion`) y `total_extras` (horas extra + recargos); se conserva la variación frente al periodo anterior para mostrarla como nota.
2. `templates/historial/index.html` — reescrito: título «Historial de Registros» y tabla cronológica con fecha de guardado, periodo, sueldo base, total extras, total deducciones, gastos quincenales, saldo neto final y acciones (imprimir/eliminar).
3. `static/css/estilos.css` — `tabla--historial`, `tabla__fecha` y `tabla__variacion`.
4. `tests/test_periodos.py` — prueba de la vista con el periodo guardado: cabeceras nuevas, fecha larga en español y marca «Primer registro».

**Verificación**
- `python -m compileall` sin errores.
- `pytest -q` → **228 pruebas en verde** (227 + 1 neta).

**Pendiente:**
- Fase opcional de PostgreSQL + Alembic.


---

### 2026-11-13 — Definición de stack y Tarea 1
**Objetivo:** iniciar el desarrollo con reglas definitivas de lenguaje y documentación.

**Cambios realizados**
1. Se adopta **Python puro (FastAPI + Jinja2 + HTMX)** como stack único (ADR-04).
2. Se establece la **política de documentación obligatoria** de funciones y reglas de negocio (ADR-05).
3. Se crea `diccionario_datos.md` con el modelo lógico completo: usuarios, perfil financiero, periodos de nómina, horas extra/recargos, incapacidades, saldos arrastrados, gastos, deudas, chancucos y entidades futuras de OLB_BYTE (clientes, productos, ventas, abonos).
4. **Tarea 1 completada:** andamiaje de la aplicación:
   - `backend/app/main.py` con fábrica de aplicación y montaje de estáticos.
   - `backend/app/core/config.py` con parámetros de negocio parametrizables y factores de recargo.
   - `backend/app/dependencias.py` con stub de sesión (rol simulado vía `?rol_demo=`).
   - `backend/app/routers/vistas.py` con rutas `/login`, `/` y `/finanzas`.
   - Plantillas `base.html`, `login.html`, `dashboard.html`, `finanzas/index.html` con RBAC visual.
   - `backend/app/static/css/estilos.css` con la paleta oficial y componentes (tarjetas, banners, badges).
   - `backend/requirements.txt` y utilidades de formato COP/fechas.
   - `backend/tests/test_vistas.py` con 4 pruebas de humo (RBAC visual, parámetros legales, `/salud`).

**Decisiones de implementación**
- El dashboard se alimenta de una lista de tarjetas definida en Python (`TARJETAS_DASHBOARD`) y se filtra por rol en el servidor; así el bloqueo no depende del cliente.
- El auxilio de transporte y las deducciones se mantienen como **parámetros**, nunca como literales.
- Los nombres de las rutas y variables son en español para consistencia con la documentación.

**Pendiente inmediato (Tarea 2):** implementar `backend/app/servicios/nomina.py` con funciones puras:
`calcular_valor_hora_ordinaria`, `calcular_deducciones_ley`, `calcular_recargos`, `calcular_total_devengado`, `calcular_auxilio_transporte` (depende de Tarea 3) y `liquidar_periodo`.

**Verificación ejecutada**
- `python -m compileall backend/app` → sin errores.
- `pytest` → **4 pruebas en verde**: el administrador ve OLB_BYTE y Chancucos; `USER_FINANZAS` no recibe ese HTML y sí ve el banner publicitario; `/finanzas` muestra 210 horas y el tope de $3.501.810; `/salud` responde `ok`.
- Entorno: Python 3.15 con `fastapi 0.162.5`, `jinja2`, `uvicorn` y `pytest` instalados en `backend/.venv`.

---

### 2026-11-13 — Tarea 2: motor de nómina puro

**Objetivo:** implementar el cálculo salarial como funciones puras y testeables, sin dependencias de HTTP ni de base de datos.

**Archivos creados**
1. `backend/app/servicios/__init__.py` — declara el paquete de servicios de dominio.
2. `backend/app/servicios/nomina.py` — motor completo:
   - `calcular_valor_hora_ordinaria`: divide el sueldo entre `parametros.horas_mensuales` (210) y redondea la hora a 4 decimales.
   - `calcular_deducciones_ley`: devuelve `DeduccionesLey(salud, pension, total)` al 4% + 4% sobre el sueldo básico.
   - `calcular_recargo` / `calcular_recargos`: aplican la matriz oficial (1.25 / 1.75 / 2.00 / 2.50 / 0.35 / 1.90) con soporte decimal y orden canónico del desglose.
   - `calcular_total_devengado`: `sueldo + recargos`, según la definición del SRS RF-07.
   - `liquidar_periodo`: orquesta todo y devuelve `LiquidacionNomina` inmutable con `como_diccionario()` para HTMX/JSON.
3. `backend/app/core/numeros.py` — conversión segura a `Decimal`, redondeo comercial y suma monetaria; única fuente de redondeo del proyecto.
4. `backend/tests/test_nomina.py` — **22 pruebas** (factores, decimales, parámetros alternos, errores de captura e invariante contable).

**Decisiones de implementación**
- `total_devengado` **excluye** el auxilio de transporte (definición del SRS), y se añadió `total_ingresos` para el dinero que entra al bolsillo. Esto deja lista la Tarea 3, que comparará `total_devengado` contra 2 SMMLV.
- El auxilio y el descuento por incapacidad entran a `liquidar_periodo` como **parámetros explícitos**: el motor no decide reglas de otras tareas.
- El desglose de recargos se construye recorriendo la matriz canónica, no el diccionario recibido, para que la UI muestre siempre el mismo orden.
- `texto.py` se refactorizó para consumir `core.numeros.a_decimal` y no duplicar la validación numérica.

**Verificación**
- `pytest` → **26 pruebas en verde** (22 del motor + 4 de vistas).
- Caso de control: sueldo 2.100.000 + 10 h extra diurna + auxilio 200.000 + incapacidad 50.000 → devengado 2.225.000; deducciones 218.000; **saldo de bolsillo 2.207.000**.
- Se verificó la invariante `saldo_bolsillo = total_ingresos − total_deducciones`, incluido el escenario de saldo negativo.

---

### 2026-11-13 — Tarea 3: validador del auxilio de transporte

**Objetivo:** aplicar la regla del SRS RF-07 (tope de 2 SMMLV) como función pura y dejarla disponible para la UI.

**Archivos**
1. `backend/app/servicios/auxilio.py`:
   - `evaluar_auxilio_transporte(total_devengado, parametros)` → `EvaluacionAuxilio`.
   - `evaluar_auxilio_salarial(sueldo_basico, total_recargos, parametros)` → aplica la suma del SRS.
   - Constante `MENSAJE_SIN_AUXILIO` con el texto literal exigido.
2. `backend/tests/test_auxilio.py` — 11 pruebas (tope exacto, excedente mínimo, parámetros alternos y errores).

**Decisiones**
- Se mantiene la condición estricta del SRS: igualar el tope **conserva** el auxilio; sólo superarlo lo anula.
- El resultado expone `diferencia_hasta_tope` y `excedente` para que la UI explique el cálculo.
- `liquidar_periodo` incorpora la regla con `aplicar_auxilio_legal=True`; si se envía además un auxilio explícito, lanza `ValueError` para evitar resultados ambiguos.
- Se conservó el comportamiento anterior por defecto (auxilio explícito en 0) para no alterar las pruebas de la Tarea 2.

**Verificación**
- Caso 1: devengado 2.100.000 → auxilio 200.000; faltan **1.401.810** para el tope.
- Caso 2: devengado 3.501.810 → aplica (igualdad) con diferencia 0.
- Caso 3: devengado 3.501.811 → auxilio 0, excedente 1 y mensaje literal del SRS.
- `pytest` → **37 pruebas en verde**.

---

### 2026-11-13 — Tarea 4: incapacidades y rollover

**Objetivo:** calcular el descuento de una incapacidad de origen común y repartir sus días por mes para arrastrar el saldo al periodo siguiente.

**Archivos**
1. `backend/app/servicios/incapacidad.py`:
   - `calcular_incapacidad(...)` → `LiquidacionIncapacidad` con totales y `tramos` por mes.
   - `liquidar_mes_incapacidad(...)` → `ResultadoMesIncapacidad` con el descuento del mes activo y `saldos_pendientes`.
   - Dataclasses `TramoMensual`, `SaldoIncapacidad` listas para mapear a las tablas `incapacidades` y `saldos_incapacidad`.
2. `backend/tests/test_incapacidad.py` — **17 pruebas** (regla 100%/66.67%, parámetros alternos, cruce de mes, cruce de año, tres meses, errores e integración con la liquidación).

**Decisiones**
- **Valor día = sueldo básico / 30**, alineado con la práctica colombiana y con el diccionario de datos.
- El descuento se calcula sobre el **33.33%** (complemento del 66.67% de la EPS), no sobre 66.67%.
- El reparto se hace **día por día** y luego se agrupa por mes: así la continuidad del día 3 se conserva aunque la incapacidad cruce de mes o de año.
- `SaldoIncapacidad` incluye `dias_liquidados_previos` para auditar desde qué día de la incapacidad se reanuda el siguiente periodo.
- Una incapacidad que abarca tres meses genera **dos saldos** independientes (`saldos_pendientes`), evitando perder dinero en el camino.
- La persistencia de `saldos_incapacidad` queda para la fase de base de datos; el servicio no escribe nada.

**Verificación**
- Incapacidad de 5 días con sueldo 3.000.000: 2 días sin descuento, 3 al 66.67% → **$99.990**.
- Cruce marzo/abril (28-mar a 01-abr): marzo descuenta **$66.660** y arrastra 1 día por **$33.330**.
- Cruce de año (30-dic a 02-ene): se conserva la continuidad y el descuento total es **$66.660**.
- `pytest` → **54 pruebas en verde**.

---

### 2026-11-13 — Tarea 4b: formulario de incapacidades

**Objetivo:** exponer el motor de incapacidades en la interfaz, con validación amable y sin depender de JavaScript.

**Archivos**
1. `backend/app/routers/incapacidades.py` — rutas `GET /incapacidades` y `POST /incapacidades/calcular`; parsea el formulario, acumula errores y renderiza el resultado.
2. `backend/app/templates/incapacidades/index.html` — formulario (fechas, sueldo y mes a liquidar), resumen de reglas, tarjetas de resultado, tabla de tramos y tabla de saldos arrastrados.
3. `backend/app/core/texto.py` — `parsear_monto` (formato colombiano), `parsear_periodo_mes` y `formatear_mes_anio`.
4. `backend/tests/test_texto.py` y `backend/tests/test_incapacidades_vistas.py` — 11 + 9 pruebas.

**Decisiones**
- **Sin JavaScript para el cálculo:** el formulario hace POST y el servidor devuelve la página con el resultado. La aritmética sigue en un solo lugar (Python).
- **Repoblado tras error:** los valores escritos se conservan y los errores se agrupan en un bloque de alerta.
- **Mes a liquidar opcional:** si se deja vacío se liquida el mes de la fecha de inicio (comportamiento natural del usuario).
- **Parser de montos tolerante:** acepta `3.000.000`, `$ 3.000.000,50` y `1500.50`, y rechaza texto para no calcular con ceros silenciosos.
- Se añadió el enlace **Incapacidades** en la navegación y un acceso directo desde `Mis Finanzas`.

**Verificación**
- Rango 2–4 de marzo con sueldo 3.000.000 → descuento **$33.330** y sin saldos.
- Rango 30-mar a 02-abr → marzo sin descuento y saldo de **$66.660** para abril.
- Errores probados: rango invertido, sueldo cero, sueldo con letras y periodo mal formado.
- `pytest` → **74 pruebas en verde**.

---

### 2026-11-13 — Tareas 5 y 6: RBAC real y calculadora reactiva

**Objetivo:** cerrar el flujo funcional completo (nómina en vivo) y proteger las rutas privadas con sesión real, sin dependencias externas.

**Archivos**
1. `backend/app/core/seguridad.py` — hash PBKDF2-HMAC-SHA256 y JWT HS256 con `hmac`/`base64url`.
2. `backend/app/servicios/usuarios.py` — repositorio en memoria con cuentas semilla, autenticación y registro público.
3. `backend/app/dependencias.py` — `SesionRequerida`, `UsuarioSesion`, `usuario_opcional`, `obtener_usuario_actual` y `exigir_administrador`.
4. `backend/app/routers/auth.py` — `GET/POST /login`, `POST /salir`, `GET/POST /registro`.
5. `backend/app/routers/finanzas.py` — `GET/POST /finanzas` y `POST /finanzas/calcular` (JSON).
6. `backend/app/templates/login.html`, `registro.html`, `privado/index.html`, `finanzas/index.html` reescrito.
7. `backend/app/static/js/finanzas.js` — debounce 150 ms, `fetch` con `Accept: application/json`, actualización del DOM.
8. `backend/tests/conftest.py` — fixtures `cliente`, `cliente_admin`, `cliente_usuario`.
9. Nuevas pruebas: `test_seguridad.py` (11), `test_auth.py` (11), `test_finanzas_vistas.py` (12); `test_vistas.py` y `test_incapacidades_vistas.py` migradas al login real.

**Decisiones**
- **RBAC en el servidor:** `USER_FINANZAS` no recibe el HTML de OLB_BYTE, Deudas, Trabajos Extras ni Chancucos; si escribe la URL recibe **403**.
- **Cookie `HttpOnly` + `SameSite=Lax`:** JavaScript no puede leer el token; el cierre de sesión es un `POST /salir` (no un enlace GET).
- **Auto-registro siempre `USER_FINANZAS`:** el rol se asigna en el servidor, nunca desde el formulario.
- **Mensaje de login genérico:** no revela si el correo existe.
- **Calculadora con doble camino:** POST clásico renderizado en servidor (sin JS) y endpoint JSON para la actualización en vivo; el cálculo siempre vive en `servicios/nomina.py`.
- **Fixtures con token directo:** las pruebas de vistas no repagan PBKDF2 en cada caso; el flujo real de login se cubre en `test_auth.py`.

**Verificación**
- Login admin/usuario → 303 al tablero con cookie `HttpOnly`; credenciales erróneas → 401 sin cookie.
- `USER_FINANZAS` en `/olb-byte`, `/deudas`, `/trabajos-extras`, `/chancucos` → **403**; admin → 200.
- Sueldo 3.000.000 sin horas → saldo **$2.960.000** y auxilio completo.
- Sueldo 3.000.000 + 10 h nocturnas → recargo **$250.000** y saldo **$3.210.000**.
- Sueldo 3.600.000 → auxilio **$0** con el mensaje literal del SRS.
- `/finanzas/calcular` sin sesión → **401** JSON; con sesión → totales, desglose y mensaje del auxilio.
- `python -m compileall` OK y `pytest` → **111 pruebas en verde**.

---

### 2026-11-13 — Bloques A, B, C y D: plataforma completa

**Objetivo:** cerrar el backlog funcional completo (persistencia, módulos privados, PWA y endurecimiento) sin introducir tecnologías fuera del stack Python.

**Persistencia (ADR-09)**
1. `core/base_datos.py` — motor SQLite, `sesionmaker`, `PRAGMA foreign_keys=ON`, `obtener_bd`, `crear_esquema` e `inicializar_base_datos`.
2. `modelos.py` — todas las tablas del diccionario (§2–§13), incluidas `trabajos_extras` y `auditoria`.
3. `servicios/ usuarios.py` reescrito sobre SQLAlchemy: alta, autenticación, alias, contraseña, rol, estado, listado y siembra idempotente.
4. Servicios nuevos: `perfiles`, `periodos`, `registro_incapacidades`, `gastos`, `chancucos`, `deudas`, `trabajos`, `comercial`, `auditoria`.
5. `tests/conftest.py` — base temporal por proceso, limpieza transaccional por prueba y fixtures `cliente`, `cliente_admin`, `cliente_usuario` y `bd`.

**Módulos y vistas**
- `perfil` (onboarding y cambio de contraseña), `admin` (roles y estado), `gastos`, `historial` con CSV e impresión, `chancucos`, `deudas`, `trabajos` y `olb_byte` (inventario, ventas multipartida, abonos, cartera, factura y WhatsApp).
- El dashboard mantiene el filtrado por rol en Python; `/olb-byte` y los demás módulos privados siguen devolviendo **403** a `USER_FINANZAS`.

**PWA y experiencia (bloque C)**
- `manifest.webmanifest`, `sw.js` (cachea **solo** estáticos, nunca HTML autenticado), íconos SVG y favicon.
- `app.js` para portapapeles y filas dinámicas; `perfil.js` para la modalidad quincenal; `finanzas.js` con plantillas de horas y aviso `beforeunload`.
- CSS de impresión (`@media print`), tablas editables, botones pequeños/peligro y alertas de aviso.

**Endurecimiento (bloque D, ADR-10 y ADR-11)**
- `core/middleware.py`: rechazo de escrituras con `Origin` ajeno o `Sec-Fetch-Site: cross-site` y cabeceras CSP/nosniff/frame/referrer/permissions. El **403 también** las incluye (método `_con_cabeceras`), para que ninguna respuesta quede sin endurecer.
- `core/limitador.py`: ventana deslizante por IP + correo, método `reiniciar()` y máximo desde configuración.
- `auth.py`: 429 tras el máximo, limpieza en acceso correcto y auditoría de intentos.
- `config.py`: `entorno` y `clave_secreta` se leen al **instanciar** (no al importar), lo que permite probar producción con `monkeypatch`; `validar_para_produccion()` impide arrancar con clave débil y `documentacion_habilitada` apaga `/docs`.
- `scripts/respaldo.py`: API `backup`, verificación `integrity_check` (devuelve `False` ante archivos no SQLite), rotación por nombre y cierre explícito de conexiones (necesario en Windows). La marca temporal usa microsegundos para no sobrescribir copias del mismo segundo.
- `.github/workflows/ci.yml` y `DESPLIEGUE.md` (systemd, NSSM, Nginx/HTTPS, respaldos, rollback y ruta a PostgreSQL).

**Correcciones relevantes**
- FastAPI 0.162 rechaza anotaciones de retorno `HTMLResponse | RedirectResponse`: se añadió `response_model=None` a los decoradores POST que devuelven una unión.
- Los servicios que reciben montos de formulario usan `parsear_monto` (acepta `3.000.000` y `2.960.000,50`); `a_decimal` se reserva para valores ya normalizados.
- Se corrigió un `IndentationError` en `usuarios.cambiar_rol` y un `order_by` duplicado en `gastos.listar_gastos`.

**Verificación**
- `python -m compileall` sin errores.
- `pytest` → **185 pruebas en verde**: 22 nómina, 11 auxilio, 17 incapacidades, 11 texto, 11 seguridad, 11 auth/RBAC, 12 finanzas, 10 incapacidades vistas, 6 vistas generales, 7 perfiles, 6 periodos, 8 gastos/deudas, 8 trabajos/chancucos, 14 comercial, 19 seguridad HTTP y 12 de respaldo.
- `scripts/respaldo.py` cubierto con `tmp_path`: copia consistente de una base con datos, respaldo real de la base de la aplicación, origen inexistente, nombres únicos con microsegundos, detección de archivo inválido, rotación por nombre y códigos de salida 0/1/2 de la CLI.
- Flujo manual comprobado: perfil quincenal (sueldo del periodo 1.480.000), incapacidad 28-nov a 03-dic con rollover visible en diciembre, guardado de periodo e historial, gastos, deudas con abono, trabajos, chancucos, producto/cliente/venta/factura de OLB_BYTE y respaldo verificado con `PRAGMA integrity_check`.

**Pendiente**
- PostgreSQL + Alembic y limitador compartido (Redis) para despliegue multi-instancia; no bloquean el uso actual.





