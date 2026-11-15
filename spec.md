# Spec 001: Núcleo del Sistema, Autenticación y Módulo de Finanzas Personales

## Objetivo
Desarrollar el flujo de autenticación por roles, el dashboard principal de 4 tarjetas y el motor automatizado del cuadro de nómina y finanzas personales.

## Componentes Técnicos
1. **Control de Acceso (RBAC):** Pantalla de login unificada con redirección basada en roles (`USER_FINANZAS` y `ADMIN_OLB`).
2. **Onboarding de Perfil:** Configuración inicial de sueldo básico, modalidad de pago (mensual/quincenal), porcentaje quincenal y captura de un alias de usuario para saludos personalizados.
3. **Motor Salarial e Ingresos:** 
   - Cálculo automático de la hora ordinaria basada en una jornada mensual de 210 horas.
   - Matriz de recargos y horas extras con soporte decimal.
   - Evaluación dinámica del umbral de 2 SMMLV para la asignación o anulación del auxilio de transporte.
4. **Gestión de Incapacidades con Arrastre (Rollover):** Formulario por rangos de fecha que computa los días al 66.67% y traslada los remanentes al mes siguiente.
5. **Panel de Chancucos (Solo Administrador):** Listado de contratos y servicios con función de copiado rápido al portapapeles y enlaces directos de pago web.