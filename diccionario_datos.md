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
| `avatar_url` | `VARCHAR(500)` | Sí | No | Foto de perfil de Google (`https://*.googleusercontent.com`). Nula en cuentas con contraseña; se actualiza en cada inicio de sesión con Google. No se guarda ningún archivo. |

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
| `porcentaje_quincena_1` | `NUMERIC(5,2)` | Sí | Condicional | Obligatorio si `modalidad_pago = QUINCENAL`. Porcentaje del sueldo pagado en la quincena 1. `CHECK (> 0)`. |
| `porcentaje_quincena_2` | `NUMERIC(5,2)` | Sí | Condicional | Obligatorio si `modalidad_pago = QUINCENAL`. Porcentaje del sueldo pagado en la quincena 2. `CHECK (> 0)`. |
| `quincena_deducciones` | `SMALLINT` | Sí | Condicional | Obligatorio si `modalidad_pago = QUINCENAL`. `1` o `2`: quincena a la que se descuentan salud y pensión. `CHECK (IN (1,2))`. |
| `dia_quincena_1` | `SMALLINT` | Sí | Condicional | SRS v1.9. Obligatorio si `modalidad_pago = QUINCENAL`: día del mes en que se paga la quincena 1 (por ejemplo, 5). `CHECK (BETWEEN 1 AND 31)`. Los perfiles anteriores quedan con 15. |
| `dia_quincena_2` | `SMALLINT` | Sí | Condicional | SRS v1.9. Obligatorio si `modalidad_pago = QUINCENAL`: día del mes en que se paga la quincena 2 (por ejemplo, 20). Debe ser mayor que `dia_quincena_1`. `CHECK (BETWEEN 1 AND 31)`. Los perfiles anteriores quedan con 30. |
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
| `categoria` | `VARCHAR(60)` | No | Sí | SRS v1.9: una de las ocho categorías cerradas del catálogo de `core/categorias.py` (por ejemplo, `Vivienda y Servicios`). El texto libre heredado se normaliza en la migración. |
| `descripcion` | `VARCHAR(150)` | No | Sí | Detalle legible. |
| `valor` | `NUMERIC(14,2)` | No | Sí | `CHECK (valor >= 0)`. |
| `es_fijo` | `BOOLEAN` | No | Sí | Si es recurrente cada periodo. |
| `fecha` | `DATE` | No | Sí | Fecha del gasto. |
| `quincena` | `SMALLINT` | Sí | No | `1` o `2`: quincena a la que se imputa el gasto fijo. `NULL` = gasto del mes completo. `CHECK (quincena IN (1,2) OR quincena IS NULL)`. |
| `id_proyeccion` | `UUID` (FK → `proyecciones_ahorro`) | Sí | No | SRS v1.6: meta que originó el gasto. `ON DELETE CASCADE`. `NULL` para gastos manuales. |
| `id_trabajo` | `UUID` (FK → `trabajos_extras`) | Sí | No | SRS v1.7: pago generado por un trabajo extra. `ON DELETE CASCADE`. Los gastos con `id_trabajo` no se listan como gastos ni restan del sueldo o las quincenas: su neto va al diagnóstico del mes. |
| `id_deuda` | `UUID` (FK → `deudas`) | Sí | No | SRS v1.9: deuda registrada cuyo pago es este gasto. `ON DELETE SET NULL`. El valor se toma de la cuota de la deuda y la categoría pasa a `Créditos y Obligaciones`. No se suma como gasto propio: su dinero ya está en la categoría 8 de la dona (anti-duplicación). |
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
- SRS v1.9, catálogo cerrado: la categoría se elige entre ocho opciones fijas con colores definidos en `core/categorias.py`. La categoría 8 (`Créditos y Obligaciones`, `#EF4444`) **sí se puede seleccionar** en el formulario, pero en ese caso el backend exige un `id_deuda` vinculado; la lista de arcos vuelve a calcular su valor con la cuota de las deudas activas.
- SRS v1.9, anti-duplicación: un gasto con `id_deuda` no se imputa a las quincenas ni se suma en las categorías 1 a 7 de la dona; su cuota ya se contó en la categoría 8.

---

## 8. `deudas`

Pasivos del usuario (módulo `Registro y Detalles de deudas`). Se capturan seis
datos visibles: acreedor, descripción, total adeudado, cuota, cuotas pendientes y
periodicidad. Desaparecen la tasa, la fecha límite y el abono manual. **SRS v1.9,
ADR-58:** se admite interés implícito —`cuota × cuotas` puede superar el capital—,
pero se calcula en privado y nunca se guarda ni se muestra; los pagos siguen
abonando capital completo.

| Campo | Tipo | Nulo | Obligatorio | Descripción / Regla |
| --- | --- | --- | --- | --- |
| `id_deuda` | `UUID` (PK) | No | Sí | Identificador. |
| `id_usuario` | `UUID` (FK → `usuarios`) | No | Sí | Dueño. |
| `acreedor` | `VARCHAR(100)` | No | Sí | Entidad o persona. |
| `descripcion` | `VARCHAR(150)` | Sí | No | Detalle. |
| `saldo_total` | `NUMERIC(14,2)` | No | Sí | Total adeudado (capital); se reduce con cada cuota aplicada. |
| `cuota_mensual` | `NUMERIC(14,2)` | No | Sí | Valor de cada pago (mensual o quincenal según `periodicidad`). |
| `cuotas_pendientes` | `SMALLINT` | No | Sí | Pagos que faltan; `1..600`. |
| `periodicidad` | `VARCHAR(12)` | No | Sí | `QUINCENAL` o `MENSUAL`. |
| `fecha_creacion` | `TIMESTAMPTZ` | No | Sí | Ancla del calendario de amortización. |
| `fecha_limite` | `DATE` | Sí | No | Heredada; sin uso. |
| `estado` | `estado_deuda` | No | Sí | `ACTIVA` o `PAGADA` (se actualiza al aplicar cuotas). |

> La columna heredada `tasa_interes` puede seguir existiendo en bases ya
> desplegadas; queda nula y sin uso. El modelo ya no la mapea.

**Coherencia del plan (SRS v1.9 §2.2, mensaje actualizado en v3.9.1):** se acepta
que `cuota × cuotas >= total adeudado`; el excedente es interés implícito. El único
plan inválido es `cuota × cuotas < total`, con este mensaje exacto y amigable,
sin códigos HTTP: «El número de cuotas por el valor de cuota no alcanza a cubrir
el valor total de la deuda. Revisa los datos y digítalos nuevamente.». La
validación se aplica al registrar y al editar, y desde v3.9.1 también en vivo en
el formulario, antes de pulsar «Guardar deuda». V3.9.3: `validar_formulario`
elimina los prefijos técnicos de Pydantic (`tasa_implicita: Value error,`) para
que el mensaje de negocio llegue limpio al usuario.

**Interés implícito simulado (oculto):** `servicios/deudas.py` expone
`tasa_implicita_simulada()` y `amortizacion_simulada()`, que derivan por bisección
(diez decimales) la tasa y el calendario ficticio que cuadran el modelo y cierran
el saldo en cero en la última cuota. Son **cálculos internos**: no se persisten,
no aparecen en pantallas, tablas ni recibos y no alimentan el consejero. Los
pagos reales siguen abonando capital completo con `interes = 0`.

## 8.1 `pagos_deuda` — *Amortización automática* (SRS v1.8)

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
| `abono_capital` | `NUMERIC(14,2)` | No | Sí | Porción que reduce el capital (la cuota completa, sin intereses). |
| `interes` | `NUMERIC(14,2)` | No | Sí | Heredado; se guarda en `0` porque el modelo no cobra intereses. |
| `saldo_despues` | `NUMERIC(14,2)` | No | Sí | Saldo restante; la última cuota lo deja en `0`. |

---

## 9. `chancucos` — *Atajos de pago*

Referencias de pago rápido. Desde SRS v1.8 **todos los usuarios autenticados**
pueden crear y administrar sus propios atajos (cada uno ve solo los suyos).
**SRS v1.3:** el registro se simplifica a tres datos visibles; desaparecen
`entidad` y `tipo_servicio`, que se fusionan en una sola descripción libre.

| Campo | Tipo | Nulo | Obligatorio | Descripción / Regla |
| --- | --- | --- | --- | --- |
| `id_chancuco` | `UUID` (PK) | No | Sí | Identificador. |
| `id_usuario` | `UUID` (FK → `usuarios`) | No | Sí | Propietario del registro. |
| `descripcion` | `VARCHAR(120)` | No | Sí | Texto libre que identifica el atajo. Ej. `EPM energía`, `Claro internet`, `Tarjeta Bancolombia`. Absorbe los antiguos `entidad` + `tipo_servicio`. |
| `numero_referencia` | `VARCHAR(60)` | No | Sí | Código que el usuario copia al portapapeles antes de pagar. |
| `valor_pago` | `NUMERIC(14,2)` | Sí | No | SRS v1.9, sección 4.2: valor exacto a pagar. Opcional porque hay servicios con consumo variable; si existe se muestra en la tabla de «Atajos guardados» y en la tarjeta embebida de Mis Finanzas. No puede ser negativo. |
| `url_pago` | `VARCHAR(300)` | Sí | No | URL oficial de la pasarela. Validar `http(s)`. Se mantiene opcional: hay recibos que solo se pagan en ventanilla y el atajo sigue sirviendo para copiar la referencia. En el modal de edición se muestra en un `input type="url"` de ancho controlado para no romper la tarjeta. |
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

**Migración SRS v1.9, sección 4.2:** `_migrar_valor_atajo()` agrega `valor_pago`
`NUMERIC(14,2) NULL` en SQLite (`PRAGMA`) y PostgreSQL (`IF NOT EXISTS`). Los
atajos existentes conservan sus datos y muestran «No definido» hasta editarlos.

**Edición (SRS v1.9):** `POST /chancucos/{id_chancuco}/editar` actualiza
descripción, referencia, valor, día de pago, enlace y favorito mediante
`actualizar_chancuco()`. El modal de edición no ofrece un segundo día visible;
si el atajo ya tenía `dia_pago_2`, el valor se conserva en un campo oculto.
En escritorio la fila de «Atajos guardados» ofrece «Actualizar» (no «Pagar»);
en móvil la fila se toca para abrir el mismo modal.

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
| `categoria` | `VARCHAR(60)` | No | Sí | SRS v1.9: una de las ocho categorías cerradas de `core/categorias.py`; `DEFAULT 'Otros Gastos Fijos'`. Las libranzas heredadas se clasifican como `Créditos y Obligaciones`. |
| `id_deuda` | `UUID` (FK → `deudas`) | Sí | No | SRS v1.9 (ADR-56, sección 3.2). Deuda **activa** que esta deducción paga, mensual o quincenal. Si existe, `valor` toma la cuota de la deuda y la cuota no se cuenta dos veces. `ON DELETE SET NULL`: al borrar la deuda la deducción sigue como descuento normal. Cuando la deuda se paga, la deducción deja de descontarse. |
| `fecha_creacion` | `TIMESTAMPTZ` | No | Sí | `now()`. |

**Reglas SRS v1.9:** el selector de categoría es cerrado (ocho opciones) en el
formulario. Una deducción con `id_deuda` no se imputa a la quincena ni se suma en
las categorías 1 a 7 de la dona: su cuota ya está en la categoría 8. En una base
PostgreSQL existente, `aplicar_migraciones()` agrega `categoria` e `id_deuda` con
`ADD COLUMN IF NOT EXISTS` y normaliza los textos heredados sin borrar filas.

---

## 10. OLB_BYTE — Gestión comercial (SRS OLB_BYTE v1.0, ADR-35)

Modelo sin inventario físico: cada venta se compra al proveedor a crédito a precio
de costo en el momento de la venta. No existe control de stock. Los datos de
producto se guardan como **copia** dentro de la venta, para que un cambio posterior
de precio no altere historiales ni garantías.

Mapeo con el SRS: `ordenes_venta` = tabla `ventas`; `detalle_venta` = `venta_detalle`;
`abonos_clientes` = `abonos`. Se conservan los nombres existentes para no romper datos.

### 10.1 `clientes`
| Campo | Tipo | Nulo | Descripción |
| --- | --- | --- | --- |
| `id_cliente` | `UUID` (PK) | No | Identificador. |
| `nombre` | `VARCHAR(120)` | No | Nombre completo. |
| `telefono_whatsapp` | `VARCHAR(20)` | Sí | Celular de 10 dígitos (sin indicativo) para factura y WhatsApp. Se normaliza al guardar. |
| `correo` | `VARCHAR(150)` | Sí | Opcional. |
| `direccion` | `VARCHAR(200)` | Sí | Entrega. |
| `fecha_registro` | `TIMESTAMPTZ` | No | `now()`. |

### 10.2 `productos` — *Legado, sin uso en el flujo nuevo*
Tabla existente con SKU, costo y precio. Se **conserva** para no perder datos
históricos. Se elimina la columna `stock` (migración por reconstrucción). El flujo
nuevo no la consulta; la venta guarda la copia de los datos del producto.

| Campo | Tipo | Nulo | Descripción |
| --- | --- | --- | --- |
| `id_producto` | `UUID` (PK) | No | Identificador. |
| `sku` | `VARCHAR(40)` | No | Único. |
| `nombre` | `VARCHAR(120)` | No | Descripción comercial. |
| `costo` | `NUMERIC(14,2)` | No | Último costo conocido. |
| `precio_venta` | `NUMERIC(14,2)` | No | Precio público. |
| `garantia_meses` | `SMALLINT` | Sí | Meses de garantía de referencia. |

### 10.3 `ventas` — *Órdenes de venta*
| Campo | Tipo | Nulo | Descripción |
| --- | --- | --- | --- |
| `id_venta` | `UUID` (PK) | No | Identificador interno. |
| `numero_orden` | `INTEGER` | No | Consecutivo visible en factura. `UNIQUE`, empieza en 1 (confirmado por el propietario; aplicativo nuevo). Se asigna como máximo + 1 y **nunca se reutiliza**, ni al anular. |
| `id_cliente` | `UUID` (FK) | No | Comprador. `ON DELETE RESTRICT`. |
| `cliente_nombre` | `VARCHAR(120)` | No | Copia del nombre al vender. |
| `cliente_telefono` | `VARCHAR(20)` | Sí | Copia del celular al vender. |
| `fecha_venta` | `TIMESTAMPTZ` | No | Fecha y hora de la venta; la garantía inicia aquí. |
| `subtotal` | `NUMERIC(14,2)` | No | Suma de `subtotal_item`. |
| `total` | `NUMERIC(14,2)` | No | Valor total de la orden (`total_venta` del SRS). |
| `total_costo` | `NUMERIC(14,2)` | No | Suma de `costo_unitario × cantidad`. Es la deuda con el proveedor. |
| `ganancia_neta` | `NUMERIC(14,2)` | No | `Σ (precio − costo) × cantidad`. Cero si la orden está anulada. |
| `total_abonado` | `NUMERIC(14,2)` | No | Suma de abonos del cliente. |
| `saldo_pendiente` | `NUMERIC(14,2)` | No | `total − total_abonado`. Cartera viva. `CHECK (saldo_pendiente >= 0)`. |
| `estado_pago` | `VARCHAR(20)` | No | `PENDIENTE`, `PARCIAL` o `PAGADA`. |
| `estado_orden` | `VARCHAR(20)` | No | `ACTIVA` o `ANULADA`. Default `ACTIVA`. |
| `garantia_texto` | `VARCHAR(200)` | No | Por defecto «3 meses por defectos de fábrica». Se puede editar por venta. |
| `garantia_fecha_fin` | `DATE` | Sí | `fecha_venta` + meses de garantía. Base del semáforo. |
| `motivo_anulacion` | `VARCHAR(200)` | Sí | Obligatorio si `estado_orden = ANULADA`. |
| `fecha_anulacion` | `TIMESTAMPTZ` | Sí | Momento de la anulación. |

**Reglas de anulación (ADR-35):** la orden anulada sale de la cartera, de los totales
de venta, de la ganancia y de los rankings. **No** se revierte la deuda con el
proveedor (`movimientos_proveedor` de tipo `COMPRA_CREDITO` permanece): la mercancía
ya se compró. Si el cliente ya abonó, la anulación registra la devolución del dinero
en `devoluciones_clientes` (§10.8); los abonos originales se conservan como historial.

### 10.4 `venta_detalle` — *Líneas de la orden*
| Campo | Tipo | Nulo | Descripción |
| --- | --- | --- | --- |
| `id_detalle` | `UUID` (PK) | No | Identificador. |
| `id_venta` | `UUID` (FK) | No | Orden padre. `ON DELETE CASCADE`. |
| `id_producto` | `UUID` (FK) | Sí | Solo ventas anteriores a ADR-35. `NULL` en ventas nuevas. |
| `producto_nombre` | `VARCHAR(120)` | No | Nombre del producto. |
| `categoria` | `VARCHAR(60)` | Sí | Categoría del producto (por ejemplo, Audio). Antes se llamaba `referencia`; se renombró sin perder datos. |
| `cantidad` | `INTEGER` | No | `CHECK (cantidad > 0)`. |
| `costo_unitario` | `NUMERIC(14,2)` | No | Precio proveedor, congelado. `CHECK (>= 0)`. |
| `precio_unitario` | `NUMERIC(14,2)` | No | Precio al cliente. `CHECK (>= 0)`. |
| `subtotal_item` | `NUMERIC(14,2)` | No | `precio_unitario × cantidad`. |
| `garantia_texto` | `VARCHAR(200)` | Sí | Garantía de esta línea. |
| `garantia_fecha_fin` | `DATE` | Sí | SRS v1.9. Vencimiento de la garantía de esta línea (fecha de venta + meses de la línea). Las líneas anteriores heredan la fecha de su orden. Lo usa la tabla de ventas de la analítica para indicar Activa o Vencida por producto. |

### 10.5 `abonos` — *Pagos del cliente (`abonos_clientes` del SRS)*
| Campo | Tipo | Nulo | Descripción |
| --- | --- | --- | --- |
| `id_abono` | `UUID` (PK) | No | Identificador. |
| `id_venta` | `UUID` (FK) | No | Orden abonada. `ON DELETE CASCADE`. |
| `monto` | `NUMERIC(14,2)` | No | `CHECK (monto > 0)`. |
| `metodo_pago` | `VARCHAR(30)` | No | Nuevos registros: `EFECTIVO` o `TRANSFERENCIA`. Los históricos (`NEQUI`, `DAVIPLATA`, `TARJETA`) se conservan. |
| `fecha_abono` | `TIMESTAMPTZ` | No | Fecha **y hora** del pago (RF-06). |

### 10.6 `movimientos_proveedor` — *Cuenta por pagar al proveedor (RF-08)*
| Campo | Tipo | Nulo | Descripción |
| --- | --- | --- | --- |
| `id_movimiento` | `UUID` (PK) | No | Identificador. |
| `fecha` | `TIMESTAMPTZ` | No | Momento del movimiento. |
| `tipo` | `VARCHAR(20)` | No | `COMPRA_CREDITO` (sube la deuda) o `ABONO` (la baja). |
| `id_venta` | `UUID` (FK) | Sí | Orden que origina la compra. `ON DELETE RESTRICT`. `NULL` en abonos generales. |
| `concepto` | `VARCHAR(200)` | No | Descripción legible. |
| `monto` | `NUMERIC(14,2)` | No | `CHECK (monto > 0)`. |
| `saldo_resultante` | `NUMERIC(14,2)` | No | Deuda con el proveedor después del movimiento. |

Deuda con el proveedor = Σ `COMPRA_CREDITO` − Σ `ABONO`. Los movimientos no se editan
ni se borran: una corrección se registra como un movimiento nuevo.

### 10.7 `garantias_proveedor` — *Garantías en trámite (RF-05)*
| Campo | Tipo | Nulo | Descripción |
| --- | --- | --- | --- |
| `id_garantia` | `UUID` (PK) | No | Identificador. |
| `id_venta` | `UUID` (FK) | No | Orden original. `ON DELETE RESTRICT`. |
| `id_detalle` | `UUID` (FK) | Sí | Línea con falla. |
| `producto_referencia` | `VARCHAR(120)` | No | Copia del nombre o referencia, para el ranking de fallas. |
| `estado_tramite` | `VARCHAR(20)` | No | `ABIERTA`, `EN_TRAMITE`, `RESUELTA` o `RECHAZADA`. |
| `fecha_reclamo` | `TIMESTAMPTZ` | No | Fecha del reclamo. |
| `fecha_resolucion` | `TIMESTAMPTZ` | Sí | Se llena al resolver o rechazar. |
| `observacion` | `VARCHAR(300)` | Sí | Notas del trámite. |

### 10.8 `devoluciones_clientes` — *Dinero devuelto al cliente tras anular*
Se registra cuando una orden anulada devuelve al cliente lo que ya había abonado
(ADR-35, decisión del 17/11/2026). Un abono devuelto no vuelve a la caja.

| Campo | Tipo | Nulo | Descripción |
| --- | --- | --- | --- |
| `id_devolucion` | `UUID` (PK) | No | Identificador. |
| `id_venta` | `UUID` (FK) | No | Orden anulada. `ON DELETE RESTRICT`. |
| `fecha_devolucion` | `TIMESTAMPTZ` | No | Fecha y hora de la devolución. |
| `monto` | `NUMERIC(14,2)` | No | `CHECK (monto > 0)`. La suma de devoluciones no supera el total abonado. |
| `metodo_pago` | `VARCHAR(30)` | No | `EFECTIVO` o `TRANSFERENCIA`. |

Dinero abonado pendiente de devolver = Σ `abonos` − Σ `devoluciones_clientes` de la orden.

### 10.9 Índices y reglas transversales
- Ganancia, cartera y deuda excluyen órdenes `ANULADA`.
- Montos en `NUMERIC(14,2)` y en `Decimal`; redondeo al persistir (ADR-23 para mostrar sin centavos).
- Teléfono: 10 dígitos colombianos en el registro. El indicativo `57` se agrega solo al generar el enlace de WhatsApp.

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
usuarios 1 ─── N feedback_usuarios
deudas 1 ─── N gastos (gastos.id_deuda, ON DELETE SET NULL)
deudas 1 ─── N deducciones_fijas (deducciones_fijas.id_deuda, ON DELETE SET NULL)
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
| `valor_quincena_1` | `NUMERIC(14,2)` | Sí | Solo quincenal | Monto de la quincena 1. `valor` es el total del mes; ambas quincenas suman ese total (por porcentajes conocidos o por el valor de una quincena escrita). |
| `valor_quincena_2` | `NUMERIC(14,2)` | Sí | Solo quincenal | Monto de la quincena 2; es el total menos la quincena 1. |
| `fecha_pago_quincena_2` | `DATE` | Sí | Solo quincenal | Segunda fecha de pago del contrato quincenal; `fecha_pago` es la de la quincena 1. Define el día de cada quincena. |
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

---

## 14. `feedback_usuarios` — *Reportes de soporte* (SRS v2.0, Fase A)

Reportes enviados desde «Ayuda y comentarios». Solo los módulos públicos pueden
seleccionarse (`Finanzas`, `Gastos y presupuestos`, `Registro y Detalles de deudas`,
`Trabajos Extras`, `Atajos de pago`, `Otro`): **OLB_BYTE y la facturación están
prohibidos** en los textos y selectores dirigidos al usuario estándar (regla 2 de
la SRS v2.0). Los nombres de columna siguen la convención del proyecto en español;
entre paréntesis se indica el nombre del campo que aparece en la SRS.

| Campo | Tipo | Nulo | Obligatorio | Descripción / Regla |
| --- | --- | --- | --- | --- |
| `id_feedback` (`id`) | `VARCHAR(32)` (PK) | No | Sí | UUID hexadecimal sin guiones. |
| `id_usuario` (`user_id`) | `VARCHAR(32)` (FK → `usuarios`) | No | Sí | Dueño del reporte; `ON DELETE CASCADE`. |
| `usuario_nombre` | `VARCHAR(60)` | No | Sí | Alias **snapshot** en el momento del envío. |
| `usuario_correo` | `VARCHAR(150)` | No | Sí | Correo **snapshot** en el momento del envío. |
| `tipo_reporte` | `VARCHAR(20)` | No | Sí | `ERROR`, `SUGERENCIA` o `CALCULO` (etiquetas: error, sugerencia, cálculos/datos). |
| `modulo` | `VARCHAR(40)` | No | Sí | Uno de los seis módulos públicos; vacío se normaliza a `Otro`. |
| `descripcion` | `VARCHAR(2000)` | No | Sí | Texto libre; no puede estar vacío. |
| `dispositivo` | `VARCHAR(12)` | No | Sí | `Móvil` o `Escritorio`; lo detecta el servidor desde `User-Agent`. |
| `estado` | `VARCHAR(20)` | No | Sí | `Pendiente` (inicial), `En revisión` o `Resuelto`; indexado para el contador. |
| `fecha_creacion` (`created_at`) | `TIMESTAMPTZ` | No | Sí | `now()`. |
| `fecha_resolucion` | `TIMESTAMPTZ` | Sí | No | Se registra al pasar a `En revisión` o `Resuelto`; vuelve a nulo si se devuelve a `Pendiente` (SRS v3.0). |

**Relaciones y reglas transversales**

- `id_usuario → usuarios.id_usuario` con `ON DELETE CASCADE`: al eliminar una
  cuenta se borran sus reportes.
- El contador de la tarjeta administrativa cuenta solo `estado = 'Pendiente'`.
  Al pasar a `En revisión` o `Resuelto` el badge se actualiza en tiempo real.
- SRS v3.0: `PATCH /api/feedback/{id}` persiste el estado y `fecha_resolucion`.
  La sección «Mis reportes enviados» de `/ayuda` consulta `GET /api/feedback/mios`
  y muestra a cada usuario únicamente sus propios tickets con su estado actual.
- La tabla se crea con `create_all` en SQLite y PostgreSQL al arrancar
  (`aplicar_migraciones()`), sin borrar datos existentes.

---

## 15. Paleta oficial de donas (SRS v3.4, sección 1)

`backend/app/core/categorias.py` es la **única fuente de verdad** de los colores de
los gráficos. No se hardcodea ningún HEX en plantillas, JavaScript ni servicios;
los arcos y los puntos de la leyenda leen el mismo diccionario. Los diez HEX son
distintos (`catalogo.paleta_es_unica()` lo certifica).

| Ítem | HEX | Uso |
| --- | --- | --- |
| Base mínima de liquidez ($300.000) | `#10B981` | Dona de categorías y de capacidad |
| Alimentación y Mercado | `#F97316` | Categoría 2 |
| Vivienda y Servicios Públicos | `#3B82F6` | Categoría 1 y «Gastos fijos» en capacidad |
| Créditos y Obligaciones | `#EF4444` | Categoría 8 y «Cuota de deudas» |
| Transporte y Movilidad | `#EAB308` | Categoría 3 |
| Salud y Bienestar | `#06B6D4` | Categoría 4 |
| Educación y Desarrollo | `#8B5CF6` | Categoría 6 (Educación y Familia) |
| Entretenimiento y Ocio | `#EC4899` | Categoría 5 (Telefonía y Suscripciones) |
| Otros / Imprevistos | `#64748B` | Categoría 7 (Otros Gastos Fijos) |
| Dinero Libre / Excedente | `#84CC16` | «Disponible para abonar» |

El cambio crítico fue separar la base mínima (`#10B981`) de Alimentación
(antes `#10B981`, ahora `#F97316`), que antes compartían el mismo verde.

**Campos y flujos relacionados (sin cambios de esquema en v3.4):**
- `gastos.id_deuda` y `deducciones_fijas.id_deuda` sincronizan la cuota_oficial
  de `deudas.cuota_mensual` sin duplicarla en dona ni consejero.
- `feedback_usuarios` conserva `estado` y `fecha_resolucion` para «Mis reportes
  enviados» y el badge administrativo.

La SRS v3.7 **no añade columnas ni tablas**: la gráfica del Consejero lee la
misma serie de doce meses que ya produce `servicios/consejero.py`, enriquecida
con el diccionario en memoria `cierre` (puntos, hitos y totales). Tampoco cambia
el esquema el nuevo icono nativo ni el esquema `whatsapp://send`.

La SRS v3.9.5 tampoco modifica el modelo de datos: sustituye el ícono de menú de
OLB_BYTE por `static/img/icono_OLBBYTE.png` (recurso visual, 20×20 px) y fuerza
la rejilla de dos columnas de los velocímetros del Consejero en escritorio.

## 15. SRS v4.4 — Campos derivados (sin cambios de esquema)

La versión 4.4 **no añade columnas ni tablas**. Reutiliza las relaciones ya documentadas:

- `gastos.id_deuda` → `deudas.id_deuda`: un gasto con `id_trabajo = NULL` vincula la deuda al módulo **Finanzas**; con `id_trabajo` presente, a **Trabajos Extras** (§7 y §11).
- `deducciones_fijas.id_deuda` → `deudas.id_deuda`: siempre vincula al módulo **Finanzas** (§9).
- `deudas.id_usuario`: dueño de la deuda, usado junto con los valores del formulario para la idempotencia de 10 segundos del alta (§8).

El endpoint `GET /api/deudas` expone dos campos **derivados, no persistidos**:

| Campo | Tipo | Regla |
| --- | --- | --- |
| `esta_vinculada` | booleano | `True` si existe al menos un `gastos.id_deuda` o `deducciones_fijas.id_deuda` que apunte a la deuda. |
| `modulos_vinculados` | arreglo de texto | `[]`, `['Finanzas']`, `['Trabajos Extras']` o ambos, según las reglas anteriores. |

Los campos `misfinanzas_saved_scroll_y` y `misfinanzas_saved_scroll_ancla` viven en `sessionStorage` del navegador; no forman parte de la base de datos.

## 16. SRS v4.5 — Campos derivados de la dona global (sin cambios de esquema)

La versión 4.5 **no añade columnas ni tablas**. Reutiliza `gastos.id_deuda` e `id_trabajo` para distinguir el origen de cada compromiso (§7 y §11).

**Agrupación global en memoria** (`servicios/capacidad.py`):

| Concepto | Origen | Regla |
| --- | --- | --- |
| `base_global` | `sueldo_basico` del perfil + `pagos_del_mes().ingreso` de Trabajos Extras | Base del 100 % de la dona global; usa ingresos brutos, no el neto. |
| `totales_finanzas[categoria]` | `gastos`, `deducciones_fijas` y deducciones de ley de Mis Finanzas | Una categoría por nombre canónico del catálogo. |
| `totales_extras[categoria]` | `gastos` con `id_trabajo` de Trabajos Extras | Incluye los créditos vinculados en «Créditos y Obligaciones». |
| `categorias_globales` | Suma de ambos totales por categoría | Misma categoría => un solo valor y un solo color. |
| `Total libre` | `base_global − gastos_globales` | Un solo arco; `desglose` con `Libre - Mis Finanzas` y `Libre - Trabajos Extras`. |

Cada arco expone `desglose: [{origen, valor, porcentaje}]`. El sub-desglose se emite solo cuando una categoría tiene valores en ambos orígenes; «Total libre» siempre lo incluye. Los porcentajes se calculan sobre el mismo denominador del arco, por lo que la suma de sub-ítems cuadra con el porcentaje de la categoría (salvo redondeo a un decimal).

**Campo editable:** `deudas.descripcion` (VARCHAR 150, §8) pasa a ser modificable desde el modal y desde `PUT /api/deudas/{id}` / `PATCH /api/deudas/{id}`; el endpoint devuelve el objeto actualizado. Los campos omitidos conservan su valor actual.

**Velocímetros:** parámetros de presentación sin persistencia. Escritorio (`>= 768px`): `max-width: 640px`, `gap: 20px`, SVG `156×88`. Móvil: `max-width: 540px`, SVG `120×68`.

## 17. SRS v4.8 — Nómina 2026 (sin cambios de esquema)

**Divisor de hora ordinaria:** `HORAS_MENSUALES = 220` (antes 210). `Hora Ordinaria = sueldo_basico / 220`, conservando 4 decimales. Se admiten `cantidad_horas` decimales en `registros_horas_extra.cantidad_horas` (`NUMERIC(6,2)`).

**Catálogo de siete conceptos** (`core/config.py :: FACTORES_RECARGO`):

| Clave | Concepto | Factor |
| --- | --- | --- |
| `EXTRA_DIURNA_NORMAL` | Hora extra diurna normal | 1.25 |
| `EXTRA_NOCTURNA` | Hora extra nocturna | 1.75 |
| `EXTRA_DIURNA_DOMINICAL_FESTIVA` | Hora extra diurna dominical/festiva | 2.15 |
| `EXTRA_NOCTURNA_DOMINICAL_FESTIVA` | Hora extra nocturna dominical/festiva | 2.65 |
| `RECARGO_NOCTURNO` | Recargo nocturno ordinario | 0.35 |
| `RECARGO_DOMINICAL_FESTIVO` | Recargo ordinario dominical/festivo | 0.90 |
| `RECARGO_NOCTURNO_DOMINICAL_FESTIVO` | Recargo nocturno dominical/festivo | 1.25 |

`registros_horas_extra.tipo_hora` guarda la clave canónica. La migración `_migrar_tipos_hora_2026()` reescribe `Recargo Dominical o Festivo Diurno/Nocturno` → `RECARGO_DOMINICAL_FESTIVO` y su `factor_aplicado` a 0.90, sin tocar `valor_total`.

**Fórmulas por corte** (`ResumenQuincena`):
- `ingreso (Sueldo devengado)`: Q1 = `sueldo × %Q1`; Q2 (o pago mensual) = `sueldo × %Q2 + auxilio_transporte + recargos`, en el corte configurado en `perfil.quincena_deducciones`.
- `devengado_neto`: `ingreso − deducciones de ley del corte`.
- `saldo_libre`: `ingreso − deducciones de ley − deducciones fijas − gastos fijos del corte`.
- `total_devengado_consolidado`: suma de `devengado_neto` de todos los cortes del mes.

**Nomenclatura:** «Ingreso proyectado» → `Sueldo devengado`; «Sueldo-percibido» → `Total devengado`. El campo JSON reactivo `total_devengado_consolidado` expone el valor formateado; `saldo_bolsillo` se mantiene por compatibilidad.

## 18. SRS v4.10 — Estructura del resumen (sin cambios de esquema)

- `ResumenQuincena.ingreso` conserva el valor bruto del corte (sueldo + auxilio + recargos) porque la dona global y el Consejero lo consumen. `ResumenQuincena.devengado_neto` es `ingreso − deducciones de ley del corte` y es lo que muestra la tarjeta como «Sueldo devengado».
- Fórmula visual por corte: `saldo_libre = devengado_neto − gastos fijos del corte (con créditos vinculados) − deducciones fijas del corte`. No se resta la ley por segunda vez.
- `resumen_quincenas()` acepta `sueldo_basico` opcional: si llega, sustituye al del perfil para que los cortes cuadren con la liquidación en vivo.
- El JSON reactivo dejó de enviar `deducciones` por corte y envía el sueldo neto en `ingreso`; `finanzas.js` ya no pinta ese campo.
- `total_gastos_mes` = gastos fijos del mes + deducciones fijas vigentes; alimenta la línea «Total de Gastos del mes» del resultado y está disponible en el JSON reactivo.
- Desglose del resultado, en orden: `valor_hora`, `total_recargos`, `total_devengado`, `auxilio_transporte`, `total_ingresos`, separador, `deduccion_salud`, `deduccion_pension`, `deduccion_incapacidad`, `total_deducciones`. Se retiró «Disponible después de gastos». La dona global no se calcula nunca desde estos saldos parciales.

## 19. SRS v4.13 — Neto por corte y salidas del Consejero (sin cambios de esquema)

**Bloques de liquidación:**
- `sueldo_devengado_neto_corte` (`ResumenQuincena.sueldo_neto_corte`): `devengado_neto − deducciones fijas del corte`. Es el valor que ve el usuario en la tarjeta.
- `gastos_fijos_corte` (`ResumenQuincena.gastos`): gastos fijos del corte, con créditos vinculados.
- `saldo_libre = sueldo_devengado_neto_corte − gastos_fijos_corte`.
- El JSON reactivo expone el neto en `ingreso` y ya no envía `deducciones_fijas`.

**Salidas del motor del Consejero** (`Consejo.cierre`, todas derivadas del saldo real):
| Campo | Significado |
| --- | --- |
| `saldo_actual` / `deuda_inicial` | Saldo pendiente registrado, sin inflar. |
| `meses_minimo` | Plazo exacto pagando solo cuotas. |
| `meses_con_excedente` | Plazo exacto aplicando el excedente mensual. |
| `meses_ahorrados` | Diferencia entre ambos plazos. |
| `reduccion_capital_12m` | Diferencia real entre las dos curvas a 12 meses. |
| `deudas_detalle` | Lista `{nombre, saldo, cuota}` de cada deuda activa. |
| `cuotas_liberadas_detalle` | Lista `{nombre, saldo, cuota}` de las deudas que cierran. |

`ahorro_mostrado` es un alias de `reduccion_capital_12m`; no existe ningún campo de intereses. Las fechas usan nombres completos de meses en español y el detalle del mes seleccionado se calcula en `punto.base − punto.optimizado`.

## 20. SRS v4.17 — Componente visual del velocímetro (sin cambios de esquema)

El dial es presentación: no añade campos a `Consejo.cierre`. Lee `saldo_actual`, `fecha_cierre_base`, `fecha_cierre_opt`, `meses_minimo`, `meses_con_excedente`, `meses_ahorrados` y `excedente_mensual`.

| Elemento | Origen / regla |
| --- | --- |
| `mf-cockpit-dial` | SVG `viewBox="0 0 240 138"`, tamaño heredado 120×68 en móvil y 156×88 en escritorio. |
| `mf-dial-ticks` | 41 líneas generadas en `consejero.js`, una sola vez por SVG. |
| `mf-dial-progress` | Degradado `mfArcBlue` / `mfGlowBlue` en «Pago mínimo»; `mfArcGreen` / `mfGlowGreen` en «Con excedente». |
| `mf-gauge-meta` | Texto centrado: título, fecha completa, «En N meses», línea de saldo y condición. |
| `mf-gauge-badge` | Píldora «-N meses antes», solo en la variante excedente con `meses_ahorrados > 0`. |

Las reglas CSS viven fuera de `@media (max-width: 767px)` para aplicar en ambos tamaños; no modifican las dimensiones del contenedor ni del SVG.

## 21. SRS v4.18 — Precisión del Consejero y presentación (sin cambios de esquema)

**Bloques de liquidación:** las filas `sueldo_devengado_neto_corte` y `gastos_fijos_corte` usan 6 px de padding vertical y 0 de margen; la separación hasta la divisoria inferior es de 8 px. El bloque «Resultado del periodo» conserva su espaciado.

**Salidas del Consejero:**
- `cuotas_liberadas_detalle` se filtra por `plan_ids` (objetivo + dos siguientes). `Consejo.cuota_liberada` es la suma de ese subconjunto, nunca de todas las deudas que cierran en la simulación.
- `detalle` de `_simular()` incluye `id_deuda` y `mes`; el plazo de la deuda objetivo se lee de ahí y se compara con `objetivo.cuotas` (pago mínimo de esa deuda).
- `saldo_proyectado_excedente` es el saldo de la serie optimizada en el mes previo al cierre (o al horizonte de 12 meses), distinto de `saldo_actual` cuando hay abono extra.
- Terminología única: «pago mínimo». Quedan prohibidas «pagando solo lo mínimo» y «por más tiempo».

**Gráfica de 12 meses:** `min-height: 220px` en móvil; etiquetas de ejes `#e2e8f0` a 14 px; curva optimizada `#10b981` continua y curva base `#38bdf8` discontinua; selector `nowrap` con un único botón activo y una sola línea `data-cierre-detalle`.

## 22. SRS v4.19 — Amortización paralela y presentación (sin cambios de esquema)

- `meses_minimo` es el **mayor plazo individual** del portafolio (o el mes de liquidación de la simulación base), nunca la suma de plazos. `meses_excedente` es el mes de liquidación de la simulación con cascada; la cuota de cada deuda cerrada se suma a `extra_activa` desde el mes siguiente.
- `cuotas_liberadas_detalle` mantiene `{id_deuda, nombre, saldo, cuota, mes}`; el texto de liberación dice «para tus próximas metas a pagar (Deuda $X; Deuda $Y)».
- La proyección visual usa `consejo.cierre.puntos[:6]`: badges `Inicial` y `Mes 6`, curva base `#38bdf8` con `stroke-dasharray="7 7"` y 3,5 px, curva optimizada `#10b981` continua de 3,5 px, área diferencial con «+ Ahorro acumulado», seis píldoras y una sola línea `data-cierre-detalle`.
- Presentación: banner `.cierre-deuda__pill` con `border-radius: 14px` y texto justificado en móvil; `.capacidad__resumen` centrado en escritorio; texto corrido global `text-align: justify`.
- «Atajos guardados» en móvil: `<table>` real `table-fixed` con `min-width: 0`, columnas 38 % / 34 % / 28 % y `padding: 10px 8px` idéntico en `th` y `td`.
