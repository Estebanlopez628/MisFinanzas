# Skill Name: olb-finanzas-workflow
# Description: Asistente técnico principal y arquitecto full-stack para el desarrollo modular y escalable del proyecto "Finanzas y OLB_BYTE". Garantiza el cumplimiento de normativas de negocio colombianas, control estricto por fases (plan.md, tasks.md, constitution.md), desarrollo paso a paso y la sincronización continua de la memoria técnica en español.

## 1. Alcance y Cobertura de Módulos
Esta skill rige el desarrollo, mantenimiento y expansión de todo el ecosistema del proyecto, abarcando de forma secuencial:
- **Módulo 1:** Finanzas Personales, motor de nómina, cálculo de hora ordinaria (210h), deducciones de ley automáticas (4% Salud y 4% Pensión), validación de 2 SMMLV para auxilio de transporte, incapacidades con rollover (arrastre de saldos) y panel de referencias de pago ("chancucos").
- **Módulo 2:** OLB_BYTE Admin Suite (Gestión de inventarios, control de ventas y registro de abonos/cartera).
- **Módulo 3:** Módulo POS físico y pasarela de cobros/devueltas con interfaz táctil y de alta velocidad.
- **Módulo 4:** Sistema de automatización de notificaciones y facturación vía WhatsApp / Google Sheets.

## 2. Reglas de Negocio Innegociables (Colombia)
- **Base Horaria:** Jornada mensual estandarizada en 210 horas (bajo el marco de 42 horas semanales).
- **Deducciones Obligatorias:** 4% de Salud y 4% de Pensión calculadas automáticamente sobre el sueldo básico, mostradas de forma transparente.
- **Auxilio de Transporte:** Evaluación constante del umbral de 2 Salarios Mínimos Legales Vigentes (`Sueldo Básico + Total de Recargos`). Si supera el límite, se desactiva de forma automática ($0).
- **Incapacidades y Arrastre (Rollover):** Cálculo por rangos de fecha, descuento a partir del tercer día liquidado al 66.67% (reducción del 33.33%), con persistencia y arrastre automático de saldos/días pendientes hacia el periodo siguiente.

## 3. Flujo de Trabajo Operativo (Paso a Paso)
1. **Desarrollo Modular Estricto:** NUNCA desarrollar todo de golpe. Se trabaja estrictamente tarea por tarea siguiendo el orden definido en `plan.md` y `tasks.md`.
2. **Validación Previa:** Antes de avanzar al siguiente bloque o componente, se debe presentar el fragmento de código estructurado para su revisión y validación conjunta.
3. **Control Normativo y Constitucional:** Toda línea de código y lógica debe alinearse con la especificación activa (`SRS v1.1.0`), respetando la jerarquía normativa y la privacidad de los datos del usuario.

## 4. Obligación de Documentación Continua
- Cada vez que se complete una tarea, se implemente un cambio o se resuelva un componente técnico en cualquiera de los módulos, el agente está **OBLIGADO** a actualizar y registrar de forma explícita los detalles, decisiones y cambios en los archivos **`memory.md`** y **`agents.md`**.
- Toda la documentación, comentarios de código, docstrings y registros en las memorias deben redactarse utilizando un **español claro, técnico y estructurado**.