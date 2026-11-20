# Guía del proyecto — Finanzas y OLB_BYTE

> **Documento vivo.** Se reescribe completo en cada cambio relevante del código
> (ver `AGENTS.md` §5 y `MEMORY.md`). El inventario de §4 es automático y no debe
> editarse a mano; las fichas de §5 sí son manuales y deben reflejar el estado del
> archivo.

## 1. Para qué sirve esta guía

Esta guía responde tres preguntas concretas:

1. **¿Dónde está cada cosa?** Inventario de los 70 archivos de `backend/app` con
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
| `ADMIN_OLB` | Mis Finanzas (+ Chancucos), OLB_BYTE, Resumen de Deudas, Trabajos Extras, Mi Perfil, Usuarios | — |
| `USER_FINANZAS` | Mis Finanzas (+ Chancucos propios), Resumen de Deudas, Trabajos Extras, Mi Perfil | OLB_BYTE (403 en UI y endpoint) |

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

- **99 archivos** documentados: 51 Python, 36 plantillas Jinja2 y 12 recursos estáticos.
- **56 clases**, **487 funciones** y **26 métodos** de clase.

### Detalle por archivo

#### `backend/app/`

- **`__init__.py`** · 9 líneas — Paquete principal de la aplicación `app`.
- **`dependencias.py`** · 226 líneas — Dependencias de sesión y autorización (RBAC).
  - Clases: `SesionRequerida`, `OnboardingRequerido`, `UsuarioSesion`
  - Funciones: `_usuario_desde_token`, `usuario_opcional`, `obtener_usuario_actual`, `obtener_usuario_sin_onboarding`, `exigir_administrador`, `exigir_olb_byte`
- **`main.py`** · 168 líneas — Punto de entrada de la aplicación **Finanzas y OLB_BYTE**.
  - Funciones: `_pide_json`, `_manejar_sesion_requerida`, `_manejar_onboarding`, `crear_aplicacion`
- **`modelos.py`** · 734 líneas — Modelos SQLAlchemy derivados de `diccionario_datos.md`.
  - Clases: `Usuario`, `PerfilFinanciero`, `PeriodoNomina`, `RegistroHorasExtra`, `Incapacidad`, `SaldoIncapacidad`, `Gasto`, `Deuda`, `PagoDeuda`, `Chancuco`, `ProyeccionAhorro`, `AbonoProyeccion`, `DeduccionFija`, `Cliente`, `Producto`, `Venta`, `VentaDetalle`, `Abono`, `DevolucionCliente`, `MovimientoProveedor`, `GarantiaProveedor`, `TrabajoExtra`, `Auditoria`
  - Funciones: `nuevo_id`

#### `backend/app/core/`

- **`__init__.py`** · 11 líneas — Núcleo de la aplicación: parámetros de negocio y utilidades transversales.
- **`base_datos.py`** · 673 líneas — Conexión a la base de datos y sesión por petición.
  - Clases: `Base`
  - Funciones: `_cargar_archivo_entorno`, `_url_con_driver`, `obtener_bd`, `crear_esquema`, `_renombrar_referencia_a_categoria`, `_reconstruir_comercial_sin_stock`, `_migrar_columnas_trabajos`, `_migrar_columnas_chancucos`, `_migrar_columnas_metas`, `_migrar_columnas_perfil`, `_migrar_columnas_gastos`, `_migrar_chancucos`, `_migrar_columnas_deudas`, `_migrar_proyeccion_quincena`, `_migrar_saldos_incapacidad`, `_migrar_columnas_usuarios`, `inicializar_base_datos`
- **`config.py`** · 314 líneas — Parámetros de negocio y configuración de la plataforma.
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
- **`texto.py`** · 178 líneas — Utilidades de formato para la interfaz (pesos colombianos, porcentajes y fechas).
  - Funciones: `formatear_cop`, `formatear_porcentaje`, `formatear_fecha`, `parsear_monto`, `formatear_mes_anio`, `parsear_periodo_mes`

#### `backend/app/routers/`

- **`__init__.py`** · 11 líneas — Routers de la aplicación.
- **`admin.py`** · 176 líneas — Administración de cuentas (solo `ADMIN_OLB`).
  - Funciones: `_contexto_admin`, `ver_usuarios`, `cambiar_rol_usuario`, `cambiar_estado_usuario`
- **`auth.py`** · 569 líneas — Rutas de autenticación: login, registro y cierre de sesión.
  - Funciones: `_clave_intento`, `_establecer_cookie`, `ver_login`, `procesar_login`, `cerrar_sesion`, `ver_registro`, `procesar_registro`, `ver_olvide_contrasena`, `_login_con_error`, `iniciar_google`, `callback_google`, `_base_publica`, `_pagina_olvide`, `_cuenta_del_enlace`, `_pagina_restablecer`, `procesar_olvide_contrasena`, `ver_restablecer_contrasena`, `procesar_restablecer_contrasena`
- **`chancucos.py`** · 180 líneas — Panel de Chancucos: referencias de pago con copiado y botón *Pagar*.
  - Funciones: `ver_chancucos`, `crear_chancuco`, `alternar_favorito`, `eliminar_chancuco`
- **`deudas.py`** · 180 líneas — Rutas del módulo "Resumen de Deudas".
  - Funciones: `_contexto`, `ver_deudas`, `crear_deuda`, `eliminar_deuda`
- **`finanzas.py`** · 1082 líneas — Módulo "Mis Finanzas": liquidación, guardado e historial.
  - Clases: `EntradaFinanzas`
  - Funciones: `_texto`, `_entero`, `_descuento_por_fechas`, `_leer_entradas`, `_liquidar`, `_deducciones_segun_quincena`, `_datos_formateados`, `_detalle_formateado`, `_detalle_incapacidad_json`, `_fijas_del_periodo`, `_total_fijas`, `_total_deducciones_ley`, `_saldos_quincenas`, `_contexto_calculadora`, `ver_finanzas`, `procesar_finanzas`, `calcular_finanzas_json`, `guardar_liquidacion`, `_filas_historial`, `_etiqueta_periodo`, `ver_historial`, `exportar_historial_csv`, `imprimir_periodo`, `eliminar_periodo`
- **`gastos.py`** · 458 líneas — Rutas del presupuesto de gastos.
  - Funciones: `_parsear_fecha`, `ver_gastos`, `crear_gasto`, `editar_gasto`, `_volver`, `eliminar_gasto`, `marcar_pagado_gasto`, `desmarcar_pagado_gasto`, `registrar_abono_gasto`, `limpiar_pagos_gastos`
- **`incapacidades.py`** · 310 líneas — Rutas del módulo de incapacidades.
  - Funciones: `_valores_del_formulario`, `_parsear_fecha`, `_validar`, `_contexto`, `ver_incapacidades`, `calcular_incapacidad_formulario`, `guardar_incapacidad`, `eliminar_incapacidad`
- **`olb_byte.py`** · 1050 líneas — Módulo comercial OLB_BYTE: ventas a crédito, cobros, anulaciones y factura.
  - Clases: `DetalleVenta`
  - Funciones: `_detalle_de_venta`, `_filas_del_formulario`, `_lineas_desde_filas`, `_contexto`, `_contexto_pendientes`, `_pagina_con_error`, `ver_olb_byte`, `_datos_pago`, `_pago_desde_datos`, `registrar_venta`, `registrar_abono`, `_contexto_cobro`, `ver_cobro`, `ver_pendientes`, `ver_recibo`, `anular_venta`, `registrar_devolucion`, `ver_factura_hoja`, `ver_recibo_hoja`, `ver_factura`, `_contexto_cartera`, `ver_cartera`, `registrar_abono_proveedor`, `_pagina_error_pdf`, `ver_analitica`, `_contexto_garantias`, `ver_garantias`, `registrar_garantia`, `actualizar_garantia`
- **`perfil.py`** · 289 líneas — Rutas del perfil financiero y del cambio de contraseña.
  - Funciones: `_formatear_porcentaje`, `_contexto_perfil`, `ver_perfil`, `guardar_perfil`, `cambiar_contrasena`
- **`presupuesto.py`** · 417 líneas — Rutas del planificador de ahorro y metas (SRS v1.3, bloque 3).
  - Funciones: `_fecha_del_formulario`, `_meses_del_formulario`, `_contexto`, `ver_presupuesto`, `crear_proyeccion`, `eliminar_proyeccion`, `extender_meta`, `crear_deduccion_fija`, `editar_deduccion_fija`, `eliminar_deduccion_fija`
- **`pwa.py`** · 56 líneas — Recursos PWA: manifiesto, service worker y favicon.
  - Funciones: `manifiesto`, `service_worker`, `favicon`
- **`trabajos.py`** · 298 líneas — Rutas del módulo "Trabajos Extras".
  - Funciones: `_fecha_opcional`, `_contexto`, `ver_trabajos_extras`, `crear_trabajo`, `cambiar_estado`, `eliminar_trabajo`, `agregar_gasto_trabajo`
- **`vistas.py`** · 203 líneas — Rutas de navegación principal y endpoint de salud.
  - Funciones: `iniciales_alias`, `contexto_base`, `verificar_salud`, `ver_dashboard`

#### `backend/app/servicios/`

- **`__init__.py`** · 14 líneas — Servicios de dominio (reglas de negocio puras).
- **`acceso_google.py`** · 123 líneas — Inicio de sesión con Google (cuenta de Gmail) mediante OAuth 2.0 (ADR-48).
  - Clases: `AccesoGoogleError`
  - Funciones: `google_activo`, `url_autorizacion`, `_leer_json`, `intercambiar_codigo`
- **`ahorro.py`** · 847 líneas — Planificador de ahorro y metas del usuario (SRS v1.3, bloque 3).
  - Clases: `MesMeta`, `MetaResumen`
  - Funciones: `etiqueta_quincena`, `valor_por_pago`, `_normalizar_modo_ambas`, `valor_mensual_efectivo`, `_mover_mes`, `_etiqueta_mes`, `_validar_duracion`, `crear_proyeccion`, `listar_proyecciones`, `_posicion`, `eliminar_proyeccion`, `extender_proyeccion`, `historial_metas`, `_detalle_pagos`, `meses_de_la_meta`, `_estado_mes`, `resumen_metas`, `saldo_libre_total`, `diagnostico`
- **`analitica.py`** · 302 líneas — Analítica de OLB_BYTE: reportes mensuales y anuales, clientes VIP y costos.
  - Clases: `_Acumulado`
  - Funciones: `_variacion`, `_ordenes_activas`, `anios_con_ventas`, `reporte_mensual`, `reporte_anual`, `ranking_vip`, `alertas_costos`
- **`auditoria.py`** · 61 líneas — Bitácora de auditoría de acciones sensibles.
  - Funciones: `registrar`, `listar_eventos`
- **`auxilio.py`** · 146 líneas — Evaluación del derecho al auxilio de transporte (SRS RF-07).
  - Clases: `EvaluacionAuxilio`
  - Funciones: `evaluar_auxilio_transporte`, `evaluar_auxilio_salarial`
- **`capacidad.py`** · 536 líneas — Capacidad de endeudamiento y proyección a doce meses (SRS v1.7, bloque F).
  - Clases: `Capacidad`
  - Funciones: `es_credito`, `_porcentaje`, `_repartir_arcos`, `_meses_equivalentes`, `_etiqueta_mes`, `_mover_mes`, `meses_siguientes`, `deudas_por_terminar`, `proyeccion_capacidad`, `_mensaje_semaforo`, `capacidad_trabajos`, `capacidad_endeudamiento`
- **`chancucos.py`** · 202 líneas — Referencias de pago rápido ("Chancucos").
  - Funciones: `_normalizar_dia`, `_normalizar_dias`, `_validar_url`, `crear_chancuco`, `listar_chancucos`, `alternar_favorito`, `eliminar_chancuco`
- **`comercial.py`** · 1442 líneas — Operación comercial de OLB_BYTE: ventas a crédito, cartera y deuda con proveedor.
  - Clases: `LineaVenta`, `PagoInicial`
  - Funciones: `ahora_tienda`, `normalizar_telefono`, `_dinero`, `_sumar_meses`, `_texto_garantia`, `_validar_linea`, `_cliente_para_venta`, `_siguiente_numero_orden`, `deuda_proveedor`, `_registrar_movimiento_proveedor`, `registrar_cliente`, `listar_clientes`, `buscar_clientes`, `registrar_venta`, `obtener_venta`, `_venta_activa`, `_recalcular_estado_pago`, `_validar_metodo`, `registrar_abono`, `_devuelto`, `_registrar_devolucion`, `anular_venta`, `registrar_devolucion`, `pendiente_devolver`, `obtener_abono`, `abonos_de_venta`, `buscar_cartera`, `registrar_abono_proveedor`, `listar_movimientos_proveedor`, `_texto_busqueda`, `filtrar_ventas`, `listar_ventas`, `cartera`, `resumen_cartera`, `estado_garantia`, `clasificar_saldo`, `barras_balance`, `segmentos_dona`, `etiqueta_producto`, `opciones_garantia`, `registrar_garantia`, `actualizar_estado_garantia`, `listar_garantias`, `garantia_vigente_al_reclamo`, `ranking_fallas`, `formatear_pesos`, `texto_compartir_factura`, `enlace_whatsapp_factura`, `enlace_whatsapp_recibo`, `enlace_whatsapp_cobro`, `_enlace_wa`
- **`consejero.py`** · 526 líneas — Consejero financiero del excedente mensual (SRS v1.7, bloque G).
  - Clases: `Consejo`, `_EstadoDeuda`
  - Funciones: `_tasa_mensual`, `_estados`, `_ordenar`, `_simular`, `_altura`, `_serie_comparada`, `_consejo_deuda`, `_consejo_ahorro`, `consejo_financiero`
- **`correo.py`** · 62 líneas — Envío de correos del sistema por SMTP estándar (SRS v1.8, bloque 8).
  - Funciones: `enviar_correo`
- **`deducciones_fijas.py`** · 187 líneas — Deducciones fijas del salario (SRS v1.4, REQ-08).
  - Funciones: `_validar`, `crear_deduccion`, `actualizar_deduccion`, `eliminar_deduccion`, `listar_deducciones`, `total_por_quincena`
- **`deudas.py`** · 549 líneas — Pasivos del usuario y amortización automática ("Resumen de Deudas").
  - Clases: `CuotaProyectada`
  - Funciones: `_limpiar_periodicidad`, `_sumar_periodo`, `_periodos_transcurridos`, `tasa_implicita`, `crear_deuda`, `listar_deudas`, `listar_pagos`, `_aplicar_pago`, `aplicar_cuotas_vencidas`, `proyeccion_deuda`, `cuota_mensual_equivalente`, `eliminar_deuda`, `resumen_deudas`
- **`factura_pdf.py`** · 159 líneas — Factura de OLB_BYTE: datos, logos, diseño compartido y conversión a PDF (ADR-36).
  - Funciones: `nombre_archivo`, `logo_como_data_uri`, `datos_factura`
- **`gastos.py`** · 333 líneas — Gastos y presupuesto del usuario.
  - Funciones: `valor_computable`, `crear_gasto`, `_normalizar_quincena`, `listar_gastos`, `total_gastos_mes`, `total_gastos_quincena`, `total_gastos_periodo`, `resumen_por_categoria`, `eliminar_gasto`, `actualizar_gasto`
- **`incapacidad.py`** · 361 líneas — Incapacidades laborales y reparto de días por mes calendario (Tarea 4).
  - Clases: `_AcumuladorMes`, `TramoMensual`, `SaldoIncapacidad`, `LiquidacionIncapacidad`, `ResultadoMesIncapacidad`
  - Funciones: `_validar_rango`, `calcular_incapacidad`, `liquidar_mes_incapacidad`
- **`nomina.py`** · 443 líneas — Motor de nómina colombiana — Tarea 2.
  - Clases: `DeduccionesLey`, `RecargoCalculado`, `ResultadoRecargos`, `LiquidacionNomina`
  - Funciones: `_obtener_parametros`, `_validar_no_negativo`, `calcular_valor_hora_ordinaria`, `calcular_deducciones_ley`, `calcular_recargo`, `calcular_recargos`, `calcular_total_devengado`, `liquidar_periodo`
- **`pagos_metas.py`** · 560 líneas — Metas de ahorro convertidas en gastos fijos con check de pago (SRS v1.6).
  - Funciones: `_posicion`, `_desde_posicion`, `_rango_del_mes`, `_gastos_de_meta_en_mes`, `_quincenas_de_la_meta`, `_meses_a_generar`, `_valor_vigente`, `asegurar_gastos_de_metas`, `sincronizar_abono`, `sincronizar_gasto`, `propagar_valor`, `marcar_pagado`, `desmarcar_pagado`, `registrar_abono_manual`, `limpiar_checks`, `inhabilitar_gasto`, `quitar_gasto`
- **`perfiles.py`** · 287 líneas — Perfil financiero del usuario (onboarding).
  - Funciones: `obtener_perfil`, `perfil_configurado`, `_validar_porcentaje`, `validar_quincenas`, `calcular_quincenas_desde_neto`, `guardar_perfil`, `porcentajes_quincena`, `sueldo_del_periodo`
- **`periodos.py`** · 191 líneas — Persistencia y consulta de periodos de nómina.
  - Funciones: `obtener_periodo`, `listar_periodos`, `horas_del_periodo`, `guardar_liquidacion`, `eliminar_periodo`
- **`quincenas.py`** · 226 líneas — Resumen de quincenas para el panel izquierdo de "Mis Finanzas".
  - Clases: `ResumenQuincena`
  - Funciones: `_etiqueta`, `resumen_quincenas`, `_a_decimal`
- **`recibo_imagen.py`** · 74 líneas — Recibo de abono de OLB_BYTE como imagen PNG para compartir por WhatsApp (RF-07).
  - Funciones: `nombre_archivo_recibo`, `texto_compartir_recibo`, `datos_recibo`
- **`registro_incapacidades.py`** · 201 líneas — Persistencia de incapacidades y consulta de sus tramos mensuales.
  - Funciones: `registrar_incapacidad`, `tramos_del_mes`, `descuento_del_mes`, `listar_incapacidades`, `eliminar_incapacidad`
- **`trabajos.py`** · 905 líneas — Ingresos independientes ("Trabajos Extras").
  - Funciones: `_posicion`, `_desde_posicion`, `_rango_del_mes`, `_fecha_con_dia`, `_normalizar_contrato`, `_normalizar_frecuencia`, `_normalizar_quincena`, `_monto_opcional`, `_porcentaje_opcional`, `reparto_por_porcentajes`, `reparto_quincenal`, `porcentaje_del_total`, `valor_del_pago`, `crear_trabajo`, `listar_trabajos`, `cambiar_estado`, `eliminar_trabajo`, `gastos_fijos_trabajo`, `crear_gasto_trabajo`, `_pagos_del_mes`, `_meses_a_generar`, `_crear_pagos_del_mes`, `asegurar_pagos_trabajos`, `_periodos_del_trabajo`, `pagos_del_mes`, `extras_cobrados_mes`, `resumen_trabajos`
- **`usuarios.py`** · 359 líneas — Repositorio de usuarios sobre SQLAlchemy (Fase 2).
  - Funciones: `_normalizar_correo`, `correo_valido`, `sembrar_demostracion`, `buscar_por_correo`, `obtener_por_id`, `listar_usuarios`, `autenticar`, `crear_usuario`, `actualizar_alias`, `cambiar_contrasena`, `cambiar_rol`, `cambiar_estado`, `huella_contrasena`, `restablecer_contrasena`, `url_avatar_valida`, `actualizar_avatar`

#### `backend/app/static/`

- **`manifest.webmanifest`** · 35 líneas — Manifiesto PWA

#### `backend/app/static/css/`

- **`estilos.css`** · 3672 líneas — Fondo y superficies
- **`factura-olb.css`** · 671 líneas — Sello de Anulada si aplica

#### `backend/app/static/js/`

- **`app.js`** · 281 líneas — Mejoras progresivas globales.
  - Funciones: `copiar`, `seleccionarManual`, `cerrarEdicion`
- **`factura.js`** · 304 líneas — Factura y recibo de abono de OLB_BYTE como imagen PNG (ADR-50).
  - Funciones: `descargar`, `esperarImagen`, `montarHoja`, `crearPng`, `imagenDe`, `copiarImagen`, `mensajeDelEnlace`, `compartirArchivo`, `enviarPorWhatsapp`, `descargarImagen`
- **`finanzas.js`** · 598 líneas — Mejora progresiva de "Mis Finanzas".
  - Funciones: `leerFormulario`, `pintarCampo`, `pintarDeduccion`, `pintarValorAuxilio`, `pintarErrores`, `pintarDetalle`, `pintarAuxilio`, `aplicarResultado`, `pintarTramos`, `pintarIncapacidad`, `pintarQuincenas`, `pintarTexto`, `calcular`, `programarCalculo`, `marcarCambios`, `aplicarPlantilla`, `copiarAlPortapapeles`, `prepararCopiadoRapido`
- **`incapacidades.js`** · 129 líneas — Cálculo automático del módulo de incapacidades (SRS v1.5).
  - Funciones: `fechasListas`, `reemplazar`, `actualizar`, `programar`
- **`olb_byte.js`** · 521 líneas — Formulario de venta de OLB_BYTE: forma de pago, productos guardados y totales.
  - Funciones: `numero`, `pesos`, `normalizarTelefono`, `leerCampos`, `escribirPanel`, `escribirEdicion`, `validarProducto`, `mostrarError`, `actualizarSubtotalPanel`, `hayDatosEnPanel`, `leerFila`, `escribirFila`, `actualizarVacia`, `recalcular`, `agregarFila`, `guardarProducto`, `habilitarPanel`, `sincronizarPago`, `mostrarNotaContactos`, `pegarNumero`
- **`perfil.js`** · 99 líneas — Mejora progresiva del perfil financiero (SRS v1.2).
  - Funciones: `alternarSubgrupo`, `conocePorcentajes`, `actualizar`
- **`presupuesto.js`** · 170 líneas — Mejora progresiva de "Gastos y Presupuesto" (SRS v1.3, bloque 3).
  - Funciones: `aNumero`, `formatear`, `usaAmbasQuincenas`, `duplicaElMonto`, `sincronizarModo`, `actualizarTotal`
- **`sw.js`** · 78 líneas — Service worker de la PWA.

#### `backend/app/static/js/vendor/`

- **`html-to-image.js`** · 3 líneas — # sourceMappingURL=html-to-image.js.map

#### `backend/app/templates/`

- **`base.html`** · 102 líneas — Encabezado: marca institucional + alias del usuario y badge de rol.
- **`dashboard.html`** · 53 líneas — Plantilla: Panel principal
- **`login.html`** · 88 líneas — Plantilla: Iniciar sesión
- **`olvide_contrasena.html`** · 29 líneas — Plantilla: Recuperar contraseña
- **`registro.html`** · 59 líneas — Plantilla: Crear cuenta
- **`restablecer_contrasena.html`** · 37 líneas — Plantilla: Nueva contraseña

#### `backend/app/templates/admin/`

- **`usuarios.html`** · 76 líneas — Plantilla: Usuarios

#### `backend/app/templates/chancucos/`

- **`_dias.html`** · 15 líneas
- **`index.html`** · 160 líneas — Plantilla: Configurar Atajos de Pago

#### `backend/app/templates/componentes/`

- **`avatar.html`** · 21 líneas

#### `backend/app/templates/deudas/`

- **`index.html`** · 229 líneas — Plantilla: Resumen de Deudas

#### `backend/app/templates/finanzas/`

- **`_capacidad.html`** · 119 líneas
- **`_gasto_fijo.html`** · 188 líneas
- **`_subnav.html`** · 27 líneas — Subnavegación interna del módulo "Mis Finanzas" (SRS v1.3, bloque 1).
- **`index.html`** · 726 líneas — Plantilla: Mis Finanzas

#### `backend/app/templates/gastos/`

- **`index.html`** · 143 líneas — Plantilla: Gastos

#### `backend/app/templates/historial/`

- **`imprimir.html`** · 41 líneas — Plantilla: Liquidación
- **`index.html`** · 109 líneas — Plantilla: Historial de Registros

#### `backend/app/templates/incapacidades/`

- **`index.html`** · 243 líneas — Plantilla: Incapacidades

#### `backend/app/templates/olb_byte/`

- **`_fragmento_factura.html`** · 3 líneas — Plantilla Jinja2
- **`_fragmento_recibo.html`** · 8 líneas — Plantilla Jinja2
- **`_hoja_factura.html`** · 254 líneas
- **`_recibo.html`** · 47 líneas
- **`_subnav.html`** · 30 líneas — Subnavegación de OLB_BYTE con el mismo componente que Mis Finanzas (subnav-finanzas).
- **`analitica.html`** · 212 líneas — Plantilla: Analítica
- **`cartera.html`** · 133 líneas — Plantilla: Cartera y liquidez
- **`cobro.html`** · 93 líneas — Plantilla: Gestionar cobro
- **`factura.html`** · 36 líneas — Plantilla: Factura No.
- **`garantias.html`** · 148 líneas — Plantilla: Garantías
- **`index.html`** · 466 líneas — Plantilla: OLB_BYTE
- **`pendientes.html`** · 117 líneas — Plantilla: Pendientes de pago
- **`recibo.html`** · 23 líneas — Plantilla: Recibo de abono · No.

#### `backend/app/templates/perfil/`

- **`index.html`** · 245 líneas — Saludo de onboarding: usa el alias capturado en el registro (SRS v1.2).

#### `backend/app/templates/presupuesto/`

- **`index.html`** · 523 líneas — Plantilla: Gastos y Presupuesto

#### `backend/app/templates/privado/`

- **`index.html`** · 40 líneas — Módulo privado: sólo un ADMIN_OLB llega a esta plantilla.

#### `backend/app/templates/trabajos/`

- **`index.html`** · 316 líneas — Plantilla: Trabajos Extras

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
si la petición lo pide (`_pide_json`) y redirección con 303 si es HTML. Inicializa
la base al arrancar y cierra `/docs` en producción.

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

### `backend/app/core/config.py`

Parámetros de negocio y entorno, sin valores mágicos en el resto del código.
`ParametrosNomina` reúne horas mensuales (210), porcentajes de salud/pensión,
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
`AAAA-MM` y resuelve el mes actual si llega vacío.

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
entrega `cafe` (monto y QR de Bre-B en data URI) para el apoyo voluntario.

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
pago (o de la creación).

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

### 5.4 Servicios de dominio

### `backend/app/servicios/__init__.py`

Paquete de servicios; documenta la convención: funciones puras, sin FastAPI, que
reciben `Session` solo cuando necesitan persistir.

### `backend/app/servicios/nomina.py`

Motor salarial colombiano. `calcular_valor_hora_ordinaria` divide el básico entre
210 h; `calcular_deducciones_ley` aplica 4 % + 4 % sobre el **devengado**
(básico + extras − incapacidad, ADR-19); `calcular_recargo`/`calcular_recargos`
aplican la matriz de factores (1,25 / 1,75 / 2,00 / 2,50 / 0,35 / 1,90);
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
liquidación y las quincenas.

### `backend/app/servicios/quincenas.py`

Panel izquierdo de Mis Finanzas. `resumen_quincenas` reparte el sueldo por los
porcentajes del perfil, suma recargos en la quincena configurada, resta
incapacidad, deducciones de ley (solo en la quincena marcada), fijas y gastos, y
devuelve una `ResumenQuincena` por pago con saldo libre. `_etiqueta` nombra cada
pago y `_a_decimal` normaliza entradas.

### `backend/app/servicios/gastos.py`

CRUD y agregados de gastos. `crear_gasto` valida monto/fecha y
`_normalizar_quincena` acepta 1, 2 o `NULL` («todo el mes»). `listar_gastos`,
`total_gastos_mes`, `total_gastos_quincena`, `total_gastos_periodo` y
`resumen_por_categoria` alimentan vistas y diagnóstico; `actualizar_gasto`
mantiene la quincena al editar.

### `backend/app/servicios/deducciones_fijas.py`

Descuentos de nómina del SRS v1.4. `crear_deduccion`, `actualizar_deduccion` y
`eliminar_deduccion` validan concepto, valor y quincena; `listar_deducciones` y
`total_por_quincena` entregan lo que resta la caja única de deducciones.

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

Amortización automática (v1.5). `tasa_implicita` resuelve por bisección
`saldo = cuota × (1 − (1+r)^−n) / r` con precisión de 10 decimales;
`crear_deuda` valida los seis datos y persiste la tasa derivada;
`aplicar_cuotas_vencidas` avanza el calendario desde el último pago y registra
cada cuota en `PagoDeuda` mediante `_aplicar_pago`, donde la última absorbe el
redondeo y deja el saldo en cero. `proyeccion_deuda` lista las cuotas futuras,
`cuota_mensual_equivalente` mensualiza la quincenal y `resumen_deudas` totaliza la
cartera.

### `backend/app/servicios/capacidad.py`

Capacidad de endeudamiento y proyección a doce meses (SRS v1.7, bloque F).
`capacidad_endeudamiento` suma el ingreso de las quincenas y los extras cobrados,
resta gastos fijos, deducciones y cuota mensual de deudas, y reparte el resultado
en tres arcos (`_repartir_arcos`) que siempre cierran en 100. El semáforo usa el
porcentaje de deuda sobre el ingreso (`UMBRAL_VERDE = 20`, `UMBRAL_AMBAR = 35`).
`deudas_por_terminar` lista las deudas con tres cuotas o menos y su fecha de
cierre; `proyeccion_capacidad` simula doce meses en los que la cuota baja cuando
cada deuda termina. No escribe en la base de datos.

### `backend/app/servicios/consejero.py`

Consejero del excedente (SRS v1.7, bloque G). Solo se activa si el disponible
supera `UMBRAL_ACTIVACION = 300000`. Con deudas simula doce meses de cuotas
mínimas frente a un escenario que aplica todo el excedente, compara bola de nieve
(`_ordenar` por saldo) y avalancha (por tasa) y recomienda la de menor interés,
con la deuda objetivo y los pasos a seguir. Sin deudas dirige el excedente a las
metas (`ahorro.resumen_metas`) o sugiere crear una. `_serie_comparada` entrega
las doce filas de la gráfica base frente a optimizado. No escribe en la base.

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

### 5.5 Estáticos (`static/`)

### `backend/app/static/css/estilos.css`

Clases `.avatar`, `.avatar--compacto`, `.avatar--destacado` y `.avatar__iniciales`: círculo
con degradado `#0066cc` a `#00a8ff` y tamaños de 36 px y 96 px (SRS v1.8). `sw.js` en `olb-finanzas-v30`.

Única hoja de estilos. Define la paleta oficial en `:root`, componentes
(tarjetas, paneles, tablas, botones, formularios), las dos rejillas de Mis
Finanzas (`rejilla-finanzas` y `--5050`), la tabla compacta del desglose y las
reglas móviles: submenú 2 × 2 a 640 px, `.fila-campos` a una columna, paneles a
16 px y botones a ancho completo; a 640 px o menos la edición de un gasto
(`edicion-gasto--modal`) se abre centrada, con fondo oscuro y scroll propio.
Incluye estilos de impresión de la factura y
del historial.

### `backend/app/static/js/app.js`

Mejoras globales: `copiar` usa la API de portapapeles con respaldo
(`seleccionarManual`), la delegación `data-copiar` pinta «¡Copiado!», las filas
plegables y el registro del service worker. `cerrarEdicion` descarta la edición
en línea desde «Cancelar», el fondo oscuro móvil o la tecla Escape. Sin
dependencias.

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
(neto); `actualizar` mantiene los avisos de suma 100 %.

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
producción solo registra el fallo, sin contenido ni enlaces.

### `backend/app/static/js/factura.js`

Acciones de la factura. Captura la hoja como PNG con `html-to-image` en el navegador (ADR-50). La imagen se prepara al cargar la página. «Compartir por WhatsApp»: en móvil abre la hoja de compartir del sistema con el PNG adjunto y el mensaje; en escritorio copia el PNG al portapapeles en el mismo clic, abre la conversación del número del cliente (wa.me/57…) y descarga el PNG. WhatsApp Web no admite adjuntos desde un enlace, por eso se pega con Ctrl+V. Si la orden no tiene celular, el botón avisa y no abre nada. «Descargar imagen» solo descarga el PNG (SRS v1.8).

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
de la tienda. La misma plantilla se usa en la página del recibo y en la captura.

### `backend/app/templates/olb_byte/_fragmento_recibo.html`

Fragmento que sirve `_recibo.html` en `/olb-byte/recibos/{id}/hoja` para la captura.

### `backend/app/templates/olvide_contrasena.html`

Formulario «Recuperar contraseña» con el correo de la cuenta. Muestra siempre el mensaje
neutro tras enviarlo, y un enlace de regreso al login.

### `backend/app/templates/restablecer_contrasena.html`

Formulario de nueva contraseña (contraseña y repetición, mínimo 8 caracteres). Si el enlace
no es válido o venció, muestra el aviso y el enlace para pedir uno nuevo.

### `backend/app/servicios/analitica.py`

Analítica de OLB_BYTE (RF-12 a RF-14). `reporte_mensual` agrupa las órdenes activas por
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
`start_url`. Lo sirve `routers/pwa.py`.

### 5.6 Plantillas

### `backend/app/templates/base.html`

El pie muestra solo «Finanzas · v1.0.0 | © año», sin el entorno (SRS v1.8). El `body` acepta
la clase de cada pantalla mediante el bloque `clase_cuerpo`.

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
(porcentajes + quincena de deducciones) o caso B (neto sin deducciones). Incluye
cambio de contraseña y, para el administrador, acceso a Usuarios.

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
`trabajos/index.html` para que ambas vistas sean idénticas.

### `backend/app/templates/finanzas/_capacidad.html`

Panel compartido de capacidad de endeudamiento (SRS v1.7, bloque F). La macro
`panel_capacidad(capacidad, titulo, descripcion)` dibuja la dona del ingreso
repartido entre gastos fijos, cuota de deudas y libre, la leyenda con montos y
porcentajes, el semáforo, las deudas con tres cuotas o menos y la tabla de doce
meses con su barra de saldo libre. Se incluye una vez en `presupuesto/index.html`
y otra en `trabajos/index.html`, cada una con su propio título.

### `backend/app/templates/gastos/index.html`

Registro de gastos: formulario, lista con acciones de edición en línea
(`<details>`) y totales por quincena. Enlace de regreso al planificador.

### `backend/app/templates/presupuesto/index.html`

Planificador: diagnóstico del mes, alerta de liquidez, formulario de metas (con
«Ambas quincenas»), tarjetas de metas con avance, abonos mensuales y gestión de
deducciones fijas del salario.

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

Cuatro tarjetas de resumen, formulario de seis campos y tabla de deudas con tasa
implícita. Cada fila despliega «Ver amortización»: cuotas aplicadas y próximas
cuotas con interés, capital y saldo.

### `backend/app/templates/chancucos/_dias.html`

Distintivo de los días de pago de un atajo (SRS v1.7, bloque D). La macro
`dias_pago(item, clase)` imprime «Día 15» o «Día 15 · Día 30» a partir de
`dia_pago_1`/`dia_pago_2`, con clase CSS configurable. Se reutiliza en la tarjeta
de atajos de Mis Finanzas y en la tabla de «Configurar Atajos de Pago» para
mostrar exactamente el mismo texto.

### `backend/app/templates/chancucos/index.html`

Configuración de atajos: formulario de tres campos con la pregunta «¿Es un único
pago mensual?» (una o dos fechas), y lista con referencia, días de pago, enlace,
favorito, copiar y eliminar.

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

1. El usuario registra acreedor, descripción, saldo, cuota, cuotas y periodicidad.
2. `tasa_implicita` deriva `r` por bisección y se guarda en `deudas.tasa_interes`.
3. Al abrir el módulo, `aplicar_cuotas_vencidas` cuenta periodos vencidos desde el
   último pago (o la creación) y registra cada cuota.
4. La última cuota se recalcula como `saldo + interés` y deja el saldo en cero.
5. `proyeccion_deuda` muestra lo que falta sin alterar la base.

### 6.5 Meta con «Ambas quincenas»

`quincena = 3` guarda la cuota **mensual** y `valor_por_pago` la divide entre dos.
La interfaz muestra «Ambas quincenas (X por pago)». El planificador compara contra
el saldo libre total, no contra un pago concreto.

---

## 7. Motor financiero en fórmulas

| Concepto | Fórmula |
| --- | --- |
| Hora ordinaria | `sueldo_básico / 210` |
| Recargo | `valor_hora × horas × factor` |
| Devengado | `básico + Σ recargos − descuento_incapacidad` |
| Salud / Pensión | `4 % × devengado` cada una |
| Auxilio de transporte | `$ 200.000` si `básico + recargos ≤ 2 SMMLV`, si no `0` |
| Incapacidad días 1–2 | `100 %` del valor día |
| Incapacidad día 3+ | `66,67 %` (descuento `33,33 %`) |
| Quincena | `sueldo × porcentaje` + recargos − deducciones imputadas − fijas − gastos |
| Tasa implícita de deuda | `saldo = cuota × (1 − (1+r)^−n) / r` |
| Cuota final | `saldo_pendiente + interés_del_periodo` |

Constantes parametrizables en `core/config.py`: 210 h, 4 % + 4 %, factores
1,25/1,75/2,00/2,50/0,35/1,90, SMMLV y tope de 2 SMMLV (COP 3.501.810).

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

---

## 9. Comandos y pruebas

```bash
cd backend
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

.\.venv\Scripts\python -m compileall -q app     # sintaxis
.\.venv\Scripts\python -m pytest -q             # suite completa (260 pruebas)
.\.venv\Scripts\python scripts\respaldo.py      # respaldo SQLite
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
| `test_gastos_deudas.py` | Gastos, tasa implícita y amortización automática. |
| `test_presupuesto.py` | Metas, abonos, «Ambas quincenas», deducciones fijas. |
| `test_auth.py`, `test_seguridad*.py` | Login, RBAC, JWT, CSRF y cabeceras. |
| `test_vistas.py`, `test_finanzas_vistas.py` | Renderizado y navegación. |
| `test_trabajos_chancucos.py`, `test_comercial.py` | Módulos restantes. |
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

1. `python -m compileall -q app` sin errores.
2. `pytest -q` en verde (hoy: 260).
3. Migraciones nuevas probadas **dos veces** sobre copia de `finanzas.db`.
4. `sw.js` con la caché subida si cambió CSS o JS.
5. `python scripts\generar_guia.py` y luego `--verificar` sin problemas.
6. `MEMORY.md` con la bitácora y el ADR si cambió una regla.
7. `AGENTS.md` §9 con el estado verificado y el conteo de pruebas.
