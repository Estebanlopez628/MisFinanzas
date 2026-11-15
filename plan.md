# Plan de Trabajo — OLB_BYTE & Finanzas Personales

> Stack oficial: **Python (FastAPI + Jinja2 + HTMX)**. Cada fase se ejecuta tarea por tarea con validación previa.

## Fase 0 — Estructuración y Arquitectura Base
- Configuración de repositorio, archivos de contexto (`AGENTS.md`, `MEMORY.md`, `constitution.md`) y política de documentación.
- Definición del **diccionario de datos** (`diccionario_datos.md`) como contrato previo a la base de datos.
- Andamiaje de la aplicación: fábrica FastAPI, configuración de parámetros de negocio, montaje de estáticos, plantillas base y paleta visual.

## Fase 1 — Módulo de Autenticación y Perfil
- Implementación del login con hash de contraseña y sesión por token (JWT en cookie `HttpOnly`).
- Control de roles (`ADMIN_OLB`, `USER_FINANZAS`) a nivel de dependencia FastAPI y de plantilla.
- Onboarding: alias, sueldo básico, modalidad y porcentaje quincenal.

## Fase 2 — Motor Financiero y Nómina ("Mis Finanzas")
- Funciones puras: hora ordinaria (210 h), deducciones de ley (4% + 4%), matriz de recargos y horas extras con decimales.
- Validador automático del tope de 2 SMMLV para el auxilio de transporte.
- Liquidación de periodo (mensual y quincenal) con desglose transparente.

## Fase 3 — Módulo de Incapacidades y Arrastre de Saldos
- Formulario por rangos de fecha, cálculo de días 1–2 al 100% y días 3+ al 66.67%.
- Persistencia del rollover y aplicación automática como deducción en el periodo siguiente.

## Fase 4 — Dashboard y Panel de Chancucos
- Dashboard de 4 tarjetas con visibilidad condicionada por rol (ya maquetado en Fase 0).
- Panel privado de referencias de pago: copiado al portapapeles y redirección segura.

## Fase 5 — Persistencia y Despliegue
- Modelos SQLAlchemy 2.x y migraciones derivadas **exactamente** de `diccionario_datos.md`.
- Pruebas `pytest` del motor financiero con casos límite (tope SMMLV, cruce de mes, decimales).
- Empaquetado PWA (manifest + service worker mínimo) y despliegue.
