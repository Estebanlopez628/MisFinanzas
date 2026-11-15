# Tareas Pendientes / Backlog Activo

## Completadas

- [x] **T1. Estructura base de componentes** (Python/FastAPI + Jinja2 + CSS con paleta oficial, navegación y RBAC visual).
- [x] **T0.1** Documento `diccionario_datos.md` con el modelo lógico completo (previo a BD).
- [x] **T0.2** Política de documentación de código (docstrings obligatorios en español) registrada en `AGENTS.md`, `MEMORY.md` y `constitution.md`.
- [x] **T2. Motor de nómina (lógica pura)** — `backend/app/servicios/nomina.py`:
  - [x] `calcular_valor_hora_ordinaria(sueldo_basico, parametros)` → base de 210 h
  - [x] `calcular_deducciones_ley(sueldo_basico, parametros)` → salud 4% + pensión 4%
  - [x] `calcular_recargo(...)` y `calcular_recargos(...)` → matriz completa con decimales
  - [x] `calcular_total_devengado(sueldo, recargos)` según SRS RF-07
  - [x] `liquidar_periodo(...)` con desglose, auxilio e incapacidad como parámetros
  - [x] 22 pruebas unitarias en `tests/test_nomina.py`
- [x] **T3. Validador del tope de 2 SMMLV** — `backend/app/servicios/auxilio.py`:
  - [x] `evaluar_auxilio_transporte(total_devengado)` con tope 2 SMMLV
  - [x] `evaluar_auxilio_salarial(sueldo_basico, total_recargos)` según SRS RF-07
  - [x] Mensaje literal del SRS y diferencia restante hasta el tope
  - [x] Integración opcional en `liquidar_periodo(aplicar_auxilio_legal=True)`
  - [x] 11 pruebas unitarias en `tests/test_auxilio.py`
- [x] **T4. Motor de incapacidades y rollover** — `backend/app/servicios/incapacidad.py`:
  - [x] `calcular_incapacidad(fecha_inicio, fecha_fin, sueldo_basico)` con días 1–2 al 100% y 3+ al 66.67%
  - [x] Reparto por mes calendario (`TramoMensual`), cruce de mes y de año
  - [x] `liquidar_mes_incapacidad(...)` con `saldos_pendientes` para el mes siguiente
  - [x] 17 pruebas unitarias en `tests/test_incapacidad.py`
- [x] **T4b. Formulario de incapacidades** — `routers/incapacidades.py` + `templates/incapacidades/index.html`:
  - [x] `GET /incapacidades` y `POST /incapacidades/calcular` con repoblado tras error
  - [x] Tarjetas de resultado, tabla de tramos y tabla de saldos arrastrados
  - [x] `parsear_monto`, `parsear_periodo_mes` y `formatear_mes_anio` en `core/texto.py`
  - [x] 11 pruebas de helpers (`test_texto.py`) y 10 de vista
- [x] **T5. RBAC real** — login, sesión y bloqueo de rutas privadas:
  - [x] `core/seguridad.py`: PBKDF2-HMAC-SHA256 y JWT HS256 sin dependencias externas
  - [x] `servicios/usuarios.py`: repositorio en memoria, cuentas demo y registro público
  - [x] `dependencias.py`: `SesionRequerida`, `usuario_opcional`, `obtener_usuario_actual`, `exigir_administrador`
  - [x] `routers/auth.py`: `GET/POST /login`, `POST /salir`, `GET/POST /registro`
  - [x] Cookie `sesion` `HttpOnly` + `SameSite=Lax`; 303 al login y 401 JSON para la UI
  - [x] `USER_FINANZAS` recibe **403** en los cuatro módulos privados
  - [x] 11 pruebas de seguridad y 11 de autenticación/RBAC
- [x] **T6. Calculadora reactiva de "Mis Finanzas"** — `routers/finanzas.py` + `static/js/finanzas.js`:
  - [x] `GET/POST /finanzas` como respaldo sin JavaScript
  - [x] `POST /finanzas/calcular` con totales, desglose y mensaje del auxilio en JSON
  - [x] Debounce de 150 ms y actualización del DOM (tarjetas, tabla y aviso de 2 SMMLV)
  - [x] 12 pruebas de vista y endpoint
- [x] **T7. Persistencia SQLite + SQLAlchemy 2.x** — `core/base_datos.py`, `modelos.py`:
  - [x] Todas las tablas de `diccionario_datos.md` (§2 a §13) con UUID, `Numeric` y `CHECK`
  - [x] Sesión por petición, claves foráneas activas y siembra idempotente de cuentas demo
  - [x] `DATABASE_URL` parametrizable y ADR-09 (SQLite ahora, PostgreSQL después)
- [x] **T8. Perfil y onboarding salarial** — `routers/perfil.py`, `servicios/perfiles.py`:
  - [x] Sueldo básico, modalidad mensual/quincenal, porcentaje y alias
  - [x] Precarga del sueldo del periodo en la calculadora y cambio de contraseña
- [x] **T9. Historial, exportación e incapacidades persistidas**:
  - [x] Guardar/actualizar periodos y detalle de horas extra
  - [x] Rollover aplicado al periodo siguiente y liberado al eliminar
  - [x] Exportación CSV, comparación entre meses y versión imprimible
- [x] **T10. Gastos, Chancucos, Deudas y Trabajos Extras**:
  - [x] Gastos fijos/variables con totales por mes y categoría
  - [x] Referencias de pago con copiado, favorito y validación de URL
  - [x] Deudas con abonos y estado; trabajos extras con estado COBRADO/PENDIENTE
- [x] **T11. OLB_BYTE** — `routers/olb_byte.py`, `servicios/comercial.py`:
  - [x] Productos, clientes, ventas multipartida con descuento de stock
  - [x] Abonos, cartera, factura imprimible y enlace de WhatsApp
- [x] **T12. PWA, publicidad y endurecimiento**:
  - [x] Manifest, service worker (solo estáticos), íconos y favicon
  - [x] Exportación/impresión, aviso de cambios sin guardar y publicidad por rol
  - [x] CSRF por origen, CSP/nosniff/frame, rate limiting y auditoría
  - [x] Administración de cuentas (rol y estado) con protección de la propia cuenta
  - [x] `/docs` cerrado y `CLAVE_SECRETA` obligatoria en producción
- [x] **T13. Operación y CI**:
  - [x] `backend/scripts/respaldo.py` con API `backup`, verificación y rotación
  - [x] Nombres con microsegundos, rotación por nombre y cierre explícito de conexiones (Windows)
  - [x] 12 pruebas en `tests/test_respaldo.py` (copia real, integridad, rotación y CLI)
  - [x] `.github/workflows/ci.yml` (compileall + pytest + respaldo)
  - [x] `DESPLIEGUE.md` con systemd, NSSM, Nginx/HTTPS, respaldos y rollback
  - [x] Verificación final: **185 pruebas** en verde y `compileall` OK

## En curso / Siguiente

- [ ] **T14 (opcional). PostgreSQL + Alembic** para despliegue multi-instancia (ver `DESPLIEGUE.md` §11).

## Backlog posterior

- [ ] Notificaciones de cuotas y recordatorios de pago.
- [ ] Multiusuario real para OLB_BYTE (hoy el módulo es exclusivo de `ADMIN_OLB`).
- [ ] Facturación electrónica ante la DIAN (la factura actual es un comprobante interno).
