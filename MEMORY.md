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
- **Registro y Detalles de deudas:** pasivos acumulados.
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
  - Dashboard con **cuatro tarjetas**: `Mis Finanzas`, `OLB_BYTE` (solo `ADMIN_OLB`), `Registro y Detalles de deudas` y `Trabajos Extras`.
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

### ADR-46 — Diseño único de la factura para pantalla, PDF y WhatsApp (SRS OLB_BYTE v1.0, rediseño)
- **Contexto:** el propietario entregó un diseño corporativo (cabecera con curva, tarjetas, tabla con relleno hasta nueve filas, totales, medios de pago y pie). Debe verse igual en la pantalla, en la vista previa, en la descarga y en el PDF enviado por WhatsApp.
- **Decisión:**
  - Una sola hoja compartida (`templates/olb_byte/_hoja_factura.html`) y un solo CSS (`static/css/factura-olb.css`). `factura.html` (pantalla) y `factura_pdf.html` (PDF) solo las incluyen; por eso no pueden divergir.
  - Un solo contexto (`factura_pdf.datos_factura`) alimenta las dos salidas. La pantalla no aplica el límite de diez productos (`validar_maximo=False`); el PDF sí.
  - El CSS se incrusta en el PDF como texto y los logos como data URI, para que Chromium no dependa de rutas ni de red.
  - El PDF se dibuja con un cuerpo más ancho y se reduce con `ESCALA_PDF = 0.75`: a 100 % el diseño con diez productos ocupa dos hojas Carta. La prueba `test_pdf_con_diez_productos_cabe_en_una_ppagina` lo vigila.
  - Columna «REFERENCIA» del diseño renombrada a «CATEGORÍA», para coincidir con el campo que se captura en la venta.
  - La cuenta BBVA, la dirección y el teléfono se guardan como constantes en `factura_pdf.py`, no en el HTML, para editarlos en un solo lugar.
  - En pantallas de 760 px o menos la hoja se reorganiza en una columna; el PDF no usa esas reglas porque se dibuja con ancho de hoja Carta.
- **Verificación:** 479 pruebas en verde (incluye el PDF de 3 y de 10 productos en una hoja). Capturas en escritorio (850 px) y celular (390 px): sin desbordamiento horizontal.
- **Archivos:** `servicios/factura_pdf.py`, `routers/olb_byte.py` (`ver_factura`), `templates/olb_byte/{_hoja_factura,factura,factura_pdf}.html`, `static/css/factura-olb.css`, `Guia.md` §10, `tests/test_factura_pdf.py`, `tests/test_olb_vistas.py`.

### ADR-43 — Pago al vender, cobro en página propia, WhatsApp con PDF y límites de la web (SRS OLB_BYTE v1.0, ajustes 3)
- **Contexto:** el usuario pidió registrar la forma de pago y el anticipo en la venta, un flujo de cobro completo, enviar la factura en PDF por WhatsApp desde la tabla de órdenes, quitar «Nuevo cliente», ocultar ganancia y saldo en órdenes, y que el botón de contactos abra la libreta.
- **Decisiones:**
  - **Pago al vender:** `registrar_venta` recibe un `PagoInicial` opcional. El contado cobra el total; el crédito registra el anticipo solo si el cliente lo hace. El pago se valida antes de crear la orden y se guarda en la misma transacción. Un anticipo por encima del total se rechaza. El campo «Valor del anticipo» no estaba en la especificación: se añadió porque el anticipo necesita un monto.
  - **Cobro:** la gestión de cada orden vive en `/olb-byte/ventas/{id}/cobro` con dos opciones (registrar abono o pago total, y recordatorio por WhatsApp). Cancelar regresa a pendientes. Un error al cobrar vuelve a esa página (`desde_cobro`).
  - **Órdenes:** solo muestran el total. La ganancia y el saldo se ocultan en la tabla del panel. Analítica y Cartera siguen mostrándolos: el propietario decidió que no requieren protección adicional, porque el módulo es de uso exclusivo del administrador.
  - **WhatsApp con PDF:** la Web Share API comparte el PDF como archivo con el texto «Hola {cliente}, adjunto tu factura de compra.». Si el navegador no puede compartir archivos (por ejemplo, un PC), se descarga el PDF y se abre WhatsApp, y el usuario lo adjunta con el clip. Una página web no puede adjuntar un archivo a un chat sin pasar por la hoja de compartir.
  - **Panel de producto:** «Guardar» agrega el producto a la tabla y bloquea el panel. «+ Agregar otro producto» lo desbloquea. Ambos botones de abajo comparten tamaño y color.
  - **Contactos:** la Contact Picker API solo funciona en Android con Chrome y HTTPS, y solo selecciona contactos existentes; no crea contactos nuevos. Donde no existe, el botón guarda el número como tarjeta de contacto (.vcf), que el celular abre para guardarlo.
  - **Balance:** la tabla de texto se cambia por barras horizontales. Con déficit, el cero queda al centro y el déficit sale a la izquierda, en rojo y con signo.
  - **Submenú:** el borde superior se cortaba por `overflow-x: auto`; se agregó espacio interno.
- **Archivos:** `servicios/comercial.py` (`PagoInicial`, `barras_balance`, `texto_compartir_factura`), `routers/olb_byte.py` (`ver_cobro`, `_datos_pago`, `_pago_desde_datos`, se retira `crear_cliente`), `templates/olb_byte/{index,cobro,pendientes,cartera}.html`, `static/js/{olb_byte,factura}.js`, `static/css/estilos.css`, `Guia.md` §10 (personalizar la factura), `tests/test_pago_y_cobro.py`.

### ADR-44 — Capacidad de endeudamiento compartida y proyección a 12 meses (SRS v1.7, bloque F)
- **Contexto:** el usuario necesita ver cuánto de su ingreso está comprometido con gastos y deudas, qué deudas están por terminar y cómo cambiaría su saldo libre en el próximo año.
- **Decisión:** nuevo `servicios/capacidad.py` de solo lectura. El ingreso es el de las quincenas más los trabajos extras cobrados; los gastos fijos suman gastos, deducciones de ley y deducciones fijas; la cuota de deudas se calcula con `cuota_mensual_equivalente`. La dona reparte el ingreso en tres arcos (`_repartir_arcos`) que siempre suman 100: si los compromisos superan el ingreso, se escalan proporcionalmente y el libre queda en cero. El semáforo usa el porcentaje real de deuda sobre el ingreso: hasta 20 % verde, hasta 35 % ámbar, más rojo. `deudas_por_terminar` incluye las que tienen tres cuotas o menos y su fecha de cierre; `proyeccion_capacidad` simula doce meses y retira la cuota cuando cada deuda termina. El panel vive en `templates/finanzas/_capacidad.html` y se instancia de forma independiente en Gastos y Presupuesto y en Trabajos Extras.
- **Archivos:** `servicios/capacidad.py`, `templates/finanzas/_capacidad.html`, `routers/presupuesto.py`, `routers/trabajos.py`, `templates/presupuesto/index.html`, `templates/trabajos/index.html`, `static/css/estilos.css`, `static/js/sw.js` (`olb-finanzas-v16`), `tests/test_capacidad.py`.

### ADR-45 — Consejero financiero con bola de nieve, avalancha y metas (SRS v1.7, bloque G)
- **Contexto:** con un excedente real el usuario debe decidir entre amortizar deudas o ahorrar, y no siempre sabe qué deuda atacar primero.
- **Decisión:** `servicios/consejero.py` se activa solo si el disponible consolidado (quincenas + extras) supera $300.000. Con deudas simula doce meses de cuotas mínimas y dos escenarios que aplican todo el excedente: bola de nieve (saldo menor primero) y avalancha (tasa mayor primero). Recomienda el de menor interés total y muestra la deuda objetivo, el ahorro en intereses, el mes de liquidación y la deuda más grande. Sin deudas dirige el excedente a la primera meta activa y calcula en cuántos meses se completa; si no hay metas, sugiere crearlas. La gráfica compara doce meses de base contra optimizado: en modo deuda es saldo restante (más bajo es mejor) y en modo ahorro es dinero acumulado (más alto es mejor). Las tasas quincenales se convierten a mensuales con `(1 + r)² − 1`. Es una proyección educativa con ingreso y cuotas constantes.
- **Archivos:** `servicios/consejero.py`, `routers/presupuesto.py`, `templates/presupuesto/index.html`, `static/css/estilos.css`, `tests/test_consejero.py`.

### ADR-56 — Deducción fija vinculada a la deuda que paga (SRS v1.9)
- **Contexto:** una libranza es un descuento de nómina y también un crédito con cuotas. Registrada en los dos lugares, el sistema la contaba dos veces; registrada solo en uno, no se veía el avance de cuotas o no se descontaba en la quincena correcta.
- **Decisión:** `deducciones_fijas.id_deuda` (nulo por defecto) vincula la deducción a una deuda **mensual** y **activa** del mismo usuario. El valor de la deducción toma la cuota de la deuda. Mientras la deuda esté activa, la deducción se descuenta en su quincena y su cuota sale de la cuota de deudas (dona y diagnóstico). Al pagarse la deuda, la deducción deja de descontarse (`listar_vigentes`). Al borrar la deuda, la deducción queda como descuento normal (`ON DELETE SET NULL`). La proyección de doce meses retira el descuento y la cuota juntos cuando termina el crédito. Las deudas quincenales no se vinculan porque una deducción se descuenta una vez al mes.
- **Consecuencias:** `eliminar_deuda` desvincula las deducciones en la sesión y en la base. Presupuesto aplica las cuotas vencidas al abrirse. Las deducciones anteriores no cambian. Pendiente: vincular deudas quincenales, que necesitaría dos deducciones por mes.

### ADR-55 — Filtros compartidos, saldo por producto y garantía por línea (SRS v1.9, bloque 3)
- **Contexto:** la analítica tenía tablas separadas sin filtros y no se podía descargar lo que se veía. El propietario pidió una fila por producto en el CSV, con saldo, abonos, ganancia y garantía. El saldo y los abonos pertenecen a la orden, no a cada producto, y la garantía de la orden es la más cercana de sus productos.
- **Decisión:** un `Filtro` (año, mes, cliente, producto) lo usan todas las tablas y sus CSV. Saldo y abonos se reparten entre líneas en proporción a su total, con la última línea absorbiendo el redondeo, para que las sumas cuadren al centavo. Cada línea guarda su propia fecha de garantía (`venta_detalle.garantia_fecha_fin`).
- **Consecuencias:** las garantías antiguas heredan la fecha de su orden, así que un producto con más meses puede aparecer vencido antes de tiempo en ventas anteriores a este bloque. La garantía de reclamos (RF-05) sigue usando la fecha de la orden; no se tocó.

### ADR-54 — Día de cada quincena lo define el usuario (SRS v1.9, bloque 2)
- **Contexto:** la app suponía que todas las quincenas caen el 15 y el 30. Hay usuarios que cobran el 5 y el 20, y las metas, deducciones y gastos mostraban fechas que no eran las suyas.
- **Decisión:** el perfil quincenal guarda `dia_quincena_1` y `dia_quincena_2` (1 a 31). Son obligatorios en modalidad quincenal, la quincena 2 debe caer después de la 1, y los perfiles anteriores quedan con 15 y 30. Todas las etiquetas salen de `perfiles.etiquetas_quincena`. Un día que no existe en el mes se entiende como el último día del mes; el valor guardado no cambia.
- **Consecuencias:** en PostgreSQL la columna se agrega con `ADD COLUMN IF NOT EXISTS` al arrancar. Trabajos Extras queda pendiente porque sus fechas las digita cada contrato.

### ADR-53 — Base mínima de liquidez, deudas sin intereses y blindaje de entradas (SRS v1.8)
- **Contexto:** el consejero ofrecía abonos con dinero que el usuario necesita para vivir, las deudas se registraban con una tasa implícita que nadie podía comprobar y un dato mal digitado rompía la vista. Además, el orden de pago de las deudas priorizaba la tasa, un dato que ya no existe.
- **Decisiones:**
  - **Base mínima de liquidez:** `BASE_MINIMA_LIQUIDEZ = Decimal("300000")` en `servicios/capacidad.py`, reutilizada por `ahorro.py` y `consejero.py`. El excedente real es `libre − base`; solo ese remanente alimenta el consejo y el arco «Disponible para abonar». Si el libre no supera la base, el consejo se apaga con un mensaje fijo que invita a crear una meta de emergencia «con lo mínimo que puedas ahorrar». Nunca se llama «colchón de liquidez».
  - **Deudas sin intereses:** se elimina `tasa_implicita()` y la columna `tasa_interes` del modelo. `validar_plan()` exige que `cuota × cuotas` coincida con el total adeudado con tolerancia de **$1 por cuota** (60 cuotas → $60); un exceso o defecto mayor pide revisar y reingresar. Cada cuota abona capital completo y la última absorbe el redondeo.
  - **Orden por flujo de caja:** si el excedente puede cancelar una deuda completa, se elige la que deja más cuotas por delante (12 meses antes que 5); si no alcanza para ninguna, la de menor saldo. La estrategia se llama `FLUJO_DE_CAJA`; desaparecen avalancha y bola de nieve como conceptos de tasa.
  - **Blindaje de entradas:** `parsear_porcentaje()` acepta «60», «60 %» y «60,5», y rechaza el punto decimal ambiguo; el perfil muestra «60 %» y autocompleta el complemento igual. `main.py` registra un manejador global de `ValueError` que responde 400 con una página mínima, y `app.js` revisa los campos numéricos antes de enviar. El abono de OLB_BYTE muestra el saldo pendiente cuando el monto se pasa.
  - **Metas:** el selector de modo de «Ambas quincenas» va en su propia fila; la lista de abonos muestra cinco y se desplaza dentro de su caja.
- **Archivos:** `servicios/capacidad.py`, `servicios/consejero.py`, `servicios/deudas.py`, `servicios/ahorro.py`, `servicios/perfiles.py`, `servicios/trabajos.py`, `servicios/comercial.py`, `core/texto.py`, `main.py`, `modelos.py`, `routers/{deudas,perfil}.py`, `templates/{deudas,presupuesto,perfil}/index.html`, `templates/finanzas/_capacidad.html`, `static/js/{app,perfil}.js`, `static/css/estilos.css`, `diccionario_datos.md` §8 y §8.1, `tests/{test_capacidad,test_consejero,test_gastos_deudas}.py`.
- **Verificación:** `compileall` OK y **559 pruebas** en verde.

### ADR-42 — Formulario de venta v2, categoría y submenú (SRS OLB_BYTE v1.0, ajustes de validación)
- **Contexto:** el usuario validó la Fase 2 y pidió: que «Buscar en Contactos» funcione, mover las acciones de órdenes al submenú como en Gastos y Presupuesto, meter el detalle de productos dentro del formulario de venta, cambiar «referencia» por «categoría» y que la tabla no sea tan larga en el celular.
- **Diagnóstico del botón de contactos:** la clase `.boton` fija `display: inline-flex`, y eso anula el atributo `hidden`. El botón siempre estaba visible, y en PC no hace nada porque el navegador no tiene la Contact Picker API (solo existe en Android con Chrome y en HTTPS). Se corrige con una regla global `[hidden] { display: none !important }`, y ahora se muestra una nota que explica cuándo funciona.
- **Decisiones:**
  - `venta_detalle.referencia` pasa a `categoria`. Es un `RENAME COLUMN` idempotente (`_renombrar_referencia_a_categoria`) que conserva los datos.
  - El formulario tiene un panel de producto (nombre, categoría, cantidad, costo, precio, garantía) con subtotal y «+ Agregar otro producto» (o Enter). Los productos quedan en una tabla de detalle con Eliminar y Actualizar en la misma fila. Actualizar abre un cuadro de edición con Actualizar y Cancelar en horizontal.
  - Los campos del panel no llevan `name`: solo viajan las filas de la tabla. Si el usuario escribió un producto y pulsa «Registrar venta», se agrega antes de enviar.
  - En celular (≤ 640 px) la tabla se muestra como tarjetas. Se quitó el `min-width` heredado de `.tabla` solo en esa vista.
  - El submenú de OLB_BYTE reutiliza `subnav-finanzas`. Los enlaces de «Órdenes registradas» pasan arriba, y las vistas de cobro y cartera dejan de tener botones «Volver al panel».
- **Defecto encontrado en la verificación:** la página principal no marcaba «Ventas» como pestaña activa porque faltaba `seccion`. La prueba lo detectó y se corrigió.
- **Verificación:** `pytest` en verde (434 pruebas, incluidas 10 nuevas en `tests/test_olb_ui.py` y 1 de migración). Recorrido real en Chromium con la aplicación levantada (19 comprobaciones: agregar con Enter, cancelar sin cambios, botones horizontales, totales, sin desplazamiento en celular, precio en pesos) y revisión visual de escritorio y celular.
- **Archivos:** `modelos.py`, `core/base_datos.py`, `servicios/comercial.py`, `servicios/analitica.py`, `servicios/factura_pdf.py`, `routers/olb_byte.py`, `templates/olb_byte/index.html`, `templates/olb_byte/_subnav.html`, `templates/olb_byte/{pendientes,cartera,garantias,analitica,factura,factura_pdf}.html`, `static/js/olb_byte.js`, `static/css/estilos.css`, `diccionario_datos.md` §10.4, `tests/test_olb_ui.py`, `tests/test_migracion_olb.py`.

### ADR-41 — Factura PDF: arquitectura de render y límites (SRS OLB_BYTE v1.0, Fase 7)
- **Contexto:** ADR-36 eligió Playwright. La factura debe salir en una sola página Carta con la paleta del SRS, logos de `assets/` y medios de pago.
- **Decisión:**
  - La plantilla `olb_byte/factura_pdf.html` es un HTML independiente (sin el layout de la app). El router la renderiza con Jinja y la pasa a `servicios/factura_pdf.generar_pdf`, que abre Chromium headless por petición, carga el HTML con `set_content` y genera el PDF con `printBackground=True`, formato Carta y márgenes en cero.
  - Los logos se embeben como data URI para que el PDF no dependa de rutas ni de red. Se localizan con globs porque los nombres de `assets/` tienen tildes.
  - La tabla tiene diez filas fijas: las vacías se rellenan para mantener el efecto cebra. Con más de diez productos la factura no cabe en una página; el sistema lo rechaza (HTTP 422) con el motivo, en lugar de partir la factura.
  - Sin Chromium instalado la respuesta es HTTP 503 con el comando `python -m playwright install chromium`. La vista HTML sigue funcionando.
  - La vista previa y la descarga usan la misma ruta con `?descargar=0|1`. Compartir usa la Web Share API con el archivo; si el navegador no lo permite, abre WhatsApp.
- **Verificación visual:** se generó una factura de cuatro productos con abono y se revisó la imagen resultante; los medios de pago quedaron en una fila tras ajustar el ancho de la columna.
- **Archivos:** `servicios/factura_pdf.py`, `routers/olb_byte.py` (`ver_factura_pdf`), `templates/olb_byte/factura_pdf.html`, `templates/olb_byte/factura.html`, `static/js/factura.js`, `static/js/sw.js` (v15), `static/css/estilos.css`, `requirements.txt`, `DESPLIEGUE.md` §13, `tests/test_factura_pdf.py`.

### ADR-40 — Analítica: reglas de cálculo y umbral de margen (SRS OLB_BYTE v1.0, Fase 6)
- **Contexto:** RF-12 a RF-14 piden reportes mensuales y anuales, rentabilidad, ranking de clientes VIP y alertas de subida de costo.
- **Decisión:**
  - Ingresos, ganancia, ventas y rankings solo usan órdenes activas (ADR-35). El historial de costos incluye todas las compras, porque la mercancía ya se compró aunque la orden se haya anulado.
  - Variación = (actual − anterior) ÷ |anterior| × 100. Sin base de comparación (periodo anterior en cero) se muestra «—».
  - Rentabilidad anual = ganancia ÷ costo × 100. Sin costo se muestra «—».
  - Ranking VIP: monto total de compras activas; empate por número de compras; luego por nombre.
  - Alerta de costo: el costo unitario de la compra más reciente es mayor que el de la compra anterior del mismo producto (nombre y referencia). Un producto con una sola compra no genera alerta.
  - Margen = (último precio − último costo) ÷ último precio × 100. Por debajo de **15 %** (`UMBRAL_MARGEN_BAJO`) se marca «Margen bajo». El umbral es una decisión de negocio, no un dato legal: se puede ajustar en `servicios/analitica.py`.
- **Archivos:** `servicios/analitica.py`, `routers/olb_byte.py` (`ver_analitica`), `templates/olb_byte/analitica.html`, `static/css/estilos.css` (`.barra`), `tests/test_analitica.py`.

### ADR-39 — Garantías y tasa de fallas por producto (SRS OLB_BYTE v1.0, Fase 5)
- **Contexto:** RF-05 pide reclamos en trámite con el proveedor y un ranking de productos con mayor tasa de fallas. La tabla `garantias_proveedor` ya existía desde la Fase 1.
- **Decisión:**
  - Un reclamo nace `ABIERTA` sobre una línea de una orden activa. Copia el producto con referencia (`Audífonos BT (AB-1)`) para que el ranking no dependa de la línea.
  - El flujo es `ABIERTA → EN_TRAMITE → RESUELTA | RECHAZADA`. Un reclamo cerrado es final; si la falla vuelve, se abre uno nuevo. Ningún reclamo vuelve a `ABIERTA`.
  - Tasa (%) = reclamos ÷ unidades vendidas en órdenes activas × 100. Cada reclamo cuenta como una falla. Un producto con reclamos y sin unidades activas se muestra como «—».
  - La vigencia del reclamo compara su día con `garantia_fecha_fin` de la orden (la más temprana de sus líneas). No se guarda fin de garantía por línea para no duplicar el dato.
- **Archivos:** `servicios/comercial.py` (`registrar_garantia`, `actualizar_estado_garantia`, `ranking_fallas`, `garantia_vigente_al_reclamo`, `opciones_garantia`), `routers/olb_byte.py` (`ver_garantias`, `registrar_garantia`, `actualizar_garantia`), `templates/olb_byte/garantias.html`, `tests/test_garantias.py`.

### ADR-38 — Dona de cartera frente a deuda y signos de cartera (SRS OLB_BYTE v1.0, Fase 4)
- **Contexto:** RF-11 pide una dona con la proporción entre cartera, deuda y balance. El balance es la diferencia de las otras dos cifras, así que no es una parte del total y no puede ser un arco.
- **Decisión:** la dona tiene dos arcos (cartera por cobrar y deuda con el proveedor), calculados en Python como porcentajes de su suma y dibujados como SVG con `stroke-dasharray`, sin JavaScript. El balance va en el centro, con el signo y color de RF-10. Si no hay cartera ni deuda no se dibuja nada.
- **Signos (RF-10):** `clasificar_saldo` aplica «−» y rojo a los déficits, y verde a los superávits. Solo se usa en el módulo de cartera. En el resto de la app los montos no llevan signo.
- **Archivos:** `servicios/comercial.py` (`clasificar_saldo`, `tabla_balance`, `segmentos_dona`), `routers/olb_byte.py` (`ver_cartera`, `registrar_abono_proveedor`), `templates/olb_byte/cartera.html`, `static/css/estilos.css`, `tests/test_cartera.py`.

### ADR-37 — Fechas comerciales en hora de la tienda (SRS OLB_BYTE v1.0, Fase 3)
- **Contexto:** las ventas y abonos usaban UTC en Python y `func.now()` (también UTC) en la base. El recibo de un abono habría mostrado horas 5 h distintas a las de la venta, y la garantía de una venta nocturna habría vencido un día antes o después.
- **Decisión:** `servicios/comercial.ahora_tienda()` devuelve `datetime.now(ZONA_TIENDA)` con desfase fijo UTC−5 (Colombia no tiene horario de verano; evita depender de `tzdata` en Windows). Todas las fechas comerciales (venta, abono, anulación, devolución y movimiento de proveedor) se fijan desde Python. Las vistas muestran la hora tal como quedó guardada.
- **Consecuencias:** las filas creadas antes de este cambio con `func.now()` quedan en UTC; el sistema es nuevo y no tiene datos reales, así que no se migran.

### ADR-35 — OLB_BYTE sin inventario, órdenes con snapshot y anulación sin reversa de proveedor (SRS OLB_BYTE v1.0)
- **Contexto:** el negocio no maneja stock: cada venta se compra al proveedor a crédito al momento de vender. El modelo previo descontaba `stock` y bloqueaba ventas, lo que contradice el SRS. Además, un cambio posterior de precio de catálogo no debe alterar facturas ni garantías.
- **Decisión:**
  - Se elimina el control de stock (columna `productos.stock` y validación de existencias). `productos` queda como legado sin uso en el flujo nuevo; no se borran datos.
  - Cada línea de venta guarda una copia de nombre, referencia, costo y precio (`venta_detalle`).
  - `ventas` conserva su nombre (equivale a `ordenes_venta` del SRS) y gana `numero_orden` (consecutivo sin reutilización, empieza en 1, confirmado por el propietario), `estado_orden` (`ACTIVA`/`ANULADA`), motivo y fecha de anulación.
  - La deuda con el proveedor es un libro de movimientos (`movimientos_proveedor`): `COMPRA_CREDITO` al vender y `ABONO` al pagar. Los movimientos no se editan.
  - **Anulación:** la orden sale de cartera, totales, ganancia y rankings. La deuda con el proveedor **no se revierte** (la mercancía ya se compró). Si el cliente ya abonó, la anulación **registra la devolución** en `devoluciones_clientes` (monto y método). Los abonos originales se conservan como historial.
  - **Consecutivo:** arranca en 1 (aplicativo nuevo, sin facturas previas).
  - **Productos:** la venta se escribe a mano (nombre, referencia, costo, precio, garantía); no se autocompleta desde el catálogo.
  - Abonos de clientes: nuevos registros solo `EFECTIVO` o `TRANSFERENCIA`, con fecha y hora. Los históricos se mantienen.
  - Garantías con proveedor en `garantias_proveedor` (estados `ABIERTA`, `EN_TRAMITE`, `RESUELTA`, `RECHAZADA`).
- **Consecuencias:** la migración reconstruye `productos` sin `stock`, agrega columnas a `ventas` y `venta_detalle` y asigna `numero_orden` a las ventas existentes en orden de fecha. Se probará sobre copia de `finanzas.db`.
- **Archivos:** `diccionario_datos.md` §10 (fuente única), `modelos.py`, `core/base_datos.py`, `servicios/comercial.py`, `routers/olb_byte.py`, plantillas `olb_byte/`.

### ADR-36 — Motor PDF: Playwright (Chromium headless) para la factura (SRS OLB_BYTE v1.0)
- **Contexto:** el SRS pide HTML5 + CSS3 con `printBackground: true`, tarjetas, efecto cebra y logos. Las opciones evaluadas eran WeasyPrint (requiere GTK en Windows), xhtml2pdf (CSS limitado para la paleta y el layout) y Playwright.
- **Decisión:** **Playwright para Python** renderiza la misma plantilla Jinja2 que la vista previa, en Chromium headless, con `printBackground=True` y formato Carta. Es la opción de mayor fidelidad visual y se mantiene en Python.
- **Costos asumidos:** dependencia nueva en `requirements.txt` y una descarga única de Chromium con `playwright install chromium`. La generación requiere ese navegador en el servidor; en `DESPLIEGUE.md` se documenta el paso. Si el entorno no lo tiene, la vista HTML sigue disponible y la descarga PDF devuelve un error explícito.
- **Archivos previstos:** `servicios/factura_pdf.py`, `routers/olb_byte.py`, `templates/olb_byte/factura_pdf.html`, `requirements.txt`, `DESPLIEGUE.md`.

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

### 2026-11-20 — Vista previa de WhatsApp reducida a JPEG de 71 KB

**Cambios realizados**
1. `static/img/vista-previa.png` (1,4 MB) reemplazado por `static/img/vista-previa.jpg`: 1200×588 px, JPEG calidad 85, 71 KB. Se hizo desde `assets/Nuevo Logo2.png`, que no se modificó.
2. `templates/base.html`: `og:image` y `twitter:image` apuntan a `vista-previa.jpg?v=5`.
3. `tests/test_vista_previa.py` espera el `.jpg` con `image/jpeg` y `?v=5`.

**Verificación:** `pytest` en verde con **621 pruebas**.

### 2026-11-20 — Imagen de vista previa de WhatsApp actualizada

**Causa:** la vista previa usa `static/img/vista-previa.png`, una copia separada de `assets/Nuevo Logo2.png`. Al cambiar solo `assets/`, la app seguía sirviendo la copia anterior. Además, WhatsApp guarda la imagen por su dirección (`?v=2`).

**Cambios realizados**
1. `static/img/vista-previa.png` es ahora una copia de `assets/Nuevo Logo2.png` (mismo MD5).
2. `templates/base.html`: `og:image` y `twitter:image` apuntan a `vista-previa.png?v=3`.
3. `tests/test_vista_previa.py` espera `?v=3`.

**Nota:** el logo de la factura se guarda en memoria al arrancar (`logo_como_data_uri`); para verlo cambiado hay que reiniciar la aplicación.

**Verificación:** `pytest` en verde con **621 pruebas**.

### 2026-11-20 — Metas en móvil: dos abonos visibles y formulario «Extender» dentro de la tarjeta

**Cambios realizados**
1. `static/css/estilos.css`: en celular la lista de abonos muestra dos meses (`max-height: 214px`, medido en Chromium a 390 px: cada tarjeta mide 101 px y la separación 10 px); el resto se desplaza.
2. El formulario «Extender» (`.formulario-abono-manual`) se acomoda en varias líneas en celular; antes, su campo de 90 px fijo lo sacaba de la tarjeta.
3. `sw.js` en `olb-finanzas-v49`.

**Verificación:** medición en Chromium a 390 px: el formulario termina en 340 px y el contenedor en 359 px; la lista mide 214 px. `pytest` en verde con **621 pruebas**. Pendiente: confirmar en 360 px.

### 2026-11-20 — Selección de la dona persistente y leyenda más pequeña

**Cambios realizados**
1. `static/js/dona.js`: el detalle seleccionado se mantiene al tocar el centro o el fondo; tocar otro arco lo cambia y tocar el mismo lo quita. Se eliminó el reinicio por clic fuera.
2. `static/css/estilos.css`: los arcos solo reciben el toque sobre su trazo (`pointer-events: stroke`), así que el centro ya no activa un arco. La leyenda de ambas donas pasa a 0,8 rem.
3. `sw.js` en `olb-finanzas-v48`.

**Verificación:** prueba en Chromium (390 px): tocar un arco muestra el detalle; tocar el centro y el fondo lo mantiene; un segundo toque al mismo arco lo quita. `pytest` en verde con **621 pruebas**; `generar_guia.py --verificar` sin problemas.

### 2026-11-20 — Formato de pesos al escribir en los campos de dinero

**Cambios realizados**
1. `static/js/moneda.js` (nuevo, cargado desde `base.html`): los campos con `data-moneda` agrupan los miles con punto mientras se escribe o pega; la coma separa hasta dos centavos; el cursor se conserva al insertar en medio. Porcentajes y cantidades no se tocan.
2. 24 campos de dinero marcados con `data-moneda` en perfil, deudas, gastos, trabajos, Mis Finanzas, presupuesto, OLB_BYTE (ventas, cobro, abonos, costos y precios de productos) e incapacidades.
3. `routers/perfil.py`: el sueldo guardado se muestra como «3.484.000» (antes «3484000,00»).
4. `sw.js` en `olb-finanzas-v47`.

**Verificación:** prueba en navegador (Chromium): escribir `3484000` → `3.484.000`; `1234567,5` → `1.234.567,5`; insertar un dígito en medio conserva el cursor; pegar se formatea; el porcentaje queda en `60`. `pytest` en verde con **621 pruebas** (3 nuevas en `tests/test_formato_moneda.py`); `generar_guia.py --verificar` sin problemas.

**Pendiente:** no se cambió el campo de horas extra ni los porcentajes de quincena (son cantidades y porcentajes, no pesos).

### 2026-11-20 — Analítica: filtros con botón de quitar, colores planos y separación de los botones CSV

**Cambios realizados**
1. `templates/olb_byte/analitica.html`: cada filtro activo muestra su etiqueta y un botón circular con flecha de reinicio que lo quita. «Quitar todos los filtros» pasa a un enlace plano.
2. `static/css/estilos.css`: los azules brillantes de la analítica se cambiaron por tonos grises-azulados planos: fila con filtro activo (`#2b3a4f`), chips (`#2b3444`), enlaces al pasar el cursor (`#e2e8f0`). Las garantías y el margen bajo usan `insignia--vigente`, `insignia--vencida` y `insignia--sin-garantia`, con texto apagado y buen contraste.
3. `.panel__cabecera` tiene 14 px de margen inferior: los botones «Descargar CSV» ya no quedan pegados a la línea de la tabla.
4. `sw.js` en `olb-finanzas-v45`.

**Verificación:** `pytest` en verde con **618 pruebas**; `generar_guia.py --verificar` sin problemas. Pendiente: revisión visual en 360/390/1280 px.

### 2026-11-20 — Movimientos con el proveedor en móvil y fecha más pequeña en órdenes

**Cambios realizados**
1. `templates/olb_byte/cartera.html`: en móvil, los movimientos con el proveedor son una lista vertical de cuatro columnas (fecha sin hora, concepto, monto y saldo). Al tocar una fila se abre un diálogo centrado con fecha y hora, tipo, concepto, monto y saldo después. La tabla completa queda solo para escritorio (`tabla-escritorio`).
2. `templates/olb_byte/index.html` y `static/css/estilos.css`: la fecha de las órdenes registradas usa `orden-movil__fecha` (0,7 rem).
3. `sw.js` en `olb-finanzas-v44`.

**Verificación:** 2 pruebas nuevas en `tests/test_movimientos_movil.py`; `pytest` en verde con **618 pruebas**; `generar_guia.py --verificar` sin problemas.

**Pendiente:** revisión visual en 360/390 px.

### 2026-11-20 — Donas interactivas, dona centrada en celular, banner de café más delgado y Neon actualizado

**Cambios realizados**
1. `static/js/dona.js` (nuevo, cargado desde `base.html`): al pasar, tocar o enfocar un arco, el centro muestra su nombre, porcentaje y valor; la leyenda resalta el arco; en celular el toque lo fija hasta tocar fuera. Sin JavaScript queda la leyenda y los `<title>`.
2. `finanzas/_capacidad.html` y `olb_byte/cartera.html`: arcos con `data-etiqueta`, `data-porcentaje` y `data-valor`; centro con valores por defecto.
3. `static/css/estilos.css`: arco activo engrosado, los demás atenuados, y en celular la dona centrada (la clase `capacidad__resumen` forzaba `flex-start`).
4. Banner «Invítame un café»: padding, tipografía y botón más bajos en escritorio y en celular; el ancho y el orden no cambian.
5. Neon: `backend/.env` apunta a la nueva URL (archivo ignorado por git). La migración se aplicó: `venta_detalle.garantia_fecha_fin`, `perfiles_financieros.dia_quincena_1/2` y `deducciones_fijas.id_deuda` existen; las 3 ventas siguen intactas.
6. `sw.js` en `olb-finanzas-v43`.

**Verificación:** `node --check` de `dona.js` sin errores; `pytest` en verde con **616 pruebas** (3 nuevas en `tests/test_dona_interactiva.py`); `generar_guia.py --verificar` sin problemas (100 archivos).

**Pendiente:** revisión visual de la dona en celular y del banner en 360/390/1280 px. La clave de Neon se compartió dos veces en el chat: conviene rotarla y actualizar `DATABASE_URL` en Render.

### 2026-11-20 — Deducción vinculada a la deuda que paga (ADR-56)

**Cambios realizados**
1. `modelos.py`, `core/base_datos.py`: `deducciones_fijas.id_deuda` con migración idempotente en SQLite (PRAGMA) y PostgreSQL (`IF NOT EXISTS`).
2. `servicios/deducciones_fijas.py`: validación de la deuda (propia, activa y mensual), valor tomado de la cuota, `listar_vigentes`, `vinculadas_activas` y `cuota_de_vinculadas`.
3. `servicios/quincenas.py`: solo cuentan las deducciones vigentes.
4. `servicios/capacidad.py`: la cuota vinculada sale de la cuota de deudas; los créditos vinculados no se pasan a cuota; la proyección saca el descuento de gastos constantes y deja la cuota en su calendario.
5. `servicios/ahorro.py` (`diagnostico`): misma regla que la dona. `disponible` = dona «Total libre».
6. `servicios/deudas.py` (`eliminar_deuda`): desvincula las deducciones en la sesión y la base.
7. `routers/presupuesto.py` y `templates/presupuesto/index.html`: selector «¿Es la cuota de una deuda que estás pagando?» en alta y edición; cada deducción vinculada muestra «faltan N cuota(s) · saldo $X» o «pagado». Al abrir la vista se aplican las cuotas vencidas.
8. `diccionario_datos.md` §9.3 y `sw.js` en `olb-finanzas-v42`.

**Verificación:** prueba de la migración sobre una copia de `finanzas.db` antigua (dos ejecuciones, sin error). `pytest` en verde con **613 pruebas** (8 nuevas en `tests/test_deduccion_vinculada.py`). En la primera versión de la prueba se detectó que el borrado no desvinculaba la deducción en la sesión; se corrigió en `eliminar_deuda`.

**Pendiente:** Neon (la migración de `deducciones_fijas` corre al arrancar, igual que las anteriores, cuando la URL sea válida); revisión visual del selector en 360/390 px.

### 2026-11-19 — Diagnóstico coherente con la dona y gráfica móvil legible

**Causa del desajuste:** el diagnóstico del mes sumaba el sueldo libre y los extras sin restar la cuota mensual de las deudas. La dona de capacidad sí la resta. La diferencia era exactamente la cuota de deudas ($433.000 en el caso reportado): el diagnóstico decía $3.302.280 y la dona, «Total libre» $2.869.280.

**Cambios realizados**
1. `servicios/ahorro.py` (`diagnostico`): descuenta la cuota mensual de deudas del saldo y la expone como `cuota_deudas`. Las deducciones fijas que son créditos no se descuentan dos veces (ya restan en la quincena). Ahora `disponible` coincide con el «Total libre» de la dona.
2. `templates/presupuesto/index.html`: línea «Ya descontadas las cuotas de deudas del mes» en el diagnóstico.
3. Gráfica base frente a optimizado: la etiqueta se divide en dos líneas (mes arriba, año abajo) y deja de encimarse en móvil.
4. `sw.js` en `olb-finanzas-v39`.

**Verificación:** `pytest` en verde con **605 pruebas** (1 nueva en `tests/test_diagnostico_coherente.py`). La gráfica móvil no se pudo revisar en navegador desde aquí; queda pendiente en 360/390 px.

### 2026-11-19 — Analítica con filtros, ventas por producto y CSV (Bloque 3, ADR-55)

**Cambios realizados**
1. `servicios/analitica.py` reescrito sobre líneas de venta. `Filtro` (año, mes, cliente y producto) lo comparten todas las tablas. Las funciones existentes conservan su firma y, sin filtro, dan los mismos resultados (las 13 pruebas previas pasan sin cambios).
2. Nueva tabla «Ventas por producto»: una fila por producto con No. de orden, cliente, categoría, producto, costo, total, saldo pendiente, abonos, ganancia y garantía (Activa / Vencida / Sin garantía, medida por producto).
3. `olb_byte/analitica.html`: filtros de año y mes, chips para quitarlos, clic en una fila (mes, cliente o producto) que activa o desactiva el filtro, y «Descargar CSV» en cada tabla.
4. `routers/olb_byte.py`: `GET /olb-byte/analitica` acepta `anio`, `mes`, `cliente` y `producto` como texto y descarta valores inválidos sin error. `GET /olb-byte/analitica/exportar/{tabla}.csv` devuelve el CSV con `;` y BOM, con la misma selección de la pantalla. Tabla desconocida: 404.
5. `modelos.py`, `comercial.py` y `core/base_datos.py`: `venta_detalle.garantia_fecha_fin`, guardada en cada venta nueva. La migración la rellena con la fecha de la orden en las líneas antiguas (en SQLite y en PostgreSQL).
6. `static/css/estilos.css`: estilos de filas enlazadas, filas activas y chips de filtro.
7. `sw.js` en `olb-finanzas-v38`.

**Decisiones**
- Saldo y abonos de una orden con varios productos se reparten en proporción al total de cada línea; la última línea absorbe el redondeo (ADR-55).
- El mes filtra las tablas de datos (VIP, alertas, costos, anual y ventas). La tabla mensual siempre muestra los doce meses y solo marca el elegido.
- El CSV sale de las mismas funciones que la pantalla: lo que se descarga es lo que se ve.

**Verificación:** `compileall` OK; `pytest` en verde con **604 pruebas** (15 nuevas en `tests/test_analitica_filtros.py`). `generar_guia.py --verificar` sin problemas.

**Pendiente:** la migración de `venta_detalle` sobre una copia de `finanzas.db` antigua y sobre Neon; revisión visual de la analítica en 360/390/1280 px.

### 2026-11-19 — Día de cada quincena según el usuario (Bloque 2, ADR-54)

**Cambios realizados**
1. `modelos.py` y `diccionario_datos.md`: `perfiles_financieros.dia_quincena_1` y `dia_quincena_2` (`SMALLINT`, `CHECK 1..31`). El modelo y el diccionario ya no dan por hecho el día 15 y el 30.
2. `core/base_datos.py`: migración idempotente. En SQLite se agregan las columnas y se rellenan con 15 y 30. En PostgreSQL (Neon, producción) `_migrar_dias_quincena_postgres` ejecuta `ADD COLUMN IF NOT EXISTS`, porque las migraciones de SQLite no corren allí.
3. `servicios/perfiles.py`: `parsear_dia_quincena` (solo dígitos, 1 a 31, mensaje en español), `validar_dias_quincena` (la quincena 2 debe ser posterior a la 1), `dias_quincena`, `etiquetas_quincena`. `guardar_perfil` recibe los días; sin ellos usa 15 y 30. En modalidad mensual no se tocan.
4. `routers/perfil.py` y `templates/perfil/index.html`: dos campos «Día de la quincena 1» y «Día de la quincena 2». Los rótulos de «¿En qué quincena…?» muestran el día escrito. `static/js/perfil.js` los actualiza al teclear.
5. `servicios/quincenas.py`: el panel de Mis Finanzas toma su etiqueta del perfil.
6. Metas (`presupuesto`), deducciones fijas, edición de deducciones y gastos (`gastos`): usan `etiquetas_quincena` del perfil en lugar de «día 15» y «día 30».
7. `sw.js` en `olb-finanzas-v37`.

**Decisiones**
- El día de la quincena 2 debe ser mayor que el de la quincena 1 (por ejemplo, 5 y 20). Así las etiquetas se leen en orden. Si un caso real necesita un cierre de mes entre quincenas, se revisa en otro bloque.
- Un día que no existe en el mes (30 en febrero) se usa como último día del mes. El valor guardado sigue siendo 30. En este bloque los días solo cambian etiquetas, porque ninguna pantalla calcula fechas por quincena; el cálculo de fechas de Trabajos Extras no se tocó (ver pendientes).

**Pendiente, fuera de este bloque**
- Trabajos Extras conserva sus rótulos «día 15» y «día 30» y sus fechas de pago. Esas fechas las digita cada contrato, así que se decide en un bloque aparte.

**Verificación:** `compileall` OK; `pytest` en verde con **589 pruebas** (46 nuevas en `tests/test_dias_quincena.py` y dos casos de `test_perfiles.py` actualizados para enviar los días). La migración sobre una base SQLite antigua y sobre Neon **no se ha ejecutado** todavía; queda como verificación manual antes de desplegar.

### 2026-11-19 — Colores de la dona: verde a favor, rojo en contra (Bloque 1)

**Cambios realizados**
1. `servicios/capacidad.py`: cada arco incluye `clase`. Gastos fijos y cuota de deudas son `valor-negativo`; base mínima y disponible para abonar son `valor-positivo`. El color del trazo no cambia.
2. `templates/finanzas/_capacidad.html`: las cifras de la leyenda y el porcentaje libre del centro usan verde o rojo según el signo. «Ingreso del mes» va en verde. Sirve para Gastos y Presupuesto y para Trabajos Extras, porque ambas vistas comparten la macro.
3. `servicios/comercial.py` (`segmentos_dona`): cartera por cobrar en verde y deuda con proveedor en rojo.
4. `templates/olb_byte/cartera.html`: la dona muestra el balance en el centro con su color (`balance_clase`, vía `clasificar_saldo`), y la leyenda usa los mismos colores. `routers/olb_byte.py` pasa `balance_texto` y `balance_clase`.
5. `static/css/estilos.css`: clase `.dona__centro-valor` para el balance dentro de la dona.
6. `static/js/sw.js` en `olb-finanzas-v36`.

**Verificación:** `compileall` OK, pruebas nuevas en `test_capacidad.py` (clases de arcos y verde/rojo en la vista) y en `test_cartera.py` (clases de la dona de cartera). `pytest` completo: **561 pruebas** en verde.

### 2026-11-19 — Base mínima de liquidez, deudas sin intereses y blindaje de formularios (SRS v1.8, ADR-53)

**Cambios realizados**
1. `servicios/capacidad.py`: constante `BASE_MINIMA_LIQUIDEZ = Decimal("300000")` y helper `repartir_libre()`. La dona pasa de tres a cuatro arcos («Gastos fijos», «Cuota de deudas», «Base mínima de liquidez», «Disponible para abonar»); si el libre no alcanza la base, solo se dibuja la base. Los porcentajes se cierran a 100,0 % ajustando el arco mayor.
2. `servicios/consejero.py`: reescrito sin intereses. Estrategia única `FLUJO_DE_CAJA`: si el excedente puede cancelar una deuda completa, ataca la de más cuotas por delante (12 meses antes que 5); si no, la de menor saldo. Solo trabaja con el remanente sobre la base mínima y, por debajo, muestra el mensaje de «base mínima de liquidez» invitando a crear una meta de emergencia.
3. `servicios/deudas.py`: se elimina `tasa_implicita()` y toda simulación de intereses. `validar_plan()` exige que `cuota × cuotas` reconstruya el total adeudado con tolerancia de $1 por cuota; la cuota abona capital completo y la última cierra el saldo. `modelos.py` deja de mapear `tasa_interes`.
4. `core/texto.py`: `parsear_porcentaje()` acepta «60», «60 %» y «60,5»; rechaza el punto decimal ambiguo con un mensaje en español. `perfiles.py` y `trabajos.py` lo usan. El perfil muestra y autocompleta «60 %» con coma decimal.
5. Blindaje de entradas: `main.py` registra un manejador global de `ValueError` que responde 400 con una página mínima (o JSON) en lugar de romper; `static/js/app.js` valida en el navegador los campos `inputmode` y `type="number"` antes de enviar. El abono de OLB_BYTE rechaza texto, cero, negativos y montos sobre el saldo con el saldo pendiente en el mensaje.
6. Metas: «Quincena de descuento» pasa a «Quincena donde aplicaremos los pagos»; el selector de modo de «Ambas quincenas» vive en su propia fila alineada; la lista de abonos muestra cinco filas y se desplaza dentro de una caja (`.abonos-scroll`). `sw.js` en `olb-finanzas-v35`.

**Verificación:** `python -m compileall app` sin errores, `pytest` en verde (559 pruebas) y `generar_guia.py --verificar` sin problemas.

### 2026-11-19 — Buscador y orden de «Órdenes registradas» (SRS v1.8, bloque 6)

**Cambios realizados**
1. `servicios/comercial.py`: `filtrar_ventas(ventas, consulta)` busca por No. de orden, cliente o fecha (dd-mm-aaaa, dd/mm/aaaa o aaaa-mm-dd), sin tildes ni mayúsculas.
2. `routers/olb_byte.py`: `GET /olb-byte?q=` filtra la lista; los totales del panel no cambian.
3. `templates/olb_byte/index.html`: cuadro de búsqueda con «Buscar» y «Ver todas»; mensaje cuando no hay coincidencias. Sirve igual en móvil y escritorio.
4. Orden: se mantiene el de número de orden descendente, que coincide con el orden de registro (la última orden registrada aparece primero).
5. Pruebas nuevas en `tests/test_buscador_ordenes.py` (6).

**Verificación:** `pytest` en verde (515). En Chromium a 390 px, la búsqueda «ana» muestra solo la orden de Ana Pérez.

### 2026-11-19 — Login con ondas, órdenes y pendientes en lista móvil con detalle (SRS v1.8, bloques 4, 5 y 7)

**Cambios realizados**
1. `templates/login.html` rediseñado: tarjeta con ondas SVG en la parte superior e inferior con los colores oficiales; orden de campos correo, contraseña, recuperación, ingresar, registrarse; ojo para mostrar la contraseña; botón de Google circular con el ícono oficial y la misma ruta OAuth.
2. `templates/olvide_contrasena.html` y ruta `/olvide-contrasena`: el enlace de recuperación ya no lleva a una página inexistente.
3. `templates/olb_byte/index.html` y `pendientes.html`: en móvil (≤ 640 px) la tabla se sustituye por filas compactas; cada fila abre un `<dialog>` centrado con el detalle y el botón «Volver». Las acciones de la orden se extrajeron a la macro `acciones_orden`, usada por la tabla y el detalle.
4. `static/js/app.js`: mostrar u ocultar contraseña y abrir o cerrar diálogos (`data-abrir-dialogo`, `data-cerrar-dialogo`).
5. Se corrigió la lista de cuentas demo, que mostraba puntos porque las cuentas son tuplas.
6. `sw.js` en `olb-finanzas-v27`. Pruebas nuevas en `tests/test_ui_login_movil.py` (4).

**Verificación:** `pytest` en verde (509). En Chromium a 390 px: la tabla queda oculta, la lista aparece, el detalle se abre y se cierra.

### 2026-11-19 — Factura: WhatsApp abre el chat del cliente y logos con registro de avisos

**Problemas reportados:** (1) al descargar, la imagen salía sin logos; (2) «Compartir por WhatsApp» quedaba en «Preparando…» y no abría nada.

**Diagnóstico:** en Chromium local la imagen sale con todos los logos (verificado). El botón esperaba la captura antes de abrir WhatsApp, y en el teléfono el permiso de compartir se pierde durante esa espera. Los logos sí están versionados en Git (`assets/`), así que la causa en Render no se pudo confirmar desde aquí.

**Cambios realizados**
1. `static/js/factura.js`: la imagen se prepara al cargar la página; «Compartir por WhatsApp» abre de inmediato `wa.me/57…` con el número del cliente, copia la imagen al portapapeles si el navegador lo permite y la descarga. Sin celular, avisa y no abre nada. Las imágenes se esperan con `decode()` antes de capturar.
2. `templates/olb_byte/factura.html`: atributo `data-sin-celular` cuando la orden no tiene celular.
3. `servicios/factura_pdf.py`: si un logo no existe, queda un aviso en el log (`app.factura`) para revisarlo en Render.
4. `sw.js` en `olb-finanzas-v31`.
5. `tests/test_factura_whatsapp.py` (3 pruebas).

**Verificación:** en Chromium a 390 px, la descarga produce PNG completo con logos y el chat abre `api.whatsapp.com/send?phone=573163826366`. `pytest` en verde.

**Confirmado por el propietario:** la descarga sale con todos los logos. Queda pendiente solo la prueba del botón de WhatsApp en un celular real.

### 2026-11-19 — PostgreSQL en Neon y despliegue en Render (ADR-52)

**Decisión:** la base de producción es PostgreSQL en Neon, con `psycopg` 3 (`psycopg[binary]`, nueva dependencia justificada aquí). SQLite queda para desarrollo y pruebas. El destino de despliegue sigue siendo Render (`misfinanzas-odbc.onrender.com`); se evaluó Koyeb y se descartó porque el proyecto ya está en Render. No se añade Alembic todavía: el esquema lo crea `create_all` y las migraciones `_migrar_*` siguen siendo solo para SQLite.

**Cambios realizados**
1. `requirements.txt`: `psycopg[binary]>=3.2,<4.0`.
2. `backend/.env` (local, ignorado por Git): `DATABASE_URL` de Neon. `base_datos.py` lo carga con `setdefault`, así que las variables del entorno y las pruebas mandan.
3. `base_datos.py`: `_url_con_driver` convierte `postgresql://` a `postgresql+psycopg://`; con PostgreSQL `pool_pre_ping=True`, `pool_recycle=300` y `prepare_threshold=None` (el pooler de Neon no admite sentencias preparadas del servidor). Las funciones `PRAGMA` siguen protegidas por `_conexion_sqlite`.
4. `scripts/migrar_a_neon.py`: crea el esquema en Neon y copia `datos/finanzas.db` tabla por tabla en orden de claves foráneas, con `ON CONFLICT DO NOTHING`. Neutraliza las cuentas demo copiadas (contraseña aleatoria). Todo en una transacción.
5. `usuarios.sembrar_demostracion`: no siembra cuentas demo con `ENTORNO=produccion`. Antes, una base vacía en producción recibía cuentas con contraseñas conocidas.
6. `/salud`: consulta la base (`SELECT 1`) y responde 200 o 503.
7. `tests/test_base_datos_postgres.py` (4 pruebas): driver, pruebas aisladas en SQLite, `/salud` 200 y 503.
8. `DESPLIEGUE.md` §11: variables y configuración del servicio en Render (Root Directory `backend`, Start Command con `$PORT`, Health Check `/salud`).

**Verificación**
- `migrar_a_neon.py` ejecutado: copió 24 tablas. Conteos locales y de Neon coinciden (usuarios 2, gastos 26, ventas 2, auditoría 103, clientes 1, abonos 2, venta_detalle 2).
- Segunda ejecución: 0 filas nuevas (idempotente).
- `/salud` contra Neon: 200, `base_datos: ok`; PostgreSQL 18.
- `pytest` en verde con base temporal de SQLite (541 pruebas).

**Pendiente:** rotar la contraseña de Neon, porque se compartió en el chat. Luego actualizar `DATABASE_URL` en Render y en `backend/.env`.

### 2026-11-19 — Avatar híbrido: foto de Google o iniciales (SRS v1.8)

**Decisión:** el avatar guarda solo la URL de la foto de Google en `usuarios.avatar_url`; nunca se almacenan archivos. Sin foto (registro con contraseña o foto inválida) se dibuja un círculo con las dos iniciales del alias y el degradado de la paleta. La URL se valida: HTTPS y `*.googleusercontent.com`, hasta 500 caracteres.

**Cambios realizados**
1. `modelos.py` y `diccionario_datos.md` §1: columna `avatar_url VARCHAR(500)` nula.
2. `core/base_datos.py`: `_migrar_columnas_usuarios`, idempotente, llamada desde `inicializar_base_datos`.
3. `dependencias.py`: `UsuarioSesion.avatar_url`, leído de la base en cada petición.
4. `servicios/usuarios.py`: `url_avatar_valida` y `actualizar_avatar`.
5. `routers/auth.py`: el callback de Google guarda `picture` en cada inicio de sesión.
6. `core/middleware.py`: `img-src 'self' data: https://*.googleusercontent.com`.
7. `templates/componentes/avatar.html` (macro nueva) usada en `base.html` (compacto) y `perfil/index.html` (destacado). Si la foto falla, `onerror` oculta la imagen y muestra las iniciales. `routers/vistas.py`: `iniciales_alias` como filtro.
8. `static/css/estilos.css`: clases `.avatar*`. `sw.js` en `olb-finanzas-v30`.
9. `tests/test_avatar.py` (9 pruebas): iniciales, validación de URL, captura desde Google, respaldo, CSP y migración idempotente.

**Verificación:** `pytest` en verde (537). Migración ejecutada dos veces sobre una copia de `backend/datos/finanzas.db`: agrega la columna y conserva las 2 cuentas. `generar_guia.py --verificar` sin problemas (99 archivos).

**Pendiente:** revisión visual en navegador con una cuenta real de Google (la foto depende de Google y no se puede simular en pruebas).

### 2026-11-19 — Apoyo voluntario «invítame un café» (solo Colombia)

**Decisión:** un botón discreto en el pie y un modal `<dialog>` para `USER_FINANZAS`, con Nequi y Bre-B y monto sugerido de $6.000 COP. Sin librerías ni JavaScript nuevo: lo manejan `data-abrir-dialogo`, `data-cerrar-dialogo` y `data-copiar` de `app.js`. Respeta la CSP (`script-src 'self'`, logos en `img-src data:`).

**Cambios realizados**
1. `core/config.py`: sin datos de pago. Se eliminaron `NEQUI_CAFE` y `LLAVE_BRE_B_CAFE`: el teléfono no debe quedar expuesto.
2. `routers/vistas.py`: `contexto_base` entrega `cafe` con monto y QR de Bre-B en data URI.
3. `servicios/factura_pdf.py`: nueva clave `bre_b_qr` apuntando a `assets/Logo De Bre-B.png` (el logo de Bre-B de la factura no cambia).
4. `templates/base.html`: disparador en el pie y `<dialog id="dialogo-cafe">` con solo el QR de Bre-B.
5. `static/css/estilos.css`: clases `cafe-*` con la paleta oficial; logos y QR sobre fondo blanco.
6. `static/js/sw.js` en `olb-finanzas-v29`.
7. `tests/test_cafe.py` (3 pruebas): visibilidad por rol, QR incrustado y ausencia del teléfono y de botones de copiado en el modal.
8. Nota: la factura sigue mostrando el número de Nequi en sus medios de pago; no se cambió porque es un documento de cobro.

**Verificación:** `pytest` en verde y `generar_guia.py --verificar` sin problemas. Pendiente: revisión visual en celular y escritorio.

### 2026-11-19 — Recuperación de contraseña por correo (SRS v1.8, bloque 8, ADR-51)

**Decisión:** la recuperación usa solo correo (SMTP estándar con `smtplib`) y tokens firmados de 15 minutos con propósito `recuperacion` y una huella de la contraseña vigente. Sin tabla nueva. Así un enlace no abre sesión y no se reutiliza tras cambiar la contraseña. La respuesta de `POST /olvide-contrasena` es siempre la misma para no revelar cuentas.

**Cambios realizados**
1. `core/seguridad.py`: `decodificar_token` rechaza claim `proposito`; nuevas `crear_token_recuperacion` y `decodificar_token_recuperacion`.
2. `core/config.py`: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `SMTP_FROM` y `APP_URL`.
3. `servicios/correo.py` (nuevo): `enviar_correo`. Sin SMTP en desarrollo escribe el contenido en el log; en producción solo registra el fallo.
4. `servicios/usuarios.py`: `huella_contrasena` y `restablecer_contrasena`.
5. `routers/auth.py`: `GET/POST /olvide-contrasena` y `GET/POST /restablecer-contrasena`; auditoría `RECUPERACION_SOLICITADA` y `CONTRASENA_RESTABLECIDA`; `/login?restablecida=1` muestra el aviso.
6. Plantillas `olvide_contrasena.html` y `restablecer_contrasena.html`; aviso de éxito en `login.html`.
7. `scripts/generar_guia.py` lee con `utf-8-sig` (tolera el BOM de Windows). `Guia.md` actualizada: tabla de roles, fichas nuevas y fichas de archivos eliminados retiradas. `--verificar` sin problemas (98 archivos).
8. `sw.js` ya en `olb-finanzas-v27`, que cubre el CSS y JS cambiados desde el último commit.

**Pendiente de configuración en Render:** `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `SMTP_FROM` y `APP_URL`. Sin ellas, en producción el correo no sale.

**Verificación:** `pytest` en verde (525, incluidas 10 en `tests/test_recuperacion.py`).

### 2026-11-19 — Factura y recibo como PNG en el navegador; sin Playwright en el servidor (ADR-50)

**Decisión:** la imagen de la factura y del recibo se genera en el navegador con `html-to-image` (local, en `static/js/vendor/`). Se elimina Playwright y Chromium del servidor, que consumían mucha RAM en Render gratuito. ADR-50 reemplaza a ADR-36 y ADR-41 en lo relativo al PDF.

**Cambios realizados**
1. `servicios/factura_pdf.py` y `servicios/recibo_imagen.py`: sin Playwright; los archivos se llaman `.png`.
2. Rutas nuevas: `GET /olb-byte/factura/{id}/hoja` y `GET /olb-byte/recibos/{id}/hoja` (solo HTML). Se eliminan `/factura/{id}/pdf` y `/recibos/{id}/imagen`.
3. `templates/olb_byte/_fragmento_factura.html` y `_fragmento_recibo.html` (nuevas); se eliminan `factura_pdf.html` y `recibo_imagen.html`.
4. `static/js/factura.js` reescrito: monta la hoja fuera de la vista, la convierte en PNG con `pixelRatio: 2`, comparte con `navigator.share` o copia al portapapeles y descarga.
5. `templates/olb_byte/factura.html`, `recibo.html` e `index.html`: botones «Descargar imagen» y «Compartir por WhatsApp»; se quita la vista previa PDF.
6. `requirements.txt` sin `playwright`; `DESPLIEGUE.md` §13 reescrita.
7. `sw.js` en `olb-finanzas-v26` con la librería en la caché.
8. Pruebas: `tests/test_factura_imagen.py` reemplaza a `test_factura_pdf.py` y `test_recibo_imagen.py`.

**Verificación:** `pytest` en verde (505). En Chromium con base temporal: la factura se descarga como PNG de 1700 × 2630 px, y el recibo como PNG de 936 × 1040 px, ambos legibles.

**Pendiente:** resuelto en la tarea de recuperación de contraseña (la guía ya no tiene fichas de archivos eliminados).

### 2026-11-19 — Administrador OLB_BYTE para los correos del propietario (ADR-49)

**Decisión:** `CORREOS_ADMIN_OLB` (por defecto, los dos correos del propietario). El rol `ADMIN_OLB` se asigna solo cuando la cuenta entra con Google y Google confirma el correo. No se asigna por registro con contraseña, porque cualquiera podría registrar un correo ajeno. Para otras cuentas, el rol se cambia desde «Administración de cuentas».

**Cambios realizados**
1. `core/config.py`: `correos_admin_olb` desde `CORREOS_ADMIN_OLB`.
2. `routers/auth.py`: en el inicio con Google, si el correo está en la lista, se asigna `ADMIN_OLB`.
3. `tests/test_acceso_google_y_olb.py`: prueba del ascenso con Google.

**Verificación:** `pytest` en verde (522 pruebas).

**Pendiente:** las dos cuentas no existen aún en la base local. Deben entrar con Google en el servidor para recibir el rol. El registro con contraseña para esos correos sigue abierto; conviene bloquearlo.

### 2026-11-19 — Chancucos (Atajos de Pago) para todos los usuarios (SRS v1.8)

**Cambios realizados**
1. `routers/chancucos.py`: las cuatro rutas usan `obtener_usuario_actual`; ya no exigen administrador.
2. `routers/finanzas.py`: el bloque de atajos del resumen se entrega a todos los usuarios.
3. `templates/finanzas/_subnav.html`: el enlace «Configurar Atajos de Pago» se muestra a todos.
4. `servicios/chancucos.py`: cada usuario ve y gestiona solo sus atajos (`Chancuco.id_usuario`).
5. Pruebas nuevas en `tests/test_chancucos_publicos.py` (3).

**Verificación:** `pytest` en verde (521 pruebas).

### 2026-11-18 — Acceso por correo a OLB_BYTE e inicio con Gmail (ADR-48)

**Decisión:** OLB_BYTE solo para los correos de `CORREOS_OLB_BYTE` (por defecto, dos cuentas de Gmail). La tarjeta del panel y las rutas `/olb-byte` usan `exigir_olb_byte`, no el rol. El inicio con Google usa OAuth 2.0 con la biblioteca estándar (`urllib`), sin dependencias nuevas, y crea la cuenta como `USER_FINANZAS`.

**Cambios realizados**
1. `core/config.py`: `correos_olb_byte`, `google_client_id`, `google_client_secret`, `google_redirect_uri` desde el entorno.
2. `dependencias.py`: `UsuarioSesion.puede_ver_olb_byte` y `exigir_olb_byte` (403 si el correo no está autorizado).
3. `routers/olb_byte.py`: las 18 comprobaciones pasan a `exigir_olb_byte`.
4. `routers/vistas.py`: la tarjeta se filtra por correo (`solo_autorizados`).
5. `servicios/acceso_google.py` (nuevo) y `routers/auth.py`: `/login/google` y `/login/google/callback` con cookie de `state`.
6. `templates/login.html`: botón «Continuar con Gmail» solo si hay credenciales.

**Verificación:** `pytest` en verde (518 pruebas, 8 nuevas en `tests/test_acceso_google_y_olb.py`).

**Pendiente:** `Guia.md` no incluye aún las fichas del servicio nuevo; el verificador sigue bloqueado por el BOM de archivos de OLB_BYTE.

### 2026-11-18 — Órdenes con iconos, ventanas centradas y campos de quincena iguales (SRS v1.8, ajuste 7)

**Cambios realizados**
1. OLB_BYTE, acciones de cada orden: iconos (documento para factura, WhatsApp y papelera para anular) en una fila de tres columnas iguales, también en celular. Cada icono tiene `aria-label` y `title`.
2. Anular y Devolver usan `edicion-gasto--modal` y el formulario `edicion-gasto__formulario`: en celular se abren centrados sobre fondo oscuro.
3. Trabajos Extras: el selector de la quincena y el campo de valor miden 44 px de alto en la misma fila.
4. `sw.js` en `olb-finanzas-v24`.

**Límite:** el calendario de fecha lo dibuja el sistema del celular; la ventana del formulario que lo contiene sí queda centrada.

**Verificación:** `pytest` en verde (510). En celular: tres acciones de 91 × 38 px en una fila; Anular centrado (centro en 195 px de 390).

### 2026-11-18 — Proyección con créditos, órdenes alineadas y medios de pago (SRS v1.8, ajuste 6)

**Cambios realizados**
1. `servicios/capacidad.proyeccion_capacidad` recibe `creditos`: cada mes de la proyección suma la cuota de créditos de deducción (no tienen fecha de fin).
2. Órdenes registradas (OLB_BYTE): Factura, WhatsApp y Anular comparten alto, ancho de columna y grosor (`.acciones-orden` en tres columnas, `min-width: 0` para vencer el mínimo de `.boton`); la fecha se muestra como dd-mm-aaaa.
3. Factura: el título «MEDIOS DE PAGO» queda encima de los recuadros, sin taparlos.
4. `sw.js` en `olb-finanzas-v21`.

**Verificación:** `pytest` en verde (510). En celular, los tres botones miden 91 × 38 px y la fecha sale corta.

### 2026-11-18 — Dona de Gastos y Presupuesto: créditos como deuda y libre desglosado (SRS v1.8, ajuste 5)

**Cambios realizados**
1. `servicios/capacidad.es_credito`: una deducción fija cuya descripción contiene «crédito» o «créditos» (sin tildes ni mayúsculas) se suma a la cuota de deudas y sale de los gastos fijos. Por ejemplo, una libranza.
2. La dona muestra el libre del salario y el libre de trabajos extras, con su valor y porcentaje, y el total libre. Los trabajos entran por su valor de pago y salen con sus gastos fijos.
3. `sw.js` en `olb-finanzas-v20`: el service worker servía el CSS de la factura desde caché, por eso el recuadro de medios de pago se veía sin centrar aunque el código ya estaba centrado.

**Limitación:** la proyección a doce meses solo cuenta las deudas registradas en «Registro y Detalles de deudas»; los créditos de deducción no se proyectan.

**Verificación:** `pytest` en verde (510 pruebas). En la aplicación, la dona muestra libre del salario $2.572.280 + libre de trabajos extras $1.429.000 = libre total $4.001.280.

### 2026-11-18 — Trabajos Extras: formulario alineado, medios de pago centrados (SRS v1.8, ajuste 4)

**Cambios realizados**
1. Formulario de Trabajos Extras en rejilla de dos columnas (una en celular), con los campos de quincena en filas propias y sin textos de ayuda dentro de cada campo, para que todo quede alineado.
2. `app.js`: cada campo quincenal se muestra según frecuencia y opción de porcentaje (corrige que el campo de la quincena se mostrara en mensual).
3. Factura: el título «MEDIOS DE PAGO» centrado; el texto de las tarjetas dice «Recibimos todas las tarjetas».

**Verificación:** `pytest` en verde (507). Capturas en escritorio y celular del formulario quincenal y de los medios de pago.

### 2026-11-18 — Trabajos Extras: dona solo de trabajos y medios de pago en recuadros (SRS v1.8, ajuste 3)

**Cambios realizados**
1. La dona de Trabajos Extras usa `servicios/capacidad.capacidad_trabajos`: ingreso = pagos cobrados de trabajos; gastos = gastos fijos de trabajos. No cuenta sueldo, quincenas ni deudas. La macro `panel_capacidad` acepta `solo_trabajos=True` y oculta semáforo y deudas.
2. Factura: los cuatro medios de pago (Bre-B, Nequi, datáfono y Mastercard/Visa) tienen el mismo recuadro cerrado por ambos lados; la caja exterior ya no dibuja marco.

3. Regla única de saldo: el saldo, la dona y el diagnóstico usan el valor del pago (cobrado o no) menos los gastos fijos del trabajo. Un pago saltado con la × vale cero (ya no se espera).

**Verificación:** `pytest` en verde (507 pruebas). En la aplicación, la tarjeta, el resultado del periodo y la dona muestran el mismo saldo.

### 2026-11-18 — Trabajos Extras: fechas de pago, resumen por contrato y medios de pago (SRS v1.8, ajuste 2)

**Cambios realizados**
1. El formulario muestra los campos de quincena (conoce porcentaje, porcentajes, quincena y valor) solo con frecuencia quincenal. Están ocultos desde el servidor; el JavaScript los muestra al elegir quincenal.
2. «Fecha del primer pago» pasa a «Fecha de pago»: mensual escoge una fecha; quincenal escoge dos (quincena 1 y quincena 2). Columna nueva `fecha_pago_quincena_2` con migración idempotente; los contratos anteriores conservan los días 15 y 30.
3. «Pagos de noviembre» muestra por contrato el cuadro «Resultado del periodo» (mismas clases que Mis Finanzas): mes, saldo para el bolsillo (valor del pago menos gastos fijos), total de ingreso y total de gastos fijos.
4. Factura: eslogan justo debajo del logo; medios de pago en cuatro módulos centrados (Bre-B, Nequi, datáfono y Mastercard/Visa).
5. `sw.js` en `olb-finanzas-v19` para que el navegador descargue los CSS y JS nuevos.

**Pendiente de decisión:** el cuadro «Resultado del periodo» calcula el saldo como valor del pago menos gastos fijos. El disponible que suma al diagnóstico y la tarjeta superior usan lo cobrado menos los gastos fijos, así que un pago sin cobrar resta gastos. Hay que alinear las dos reglas.

**Verificación:** `pytest` en verde (505 pruebas). Capturas en la aplicación principal de la factura y de Trabajos Extras.

### 2026-11-18 — Trabajos Extras: quincenas propias, gastos fijos aislados y factura (SRS v1.8)

**Cambios realizados**
1. Los gastos fijos de un trabajo se guardan con `id_trabajo` y otra categoría; no aparecen en las quincenas ni en los totales de Mis Finanzas (`gastos.listar_gastos` ya los excluye). Ruta `POST /trabajos-extras/{id}/gastos` (`agregar_gasto_trabajo`).
2. Cada contrato muestra sus periodos: mensual «Pago mensual»; quincenal «Quincena 1» y «Quincena 2». Cada periodo tiene su pago, sus gastos fijos y el disponible (cobrado − gastos fijos). Ese disponible suma al diagnóstico de Gastos y Presupuesto.
3. Formulario: `valor del pago` es el total del mes. Mensual pide solo fechas. Quincenal pregunta si conoce los porcentajes: si sí, se escriben ambos (suman 100 %); si no, se escribe el valor de una quincena y el sistema calcula la otra y sus porcentajes. Reemplaza el reparto anterior contra el sueldo (ADR-47).
4. Factura: medios de pago Bre-B, Nequi y datáfono con Mastercard y Visa en un solo recuadro; BBVA retirado; eslogan junto al logo; PDF a escala 0,72 para mantener una hoja.
5. Recibo de abono: el botón copia la imagen PNG al portapapeles cuando el navegador no puede compartir archivos (PC), para pegarla en WhatsApp Web.
6. «← Volver» en Configurar Atajos de Pago y en el Historial.

**Verificación:** `pytest` en verde (504 pruebas). En Chromium con base temporal: formulario que cambia con la frecuencia y el porcentaje, tablas por quincena sin desborde a 390 px, regresos presentes, factura sin BBVA.

**Pendiente:** la vista previa y el PDF necesitan Chromium instalado en el servidor (DESPLIEGUE §13). Revisar la factura en un celular real.

### 2026-11-18 — OLB_BYTE: logo sin recuadro, logo exacto y PDF/impresión (puntos 4 y 5)

**Cambios realizados**
1. `servicios/factura_pdf.py` — el logo se busca por el nombre exacto `Nuevo Logo.png`; el patrón `Nuevo Logo*` tomaba `Nuevo Logo2.png` (1,4 MB).
2. `static/css/factura-olb.css` — `.logo-ob-caja` sin fondo blanco, relleno, esquinas ni sombra: el PNG ya es transparente.
3. `static/js/sw.js` — caché `olb-finanzas-v18`. El service worker sirve CSS y JS desde caché primero; sin subir la versión, el navegador seguía mostrando el recuadro anterior.
4. `DESPLIEGUE.md` §13 — bloque de instalación de Chromium corregido (estaba roto) y comando `playwright install --with-deps chromium` para el paso de compilación del hosting.
5. `tests/test_factura_pdf.py` — prueba de regresión del logo.

**Causa del PDF «no pudo generar»:** en el servidor publicado no está instalado el navegador de Playwright; el endpoint responde 503. En local el PDF se genera (una hoja Carta, logo transparente). Requiere ejecutar el comando de §13 en el servidor.

**Verificación:** `pytest` en verde (499 pruebas). En Chromium con base temporal: logo cargado desde `Nuevo Logo.png` (612 px) sin caja; vista de impresión con la factura completa; PDF 200 en una hoja.

**Pendiente:** confirmar en el hosting que el build instala Chromium y revisar el botón Imprimir en un celular real.

### 2026-11-18 — Botones de vuelta, Trabajos Extras por frecuencia y proyección retirada

**Cambios realizados**
1. Botón «← Volver» (mismo patrón que OLB_BYTE) en Mis Finanzas y Registro y Detalles de deudas y Trabajos Extras (al inicio) y en Gastos y Presupuesto (a Mis Finanzas).
2. Se retira la tabla «Proyección a 12 meses» de la capacidad (Gastos y Presupuesto y Trabajos Extras); la dona y el semáforo se conservan.
3. Trabajos Extras: aviso «Ten en cuenta» sobre el valor por pago al registrar.
4. Frecuencia mensual: una tabla «Mes completo». Quincenal: tablas «Quincena 1» y «Quincena 2», cada una con su porcentaje del sueldo y el formulario «Gasto fijo – Categoría – Valor» (crea el gasto en Mis Finanzas, `origen=trabajos`).
5. Quincenal: se escribe el valor de una quincena; la otra es sueldo menos esa cantidad (`servicios/trabajos.reparto_quincenal`). Columnas `valor_quincena_1` y `valor_quincena_2` con migración idempotente.

**Fuera de alcance (módulo OLB_BYTE, no tocado):** logo «Nuevo Logo.png» con recuadro y descarga de PDF/WhatsApp.

**Verificación:** `pytest` en verde (498 pruebas, incluidas las nuevas de reparto, tablas por frecuencia y botones de vuelta).

### 2026-11-18 — Ajuste móvil: la edición de gastos se abre como ventana centrada (ADR-30)

**Contexto:** en el celular el lápiz de cada gasto queda al final de la fila y el
formulario de edición (`position: absolute; right: 0`) se salía de la pantalla:
aparecía pegado a la derecha y cortado.

**Cambios realizados**
1. `templates/finanzas/_gasto_fijo.html` y `templates/presupuesto/index.html` — el `<details>` de edición lleva la clase `edicion-gasto--modal`.
2. `static/css/estilos.css` — a 640 px o menos el formulario pasa a `position: fixed` centrado (`translate(-50%, -50%)`), con ancho `min(340px, 100vw - 32px)` y alto máximo `100vh - 48px` con scroll propio; el `<details>` dibuja un fondo oscuro con `::before`, la página no se desplaza (`body:has(...)`) y una fila de pago saltado recupera opacidad plena mientras se edita. En escritorio se conserva el desplegable anclado al lápiz.
3. `static/js/app.js` — tocar el fondo o pulsar Escape cierra la ventana y descarta lo escrito, igual que «Cancelar» (ayudante `cerrarEdicion`).
4. `static/js/sw.js` — caché `olb-finanzas-v17`.
5. `tests/test_gastos_checks.py` — las dos pruebas del lápiz comprueban la clase `edicion-gasto--modal`.

**Verificación**
- Chromium real con base temporal y sesión de administrador: a 360 y 390 px la ventana queda `fixed`, centrada y completa dentro de la vista (328 y 340 px de ancho, sin desborde interno); a 768 y 1280 px sigue el desplegable absoluto. El fondo cubre la vista y se cierra al tocarlo y con Escape.
- `pytest` de los módulos tocados (99 pruebas: gastos, quincenas, capacidad, consejero, trabajos, finanzas y presupuesto) en verde.


### 2026-11-18 — Ajustes de validación 3: pago al vender, cobro, WhatsApp con PDF, barras y responsive (ADR-43)

**Cambios realizados**
1. Forma de pago y anticipo en el formulario de venta; `registrar_venta` con `PagoInicial` en la misma transacción.
2. Página de cobro con dos opciones; abono con retorno a la página de cobro si falla.
3. Pendientes con una acción por cliente («Añadir pago o gestionar cobro») y tabla compacta.
4. Órdenes sin ganancia ni saldo; acciones Factura, WhatsApp y Anular en una fila; WhatsApp envía el PDF.
5. Formulario: categoría antes del nombre, «Guardar» que bloquea el panel y «+ Agregar otro producto» y «Registrar venta» del mismo tamaño.
6. Se retira «Nuevo cliente»; `/olb-byte/clientes` ya no existe.
7. Cartera: barras horizontales del balance con la misma información de texto.
8. Submenú de OLB_BYTE: se corrige el borde cortado al pasar el ratón.
9. Contactos: en PC, guardar el número como tarjeta de contacto (.vcf); con la API del navegador, buscar en la libreta.
10. `Guia.md` §10: cómo personalizar la factura (datos, colores, logos y medios de pago).

**Verificación:** `pytest` en verde (453 pruebas). Recorrido en Chromium con 35 comprobaciones en verde, incluidas la alineación de botones, el bloqueo del panel, el desbordamiento en escritorio y celular en las cinco vistas, y el borde del submenú. `generar_guia.py --verificar` solo marca las dos plantillas heredadas de SRS v1.7.

### 2026-11-18 — Ajustes de validación del usuario: contactos, submenú, formulario v2 y categoría (ADR-42)

**Cambios realizados**
1. Botón «Buscar en Contactos»: se oculta de verdad (regla global `[hidden]`); si no hay API se muestra una nota con las condiciones.
2. Submenú de OLB_BYTE (`templates/olb_byte/_subnav.html`) arriba en Ventas, Pendientes, Cartera, Garantías y Analítica; se quitaron los botones de «Órdenes registradas» y «Volver al panel».
3. Formulario de venta v2: panel de producto con subtotal, tabla de detalle con Eliminar y Actualizar, cuadro de edición con Actualizar y Cancelar horizontales; `static/js/olb_byte.js` reescrito.
4. `referencia` → `categoria` en `venta_detalle`, LineaVenta, factura y ranking; migración `_renombrar_referencia_a_categoria` y diccionario §10.4.
5. Celular: tabla de detalle y de órdenes como tarjetas, sin `min-width`; encabezado compacto.
6. Página principal: `seccion = 'ventas'` para marcar la pestaña activa.

**Verificación:** `pytest` en verde (434 pruebas). Recorrido en Chromium con la app levantada: 19 comprobaciones en verde, incluido el celular sin desplazamiento horizontal. `generar_guia.py --verificar` solo marca las dos plantillas heredadas de SRS v1.7.

### 2026-11-18 — SRS OLB_BYTE v1.0, Fase 7: factura PDF con Playwright

**Cambios realizados**
1. `servicios/factura_pdf.py` (nuevo) — datos de la factura, logos como data URI, nombre de archivo y `generar_pdf` con Chromium (ADR-41).
2. `templates/olb_byte/factura_pdf.html` (nuevo) — documento de una página Carta con la paleta del SRS, tabla cebra de diez filas, medios de pago y pie institucional.
3. `routers/olb_byte.py` — `ver_factura_pdf` (GET `/olb-byte/factura/{id}/pdf?descargar=0|1`) con respuestas 404, 422 (más de diez productos) y 503 (sin Chromium).
4. `templates/olb_byte/factura.html` y `static/js/factura.js` — vista previa en diálogo, descarga, compartir con Web Share API y respaldo a WhatsApp.
5. `requirements.txt` — `playwright>=1.45`; `DESPLIEGUE.md` §13 con la instalación de Chromium.
6. `static/js/sw.js` — `olb-finanzas-v15` con `factura.js`.
7. `tests/test_factura_pdf.py` (nuevo, 14 pruebas, dos con Chromium real).

**Verificación:** `pytest` en verde (425 pruebas). Se generó una factura de muestra y se revisó la imagen: una página, medios de pago en una fila tras ajustar la columna.

### 2026-11-17 — SRS OLB_BYTE v1.0, Fase 6: analítica, clientes VIP y alertas de costo

**Cambios realizados**
1. `servicios/analitica.py` (nuevo) — `reporte_mensual`, `reporte_anual`, `ranking_vip`, `alertas_costos`, `anios_con_ventas` (ADR-40).
2. `routers/olb_byte.py` — `ver_analitica` (GET `/olb-byte/analitica?anio=`).
3. `templates/olb_byte/analitica.html` (nuevo) y `static/css/estilos.css` (barra de ingresos mensual).
4. `templates/olb_byte/index.html` — enlace «Analítica» en el panel.
5. `tests/test_analitica.py` (nuevo, 13 pruebas).

**Corrección en pruebas:** tres expectativas tenían error de cálculo (variación mensual, variación anual y orden del ranking VIP con empate). El código era correcto; se corrigieron las pruebas.

**Verificación:** `pytest` en verde (411 pruebas). `generar_guia.py --verificar` solo marca las dos plantillas heredadas de SRS v1.7, que siguen pendientes de ficha.

### 2026-11-17 — SRS OLB_BYTE v1.0, Fase 5: garantías en trámite y ranking de fallas

**Cambios realizados**
1. `templates/olb_byte/garantias.html` (nuevo) — formulario de reclamo, ranking de fallas, lista de reclamos con vigencia y avance de trámite.
2. `servicios/comercial.py` — `opciones_garantia`, `registrar_garantia`, `actualizar_estado_garantia`, `listar_garantias`, `garantia_vigente_al_reclamo` y `ranking_fallas` (ADR-39).
3. `routers/olb_byte.py` — `ver_garantias` (GET `/olb-byte/garantias`), `registrar_garantia` (POST) y `actualizar_garantia` (POST `/olb-byte/garantias/{id}/estado`), con auditoría.
4. `templates/olb_byte/index.html` — enlace «Garantías y fallas» en el panel.
5. `tests/test_garantias.py` (nuevo, 14 pruebas).

**Corrección en pruebas:** una prueba comparaba dos estados sobre el mismo objeto en memoria; ahora revisa el estado intermedio antes de la segunda actualización.

**Verificación:** `pytest` en verde (399 pruebas). `generar_guia.py --verificar` solo marca las dos plantillas heredadas de SRS v1.7; la ficha de `garantias.html` ya está en `Guia.md`.

### 2026-11-17 — SRS OLB_BYTE v1.0, Fase 4: cartera, liquidez y deuda con proveedor

**Cambios realizados**
1. `templates/olb_byte/cartera.html` (nuevo) — tabla de balance (RF-09), dona SVG (RF-11), formulario de pago al proveedor (RF-08) y libro de movimientos.
2. `servicios/comercial.py` — `clasificar_saldo` (RF-10), `tabla_balance` y `segmentos_dona`.
3. `routers/olb_byte.py` — rutas `ver_cartera` (GET `/olb-byte/cartera`) y `registrar_abono_proveedor` (POST `/olb-byte/proveedor/abonos`), con auditoría `ABONO_PROVEEDOR`.
4. `static/css/estilos.css` — estilos de la dona; enlace desde el panel principal.
5. `tests/test_cartera.py` (nuevo, 10 pruebas).

**Verificación:** `pytest` en verde (385 pruebas). `generar_guia.py --verificar` solo marca las dos plantillas de SRS v1.7 ya conocidas.

### 2026-11-17 — SRS OLB_BYTE v1.0, Fase 3: pendientes de pago y recibos

**Cambios realizados**
1. `templates/olb_byte/pendientes.html` (nuevo) — vista filtrada de RF-06 con búsqueda, abono con fecha y hora, cobro por WhatsApp y acceso al último recibo.
2. `templates/olb_byte/recibo.html` (nuevo) — recibo compacto de RF-07 con monto, medio, fecha y hora, desglose e insignia de saldo total; botones de WhatsApp, impresión y regreso.
3. `routers/olb_byte.py` — rutas `ver_pendientes` y `ver_recibo`; el abono redirige a su recibo y, si falla, vuelve a pendientes conservando el filtro. El panel principal enlaza a pendientes y ya no muestra la cartera.
4. `servicios/comercial.py` — `ahora_tienda()` para fijar todas las fechas en hora de Colombia (ADR-37); `buscar_cartera`, `abonos_de_venta`, `obtener_abono` y `enlace_whatsapp_recibo`.
5. `static/css/estilos.css` — estilos del recibo y de la insignia de saldo total; clase `no-imprimir` para la impresión.
6. `tests/test_cobros_vistas.py` (nuevo, 13 pruebas).

**Verificación:** `pytest` en verde (374 pruebas). `generar_guia.py --verificar` solo marca las dos plantillas de SRS v1.7 ya conocidas.

### 2026-11-17 — SRS OLB_BYTE v1.0, Fase 2: formulario de venta multi-producto y cobros

**Cambios realizados**
1. `templates/olb_byte/index.html` — reescrito sin inventario: formulario de venta con mini-tabla (lápiz, Actualizar/Cancelar, ×, «+ Agregar otro producto»), totales en vivo, cartera con abono (fecha y hora), órdenes con semáforo de garantía y acciones de anulación y devolución.
2. `static/js/olb_byte.js` (nuevo) — modos vista/edición por fila con copia para «Cancelar», totales, limpieza de filas vacías antes de validar, autocompletado de celular y Contact Picker como mejora progresiva. `static/css/estilos.css` con modos de fila, insignias y semáforo.
3. `routers/olb_byte.py` — reescrito: `registrar_venta` lee listas paralelas y repuebla el formulario tras un error; `registrar_abono` acepta fecha y hora; nuevas rutas `anular_venta` y `registrar_devolucion`; rutas de productos eliminadas.
4. `servicios/comercial.py` — `estado_garantia` (semáforo) y validación de precios antes de tocar la sesión, para que un error no deje una orden a medias.
5. `templates/olb_byte/factura.html` — consecutivo, referencia, garantía por línea y estado real.
6. `static/js/sw.js` — `olb-finanzas-v14` con `olb_byte.js` en la precarga.
7. `tests/test_olb_vistas.py` (nuevo, 13 pruebas HTTP y de semáforo).

**Errores corregidos durante la verificación:** una fila en blanco con cantidad por defecto se tomaba como producto; un error de precio dejaba vacío el formulario repoblado; la prueba de abono leía un objeto desactualizado de la sesión.

**Verificación:** `pytest` en verde (361 pruebas), `node --check` sobre el JavaScript y `generar_guia.py` regenerado con fichas nuevas. `--verificar` falla solo por las dos plantillas de SRS v1.7 ya conocidas.

### 2026-11-17 — SRS OLB_BYTE v1.0, Fases 0 y 1: modelo sin inventario y servicio comercial

**Cambios realizados**
1. `diccionario_datos.md` §10 — modelo comercial completo (fuente única): `ventas` con `numero_orden`, `venta_detalle` con copia de datos, `movimientos_proveedor`, `garantias_proveedor` y `devoluciones_clientes` (§10.8). Decisiones en ADR-35 y ADR-36.
2. `modelos.py` — `Producto` sin `stock`; `Venta` y `VentaDetalle` reescritas; nuevas `DevolucionCliente`, `MovimientoProveedor` y `GarantiaProveedor`.
3. `core/base_datos.py` — `_reconstruir_comercial_sin_stock()` antes de `create_all`: detecta el esquema anterior, reconstruye si las tablas están vacías y se detiene si tienen datos.
4. `servicios/comercial.py` — reescrito: consecutivo sin reutilizar, deuda con proveedor como libro de movimientos, abonos con fecha y hora (solo Efectivo o Transferencia), anulación con devolución opcional, devolución posterior, cartera, balance y efectivo libre. Zona horaria de garantías fijada en UTC−5 (Colombia sin horario de verano) para no depender de `tzdata` en Windows.
5. `routers/olb_byte.py` — solo lectura adaptada al servicio nuevo; los formularios de escritura quedan para la Fase 2.
6. `tests/test_comercial.py` (reescrito, 26 pruebas de servicio), `tests/test_migracion_olb.py` (3 pruebas en proceso aislado) y `tests/conftest.py` (nuevas tablas en la limpieza).

**Verificación:** `pytest` en verde (345 pruebas). `generar_guia.py` regenerado; `--verificar` falla solo por dos plantillas sin ficha de un bloque anterior (ver AGENTS.md §9).

### 2026-11-18 — SRS v1.7, bloques F y G: capacidad de endeudamiento y consejero

**Cambios realizados**
1. `servicios/capacidad.py` (nuevo) — reparto del ingreso en gastos fijos, deudas y libre; semáforo 20 %/35 %; deudas con tres cuotas o menos; proyección a doce meses que retira la cuota al terminar cada deuda (ADR-44).
2. `templates/finanzas/_capacidad.html` (nuevo) — macro `panel_capacidad` con dona SVG, leyenda, semáforo, deudas por terminar y tabla de doce meses.
3. `routers/presupuesto.py` y `routers/trabajos.py` — ambos contextos entregan `capacidad`; cada vista instancia el panel por separado.
4. `servicios/consejero.py` (nuevo) — activación sobre $300.000, simulación mensual de bola de nieve y avalancha, recomendación con deuda objetivo, modo ahorro con metas y serie base/optimizado de doce meses (ADR-45).
5. `routers/presupuesto.py` — el contexto entrega `consejo` calculado con el `disponible` del diagnóstico.
6. `templates/presupuesto/index.html` — panel del consejero con saludo, pasos, tarjetas de intereses o ahorro y gráfica de barras comparativas; se oculta cuando el excedente no supera el umbral.
7. `static/css/estilos.css` — estilos de capacidad, semáforo ámbar/sin datos, consejero y gráfica comparativa con adaptación a 640 px.
8. `static/js/sw.js` — caché `olb-finanzas-v16`.
9. Pruebas nuevas: `tests/test_capacidad.py` (13) y `tests/test_consejero.py` (11).
10. `Guia.md` — fichas de los dos servicios y de la macro; `MEMORY.md` — ADR-44 y ADR-45.

**Verificación**
- `pytest -q` → **478 pruebas en verde** (454 previas + 24 netas).
- `python -m compileall -q app scripts` sin errores.
- `generar_guia.py --verificar` → 88 archivos con ficha y sin docstrings pendientes.

**Pendiente**
- Revisión visual en navegador de los bloques A a G (360/390/768/escritorio), incluida la gráfica del consejero en móvil.

### 2026-11-17 — SRS v1.7, bloque E: Trabajos Extras como contratos con pagos propios

**Cambios realizados**
1. `modelos.py` — `TrabajoExtra` gana `tipo_contrato`, `frecuencia`, `fecha_fin` y `fecha_pago`; `Gasto.id_trabajo` enlaza los pagos generados (ADR-34).
2. `core/base_datos.py` — `_migrar_columnas_trabajos` y la columna `id_trabajo` en `_migrar_columnas_gastos`, ambas idempotentes.
3. `servicios/trabajos.py` — reescrito: generación idempotente de pagos (mensual o quincenal con día 15 y 30 ajustado), `pagos_del_mes`, `extras_cobrados_mes` y `resumen_trabajos` calculado sobre pagos reales.
4. `servicios/gastos.py` — `listar_gastos` excluye `id_trabajo IS NOT NULL`, de modo que los cobros no alteran el sueldo, las quincenas ni los totales de gastos.
5. `servicios/pagos_metas.py` — `quitar_gasto` inhabilita 15 días también los pagos de trabajo (no los borra, para no regenerarlos).
6. `servicios/ahorro.py` — `diagnostico` suma `extras_mes` al `disponible`; el banner de `presupuesto/index.html` muestra el consolidado.
7. `routers/trabajos.py` y `templates/trabajos/index.html` — formulario con Descripción, Cliente, Valor, Tipo de Contrato y Frecuencia; fechas según contrato; reutiliza la macro `fila_gasto` de `finanzas/_gasto_fijo.html`.
8. `routers/gastos.py` — `_volver('trabajos')` para que las acciones regresen al módulo correcto.
9. `static/js/app.js` — `fecha_fin` solo visible en término fijo.
10. Pruebas: `tests/test_trabajos_extras.py` (15).
11. `MEMORY.md` — ADR-34; `diccionario_datos.md` §7 y §12.

**Verificación**
- `pytest -q` → **333 pruebas en verde** al cerrar el bloque (454 tras integrar OLB_BYTE).
- `python -m compileall -q app scripts` sin errores.
- Migración probada sobre una copia de `datos/finanzas.db` y conversión del registro heredado a término fijo de un mes.

**Pendiente**
- Revisión visual en navegador (360/390/768/escritorio) de los bloques A a E.
- Bloques F y G cerrados en la entrada del 2026-11-18.

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
- Bloques E a G del SRS v1.7 (cerrados en las entradas siguientes).

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
2. `routers/vistas.py` — `TARJETAS_DASHBOARD` se reduce a cuatro entradas: Mis Finanzas, OLB_BYTE (`solo_admin`), Registro y Detalles de deudas y Trabajos Extras (ambas de acceso general). El contexto del dashboard deja de exponer `perfil` y `mostrar_chancucos`.
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

---

### ADR-57 — Catálogo cerrado de categorías, dona por categoría y tasa implícita simulada (SRS v1.9)

- **Contexto:** los gastos usaban texto libre y las deducciones fijas no tenían categoría, así que la dona no podía agrupar egresos con colores consistentes. Además, la cuota de una deuda vinculada podía contarse como gasto y como obligación a la vez.
- **Decisión:**
  - `core/categorias.py` define las **ocho** categorías y sus colores exactos; `Gasto.categoria` y la nueva `DeduccionFija.categoria` se capturan con un selector cerrado, validado por esquemas Pydantic en `app/esquemas.py`.
  - `Gasto.id_deuda` (FK → `deudas`) complementa al `id_deuda` que ya tenía `DeduccionFija`. Un gasto o deducción vinculado deja de imputarse a las quincenas y de sumarse a las categorías 1–7: su cuota ya está en la categoría 8, que se alimenta de las deudas activas.
  - `aplicar_migraciones()` agrega las columnas en SQLite (`PRAGMA`) y PostgreSQL (`ADD COLUMN IF NOT EXISTS`) y normaliza los textos heredados sin borrar filas. `migrar_a_neon.py` la invoca antes de copiar datos.
  - La liquidez mínima sigue siendo $300.000 y se aplica **después** del reparto: solo el remanente alimenta el consejero.
  - `tasa_implicita_simulada()` deriva por bisección la tasa que implican saldo, cuota y cuotas, y la usa `DeudaNueva` para validar. No se persiste, no se cobra y no cambia la amortización: ADR-53 sigue vigente.
- **Consecuencias:** `Capacidad.deudas` pasa a ser la cuota bruta de la categoría 8 (antes se restaba la cuota vinculada). `ahorro.diagnostico` usa la misma cifra para que dona y consejero coincidan. La dona expone `categorias` y `arcos_categoria` con los colores del catálogo, además de sus cuatro arcos históricos.
- **Archivos:** `core/categorias.py`, `app/esquemas.py`, `modelos.py`, `core/base_datos.py`, `scripts/migrar_a_neon.py`, `servicios/{gastos,deducciones_fijas,deudas,quincenas,capacidad,ahorro}.py`, `routers/{gastos,presupuesto,deudas}.py`, `diccionario_datos.md` §7/§8/§9.3.

### 2026-11-20 — Paso 1: backend, migraciones, catálogo cerrado y anti-duplicación (SRS v1.9)

**Cambios realizados**
1. Catálogo cerrado de ocho categorías con colores exactos y normalización de textos heredados (`core/categorias.py`).
2. Columnas `gastos.id_deuda` y `deducciones_fijas.categoria` en los modelos; migración idempotente para SQLite y PostgreSQL, disponible también para el script de Neon mediante `aplicar_migraciones()`.
3. Esquemas Pydantic para gastos, deducciones y deudas, integrados en los routers sin cambiar el contrato de los formularios.
4. Simulación de tasa implícita por bisección (10 decimales) solo para validación; la amortización sigue sin intereses.
5. Dona agrupada por categorías, categoría 8 alimentada por deudas activas, anti-duplicación de cuotas vinculadas y base mínima de $300.000 respetada por dona y consejero.
6. Pruebas nuevas en `tests/test_categorias_cerradas.py` (9) y actualización de `test_deduccion_vinculada.py` a la nueva semántica de `deudas`.

**Verificación**
- `python -m compileall` sin errores.
- `pytest -q` → **630 pruebas en verde**.
- `scripts/generar_guia.py --verificar` → 103 archivos con ficha y sin docstrings pendientes.
- Neon: con la URL nueva se actualizó `backend/.env` (no versionado), se ejecutó `aplicar_migraciones()` y se confirmaron en `information_schema` las columnas `gastos.id_deuda`, `deducciones_fijas.categoria` e `id_deuda`; `SELECT 1` responde correctamente. Falta actualizar `DATABASE_URL` en Render.

### 2026-11-20 — Paso 2: selector cerrado, vinculación con deuda y dona por categorías (SRS v1.9)

**Cambios realizados**
1. `templates/_categorias.html`: macros `selector_categoria` (cuadro de solo lectura que despliega las 8 opciones con sus colores y pega el nombre exacto) y `vinculo_deuda` (pregunta SÍ/NO con selector de deudas mensuales activas y nota anti-duplicación).
2. `static/js/categorias.js`: apertura/cierre del desplegable, navegación con teclado, sincronización del vínculo y conservación de formularios en `sessionStorage` cuando la página vuelve con `?error…`. Cargado globally desde `base.html` y cacheado en `sw.js` (`olb-finanzas-v50`).
3. Selector incorporado en los formularios de Mis Finanzas, Gastos, Trabajos Extras (alta y edición de gasto) y Deducciones Fijas (alta y edición). `/trabajos-extras/{id}/gastos` ahora valida con `esquemas.GastoNuevo` y acepta `id_deuda`.
4. `_capacidad.html` dibuja los arcos y la leyenda con `capacidad.arcos_categoria`, más un desglose de las 8 categorías con la 8 marcada como «automática · deudas». Las metas conservan sus propias sugerencias en `sugerencias_metas`.
5. Pruebas nuevas en `tests/test_selector_categoria_ui.py` (8) y ajuste de `test_dona_interactiva.py` a la etiqueta por categoría.

**Verificación**
- `compileall` y `node --check js/categorias.js` sin errores.
- `pytest -q` → **638 pruebas en verde**.
- `scripts/generar_guia.py --verificar` → 105 archivos con ficha y sin docstrings pendientes.

### 2026-11-20 — Sección 2.1: renombramiento y alineación de deudas

**Cambios realizados**
1. «Resumen de Deudas» pasa a ser «Registro y Detalles de deudas» en la tarjeta del dashboard (`routers/vistas.py`), el `<title>` y el `<h1>` de la plantilla, el `titulo_pagina` del router, los docstrings, el diccionario de datos, el SRS, `Guia.md` y `AGENTS.md`. En los mensajes de la vista se conserva el texto neutral «deuda(s)».
2. Alineación de escritorio: la rejilla de la vista lleva `rejilla-paneles--deudas`, con `align-items: start` y `margin-top: 0` para el panel de tabla. Así «Nueva deuda» y «Deudas registradas» arrancan a la misma altura; en móvil el `gap` de la rejilla mantiene la separación. El `margin-top` genérico de `.panel--tabla` se conserva para las demás vistas.

**Verificación**
- `compileall` sin errores.
- `pytest -q` → **641 pruebas en verde** (3 nuevas en `test_deudas_ui_v19.py`).
- `scripts/generar_guia.py --verificar` → 105 archivos con ficha y sin docstrings pendientes.

### ADR-58 — Interés implícito permitido y simulación oculta (SRS v1.9, sección 2.2)

- **Contexto:** el SRS exige aceptar planes donde `cuota × cuotas` supera el capital (por ejemplo, $30.000.000 en 164 cuotas de $300.000 = $49.200.000) y solo rechazar el plan que no cubre el capital. La regla de igualdad estricta de ADR-53 quedó obsoleta.
- **Decisión:**
  - `validar_plan` rechaza únicamente `cuota × cuotas < saldo_total`, con el mensaje único «El número de cuotas por el valor de cuota no alcanza a cubrir el valor total de la deuda, revisa los datos y digítalos nuevamente». Se aplica al registrar y al editar.
  - `amortizacion_simulada()` deriva por bisección una tasa ficticia y reparte cada cuota entre interés y capital, ajustando la última para cerrar en cero. Es una comprobación matemática privada: no se persiste, no se muestra y no alimenta tablas ni recomendaciones.
  - Los pagos reales siguen abonando capital completo y `pagos_deuda.interes = 0`. Cuando el capital se agota antes del número de cuotas previsto, `cuotas_pendientes` pasa a cero para que la deuda no quede «pagada con cuotas pendientes».
  - Se agregó `actualizar_deuda()` y `POST /deudas/{id_deuda}/editar` con la misma validación; el historial de `pagos_deuda` no se reescribe.
- **Consecuencias:** ADR-53 se mantiene solo en lo referente a no capturar ni exhibir intereses; su tolerancia de $1 por cuota desaparece. Los esquemas Pydantic calculan la tasa simulada solo para validar.
- **Archivos:** `servicios/deudas.py`, `esquemas.py`, `routers/deudas.py`, `diccionario_datos.md` §8, `tests/test_deudas_interes_implicito.py`.

### 2026-11-20 — Sección 2.2: validación de cuotas con interés implícito (backend)

**Cambios realizados**
1. `validar_plan` acepta `cuota × cuotas >= total` y usa un único mensaje de error para el caso `< total`; se retira la tolerancia por cuota.
2. `amortizacion_simulada()` cuadra el modelo en privado (tasa y calendario ficticios, última cuota en cero) y se invoca al alta y a la edición descartando su resultado.
3. `DeudaNueva`/`DeudaEditar` validan con la tasa simulada; nuevo servicio `actualizar_deuda()` y ruta `POST /deudas/{id_deuda}/editar` sin reescribir pagos aplicados.
4. Los pagos reales conservan `interes = 0` y al agotar el capital se cierra `cuotas_pendientes`.

**Verificación**
- `compileall` sin errores.
- `pytest -q` → **647 pruebas en verde** (6 nuevas en `test_deudas_interes_implicito.py`; se ajustaron pruebas de la regla anterior).
- `scripts/generar_guia.py --verificar` → sin docstrings pendientes.

### 2026-11-20 — Sección 2.3: tabla tipo Excel y edición responsiva de deudas

**Cambios realizados**
1. Se elimina por completo «Próximas cuotas» y el cálculo de `planes` en `routers/deudas.py`; bajo cada deuda solo se listan las cuotas aplicadas. No hay campos ni columnas de interés.
2. La tabla usa las seis columnas pedidas: Acreedor, Total Adeudado, Cuota, No. Cuotas Pendientes, Periodicidad y Estado, más una séptima de acciones.
3. Escritorio: lápiz (macro `boton_editar`) y × al final de cada fila. El lápiz abre el patrón `<details class="edicion-gasto--modal">` con solo Total Adeudado, Cuota y No. Cuotas Pendientes, más «Actualizar» y «Cancelar»; acreedor, descripción y periodicidad viajan ocultos para la ruta de edición de 2.2.
4. Móvil: CSS oculta los iconos de la fila y `js/deudas.js` abre el mismo modal al tocar cualquier parte de `tr[data-deuda-fila]`, cerrando primero cualquier otro modal abierto. `sw.js` pasa a `olb-finanzas-v51`.

**Verificación**
- `compileall` y `node --check js/deudas.js` sin errores.
- `pytest -q` → **650 pruebas en verde** (3 nuevas; se ajustó la prueba que esperaba «Próximas cuotas»).
- `scripts/generar_guia.py --verificar` → 106 archivos con ficha y sin docstrings pendientes.

### 2026-11-20 — Sección 3.1: estructura de campos en deducciones fijas

**Cambios realizados**
1. El formulario de deducciones fijas pasa a dos filas: `fila-campos--deducciones` con Concepto | Categoría (selector cerrado) | Valor Descontado (COP), y debajo «Quincena donde aplican los pagos».
2. Se retira la etiqueta «Valor por pago (COP)»; el modal de edición usa el mismo nombre «Valor Descontado (COP)». La etiqueta «Quincena donde aplicaremos los pagos» sigue solo en el formulario de metas.
3. CSS: `.fila-campos--deducciones` fuerza tres columnas desde 641 px y hereda el apilado a una columna en móvil; `.deduccion-quincena` separa la fila inferior.

**Verificación**
- `pytest -q` → **651 pruebas en verde** (1 nueva en `test_selector_categoria_ui.py`).
- `scripts/generar_guia.py --verificar` → 106 archivos con ficha y sin docstrings pendientes.

### 2026-11-20 — Sección 3.2: flujo condicional de vinculación

**Cambios realizados**
1. La categoría 8 ya se puede elegir en los formularios; antes se reclasificaba a «Otros Gastos Fijos». Los esquemas Pydantic exigen `id_deuda` cuando la categoría es «Créditos y Obligaciones», con el mensaje de la sección 3.2.
2. `vinculo_condicional` (macro nueva en `_categorias.html`) muestra la pregunta SI/NO con el texto exacto de cada módulo solo al elegir crédito. SI habilita «Deudas registradas»; NO deshabilita guardar, muestra el mensaje exacto y el enlace «Ve a registrar la deuda».
3. Se ampliaron `deuda_vinculable` y `listar_vinculables` para aceptar **todas** las deudas activas, incluidas las quincenales (antes solo mensuales). Se conserva la anti-duplicación: el gasto/deducción vinculado no se suma a las categorías 1–7 de la dona.
4. `deudas.js` no cambia; `categorias.js` guarda en `sessionStorage` los campos y el módulo (`deducciones`, `finanzas`, `trabajos`) al pulsar el enlace. La vista de deudas muestra «Volver al formulario de origen» con `?guardado_deuda=1&deuda_id=…`; al regresar se restauran los campos, se marca SI y se preselecciona la deuda recién creada. `sw.js` pasa a `olb-finanzas-v52`.

**Verificación**
- `compileall` y `node --check js/categorias.js` sin errores.
- `pytest -q` → **656 pruebas en verde** (5 nuevas en `test_vinculacion_condicional.py`).
- `scripts/generar_guia.py --verificar` → 106 archivos con ficha y sin docstrings pendientes.

### 2026-11-20 — Sección 3.3: alineación y modal de deducciones fijas

**Cambios realizados**
1. Escritorio: `.lista-gastos__item[data-deduccion-fila] > .lista-gastos__acciones` usa `justify-content: flex-end`, `text-align: right` y `margin-left: auto` para que Editar y Eliminar queden pegados al borde derecho.
2. Móvil: se ocultan el summary del lápiz y el formulario lateral de borrado; la fila completa (`data-deduccion-fila`) abre el modal centrado existente.
3. El modal muestra la información de la deducción y tres botones: Actualizar, Eliminar y Cancelar. Eliminar usa `formaction` sobre el formulario de edición, así que no hay formularios anidados; conserva su confirmación.
4. `deudas.js` conecta ahora tanto `tr[data-deuda-fila]` como `li[data-deduccion-fila]` y se carga también en presupuesto. `sw.js` pasa a `olb-finanzas-v53`.

**Verificación**
- `compileall` y `node --check js/deudas.js` sin errores.
- `pytest -q` → **659 pruebas en verde** (3 nuevas en `test_deducciones_ui_v19.py`).
- `scripts/generar_guia.py --verificar` → 106 archivos con ficha y sin docstrings pendientes.

### 2026-11-20 — Bloque 4: modales centrados, valor de atajos y recibo legible

**Cambios realizados**
1. **4.1** Utilidad global `.modal-centrado` con `position: fixed; inset: 0; display: flex; align-items: center; justify-content: center; z-index: 50; padding: 1rem`. Se aplica también a `details.edicion-gasto--modal[open]`, cuya tarjeta pasa a ser un elemento flex centrado (`inset:auto`, `transform:none`, ancho `min(440px,100%)`, scroll propio). Se anula el `::before` y el summary del modal abierto. Los `<dialog>` nativos conservan el centrado del navegador con el mismo `z-index` y límites de viewport.
2. **4.2** Nuevo campo `chancucos.valor_pago NUMERIC(14,2)` opcional, validado en el servicio, con formulario en `chancucos/index.html`, columna «Valor a pagar» en la tabla y línea «Valor a pagar: …» en la tarjeta de Mis Finanzas antes de «Pagar». Migración idempotente en SQLite y Neon (`_migrar_valor_atajo()`).
3. **4.3** Recibo estilo Nequi: `.recibo` con fondo `#f8fafc` y texto `#111827`, separadores claros, montos y estado aprobado en `#16a34a`, cabecera azul `var(--accent-blue)` intacta. El wrapper de la captura PNG usa el mismo gris perla. `sw.js` en `olb-finanzas-v54`.

**Verificación**
- `compileall` sin errores.
- `pytest -q` → **663 pruebas en verde** (4 nuevas en `test_srs_v1_9_bloque4.py`).
- `aplicar_migraciones()` ejecutado en Neon: `chancucos.valor_pago` confirmado en `information_schema`.
- `scripts/generar_guia.py --verificar` → 106 archivos con ficha y sin docstrings pendientes.

### 2026-11-20 — Ajuste visual post Step 3: leyenda de dona y filas de deducciones

- La leyenda `.dona__leyenda--categorias` solo pinta categorías con `valor > 0`; las categorías en cero (por ejemplo, «Créditos y Obligaciones» sin deudas) ya no aparecen con `$ 0`. Los arcos ya filtraban ceros.
- Se retiró el bloque «Crédito con …: faltan N cuota(s) · saldo …» de la fila de deducciones vinculadas: ocupaba una cuarta celda de la grid de tres columnas y bajaba los botones al centro. Ahora Editar/Eliminar quedan fijos en `grid-column: 3; justify-self: end`. El vínculo `id_deuda` y la anti-duplicación no cambian.
- `sw.js` pasa a `olb-finanzas-v55`. Verificación: **663 pruebas** en verde y `generar_guia.py --verificar` sin problemas.

### 2026-11-20 — Ajuste de modales: cierre superior y orden de botones

- En móvil, el lápiz y la × laterales de las deducciones se ocultan con `display: none !important`; la fila sigue siendo táctil y abre el modal centrado.
- En los modales de edición de deudas, gasto fijo y deducciones se añadió `.edicion-gasto__cabecera` con un botón sutil `.edicion-gasto__cerrar` (`data-cancelar-edicion`) y se retiró el «Cancelar» inferior.
- En deducciones las acciones quedan en orden **Actualizar → Eliminar** (Eliminar usa `formaction`). En deudas y gasto fijo solo queda Actualizar.
- `sw.js` pasa a `olb-finanzas-v56`. Verificación: **663 pruebas** en verde y `generar_guia.py --verificar` sin problemas.

### 2026-11-20 — Leyenda única de la dona

- Se eliminó el segundo `<ul class="dona__leyenda--categorias">` que repetía «Vivienda y Servicios», «Transporte y Movilidad», etc. La leyenda de los arcos (`data-leyenda-etiqueta`) ya incluye nombre, color, valor y porcentaje de cada categoría con valor > 0.
- Se retiró la insignia «automática · deudas» y el CSS huérfano `.dona__leyenda--categorias`. `sw.js` pasa a `olb-finanzas-v57`.
- Verificación: **663 pruebas** en verde y `generar_guia.py --verificar` sin problemas.

### 2026-11-20 — Centrado directo de modales y espaciado de avisos

- La tarjeta de los modales de edición ya no depende del flex del `<details>` para centrarse: usa `position: fixed; inset: auto; top: 50%; left: 50%; transform: translate(-50%, -50%)` y ancho `min(440px, calc(100vw - 2rem))`. Esto corrige que el modal de la libranza (dentro de una celda de la grid) saliera desplazado a la izquierda mientras el de almuerzos sí salía centrado.
- `.alerta` lleva `margin-bottom: 12px`; el formulario de deducciones usa `formulario--deducciones` (18 px) y la lista `lista-gastos--deducciones` (4 px) para que el alta y el listado, y los avisos, no queden pegados.
- `sw.js` pasa a `olb-finanzas-v58`. Verificación: **665 pruebas** en verde y `generar_guia.py --verificar` sin problemas.

### 2026-11-20 — Corrector: ocultar el lápiz de deducciones en móvil

- El lápiz de edición es el `<summary>` del `<details>` y no un hijo directo de `.lista-gastos__acciones`; por eso la regla anterior `> .lista-gastos__acciones > summary` no lo ocultaba. Se cambió a `> .lista-gastos__acciones > details > summary` con `display: none !important`. La «×» de borrado (formulario hijo directo) ya se ocultaba.
- El toque sobre la fila sigue abriendo el modal centrado (`deudas.js`). `sw.js` pasa a `olb-finanzas-v59`; **665 pruebas** en verde.

### 2026-11-20 — Selector de categorías sin cuadrito de color

- En `templates/_categorias.html`, las opciones del desplegable ya no pintan `<span class="dona__muestra" style="background: color">`; llevan un punto neutro `•` con `.selector-categoria__punto` en `--text-muted`.
- Los colores hexadecimales siguen intactos en `core/categorias.py`, en los arcos SVG y en la leyenda de la dona. El nombre exacto se sigue pegando al cuadro de solo lectura al elegir.
- Aplica a todos los formularios que usan el selector (Finanzas, Gastos, Trabajos Extras y Deducciones Fijas). `sw.js` pasa a `olb-finanzas-v60`; **665 pruebas** en verde.

### 2026-11-20 — Atajos guardados: grosores iguales y filas táctiles

- Escritorio: Copiar, Pagar y Eliminar comparten `.atajo-accion` (min-height 34 px, padding 7×12, fuente 0.78rem), para que Pagar no sea más grueso.
- Móvil (≤640 px, solo `/chancucos`): `.tabla--atajos` convierte cada `<tr data-chancuco-fila>` en una fila tipo Excel con Descripción | Valor a pagar | Día de pago; se ocultan Favorito, Referencia y los controles de la celda de acciones.
- Al tocar la fila, `deudas.js` abre `details.atajo-modal` centrado con descripción, valor, días, referencia con Copiar al lado, enlace y favorito; abajo Pagar → Eliminar y cierre sutil en la cabecera.
- No se tocó el panel embebido de Mis Finanzas. `sw.js` pasa a `olb-finanzas-v61`; **668 pruebas** en verde y `node --check` OK.

### 2026-11-20 — Atajos embebidos de Mis Finanzas en móvil

- En `finanzas/index.html`, cada `li[data-atajo-fila]` lleva un `details.atajo-finanzas-modal` con la ficha completa del atajo (descripción, valor pagar, días, referencia con Copiar, enlace y favorito) y el botón Pagar abajo.
- CSS móvil (≤640 px): se ocultan la línea de valor, la referencia y el enlace Pagar de la tarjeta; solo quedan descripción y día. El toque de la fila abre el modal centrado (`deudas.js` → `conectarFilas("li[data-atajo-fila]"…)`).
- No se cambió el panel de Atajos guardados ni la lógica de negocio. `sw.js` pasa a `olb-finanzas-v62`; **669 pruebas** en verde.

### 2026-11-20 — Modal de atajos en Mis Finanzas sin enlace visible

- Se eliminó del modal la fila «Enlace de pago»: la URL ya no se muestra como texto, solo queda en el `href` del botón Pagar.
- El botón Pagar queda centrado a ancho natural (`grid-template-columns: 1fr; justify-items: center; width: auto; min-width: 160px`). El modal de `/chancucos` no cambia.
- `sw.js` pasa a `olb-finanzas-v63`; **669 pruebas** en verde.

### 2026-11-20 — Modal de edición de atajos y ajustes de presentación

- Se quitaron las líneas divisorias (`border-bottom`) de `.atajo-modal__datos` en ambos modales, igualando el formato de los demás modales.
- Móvil de «Atajos guardados»: se restablece una cabecera compacta con Descripción | Valor a pagar | Día de pago y las columnas pasan a `max-content` con gap de 6 px, para que los datos no queden alejados de la descripción.
- El modal de `/chancucos` ya no es informativo: permite editar descripción, referencia, valor a pagar, día(s), enlace (input `type="url"` con ancho controlado) y favorito; abajo Actualizar → Eliminar, sin Copiar ni Pagar. Se agregó `actualizar_chancuco()` y `POST /chancucos/{id}/editar` con auditoría. El modal de Mis Finanzas queda solo lectura + Pagar.
- `sw.js` pasa a `olb-finanzas-v64`; **670 pruebas** en verde y `generar_guia.py --verificar` sin problemas.

### 2026-11-20 — Sin etiqueta «Ver» en los modales de atajos

- Se eliminó el `<summary>Ver</summary>` de `atajo-modal` (`/chancucos`) y de `atajo-finanzas-modal` (Mis Finanzas). En escritorio no debe aparecer ningún enlace «Ver» porque la tabla ya muestra todas las opciones.
- La apertura sigue siendo exclusivamente por clic/toque en la fila (`deudas.js` → `conectarFilas`); el `<details>` sin summary se abre programáticamente con `.open = true`.
- Se retiraron las reglas CSS que ocultaban ese summary. `sw.js` pasa a `olb-finanzas-v65`; **670 pruebas** en verde.

### 2026-11-20 — Estado temporal del botón Copiar

- Existían dos manejadores para `[data-copiar]`: uno global en `app.js` (1500 ms) y otro en `finanzas.js` (1200 ms), que se pisaban y dejaban varios botones en «¡Copiado!».
- Se eliminó `copiarAlPortapapeles()`/`prepararCopiadoRapido()` de `finanzas.js`. Ahora `app.js` es el único manejador: guarda el texto original en `data-texto-original`, muestra «¡Copiado!» solo en el botón pulsado, restaura cualquier otro botón en estado copiado y vuelve a «Copiar» a los **5000 ms**.
- `sw.js` pasa a `olb-finanzas-v66`; `node --check` OK y **671 pruebas** en verde.

### 2026-11-20 — Tabla de deudas: una fila por deuda y vista limitada

- Se eliminó el `<tr class="fila-detalle-deuda">` completo: ya no se muestra «Cuotas aplicadas» ni el mensaje «Esta deuda no tiene cuotas aplicadas». Cada deuda ocupa una sola fila, una debajo de otra.
- El router dejó de consultar `pagos` para esta vista (solo se usa en el servidor cuando hace falta).
- `.tabla-contenedor--deudas` fija `max-height: 280px` (≈4 deudas visibles) con `overflow: auto`, cabecera `position: sticky` y scroll horizontal para ver el resto de columnas.
- `sw.js` pasa a `olb-finanzas-v67`; **671 pruebas** en verde y `generar_guia.py --verificar` sin problemas.

### 2026-11-20 — Alineación de botones de deuda y columna de cuotas

- El `<td class="deudas__acciones">` dejó de ser `display:flex` (eso rompía el centrado vertical de la celda). Ahora los botones van en `<div class="deudas__acciones-contenido">` con flex interno y la celda mantiene `vertical-align: middle`, así el lápiz y la × quedan alineados con la línea divisoria de cada deuda en móvil y escritorio.
- El encabezado «No. Cuotas Pendientes» se parte en tres líneas («No. de / cuotas / pendientes») y la columna mide 92 px centrada, en vez de ocupar un ancho excesivo para un solo número.
- Se ajustaron los selectores móviles que ocultan el lápiz/× para el nuevo envoltorio. `sw.js` pasa a `olb-finanzas-v68`; **671 pruebas** en verde.

### 2026-11-20 — Paneles de deudas con la misma altura

- `.rejilla-paneles--deudas` pasó de `align-items: start` a `align-items: stretch`: «Nueva deuda» y «Deudas registradas» comparten ahora el mismo top y la misma altura en escritorio.
- Se conserva `.rejilla-paneles--deudas > .panel--tabla { margin-top: 0; }` para que el panel de la tabla no baje respecto al formulario.
- `sw.js` pasa a `olb-finanzas-v69`; **671 pruebas** en verde y `generar_guia.py --verificar` sin problemas.

### 2026-11-20 — Tipografía uniforme en atajos embebidos

- En el panel «Atajos de pago» de Mis Finanzas (Resumen/Liquidación), la descripción y el número de referencia usan ahora el mismo `font-size: 0.85rem`; antes la descripción heredaba 1 rem y destacaba más.
- `sw.js` pasa a `olb-finanzas-v70`; **671 pruebas** en verde y `generar_guia.py --verificar` sin problemas.

### 2026-11-20 — Atajos guardados: sin «Details», letra menor y menos campos

- El texto «Details» que aparecía sobre la descripción en móvil venía del `<details>` sin `<summary>`: el navegador muestra su etiqueta por defecto. Se añadió `<summary class="sr-only" aria-hidden="true">` en ambos modales y `pointer-events: none` en `.sr-only` para que no intercepte clics.
- `.tabla--atajos` bajó a `font-size: 0.8rem`.
- El modal de edición ya no contiene el campo «Segundo día (opcional)»; su valor se conserva en un `<input type="hidden" name="dia_pago_2">` para no perderlo al actualizar.
- `sw.js` pasa a `olb-finanzas-v71`; **671 pruebas** en verde y `generar_guia.py --verificar` sin problemas.

### 2026-11-20 — Actualizar sustituye a Pagar en Atajos guardados

- En escritorio se retiró el enlace «Pagar» de la fila. Ahora hay un botón «Actualizar» (`data-abrir-atajo`, con `.atajo-accion`) que abre el modal de edición del atajo mediante `deudas.js`.
- El modal sigue teniendo el enlace en un `<input type="url">` con `min-width: 0; max-width: 100%; box-sizing: border-box`, para que una URL larga no ensanche la tarjeta.
- Solo afecta a `/chancucos`; los atajos embebidos de Mis Finanzas mantienen su botón Pagar. `sw.js` pasa a `olb-finanzas-v72`; **671 pruebas** en verde.

**Pendiente para el Paso 3:** solo la revisión visual en navegador (360/390/768/escritorio) de la dona, el consejero, los modales, el formulario de deducciones, el flujo SI/NO y el recibo; la corrección aritmética y la anti-duplicación ya están cubiertas por pruebas.





