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

24. **Abonos extraordinarios a deudas y centrado de la dona (SRS v4.21):**
    - Todo gasto o deducción con categoría «Créditos y Obligaciones» y toda deuda registrada ofrecen «Abonar» en su modal de edición, en web y móvil, con un modal propio que pide el valor y ofrece «Registrar abono», «Registrar abono + cuota» y «Cancelar».
    - El abono descuenta el saldo y recalcula las cuotas; nunca modifica la cuota pactada salvo que el resto sea menor, en cuyo caso se ajusta a ese resto. Los abonos se guardan en su propia tabla, separados de las cuotas automáticas.
    - «Registrar abono + cuota» marca el gasto o deducción vinculado como pagado del corte; al pagar la deuda, su cuota vinculada deja de contarse en totales, dona y Consejero.
    - Las leyendas, el título, la descripción y la dona del panel de capacidad van centrados en móvil y escritorio, y las cabeceras «Valor a pagar» y «Días de pago» conservan su salto de línea con centrado.

25. **Barras comparativas de impacto (SRS v4.22):**
    - La proyección a 6 meses se sustituye por «¡Tu Excedente Aplasta tus Deudas!», visible en web y móvil, con barras proporcionales, porcentaje de ahorro por deuda y zona demarcada con candado abierto. Las cifras las calcula Python; la vista es Jinja2/CSS/SVG, sin React.
    - El modal de abono separa sus botones del campo de valor; las leyendas de la dona se centran debajo en escritorio sin alterar móvil; «Configurar atajos de pago» no ofrece favoritos y la tabla usa cinco columnas.
    - El logo de OLB_BYTE mide 30 px y Mis Finanzas muestra el logo oficial al entrar al módulo.

26. **Legibilidad de las barras en móvil (SRS v4.24):**
    - La fecha de cierre se muestra en formato `MM/AAAA` y la barra es al menos tan ancha como su texto: ningún rótulo puede recortarse ni salirse del recuadro.
    - El fondo del componente iguala al de los velocímetros; en móvil el porcentaje acompaña a «Pago mínimo», la cuota no lleva `/mes`, el subtítulo replica el recuadro verde del banner y gráfica y velocímetros comparten el mismo ancho.
    - Las reglas móviles se declaran después de las bases para no ser sobrescritas.

27. **Icono de Mis Finanzas y texto sin paréntesis (SRS v4.25):**
    - El encabezado de Mis Finanzas muestra la bolsa de dinero (💰) que identifica al módulo en el inicio.
    - Ningún rótulo de la gráfica comparativa usa paréntesis; en móvil el badge del porcentaje se alinea al extremo derecho de «Pago mínimo».

28. **Grilla simétrica y checks sin parpadeo (SRS v4.26):**
    - Los modales de Editar deuda y Editar deducción usan dos botones lado a lado y un tercero a ancho completo; la acción secundaria se mantiene accesible en la cabecera.
    - El ✔ de un gasto fijo cambia al instante y se guarda en segundo plano; solo se revierte si falla el servidor, sin recargar la página ni mostrar alertas que desplacen el contenido. La lógica de créditos vinculados y metas no se modifica.

29. **Abono en la fila inferior (SRS v4.27):**
    - En los modales de deuda y deducción «Abonar» ocupa la fila inferior a ancho completo y «Cancelar» se elimina, porque la X de la cabecera ya cierra.
    - No se introducen librerías de navegación parcial: donas, Consejero, checks y subnavegación se mantienen intactos.

30. **Pulido integral y paridad (SRS v4.28):**
    - La comparativa de cierre es idéntica para todos los roles; sin deudas se muestra el mismo componente con un mensaje, nunca la gráfica antigua.
    - Los modales respetan las capas (9000 / 9999) y conservan la posición de scroll; la anulación en OLB_BYTE confirma al pulsar.
    - Los abonos a metas se acumulan en el mes, y los textos de la interfaz usan lenguaje claro sin roles técnicos ni nombres de algoritmos.

31. **Modales propios a nivel superior (SRS v4.29):**
    - Los estilos de `.app-modal` no pueden quedar dentro de un media query móvil: los modales de abono, confirmación y aviso deben centrarse en el viewport también en escritorio.
    - Las reglas exclusivas de móvil se agrupan en su propio `@media` y la profundidad de llaves antes de `.app-modal` debe ser cero.

32. **Atajos en dos filas y capa superior de OLB (SRS v4.30):**
    - En escritorio cada atajo muestra descripción, valor con salto de línea y día arriba, y referencia con Copiar y Pagar abajo, sin recortar la descripción.
    - Los modales propios que se abren desde un `<dialog>` nativo se trasladan temporalmente dentro de él para heredar su capa superior y no quedar ocultos.

33. **Formulario de Nueva deuda en escritorio (SRS v4.31):**
    - La tarjeta ocupa el ancho exacto de las tres KPI y sus seis campos forman una grilla 3 × 3 con base alineada y pie separado por una divisoria.
    - Las columnas se alinean con las KPI compensando el padding del panel; móvil y «Deudas registradas» no cambian.
    - Las cajas de texto son compactas (42 px) y conservan 12 px de separación respecto a los bordes del contenedor.

34. **Distribución exacta de atajos (SRS v4.33):**
    - Web y modal móvil comparten la misma estructura de tres filas con «Fecha pago: Día X» subrayada en azul y botones igualados; la vista primaria móvil se mantiene intacta.
    - La etiqueta visible es «Intervalo de pago»; todos los controles de una fila comparten la misma altura.

35. **Omisión temporal y homogeneidad (SRS v4.35):**
    - La X de un gasto fijo normal ofrece omitir el pago 10 días o eliminarlo; las metas no entran en ese flujo y conservan su regla de 15 días.
    - Todos los modales y alertas son opacos, centrados y delante del contenido, con campos contenidos y scroll preservado.

36. **Modal X y backdrop suave (SRS v4.36):**
    - El modal de la X saluda al usuario por su alias, muestra la descripción, ofrece solo dos acciones y se cierra con una X en la cabecera.
    - El fondo de modales y alertas es un velo oscuro suave con desenfoque, conservando la superficie homogénea de la tarjeta.

37. **Modal unificado y reactivación (SRS v4.37):**
    - Gastos fijos normales y metas comparten el modal de la X, pero una meta nunca se elimina desde gastos fijos; se muestra el mensaje exacto de derivación al módulo de metas.
    - Los ítems omitidos ofrecen «Habilitar» para reactivarse de inmediato, y el modal Editar gasto mantiene superficie sólida por encima de todo contenido.
    - Los íconos representativos acompañan al título grande de cada vista de Mis Finanzas, no a los botones de pestaña.

38. **Emojis, scroll exacto y acreedor (SRS v4.38):**
    - Los títulos grandes usan emojis a todo color; las pestañas permanecen sin íconos.
    - Toda acción que recargue la página conserva la posición vertical y horizontal exacta, sin re-anclaje.
    - El modal Editar de ítems inhabilitados se muestra sólido y por encima del contenido, y el acreedor se puede corregir desde Deudas.

39. **Pie del modal Editar gasto (SRS v4.39):**
    - El botón «Cancelar» se sustituye por la X de la cabecera en todos los modales que lo tenían.
    - Los botones restantes quedan centrados: dos juntos o uno solo, según corresponda.

40. **Checks y retorno exacto (SRS v4.40):**
    - «Limpiar checks» está presente desde la primera carga, sin exigir un ✔ previo.
    - Las acciones con `form.submit()` guardan el scroll explícitamente para conservar la posición de la quincena.

41. **Paridad de gastos en Trabajos Extras (SRS v4.41):**
    - Los gastos fijos de un trabajo usan la misma fila que Mis Finanzas: editar, ✔, X unificada, Habilitar y abonos.
    - La limpieza masiva de checks está disponible por contrato y nunca afecta los gastos de Mis Finanzas.

42. **Atajos y Deep Links (SRS v4.42):**
    - Se aceptan enlaces web y esquemas nativos de apps de pago; la apertura web usa pestaña nueva y el Deep Link se ejecuta en la ventana actual.
    - En móvil, «Atajos guardados» se desplaza horizontalmente y «Atajos de pago» muestra tarjetas directas con Copiar y Pagar, sin modal intermedio.
    - La vista de escritorio de atajos y las gráficas aprobadas permanecen intactas.
