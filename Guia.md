# Guía del proyecto — Finanzas y OLB_BYTE

> **Documento vivo.** Se reescribe completo en cada cambio relevante del código
> (ver `AGENTS.md` §5 y `MEMORY.md`). El inventario de §4 es automático y no debe
> editarse a mano; las fichas de §5 sí son manuales y deben reflejar el estado del
> archivo.

## 1. Para qué sirve esta guía

Esta guía responde tres preguntas concretas:

1. **¿Dónde está cada cosa?** Inventario de los 114 archivos de `backend/app` con
   sus clases, funciones y una línea de propósito.
2. **¿Qué hace cada archivo?** Una ficha por archivo con las decisiones que no se
   ven a simple vista (reglas de negocio, límites, dependencias).
3. **¿Cómo se sostiene?** Fórmulas del motor financiero, flujos de extremo a
   extremo, migraciones de base de datos y comandos de trabajo.

### Regla de mantenimiento (obligatoria)

| Cuándo | Qué hacer |
| --- | --- |
| Se crea, renombra o elimina un archivo | Añadir/ajustar su ficha en §5 y regenerar el inventario. |
| Cambia una función o su docstring | Regenerar el inventario (se actualiza solo). |
| Cambia una regla de negocio | Actualizar §7 y registrar el ADR en `MEMORY.md`. |
| Antes de cerrar un bloque | `python scripts\generar_guia.py --verificar`. |

```bash
cd backend
.\.venv\Scripts\python scripts\generar_guia.py             # reescribe §4
.\.venv\Scripts\python scripts\generar_guia.py --verificar # falla si falta algo
```

`--verificar` comprueba dos cosas: que **todo** módulo, clase, función y método
tenga docstring, y que **cada archivo del inventario** tenga su ficha `###` en
esta guía. Si una ficha apunta a un archivo que ya no existe, también falla.

---

## 2. Arquitectura en una página

```
Petición HTTP
   │
   ├─ MiddlewareSeguridad        CSRF por origen + cabeceras (CSP, nosniff…)
   ├─ Dependencias               cookie `sesion` → UsuarioSesion → RBAC / onboarding
   ├─ Router (app/routers)       valida Form/Query, elige plantilla o JSON
   ├─ Servicio (app/servicios)   reglas puras: nómina, quincenas, deudas, ahorro…
   ├─ Modelos (app/modelos)      SQLAlchemy 2.x sobre SQLite/PostgreSQL
   └─ Jinja2 (app/templates)     HTML server-side + HTMX/JS mínima
```

Principios que explican el resto del código:

- **Python es el cerebro.** Toda cifra que ve el usuario la calcula un servicio.
  El JavaScript solo pide el cálculo (`POST /finanzas/calcular`) y pinta la
  respuesta; nunca reimplementa la fórmula.
- **Un servicio, un tema.** `nomina.py` no conoce HTTP ni la base de datos;
  `deudas.py` no sabe de plantillas. Así se prueban sin navegador.
- **El router no calcula.** Valida entradas, llama al servicio, audita y
  redirige. Cuando una vista necesita datos derivados, los arma en `_contexto`.
- **Todo en español.** Nombres, docstrings, comentarios, mensajes y commits.
- **Migraciones idempotentes.** `core/base_datos.py` ajusta esquemas existentes
  sin Alembic en la fase SQLite; cada `_migrar_*` se puede ejecutar dos veces.

### Capas y dependencias permitidas

| Capa | Puede importar | Nunca importa |
| --- | --- | --- |
| `core/` | stdlib, SQLAlchemy | routers, servicios, plantillas |
| `servicios/` | `core/`, `modelos` | `routers/`, FastAPI |
| `routers/` | `servicios/`, `dependencias`, `core/` | JavaScript |
| `templates/` | datos del contexto | lógica de negocio |

---

## 3. Roles y navegación

| Rol | Ve | No ve |
| --- | --- | --- |
| `ADMIN_OLB` | Mis Finanzas (+ Chancucos), OLB_BYTE, Registro y Detalles de deudas, Trabajos Extras, Mi Perfil, Usuarios, Comentarios y Reportes (con badge de pendientes) | — |
| `USER_FINANZAS` | Mis Finanzas (+ Chancucos propios), Registro y Detalles de deudas, Trabajos Extras, Mi Perfil, Ayuda y comentarios (con «Mis reportes enviados») | OLB_BYTE y Comentarios y Reportes (403 en UI y endpoint) |

- **Acceso a OLB_BYTE por correo (ADR-48):** solo los correos de `CORREOS_OLB_BYTE`
  ven la tarjeta y entran al módulo; el resto recibe 403.
- **Chancucos (Atajos de Pago)** está disponible para todos los usuarios autenticados;
  cada cuenta ve solo sus propios atajos.
- **ADMIN_OLB por Google (ADR-49):** los correos de `CORREOS_ADMIN_OLB` quedan como
  `ADMIN_OLB` al iniciar sesión con Google con correo verificado. El registro con
  contraseña nunca asigna ese rol.
- **Recuperación de contraseña (ADR-51):** cualquier cuenta activa puede pedir un enlace
  por correo; la respuesta es siempre la misma para no revelar cuentas registradas.
- El header tiene **solo** `Inicio`, `Mi Perfil` y `Salir`; la navegación de
  módulos vive en el dashboard y en el submenú de Mis Finanzas.
- `dependencias.py` aplica el RBAC: `obtener_usuario_actual`, `exigir_administrador`,
  `SesionRequerida` (303 HTML / 401 JSON) y `OnboardingRequerido` (303 / 409).
- `UsuarioSesion.perfil_configurado` se calcula en cada petición: sin perfil, toda
  ruta de negocio redirige a `/perfil?bienvenida=1`.

---

## 4. Inventario automático

<!-- INVENTARIO:INICIO -->

### Resumen del inventario

- **115 archivos** documentados: 56 Python, 40 plantillas Jinja2 y 19 recursos estáticos.
- **71 clases**, **689 funciones** y **43 métodos** de clase.

### Detalle por archivo

#### `backend/app/`

- **`__init__.py`** · 9 líneas — Paquete principal de la aplicación `app`.
- **`dependencias.py`** · 226 líneas — Dependencias de sesión y autorización (RBAC).
  - Clases: `SesionRequerida`, `OnboardingRequerido`, `UsuarioSesion`
  - Funciones: `_usuario_desde_token`, `usuario_opcional`, `obtener_usuario_actual`, `obtener_usuario_sin_onboarding`, `exigir_administrador`, `exigir_olb_byte`
- **`esquemas.py`** · 489 líneas — Esquemas Pydantic de las entradas de gastos, deducciones y deudas.
  - Clases: `_FormularioBase`, `GastoNuevo`, `GastoEditar`, `DeduccionNueva`, `DeduccionEditar`, `DeudaNueva`, `DeudaEditar`, `FeedbackNuevo`
  - Funciones: `_categoria_cerrada`, `_exigir_deuda_si_es_credito`, `validar_formulario`
- **`main.py`** · 224 líneas — Punto de entrada de la aplicación **Finanzas y OLB_BYTE**.
  - Funciones: `_pide_json`, `_manejar_sesion_requerida`, `_manejar_onboarding`, `_pagina_dato_invalido`, `_manejar_dato_invalido`, `crear_aplicacion`
- **`modelos.py`** · 875 líneas — Modelos SQLAlchemy derivados de `diccionario_datos.md`.
  - Clases: `Usuario`, `PerfilFinanciero`, `PeriodoNomina`, `RegistroHorasExtra`, `Incapacidad`, `SaldoIncapacidad`, `Gasto`, `Deuda`, `PagoDeuda`, `AbonoDeuda`, `Chancuco`, `ProyeccionAhorro`, `AbonoProyeccion`, `DeduccionFija`, `Cliente`, `Producto`, `Venta`, `VentaDetalle`, `Abono`, `DevolucionCliente`, `MovimientoProveedor`, `GastoOperativo`, `GarantiaProveedor`, `TrabajoExtra`, `Auditoria`, `FeedbackUsuario`
  - Funciones: `nuevo_id`

#### `backend/app/core/`

- **`__init__.py`** · 11 líneas — Núcleo de la aplicación: parámetros de negocio y utilidades transversales.
- **`base_datos.py`** · 1017 líneas — Conexión a la base de datos y sesión por petición.
  - Clases: `Base`
  - Funciones: `_cargar_archivo_entorno`, `_url_con_driver`, `obtener_bd`, `crear_esquema`, `_renombrar_referencia_a_categoria`, `_reconstruir_comercial_sin_stock`, `_migrar_columnas_trabajos`, `_migrar_columnas_chancucos`, `_migrar_columnas_metas`, `_migrar_dias_quincena_postgres`, `_migrar_columnas_perfil`, `_migrar_columnas_gastos`, `_migrar_chancucos`, `_migrar_columnas_deudas`, `_migrar_proyeccion_quincena`, `_migrar_saldos_incapacidad`, `_migrar_columnas_usuarios`, `_migrar_garantia_detalle`, `_migrar_deduccion_vinculada`, `_migrar_categorias_y_vinculos`, `_migrar_valor_atajo`, `_migrar_feedback_resolucion`, `_migrar_tipo_deuda_inicial`, `_migrar_tipos_hora_2026`, `aplicar_migraciones`, `inicializar_base_datos`
- **`categorias.py`** · 240 líneas — Catálogo cerrado de categorías de egresos y colores de la dona.
  - Clases: `Categoria`
  - Funciones: `_clave`, `normalizar_categoria`, `es_categoria_valida`, `color_de_categoria`, `es_credito`, `paleta_es_unica`, `lista_categorias`
- **`config.py`** · 331 líneas — Parámetros de negocio y configuración de la plataforma.
  - Clases: `ParametrosNomina`, `ConfiguracionApp`
  - Funciones: `_decimal_desde_entorno`, `_lista_desde_entorno`, `obtener_parametros`, `obtener_configuracion`
- **`limitador.py`** · 130 líneas — Limitador de intentos para proteger el inicio de sesión.
  - Clases: `_RegistroIntentos`, `LimitadorIntentos`
- **`middleware.py`** · 99 líneas — Middlewares de seguridad HTTP.
  - Clases: `MiddlewareSeguridad`
- **`numeros.py`** · 112 líneas — Conversión y redondeo seguro de valores monetarios y de horas.
  - Funciones: `a_decimal`, `redondear_dinero`, `redondear_hora`, `sumar_dinero`
- **`seguridad.py`** · 299 líneas — Seguridad de la aplicación: hash de contraseñas y tokens de sesión.
  - Clases: `TokenInvalido`
  - Funciones: `hash_contrasena`, `verificar_contrasena`, `_codificar_base64url`, `_decodificar_base64url`, `_firmar`, `crear_token`, `_decodificar_contenido`, `decodificar_token`, `crear_token_recuperacion`, `decodificar_token_recuperacion`
- **`texto.py`** · 223 líneas — Utilidades de formato para la interfaz (pesos colombianos, porcentajes y fechas).
  - Funciones: `formatear_cop`, `formatear_porcentaje`, `formatear_fecha`, `parsear_monto`, `formatear_mes_anio`, `parsear_porcentaje`, `parsear_periodo_mes`

#### `backend/app/routers/`

- **`__init__.py`** · 11 líneas — Routers de la aplicación.
- **`admin.py`** · 176 líneas — Administración de cuentas (solo `ADMIN_OLB`).
  - Funciones: `_contexto_admin`, `ver_usuarios`, `cambiar_rol_usuario`, `cambiar_estado_usuario`
- **`auth.py`** · 595 líneas — Rutas de autenticación: login, registro y cierre de sesión.
  - Funciones: `_clave_intento`, `_establecer_cookie`, `ver_login`, `procesar_login`, `cerrar_sesion`, `ver_registro`, `procesar_registro`, `ver_olvide_contrasena`, `_login_con_error`, `iniciar_google`, `callback_google`, `_base_publica`, `_pagina_olvide`, `_cuenta_del_enlace`, `_pagina_restablecer`, `procesar_olvide_contrasena`, `ver_restablecer_contrasena`, `procesar_restablecer_contrasena`
- **`ayuda.py`** · 50 líneas — Vista «Ayuda y comentarios» del usuario estándar (SRS v2.0, Fase C).
  - Funciones: `ver_ayuda`
- **`chancucos.py`** · 250 líneas — Panel de Chancucos: referencias de pago con copiado y botón *Pagar*.
  - Funciones: `ver_chancucos`, `crear_chancuco`, `editar_chancuco`, `alternar_favorito`, `eliminar_chancuco`
- **`deudas.py`** · 594 líneas — Rutas del módulo "Registro y Detalles de deudas".
  - Funciones: `_clave_idempotencia`, `_deuda_reciente`, `_recordar_deuda`, `_contexto`, `ver_deudas`, `api_deudas`, `api_eliminar_deuda`, `api_actualizar_deuda`, `api_abonar_deuda`, `crear_deuda`, `editar_deuda`, `eliminar_deuda`
- **`feedback.py`** · 271 líneas — API de reportes de soporte «Ayuda y comentarios» (SRS v2.0, Fase A).
  - Clases: `CambioEstado`
  - Funciones: `enviar_feedback`, `contar_feedback_pendiente`, `listar_feedback`, `actualizar_estado_feedback`, `actualizar_feedback_api`, `listar_feedback_propio`, `ver_comentarios`
- **`finanzas.py`** · 1134 líneas — Módulo "Mis Finanzas": liquidación, guardado e historial.
  - Clases: `EntradaFinanzas`
  - Funciones: `_texto`, `_entero`, `_descuento_por_fechas`, `_leer_entradas`, `_liquidar`, `_deducciones_segun_quincena`, `_datos_formateados`, `_detalle_formateado`, `_detalle_incapacidad_json`, `_fijas_del_periodo`, `_total_fijas`, `_total_deducciones_ley`, `_saldos_quincenas`, `_contexto_calculadora`, `ver_finanzas`, `procesar_finanzas`, `calcular_finanzas_json`, `guardar_liquidacion`, `_filas_historial`, `_etiqueta_periodo`, `ver_historial`, `exportar_historial_csv`, `imprimir_periodo`, `eliminar_periodo`
- **`gastos.py`** · 694 líneas — Rutas del presupuesto de gastos.
  - Funciones: `_etiquetas_quincena`, `_parsear_fecha`, `ver_gastos`, `api_gastos_fijos`, `crear_gasto`, `editar_gasto`, `_volver`, `eliminar_gasto`, `marcar_pagado_gasto`, `desmarcar_pagado_gasto`, `api_marcar_pagado_gasto`, `api_desmarcar_pagado_gasto`, `registrar_abono_gasto`, `api_omitir_gasto`, `api_habilitar_gasto`, `api_abonar_meta`, `limpiar_pagos_gastos`
- **`incapacidades.py`** · 310 líneas — Rutas del módulo de incapacidades.
  - Funciones: `_valores_del_formulario`, `_parsear_fecha`, `_validar`, `_contexto`, `ver_incapacidades`, `calcular_incapacidad_formulario`, `guardar_incapacidad`, `eliminar_incapacidad`
- **`olb_byte.py`** · 1474 líneas — Módulo comercial OLB_BYTE: ventas a crédito, cobros, anulaciones y factura.
  - Clases: `DetalleVenta`
  - Funciones: `_detalle_de_venta`, `_filas_del_formulario`, `_lineas_desde_filas`, `_contexto`, `_contexto_pendientes`, `_pagina_con_error`, `ver_olb_byte`, `_datos_pago`, `_pago_desde_datos`, `registrar_venta`, `registrar_abono`, `_contexto_cobro`, `ver_cobro`, `ver_pendientes`, `ver_recibo`, `anular_venta`, `registrar_devolucion`, `ver_factura_hoja`, `ver_recibo_hoja`, `ver_factura`, `_contexto_cartera`, `ver_cartera`, `registrar_abono_proveedor`, `registrar_deuda_inicial`, `registrar_gasto_operativo`, `editar_gasto_operativo`, `eliminar_gasto_operativo`, `_pagina_error_pdf`, `_entero_opcional`, `_filtro_desde_url`, `_parametros_filtro`, `_url_analitica`, `ver_analitica`, `exportar_analitica_csv`, `_contexto_garantias`, `ver_garantias`, `registrar_garantia`, `actualizar_garantia`
- **`perfil.py`** · 310 líneas — Rutas del perfil financiero y del cambio de contraseña.
  - Funciones: `_formatear_porcentaje`, `_contexto_perfil`, `ver_perfil`, `guardar_perfil`, `cambiar_contrasena`
- **`presupuesto.py`** · 468 líneas — Rutas del planificador de ahorro y metas (SRS v1.3, bloque 3).
  - Funciones: `_fecha_del_formulario`, `_meses_del_formulario`, `_contexto`, `ver_presupuesto`, `crear_proyeccion`, `eliminar_proyeccion`, `extender_meta`, `crear_deduccion_fija`, `editar_deduccion_fija`, `eliminar_deduccion_fija`
- **`pwa.py`** · 56 líneas — Recursos PWA: manifiesto, service worker y favicon.
  - Funciones: `manifiesto`, `service_worker`, `favicon`
- **`trabajos.py`** · 317 líneas — Rutas del módulo "Trabajos Extras".
  - Funciones: `_fecha_opcional`, `_contexto`, `ver_trabajos_extras`, `crear_trabajo`, `cambiar_estado`, `eliminar_trabajo`, `agregar_gasto_trabajo`
- **`vistas.py`** · 226 líneas — Rutas de navegación principal y endpoint de salud.
  - Funciones: `iniciales_alias`, `contexto_base`, `verificar_salud`, `ver_dashboard`

#### `backend/app/servicios/`

- **`__init__.py`** · 14 líneas — Servicios de dominio (reglas de negocio puras).
- **`acceso_google.py`** · 123 líneas — Inicio de sesión con Google (cuenta de Gmail) mediante OAuth 2.0 (ADR-48).
  - Clases: `AccesoGoogleError`
  - Funciones: `google_activo`, `url_autorizacion`, `_leer_json`, `intercambiar_codigo`
- **`ahorro.py`** · 863 líneas — Planificador de ahorro y metas del usuario (SRS v1.3, bloque 3).
  - Clases: `MesMeta`, `MetaResumen`
  - Funciones: `etiqueta_quincena`, `valor_por_pago`, `_normalizar_modo_ambas`, `valor_mensual_efectivo`, `_mover_mes`, `_etiqueta_mes`, `_validar_duracion`, `crear_proyeccion`, `listar_proyecciones`, `_posicion`, `eliminar_proyeccion`, `extender_proyeccion`, `historial_metas`, `_detalle_pagos`, `meses_de_la_meta`, `_estado_mes`, `resumen_metas`, `saldo_libre_total`, `diagnostico`
- **`analitica.py`** · 910 líneas — Analítica de OLB_BYTE: reportes, clientes VIP, costos y tablas exportables.
  - Clases: `Filtro`, `Linea`, `_Acumulado`
  - Funciones: `_acumular`, `_repartir`, `_lineas`, `_gastos_operativos_por_mes`, `_saldos_pasivo_antiguo`, `_pasivo_antiguo_en`, `_gastos_operativos_por_anio`, `_variacion`, `_ordenes_activas`, `anios_con_ventas`, `reporte_mensual`, `reporte_anual`, `ranking_vip`, `alertas_costos`, `estado_garantia_fila`, `tabla_ventas`, `_csv_dinero`, `_csv_numero`, `_csv_fecha`, `serializar_csv`, `tabla_csv`
- **`auditoria.py`** · 61 líneas — Bitácora de auditoría de acciones sensibles.
  - Funciones: `registrar`, `listar_eventos`
- **`auxilio.py`** · 146 líneas — Evaluación del derecho al auxilio de transporte (SRS RF-07).
  - Clases: `EvaluacionAuxilio`
  - Funciones: `evaluar_auxilio_transporte`, `evaluar_auxilio_salarial`
- **`capacidad.py`** · 949 líneas — Capacidad de endeudamiento y proyección a doce meses (SRS v1.7, bloque F).
  - Clases: `Capacidad`
  - Funciones: `repartir_libre`, `es_credito`, `_porcentaje`, `agrupar_por_categoria`, `resumen_categorias`, `_arcos_categoria`, `_arcos_categoria_global`, `_repartir_arcos`, `_meses_equivalentes`, `_etiqueta_mes`, `_mover_mes`, `meses_siguientes`, `deudas_por_terminar`, `proyeccion_capacidad`, `_mensaje_semaforo`, `capacidad_trabajos`, `capacidad_endeudamiento`
- **`chancucos.py`** · 321 líneas — Referencias de pago rápido ("Chancucos").
  - Funciones: `_normalizar_dia`, `_normalizar_dias`, `normalizar_enlace_pago`, `_validar_url`, `crear_chancuco`, `actualizar_chancuco`, `listar_chancucos`, `alternar_favorito`, `eliminar_chancuco`
- **`comercial.py`** · 1846 líneas — Operación comercial de OLB_BYTE: ventas a crédito, cartera y deuda con proveedor.
  - Clases: `LineaVenta`, `PagoInicial`
  - Funciones: `etiqueta_tipo_movimiento`, `ahora_tienda`, `normalizar_telefono`, `_dinero`, `_sumar_meses`, `_texto_garantia`, `_validar_linea`, `_cliente_para_venta`, `_siguiente_numero_orden`, `deuda_proveedor`, `_registrar_movimiento_proveedor`, `registrar_cliente`, `listar_clientes`, `buscar_clientes`, `registrar_venta`, `obtener_venta`, `_venta_activa`, `_recalcular_estado_pago`, `_validar_metodo`, `registrar_abono`, `_devuelto`, `_registrar_devolucion`, `anular_venta`, `registrar_devolucion`, `pendiente_devolver`, `obtener_abono`, `abonos_de_venta`, `buscar_cartera`, `registrar_abono_proveedor`, `registrar_deuda_inicial`, `listar_movimientos_proveedor`, `listar_movimientos_con_orden`, `_fecha_gasto`, `registrar_gasto_operativo`, `actualizar_gasto_operativo`, `eliminar_gasto_operativo`, `listar_gastos_operativos`, `total_gastos_operativos`, `_texto_busqueda`, `filtrar_ventas`, `listar_ventas`, `cartera`, `resumen_cartera`, `estado_garantia`, `clasificar_saldo`, `_barra_divergente`, `balance_tres_bloques`, `barras_balance`, `segmentos_dona`, `etiqueta_producto`, `opciones_garantia`, `registrar_garantia`, `actualizar_estado_garantia`, `listar_garantias`, `garantia_vigente_al_reclamo`, `ranking_fallas`, `formatear_pesos`, `texto_compartir_factura`, `enlace_whatsapp_factura`, `enlace_whatsapp_recibo`, `enlace_whatsapp_cobro`, `_enlace_wa`
- **`consejero.py`** · 878 líneas — Consejero financiero del excedente mensual (SRS v1.8).
  - Clases: `Consejo`, `_EstadoDeuda`
  - Funciones: `_cuotas_mensuales`, `_estados`, `_ordenar`, `_simular`, `_altura`, `_serie_comparada`, `_fecha_cierre`, `_fecha_cierre_corta`, `_palabra_plazo`, `_datos_cierre`, `_consejo_deuda`, `_consejo_ahorro`, `consejo_financiero`
- **`correo.py`** · 261 líneas — Envío de correos del sistema: APIs transaccionales HTTPS o SMTP (SRS v3.1).
  - Funciones: `_destinatario`, `_enviar_por_api`, `enviar_correo`, `configuracion_valida`, `enviar_recuperacion`
- **`deducciones_fijas.py`** · 335 líneas — Deducciones fijas del salario (SRS v1.4, REQ-08; vinculación SRS v1.9).
  - Funciones: `_validar`, `_deuda_vinculable`, `crear_deduccion`, `actualizar_deduccion`, `eliminar_deduccion`, `listar_deducciones`, `listar_vigentes`, `sin_vinculo`, `total_creditos_sin_vinculo`, `vinculadas_activas`, `cuota_de_vinculadas`, `total_por_quincena`
- **`deudas.py`** · 948 líneas — Pasivos del usuario y amortización automática ("Registro y Detalles de deudas").
  - Clases: `CuotaProyectada`
  - Funciones: `_limpiar_periodicidad`, `_sumar_periodo`, `_periodos_transcurridos`, `_validar_datos_plan`, `validar_plan`, `_valor_presente`, `tasa_implicita_simulada`, `amortizacion_simulada`, `deuda_vinculable`, `crear_deuda`, `actualizar_deuda`, `listar_deudas`, `vinculaciones_de_deudas`, `vinculacion_de_deuda`, `listar_vinculables`, `listar_pagos`, `_aplicar_pago`, `aplicar_cuotas_vencidas`, `registrar_abono`, `proyeccion_deuda`, `cuota_mensual_equivalente`, `eliminar_deuda`, `resumen_deudas`
- **`factura_pdf.py`** · 159 líneas — Factura de OLB_BYTE: datos, logos, diseño compartido y conversión a PDF (ADR-36).
  - Funciones: `nombre_archivo`, `logo_como_data_uri`, `datos_factura`
- **`feedback.py`** · 247 líneas — Reportes de soporte del módulo «Ayuda y comentarios» (SRS v2.0, Fase A).
  - Funciones: `detectar_dispositivo`, `tipos_reporte_para_ui`, `crear_reporte`, `contar_pendientes`, `listar_reportes`, `cambiar_estado`, `listar_del_usuario`, `serialize`
- **`gastos.py`** · 432 líneas — Gastos y presupuesto del usuario.
  - Funciones: `valor_computable`, `crear_gasto`, `_normalizar_quincena`, `listar_gastos`, `serializar_gasto`, `listar_gastos_con_deuda`, `total_gastos_mes`, `total_gastos_quincena`, `total_gastos_periodo`, `resumen_por_categoria`, `eliminar_gasto`, `actualizar_gasto`
- **`incapacidad.py`** · 361 líneas — Incapacidades laborales y reparto de días por mes calendario (Tarea 4).
  - Clases: `_AcumuladorMes`, `TramoMensual`, `SaldoIncapacidad`, `LiquidacionIncapacidad`, `ResultadoMesIncapacidad`
  - Funciones: `_validar_rango`, `calcular_incapacidad`, `liquidar_mes_incapacidad`
- **`nomina.py`** · 443 líneas — Motor de nómina colombiana — Tarea 2.
  - Clases: `DeduccionesLey`, `RecargoCalculado`, `ResultadoRecargos`, `LiquidacionNomina`
  - Funciones: `_obtener_parametros`, `_validar_no_negativo`, `calcular_valor_hora_ordinaria`, `calcular_deducciones_ley`, `calcular_recargo`, `calcular_recargos`, `calcular_total_devengado`, `liquidar_periodo`
- **`pagos_metas.py`** · 713 líneas — Metas de ahorro convertidas en gastos fijos con check de pago (SRS v1.6).
  - Funciones: `_posicion`, `_desde_posicion`, `_rango_del_mes`, `_gastos_de_meta_en_mes`, `_quincenas_de_la_meta`, `_meses_a_generar`, `_valor_vigente`, `asegurar_gastos_de_metas`, `sincronizar_abono`, `sincronizar_gasto`, `propagar_valor`, `marcar_pagado`, `desmarcar_pagado`, `registrar_abono_manual`, `registrar_abono_meta`, `limpiar_checks`, `inhabilitar_gasto`, `omitir_pago`, `habilitar_gasto`, `quitar_gasto`
- **`perfiles.py`** · 392 líneas — Perfil financiero del usuario (onboarding).
  - Funciones: `obtener_perfil`, `perfil_configurado`, `_validar_porcentaje`, `parsear_dia_quincena`, `validar_dias_quincena`, `dias_quincena`, `etiquetas_quincena`, `validar_quincenas`, `calcular_quincenas_desde_neto`, `guardar_perfil`, `porcentajes_quincena`, `sueldo_del_periodo`
- **`periodos.py`** · 191 líneas — Persistencia y consulta de periodos de nómina.
  - Funciones: `obtener_periodo`, `listar_periodos`, `horas_del_periodo`, `guardar_liquidacion`, `eliminar_periodo`
- **`quincenas.py`** · 297 líneas — Resumen de quincenas para el panel izquierdo de "Mis Finanzas".
  - Clases: `ResumenQuincena`
  - Funciones: `_etiqueta`, `resumen_quincenas`, `_a_decimal`
- **`recibo_imagen.py`** · 74 líneas — Recibo de abono de OLB_BYTE como imagen PNG para compartir por WhatsApp (RF-07).
  - Funciones: `nombre_archivo_recibo`, `texto_compartir_recibo`, `datos_recibo`
- **`registro_incapacidades.py`** · 201 líneas — Persistencia de incapacidades y consulta de sus tramos mensuales.
  - Funciones: `registrar_incapacidad`, `tramos_del_mes`, `descuento_del_mes`, `listar_incapacidades`, `eliminar_incapacidad`
- **`trabajos.py`** · 1008 líneas — Ingresos independientes ("Trabajos Extras").
  - Funciones: `_posicion`, `_desde_posicion`, `_rango_del_mes`, `_fecha_con_dia`, `_normalizar_contrato`, `_normalizar_frecuencia`, `_normalizar_quincena`, `_monto_opcional`, `_porcentaje_opcional`, `reparto_por_porcentajes`, `reparto_quincenal`, `porcentaje_del_total`, `valor_del_pago`, `crear_trabajo`, `listar_trabajos`, `cambiar_estado`, `eliminar_trabajo`, `gastos_fijos_trabajo`, `crear_gasto_trabajo`, `_pagos_del_mes`, `_meses_a_generar`, `_crear_pagos_del_mes`, `asegurar_pagos_trabajos`, `_periodos_del_trabajo`, `pagos_del_mes`, `libre_neto_mes`, `extras_cobrados_mes`, `resumen_trabajos`, `reparar_pagos_duplicados`
- **`usuarios.py`** · 359 líneas — Repositorio de usuarios sobre SQLAlchemy (Fase 2).
  - Funciones: `_normalizar_correo`, `correo_valido`, `sembrar_demostracion`, `buscar_por_correo`, `obtener_por_id`, `listar_usuarios`, `autenticar`, `crear_usuario`, `actualizar_alias`, `cambiar_contrasena`, `cambiar_rol`, `cambiar_estado`, `huella_contrasena`, `restablecer_contrasena`, `url_avatar_valida`, `actualizar_avatar`

#### `backend/app/static/`

- **`manifest.webmanifest`** · 35 líneas — Manifiesto PWA

#### `backend/app/static/css/`

- **`estilos.css`** · 6756 líneas — Fondo y superficies
- **`factura-olb.css`** · 755 líneas — SRS v4.44: el retorno de la factura es «Volver a Ventas» en todos los

#### `backend/app/static/js/`

- **`app.js`** · 1579 líneas — Mejoras progresivas globales.
  - Funciones: `restaurarBotonCopiar`, `confirmarCopia`, `copiar`, `seleccionarManual`, `mostrarErrorModal`, `ocultarErrorModal`, `validarAtajo`, `normalizarEnlaceModal`, `normalizarEnlace`, `sacarDelContexto`, `devolverAlContexto`, `cerrarEdicion`, `limpiarMensajeError`, `elevarSobreDialogo`, `reposicionarModal`, `cerrarConfirmacion`, `pedirConfirmacion`, `mostrarAvisoApp`, `anclaCercana`, `guardarScroll`, `restaurarScroll`, `guardarPosicionVentas`, `restaurarPosicionVentas`, `aplicar`, `cerrarModalAbono`, `abrirModalAbono`, `registrarAbono`, `configurarEliminar`, `cerrar`, `accion`, `cerrar`, `abrir`, `registrar`, `hayModal`, `aplicarEstado`
- **`ayuda.js`** · 127 líneas — Envío de reportes desde «Ayuda y comentarios» (SRS v2.0, sección 5.3).
  - Funciones: `escapar`, `cargarMisReportes`
- **`categorias.js`** · 526 líneas — Selector cerrado de categorías, vinculación con deudas y conservación de
  - Funciones: `idsDeudasActuales`, `datosFormulario`, `restaurarDatos`, `cerrar`, `abrir`, `alternar`, `sincronizar`, `sincronizar`, `vinculado`, `sincronizarValor`
- **`comentarios.js`** · 46 líneas — Cambio de estado en el panel administrativo de reportes (SRS v2.0, 5.5).
- **`consejero.js`** · 80 líneas — Tooltip táctil de la gráfica «Comparativa de cierre de deuda» (SRS v3.7).
  - Funciones: `mostrar`
- **`deudas.js`** · 378 líneas — Interacción de filas con modal centrado (SRS v1.9, secciones 2.3 y 3.3).
  - Funciones: `esMovil`, `sacarDeLaTabla`, `devolverALaTabla`, `sacarAtajoDelContexto`, `vigilarPortabilidad`, `cerrarOtras`, `conectarFilas`, `pendienteDeDeuda`, `numeroDeuda`, `validarPlan`, `numero`, `validarEdicion`
- **`dona.js`** · 122 líneas — Interacción de las gráficas tipo dona (capacidad de endeudamiento y cartera).
  - Funciones: `centro`, `mostrar`, `restaurar`, `iniciar`
- **`factura.js`** · 422 líneas — Factura y recibo de abono de OLB_BYTE como imagen PNG (ADR-50).
  - Funciones: `descargar`, `esperar`, `esperarImagen`, `protegerLogoVisible`, `mostrarAviso`, `montarHoja`, `crearPng`, `imagenDe`, `copiarImagen`, `mensajeDelEnlace`, `numeroDelEnlace`, `enviarPorWhatsapp`, `finalizar`, `descargarImagen`
- **`finanzas.js`** · 541 líneas — Mejora progresiva de "Mis Finanzas".
  - Funciones: `leerFormulario`, `pintarCampo`, `pintarDeduccion`, `pintarValorAuxilio`, `pintarErrores`, `pintarDetalle`, `pintarAuxilio`, `aplicarResultado`, `pintarTramos`, `pintarIncapacidad`, `pintarQuincenas`, `pintarTexto`, `calcular`, `programarCalculo`, `marcarCambios`, `aplicarPlantilla`
- **`incapacidades.js`** · 129 líneas — Cálculo automático del módulo de incapacidades (SRS v1.5).
  - Funciones: `fechasListas`, `reemplazar`, `actualizar`, `programar`
- **`moneda.js`** · 77 líneas — Formato de los campos de pesos mientras se escriben (SRS v1.9).
  - Funciones: `formatear`, `cuantosDigitos`, `posicionCursor`, `alEscribir`, `iniciar`
- **`olb_byte.js`** · 582 líneas — Formulario de venta de OLB_BYTE: forma de pago, productos guardados y totales.
  - Funciones: `numero`, `pesos`, `normalizarTelefono`, `leerCampos`, `escribirPanel`, `escribirEdicion`, `validarProducto`, `mostrarError`, `actualizarSubtotalPanel`, `hayDatosEnPanel`, `leerFila`, `escribirFila`, `actualizarVacia`, `recalcular`, `agregarFila`, `guardarProducto`, `habilitarPanel`, `sincronizarPago`, `mostrarNotaContactos`, `pegarNumero`, `agregarNumeroMovil`, `manejarBotonNumero`
- **`perfil.js`** · 138 líneas — Mejora progresiva del perfil financiero (SRS v1.2).
  - Funciones: `alternarSubgrupo`, `conocePorcentajes`, `actualizar`, `leerPorcentaje`, `escribirPorcentaje`
- **`presupuesto.js`** · 170 líneas — Mejora progresiva de "Gastos y Presupuesto" (SRS v1.3, bloque 3).
  - Funciones: `aNumero`, `formatear`, `usaAmbasQuincenas`, `duplicaElMonto`, `sincronizarModo`, `actualizarTotal`
- **`sw.js`** · 84 líneas — Service worker de la PWA.

#### `backend/app/static/js/vendor/`

- **`html-to-image.js`** · 3 líneas — # sourceMappingURL=html-to-image.js.map

#### `backend/app/templates/`

- **`_categorias.html`** · 126 líneas
- **`base.html`** · 214 líneas — Vista previa al compartir el enlace (WhatsApp, redes). La URL pública sale de APP_URL;
- **`dashboard.html`** · 96 líneas — Plantilla: Panel principal
- **`login.html`** · 95 líneas — Plantilla: Iniciar sesión
- **`olvide_contrasena.html`** · 35 líneas — Plantilla: Recuperar contraseña
- **`registro.html`** · 59 líneas — Plantilla: Crear cuenta
- **`restablecer_contrasena.html`** · 37 líneas — Plantilla: Nueva contraseña

#### `backend/app/templates/admin/`

- **`comentarios.html`** · 89 líneas — Plantilla: Comentarios y Reportes
- **`usuarios.html`** · 76 líneas — Plantilla: Usuarios

#### `backend/app/templates/ayuda/`

- **`_legal.html`** · 22 líneas
- **`index.html`** · 146 líneas — Plantilla: Ayuda y comentarios

#### `backend/app/templates/chancucos/`

- **`_dias.html`** · 31 líneas
- **`index.html`** · 228 líneas — Plantilla: Configurar Atajos de Pago

#### `backend/app/templates/componentes/`

- **`avatar.html`** · 21 líneas

#### `backend/app/templates/deudas/`

- **`index.html`** · 294 líneas — Plantilla: Registro y Detalles de deudas

#### `backend/app/templates/finanzas/`

- **`_capacidad.html`** · 143 líneas
- **`_gasto_fijo.html`** · 197 líneas
- **`_subnav.html`** · 27 líneas — Subnavegación interna del módulo "Mis Finanzas" (SRS v1.3, bloque 1).
- **`index.html`** · 741 líneas — Plantilla: Mis Finanzas

#### `backend/app/templates/gastos/`

- **`index.html`** · 136 líneas — Plantilla: Gastos

#### `backend/app/templates/historial/`

- **`imprimir.html`** · 41 líneas — Plantilla: Liquidación
- **`index.html`** · 114 líneas — Plantilla: Historial de Registros

#### `backend/app/templates/incapacidades/`

- **`index.html`** · 243 líneas — Plantilla: Incapacidades

#### `backend/app/templates/olb_byte/`

- **`_fragmento_factura.html`** · 3 líneas — Plantilla Jinja2
- **`_fragmento_recibo.html`** · 8 líneas — Plantilla Jinja2
- **`_hoja_factura.html`** · 270 líneas
- **`_recibo.html`** · 47 líneas
- **`_subnav.html`** · 30 líneas — Subnavegación de OLB_BYTE con el mismo componente que Mis Finanzas (subnav-finanzas).
- **`analitica.html`** · 356 líneas — Plantilla: Analítica
- **`cartera.html`** · 371 líneas — Plantilla: Cartera y liquidez
- **`cobro.html`** · 93 líneas — Plantilla: Gestionar cobro
- **`factura.html`** · 42 líneas — Plantilla: Factura No.
- **`garantias.html`** · 148 líneas — Plantilla: Garantías
- **`index.html`** · 477 líneas — Plantilla: OLB_BYTE
- **`pendientes.html`** · 119 líneas — Plantilla: Pendientes de pago
- **`recibo.html`** · 23 líneas — Plantilla: Recibo de abono · No.

#### `backend/app/templates/perfil/`

- **`index.html`** · 265 líneas — Saludo de onboarding: usa el alias capturado en el registro (SRS v1.2).

#### `backend/app/templates/presupuesto/`

- **`index.html`** · 813 líneas — Plantilla: Gastos y Presupuesto

#### `backend/app/templates/privado/`

- **`index.html`** · 40 líneas — Módulo privado: sólo un ADMIN_OLB llega a esta plantilla.

#### `backend/app/templates/trabajos/`

- **`index.html`** · 336 líneas — Plantilla: Trabajos Extras

<!-- INVENTARIO:FIN -->

---

## 5. Fichas por archivo

Cada ficha explica el propósito y lo que no es evidente: reglas, límites,
dependencias y por qué existe el archivo. El detalle línea a línea está en el
docstring de cada función.

### 5.1 Raíz de la aplicación

### `backend/app/__init__.py`

Marca el paquete `app` y declara la versión del proyecto. No contiene lógica.

### `backend/app/main.py`

Fábrica de la aplicación FastAPI (`crear_aplicacion`). Registra routers en orden,
monta estáticos, instala `MiddlewareSeguridad` y traduce las excepciones de
autorización: `_manejar_sesion_requerida` y `_manejar_onboarding` devuelven JSON
si la petición lo pide (`_pide_json`) y redirección con 303 si es HTML. Un
`ValueError` que se escape de una vista se responde con `_manejar_dato_invalido`:
400 con JSON o con una página mínima (`_pagina_dato_invalido`) que explica el dato
por corregir. Inicializa la base al arrancar y cierra `/docs` en producción.

### `backend/app/dependencias.py`

`UsuarioSesion.avatar_url` se llena desde la base en cada petición (SRS v1.8), así que un
cambio de foto se ve sin cerrar sesión.

Puente entre la cookie y el dominio. `_usuario_desde_token` decodifica el JWT y
relee el usuario de la base (un cambio de rol o de estado surte efecto sin
esperar a que caduque el token). `usuario_opcional` y `obtener_usuario_actual`
alimentan las vistas; `obtener_usuario_sin_onboarding` deja pasar solo el
onboarding; `exigir_administrador` implementa el 403 de OLB_BYTE y Chancucos.

### `backend/app/modelos.py`

`Usuario.avatar_url` (VARCHAR 500, nulable) guarda la URL de la foto de Google, nunca un
archivo. Las cuentas con contraseña local la dejan vacía y muestran iniciales (SRS v1.8).

Traducción del `diccionario_datos.md` a SQLAlchemy 2.x: 21 tablas con
`String(32)` como PK, dinero en `Numeric(14,2)` y enumeraciones como texto con
`CHECK`. Incluye `Deuda`/`PagoDeuda` (amortización v1.5), `ProyeccionAhorro` con
`quincena IN (1,2,3)` y las columnas heredadas de `deudas` que se conservan
nulas para no romper bases desplegadas. `nuevo_id()` genera UUID hexadecimal.

### 5.2 Núcleo (`core/`)

### `backend/app/core/__init__.py`

Paquete del núcleo. Agrupa configuración y utilidades sin dependencias de dominio.

### `backend/app/core/base_datos.py`

Base de datos dual (ADR-52). `_cargar_archivo_entorno` lee `backend/.env` sin sobrescribir
variables ya definidas (Render o las pruebas mandan). `_url_con_driver` convierte
`postgresql://` (Neon) a `postgresql+psycopg://`. Con PostgreSQL el motor usa
`pool_pre_ping`, `pool_recycle=300` y `prepare_threshold=None` (pooler de Neon). Las
funciones `_migrar_*` solo corren con SQLite.

`_migrar_columnas_usuarios` agrega `avatar_url` a `usuarios` solo si falta; se ejecuta
desde `inicializar_base_datos` y se probó dos veces sobre una copia de la base real (SRS v1.8).

Motor, sesión por petición y esquema. `crear_esquema` crea las tablas que falten;
las funciones `_migrar_*` ajustan bases antiguas de forma **idempotente**:

| Migración | Qué resuelve |
| --- | --- |
| `_migrar_columnas_perfil` | Columnas del onboarding v1.2 (alias, modalidad, quincenas). |
| `_migrar_columnas_gastos` | `Gasto.quincena` (1, 2 o `NULL`). |
| `_migrar_chancucos` | Reconstruye la tabla al atajo de 3 campos del SRS v1.3. |
| `_migrar_columnas_deudas` | `cuotas_pendientes`, `periodicidad` y `fecha_creacion`. |
| `_migrar_proyeccion_quincena` | Reconstruye metas + abonos para admitir `quincena = 3`. |
| `_migrar_saldos_incapacidad` | Columnas del corte por tramo mensual (v1.5). |

Activa `PRAGMA foreign_keys=ON` en SQLite y siembra las cuentas demo solo si
`usuarios` está vacía. `inicializar_base_datos` orquesta esquema, migraciones y
siembra.

### `backend/app/esquemas.py`

Capa Pydantic de validación de los formularios de gastos, deducciones fijas y
deudas. `validar_formulario` construye el esquema y convierte `ValidationError`
en el `ValueError` que ya entienden los routers. Todos los esquemas usan
`_categoria_cerrada`, que rechaza texto libre y reserva «Créditos y
Obligaciones» para el cálculo automático con deudas. `DeudaNueva` calcula
`tasa_implicita` con la simulación de `servicios/deudas.py`: es solo una
comprobación del plan, no se persiste ni se cobra (ADR-53). V3.9.3:
`validar_formulario` quita los prefijos técnicos de Pydantic y, para
`tasa_implicita`, devuelve únicamente el mensaje de negocio.

### `backend/app/core/categorias.py`

Fuente única del catálogo cerrado de ocho categorías y sus colores exactos para
la dona. `CATEGORIAS` fija nombres y hexadecimales; `normalizar_categoria`
traduce el texto heredado en modo laxo y lo rechaza en modo estricto;
`es_categoria_valida`, `color_de_categoria` y `lista_categorias` alimentan
backend y frontend. `es_credito` reconoce libranzas para clasificarlas en la
categoría 8 sin depender de `capacidad.py`. SRS v3.4: `COLORES_DONA` reúne diez
HEX únicos (ocho categorías, base mínima `#10B981` y dinero libre `#84CC16`);
`paleta_es_unica()` certifica que no hay repeticiones. Alimentación usa
`#F97316` para no chocar con la base mínima.

### `backend/app/core/config.py`

Parámetros de negocio y entorno, sin valores mágicos en el resto del código.
`ParametrosNomina` reúne horas mensuales (220 en 2026), porcentajes de salud/pensión,
factores de recargo, SMMLV, auxilio de transporte y porcentaje de incapacidad;
`ConfiguracionApp` agrupa entorno, clave secreta, duración de sesión, publicidad y
límites de login. `obtener_parametros`/`obtener_configuracion` cachean y aceptan
sobrescritura por entorno (`_decimal_desde_entorno`). El apoyo voluntario no tiene
datos de pago en el código: solo muestra el QR de Bre-B.

### `backend/app/core/numeros.py`

Conversión segura a `Decimal` y redondeo monetario. `redondear_dinero` usa
`ROUND_HALF_UP` a 2 decimales; `redondear_hora` a 2 decimales; `sumar_dinero`
evita el error de suma flotante. Todas lanzan `ValueError` con mensaje legible.

### `backend/app/core/texto.py`

Formato de presentación y parseo de entradas. `formatear_cop` produce
`$ 3.000.000` (omite `,00` en enteros); `formatear_porcentaje`, `formatear_fecha`
(«13 de noviembre de 2026») y `formatear_mes_anio`. `parsear_monto` acepta
`3.000.000`, `$ 3.000.000,50` y `1500.50`; `parsear_periodo_mes` interpreta
`AAAA-MM` y resuelve el mes actual si llega vacío. `parsear_porcentaje` acepta
«60», «60 %» y «60,5», y rechaza el punto decimal ambiguo.

### `backend/app/core/seguridad.py`

Hash PBKDF2-HMAC-SHA256 con sal por usuario y JWT HS256 implementado con
`hmac`/`base64url` (sin dependencias externas). `crear_token` firma
`sub` + expiración; `decodificar_token` valida firma y vigencia y lanza
`TokenInvalido`. `verificar_contrasena` compara en tiempo constante.
`decodificar_token` rechaza los tokens con claim `proposito`, así que un enlace de
recuperación nunca abre sesión. `crear_token_recuperacion` y
`decodificar_token_recuperacion` emiten y validan enlaces con `proposito="recuperacion"`,
una `huella` de la contraseña vigente y 15 minutos de vigencia. Al cambiar la
contraseña la huella deja de coincidir, así que el enlace no se reutiliza.

### `backend/app/core/limitador.py`

Ventana deslizante de intentos fallidos de login en memoria. `LimitadorIntentos`
cuenta por clave (correo + IP), bloquea al superar el máximo y libera al vencer la
ventana. `_RegistroIntentos` guarda marcas de tiempo; el estado se reinicia con el
proceso, suficiente para una instancia.

### `backend/app/core/middleware.py`

La CSP de imágenes es `img-src 'self' data: https://*.googleusercontent.com` para mostrar
la foto de Google sin abrir otros orígenes (SRS v1.8).

`MiddlewareSeguridad` hace dos cosas: rechaza `POST` cuyo `Origin` no coincida con
el host (CSRF por origen, sin token en formularios) y añade cabeceras de seguridad
(CSP, `X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options`). Exime las
rutas de estáticos y `/salud`.

### 5.3 Routers

### `backend/app/routers/__init__.py`

Paquete de routers; no registra nada por sí mismo (lo hace `main.crear_aplicacion`).

### `backend/app/routers/vistas.py`

`/salud` ejecuta `SELECT 1` contra la base y responde 200 (`base_datos: ok`) o 503 si no
contesta, para que Render no envíe tráfico a una instancia sin base (SRS v1.8, ADR-52).

`iniciales_alias` obtiene las dos iniciales del alias para el círculo de respaldo y se
registra como filtro `iniciales` de Jinja (SRS v1.8).

Navegación principal. `contexto_base` arma el contexto común (usuario, rol,
publicidad, ruta activa) que consumen todas las plantillas; `ver_dashboard`
muestra las 4 tarjetas según rol; `verificar_salud` responde `/salud` para
monitoreo. Aquí viven también la instancia de `Jinja2Templates`, los filtros
(`cop`, `porcentaje`, `fecha_larga`) y los globales de plantilla. `contexto_base` también
entrega `cafe` (monto y QR de Bre-B en data URI) para el apoyo voluntario. V3.9.3:
la tarjeta de OLB_BYTE llevaba un escaparate SVG; en **v3.9.5** se sustituye por
`icono_archivo = "img/icono_OLBBYTE.png"`, que `dashboard.html` renderiza como
`<img>` de 20×20 con `object-fit: contain`, igual que los íconos vecinos. El
ícono PWA neón azul no se modifica.

### `backend/app/routers/auth.py`

El callback de Google guarda la foto (`picture`) con `usuarios.actualizar_avatar` antes de
abrir la sesión. Los registros con contraseña no pasan por ahí y conservan el avatar vacío
(SRS v1.8).

Login, registro y salida. `procesar_login` aplica el limitador
(`_clave_intento`), verifica la contraseña con el servicio de usuarios, emite el
JWT y lo guarda en la cookie `sesion` (`_establecer_cookie`: `HttpOnly`,
`SameSite=Lax`, `Secure` en producción). Registra auditoría de éxito y fallo;
`cerrar_sesion` borra la cookie. El registro valida correo único y fuerza el rol
`USER_FINANZAS`.

Recuperación de contraseña (SRS v1.8, ADR-51): `procesar_olvide_contrasena`
(`POST /olvide-contrasena`) responde siempre con el mismo mensaje neutro y solo envía el
enlace si la cuenta existe y está activa; registra `RECUPERACION_SOLICITADA` en
auditoría. `ver_restablecer_contrasena` y `procesar_restablecer_contrasena` validan el
enlace (`_cuenta_del_enlace`), exigen 8 caracteres y coincidencia, cambian la contraseña
y redirigen a `/login?restablecida=1` con auditoría `CONTRASENA_RESTABLECIDA`. Los enlaces
usan `APP_URL` si está configurada.

### `backend/app/routers/perfil.py`

Onboarding y mantenimiento del perfil financiero. `ver_perfil` muestra el
formulario (con modo bienvenida); `guardar_perfil` valida sueldo, modalidad y
quincenas —caso A: porcentajes Q1/Q2 y quincena de deducciones; caso B: neto sin
deducciones y porcentajes por descarte— y redirige a `/?guardado=1`.
`cambiar_contrasena` exige la actual y audita el cambio.

### `backend/app/routers/admin.py`

Administración de cuentas, exclusiva de `ADMIN_OLB`. `ver_usuarios` lista cuentas;
`cambiar_rol_usuario` y `cambiar_estado_usuario` impiden que el administrador se
degrade o se desactive a sí mismo. Cada cambio queda en auditoría.

### `backend/app/routers/finanzas.py`

El router más grande: calculadora, guardado e historial.

- `_leer_entradas` normaliza el formulario a `EntradaFinanzas` (`_texto`,
  `_entero`, `_descuento_por_fechas` para derivar días de incapacidad).
- `_liquidar` llama al motor de nómina y a las quincenas; `_deducciones_segun_quincena`
  imputa el 8 % a la quincena del perfil.
- `_fijas_del_periodo`, `_total_fijas` y `_total_deducciones_ley` construyen la
  **caja única de deducciones** del SRS v1.5: salud + pensión + incapacidad +
  deducciones fijas.
- `_detalle_formateado` publica el desglose sin `factor` (tabla compacta sin
  scroll horizontal); `_detalle_incapacidad_json` y `_datos_formateados` alimentan
  la reactividad.
- `calcular_finanzas_json` responde a `finanzas.js`; `guardar_liquidacion`
  persiste el periodo y sus horas extra.
- `ver_historial`, `exportar_historial_csv`, `imprimir_periodo` y
  `eliminar_periodo` cierran el ciclo; `_filas_historial` agrega fecha de guardado
  y total de extras.

### `backend/app/routers/gastos.py`

Presupuesto de gastos fijos y variables. `ver_gastos` lista con totales por
categoría y por quincena; `crear_gasto`, `editar_gasto` y `eliminar_gasto` validan
monto y fecha (`_parsear_fecha`) y auditan. La edición conserva la quincena
asignada (SRS v1.3).

### `backend/app/routers/incapacidades.py`

Formulario de incapacidades y su liquidación. `_validar` exige fechas coherentes
y origen válido; `_contexto` calcula el descuento del mes **por tramos** (v1.5) y
muestra los días cubiertos; `calcular_incapacidad_formulario` responde al cálculo
en vivo de `incapacidades.js`; `guardar_incapacidad` persiste y
`eliminar_incapacidad` revierte.

### `backend/app/routers/presupuesto.py`

Planificador de ahorro, metas y deducciones fijas. `crear_proyeccion` admite
`quincena` 1, 2 o 3 («Ambas quincenas»); `registrar_abono` actualiza el abono del
mes (uno por mes y meta); `crear_deduccion_fija`, `editar_deduccion_fija` y
`eliminar_deduccion_fija` gestionan los descuentos de nómina del SRS v1.4.
`_fecha_del_formulario` interpreta `type="date"` y `_contexto` reúne diagnóstico,
metas y deducciones.

### `backend/app/routers/deudas.py`

Seis campos, sin abonos manuales. `ver_deudas` ejecuta
`aplicar_cuotas_vencidas` **antes** de renderizar e informa cuántas se aplicaron;
`crear_deuda` valida y audita; `eliminar_deuda` borra la deuda y sus pagos en
cascada. La proyección de cada deuda se arma en `_contexto` partiendo del último
pago (o de la creación). SRS v3.0: `crear_deuda` recibe el campo oculto `volver`
y lo conserva en el redirect, para que el enlace de retorno siga bajo «Nueva
deuda» después de guardar.

### `backend/app/routers/chancucos.py`

Panel de atajos de pago (solo `ADMIN_OLB`). `ver_chancucos` lista con favoritos
primero; `crear_chancuco`, `alternar_favorito` y `eliminar_chancuco` auditan. Se
muestra embebido en Mis Finanzas y con página propia en «Configurar Atajos».

### `backend/app/routers/trabajos.py`

Ingresos independientes. `crear_trabajo` registra concepto, cliente, monto y
fecha; `cambiar_estado` alterna `PENDIENTE`/`COBRADO`; `eliminar_trabajo` borra;
`_contexto` entrega resumen y listado.

### `backend/app/routers/olb_byte.py`

Módulo comercial. `ver_olb_byte` compone ventas, cartera y resumen con semáforo de
garantía; `registrar_venta` lee las filas del formulario (`_filas_del_formulario`,
`_lineas_desde_filas`) y repuebla el formulario si hay error; `registrar_abono`,
`anular_venta` y `registrar_devolucion` aplican los cobros y devoluciones;
`ver_factura` renderiza la factura imprimible. Todo el módulo exige `ADMIN_OLB`.

### `backend/app/routers/pwa.py`

Sirve `manifest.webmanifest`, el service worker (`Cache-Control: no-cache` para
que la actualización llegue) y el favicon.

### `backend/app/routers/feedback.py`

API del módulo «Ayuda y comentarios» (SRS v2.0, Fase A). `enviar_feedback` recibe
el reporte en JSON y detecta el dispositivo desde el `User-Agent`, sin fiarse del
cliente. `contar_feedback_pendiente` alimenta el badge circular de la tarjeta
administrativa; `listar_feedback` y `actualizar_estado_feedback` gestionan el
panel. Las tres rutas de administrador exigen `ADMIN_OLB` en servidor. Además
sirve `GET /admin/comentarios`, la vista HTML del panel con el contador. SRS v3.0:
`PATCH /api/feedback/{id}` persiste estado y `fecha_resolucion`, y
`GET /api/feedback/mios` entrega al usuario sus propios tickets.

### `backend/app/routers/ayuda.py`

Vista «Ayuda y comentarios» (SRS v2.0, sección 5). `ver_ayuda` entrega la
versión de la app, los tipos de reporte y el catálogo de módulos públicos del
servicio de soporte; OLB_BYTE y facturación quedan fuera. El envío lo hace la
API de `routers/feedback.py`.

### 5.4 Servicios de dominio

### `backend/app/servicios/__init__.py`

Paquete de servicios; documenta la convención: funciones puras, sin FastAPI, que
reciben `Session` solo cuando necesitan persistir.

### `backend/app/servicios/nomina.py`

Motor salarial colombiano. `calcular_valor_hora_ordinaria` divide el básico entre
220 h (2026); `calcular_deducciones_ley` aplica 4 % + 4 % sobre el **devengado**
(básico + extras − incapacidad, ADR-19); `calcular_recargo`/`calcular_recargos`
aplican la matriz de siete factores (1,25 / 1,75 / 2,15 / 2,65 / 0,35 / 0,90 /
1,25, ADR-77);
`calcular_total_devengado` suma todo; `liquidar_periodo` devuelve
`LiquidacionNomina` con deducciones, auxilio y neto. `_validar_no_negativo`
centraliza el rechazo de entradas.

### `backend/app/servicios/auxilio.py`

Tope de 2 SMMLV. `evaluar_auxilio_transporte` anula el auxilio cuando
`básico + recargos` supera el tope parametrizable y devuelve `EvaluacionAuxilio`
con el monto, la diferencia hasta el tope y el mensaje del SRS.
`evaluar_auxilio_salarial` es la variante que usa el panel de quincenas.

### `backend/app/servicios/incapacidad.py`

Reparto de una incapacidad por mes calendario. `calcular_incapacidad` valida el
rango (`_validar_rango`), cuenta los días una sola vez y aplica la regla 100 %
(días 1–2) / 66,67 % (desde el día 3) sobre la incapacidad **completa**;
`liquidar_mes_incapacidad` recorta el tramo que cae en el mes pedido. Los
dataclasses `TramoMensual`, `SaldoIncapacidad`, `LiquidacionIncapacidad` y
`ResultadoMesIncapacidad` describen el resultado sin tuplas sueltas.

### `backend/app/servicios/registro_incapacidades.py`

Persistencia y consulta por mes. `registrar_incapacidad` guarda el rango;
`tramos_del_mes` devuelve los tramos que tocan un mes concreto y
`descuento_del_mes` suma su descuento, que es lo que consume Mis Finanzas (v1.5,
sin rollover). `listar_incapacidades` y `eliminar_incapacidad` completan el CRUD.

### `backend/app/servicios/perfiles.py`

Perfil financiero 1:1. `obtener_perfil`/`perfil_configurado` resuelven el
onboarding; `validar_quincenas` garantiza que los porcentajes sumen 100;
`calcular_quincenas_desde_neto` deriva los porcentajes por descarte cuando el
usuario solo conoce el neto de una quincena; `guardar_perfil` hace upsert;
`porcentajes_quincena` y `sueldo_del_periodo` entregan lo que necesitan la
liquidación y las quincenas. SRS v1.9: `parsear_dia_quincena` acepta solo dígitos
de 1 a 31; `validar_dias_quincena` exige que la quincena 2 sea posterior a la 1;
`dias_quincena` devuelve 15 y 30 cuando no hay dato, y `etiquetas_quincena`
arma los rótulos «Quincena N · día X» que usan los formularios.

### `backend/app/servicios/quincenas.py`

Panel izquierdo de Mis Finanzas. `resumen_quincenas` reparte el sueldo por los
porcentajes del perfil, suma recargos en la quincena configurada, resta
incapacidad, deducciones de ley (solo en la quincena marcada), fijas y gastos, y
devuelve una `ResumenQuincena` por pago con saldo libre. `_etiqueta` nombra cada
pago y `_a_decimal` normaliza entradas. SRS v2.0: `gastos_vinculados` expone los
gastos con `id_deuda` para que se pinten en la lista sin volver a sumarlos a
`gastos` (anti-duplicación).

### `backend/app/servicios/gastos.py`

CRUD y agregados de gastos. `crear_gasto` valida monto/fecha y
`_normalizar_quincena` acepta 1, 2 o `NULL` («todo el mes»). `listar_gastos`,
`total_gastos_mes`, `total_gastos_quincena`, `total_gastos_periodo` y
`resumen_por_categoria` alimentan vistas y diagnóstico; `actualizar_gasto`
mantiene la quincena al editar. SRS v2.0 (Fase A): `listar_gastos` carga
`Gasto.deuda` con `joinedload` (un `LEFT JOIN`, sin duplicar filas) y
`serializar_gasto`/`listar_gastos_con_deuda` exponen `cuota_mensual` y `acreedor`
en los GET, incluidos los registros con `id_deuda`. La anti-duplicación sigue en
`capacidad.py` y `quincenas.py` vía `excluir_vinculados=True`.

### `backend/app/servicios/deducciones_fijas.py`

Descuentos de nómina del SRS v1.4. `crear_deduccion`, `actualizar_deduccion` y
`eliminar_deduccion` validan concepto, valor y quincena; `listar_deducciones` y
`total_por_quincena` entregan lo que resta la caja única de deducciones. SRS v1.9
(ADR-56): una deducción puede vincularse a una deuda mensual activa (`id_deuda`); en
ese caso su valor es la cuota de la deuda. `listar_vigentes` deja fuera las vinculadas
a deudas pagadas, `vinculadas_activas` y `cuota_de_vinculadas` alimentan la capacidad
y el diagnóstico sin contar la cuota dos veces.

### `backend/app/servicios/periodos.py`

Historial de liquidaciones. `guardar_liquidacion` hace upsert del periodo y
reemplaza sus horas extra; `obtener_periodo` y `listar_periodos` los recuperan con
`horas_del_periodo`; `eliminar_periodo` borra en cascada. Ya **no** hay rollover
de incapacidades: el descuento se recalcula por tramo (ADR-20).

### `backend/app/servicios/ahorro.py`

Planificador de metas. `crear_proyeccion` valida duración (`_validar_duracion`),
meses (1–600, SRS v1.6) y quincena (`QUINCENAS_VALIDAS = (1, 2, 3)`);
`etiqueta_quincena` y `valor_por_pago` traducen `3` a «Ambas quincenas» y a la
mitad de la cuota. SRS v1.7: `valor_por_pago` respeta `modo_ambas` (`DIVIDIR` o
`DUPLICAR`) y `diagnostico` suma `extras_mes` de Trabajos Extras al `disponible`.
SRS v1.6: el abono ya no se digita; `resumen_metas` lo lee de
los pagos y clasifica cada mes (`MesMeta.estado`: `registrado`, `no_pagado` o
`pendiente`) con `_estado_mes`. `saldo_libre_total` y `diagnostico` disparan la
alerta de liquidez (`UMBRAL_ALERTA = 300000`) y devuelven `metas_mes` para el
banner.

### `backend/app/servicios/pagos_metas.py`

Metas como gastos fijos con check (SRS v1.6). `asegurar_gastos_de_metas` crea un
gasto por meta y quincena (`Ambas quincenas` = dos mitades) desde el mes visible:
todo el periodo que escogió el usuario (meses o años). Si un abono
heredado existe, el gasto nace pagado con ese monto. `marcar_pagado` registra el ✔ (irreversible); `limpiar_checks` oculta los
✔ de una quincena sin tocar los pagos (la quincena 1 incluye los gastos del mes).
`sincronizar_abono` recalcula el abono como suma de los `monto_pagado` de los pagos
marcados. `quitar_gasto` decide la × : un gasto de meta se inhabilita 15 días en su
quincena (`inhabilitar_gasto`, no suma en el saldo) y su pago se retira; un gasto
manual se elimina. `registrar_abono_manual` abona un monto en un pago saltado.
`propagar_valor` lleva el valor editado a los meses posteriores no pagados de la
misma quincena. La meta solo se borra desde Gastos y Presupuesto (cascada).

### `backend/app/servicios/deudas.py`

Amortización automática sin intereses (SRS v1.8, ADR-53). `validar_plan` exige que
`cuota × cuotas` reconstruya el total adeudado con tolerancia de un peso por
cuota; `crear_deuda` valida los seis datos; `aplicar_cuotas_vencidas` avanza el
calendario desde el último pago y registra cada cuota en `PagoDeuda` mediante
`_aplicar_pago`, donde la cuota abona capital completo y la última absorbe el
redondeo y deja el saldo en cero. `proyeccion_deuda` lista las cuotas futuras,
`cuota_mensual_equivalente` mensualiza la quincenal y `resumen_deudas` totaliza la
cartera.

### `backend/app/servicios/capacidad.py`

Capacidad de endeudamiento y proyección a doce meses (SRS v1.7, bloque F; base
mínima en v1.8). `capacidad_endeudamiento` suma el ingreso de las quincenas y los
extras cobrados, resta gastos fijos, deducciones y cuota mensual de deudas;
`repartir_libre` separa el libre en `BASE_MINIMA_LIQUIDEZ` ($300.000) y el
disponible para abonar. `_repartir_arcos` dibuja cuatro arcos («Gastos fijos»,
«Cuota de deudas», «Base mínima de liquidez», «Disponible para abonar») que
siempre cierran en 100,0 %. El semáforo usa el porcentaje de deuda sobre el
ingreso (`UMBRAL_VERDE = 20`, `UMBRAL_AMBAR = 35`). `deudas_por_terminar` lista
las deudas con tres cuotas o menos y su fecha de cierre; `proyeccion_capacidad`
simula doce meses en los que la cuota baja cuando cada deuda termina. No escribe
en la base de datos. SRS v3.4: `_arcos_categoria` y `_repartir_arcos` toman todos
los colores del catálogo centralizado (`catalogo.COLOR_*`), sin CSS variables
hardcodeadas, de modo que dentro de cada dona no se repite ningún HEX.

### `backend/app/servicios/consejero.py`

Consejero del excedente (SRS v1.8, ADR-53). Solo se activa si el libre supera
`BASE_MINIMA_LIQUIDEZ = 300000`; trabaja con el remanente. Con deudas simula doce
meses de cuotas mínimas frente a un escenario que aplica todo el excedente y
ordena por liberación de flujo de caja (`_ordenar`): primero la deuda que el
excedente cancela completa con más cuotas por delante; si no alcanza, la de menor
saldo. Sin deudas dirige el excedente a las metas (`ahorro.resumen_metas`) o
sugiere crear una. `_serie_comparada` entrega las doce filas de la gráfica base
frente a optimizado. No escribe en la base. SRS v3.7: `_datos_cierre` produce
el diccionario `cierre` de la gráfica unificada (puntos de doce meses, índice
`mes_libre_index`, meses ahorrados, fecha de cierre y totales). Si ambas curvas
llegan a cero en el año, el ahorro mostrado es la cuota liberada por los meses
ahorrados; nunca se inventan intereses.

### `backend/app/servicios/comercial.py`

Ventas a crédito de OLB_BYTE sin inventario (ADR-35). `registrar_venta` recibe
`LineaVenta`, copia nombre, costo y precio en la orden, asigna el consecutivo
`numero_orden` y suma la compra a la deuda con el proveedor. `registrar_abono`
aplica abonos con fecha y hora; `anular_venta` anula con motivo y registra la
devolución; `registrar_devolucion` completa devoluciones pendientes.
`resumen_cartera` calcula cartera, deuda, caja y efectivo libre; `estado_garantia`
da el semáforo; `enlace_whatsapp_factura`, `enlace_whatsapp_cobro` y
`enlace_whatsapp_recibo` arman los mensajes con el celular normalizado. `buscar_cartera`
filtra los pendientes, `abonos_de_venta` y `obtener_abono` alimentan los recibos y
`ahora_tienda` fija todas las fechas en hora de Colombia. `registrar_garantia` abre un reclamo,
`actualizar_estado_garantia` avanza su trámite, `garantia_vigente_al_reclamo` compara
con la fecha de fin de la orden y `ranking_fallas` calcula la tasa por producto.
`clasificar_saldo` aplica el signo y color de RF-10, `tabla_balance` arma las filas del balance y `segmentos_dona`
calcula los arcos de la gráfica (RF-11).

### `backend/app/servicios/usuarios.py`

`sembrar_demostracion` no crea cuentas con contraseñas conocidas cuando `ENTORNO=produccion`
(ADR-52). Fuera de producción sigue creando las cuentas demo en una base vacía.

`url_avatar_valida` acepta solo HTTPS en `*.googleusercontent.com` de hasta 500 caracteres.
`actualizar_avatar` guarda la foto que informa Google o deja `NULL` si no es válida; lo
llama el callback de Google en cada inicio de sesión (SRS v1.8).

Repositorio de cuentas sobre la base. `sembrar_demostracion` crea las cuentas demo
solo si no hay usuarios; `autenticar` verifica hash y estado; `crear_usuario`
valida correo (`correo_valido`) y unicidad; `actualizar_alias`,
`cambiar_contrasena`, `cambiar_rol` y `cambiar_estado` cubren perfil y
administración. `listar_usuarios` ordena para la vista de admin.

### `backend/app/servicios/chancucos.py`

Atajos de pago con tres datos. `_validar_url` acepta solo `http(s)`;
`crear_chancuco`, `listar_chancucos`, `alternar_favorito` y `eliminar_chancuco`
completan el CRUD. El favorito se ordena primero en la vista.

### `backend/app/servicios/trabajos.py`

Trabajos extras. `crear_trabajo` registra el ingreso, `cambiar_estado` alterna
pendiente/cobrado, `eliminar_trabajo` borra y `resumen_trabajos` suma pendientes y
cobrados por periodo. En frecuencia quincenal, `reparto_quincenal` toma la quincena
escrita y calcula la otra como sueldo menos esa cantidad (las dos suman el sueldo);
`valor_del_pago` indica el monto de cada pago generado.

### `backend/app/servicios/auditoria.py`

Bitácora de acciones sensibles. `registrar` inserta el evento (usuario, acción,
tabla, detalle) y `listar_eventos` los devuelve para consulta. Se llama desde los
routers tras cada cambio relevante.

### `backend/app/servicios/feedback.py`

Reportes de soporte (SRS v2.0, Fase A). `detectar_dispositivo` lee el
`User-Agent`; `crear_reporte` guarda tipo, módulo público, descripción,
dispositivo y un snapshot de alias/correo con estado «Pendiente».
`contar_pendientes`, `listar_reportes`, `cambiar_estado` y `serialize` sirven al
panel administrativo. El catálogo de módulos excluye OLB_BYTE y facturación por
la regla de separación estricta por rol.

### 5.5 Estáticos (`static/`)

### `backend/app/static/css/estilos.css`

Clases `.avatar`, `.avatar--compacto`, `.avatar--destacado` y `.avatar__iniciales`: círculo
con degradado `#0066cc` a `#00a8ff` y tamaños de 36 px y 96 px (SRS v1.8). `sw.js` en `olb-finanzas-v30`.

Única hoja de estilos. Define la paleta oficial en `:root`, componentes
(tarjetas, paneles, tablas, botones, formularios), las dos rejillas de Mis
Finanzas (`rejilla-finanzas` y `--5050`), la tabla compacta del desglose y las
reglas móviles: submenú 2 × 2 a 640 px, `.fila-campos` a una columna, paneles a
16 px y botones a ancho completo. Desde SRS v1.9, 4.1, la utilidad
`.modal-centrado` y todo `details.edicion-gasto--modal[open]` usan
`position: fixed; inset: 0; display: flex; align-items: center;
justify-content: center; z-index: 50; padding: 1rem`, con la tarjeta como
elemento flex centrado y scroll propio; los `<dialog>` nativos conservan el
centrado del navegador con el mismo nivel de capa. El recibo de abono usa fondo
`#f8fafc`, texto `#111827` y valores verdes `#16a34a` con cabecera azul.
Incluye estilos de impresión de la factura y
del historial.

### `backend/app/static/js/deudas.js`

Interacción de filas con modal centrado (SRS v1.9, secciones 2.3 y 3.3). En
escritorio los botones lápiz y × van al final de cada fila. En móvil se ocultan
por CSS y un toque en `tr[data-deuda-fila]` o en `li[data-deduccion-fila]` abre
el mismo `<details class="edicion-gasto--modal">`: `esMovil` limita el
comportamiento a 640 px, `conectarFilas` conecta ambas filas, `cerrarOtras`
evita apilar ventanas y se ignoran los clics dentro de formularios o controles.
El cierre con «Cancelar», Escape o fondo lo hace `app.js`. Se carga en deudas y
presupuesto, y se cachea en `sw.js`. SRS v2.0 (sección 2.2) y v3.0 (punto 1): al
cargar la vista lee `misfinanzas_pending_debt_link` y ajusta la etiqueta del
enlace de regreso con `origin_label`, sin alterar el `volver` que pinta el
servidor. **Nunca elimina la clave**: solo el formulario de origen la borra tras
restaurar sus datos, así que el enlace sigue vivo después de guardar la deuda.
SRS v3.9.1: `numeroDeuda` y `validarPlan` bloquean «Guardar deuda» en vivo cuando
`cuota × cuotas < total`, con la alerta roja del propio formulario.

### `backend/app/static/js/consejero.js`

Tooltip táctil de la comparativa de cierre de deuda (SRS v3.7). Escucha los
botones de mes del bloque SVG y muestra el salto «Base / Opt» del mes tocado o
sobrevolado. Las cifras y la curva las calcula Python; aquí solo se muestra el
detalle, sin lógica financiera.

### `backend/app/static/js/categorias.js`

Selector cerrado de categorías y vinculación con deudas (SRS v1.9, Paso 2). La
entrada `data-categoria-entrada` es de solo lectura: al hacer clic en ella o en
`data-categoria-boton` se abre `data-categoria-lista` con las ocho opciones; al
elegir una se pega su nombre exacto. `data-vinculo-condicional` aparece solo con
«Créditos y Obligaciones»: con SI habilita `name="id_deuda"` y con NO inhabilita
guardar y muestra el acceso rápido a deudas. Al pulsar «Ve a registrar la deuda»
se guardan los campos y el módulo de origen en `sessionStorage`; al volver con
`?guardado_deuda=1` se restauran, se marca SI y se selecciona la deuda recién
creada. Los formularios con `data-guardar-formulario` también conservan valores
ante `?error…`. Sin JavaScript el servidor vuelve a validar todo. SRS v2.0: el
ciclo usa una sola clave `misfinanzas_pending_debt_link` con
`{origin_module, origin_label, origin_destino, form_data}` (la clave heredada
`deuda-origen:` se sigue escribiendo como respaldo); al elegir deuda se copia su
`data-cuota` al campo valor, que queda `readOnly` mientras haya vínculo. SRS v3.0:
ese campo lleva la clase `campo__control--bloqueado` (gris y candado) y la clave
se borra solo tras restaurar el origen. SRS v3.1: el payload incluye
`origin_objetivo` con el ID del bloque; tras restaurar, `requestAnimationFrame` +
150 ms preceden un `scrollIntoView` suave, un resaltado de 1,5 s
(`retorno-resaltado`) y el foco en el selector de deudas. SRS v3.4: el payload
lleva `debt_created: false`; el flag `misfinanzas_scroll_to_new_debt` baja a
«Nueva deuda»; solo se marca SI si la deuda se creó realmente, y el campo Valor
se bloquea/desbloquea al instante según la categoría.

### `backend/app/static/js/moneda.js`

Formato de pesos en los campos marcados con `data-moneda` (SRS v1.9). Al escribir o
pegar, `formatear` agrupa los miles con punto y deja la coma para los centavos (hasta
dos). `posicionCursor` conserva el cursor por la cantidad de dígitos que quedan a su
derecha, así que insertar en medio funciona. Porcentajes y cantidades no llevan la
marca y no cambian. El valor inicial de esos campos también se formatea al cargar.

### `backend/app/static/js/dona.js`

Interacción de las donas de capacidad y de cartera (SRS v1.9). Al pasar el cursor,
tocar o enfocar un arco, el centro muestra su nombre, porcentaje y valor; al pasar
sobre la leyenda se resalta el arco. `mostrar` escribe el centro y marca el arco
activo, `restaurar` vuelve a los textos por defecto guardados en `data-*-defecto`, e
`iniciar` conecta los eventos de cada `[data-dona-contenedor]`. En celular, el toque
fija el arco: tocar otro arco cambia la selección y tocar el mismo lo quita; tocar el
centro o el fondo no cambia nada (los arcos solo reciben el toque sobre el trazo). Sin
JavaScript, la dona conserva su leyenda y sus `<title>`.

### `backend/app/static/js/app.js`

Mejoras globales: `copiar` usa la API de portapapeles con respaldo
(`seleccionarManual`), la delegación `data-copiar` pinta «¡Copiado!», las filas
plegables y el registro del service worker. `cerrarEdicion` descarta la edición
en línea desde «Cancelar», el fondo oscuro móvil o la tecla Escape. Antes de
enviar, revisa los campos `inputmode` y `type="number"` y detiene el envío con un
aviso si traen letras. Sin dependencias. SRS v3.9.1: `pedirConfirmacion` y
`mostrarAvisoApp` sustituyen por completo a los diálogos nativos del navegador,
con los modales oscuros `#modal-confirmacion` y `#modal-aviso` de `base.html`;
también abre el calendario con `showPicker()` al hacer clic en un `input[type=date]`
en escritorio.

### `backend/app/static/js/finanzas.js`

Reactividad de la calculadora. `leerFormulario` serializa entradas;
`programarCalculo` aplica debounce de 150 ms y `calcular` hace `fetch` a
`/finanzas/calcular`; `pintarCampo`, `pintarDeduccion`, `pintarValorAuxilio`,
`pintarTramos`, `pintarIncapacidad`, `pintarQuincenas`, `pintarDetalle` y
`aplicarResultado` escriben la respuesta sin recrear la página. `marcarCambios`,
`aplicarPlantilla`, `copiarAlPortapapeles` y `prepararCopiadoRapido` cubren el
aviso de cambios sin guardar y los atajos.

### `backend/app/static/js/incapacidades.js`

Cálculo automático del formulario de incapacidades. `fechasListas` comprueba el
rango, `actualizar` pide el cálculo y `programar` lo debounce; `reemplazar` pinta
días, descuento y tramos. Elimina la necesidad de escribir los días a mano.

### `backend/app/static/js/perfil.js`

Onboarding reactivo. `alternarSubgrupo` muestra/oculta el bloque quincenal según la
modalidad y `conocePorcentajes` alterna entre el caso A (porcentajes) y el caso B
(neto); `actualizar` mantiene los avisos de suma 100 %. `leerPorcentaje` y
`escribirPorcentaje` trabajan con «%» y coma decimal, y el complemento
autocompletado se escribe como «40 %».

### `backend/app/templates/olb_byte/pendientes.html`

Clientes con saldo por cobrar (RF-06). Tabla compacta con número, cliente, celular,
fecha, total, abonado y saldo, y un único botón por fila: «Añadir pago o gestionar
cobro», que abre la página de cobro. En celular cada cliente se muestra como tarjeta.
El filtro `q` busca por cliente, celular o número de orden.

### `backend/app/servicios/factura_pdf.py`

Si un logo no se encuentra en `assets/`, `logo_como_data_uri` lo registra como aviso en el log
del servidor (`app.factura`), para revisar en Render que los archivos llegaron.

Factura PDF de OLB_BYTE (RF-18, ADR-36). `datos_factura` reúne líneas, filas vacías para
completar diez, totales, garantía, medios de pago y el nombre del archivo; rechaza
órdenes con más de diez productos. `logo_como_data_uri` embebe los logos de `assets/`.
`nombre_archivo` arma `Factura_OLB_BYTE_No_{numero}_{cliente}.pdf` sin tildes.
`datos_factura` valida el máximo de diez productos. Desde ADR-50 ya no hay PDF en el
servidor: la imagen se genera en el navegador (ver `static/js/factura.js`).

### `backend/app/servicios/recibo_imagen.py`

Datos del recibo de abono compartido como imagen (ADR-50). `nombre_archivo_recibo` arma el
nombre del PNG, `texto_compartir_recibo` el mensaje de WhatsApp y `datos_recibo` reúne saldo,
abono y datos de la orden. La imagen se captura en el navegador.

### `backend/app/servicios/acceso_google.py`

Inicio de sesión con Google por OAuth 2.0 (ADR-48) con `urllib` y sin dependencias nuevas.
`google_activo` indica si hay credenciales; `url_autorizacion` arma la URL de consentimiento;
`intercambiar_codigo` cambia el código por el perfil verificado. Usa el tiempo de espera
`TIEMPO_ESPERA_SEGUNDOS`.

### `backend/app/servicios/correo.py`

Envío de correos por SMTP estándar (`smtplib`, SRS v1.8). `enviar_correo` usa `SMTP_HOST`,
`SMTP_PORT`, `SMTP_USER`, `SMTP_PASS` y `SMTP_FROM`; en `SMTP_PORT=465` usa SSL, si no
STARTTLS. Sin SMTP en desarrollo registra el contenido en el log para probar el flujo; en
producción solo registra el fallo, sin contenido ni enlaces. SRS v3.0: timeout de
10 s, alias `SMTP_PASSWORD`/`FROM_EMAIL`, `configuracion_valida()` y
`enviar_recuperacion()` con registro explícito de éxito o error SMTP. SRS v3.1:
`_enviar_por_api` prioriza Resend → Brevo → SendGrid por HTTPS con `urllib.request`
(sin dependencias nuevas) y registra el código HTTP exacto; si no hay API, usa
SMTP SSL en 465 con timeout de 15 s (Gmail con contraseña de aplicación) o
STARTTLS en el puerto configurado.

### `backend/app/static/js/factura.js`

Acciones de la factura. Captura la hoja como PNG con `html-to-image` en el navegador (ADR-50). La imagen se prepara al cargar la página. Los tres botones de WhatsApp (Compartir en Ver factura, ícono rápido y recibos de abono) comparten `enviarPorWhatsapp`. SRS v2.0 (sección 1) y v3.0 (punto 2): `numeroDelEnlace` limpia espacios, guiones, paréntesis y `+`, antepone `57` a los 10 dígitos y conserva los 12 que ya empiezan por 57; se abre `https://wa.me/<numero>?text=<encodeURIComponent(texto)>` con el mismo mensaje aprobado. **Nunca se usa la Web Share API** ni se navega en la misma pestaña: SRS v3.4 exige `window.open(enlaceDirecto, '_blank', 'noopener,noreferrer')` para no dejar pantalla en blanco; si el navegador bloquea la ventana se avisa con un toast. El ícono de WhatsApp nunca se sustituye por texto de carga: solo se marca `aria-busy` y se libera en `finally` (`finalizar()`). Sin número válido se avisa antes de abrir. El PNG se copia al portapapeles y se descarga para adjuntarlo manualmente; esa lógica maestra no se reescribió. «Descargar imagen» solo descarga el PNG. SRS v3.1: `protegerLogoVisible()` guarda y restaura `src`, `display`, `visibility` y `opacity` del logo del modal; la captura sigue ocurriendo en un clon fuera de pantalla y `mostrarAviso()` muestra un toast discreto con el texto aprobado.

### `backend/app/static/js/ayuda.js`

Envía el formulario de «Envía comentarios» a `POST /feedback` con `fetch`, muestra
el aviso de éxito o el error del servidor y deshabilita el botón mientras espera.
El dispositivo lo detecta el servidor; aquí no se envía.

### `backend/app/static/js/comentarios.js`

Cambia el estado de un reporte desde el panel administrativo y actualiza en vivo
el contador del badge de la tarjeta del dashboard al resolverse una solicitud.

### `backend/app/static/js/vendor/html-to-image.js`

Copia local de la librería `html-to-image` (MIT). Se sirve desde el propio servidor para
no depender de una CDN ni de Node.js en producción (ADR-50).

### `backend/app/static/css/factura-olb.css`

Diseño compartido de la factura: colores, tamaños, sellos y la hoja Carta. Lo usan la
pantalla, la vista previa y la imagen descargada, así que un cambio se refleja en todas.

### `backend/app/templates/olb_byte/_hoja_factura.html`

Hoja de la factura: cabecera con logo, tarjetas de cliente, pago y garantía, tabla de
productos, totales, nota del vendedor, medios de pago y pie institucional. La marca
«ANULADA» aparece en órdenes anuladas. Se sirve en `/olb-byte/factura/{id}/hoja`.

### `backend/app/templates/olb_byte/_fragmento_factura.html`

Fragmento que envuelve `_hoja_factura.html` para la vista de factura y la captura de imagen,
sin cabecera de la aplicación.

### `backend/app/templates/olb_byte/_recibo.html`

Recibo de abono compartido por imagen: datos del cliente, abono, saldo y fecha en la hora
de la tienda. La misma plantilla se usa en la página del recibo y en la captura. Desde
SRS v1.9, 4.3, el cuerpo es gris perla con texto carbón y montos verdes; la cabecera
conserva el azul de la marca.

### `backend/app/templates/olb_byte/_fragmento_recibo.html`

Fragmento que sirve `_recibo.html` en `/olb-byte/recibos/{id}/hoja` para la captura.

### `backend/app/templates/olvide_contrasena.html`

Formulario «Recuperar contraseña» con el correo de la cuenta. Muestra siempre el mensaje
neutro tras enviarlo, y un enlace de regreso al login.

### `backend/app/templates/restablecer_contrasena.html`

Formulario de nueva contraseña (contraseña y repetición, mínimo 8 caracteres). Si el enlace
no es válido o venció, muestra el aviso y el enlace para pedir uno nuevo.

### `backend/app/servicios/analitica.py`

Analítica de OLB_BYTE (RF-12 a RF-14). SRS v1.9: `Filtro` (año, mes, cliente y producto)
es la selección que comparten todas las tablas, y `tabla_csv` arma cada descarga con las
mismas funciones que la pantalla. `_lineas` convierte cada orden en una fila por producto
y reparte saldo y abonos en proporción a su total (`_repartir`, ADR-55). `tabla_ventas`
lista esas líneas con su garantía (`estado_garantia_fila`: Activa, Vencida o Sin garantía).
`serializar_csv` escribe `;` con BOM. `reporte_mensual` agrupa las órdenes activas por
mes con variación frente al mes anterior y ancho de barra; `reporte_anual` calcula
ingresos, costos, ganancia, rentabilidad (ganancia ÷ costo × 100) y variación anual;
`ranking_vip` ordena clientes por monto y frecuencia; `alertas_costos` compara el costo
de cada compra con la anterior del mismo producto, marca los márgenes bajo
`UMBRAL_MARGEN_BAJO` y entrega el último costo de cada producto. Las órdenes anuladas no
cuentan en ingresos ni rankings, pero sí en el historial de costos.

### `backend/app/templates/olb_byte/analitica.html`

Vista de analítica con selector de año: tabla mensual con barras de ingresos, tabla
anual con rentabilidad, ranking de clientes VIP, alertas de subida de costo con margen
y tabla del último costo por producto. Las variaciones y márgenes se muestran sin signo
ni color, porque el signo de RF-10 aplica solo al módulo de cartera.

### `backend/app/templates/olb_byte/cartera.html`

Cartera y liquidez (RF-08 a RF-11). Balance de cartera en barras horizontales: cada
barra muestra su valor en pesos; los déficits salen a la izquierda del cero, en rojo, con
signo menos (`barras_balance`). La dona compara cartera y deuda con el proveedor. Incluye
el pago al proveedor y el libro de movimientos.

### `backend/app/templates/olb_byte/garantias.html`

Garantías en trámite y ranking de fallas (RF-05). Incluye el formulario para abrir un
reclamo sobre una línea de una orden activa, el ranking con la tasa de fallas y la
lista de reclamos con su vigencia y su avance con el proveedor. Un reclamo cerrado
muestra su resultado sin formulario.

### `backend/app/templates/olb_byte/cobro.html`

Gestión de cobro de una orden (RF-06 y RF-07). Muestra los datos de la venta (número de
factura, cliente, celular, fecha, total, abonado y saldo por pagar) y dos opciones. La
opción 1 registra un abono o el pago total con su monto y método; «Registrar pago» va al
final, junto a «Cancelar», que regresa a pendientes de pago. La opción 2 abre WhatsApp con
el recordatorio de cobro ya escrito. Si la orden está anulada o pagada, no muestra
formulario.

### `backend/app/templates/olb_byte/recibo.html`

Recibo compacto tipo billetera para cada abono (RF-07). Muestra el monto y el medio,
la fecha y hora de la tienda, los datos de la factura, el desglose de abonos cuando
hay más de uno y el saldo pendiente o la insignia de saldo total. Incluye los botones
de compartir por WhatsApp, imprimir y volver.

### `backend/app/static/js/olb_byte.js`

Formulario de venta de OLB_BYTE. El bloque de pago muestra u oculta los campos según
la forma de pago y el anticipo, y deshabilita los ocultos para que no se envíen
(`sincronizarPago`). «Guardar» valida el producto del panel, lo agrega a la tabla y
bloquea el panel (`guardarProducto`); «+ Agregar otro producto» lo desbloquea con los
campos en blanco (`habilitarPanel`). Si queda un producto escrito y sin guardar al
registrar la venta, se guarda antes. Cada fila guarda sus datos en campos ocultos
(`leerFila`, `escribirFila`). «Actualizar» abre el cuadro de edición y «Cancelar» lo
cierra sin cambios. `recalcular` actualiza total, costo y ganancia. «Pegar número» lee el
número copiado (desde Contactos del celular) y lo pone en el campo de celular; si no tiene
10 dígitos, o el navegador no permite leer el portapapeles, muestra una nota.

### `backend/app/templates/olb_byte/_subnav.html`

Submenú de OLB_BYTE con el mismo componente de Mis Finanzas (`subnav-finanzas`):
Ventas, Pendientes de pago, Cartera y liquidez, Garantías y Analítica. La pestaña
activa se marca con `seccion`, que cada vista define antes de incluirlo.

### `backend/app/static/js/presupuesto.js`

Planificador. `aNumero` y `formatear` normalizan montos, `actualizarTotal` muestra
el total proyectado de una meta limitada y `sincronizarDuracion` estima la
duración con la cuota y el saldo libre.

### `backend/app/static/js/sw.js`

Service worker de caché **solo de estáticos**. La constante `CACHE` debe subir de
versión (`olb-finanzas-vN`) cada vez que cambien CSS o JS; sirve caché primero y
red para el resto.

### `backend/app/static/manifest.webmanifest`

Manifiesto PWA: nombre, colores de la paleta, `display: standalone`, íconos y
`start_url`. Lo sirve `routers/pwa.py`. SRS v3.7: los PNG se generan desde
`assets/Logotipo OLB BYTE futurista en neón azul.png` (ícono oficial): `favicon-32.png`,
`icono-180.png` (apple-touch-icon), `icono-192.png` e `icono-512.png` con
`purpose: "any maskable"`, más `icono-512-maskable.png` con el contenido al 80 %
central. `favicon.svg` sigue disponible para la pestaña del navegador.

### 5.6 Plantillas

### `backend/app/templates/base.html`

El `<head>` declara las etiquetas Open Graph y Twitter Card para la vista previa al compartir
el enlace: título «Mis Finanzas», descripción comercial, `og:url`, `twitter:card` tipo
`summary_large_image` y la imagen `/estaticos/img/vista-previa.jpg?v=5` con URL absoluta (JPEG de 1200×588 px, 71 KB). La base
es `APP_URL`; sin esa variable usa `https://misfinanzas-odbc.onrender.com` (SRS v1.8).

El pie muestra solo «Finanzas · v1.0.0 | © año», sin el entorno (SRS v1.8). El `body` acepta
la clase de cada pantalla mediante el bloque `clase_cuerpo`. SRS v3.7: el `<head>`
declara `icon` PNG de 32×32 y 192×192 y `apple-touch-icon` de 180×180 con el
logotipo neón azul oficial.

El encabezado usa la macro `avatar` en tamaño compacto antes del saludo (SRS v1.8).

Layout común: `<head>` con manifest y CSS, header de tres opciones (`Inicio`,
`Mi Perfil`, `Salir`), banner de publicidad para `USER_FINANZAS`, contenedor de
mensajes y bloque `contenido`. Carga `app.js` y registra el service worker.
En el espacio que antes ocupaba la publicidad (solo USER_FINANZAS) aparece una tarjeta visible «Si te gusta mi trabajo · Invítame un café ($6.000 COP)» con un botón que abre un <dialog> con una sola tarjeta: el QR de Bre-B (ssets/Logo De Bre-B.png). No muestra teléfono ni llave. La publicidad quedó retirada de la plantilla (SRS v1.8). No usa JavaScript propio: lo abren data-abrir-dialogo y data-cerrar-dialogo de pp.js.

### `backend/app/templates/componentes/avatar.html`

Macro `avatar(usuario, tamano)`: círculo de avatar reutilizable (SRS v1.8). Con
`avatar_url` muestra la foto de Google con `referrerpolicy="no-referrer"`; si la carga
falla (`onerror`), oculta la imagen y muestra las iniciales. Sin foto, dibuja el círculo
de iniciales con el degradado de la paleta. Tamaños `compacto` (encabezado) y `destacado`
(perfil).

### `backend/app/templates/dashboard.html`

Panel principal con las tarjetas de módulo según rol (OLB_BYTE se omite para
`USER_FINANZAS`), saludo con alias y accesos a Mi Perfil/Usuarios.

### `backend/app/templates/login.html`

Pantalla de acceso a pantalla completa (clase `pagina-acceso` en el `body`, que oculta la
cabecera y quita la caja interior). Muestra la marca y el subtítulo «Análisis de nómina y
presupuesto». No muestra cuentas de demostración ni contraseñas (SRS v1.8, en producción).

Formulario de acceso con correo y contraseña, enlace al registro y mensajes de
error del limitador. Sin JavaScript obligatorio.

### `backend/app/templates/registro.html`

Formulario de creación de cuenta (alias, correo, contraseña con reglas visibles).
Siempre crea `USER_FINANZAS`; el onboarding del perfil llega después.

### `backend/app/templates/admin/usuarios.html`

Tabla de cuentas con rol, estado y acciones para cambiar ambos. Los controles del
propio administrador están deshabilitados para no autodegradarse.

### `backend/app/templates/perfil/index.html`

Muestra el avatar destacado (96 px) al inicio de la cabecera del perfil (SRS v1.8).

Formulario del perfil financiero: alias, sueldo, modalidad y bloque quincenal.
En modalidad `MENSUAL` el bloque se oculta con aviso; en `QUINCENAL` pide caso A
(porcentajes + quincena de deducciones) o caso B (neto sin deducciones). Los
porcentajes se escriben y se muestran con «%» y coma decimal. Incluye cambio de
contraseña y, para el administrador, acceso a Usuarios.

### `backend/app/templates/finanzas/index.html`

Vista central del proyecto (50/50 en escritorio). Izquierda: quincena 1, quincena
2 y atajos de pago en solo lectura; derecha: sueldo de solo lectura, deducciones
de ley en pesos, cuadrícula 2 × 3 de horas extras, acciones, auxilio,
incapacidades compactas, resultado y desglose. Incluye el submenú y el formulario
clásico para funcionar sin JavaScript.

### `backend/app/templates/finanzas/_subnav.html`

Subnavegación de cuatro pestañas de Mis Finanzas: Calculadora y Nómina, Gastos
Fijos, Incapacidades y Configurar Atajos de Pago. Marca la activa con
`subnav-finanzas__enlace--activo`.

### `backend/app/templates/finanzas/_gasto_fijo.html`

Componente compartido (DRY) de una fila de gasto fijo con su check de pago
(SRS v1.7, bloques C y E). Expone dos macros: `boton_editar(etiqueta)` pinta el
lápiz del tamaño del check y `fila_gasto(gasto, hoy, origen, id_trabajo)`
compone nombre, valor, edición en línea con «Actualizar»/«Cancelar», × de
eliminación o salto y ✔ de pago reversible. El desplegable lleva la clase
`edicion-gasto--modal`, que en el celular lo convierte en una ventana centrada
con fondo oscuro. No aplica reglas de negocio: solo
pinta el estado que calculó el servidor. Lo consumen `finanzas/index.html` y
`trabajos/index.html` para que ambas vistas sean idénticas. SRS v2.0: cuando
`gasto.id_deuda` existe muestra `gasto.deuda.cuota_mensual` como valor y
conserva la descripción escrita por el usuario, sin añadir el acreedor a la fila
(para no ensancharla); conserva check, lápiz y ×.

### `backend/app/templates/ayuda/index.html`

Vista «Ayuda y comentarios» (SRS v2.0, sección 5.3): cabecera con logo, nombre y
versión; tarjeta de soporte con el acordeón del centro de ayuda (GUÍA A de
instalación PWA y GUÍA B de preguntas frecuentes) y el modal de reportes; tarjeta
legal con los modales de condiciones/privacidad y licencias; pie «© 2026
MisFinanzas». Todos los textos son literales y solo mencionan módulos públicos.
SRS v3.0 (punto 7): incluye «Mis reportes enviados», alimentado por
`/api/feedback/mios`, con la etiqueta de estado actual de cada ticket; «Volver
al inicio» usa el botón azul primario y los textos van justificados.

### `backend/app/templates/ayuda/_legal.html`

Modal `<dialog>` compartido por la vista de ayuda y la pantalla de ingreso con el
texto literal «CONDICIONES DE USO Y POLÍTICA DE PRIVACIDAD — MISFINANZAS».
`app.js` lo abre desde cualquier `[data-abrir-dialogo="dialogo-legal"]`.

### `backend/app/templates/admin/comentarios.html`

Panel administrativo de reportes (SRS v2.0, 5.5): tabla con usuario y correo,
fecha, tipo, módulo, dispositivo, descripción y selector de estado. Cada cambio
llama a la API y actualiza el contador de pendientes del dashboard. SRS v3.0
(punto 7): la tabla se oculta en móvil y se sustituye por tarjetas
`.reportes-moviles` conectadas al mismo arreglo, con el selector de estado
(`PATCH /api/feedback/{id}`) para que la vista no quede en blanco en celular.

### `backend/app/templates/_categorias.html`

Macros reutilizables del catálogo cerrado (SRS v1.9). `selector_categoria` pinta
un cuadro de solo lectura con `name="categoria"` y un botón que despliega las
ocho opciones, marcadas con un punto neutro (sin cuadrito de color), incluida
«Créditos y Obligaciones». Los colores exactos siguen en la dona.
`vinculo_condicional` muestra la pregunta SI/NO de la sección 3.2 con el texto
propio de cada módulo, el desplegable «Deudas registradas» con todas las deudas
activas y el acceso «Ve a registrar la deuda». `vinculo_deuda` es la versión
simple que siguen usando los formularios de edición. Lo importan Mis Finanzas,
Gastos, Trabajos Extras, Deducciones Fijas y la fila de gasto compartida.

### `backend/app/templates/finanzas/_capacidad.html`

Panel compartido de capacidad de endeudamiento (SRS v1.7, bloque F; base mínima
en v1.8). La macro `panel_capacidad(capacidad, titulo, descripcion)` dibuja la
dona del ingreso repartido entre gastos fijos, cuota de deudas, base mínima de
liquidez y disponible para abonar. Desde SRS v1.9 los arcos y la leyenda salen
de `capacidad.arcos_categoria`, con los nombres y colores del catálogo. Hay una
**sola** leyenda: los propios arcos ya traen el nombre, el color, el valor y el
porcentaje de cada categoría con valor mayor que cero, sin duplicados ni notas
adicionales. También muestra el semáforo,
las deudas con tres cuotas o menos y la tabla de doce meses con su
barra de saldo libre. Se incluye una vez en `presupuesto/index.html` y otra en
`trabajos/index.html`, cada una con su propio título.

### `backend/app/templates/gastos/index.html`

Registro de gastos: formulario, lista con acciones de edición en línea
(`<details>`) y totales por quincena. Enlace de regreso al planificador.

### `backend/app/templates/presupuesto/index.html`

Planificador: diagnóstico del mes, alerta de liquidez, formulario de metas (con
«Ambas quincenas», el modo en su propia fila y la quincena donde se aplican los
pagos), tarjetas de metas con avance, lista de abonos de cinco filas con scroll
interno y gestión de deducciones fijas del salario. El formulario de deducciones
va en dos filas (SRS v1.9, sección 3.1): arriba Concepto | Categoría (selector
cerrado) | Valor Descontado (COP), y abajo «Quincena donde aplican los pagos».
En la lista, las acciones se alinean a la derecha y en móvil la fila completa
abre un modal con Actualizar, Eliminar y Cancelar (sección 3.3). El consejero financiero se
muestra activo cuando el libre supera la base mínima o apagado con el mensaje de
emergencia. V3.9.5: en la comparativa de cierre, el contenedor de velocímetros
fuerza en línea `grid-template-columns: repeat(2, minmax(0, 1fr))`, ancho 100 %,
máximo 540 px y margen central; cada tarjeta lleva `min-width: 0` y su SVG
120×68 con `flex-shrink: 0`, sin tocar móvil ni el fondo de la tarjeta.

### `backend/app/templates/historial/index.html`

Historial cronológico: fecha de guardado, periodo, sueldo base, total de extras,
deducciones, gastos quincenales, saldo neto con variación y acciones (ver, CSV,
imprimir, eliminar).

### `backend/app/templates/historial/imprimir.html`

Versión imprimible de una liquidación: encabezado del periodo, desglose y neto,
sin navegación. Se abre en pestaña nueva.

### `backend/app/templates/incapacidades/index.html`

Formulario de incapacidad (fechas, origen, días calculados), resultados del mes y
tramos con su descuento, más el listado de incapacidades registradas.

### `backend/app/templates/deudas/index.html`

Cuatro tarjetas de resumen, formulario de seis campos y tabla tipo Excel con
las columnas Acreedor, Total Adeudado, Cuota, No. de cuotas pendientes (en tres
líneas, columna estrecha), Intervalo de pago y Estado (SRS v1.9, sección 2.3). Hay
**una sola fila por deuda**: se eliminaron el bloque de «Cuotas aplicadas» y el
mensaje de deuda sin cuotas. Al final de cada fila van el lápiz de edición y la
× de borrado; el modal centrado ofrece solo Total Adeudado, Cuota y No. Cuotas,
con cierre sutil arriba y «Actualizar». En móvil los iconos se ocultan y la fila
abre ese modal con `js/deudas.js`. El contenedor de la tabla fija la cabecera con
fondo opaco, limita la altura (cuatro deudas en escritorio) y confina el scroll
horizontal y vertical dentro de la caja. Si se llega con `?volver=…`, aparece
«Volver al formulario de origen» con el id de la deuda recién creada.

### `backend/app/templates/chancucos/_dias.html`

Distintivo de los días de pago de un atajo (SRS v1.7, bloque D). La macro
`dias_pago(item, clase)` imprime «Día 15» o «Día 15 · Día 30» a partir de
`dia_pago_1`/`dia_pago_2`, con clase CSS configurable. Se reutiliza en la tarjeta
de atajos de Mis Finanzas y en la tabla de «Configurar Atajos de Pago» para
mostrar exactamente el mismo texto.

### `backend/app/templates/chancucos/index.html`

Configuración de atajos: formulario con descripción, referencia, «Valor a pagar
(COP)» (opcional, sección 4.2), enlace, la pregunta «¿Es un único pago mensual?»
(una o dos fechas) y favorito. La tabla muestra el valor a pagar antes del botón
«Pagar»; el mismo dato aparece en la tarjeta embebida de Mis Finanzas.

### `backend/app/templates/olb_byte/index.html`

Panel comercial: inventario, clientes, venta multipartida, cartera y ventas
recientes con acceso a la factura.

### `backend/app/templates/olb_byte/factura.html`

Factura imprimible con datos del negocio, cliente, detalle, totales y enlace de
WhatsApp. Pensada para impresión directa del navegador.

### `backend/app/templates/privado/index.html`

Plantilla de módulo bloqueado: explica al `USER_FINANZAS` que la sección es
exclusiva del administrador.

### `backend/app/templates/trabajos/index.html`

Trabajos extras: formulario, resumen de pendientes/cobrados y tabla con acciones
para marcar cobrado o eliminar.

---

## 6. Flujos de extremo a extremo

### 6.1 Arranque de una petición autenticada

1. `MiddlewareSeguridad` valida origen (POST) y añade cabeceras.
2. `obtener_usuario_actual` lee la cookie, decodifica el JWT y recarga el usuario.
3. Si no hay perfil, `OnboardingRequerido` redirige a `/perfil?bienvenida=1`.
4. El router arma el contexto con `contexto_base` y llama al servicio.
5. Jinja2 renderiza; `finanzas.js` puede pedir un recálculo por JSON.

### 6.2 Liquidación en vivo

```
formulario → finanzas.js (debounce 150 ms)
           → POST /finanzas/calcular (JSON)
           → _leer_entradas → _liquidar
           → nomina.liquidar_periodo + quincenas.resumen_quincenas
           → JSON con sueldo, deducciones, desglose, tramos y quincenas
           → pintar* actualiza sin recargar
```

Guardar (`POST /finanzas/guardar`) repite el cálculo en el servidor y persiste el
periodo: nunca se confía en las cifras del cliente.

### 6.3 Incapacidad que cruza de mes

1. El usuario registra inicio y fin; los días son `fin − inicio + 1`.
2. `calcular_incapacidad` aplica 100 % a los dos primeros días y 66,67 % al resto,
   sobre la incapacidad completa.
3. `tramos_del_mes(mes)` recorta lo que cae en el mes consultado.
4. Mis Finanzas resta **solo** el tramo del mes; el mes siguiente resta el suyo.
   No hay rollover.

### 6.4 Deuda con amortización automática

1. El usuario registra acreedor, descripción, total adeudado, cuota, cuotas y
   periodicidad.
2. `validar_plan` exige que `cuota × cuotas` coincida con el total adeudado
   (tolerancia de $1 por cuota); no hay tasa ni intereses.
3. Al abrir el módulo, `aplicar_cuotas_vencidas` cuenta periodos vencidos desde el
   último pago (o la creación) y registra cada cuota.
4. Cada cuota abona capital completo; la última absorbe el redondeo y deja el
   saldo en cero.
5. `proyeccion_deuda` muestra lo que falta sin alterar la base.

### 6.5 Meta con «Ambas quincenas»

`quincena = 3` guarda la cuota **mensual** y `valor_por_pago` la divide entre dos.
La interfaz muestra «Ambas quincenas (X por pago)». El planificador compara contra
el saldo libre total, no contra un pago concreto.

---

## 7. Motor financiero en fórmulas

| Concepto | Fórmula |
| --- | --- |
| Hora ordinaria | `sueldo_básico / 220` (2026; antes 210) |
| Recargo | `valor_hora × horas × factor` |
| Devengado | `básico + Σ recargos − descuento_incapacidad` |
| Salud / Pensión | `4 % × devengado` cada una |
| Auxilio de transporte | `$ 249.095` si `básico + recargos ≤ 2 SMMLV`, si no `0` (parametrizable con `AUXILIO_TRANSPORTE`) |
| Incapacidad días 1–2 | `100 %` del valor día |
| Incapacidad día 3+ | `66,67 %` (descuento `33,33 %`) |
| Quincena | La tarjeta muestra `sueldo_neto_corte` (neto de ley y fijas); su saldo = ese neto − gastos del corte. La dona usa el `ingreso` bruto |
| Total devengado | Suma del `devengado_neto` de todos los cortes del mes |

La tarjeta «Resultado del periodo» (SRS v4.10) usa la etiqueta **TOTAL DEVENGADO**,
el valor consolidado y una nota en dos líneas: «Ingresos totales menos deducciones
de ley e incapacidad.» y «Total de Gastos del mes: $X». El desglose inferior se
ordena en nueve filas: valor hora ordinaria, horas extras y recargos, total
devengado, auxilio de transporte y total ingresos; separador; salud, pensión,
descuento por incapacidad y total deducciones. Las tarjetas de corte no repiten
la fila de «Deducciones de ley» porque su sueldo devengado ya viene neto de ley.
En v4.13 esas tarjetas muestran directamente `sueldo_neto_corte` (ley y fijas
descontadas) y solo restan gastos fijos. El Consejero usa cifras reales:
`saldo_actual`, `meses_minimo`, `meses_con_excedente`, `reduccion_capital_12m`
y desglose por deuda con nombre, saldo y cuota; nunca intereses ficticios.
Las fechas llevan meses completos en español. La curva al 100 %, las
sub-tarjetas de velocímetros y las píldoras oscuras de meses son exclusivas de
`@media (min-width: 768px)`; el móvil conserva su distribución.

En v4.17 los velocímetros llevan un dial radial tipo cockpit con 41 micro-marcas,
resplandor azul (`Pago mínimo`) o esmeralda (`Con excedente`) y aguja con pivote.
El texto se centra debajo en cuatro líneas: título, fecha completa, duración y
saldo real con la condición del escenario. Los tamaños no cambiaron (120×68 en
móvil, 156×88 en escritorio) y las reglas CSS se declaran fuera de media queries.

En v4.18 los velocímetros se apilan en móvil (primero pago mínimo) sin tocar el
diseño web; la gráfica de 12 meses mide al menos 220 px en móvil, usa etiquetas
claras, curva verde continua frente a azul discontinua y un solo mes activo con
una línea de resumen. El Consejero distingue el plazo de la deuda recomendada
del cierre global, usa «pago mínimo» y solo suma deudas de su plan.

En v4.19 las deudas amortizan en paralelo: el plazo base es el mayor del
portafolio y la cuota liberada se reinvierte al mes siguiente. La gráfica se
recorta a 6 meses con badges de extremos, área diferencial y seis píldoras.
En móvil el banner verde comparte radio con los velocímetros, «Atajos guardados»
usa una tabla `table-fixed` 38/34/28 con `min-width: 0` y el texto corrido va
justificado; la dona se centra en escritorio.

En v4.20 el cierre del Consejero se calcula solo sobre `plan = orden[:3]`, por lo
que una deuda hipotecaria no recomendada ya no distorsiona los meses ni las
fechas. La pluralización es exacta («1 cuota» / «N cuotas»), las viñetas nombran
«la deuda que tienes con…» y la de liberación usa «deudas que te acabo de
recomendar (…) podrás liberar». Las cabeceras de atajos van en dos líneas, la
proyección a 6 meses solo existe en escritorio y el banner móvil va centrado.
| Coherencia de deuda | `cuota × cuotas = total adeudado` (tolerancia `$1 × cuotas`) |
| Cuota final | `saldo_pendiente` (absorbe el redondeo y deja cero) |

Constantes parametrizables en `core/config.py`: 220 h (2026), 4 % + 4 % y los
**siete factores oficiales**: extra diurna 1,25; extra nocturna 1,75; extra
diurna dom/fest 2,15; extra nocturna dom/fest 2,65; recargo nocturno 0,35;
recargo ordinario dom/fest 0,90; recargo nocturno dom/fest 1,25. También SMMLV y
tope de 2 SMMLV (COP 3.501.810). Se admiten horas decimales (ej. 10,4) y el
concepto heredado «Recargo Dominical o Festivo Diurno/Nocturno» se migra al
canónico con factor 0,90.

Etiquetas de la interfaz: **Sueldo devengado** en cada corte y **Total devengado**
en el resultado del periodo, sin guiones. Caso base documentado: $3.484.000 al
40 %/60 % con auxilio de $249.095 rinde $1.393.600 en Q1 y **$2.060.775** netos
en Q2; total consolidado $3.454.375.

---

## 8. Base de datos y migraciones

- **Fase actual:** SQLite + SQLAlchemy 2.x; cambiar `DATABASE_URL` apunta a
  PostgreSQL sin tocar el dominio.
- **Fuente única:** `diccionario_datos.md`. Ninguna tabla se crea sin documentar.
- **Migraciones ligeras:** `core/base_datos.py`; todas idempotentes y verificadas
  sobre copia de la base real antes de dar un bloque por cerrado.
- **Reconstrucción de tablas:** cuando SQLite no permite alterar un `CHECK` o un
  `NOT NULL` (chancucos v1.3, metas v1.5), se crea la tabla nueva, se copian las
  filas y se renombra; la tabla hija se elimina antes que la padre.
- **Respaldo:** `scripts/respaldo.py` copia de forma consistente y rota archivos (solo SQLite).
- **Migración a Neon:** `scripts/migrar_a_neon.py` crea el esquema en PostgreSQL y copia
  `datos/finanzas.db` sin duplicar registros (`ON CONFLICT DO NOTHING`). Neutraliza las
  cuentas demo copiadas. Se puede repetir sin efectos adicionales (SRS v1.8, ADR-52).
- **Reparación de pagos de trabajos:** `scripts/reparar_pagos_trabajos.py` devuelve a la
  categoría «Trabajo extra» los pagos reclasificados por una migración anterior y elimina
  los duplicados por contrato, año, mes y quincena. Acepta `--simular` y es idempotente
  (ADR-60).

---

## 9. Comandos y pruebas

```bash
cd backend
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

.\.venv\Scripts\python -m compileall -q app     # sintaxis
.\.venv\Scripts\python -m pytest -q             # suite completa (678 pruebas)
.\.venv\Scripts\python scripts\respaldo.py      # respaldo SQLite
.\.venv\Scripts\python scripts\reparar_pagos_trabajos.py --simular  # diagnóstico ADR-60
.\.venv\Scripts\python scripts\generar_guia.py --verificar
```

| Archivo de pruebas | Cubre |
| --- | --- |
| `test_nomina.py` | Hora ordinaria, recargos, deducciones sobre devengado. |
| `test_auxilio.py` | Tope de 2 SMMLV y mensaje del SRS. |
| `test_incapacidad.py` | Regla 100 %/66,67 % y reparto por mes. |
| `test_incapacidad_en_vivo.py` | Reactividad y tramos en el formulario. |
| `test_perfiles.py`, `test_quincenas.py` | Onboarding, porcentajes y saldo libre. |
| `test_periodos.py` | Historial, guardado y eliminación. |
| `test_gastos_deudas.py` | Gastos, coherencia del plan de deudas y amortización automática. |
| `test_presupuesto.py` | Metas, abonos, «Ambas quincenas», deducciones fijas. |
| `test_auth.py`, `test_seguridad*.py` | Login, RBAC, JWT, CSRF y cabeceras. |
| `test_vistas.py`, `test_finanzas_vistas.py` | Renderizado y navegación. |
| `test_trabajos_chancucos.py`, `test_comercial.py` | Módulos restantes. |
| `test_pagos_trabajos_migracion.py` | La migración respeta «Trabajo extra» y la reparación deduplica (ADR-60). |
| `test_deudas_ui_v19.py` | Tabla de deudas contenida en móvil y modales (ADR-61 y ADR-62). |
| `test_texto.py`, `test_respaldo.py` | Formato/parseo y respaldo. |

---

## 10. Personalizar la factura (pantalla, PDF y WhatsApp)

La factura se ve igual en la pantalla, en la vista previa, en la descarga y en el PDF que
se envía por WhatsApp. Para que eso sea así, todas las salidas comparten tres piezas:

| Pieza | Archivo | Qué controla |
| --- | --- | --- |
| Hoja de la factura | `backend/app/templates/olb_byte/_hoja_factura.html` | Estructura, textos fijos y tablas |
| Diseño | `backend/app/static/css/factura-olb.css` | Colores, tamaños, fondos y sellos |
| Datos | `backend/app/servicios/factura_pdf.py` | Empresa, cuenta bancaria, logos y reglas |

`factura.html` (pantalla) y `_fragmento_factura.html` (captura de imagen) solo incluyen la
hoja y el CSS. Por eso un cambio en la hoja o en el CSS se refleja en la pantalla, la vista
previa, la descarga y la imagen de WhatsApp al mismo tiempo (ADR-50).

### 10.1 Datos de la empresa y de pago

En `factura_pdf.py`, constantes al inicio del archivo:

- `NIT`, `RESPONSABLE`, `DIRECCION`, `TELEFONO`.
- `NEQUI`: número que aparece bajo el logo de Nequi.
- `BANCO`: nombre, tipo de cuenta, número de cuenta y teléfono de la cuenta de ahorros.
- `PIE_LEGAL`: el texto pequeño al final de la factura.

### 10.2 Colores y tamaños

En `factura-olb.css`, los colores de la paleta:

- `#041e42` y `#051937`: cabecera y encabezados oscuros.
- `#0066cc`, `#0b4fa3`, `#1468c9`: azules de tablas y totales.
- `#00d2ff`, `#00a8ff`: líneas de circuito y franjas.
- `#dcebfa`: filas pares de la tabla.

Las filas de relleno de la tabla salen de `FILAS_MINIMAS_TABLA` (9). El máximo de productos
por factura es `MAX_LINEAS_PDF` (10), porque el PDF debe caber en una sola hoja Carta.

### 10.3 Tamaño de la imagen

La imagen se captura del tamaño de la hoja en el navegador (`factura.js`, con
`html-to-image`). Con diez productos el diseño debe caber en una sola hoja Carta. Si subes el
tamaño de letra o agregas bloques, revisa la hoja en pantalla: si se corta o crece demasiado,
reduce espacios en `factura-olb.css`.

### 10.4 Logos

Los logos están en la carpeta `assets/` de la raíz del proyecto (no dentro de `backend/`).
Python encuentra cada uno por una palabra de su nombre de archivo (`PATRONES_LOGO`):

| Clave | Palabra que busca | Dónde se ve en la hoja |
| --- | --- | --- |
| `bre_b` | `bre-b` | Medios de pago, primera tarjeta |
| `datafono` | `Datafono` | Medios de pago, segunda tarjeta |
| `nequi` | `Nequi` | Medios de pago, cuarta tarjeta |
| `visa_mastercard` | `Mastercard` | Medios de pago, última tarjeta |
| `olb` | `Nuevo Logo` (archivo `Nuevo Logo.png`) | Cabecera de la factura, dentro de un recuadro blanco |

Para reemplazar un logo, guarda el PNG nuevo en `assets/` con la misma palabra en el nombre y
borra el archivo viejo (si hay dos archivos con la misma palabra, gana el primero que encuentre
Python). Para quitar un medio de pago, borra su bloque `<div class="pago-item">` en
`_hoja_factura.html`.

Si quieres usar el logo como imagen en lugar del texto «OB / OLB BYTE», reemplaza el bloque
`<div class="logo-ob">` de `_hoja_factura.html` por `<img src="{{ logos.olb }}" alt="OLB BYTE">`.

### 10.5 Probar los cambios

1. Reinicia el servidor (`python -m uvicorn app.main:app --reload`).
2. Abre una factura desde OLB_BYTE: la pantalla ya muestra el diseño nuevo.
3. Pulsa **Descargar** o **Enviar por WhatsApp**, o entra a `/olb-byte/factura/{id}/hoja`.
4. Si la imagen no se descarga, revisa la consola del navegador: la captura depende de
   `static/js/vendor/html-to-image.js`.

## 11. Lista de verificación antes de cerrar un bloque

1. `python -m compileall -q app scripts` sin errores.
2. `pytest -q` en verde (hoy: **847**; v4.20 añadió 5 y v4.19 cerró con 842).
3. `node --check` de todos los JS que se hayan tocado, sin errores.
4. Migraciones nuevas probadas **dos veces** sobre copia de `finanzas.db` y aplicadas en Neon.
   Toda migración usa parámetros nombrados con `text()`: el estilo `?` de SQLite falla en PostgreSQL.
5. `sw.js` con la caché subida si cambió CSS o JS (hoy: `olb-finanzas-v108`).
6. `python scripts\generar_guia.py` y luego `--verificar` sin problemas (115 fichas).
7. `MEMORY.md` con la bitácora y el ADR si cambió una regla (hoy: ADR-83 para v4.20).
8. `AGENTS.md` §9 con el estado verificado y el conteo de pruebas.
9. `constitution.md`, `diccionario_datos.md`, `USER_GUIDE.md` y la SRS con la versión activa (hoy: **v4.20**, sección 23).
10. Para v4.20, además: `.venv\Scripts\python -m scripts.crear_usuario_qa.py` y
    `.venv\Scripts\python -m scripts.qa_v4_20.py` con el servidor levantado (17 comprobaciones).
11. La regla de escritorio de los velocímetros debe estar en un `@media (min-width: 768px)`
    de nivel superior: aguas arriba hay un `@media (max-width: 767px)` abierto que anida
    cualquier bloque nuevo y lo deja inactivo en pantallas grandes.
12. La tabla de siete factores y el divisor 220 viven solo en `core/config.py`; no se
    hardcodean en plantillas ni en JavaScript.
