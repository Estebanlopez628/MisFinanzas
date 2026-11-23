# Constitución — OLB_BYTE & Finanzas Personales

Principios innegociables. Toda especificación, plan y tarea debe cumplirlos de forma estricta.

1. **Separación de Roles (RBAC Estricto):**
   - El sistema es público para la gestión de finanzas personales (`USER_FINANZAS`) y privado exclusivamente para el administrador (`ADMIN_OLB`), protegiendo el módulo de ventas, cartera y enlaces de pago ("chancucos").

2. **La Especificación Activa Manda:**
   - La especificación vigente es la **SRS v3.9.5** (sección 14 del archivo `especificaci_n_de_requisitos_de_software_srs.md`), que conserva las reglas de v1.1.0 a v3.9.3 salvo contradicción explícita.
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
    - El ícono del menú de OLB_BYTE es el PNG oficial `icono_OLBBYTE.png`, con las mismas dimensiones (20×20 px) que los íconos de los demás módulos; el ícono nativo PWA neón azul no se modifica.
    - En escritorio los dos velocímetros del Consejero se disponen en dos columnas paralelas obligatorias (`repeat(2, minmax(0, 1fr))`), sin alterar la vista móvil ni los colores de fondo.
    - Los mensajes de validación no exponen nombres de campo ni prefijos de Pydantic.

14. **Documentación Viva Completa:**
   - Además de `AGENTS.md` y `MEMORY.md`, son obligatorios esta misma `constitution.md`, `diccionario_datos.md`, `Guia.md` (fichas por archivo + inventario regenerado con `--verificar`), `USER_GUIDE.md` (manual del usuario) y la SRS del repositorio, con la versión activa reflejada en todos ellos.
   - Ningún bloque se considera terminado si `compileall`, `pytest`, `node --check` y `generar_guia.py --verificar` no están en verde.

15. **Separación contable y control de deudas (SRS v4.4):**
    - Las donas de Finanzas y Trabajos Extras son independientes: de extras solo se traslada el saldo neto; la dona de Gastos y Presupuestos usa únicamente gastos y deducciones de ese módulo.
    - El Consejero consume el libre consolidado; la cuota vinculada se cuenta una sola vez y nunca como tajada suelta.
    - «Sueldo-percibido» sustituye a «Saldo para el bolsillo» sin alterar su cálculo; el saldo libre de cada bloque descuenta todos sus gastos fijos, incluidos los vinculados.
    - `GET /api/deudas` expone la vinculación; el borrado usa el modal propio y `DELETE /api/deudas/{id}`; el alta es idempotente y el botón se bloquea de forma síncrona.
    - La posición de desplazamiento se preserva con `history.scrollRestoration = "manual"`; está prohibido devolver al inicio.
    - No se modifican la gráfica del Consejero, el ícono PWA neón azul, WhatsApp nativo, Atajos Guardados, `showPicker()`, los modales propios ni la paleta de diez colores.

16. **Balance global con trazabilidad de origen (SRS v4.5):**
    - La dona de Gastos y Presupuestos es global: su base es el sueldo más los ingresos brutos de Trabajos Extras; las categorías homólogas se consolidan en una tajada y el libre se dibuja una sola vez.
    - Toda categoría compartida debe poder verificarse en la leyenda mediante sub-ítems apilados por origen (`Mis Finanzas` / `Trabajos Extras`), con valores y porcentajes que sumen el total.
    - El Consejero consume el total libre consolidado y respeta el colchón de $300.000; la dona individual de Trabajos Extras es inmutable.
    - La descripción de una deuda es editable desde el modal y desde `PUT/PATCH /api/deudas/{id}`, preservando validaciones, borrado confirmado y bloqueo anti-doble clic.
    - En escritorio (`>= 768px`) los velocímetros miden 156×88 px en dos columnas de hasta 640 px; el móvil conserva 120×68 px.
    - Ningún bloque se publica sin el gate QA con usuario de prueba y la documentación sincronizada.

17. **Cumplimiento laboral colombiano 2026 (SRS v4.8):**
    - La hora ordinaria se calcula sobre 220 horas mensuales, con `HORAS_MENSUALES` como sobreescritura configurada.
    - La matriz oficial tiene siete conceptos con factores 1.25, 1.75, 2.15, 2.65, 0.35, 0.90 y 1.25; se admiten horas decimales y se migran limpiamente los conceptos históricos.
    - El auxilio de transporte se liquidó realmente en el corte que lleva las deducciones de ley, y el saldo neto de cada quincena refleja el valor consignado.
    - La nomenclatura visual es «Sueldo devengado» y «Total devengado», sin guiones.
    - El motor de nómina, la tabla de factores, la migración y las etiquetas se verifican con el usuario de prueba antes de cualquier publicación.

18. **Integridad contable del resumen de periodo (SRS v4.10):**
    - El sueldo devengado de cada corte es neto de ley; está prohibido volver a restar salud y pensión dentro de la tarjeta de pago.
    - La dona global y el Consejero Financiero se alimentan del total consolidado del mes, nunca de la suma de saldos parciales de las tarjetas.
    - El resultado del periodo separa en dos líneas la explicación del monto y el total de gastos del mes, con la etiqueta «TOTAL DEVENGADO» sin guiones.
    - El desglose inferior presenta primero los ingresos y su subtotal y después las deducciones y su subtotal, con un separador visible entre ambos bloques.

19. **Simplicidad de captura y cero intereses ficticios (SRS v4.13):**
    - Las tarjetas de corte muestran solo el sueldo devengado neto real y los gastos fijos; el detalle de deducciones permanece en el resumen del periodo.
    - El Consejero y sus gráficas nunca inventan intereses ni totales inflados: comunican reducción real de capital, plazos exactos y fechas con meses completos en español.
    - Cada deuda se identifica con nombre, saldo y cuota; la cuota liberada se desglosa por deuda.
    - El ajuste de layout del panel de gráficas es exclusivo de escritorio; la vista móvil se conserva.

20. **Estética de los velocímetros sin alterar su dimensión (SRS v4.17):**
    - El dial radial tipo cockpit, sus micro-marcas, el resplandor neón y la aguja con pivote son mejoras visuales; los tamaños vigentes y las cifras del Consejero son inmutables.
    - La variante azul corresponde a «Pago mínimo» y la esmeralda a «Con excedente», con texto centrado y la píldora de meses ganados solo en esta última.
    - Las reglas CSS del componente se declaran fuera de media queries móviles para que el estilo aplique en web y móvil sin cambiar su distribución.

21. **Precisión operativa y claridad visual (SRS v4.18):**
    - Los resúmenes de corte y de Trabajos Extras son compactos; el resultado del periodo conserva su estructura.
    - El Consejero distingue el plazo de la deuda recomendada del cierre global, usa «pago mínimo» y solo nombra deudas incluidas en su plan.
    - Los velocímetros se apilan en móvil sin cambiar el diseño web; la gráfica de proyección es legible y tiene un único estado activo.

22. **Amortización paralela y claridad tabular (SRS v4.19):**
    - Las deudas se amortizan en paralelo; el plazo base es el mayor del portafolio y la cuota liberada por una deuda cerrada se reinvierte al mes siguiente.
    - La proyección visual se limita a seis meses con extremos de alto contraste y una sola línea de detalle.
    - La dona se centra en escritorio, el banner móvil comparte radio con los velocímetros y los textos corridos van justificados.
    - Las tablas financieras móviles alinean cada dato con su cabecera mediante anchos fijos y padding compartido.

23. **Coherencia del Consejero y foco en el plan (SRS v4.20):**
    - Los plazos de cierre se calculan exclusivamente sobre las deudas recomendadas; una deuda larga no incluida en el plan no puede distorsionar el mensaje.
    - La redacción usa pluralización exacta y nombra cada deuda con saldo y cuota, sin términos ambiguos.
    - La proyección a 6 meses es exclusiva de escritorio; el banner móvil va centrado y el de liquidez es legible en ambos tamaños.
