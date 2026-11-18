# Diccionario de Datos — OLB_BYTE & Finanzas Personales

> **Fuente única de verdad** para el diseño de la base de datos (ver `AGENTS.md`, §5.6).
> Cualquier tabla, columna o regla nueva debe registrarse aquí **antes** de crear el modelo SQLAlchemy o la migración.
> Motor objetivo: **PostgreSQL 15+** (compatible con SQLite para desarrollo local).
> Convenciones: `snake_case`, claves primarias `id_<entidad>`, dinero en `NUMERIC(14,2)`, porcentajes en `NUMERIC(5,4)` (0.0400 = 4%), fechas en `DATE`, marcas de tiempo en `TIMESTAMPTZ`.

---

## 0. Catálogo de Enumeraciones

| Enum | Valores permitidos | Descripción |
| --- | --- | --- |
| `rol_usuario` | `ADMIN_OLB`, `USER_FINANZAS` | Rol RBAC del usuario. |
| `modalidad_pago` | `MENSUAL`, `QUINCENAL` | Forma de liquidación del salario. |
| `tipo_hora` | `EXTRA_DIURNA_NORMAL`, `EXTRA_NOCTURNA`, `EXTRA_DIURNA_DOMINICAL_FESTIVA`, `EXTRA_NOCTURNA_DOMINICAL_FESTIVA`, `RECARGO_NOCTURNO`, `RECARGO_DOMINICAL_FESTIVO` | Categoría de hora/recargo liquidada. |
| `origen_incapacidad` | `COMUN`, `LABORAL` | Origen de la incapacidad (define el porcentaje de pago). |
| `estado_periodo` | `BORRADOR`, `CALCULADO`, `CERRADO` | Ciclo de vida del periodo de nómina. |
| `estado_deuda` | `ACTIVA`, `EN_MORA`, `PAGADA` | Situación de una deuda. |
| `estado_venta` | `PENDIENTE`, `ABONADA`, `PAGADA`, `ANULADA` | Situación de una venta OLB_BYTE. |

---

## 1. `usuarios`

Cuenta de acceso y datos base del usuario. Fuente del alias usado en los saludos personalizados (RF-02).

| Campo | Tipo | Nulo | Obligatorio | Descripción / Regla |
| --- | --- | --- | --- | --- |
| `id_usuario` | `UUID` (PK) | No | Sí | Identificador único (UUID v4). |
| `correo` | `VARCHAR(150)` | No | Sí | Único, usado como login. Validación de formato email. |
| `hash_contrasena` | `VARCHAR(255)` | No | Sí | Hash Argon2/bcrypt. **Nunca** contraseña en claro. |
| `alias` | `VARCHAR(60)` | No | Sí | Apodo mostrado en UI ("¡Hola, [Alias]!"). |
| `rol` | `rol_usuario` | No | Sí | Default `USER_FINANZAS`. Alta como `ADMIN_OLB` restringida. |
| `activo` | `BOOLEAN` | No | Sí | Default `true`. Baja lógica. |
| `fecha_registro` | `TIMESTAMPTZ` | No | Sí | Default `now()`. |
| `ultimo_acceso` | `TIMESTAMPTZ` | Sí | No | Actualizado al autenticar. |

**Índices:** `UNIQUE(correo)`, `INDEX(rol)`.

---

## 2. `perfiles_financieros`

Configuración salarial del usuario (onboarding). Un registro por usuario.

| Campo | Tipo | Nulo | Obligatorio | Descripción / Regla |
| --- | --- | --- | --- | --- |
| `id_perfil` | `UUID` (PK) | No | Sí | Identificador del perfil. |
| `id_usuario` | `UUID` (FK → `usuarios`) | No | Sí | `UNIQUE`; relación 1:1. |
| `sueldo_basico` | `NUMERIC(14,2)` | No | Sí | Salario mensual base. `CHECK (sueldo_basico >= 0)`. |
| `modalidad_pago` | `modalidad_pago` | No | Sí | `MENSUAL` o `QUINCENAL`. |
| `porcentaje_quincena_1` | `NUMERIC(5,2)` | Sí | Condicional | Obligatorio si `modalidad_pago = QUINCENAL`. Porcentaje del sueldo pagado en la quincena 1 (día 15). `CHECK (> 0)`. |
| `porcentaje_quincena_2` | `NUMERIC(5,2)` | Sí | Condicional | Obligatorio si `modalidad_pago = QUINCENAL`. Porcentaje del sueldo pagado en la quincena 2 (día 30). `CHECK (> 0)`. |
| `quincena_deducciones` | `SMALLINT` | Sí | Condicional | Obligatorio si `modalidad_pago = QUINCENAL`. `1` o `2`: quincena a la que se descuentan salud y pensión. `CHECK (IN (1,2))`. |
| `auxilio_transporte_habilitado` | `BOOLEAN` | No | Sí | Resultado del validador de tope 2 SMMLV (Tarea 3). Solo lectura en UI. |
| `fecha_actualizacion` | `TIMESTAMPTZ` | No | Sí | `now()` en cada cambio. |

**Reglas:**
- Si `sueldo_basico + total_recargos > 2 SMMLV` → `auxilio_transporte_habilitado = false` (regla calculada, no editada por el usuario).
- En modalidad `QUINCENAL`, `porcentaje_quincena_1 + porcentaje_quincena_2 = 100` (tolerancia de 0,01 por redondeo). El sueldo devengado de cada quincena es `sueldo_basico × porcentaje / 100`.
- **Caso B del onboarding (SRS v1.2):** si el usuario no conoce sus porcentajes, informa el valor neto recibido en la quincena **sin** deducciones. Al no tener descuentos, ese neto equivale al devengado: `porcentaje_sin = neto / sueldo_basico × 100`, `porcentaje_con = 100 − porcentaje_sin` y `quincena_deducciones` es la quincena restante (por descarte).
- Los porcentajes son porcentajes de **devengo**; las deducciones de ley (4 % salud + 4 % pensión) se restan únicamente de la quincena marcada en `quincena_deducciones`.
- `porcentaje_quincenal` (campo único de la primera versión) quedó **obsoleto**; la migración ligera de `core/base_datos.py` copia su valor a la quincena 1 y calcula la quincena 2 como complemento a 100 %.

---

## 3. `periodos_nomina`

Liquidación de un mes/quincena por usuario. Encabezado del cuadro de nómina.

| Campo | Tipo | Nulo | Obligatorio | Descripción / Regla |
| --- | --- | --- | --- | --- |
| `id_periodo` | `UUID` (PK) | No | Sí | Identificador del periodo. |
| `id_usuario` | `UUID` (FK → `usuarios`) | No | Sí | Dueño del periodo. |
| `anio` | `SMALLINT` | No | Sí | Año fiscal (ej. 2026). |
| `mes` | `SMALLINT` | No | Sí | 1–12. `CHECK (mes BETWEEN 1 AND 12)`. |
| `quincena` | `SMALLINT` | No | Sí | `0` = mensual, `1` = primera, `2` = segunda. |
| `sueldo_basico_periodo` | `NUMERIC(14,2)` | No | Sí | Sueldo proporcional al periodo. |
| `valor_hora_ordinaria` | `NUMERIC(14,4)` | No | Sí | `sueldo_basico_periodo / 210` (base legal). |
| `total_horas_extra` | `NUMERIC(12,2)` | No | Sí | Suma de horas/recargos liquidados. |
| `total_recargos` | `NUMERIC(14,2)` | No | Sí | Valor monetario de recargos y extras. |
| `deduccion_salud` | `NUMERIC(14,2)` | No | Sí | 4% sobre sueldo básico. Solo lectura. |
| `deduccion_pension` | `NUMERIC(14,2)` | No | Sí | 4% sobre sueldo básico. Solo lectura. |
| `auxilio_transporte` | `NUMERIC(14,2)` | No | Sí | $0 si se supera el tope de 2 SMMLV. |
| `deduccion_incapacidad` | `NUMERIC(14,2)` | No | Sí | 33.33% de los días 3+ del periodo + rollover aplicado. |
| `total_gastos` | `NUMERIC(14,2)` | No | Sí | Gastos del periodo (tabla `gastos`). |
| `total_devengado` | `NUMERIC(14,2)` | No | Sí | Sueldo + recargos + auxilio. |
| `total_deducciones` | `NUMERIC(14,2)` | No | Sí | Salud + pensión + incapacidad + gastos. |
| `saldo_bolsillo` | `NUMERIC(14,2)` | No | Sí | `total_devengado - total_deducciones`. |
| `estado` | `estado_periodo` | No | Sí | Default `BORRADOR`. |
| `fecha_creacion` | `TIMESTAMPTZ` | No | Sí | `now()`. |

**Restricción:** `UNIQUE(id_usuario, anio, mes, quincena)`.
**Invariante:** `saldo_bolsillo = total_devengado - total_deducciones` (validado en pruebas).

---

## 4. `registros_horas_extra`

Detalle de horas extras y recargos de un periodo.

| Campo | Tipo | Nulo | Obligatorio | Descripción / Regla |
| --- | --- | --- | --- | --- |
| `id_registro` | `UUID` (PK) | No | Sí | Identificador del registro. |
| `id_periodo` | `UUID` (FK → `periodos_nomina`) | No | Sí | Periodo al que pertenece. |
| `tipo_hora` | `tipo_hora` | No | Sí | Categoría liquidada. |
| `cantidad_horas` | `NUMERIC(6,2)` | No | Sí | Soporta decimales. `CHECK (cantidad_horas >= 0)`. |
| `factor_aplicado` | `NUMERIC(4,2)` | No | Sí | 1.25 / 1.75 / 2.00 / 2.50 / 0.35 / 1.90. |
| `valor_hora_base` | `NUMERIC(14,4)` | No | Sí | Hora ordinaria del periodo. |
| `valor_total` | `NUMERIC(14,2)` | No | Sí | `cantidad_horas * valor_hora_base * factor_aplicado`. |

---

## 5. `incapacidades`

Registro de incapacidades con rangos de fecha (RF de nómina).

| Campo | Tipo | Nulo | Obligatorio | Descripción / Regla |
| --- | --- | --- | --- | --- |
| `id_incapacidad` | `UUID` (PK) | No | Sí | Identificador. |
| `id_usuario` | `UUID` (FK → `usuarios`) | No | Sí | Dueño del registro. |
| `numero_incapacidad` | `VARCHAR(40)` | Sí | No | Número emitido por la EPS. |
| `origen` | `origen_incapacidad` | No | Sí | `COMUN` (regla 66.67%) o `LABORAL`. |
| `fecha_inicio` | `DATE` | No | Sí | Inicio del rango. |
| `fecha_fin` | `DATE` | No | Sí | `CHECK (fecha_fin >= fecha_inicio)`. |
| `dias_totales` | `SMALLINT` | No | Sí | Días calendario del rango (inclusive). |
| `dias_mes_actual` | `SMALLINT` | No | Sí | Días liquidados en el mes de `fecha_inicio`. |
| `dias_arrastrados` | `SMALLINT` | No | Sí | Días que pasan al mes siguiente (rollover). |
| `porcentaje_pago` | `NUMERIC(5,2)` | No | Sí | 100.00 (días 1–2) / 66.67 (días 3+). |
| `valor_descontado` | `NUMERIC(14,2)` | No | Sí | Descuento efectivo al trabajador. |
| `estado` | `VARCHAR(20)` | No | Sí | `REGISTRADA`, `APLICADA`, `CERRADA`. |
| `fecha_registro` | `TIMESTAMPTZ` | No | Sí | `now()`. |

**Regla de negocio:** días 1–2 al 100% (empleador); del día 3 en adelante, 33.33% de descuento (a cargo de EPS).
**Cruce de mes:** `dias_arrastrados > 0` genera fila en `saldos_incapacidad`.

---

## 6. `saldos_incapacidad` (Rollover)

Saldo de días/dinero pendiente de aplicar en el periodo siguiente.

| Campo | Tipo | Nulo | Obligatorio | Descripción / Regla |
| --- | --- | --- | --- | --- |
| `id_saldo` | `UUID` (PK) | No | Sí | Identificador del saldo. |
| `id_usuario` | `UUID` (FK → `usuarios`) | No | Sí | Dueño. |
| `id_incapacidad_origen` | `UUID` (FK → `incapacidades`) | No | Sí | Incapacidad que lo origina. |
| `anio` | `SMALLINT` | No | Sí | Periodo destino. |
| `mes` | `SMALLINT` | No | Sí | Periodo destino (1–12). |
| `dias_pendientes` | `SMALLINT` | No | Sí | Días por liquidar. `CHECK (dias_pendientes >= 0)`. |
| `valor_pendiente` | `NUMERIC(14,2)` | No | Sí | Dinero a descontar. |
| `aplicado` | `BOOLEAN` | No | Sí | Default `false`. |
| `id_periodo_aplicado` | `UUID` (FK → `periodos_nomina`) | Sí | No | Periodo donde se aplicó. |

**Restricción sugerida:** `UNIQUE(id_incapacidad_origen, anio, mes)`.

---

## 7. `gastos`

Gastos fijos y variables que afectan el bolsillo del periodo.

| Campo | Tipo | Nulo | Obligatorio | Descripción / Regla |
| --- | --- | --- | --- | --- |
| `id_gasto` | `UUID` (PK) | No | Sí | Identificador. |
| `id_usuario` | `UUID` (FK → `usuarios`) | No | Sí | Dueño. |
| `id_periodo` | `UUID` (FK → `periodos_nomina`) | Sí | No | Nulo si es gasto fijo recurrente. |
| `categoria` | `VARCHAR(60)` | No | Sí | Ej. `VIVIENDA`, `SERVICIOS`, `TRANSPORTE`, `OCIO`. |
| `descripcion` | `VARCHAR(150)` | No | Sí | Detalle legible. |
| `valor` | `NUMERIC(14,2)` | No | Sí | `CHECK (valor >= 0)`. |
| `es_fijo` | `BOOLEAN` | No | Sí | Si es recurrente cada periodo. |
| `fecha` | `DATE` | No | Sí | Fecha del gasto. |
| `quincena` | `SMALLINT` | Sí | No | `1` o `2`: quincena a la que se imputa el gasto fijo. `NULL` = gasto del mes completo. `CHECK (quincena IN (1,2) OR quincena IS NULL)`. |
| `id_proyeccion` | `UUID` (FK → `proyecciones_ahorro`) | Sí | No | SRS v1.6: meta que originó el gasto. `ON DELETE CASCADE`. `NULL` para gastos manuales. |
| `id_trabajo` | `UUID` (FK → `trabajos_extras`) | Sí | No | SRS v1.7: pago generado por un trabajo extra. `ON DELETE CASCADE`. Los gastos con `id_trabajo` no se listan como gastos ni restan del sueldo o las quincenas: su neto va al diagnóstico del mes. |
| `pagado` | `BOOLEAN` | No | Sí | SRS v1.6: `DEFAULT false`. Registro permanente del pago (✔). No se revierte con «Limpiar». |
| `pagado_en` | `DATE` | Sí | No | SRS v1.6: fecha en que se marcó el pago. |
| `monto_pagado` | `NUMERIC(14,2)` | Sí | No | SRS v1.6: monto realmente pagado. Con ✔ es igual a `valor`; con abono manual es el monto abonado; en abonos heredados es el abono anterior. Es lo que cuenta en el saldo cuando `pagado = true`. |
| `check_visible` | `BOOLEAN` | No | Sí | SRS v1.6: `DEFAULT true`. `false` tras «Limpiar checks»; solo oculta el ✔. |
| `inhabilitado_hasta` | `DATE` | Sí | No | SRS v1.6: pago saltado con × desde una meta. Mientras la fecha sea posterior a hoy (plazo de 15 días), el gasto no suma en su quincena y no admite ✔; solo admite un abono manual. Vencido el plazo es un gasto normal. |

**Reglas:**
- Los gastos fijos con `quincena` se restan del ingreso proyectado de esa quincena en el panel de «Mis Finanzas» (SRS v1.2, bloque 3).
- Los gastos con `quincena = NULL` (incluidos los creados antes del SRS v1.2) se cuentan en la quincena 1 y se marcan como «todo el mes» para no perder el total.
- En modalidad `MENSUAL` todos los gastos del mes se acumulan en una sola tarjeta.
- SRS v1.6, metas: cada meta genera un gasto por quincena de descuento (`Ambas quincenas` = dos mitades) con la descripción «Meta · nombre». Los gastos de meta se generan desde el mes visible hasta el final del periodo escogido por el usuario.
- SRS v1.6, checks: `pagado` es permanente. Limpiar solo pone `check_visible = false`. Un gasto con `inhabilitado_hasta` vigente no cuenta en el saldo de su quincena y no admite ✔; solo admite abono manual, que lo deja pagado con el monto indicado.
- SRS v1.6, valor: editar un gasto de meta cambia su valor en los meses posteriores de la misma quincena que aún no estén pagados. Los meses nuevos toman el último valor de esa quincena.
- SRS v1.6: el abono de `abonos_proyeccion` es la suma de los gastos de la meta con `pagado = true` en ese mes; se recalcula al marcar, al editar un pago marcado y al saltar uno con ×.

---

## 8. `deudas`

Pasivos del usuario (módulo `Resumen de Deudas`). **SRS v1.5:** se capturan seis
datos visibles; la tasa de interés no se pide, se deriva del saldo, la cuota y el
número de pagos. Desaparecen la fecha límite y el abono manual.

| Campo | Tipo | Nulo | Obligatorio | Descripción / Regla |
| --- | --- | --- | --- | --- |
| `id_deuda` | `UUID` (PK) | No | Sí | Identificador. |
| `id_usuario` | `UUID` (FK → `usuarios`) | No | Sí | Dueño. |
| `acreedor` | `VARCHAR(100)` | No | Sí | Entidad o persona. |
| `descripcion` | `VARCHAR(150)` | Sí | No | Detalle. |
| `saldo_total` | `NUMERIC(14,2)` | No | Sí | Capital pendiente; se reduce con cada cuota aplicada. |
| `cuota_mensual` | `NUMERIC(14,2)` | No | Sí | Valor de cada pago (mensual o quincenal según `periodicidad`). |
| `cuotas_pendientes` | `SMALLINT` | No | Sí | Pagos que faltan; `1..600`. |
| `periodicidad` | `VARCHAR(12)` | No | Sí | `QUINCENAL` o `MENSUAL`. |
| `tasa_interes` | `NUMERIC(12,10)` | Sí | No | **Derivada**, no capturada. Tasa implícita por periodo (`0.0137085766` = 1,3709 %). |
| `fecha_creacion` | `TIMESTAMPTZ` | No | Sí | Ancla del calendario de amortización. |
| `fecha_limite` | `DATE` | Sí | No | Heredada; sin uso. |
| `estado` | `estado_deuda` | No | Sí | `ACTIVA` o `PAGADA` (se actualiza al aplicar cuotas). |

**Tasa implícita:** se resuelve por bisección
`saldo = cuota × (1 − (1 + r)^−n) / r`. Si `cuota × n = saldo`, la tasa es cero.
Si `cuota × n < saldo`, el plan no cubre la deuda y se rechaza.

## 8.1 `pagos_deuda` — *Amortización automática* (SRS v1.5)

Cada cuota que vence se registra aquí al abrir el módulo. `UNIQUE(id_deuda,
numero_cuota)` hace la operación idempotente: abrir dos veces el mismo día no
duplica pagos.

| Campo | Tipo | Nulo | Obligatorio | Descripción / Regla |
| --- | --- | --- | --- | --- |
| `id_pago` | `UUID` (PK) | No | Sí | Identificador. |
| `id_deuda` | `UUID` (FK → `deudas`) | No | Sí | Deuda amortizada; `ON DELETE CASCADE`. |
| `numero_cuota` | `SMALLINT` | No | Sí | Consecutivo; `>= 1`. |
| `fecha_aplicacion` | `DATE` | No | Sí | Fecha de vencimiento de la cuota. |
| `valor_cuota` | `NUMERIC(14,2)` | No | Sí | Valor pagado; la última se ajusta al saldo exacto. |
| `abono_capital` | `NUMERIC(14,2)` | No | Sí | Porción que reduce el capital. |
| `interes` | `NUMERIC(14,2)` | No | Sí | Porción de intereses del periodo. |
| `saldo_despues` | `NUMERIC(14,2)` | No | Sí | Saldo restante; la última cuota lo deja en `0`. |

---

## 9. `chancucos` — *Atajos de pago*

Referencias de pago rápido (exclusivo `ADMIN_OLB`). **SRS v1.3:** el registro se
simplifica a tres datos visibles; desaparecen `entidad` y `tipo_servicio`, que se
fusionan en una sola descripción libre.

| Campo | Tipo | Nulo | Obligatorio | Descripción / Regla |
| --- | --- | --- | --- | --- |
| `id_chancuco` | `UUID` (PK) | No | Sí | Identificador. |
| `id_usuario` | `UUID` (FK → `usuarios`) | No | Sí | Propietario del registro. |
| `descripcion` | `VARCHAR(120)` | No | Sí | Texto libre que identifica el atajo. Ej. `EPM energía`, `Claro internet`, `Tarjeta Bancolombia`. Absorbe los antiguos `entidad` + `tipo_servicio`. |
| `numero_referencia` | `VARCHAR(60)` | No | Sí | Código que el usuario copia al portapapeles antes de pagar. |
| `url_pago` | `VARCHAR(300)` | Sí | No | URL oficial para el botón *Pagar*. Validar `http(s)`. Se mantiene opcional: hay recibos que solo se pagan en ventanilla y el atajo sigue sirviendo para copiar la referencia. |
| `dia_pago_1` | `SMALLINT` | Sí | No | SRS v1.7: día del mes del pago (1–31). Se guarda solo el número, sin año, porque el atajo se repite todos los meses. Los atajos anteriores quedan en `NULL` y se muestran sin distintivo. |
| `dia_pago_2` | `SMALLINT` | Sí | No | SRS v1.7: segundo día del mes para un pago doble (por ejemplo, 15 y 30). Si coincide con `dia_pago_1`, se descarta y el atajo queda como pago único. |
| `favorito` | `BOOLEAN` | No | Sí | Default `false`. Ordena los atajos en el panel de lectura. |
| `fecha_creacion` | `TIMESTAMPTZ` | No | Sí | `now()`. |

**Migración desde v1.2:** `ALTER TABLE chancucos RENAME COLUMN entidad TO descripcion`
(idempotente, verificado contra `PRAGMA table_info`). La columna `tipo_servicio`
queda sin uso y se conserva para no romper bases ya desplegadas; ningún flujo la
lee ni la escribe.

**Migración SRS v1.7:** `_migrar_columnas_chancucos()` agrega `dia_pago_1` y
`dia_pago_2` como `SMALLINT NULL`. Es idempotente y no toca los atajos existentes.

---

## 9.1 `proyecciones_ahorro` — *Planificador de metas* (SRS v1.3)

Metas de ahorro o gastos programados que el usuario planifica sobre su saldo
libre mensual. La cuota se descuenta de la quincena indicada; con `3` («Ambas
quincenas», SRS v1.5) se reparte en partes iguales entre los dos pagos.

| Campo | Tipo | Nulo | Obligatorio | Descripción / Regla |
| --- | --- | --- | --- | --- |
| `id_proyeccion` | `UUID` (PK) | No | Sí | Identificador. |
| `id_usuario` | `UUID` (FK → `usuarios`) | No | Sí | Propietario de la meta. |
| `categoria` | `VARCHAR(60)` | No | Sí | Ahorro, abono a deudas, seguro del vehículo, impuestos, predial, vacaciones o texto libre. |
| `descripcion` | `VARCHAR(150)` | No | Sí | Detalle del objetivo. |
| `valor_mensual` | `NUMERIC(14,2)` | No | Sí | Cuota mensual; `>= 0`. |
| `tipo_duracion` | `VARCHAR(20)` | No | Sí | `FIJO` (indefinido) o `LIMITADO` (requiere `meses`). |
| `meses` | `SMALLINT` | Sí | Sí (SRS v1.6) | Periodo de la meta en meses (el usuario lo escribe en meses o años); `1..600`. `NULL` solo en metas anteriores a SRS v1.6, que usan 12 meses. |
| `fecha_inicio` | `DATE` | No | Sí | Primer mes de la proyección. |
| `quincena` | `SMALLINT` | No | Sí | `1`, `2` o `3`: pago del que se descuenta la cuota. `3` = ambas quincenas (se reparte entre los dos pagos). |
| `activo` | `BOOLEAN` | No | Sí | Default `true`. `false` = meta archivada (SRS v1.6). |
| `archivada_en` | `DATE` | Sí | No | SRS v1.6: fecha en que se archivó la meta. |
| `estado_final` | `VARCHAR(20)` | Sí | No | SRS v1.6: `CUMPLIDA` si el periodo terminó antes de archivarla; `ELIMINADA` si se archivó antes de cumplirse. |
| `fecha_creacion` | `TIMESTAMPTZ` | No | Sí | `now()`. |

**Total acumulado proyectado** = `valor_mensual × meses`.

**Reglas (SRS v1.6):**
- El periodo cuenta desde `fecha_inicio`. Una meta está **cumplida** cuando el mes actual supera su último mes.
- Una meta cumplida conserva su estado en Gastos y Presupuesto y ofrece **extender** (suma meses desde el mes actual) o **eliminar**.
- **Eliminar** archiva la meta (`activo = false`): se conserva con inicio, fin, total recogido y `estado_final`. Se eliminan sus gastos futuros no pagados; los pagados quedan como historial.
- Una meta archivada no se puede extender. Las metas anteriores a SRS v1.6 sin periodo conservan la ventana de 12 meses.

## 9.2 `abonos_proyeccion` — *Seguimiento mensual*

Registro de cada cuota efectivamente abonada a una meta.

| Campo | Tipo | Nulo | Obligatorio | Descripción / Regla |
| --- | --- | --- | --- | --- |
| `id_abono` | `UUID` (PK) | No | Sí | Identificador. |
| `id_proyeccion` | `UUID` (FK → `proyecciones_ahorro`) | No | Sí | Meta asociada; `ON DELETE CASCADE`. |
| `anio` | `SMALLINT` | No | Sí | Año del abono. |
| `mes` | `SMALLINT` | No | Sí | Mes del abono (1–12). |
| `valor` | `NUMERIC(14,2)` | No | Sí | Monto abonado; puede diferir de la cuota planeada. |
| `fecha_registro` | `TIMESTAMPTZ` | No | Sí | `now()`. |

**Regla:** un solo abono por meta y mes (`UNIQUE(id_proyeccion, anio, mes)`).
SRS v1.6: el abono ya no se registra a mano. Es la suma de los pagos marcados
(`gastos.pagado`) de la meta en ese mes y lo mantiene `pagos_metas.sincronizar_abono`.
Si el mes no tiene pagos, la fila se elimina.

## 9.3 `deducciones_fijas` — *Descuentos fijos del salario* (SRS v1.4, REQ-08)

Descuentos que la empresa aplica por nómina antes del pago (por ejemplo, cuotas
de libranza, fondos o seguros empresariales). Se restan de la quincena indicada
antes de calcular el saldo libre.

| Campo | Tipo | Nulo | Obligatorio | Descripción / Regla |
| --- | --- | --- | --- | --- |
| `id_deduccion` | `UUID` (PK) | No | Sí | Identificador. |
| `id_usuario` | `UUID` (FK → `usuarios`) | No | Sí | Propietario; `ON DELETE CASCADE`. |
| `descripcion` | `VARCHAR(150)` | No | Sí | Concepto, por ejemplo «Libranza banco X». |
| `valor` | `NUMERIC(14,2)` | No | Sí | Monto por pago; `>= 0`. |
| `quincena` | `SMALLINT` | No | Sí | `1` o `2`: pago del que se descuenta. |
| `fecha_creacion` | `TIMESTAMPTZ` | No | Sí | `now()`. |

---

### 10.1 `clientes`
| Campo | Tipo | Nulo | Descripción |
| --- | --- | --- | --- |
| `id_cliente` | `UUID` (PK) | No | Identificador. |
| `nombre` | `VARCHAR(120)` | No | Nombre completo. |
| `telefono_whatsapp` | `VARCHAR(20)` | Sí | Para facturación y recordatorios. |
| `correo` | `VARCHAR(150)` | Sí | Opcional. |
| `direccion` | `VARCHAR(200)` | Sí | Entrega. |
| `fecha_registro` | `TIMESTAMPTZ` | No | `now()`. |

### 10.2 `productos`
| Campo | Tipo | Nulo | Descripción |
| --- | --- | --- | --- |
| `id_producto` | `UUID` (PK) | No | Identificador. |
| `sku` | `VARCHAR(40)` | No | Único. |
| `nombre` | `VARCHAR(120)` | No | Descripción comercial. |
| `costo` | `NUMERIC(14,2)` | No | Costo de compra. |
| `precio_venta` | `NUMERIC(14,2)` | No | Precio público. |
| `stock` | `INTEGER` | No | `CHECK (stock >= 0)`. |
| `garantia_meses` | `SMALLINT` | Sí | Meses de garantía. |

### 10.3 `ventas`
| Campo | Tipo | Nulo | Descripción |
| --- | --- | --- | --- |
| `id_venta` | `UUID` (PK) | No | Identificador. |
| `id_cliente` | `UUID` (FK) | No | Comprador. |
| `fecha_venta` | `TIMESTAMPTZ` | No | `now()`. |
| `total` | `NUMERIC(14,2)` | No | Valor total. |
| `saldo_pendiente` | `NUMERIC(14,2)` | No | Cartera viva. |
| `estado` | `estado_venta` | No | Default `PENDIENTE`. |

### 10.4 `venta_detalle`
| Campo | Tipo | Nulo | Descripción |
| --- | --- | --- | --- |
| `id_detalle` | `UUID` (PK) | No | Identificador. |
| `id_venta` | `UUID` (FK) | No | Venta padre. |
| `id_producto` | `UUID` (FK) | No | Producto vendido. |
| `cantidad` | `INTEGER` | No | `CHECK (cantidad > 0)`. |
| `precio_unitario` | `NUMERIC(14,2)` | No | Precio al momento de la venta. |

### 10.5 `abonos`
| Campo | Tipo | Nulo | Descripción |
| --- | --- | --- | --- |
| `id_abono` | `UUID` (PK) | No | Identificador. |
| `id_venta` | `UUID` (FK) | No | Venta abonada. |
| `monto` | `NUMERIC(14,2)` | No | `CHECK (monto > 0)`. |
| `metodo_pago` | `VARCHAR(30)` | No | `EFECTIVO`, `NEQUI`, `TRANSFERENCIA`, `TARJETA`. |
| `fecha_abono` | `TIMESTAMPTZ` | No | `now()`. |

---

## 11. Relaciones y Reglas de Integridad

```
usuarios 1 ─── 1 perfiles_financieros
usuarios 1 ─── N periodos_nomina
usuarios 1 ─── N incapacidades
usuarios 1 ─── N gastos
usuarios 1 ─── N deudas
usuarios 1 ─── N chancucos
usuarios 1 ─── N trabajos_extras
usuarios 1 ─── N auditoria
periodos_nomina 1 ─── N registros_horas_extra
periodos_nomina 1 ─── N gastos
incapacidades 1 ─── N saldos_incapacidad
clientes 1 ─── N ventas 1 ─── N venta_detalle
ventas 1 ─── N abonos
productos 1 ─── N venta_detalle
```

1. **Borrado:** lógico (`activo=false`) en `usuarios`; en cascada sólo para `venta_detalle`.
2. **Auditoría:** toda tabla de dinero conserva `fecha_creacion`/`fecha_actualizacion`.
3. **Nunca** recalcular en SQL lo que ya define `backend/app/core/config.py`; los factores y porcentajes se replican como parámetros versionados.
4. **Redondeo:** `ROUND(..., 2)` sólo al persistir; los cálculos intermedios usan precisión completa (`Decimal`).

---

## 12. `trabajos_extras`

Ingresos independientes del salario (módulo `Trabajos Extras`). Se añadió al implementar el bloque B para no dejar el módulo sin respaldo persistente. **SRS v1.7:** el registro pasa a ser un contrato recurrente con tipo, frecuencia y fechas; sus pagos se guardan en `gastos` con `id_trabajo` (ver §7).

| Campo | Tipo | Nulo | Obligatorio | Descripción / Regla |
| --- | --- | --- | --- | --- |
| `id_trabajo` | `UUID` (PK) | No | Sí | Identificador. |
| `id_usuario` | `UUID` (FK → `usuarios`) | No | Sí | Dueño del registro. |
| `descripcion` | `VARCHAR(150)` | No | Sí | Trabajo o servicio realizado. |
| `cliente` | `VARCHAR(100)` | Sí | No | Persona o empresa que contrató. |
| `valor` | `NUMERIC(14,2)` | No | Sí | `CHECK (valor >= 0)`. Es el monto **de cada pago**: en frecuencia quincenal se cobra dos veces al mes. |
| `fecha` | `DATE` | No | Sí | Inicio del contrato. |
| `tipo_contrato` | `VARCHAR(20)` | No | Sí | `INDEFINIDO` o `TERMINO_FIJO`. Default `INDEFINIDO`. |
| `frecuencia` | `VARCHAR(12)` | No | Sí | `MENSUAL` (un pago al mes) o `QUINCENAL` (dos pagos: día 15 y día 30 ajustado). Default `MENSUAL`. |
| `fecha_fin` | `DATE` | Sí | Solo término fijo | Final del contrato. La generación de pagos se detiene en este mes. |
| `fecha_pago` | `DATE` | Sí | Sí en registros nuevos | Fecha del primer pago; ancla el día mensual y el inicio de la ventana. |
| `estado` | `VARCHAR(20)` | No | Sí | `PENDIENTE` o `COBRADO`. Default `PENDIENTE`. Se conserva por compatibilidad; el cobro real se marca pago a pago. |

**Migración SRS v1.7:** `_migrar_columnas_trabajos()` agrega `tipo_contrato`,
`frecuencia`, `fecha_fin` y `fecha_pago`. Los registros anteriores se convierten
en término fijo de un solo mes (`fecha_fin = fecha_pago = fecha`) para no
inventar ingresos recurrentes.

---

## 13. `auditoria`

Bitácora de acciones sensibles (login, cierre de sesión, guardado y borrado). Permite rastrear quién hizo qué sin depender de logs del servidor.

| Campo | Tipo | Nulo | Obligatorio | Descripción / Regla |
| --- | --- | --- | --- | --- |
| `id_evento` | `UUID` (PK) | No | Sí | Identificador. |
| `id_usuario` | `UUID` (FK → `usuarios`) | Sí | No | Nulo en intentos anónimos. |
| `accion` | `VARCHAR(40)` | No | Sí | Ej. `LOGIN_OK`, `LOGIN_FALLIDO`, `PERIODO_GUARDADO`. |
| `entidad` | `VARCHAR(40)` | Sí | No | Tabla afectada. |
| `detalle` | `VARCHAR(300)` | Sí | No | Contexto legible (sin datos sensibles). |
| `fecha` | `TIMESTAMPTZ` | No | Sí | `now()`. |
