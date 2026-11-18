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
  - (Actualizado en SRS v1.6, ADR-28) Ambos tipos exigen un periodo en meses (1–600). El formulario acepta años y los convierte a meses.
  - Solo existe **un abono por meta y mes** (`UNIQUE(id_proyeccion, anio, mes)`): volver a registrarlo corrige el monto, nunca duplica.
  - El umbral de alerta de liquidez vive en `ahorro.UMBRAL_ALERTA = Decimal("300000")`, no repartido por la plantilla.
- **Consecuencia:** el diagnóstico («te sobran $X del sueldo») y la alerta crítica son datos del servidor, no texto fijo; el planificador puede crecer (categorías, reportes) sin tocar el formulario de gastos. El coste es una pantalla más y dos tablas nuevas.

---

### ADR-18 — Deducciones fijas del salario y recálculo por quincena (SRS v1.4)
- **Contexto:** la liquidación no reflejaba descuentos recurrentes de nómina (libranzas, fondos), ni el efecto de horas extras e incapacidades sobre cada quincena. Además, el formulario de gastos fijos estaba duplicado entre pestañas.
- **Decisión:**
  - Nueva tabla `deducciones_fijas` (§9.3 del diccionario) con servicio `servicios/deducciones_fijas.py`. Se gestiona en «Gastos y Presupuesto» y se lista en la liquidación con la misma jerarquía que las deducciones de ley.
  - El saldo libre de cada quincena resta solo las deducciones de su propia quincena (`quincenas.resumen_quincenas`).
  - REQ-05: el descuento por incapacidad se resta del sueldo base antes de repartirlo por porcentaje.
  - REQ-04: los recargos se suman al ingreso de la quincena indicada en `perfil.quincena_deducciones`.
  - El endpoint `POST /finanzas/calcular` devuelve `quincenas` y el JavaScript repinta saldo, ingreso y deducciones sin recargar.
  - El formulario de gastos fijos de «Gastos y Presupuesto» se retira; el alta vive en cada tarjeta de quincena.
  - La administración de atajos sale de la vista de liquidación (REQ-07); queda en la pestaña «Configurar Atajos de Pago».
- **Decisión pendiente de validación:** REQ-04 pide recalcular salud y pensión sobre «sueldo + horas extras». El AGENTS.md (regla innegociable) dice **sueldo básico**. Se mantiene la regla vigente del AGENTS.md y el texto de ayuda se corrigió para reflejarla. Cambiar la base legal requiere aprobación explícita.
- **Consecuencia:** el saldo de cada quincena ya responde a horas extras, incapacidades y descuentos fijos. El resultado total del periodo sigue calculándose en `nomina.py` sin cambios.

---

### ADR-19 — Salud y pensión sobre el salario devengado (SRS v1.4)
- **Contexto:** la regla del AGENTS.md §6 calculaba el 4 % + 4 % sobre el sueldo básico fijo. Con horas extras o incapacidad, el salario que realmente se devenga cambia y el descuento no reflejaba ese cambio.
- **Decisión (aprobada por el usuario):** la base de cotización es el salario devengado del periodo: `sueldo básico + horas extras y recargos − descuento por incapacidad` (tope inferior en cero).
  - `servicios/nomina.py` — `liquidar_periodo` calcula el total devengado antes y aplica la base nueva.
  - `routers/finanzas.py` — `_deducciones_segun_quincena` usa la misma base mensual.
  - `servicios/quincenas.py` — el panel de quincenas usa la misma base.
- **Consecuencia:** al escribir horas extras o fechas de incapacidad, salud y pensión se actualizan en vivo junto con el sueldo proyectado y las quincenas. Una incapacidad que deja la base en cero elimina salud y pensión de ese periodo.
- **Supersede:** la regla «sobre el sueldo básico» de AGENTS.md §6.

### ADR-20 — Caja única de deducciones e incapacidad por tramo mensual (SRS v1.5)
- **Contexto:** la incapacidad vivía en un recuadro aparte y el descuento de un rango que cruzaba de mes se arrastraba al siguiente (`saldos_incapacidad`). Eso obligaba a mantener un saldo persistido y a explicar dos cifras de descuento.
- **Decisión:**
  - **Caja única:** salud + pensión + descuento de incapacidad + deducciones fijas se presentan y se suman juntas bajo «Deducciones de ley» (subtítulo «Deducciones fijas del salario» lista los conceptos). El total final resta esa caja completa. `_total_deducciones_ley` es la única fuente.
  - **Tramo mensual:** los días son calendario (`fin − inicio + 1`), sin campo manual. La regla 100 % (días 1–2) / 66,67 % (día 3+) se aplica **una sola vez** sobre la incapacidad completa. `registro_incapacidades.tramos_del_mes` recorta lo que cae en cada mes y `descuento_del_mes` suma ese tramo; Mis Finanzas descuenta solo el tramo del mes consultado.
  - Se elimina el rollover de `servicios/periodos.py`; `saldos_incapacidad` queda como tabla heredada sin uso activo.
- **Consecuencias:** registrar una incapacidad de 20 días que cruza de mes descuenta en mayo solo sus días de mayo y en junio los suyos; no hay saldo arrastrado que corregir. La migración `_migrar_saldos_incapacidad` conserva las columnas por compatibilidad.
- **Archivos:** `servicios/registro_incapacidades.py`, `servicios/incapacidad.py`, `servicios/periodos.py`, `routers/finanzas.py`, `routers/incapacidades.py`, `templates/finanzas/index.html`, `static/js/incapacidades.js`.

### ADR-21 — Deudas con tasa implícita y amortización automática (SRS v1.5)
- **Contexto:** el modelo anterior pedía tasa de interés y fecha límite, y el usuario abonaba a mano. En la práctica nadie conoce la tasa del crédito; sí conoce el saldo, la cuota y cuántos pagos faltan.
- **Decisión:**
  - Se capturan **seis campos**: acreedor, descripción, saldo total, cuota, cuotas pendientes y periodicidad (`QUINCENAL`/`MENSUAL`). Desaparecen tasa, fecha límite y abono manual (la ruta `/deudas/{id}/abonar` responde 404).
  - La tasa se **deriva** por bisección de `saldo = cuota × (1 − (1+r)^−n) / r`, con `PRECISION_TASA = 0.0000000001` y se guarda en `deudas.tasa_interes NUMERIC(12,10)`. Si `cuota × n = saldo`, la tasa es 0; si `cuota × n < saldo`, se rechaza el plan.
  - Al abrir el módulo, `aplicar_cuotas_vencidas` aplica las cuotas cuyo vencimiento pasó, con ancla en el último pago o en `fecha_creacion`. Cada pago se guarda en `pagos_deuda` con `UNIQUE(id_deuda, numero_cuota)`, lo que hace la operación idempotente.
  - La última cuota se recalcula como `saldo + interés` y deja el saldo exacto en `0`.
- **Consecuencias:** el ejemplo del SRS (3.500.000 en 48 cuotas de 100.000) produce tasa 0,0137085766, total pagado 4.800.000,02, intereses 1.300.000,02 y última cuota 100.000,02. Con 6 decimales de precisión la última cuota se desviaba 61 pesos, de ahí los 10 decimales.
- **Archivos:** `servicios/deudas.py`, `routers/deudas.py`, `modelos.py` (`Deuda`, `PagoDeuda`), `core/base_datos.py` (`_migrar_columnas_deudas`), `templates/deudas/index.html`, `diccionario_datos.md` §8 y §8.1.

### ADR-22 — Metas con «Ambas quincenas» (SRS v1.5)
- **Contexto:** una meta de ahorro debía imputarse a un pago concreto, aunque el usuario aparta el dinero de los dos.
- **Decisión:** `ProyeccionAhorro.quincena` admite `3` (`QUINCENA_AMBAS`). El valor guardado sigue siendo **mensual**; `valor_por_pago` lo divide entre dos y la interfaz muestra «Ambas quincenas (X por pago)». SQLite no altera el `CHECK` existente, así que `_migrar_proyeccion_quincena` reconstruye `proyecciones_ahorro` y `abonos_proyeccion` (hija primero) conservando filas e índices.
- **Consecuencias:** la meta no se descuenta de una quincena específica del panel; el planificador la compara contra el saldo libre total. Se mantiene como herramienta de planificación, no como gasto devengado. Queda pendiente decidir si debe restarse del saldo libre (ver §Pendientes).
- **Archivos:** `modelos.py`, `servicios/ahorro.py`, `routers/presupuesto.py`, `templates/presupuesto/index.html`, `core/base_datos.py`, `diccionario_datos.md` §9.1.

### ADR-23 — Montos sin centavos en todo el programa (SRS v1.6)
- **Contexto:** los montos mostraban centavos (`$10.369.047,63`) que el usuario no necesita para decidir.
- **Decisión:** `core/texto.formatear_cop` redondea al peso (`ROUND_HALF_UP`) y no imprime decimales. Los cálculos internos conservan centavos; porcentajes y horas no cambian.
- **Consecuencias:** solo cambia la presentación (HTML, JSON y CSV). Las deudas siguen cerrando en cero internamente.
- **Archivos:** `core/texto.py`, pruebas de vistas de finanzas.

### ADR-24 — Metas como gastos fijos con check de pago (SRS v1.6)
- **Contexto:** una meta era un número aparte y el usuario la sentía como un compromiso sin efecto real en el saldo.
- **Decisión:** cada meta genera sus gastos fijos (`gastos.id_proyeccion`), uno por quincena de descuento. El ✔ registra el pago (`pagado`, permanente) y el abono del mes es la suma de los pagos marcados (`pagos_metas.sincronizar_abono`). Se retira el formulario manual de abonos. Las metas restan del saldo solo a través de sus gastos; el banner de «Gastos y Presupuesto» muestra las metas del mes como informativo. Esto resuelve el pendiente de ADR-22.
- **Reglas:** «Limpiar checks» solo oculta el ✔ (`check_visible`); el pago y el abono se conservan. Editar un gasto pagado actualiza el abono; editar un gasto no cambia la cuota de la meta (cada quincena es independiente). Eliminar la meta desde «Gastos y Presupuesto» borra sus gastos y abonos por cascada.
- **Migración:** `_migrar_columnas_gastos` agrega las columnas nuevas. Los abonos heredados se convierten en pagos al generar el mes; su monto pasa a ser la cuota planeada.
- **Archivos:** `modelos.py`, `servicios/pagos_metas.py` (nuevo), `servicios/ahorro.py`, `servicios/gastos.py`, `servicios/quincenas.py`, `routers/gastos.py`, `routers/presupuesto.py`, `routers/finanzas.py`, `templates/finanzas/index.html`, `templates/presupuesto/index.html`, `static/css/estilos.css`, `core/base_datos.py`, `diccionario_datos.md` §7 y §9.2.

### ADR-25 — Saltar un pago de meta con × y reactivación (SRS v1.6)
- **Contexto:** eliminar el gasto de una meta en una quincena no debe borrar la meta, y el dinero no pagado debe volver al saldo real de esa quincena.
- **Decisión:** la × en un gasto de meta lo **inhabilita** (`inhabilitado_hasta = hoy + 15 días`) y retira su pago y abono. Mientras el plazo esté vigente no suma en el saldo de su quincena y no admite ✔; el mes se muestra en color «No pagado». Vencido el plazo, el pago vuelve a ser un gasto normal (vuelve a sumar y admite ✔). Un gasto manual sigue eliminándose.
- **Abono manual (ADR-25.a):** mientras el plazo esté vigente, el pago admite un abono manual con un monto. Lo deja pagado con ese `monto_pagado`, quita la inhabilitación y ese monto cuenta en el saldo y en el abono del mes. No reabre un formulario general de abonos.
- **Archivos:** `servicios/pagos_metas.py` (`inhabilitar_gasto`, `quitar_gasto`, `registrar_abono_manual`), `servicios/gastos.py` (`valor_computable`), `routers/gastos.py`, `templates/finanzas/index.html`.

### ADR-28 — Periodo escogido por el usuario para toda meta (SRS v1.6)
- **Contexto:** las metas indefinidas generaban solo 12 meses y las limitadas topaban en 120; el usuario quiere elegir la cantidad de años o meses en ambos casos.
- **Decisión:** toda meta exige `meses` (1–600, 50 años). El formulario tiene campo «Periodo» con unidad Meses o Años; el servidor convierte años × 12. Las metas `FIJO` ahora calculan total = cuota × meses. Las metas anteriores sin periodo conservan la ventana de 12 meses.
- **Archivos:** `servicios/ahorro.py` (`MESES_MAXIMOS = 600`, `_validar_duracion`, `meses_de_la_meta`, `resumen_metas`), `servicios/pagos_metas.py` (`_meses_a_generar`), `routers/presupuesto.py` (`_meses_del_formulario`), `templates/presupuesto/index.html`, `static/js/presupuesto.js`, `static/js/sw.js` (`olb-finanzas-v9`).

### ADR-29 — Ciclo de vida de la meta: cumplida, extender y archivar (SRS v1.6)
- **Contexto:** una meta debe terminar sola al cumplir su periodo, poder extenderse y, al eliminarla, conservar su historial en lugar de perderlo.
- **Decisión:** `cumplida` se calcula por fecha (el mes actual supera el último mes del periodo). `extender_proyeccion` suma meses desde el último mes planificado, o desde el mes actual si ya se cumplió. `eliminar_proyeccion` ya no borra: archiva (`activo = false`, `archivada_en`, `estado_final`), quita los gastos futuros no pagados y conserva los pagados. `historial_metas` lista las archivadas con inicio, fin, total recogido y el detalle mes por mes (`_detalle_pagos`: pagado con monto y fecha, o no pagado hasta el mes de archivado) en un desplegable por meta. Las etiquetas del selector son «Meta a largo plazo» y «Meta a corto plazo»; ambas usan el mismo periodo.
- **Archivos:** `modelos.py` (`archivada_en`, `estado_final`), `core/base_datos.py` (`_migrar_columnas_metas`), `servicios/ahorro.py`, `routers/presupuesto.py` (ruta `extender_proyeccion`), `templates/presupuesto/index.html`, `static/css/estilos.css`, `diccionario_datos.md` §9.1.

### ADR-30 — Rejillas que no desbordan y alturas homologadas (SRS v1.7, bloque A)
- **Contexto:** en móvil, `input[type="date"]` empujaba su columna y desbordaba la tarjeta; los campos de «Gastos y Presupuesto» tenían alturas distintas.
- **Decisión:** las rejillas usan `minmax(min(Npx, 100%), 1fr)`; todo hijo de `.campo`, `.fila-campos` y `.formulario` lleva `min-width: 0`; los controles de fecha fijan `width/max-width: 100%`, `box-sizing: border-box` y `appearance: none`; etiquetas con `min-height` común y controles con `min-height: 50px` (texto a 16 px en móvil para evitar el zoom de iOS). No cambia ninguna regla de negocio.
- **Archivos:** `static/css/estilos.css`, `static/js/sw.js` (`olb-finanzas-v10`).

### ADR-31 — «Ambas quincenas»: dividir o duplicar la cuota (SRS v1.7, bloque B)
- **Contexto:** con una meta en las dos quincenas, el usuario no podía decidir si la cuota se repartía o se cobraba completa en cada pago.
- **Decisión:** nueva columna `proyecciones_ahorro.modo_ambas` (`DIVIDIR` | `DUPLICAR`, por defecto `DIVIDIR`). `DIVIDIR` reparte $100.000 en $50.000 + $50.000; `DUPLICAR` cobra $100.000 + $100.000 ($200.000 al mes). El modo solo aplica a `quincena = 3`; en 1 o 2 se normaliza a `DIVIDIR`. `valor_mensual_efectivo` alimenta el total proyectado y la generación de gastos usa `valor_por_pago`.
- **Archivos:** `modelos.py`, `core/base_datos.py` (`_migrar_columnas_metas`, rebuild de `_migrar_proyeccion_quincena`), `servicios/ahorro.py`, `servicios/pagos_metas.py`, `routers/presupuesto.py`, `templates/presupuesto/index.html`, `static/js/presupuesto.js`, `diccionario_datos.md` §9.1, `tests/test_metas_modo.py`.

### ADR-32 — Desmarcar revierte el pago; la limpieza masiva lo conserva (SRS v1.7, bloque C)
- **Contexto:** el usuario puede marcar un ✔ por error y necesita corregirlo; además, al iniciar un periodo nuevo quiere ocultar los checks sin perder el histórico de pagos.
- **Decisión:** dos acciones distintas. `pagos_metas.desmarcar_pagado` (`POST /gastos/{id}/no-pagado`) revierte `pagado`, `pagado_en` y `monto_pagado`, vuelve a contar el gasto en su quincena y recalcula el abono de la meta. `limpiar_checks` solo pone `check_visible = False` y conserva el pago y el abono. El panel pinta el ✔ únicamente cuando `pagado and check_visible`, de modo que la limpieza no deja marcas residuales. La fila del gasto pasa a una macro compartida (`templates/finanzas/_gasto_fijo.html`) con lápiz de edición, «Cancelar» y × circular; «Limpiar checks» usa `boton--advertencia` y pide confirmación con `data-confirmar`.
- **Archivos:** `servicios/pagos_metas.py`, `routers/gastos.py`, `templates/finanzas/_gasto_fijo.html`, `templates/finanzas/index.html`, `templates/presupuesto/index.html`, `static/css/estilos.css`, `static/js/app.js`, `tests/test_gastos_checks.py`.

### ADR-33 — Atajos de pago con uno o dos días mensuales (SRS v1.7, bloque D)
- **Contexto:** un servicio puede pagarse una o dos veces al mes, y el usuario necesita ver el día en la tarjeta del atajo.
- **Decisión:** `chancucos` gana `dia_pago_1` y `dia_pago_2` (`SMALLINT NULL`). Se guarda **solo el número del día** (1–31), sin año ni mes, porque el atajo se repite cada mes; la interfaz muestra «Día 15» o «Día 15 · Día 30». El formulario pregunta «¿Es un único pago mensual?»; con «Sí» el segundo día se ignora aunque llegue en la petición. Un segundo día igual al primero se descarta. Los atajos existentes quedan en `NULL`, se muestran como «Sin día definido» y no se alteran. No se toca Gastos Fijos: los atajos son referencias, no movimientos de dinero.
- **Archivos:** `modelos.py`, `core/base_datos.py` (`_migrar_columnas_chancucos`), `servicios/chancucos.py`, `routers/chancucos.py`, `templates/chancucos/_dias.html`, `templates/chancucos/index.html`, `templates/finanzas/index.html`, `static/css/estilos.css`, `static/js/app.js`, `diccionario_datos.md` §9, `tests/test_chancucos_dias.py`.

### ADR-34 — Trabajos Extras como contratos recurrentes con pagos propios (SRS v1.7, bloque E)
- **Contexto:** un trabajo extra podía ser un ingreso suelto o un contrato que se cobra todos los meses; el usuario necesita registrar la frecuencia, el tipo de contrato y marcar cada cobro sin que esos ingresos alteren el sueldo ni las quincenas.
- **Decisión:** `trabajos_extras` gana `tipo_contrato` (`INDEFINIDO` | `TERMINO_FIJO`), `frecuencia` (`MENSUAL` | `QUINCENAL`), `fecha_fin` y `fecha_pago`. `valor` es el monto **de cada pago**. Los pagos se generan de forma idempotente como filas de `gastos` con `id_trabajo`: reutilizan la macro `fila_gasto` (lápiz, «Cancelar», ×, ✔ y abono manual) pero `gastos.listar_gastos` los excluye, así que no tocan el sueldo, las quincenas ni los totales de gastos. El ✔ registra el cobro y `trabajos.extras_cobrados_mes` lo suma al `disponible` del diagnóstico del mes. La frecuencia quincenal crea dos pagos (día 15 y día 30 ajustado al último día); la mensual, uno en el día de `fecha_pago`. Un contrato indefinido mantiene una ventana móvil de 12 meses desde el mes visible; un término fijo se detiene en `fecha_fin`. La × inhabilita el pago 15 días en lugar de borrarlo, para que la generación idempotente no lo recree. Los trabajos anteriores se migran como término fijo de un solo mes para no inventar ingresos recurrentes.
- **Archivos:** `modelos.py` (`TrabajoExtra`, `Gasto.id_trabajo`), `core/base_datos.py` (`_migrar_columnas_trabajos`, `id_trabajo` en `_migrar_columnas_gastos`), `servicios/trabajos.py`, `servicios/gastos.py`, `servicios/pagos_metas.py` (`quitar_gasto`), `servicios/ahorro.py` (`diagnostico`), `routers/trabajos.py`, `routers/gastos.py` (`_volver`), `templates/trabajos/index.html`, `templates/finanzas/_gasto_fijo.html`, `templates/presupuesto/index.html`, `static/js/app.js`, `diccionario_datos.md` §7 y §12, `tests/test_trabajos_extras.py`.

### ADR-27 — Monto pagado, propagación de valor y ventana de generación (SRS v1.6)
- **Contexto:** el abono de un mes debe reflejar lo realmente pagado, no la cuota; editar una quincena debe valer desde ese mes en adelante; una meta limitada debe generar toda su duración.
- **Decisión:** nueva columna `gastos.monto_pagado`. El saldo y el abono cuentan `monto_pagado` cuando `pagado = true`. `propagar_valor` copia el valor editado a los meses posteriores de la misma meta y quincena que no estén pagados. Los meses nuevos toman el último valor de esa quincena. Las metas generan todo el periodo escogido por el usuario (ADR-28).
- **Abonos heredados:** el abono de un mes anterior se convierte en pago con `monto_pagado` igual a ese abono (dividido entre las quincenas si es «Ambas»). El valor del gasto queda como la cuota planeada.
- **Archivos:** `modelos.py`, `core/base_datos.py` (`monto_pagado`), `servicios/pagos_metas.py`, `servicios/gastos.py`, `servicios/ahorro.py`, `routers/gastos.py`.

### ADR-26 — Incapacidades: Enter y «Limpiar» (SRS v1.6)
- **Contexto:** Enter guardaba la incapacidad sin querer, y «Limpiar» (`type="reset"`) no recalculaba: el servidor volvía a cargar la incapacidad registrada.
- **Decisión:** Enter solo recalcula (`finanzas.js`, `incapacidades.js`). «Limpiar» es un botón real que vacía fechas y envía `incapacidad_omitir=1`; el servidor entonces no aplica las registradas al cálculo (`_leer_entradas`). El registro **no se borra**; se muestra un aviso con enlace a `/incapacidades` que desaparece al escribir nuevas fechas.
- **Archivos:** `static/js/finanzas.js`, `static/js/incapacidades.js`, `templates/finanzas/index.html`, `routers/finanzas.py`.

---

## Parámetros de Dominio Salarial (Colombia)

| Parámetro | Valor parametrizado | Regla |
| --- | --- | --- |
| Jornada mensual | 210 horas | Sobre 42 h semanales legales. |
| Salud empleado | 4% | Automático, sólo lectura, sobre el salario **devengado** (ADR-19). |
| Pensión empleado | 4% | Automático, sólo lectura, sobre el salario **devengado** (ADR-19). |
| Tope auxilio de transporte | 2 SMMLV (**$3.501.810 COP**) | Si `Sueldo + Recargos` > tope → auxilio = $0. |
| Auxilio de transporte (valor) | Parametrizable | Se asigna sólo si no supera el tope. |
| Incapacidad días 1–2 | 100% del salario | A cargo del empleador, sin descuento. |
| Incapacidad días 3+ | 66.67% del salario | Descuento del 33.33% a cargo de EPS. |

> Todos los valores viven en `backend/app/core/config.py` (`ParametrosNomina`) para evitar números mágicos.

---

## Módulo Especial: Cruce de Meses e Incapacidades (tramo mensual, SRS v1.5)

- Una incapacidad se registra con **inicio y fin**; los días son calendario
  (`fin − inicio + 1`) y no se capturan a mano.
- La regla legal (días 1–2 al 100 %, desde el día 3 con descuento del 33,33 %) se
  aplica **una sola vez** sobre la incapacidad completa.
- Si el rango cruza de mes, `registro_incapacidades.tramos_del_mes` entrega solo los
  días de ese mes y Mis Finanzas descuenta ese tramo. **No hay rollover**: se
  eliminó el saldo arrastrado de `periodos.py` (ADR-20).
- Entidades: `incapacidades`; `saldos_incapacidad` se conserva como tabla heredada.

---

## Módulo de Referencias y Accesos de Pago ("Chancucos")

- Lista de referencias frecuentes (vivienda, remodelación, gas, energía, agua, internet, cadenas).
- **Acción 1:** copiar código al portapapeles con un clic.
- **Acción 2:** botón *Pagar* que redirige a la URL oficial.
- **Estado:** exclusivo de `ADMIN_OLB`; proyección a perfiles de usuario.

---

## Bitácora de Cambios

### 2026-11-17 — SRS v1.7, bloques A a D: UI móvil, metas dividir/duplicar, checks corregibles y días de pago

**Cambios realizados**
1. `static/css/estilos.css` — rejillas con `minmax(min(...), 100%)`, `min-width: 0` en campos, normalización de fechas, alturas de 50 px y texto a 16 px en móvil (ADR-30).
2. `modelos.py` y `core/base_datos.py` — `ProyeccionAhorro.modo_ambas` con CHECK y migración idempotente; el rebuild de la tabla conserva `COALESCE(modo_ambas, 'DIVIDIR')` (ADR-31).
3. `servicios/ahorro.py` — `MODO_DIVIDIR`/`MODO_DUPLICAR`, `valor_por_pago(valor, quincena, modo)`, `valor_mensual_efectivo`; total proyectado y planeado usan el valor efectivo.
4. `servicios/pagos_metas.py` — `desmarcar_pagado` revierte el pago y su abono; la generación de gastos respeta el modo (ADR-32).
5. `routers/gastos.py` — `POST /gastos/{id}/no-pagado` con auditoría `GASTO_DESMARCADO`.
6. `templates/finanzas/_gasto_fijo.html` (nuevo) — macro `fila_gasto` y `boton_editar` compartidas; lápiz, «Cancelar», × circular, ✔ solo con `check_visible` y abono manual.
7. `templates/finanzas/index.html` y `presupuesto/index.html` — usan la macro; «Limpiar checks» con `boton--advertencia` y `data-confirmar`; deducciones fijas con el mismo lápiz y «Cancelar».
8. `static/js/app.js` — delegación para `data-cancelar-edicion` y `data-confirmar`.
9. `templates/presupuesto/index.html` y `static/js/presupuesto.js` — selector de modo con explicación de montos.
10. `static/js/sw.js` — caché `olb-finanzas-v12`.
11. `modelos.py` y `core/base_datos.py` — `Chancuco.dia_pago_1` y `dia_pago_2` con migración idempotente (ADR-33).
12. `servicios/chancucos.py`, `routers/chancucos.py` y `templates/chancucos/_dias.html` — pregunta «¿Es un único pago mensual?», validación 1–31 y distintivo «Día 15 · Día 30» en la tabla y en la tarjeta de Mis Finanzas.
13. `static/js/app.js` — el segundo día se oculta cuando el pago es único.
14. Pruebas nuevas: `tests/test_metas_modo.py` (10), `tests/test_gastos_checks.py` (9) y `tests/test_chancucos_dias.py` (10).
15. `MEMORY.md` — ADR-30 a ADR-33; `diccionario_datos.md` §9 con los días de pago.

**Verificación**
- `pytest -q` → **318 pruebas en verde**.
- `python -m compileall -q app scripts` sin errores.
- Migración de `modo_ambas` probada dos veces sobre una copia de `datos/finanzas.db`: columna presente, meta existente en `DIVIDIR`, 0 nulos.

**Pendiente**
- Revisión visual en navegador (360/390/768/escritorio) de las cuatro primeras entregas.
- Bloques E a G del SRS v1.7.

### 2026-11-16 — SRS v1.6: montos sin centavos, metas como gastos con check, incapacidades

**Cambios realizados**
1. `core/texto.py` — `formatear_cop` sin centavos (ADR-23).
2. `modelos.py` y `core/base_datos.py` — `gastos` con `id_proyeccion`, `pagado`, `pagado_en`, `check_visible` e `inhabilitado_hasta`; migración idempotente. Verificada sobre una base con el esquema anterior.
3. `servicios/pagos_metas.py` (nuevo) — generación de gastos de meta, ✔, limpieza de checks, inhabilitación de 8 días, sincronización del abono (ADR-24, ADR-25).
4. `servicios/ahorro.py` — se retira `registrar_abono`; `MesMeta.estado`; `diagnostico` devuelve `metas_mes`.
5. `servicios/gastos.py` y `servicios/quincenas.py` — `valor_computable` excluye los pagos inhabilitados de los totales.
6. `routers/gastos.py` — rutas `POST /gastos/{id}/pagado`, `POST /gastos/limpiar-pagos`; la × usa `quitar_gasto`; editar sincroniza el abono.
7. `routers/presupuesto.py` — se retira la ruta de abono manual.
8. `routers/finanzas.py` — genera los gastos del mes visible; `incapacidad_omitir` (ADR-26).
9. Plantillas: `finanzas/index.html` (✔ y × circulares del mismo tamaño, «Limpiar checks» por quincena, estado inhabilitado, «Valor:» retirado de la fila para que quepa la descripción en el celular, aviso de incapacidades); `presupuesto/index.html` (meses de solo lectura centrados con estado, banner con metas del mes).
10. `static/css/estilos.css` — círculos, estados y centrado de meses.
11. `static/js/finanzas.js` e `incapacidades.js` — Enter solo recalcula; «Limpiar» real.
12. `static/js/sw.js` — caché `olb-finanzas-v8`.
13. `diccionario_datos.md` §7 y §9.2; `Guia.md` con la ficha de `pagos_metas.py`.
14. Pruebas: `tests/test_metas_gastos.py` (nuevo, 17 pruebas); se reemplazan los abonos manuales en `test_presupuesto.py`; se agregan dos pruebas de incapacidades en `test_incapacidad_en_vivo.py`.

**Verificación**
- `pytest -q` → **275 pruebas en verde**.
- `python -m compileall -q app scripts` sin errores.
- `generar_guia.py --verificar` → «71 archivos con ficha y sin docstrings pendientes».

**Ajustes posteriores (ADR-25.a y ADR-27)**
- Plazo de inhabilitación de 15 días; abono manual solo en pagos saltados.
- `gastos.monto_pagado`; abonos heredados como pagos con su monto real.
- Ediciones de una quincena se propagan a los meses siguientes no pagados.
- Metas generan toda su duración escogida, en meses o años (ADR-28).
- Pruebas: **282 en verde**.

**Pendiente**
- Revisión visual en navegador (móvil y escritorio): botón ✔/× y alineación de meses.
- Factura PDF de OLB_BYTE (aplazada).

### 2026-11-16 — SRS v1.5, bloque 1: caja única de deducciones

**Objetivo:** que el usuario vea una sola cifra de deducciones y no un descuento de incapacidad suelto.

1. `routers/finanzas.py` — nuevos helpers `_fijas_del_periodo`, `_total_fijas` y `_total_deducciones_ley`; el contexto y el JSON publican `detalle_fijas_periodo`, `deducciones_fijas_periodo` y `total_deducciones_ley`.
2. `templates/finanzas/index.html` — «Deducciones de ley» en rojo, sin signo menos, con subtítulo «Deducciones fijas del salario» que lista los conceptos; el total final suma salud + pensión + incapacidad + fijas.
3. `static/js/finanzas.js` y `estilos.css` — repintado de la caja y estilos de la lista de conceptos.
4. Pruebas de finanzas actualizadas al nuevo total.

**Verificación:** `pytest -q` en verde; sin cambios de esquema.

### 2026-11-16 — SRS v1.5, bloque 2: incapacidades por tramo mensual sin rollover

1. `servicios/registro_incapacidades.py` — `tramos_del_mes()` y `descuento_del_mes()`; el descuento sale de las incapacidades registradas que cubren el mes.
2. `servicios/periodos.py` — se elimina el rollover; el historial recalcula por tramo.
3. `routers/finanzas.py` — autocargan las incapacidades del periodo y exponen `tramos` en el JSON.
4. `static/js/incapacidades.js` (nuevo) — cálculo automático al cambiar fechas.
5. `core/base_datos.py` — `_migrar_saldos_incapacidad` conserva columnas heredadas.

**Decisión:** ADR-20. **Verificación:** pruebas de incapacidad y periodos en verde.

### 2026-11-16 — SRS v1.5, bloques 3 a 5: sueldo de solo lectura, desglose y móvil

1. **Sueldo de solo lectura:** la liquidación muestra el sueldo del perfil con `campo__valor--destacado` y un enlace «Cambiarlo en Mi Perfil»; el contexto publica `sueldo_periodo`. El backend sigue aceptando `sueldo_basico` inyectado para pruebas.
2. **Desglose compacto:** `.tabla--compacta` sin `min-width` ni `nowrap`; `_detalle_formateado` deja de publicar `factor` (columnas Concepto, Horas, Valor) y desaparece el scroll horizontal.
3. **Móvil:** submenú en cuadrícula 2 × 2 a 640 px, `.fila-campos` a una columna, paneles a 16 px, hero reducido y botones a ancho completo. «Agregar deducción fija» pasa a `boton boton--primario` sin `+`, idéntico a «Crear meta».
4. `sw.js` — caché `olb-finanzas-v7`.

**Verificación:** `compileall` OK y **251 pruebas** en verde; prueba nueva del botón homologado.

### 2026-11-16 — SRS v1.5, bloque 6: metas con «Ambas quincenas»

1. `servicios/ahorro.py` — `QUINCENA_AMBAS = 3`, `QUINCENAS_VALIDAS`, `etiqueta_quincena()` y `valor_por_pago()`; propiedades homónimas en `MetaResumen`.
2. `modelos.py` — `CHECK (quincena IN (1, 2, 3))`.
3. `core/base_datos.py` — `_migrar_proyeccion_quincena()` reconstruye metas y abonos (hija primero) conservando filas e índices; probada dos veces sobre una base con datos.
4. `templates/presupuesto/index.html` — tercera opción y «(X por pago)».
5. `diccionario_datos.md` §9.1 actualizado.

**Decisión:** ADR-22. **Verificación:** **254 pruebas** en verde.

### 2026-11-16 — SRS v1.5, bloque 7: deudas con amortización automática

1. `servicios/deudas.py` reescrito — `tasa_implicita` (bisección, 10 decimales), `crear_deuda` de seis campos, `_aplicar_pago`, `aplicar_cuotas_vencidas`, `proyeccion_deuda`, `cuota_mensual_equivalente`, `resumen_deudas`.
2. `modelos.py` — `Deuda` con `cuotas_pendientes`, `periodicidad`, `fecha_creacion` y `tasa_interes NUMERIC(12,10)`; nueva tabla `PagoDeuda` (`pagos_deuda`).
3. `routers/deudas.py` — seis campos, sin abono manual, aplicación de cuotas al abrir y aviso de cuántas se aplicaron.
4. `templates/deudas/index.html` — tarjetas de resumen, formulario y «Ver amortización» con cuotas aplicadas y próximas.
5. `core/base_datos.py` — `_migrar_columnas_deudas`; `conftest.py` limpia `pagos_deuda`.
6. `diccionario_datos.md` §8 reescrito y §8.1 nuevo.

**Decisión:** ADR-21. **Verificación:** el ejemplo del SRS cierra en cero con última cuota 100.000,02; **260 pruebas** en verde.

### 2026-11-16 — SRS v1.5, bloque 9: `Guia.md` y documentación

1. `backend/scripts/generar_guia.py` (nuevo) — recorre `backend/app`, extrae módulos, clases, funciones y métodos con su docstring, reescribe el bloque `<!-- INVENTARIO:INICIO --> … <!-- INVENTARIO:FIN -->` de `Guia.md` y con `--verificar` falla si falta un docstring o una ficha.
2. `Guia.md` (nuevo) — arquitectura, roles, inventario automático, **70 fichas por archivo**, flujos, fórmulas, migraciones, comandos y lista de verificación.
3. `AGENTS.md` §5 y §9 — obligación de mantener la guía y estado verificado.
4. `MEMORY.md` — ADR-20/21/22, parámetros de dominio corregidos y bitácoras del SRS v1.5.

**Verificación:** `generar_guia.py --verificar` → «70 archivos con ficha y sin docstrings pendientes».

### 2026-11-16 — SRS v1.4: layout, navegación y deducciones fijas

**Cambios realizados**
1. `templates/finanzas/_subnav.html` y `estilos.css` — el submenú pasa a botones independientes con hover y estado activo; en móvil hace scroll horizontal (REQ-03).
2. `templates/finanzas/index.html` — se elimina el encabezado intermedio de la columna izquierda para que ambas columnas empiecen a la misma altura (REQ-01); «Desglose de horas extras» pasa justo debajo de la liquidación (REQ-06); se quita el panel de administración de atajos (REQ-07).
3. `estilos.css` — `.columna-finanzas--liquidacion { order: -1 }` en móvil (REQ-02); filas de gastos compactas con botones «Editar» y «×» del mismo alto y ancho (REQ-09).
4. `diccionario_datos.md` §9.3 y `modelos.py` — tabla `deducciones_fijas` (REQ-08).
5. `servicios/deducciones_fijas.py` (nuevo) — alta, edición, eliminación y totales por quincena.
6. `servicios/quincenas.py` — resta deducciones fijas; aplica incapacidad al sueldo base (REQ-05) y recargos a la quincena de deducciones (REQ-04).
7. `routers/finanzas.py` — contexto con deducciones fijas; `POST /finanzas/calcular` devuelve `quincenas`.
8. `routers/presupuesto.py` y `templates/presupuesto/index.html` — gestión de deducciones fijas; se retira «Registrar gastos fijos».
9. `static/js/finanzas.js` — `pintarQuincenas()` actualiza saldo, ingreso y deducciones en vivo.
10. `static/js/sw.js` — caché `olb-finanzas-v3`.
11. Pruebas: `tests/test_deducciones_fijas.py` (12 pruebas nuevas); `test_quincenas.py` actualizado a REQ-01 y REQ-07; `conftest.py` limpia `deducciones_fijas`.

**Verificación**
- `python -m compileall` sin errores.
- `pytest -q` → **238 pruebas en verde**.

**Pendiente**
- Validar la base legal de salud y pensión (ver ADR-18).
- Revisión visual en navegador de REQ-01 y REQ-02.

### 2026-11-16 — Cálculo en vivo de incapacidades y sueldo proyectado

**Objetivo:** que las horas extras y la incapacidad muevan el sueldo del periodo en el mismo instante, y de ahí las quincenas, para cuadrar gastos con el salario real.

**Cambios realizados**
1. `routers/finanzas.py` — `_descuento_por_fechas()` calcula el descuento del mes con `liquidar_mes_incapacidad` (días 1–2 al 100 %; desde el día 3, 33,33 % de descuento). Si el formulario envía `incapacidad_inicio`/`incapacidad_fin`, ese valor reemplaza el oculto y se suma el saldo arrastrado del mes.
2. `routers/finanzas.py` — `sueldo_proyectado` (sueldo + horas extras − incapacidad) se devuelve en el JSON como `datos.sueldo_proyectado`. `incapacidad` resume días sin y con descuento.
3. `static/js/finanzas.js` — envía siempre las fechas, repinta el sueldo proyectado y el resumen de incapacidad, y actualiza el campo oculto para que «Guardar periodo» guarde el mismo descuento.
4. `templates/finanzas/index.html` — «Sueldo proyectado del periodo» bajo el sueldo básico; fechas de incapacidad marcadas para el cálculo en vivo; resumen de días bajo el título.
5. Pruebas: `tests/test_incapacidad_en_vivo.py` (6 pruebas: días 1–2 sin descuento, tercer día en adelante con norma, sueldo y quincenas que bajan, horas extras que suben el sueldo, rango inválido, valor listo para guardar).

**Decisión**
- La incapacidad se liquida sobre el sueldo mensual del perfil, no sobre el número escrito en el formulario, para que cada quincena use la misma base.

**Verificación**
- `pytest -q` → **244 pruebas en verde**; `node --check` del JavaScript sin errores.
- Caché del service worker: `olb-finanzas-v4`.

---

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





