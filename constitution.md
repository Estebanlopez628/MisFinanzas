# Constitución — OLB_BYTE & Finanzas Personales

Principios innegociables. Toda especificación, plan y tarea debe cumplirlos de forma estricta.

1. **Separación de Roles (RBAC Estricto):**
   - El sistema es público para la gestión de finanzas personales (`USER_FINANZAS`) y privado exclusivamente para el administrador (`ADMIN_OLB`), protegiendo el módulo de ventas, cartera y enlaces de pago ("chancucos").

2. **La Especificación Activa Manda:**
   - La especificación vigente es la **SRS v3.9.3** (sección 13 del archivo `especificaci_n_de_requisitos_de_software_srs.md`), que conserva las reglas de v1.1.0 a v3.9.1 salvo contradicción explícita.
   - Ninguna funcionalidad de cálculo salarial, recargos, incapacidades o control de quincenas se implementa si no está formalmente detallada en la especificación activa.

3. **Cálculos Financieros Transparentes y Automáticos:**
   - Las deducciones de ley (4% Salud y 4% Pensión) y la validación del tope de 2 Salarios Mínimos para el auxilio de transporte se ejecutan de forma automática e invariable bajo la normativa legal colombiana vigente.

4. **Trazabilidad y Corte Mensual de Incapacidades:**
   - El registro de incapacidades se calcula por días calendario, aplica la regla 100 % / 66,67 % una sola vez sobre la incapacidad completa y descuenta **solo el tramo de cada mes** cuando el rango cruza de mes. No hay rollover: los saldos pendientes heredados se marcan como aplicados (SRS v1.5, ADR-20).

5. **Actualización de Archivos de Control (AGENTS.md & MEMORY.md):**
   - Es obligatorio mantener sincronizados los registros del agente y la memoria de decisiones técnicas en cada avance del desarrollo.

6. **Lenguaje Único: Python:**
   - Todo el sistema (lógica de negocio, servidor, vistas y pruebas) se implementa en **Python**. El frontend se renderiza con **Jinja2** y la interactividad se limita a mejoras progresivas (HTMX / JavaScript mínimo). Queda prohibido incorporar frameworks JavaScript como núcleo (React, Vite, Node.js).

7. **Documentación Obligatoria del Código:**
   - Cada módulo, clase, función y método debe incluir docstring en **español técnico**, indicando propósito, parámetros, retorno y excepciones.
   - Los comentarios deben explicar la **regla de negocio**, no repetir la sintaxis.
   - Ningún cambio se considera terminado si no está documentado en el propio código.

8. **Diccionario de Datos como Contrato:**
   - `diccionario_datos.md` es la fuente única de verdad del modelo de datos.
   - No se crea ninguna tabla, columna o migración que no esté previamente documentada y aprobada en dicho archivo.

9. **No Regresión y Separación Estricta por Rol (SRS v2.0 y v3.0):**
   - No se altera el diseño, los cálculos, los estados ni el mensaje de las facturas de OLB_BYTE. Solo se saneó el destinatario del enlace de WhatsApp y se prohibió la Web Share API en los tres botones (factura, ícono rápido y recibos): siempre apertura directa de `wa.me/<numero>`.
   - OLB_BYTE y la facturación son exclusivos del administrador. Guías, preguntas frecuentes, selectores de reporte y textos legales del usuario estándar no los mencionan.
   - Los gastos vinculados a deudas (`id_deuda`) se ven en todas las listas, pero su cuota **no** se suma dos veces en la dona ni en el consejero; su valor se sincroniza con la deuda y la fila conserva la descripción del usuario sin mostrar el acreedor.
   - La recuperación de contraseña por olvido pertenece exclusivamente al Login; dentro de la app solo existe el cambio autenticado.
   - `misfinanzas_pending_debt_link` permanece en `sessionStorage` durante toda la estancia en deudas y se elimina únicamente al restaurar el formulario de origen.

10. **Paleta Única y Flujos Sin Pantalla en Blanco (SRS v3.4):**
    - Los diez HEX de las donas son distintos y se leen de `core/categorias.py`; la base mínima `#10B981` nunca comparte color con Alimentación `#F97316`.
    - La función maestra de WhatsApp (PNG al portapapeles + chat directo) no se reescribe: el modal «Ver factura» la invoca igual que el ícono rápido y los recibos.
    - WhatsApp se abre siempre con `window.open(url, '_blank', 'noopener,noreferrer')`: nunca se navega en la misma pestaña ni se oculta el ícono del botón.
    - El flujo de deudas es bidireccional: scroll de ida a «Nueva deuda» y de retorno al formulario de origen; solo se marca SI si el backend confirmó la deuda (`debt_created: true`), y el campo Valor se bloquea/desbloquea al instante según la categoría.

11. **Identidad Visual y Módulos Aprobados (SRS v3.7):**
    - El icono nativo de la PWA es el logotipo oficial «Logotipo OLB BYTE futurista en neón azul.png», presente en los PNG de 32/180/192/512 y en la variante maskable.
    - La gráfica del Consejero es la comparativa unificada de cierre (píldora, dos velocímetros y curva SVG de 12 meses con hito «¡Libre de deuda!»); la lógica la calcula Python y el SVG solo la dibuja.
    - En móvil, WhatsApp usa el esquema nativo `whatsapp://send` sin descargar PNG ni dejar pestañas en blanco; en escritorio se mantiene `wa.me` en `_blank`.
    - «Atajos guardados» no genera scroll lateral en móvil y mantiene encabezados y filas en la misma rejilla.
    - El retorno de deudas compara IDs reales (`existing_debt_ids`) antes de marcar SI.

12. **Experiencia de Usuario Uniforme (SRS v3.9.1):**
    - Está prohibido disparar diálogos nativos del navegador (alertas, confirmaciones o prompts). Toda confirmación o aviso usa los modales oscuros propios de MisFinanzas.
    - Las validaciones son preventivas y se explican en lenguaje claro, sin exponer códigos técnicos HTTP.
    - Los campos de fecha mantienen el icono legible en tema oscuro y se abren con un clic en escritorio.
    - La identidad visual oscura, la separación de roles y la reserva de $300.000 con cero duplicidad de cuotas se conservan sin cambios.

13. **Uniformidad Visual de Gráficas e Iconos (SRS v3.9.3):**
    - La gráfica del Consejero usa la misma superficie y borde que las tarjetas de gráficas de OLB_BYTE; en móvil se conservan sus proporciones y en escritorio los velocímetros son compactos (120×68 px) y lado a lado.
    - El ícono del menú de OLB_BYTE es un escaparate comercial, no una herramienta; el ícono nativo PWA neón azul no se modifica.
    - Los mensajes de validación no exponen nombres de campo ni prefijos de Pydantic.

14. **Documentación Viva Completa:**
   - Además de `AGENTS.md` y `MEMORY.md`, son obligatorios esta misma `constitution.md`, `diccionario_datos.md`, `Guia.md` (fichas por archivo + inventario regenerado con `--verificar`), `USER_GUIDE.md` (manual del usuario) y la SRS del repositorio, con la versión activa reflejada en todos ellos.
   - Ningún bloque se considera terminado si `compileall`, `pytest`, `node --check` y `generar_guia.py --verificar` no están en verde.
