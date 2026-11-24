# Especificación de Requisitos de Software (SRS)

## Proyecto: OLB_BYTE & Plataforma de Finanzas Personales

### 1. Introducción y Alcance

#### 1.1 Propósito del Documento

El presente documento establece la Especificación de Requisitos de Software (SRS) para la plataforma híbrida de **Finanzas Personales y Control Comercial OLB_BYTE**. Describe detalladamente las funcionalidades, reglas de negocio, estructura de datos y requerimientos no funcionales de la aplicación.

#### 1.2 Alcance del Sistema

La plataforma es un sistema web/móvil con arquitectura dual:

1. **Módulo Público (Finanzas Personales y Cuadro de Nómina):** Herramienta gratuita para el control de presupuestos quincenales, cálculo automático de nómina colombiana, liquidación de horas extras/recargos, gestión inteligente de incapacidades y referencias de pago. Monetizado mediante anuncios publicitarios no invasivos.

2. **Módulo Privado (OLB_BYTE):** Panel de administración exclusivo para la gestión del emprendimiento de gadgets (ventas, cartera de clientes, control de abonos, garantías, facturación y envío de órdenes por WhatsApp).

### 2. Arquitectura de Usuarios y Control de Acceso (RBAC)

#### 2.1 Definición de Roles

| Rol | Descripción | Permisos y Accesos | 
| ----- | ----- | ----- | 
| **`ADMIN_OLB`** | Administrador principal (Propietario del sistema) | Acceso total a los 4 módulos principales (`Mis Finanzas`, `OLB_BYTE`, `Registro y Detalles de deudas`, `Trabajos Extras`) y visualización del panel privado de "Chancucos". | 
| **`USER_FINANZAS`** | Usuario público registrado | Acceso al entorno de finanzas personales (`Mis Finanzas`). Rutas de `OLB_BYTE` totalmente bloqueadas a nivel de backend y UI. Visualización de anuncios. | 

#### 2.2 Requisitos Funcionales: Autenticación y Perfil

##### RF-01: Autenticación de Usuarios

* **Descripción:** Pantalla única de inicio de sesión (*Login*) que valida credenciales de acceso.

* **Criterios de Aceptación:**

  * Autenticación mediante correo electrónico y contraseña encriptada (Hash).

  * Generación de sesión segura basada en tokens (JWT).

  * Opción de "Recuperar Contraseña" vía correo electrónico.

  * Botón de registro visible únicamente para el rol `USER_FINANZAS` (el auto-registro como `ADMIN_OLB` está restringido).

##### RF-02: Configuración del Perfil y Alias de Usuario

* **Descripción:** Tras el registro o primer ingreso, el sistema solicita al usuario la configuración de su **Alias / Apodo**.

* **Criterios de Aceptación:**

  * El sistema utiliza dicho alias para personalizar dinámicamente los saludos y encabezados de la plataforma (ej. *"¡Hola, bienvenido a tu cuadro de nómina, \[Alias\]!"*).

### 3. Módulo de Navegación Principal (Dashboard)

##### RF-03: Pantalla Principal de Módulos (Tarjetas de Acceso)

* **Descripción:** Tras iniciar sesión, la pantalla de bienvenida presenta 4 tarjetas interactivas de navegación principal:

  1. **Mis Finanzas:** Acceso al liquidador salarial y presupuesto quincenal.

  2. **OLB_BYTE:** Panel comercial privado (deshabilitado/invisible para `USER_FINANZAS`).

  3. **Registro y Detalles de deudas:** Módulo complementario de control de pasivos.

  4. **Trabajos Extras:** Módulo para el registro de ingresos independientes o esporádicos.

### 4. Requisitos Funcionales — Módulo "Mis Finanzas"

#### 4.1 Onboarding y Parámetros Salariales Base

##### RF-04: Asistente de Configuración Salarial

* **Descripción:** Captura los parámetros económicos iniciales del usuario para alimentar el motor financiero.

* **Entradas del Usuario:**

  * **Sueldo Básico Neto (\$):** Valor mensual base devengado.

  * **Modalidad de Pago:** Selector entre *Mensual* o *Quincenal*.

  * **Configuración de Quincenas (si es Quincenal):**

    * El usuario puede ingresar el porcentaje asignado a la primera quincena (ej. $40\%$, calculando automáticamente el $60\%$ restante para la segunda).

    * **Asistente de Cálculo Porcentual:** Si el usuario desconoce el porcentaje, puede ingresar el valor en pesos (\$$) de la quincena libre de deducciones, y el sistema calculará automáticamente el porcentaje correspondiente.

  * **Asignación de Deducciones:** Selector para indicar en qué quincena se aplicarán los descuentos de ley y obligaciones fijas.

##### RF-05: Deducciones Automáticas de Ley (Sólo Lectura)

* **Descripción:** Cálculo automático e informativo de los aportes parafiscales obligatorios en Colombia.

* **Reglas de Negocio:**

  * **Salud:** $4\%$ calculated automáticamente sobre el `Sueldo Básico`.

  * **Pensión:** $4\%$ calculado automáticamente sobre el `Sueldo Básico`.

  * **Comportamiento Visual:** Los campos se presentan en modo de solo lectura (no editables).

  * **Integración:** Los valores resultantes de Salud y Pensión se suman automáticamente al total de deducciones que restan el valor neto de la quincena configurada.

#### 4.2 Liquidador de Horas Extras, Recargos y Auxilio de Transporte

##### RF-06: Matriz de Registro de Tiempo Suplementario (`TOTAL HORAS TRABAJADAS`)

* **Descripción:** Tabla interactiva para el ingreso de horas laboradas y cálculo automático de recargos salariales.

* **Base de Cálculo:** La hora ordinaria se determina dividiendo el `Sueldo Básico` entre la jornada legal de $210$ **horas mensuales** ($42$ horas semanales).

* **Parámetros de Liquidación Admitidos:**

  * Admitirá valores enteros y decimales (ej. $10.4$ horas).

  * **Tabla de Factores Multiplicadores:**

    * *Hora Extra Diurna Normal:* $\text{Hora Ordinaria} \times 1.25$

    * *Hora Extra Nocturna:* $\text{Hora Ordinaria} \times 1.75$

    * *Hora Extra Diurna Dominical o Festiva:* $\text{Hora Ordinaria} \times 2.00$

    * *Hora Extra Nocturna Dominical o Festiva:* $\text{Hora Ordinaria} \times 2.50$

    * *Recargo Nocturno Ordinario:* $\text{Hora Ordinaria} \times 0.35$

    * *Recargo Dominical o Festivo Diurno/Nocturno:* $\text{Hora Ordinaria} \times 1.90$

##### RF-07: Evaluación Dinámica del Auxilio de Transporte (Tope $2\text{ SMMLV}$)

* **Descripción:** Validación en tiempo real del derecho al subsidio de transporte legal.

* **Regla de Negocio:**

  * El sistema evalúa continuamente la sumatoria:
    

    $$
    \text{Total Devengado} = \text{Sueldo Básico} + \text{Total Recargos}
    $$

  * **Condición:**

    * Si $\text{Total Devengado} > 2\text{ SMMLV}$ ($3.501.810\text{ COP}$ o valor parametrizado del año en curso), el sistema establece el Auxilio de Transporte en $\$0$ y despliega el mensaje descriptivo: *"Supera los 2 salarios mínimos: No aplica Auxilio de Transporte"*.

    * Si $\text{Total Devengado} \le 2\text{ SMMLV}$, el sistema asigna el valor legal del auxilio de transporte —actualmente **$249.095 COP**, parametrizable mediante `AUXILIO_TRANSPORTE`— y muestra la diferencia restante para alcanzar el tope.

#### 4.3 Presupuesto Quincenal y Reactividad en Tiempo Real

##### RF-08: Gestión Dinámica de Responsabilidades y Gastos Fijos

* **Descripción:** Módulo interactivo que permite al usuario listar, crear, editar o eliminar obligaciones financieras asignadas a cada quincena (ej. servicios públicos, cuotas de créditos bancarios, arriendo, gasolina, cadenas, etc.).

##### RF-09: Recálculo en Tiempo Real (Live Balance Update)

* **Descripción:** Toda modificación efectuada en los bloques superiores (sueldo básico, horas extras, incapacidades o nuevos gastos fijos) actualiza instantáneamente los indicadores inferiores.

* **Fórmula General del Balance Disponible:**
  

  $$
  \text{Dinero Disponible en Bolsillo} = \text{Ingreso Bruto Quincenal} - \text{Deducciones de Ley} - \text{Deducciones Opcionales} - \text{Responsabilidades Quincenales}
  $$

#### 4.4 Módulo de Incapacidades Médicas con Cruce de Meses (Rollover)

##### RF-10: Gestión de Incapacidades y Arrastre de Saldos

* **Descripción:** Módulo ubicado debajo de la sección de deducciones fijas para el registro de novedades de salud.

* **Entradas:** Selección de **Fecha de Inicio** y **Fecha de Finalización** de la incapacidad.

* **Reglas de Liquidación (Origen Común):**

  * **Días 1 y 2:** Asumidos al $100\%$ por el empleador (sin deducción salarial).

  * **Días 3 en adelante:** Reconocidos por la EPS al $66.67\%$ del salario diario base (lo que genera un **menor valor o descuento del** $33.33\%$ en el ingreso del trabajador).

* **Lógica de Cruce de Meses (Corte y Arrastre):**

  1. El sistema analiza el rango de fechas contra el mes fiscal en curso.

  2. Los días pertenecientes al mes actual se descuentan de forma directa en el cuadro de nómina activo.

  3. Los días o valores que excedan el límite del mes actual se almacenan de forma automática como **Saldo Arrastrado de Incapacidad (Rollover)**.

  4. Al abrir el cuadro de nómina del mes siguiente, el valor correspondiente a los días remanentes aparece pre-cargado automáticamente en el bloque de deducciones, garantizando la continuidad del cálculo del flujo de caja.

#### 4.5 Panel de Referencias y Enlaces Rápidos de Pago ("Chancucos")

##### RF-11: Tarjeta de Referencias y Accesos de Pago

* **Descripción:** Panel de consulta rápida con los códigos de contrato y referencias de pago (créditos de vivienda, remodelación, gas, energía, agua, internet, etc.).

* **Funcionalidad:**

  * **Botón de Copiado Rápido:** Copia el número de contrato/referencia al portapapeles del dispositivo con un solo clic.

  * **Botón "Pagar":** Enlace interactivo que abre la pasarela de pago o sucursal virtual oficial en una nueva pestaña del navegador.

* **Privacidad y Escalabilidad:**

  * Visible de forma predeterminada únicamente para el rol `ADMIN_OLB`.

  * La arquitectura permite habilitar en futuras versiones un formulario para que los usuarios estándar (`USER_FINANZAS`) registren sus propios códigos y URLs de pago personalizadas.

### 5. Requerimientos No Funcionales

#### 5.1 Seguridad y Privacidad

* Encriptación de datos sensibles y contraseñas mediante algoritmos Hash seguros (ej. bcrypt).

* Separación lógica estricta en base de datos para impedir que un usuario del rol `USER_FINANZAS` pueda acceder a las API o endpoints del módulo privado `OLB_BYTE`.

#### 5.2 Rendimiento y Reactividad

* La interfaz de usuario debe procesar la liquidación salarial, recargos y deducciones en un tiempo de respuesta inferior a $100\text{ ms}$ ante cualquier cambio de entrada (Live Update).

#### 5.3 Monetización y Disposición de Anuncios (Ad Layout)

* Integración de espacios publicitarios estratégicos en el módulo público (`USER_FINANZAS`) respetando los estándares de experiencia de usuario (banners no intrusivos que no tapen los botones de pago ni los totales de quincena).

### 6. Control de Configuración y Documentación Viva del Agente AI

##### RF-12: Mantenimiento Obligatorio de AGENTS.md y MEMORY.md

* **Descripción:** El ciclo de vida del desarrollo software de este proyecto debe estar respaldado de forma permanente e imperativa por los archivos `AGENTS.md` y `MEMORY.md` ubicados en la raíz del repositorio.

* **Criterios de Aceptación y Obligatoriedad:**

  * **Manejo Permanente:** Todo agente AI o desarrollador debe consultar `AGENTS.md` para conocer los comandos de ejecución, el estado verificado del backend/frontend, las rutas API activas y las variables de entorno.

  * **Memoria del Dominio:** Todo cambio arquitectónico, regla laboral colombiana parametrizada (horas, recargos, topes de auxilio de transporte, lógica de incapacidades con saldo arrastrado) debe documentarse en `MEMORY.md`.

  * **Actualización Sincronizada:** Cada vez que se agregue o modifique un módulo (como los futuros módulos de `OLB_BYTE`, `Registro y Detalles de deudas` o `Trabajos Extras`), es obligatorio actualizar tanto `AGENTS.md` como `MEMORY.md` antes de dar por finalizada la tarea.

---

## 7. SRS v2.0 — Correcciones Quirúrgicas, Gráfica de Cartera/Efectivo, Ayuda y Actualización Documental

Esta sección recoge la versión 2.0 de los requisitos de **MisFinanzas**, ejecutada en cuatro fases con validación entre cada una. Tiene precedencia sobre las secciones anteriores donde haya conflicto, y conserva todas las reglas financieras colombianas ya aprobadas.

### 7.1 Reglas de no regresión (vigentes)

1. No se altera el diseño, los cálculos, los estados ni **una sola palabra del mensaje** de las facturas de OLB_BYTE. El único cambio permitido fue el destinatario del enlace de WhatsApp.
2. No se modifica la pregunta condicional SI/NO ni la validación de la categoría «Créditos y Obligaciones».
3. OLB_BYTE y la facturación son exclusivos del administrador. Las guías, preguntas frecuentes, selectores de reporte y textos de privacidad del usuario estándar no los mencionan.
4. Los gastos fijos vinculados a una deuda (`id_deuda`) se ven en todas las listas, pero su cuota **no** se suma dos veces en la dona ni en el consejero. La fila muestra la descripción escrita por el usuario y la cuota vigente; no muestra el acreedor para no ensanchar el cuadro.
5. El valor de un gasto vinculado se autocompleta con la cuota de la deuda y queda bloqueado mientras exista el vínculo.
6. «Ayuda y comentarios» e «Invitar amigos» van en la fila inferior de Inicio del usuario estándar; el administrador ve una tarjeta «Comentarios y Reportes» con contador circular.

### 7.2 Fase A — Backend y PostgreSQL

- Tabla `feedback_usuarios` (diccionario §14) con `id`, `user_id`, snapshot de nombre y correo, tipo de reporte, módulo público, descripción, dispositivo, estado y `created_at`.
- API: `POST /feedback`, `GET /feedback/pendientes`, `GET /feedback`, `POST /feedback/{id}/estado`. El conteo, listado y cambio de estado exigen `ADMIN_OLB`; el dispositivo se detecta en servidor desde `User-Agent`.
- Los GET de gastos fijos incluyen los registros con `id_deuda` mediante `JOIN` a `deudas`, trayendo `cuota_mensual` y acreedor sin duplicar montos.

### 7.3 Fase B — Correcciones funcionales del frontend

- WhatsApp de factura: saneamiento del celular, prefijo `57` para 10 dígitos, conservación de los 12 que ya empiezan por 57, apertura de `https://wa.me/<numero>?text=<mensaje original>` y aviso claro si no hay número válido.
- Retorno desde «Ve a registrar la deuda» con `sessionStorage` bajo la clave `misfinanzas_pending_debt_link`, banner con la etiqueta del módulo de origen y restauración de todos los campos con SI y la deuda recién creada preseleccionada.
- Gastos vinculados visibles en Mis Finanzas, Gastos y Trabajos Extras; valor sincronizado y bloqueado en edición; desvinculación al elegir NO o cambiar de categoría.

### 7.4 Fase C — Gráfica, ayuda y tarjeta administrativa

- Panel «BALANCE DE CARTERA Y EFECTIVO»: bloque A de cuentas, bloque B de efectivo y bloque C de utilidad proyectada, con barras divergentes desde el eje $0, colores definidos (azul `#3B82F6`, ámbar `#F59E0B`, verde `#10B981`, rojo `#EF4444`) y texto explicativo dinámico.
- Vista `/ayuda` con centro de ayuda (GUÍA A de instalación PWA y GUÍA B de seis preguntas frecuentes), envío de comentarios y tarjeta legal con condiciones, privacidad y licencias. El modal legal se comparte con `/login`.
- Fila inferior de Inicio para `USER_FINANZAS`; «Invitar amigos» abre `https://wa.me/?text=` sin destinatario con el mensaje literal.
- Tarjeta «Comentarios y Reportes» para `ADMIN_OLB` junto a «Trabajos Extras», con badge de pendientes y actualización en vivo al cambiar estados.

### 7.5 Fase D — Documentación

- `AGENTS.md`, `MEMORY.md` (ADR-65 a ADR-67 y bitácoras), `diccionario_datos.md` (§14 y relaciones), `Guia.md` (fichas e inventario), `USER_GUIDE.md` (manual del usuario) y esta SRS quedan sincronizados con el estado verificado.

---

## 8. SRS v3.0 — Auditoría Post-Despliegue

Versión 3.0 del alcance de **MisFinanzas**. Se ejecutaron únicamente las diez correcciones de la auditoría, sin alterar lógica contable, cálculos de dona, fórmulas de liquidez ni mensajes aprobados.

### 8.1 Retorno al registrar deudas

- El módulo de origen viaja en el `POST /deudas` y se conserva en el redirect, de modo que el enlace sigue visible tras guardar.
- `misfinanzas_pending_debt_link` permanece en `sessionStorage` durante toda la estancia en deudas y se elimina únicamente cuando el formulario de origen restaura sus datos.
- El enlace es de texto (mismo estilo que «Ve a registrar la deuda») y se renderiza bajo el formulario «Nueva deuda».

### 8.2 WhatsApp directo

- Prohibida la Web Share API en el botón «Compartir por WhatsApp» de Ver factura, el ícono rápido junto a «Ver factura» y el botón de compartir recibos de abonos.
- Los tres comparten `enviarPorWhatsapp`: saneamiento del celular, prefijo `57` para 10 dígitos y apertura de `https://wa.me/<numero>?text=<encodeURIComponent(mensaje)>` con fallback a `window.location.href`.
- Si no hay número válido se muestra una alerta clara antes de abrir nada. El mensaje aprobado no cambia.

### 8.3 Ayuda e invitación

- Acceso inferior en Inicio sin pastilla ni íconos pesados: enlaces de texto con SVGs lineales de 14 px y separador de punto; «Invitar amigos» solo en móvil.
- Centro de ayuda y políticas con `text-align: justify`; «Volver al inicio» usa el botón azul primario.

### 8.4 Contraste y modales

- Flechas de `<select>` en `#9CA3AF` mediante SVG en `background-image`; indicador de `<input type="date">` con `filter: invert(0.75)` y `color-scheme: dark`.
- Centrado estricto de todos los modales (`.modal-centrado` y `<dialog>` nativos) con fondo `fixed inset-0 z-50`.

### 8.5 Enlaces

- Paleta uniforme `#60A5FA` con hover `#93C5FD`; se elimina el morado en Mi Perfil y en cualquier enlace de acción.

### 8.6 Recuperación de contraseña

- El flujo de olvido vive exclusivamente en el Login; en Mi Perfil solo queda el cambio autenticado.
- Los botones «Enviar enlace» y «Volver a iniciar sesión» llevan separación vertical clara.
- Backend: envío con `BackgroundTasks`, timeout SMTP de 10 s, alias `SMTP_PASSWORD`/`FROM_EMAIL`, registro explícito del resultado y aviso al usuario si falta configuración en producción.

### 8.7 Comentarios y Reportes

- Vista móvil en tarjetas conectada al mismo arreglo de datos, con usuario, fecha, módulo, descripción y selector de estado.
- `PATCH /api/feedback/{id}` persiste el estado y `fecha_resolucion` en PostgreSQL; el badge circular cuenta solo `Pendiente`.
- `GET /api/feedback/mios` alimenta la sección «Mis reportes enviados» en `/ayuda`, sin mensajería externa.

### 8.8 Abonos, botones y gasto bloqueado

- El modal de abono se titula «Registrar Abono / Pago Total» y no contiene separadores de guiones.
- «Agregar gasto fijo» comparte estilo con «Guardar incapacidad».
- El valor del gasto vinculado se muestra gris oscuro con candado y cursor de no escritura cuando `id_deuda != null`.

### 8.9 Títulos de cartera

- «ESTADO DE CARTERA» (centrado), «CUENTAS POR COBRAR Y PAGAR» y «FLUJO DE CAJA DISPONIBLE».

### 8.10 Documentación

- `AGENTS.md` y `MEMORY.md` (ADR-68) registran la persistencia de `misfinanzas_pending_debt_link`, la prohibición de la Web Share API, la exclusividad de la recuperación en Login, el estilo gris de los inputs bloqueados y la vista móvil de comentarios.
- `diccionario_datos.md` documenta `fecha_resolucion` y «Mis reportes enviados»; `Guia.md`, `USER_GUIDE.md` y esta SRS quedan sincronizados.

---

## 9. SRS v3.1 — Ajustes Finos de UX, Logo, SMTP y Botones Azules

Versión 3.1 del alcance de **MisFinanzas**. Cuatro ajustes quirúrgicos sobre lo ya validado en v3.0, sin tocar lógica contable, dona, liquidez ni mensajes aprobados.

### 9.1 Scroll y enfoque al volver de deudas

- IDs estables: `seccion-gastos-fijos-finanzas`, `seccion-deducciones-fijas` y `seccion-gastos-fijos-trabajos-extras`.
- Tras restaurar `misfinanzas_pending_debt_link`, marcar SI y cargar las deudas: `requestAnimationFrame` + 150 ms, `scrollIntoView({behavior:'smooth', block:'center'})`, resaltado azul de 1,5 s y foco en el selector «Deudas registradas».

### 9.2 Logo del modal y adjunto en WhatsApp

- El `<img>` del logo lleva `loading="eager"`, `decoding="sync"`, dimensiones fijas y fallback; no se oculta ni se muta en el DOM visible.
- La captura se genera sobre un clon fuera de pantalla y se restauran `src`, `display`, `visibility` y `opacity` del logo visible.
- La imagen PNG se copia al portapapeles y se abre el chat directo con `wa.me/<numero>`; un toast discreto indica: «Chat abierto y comprobante copiado: si deseas adjuntar la imagen, solo pulsa Pegar en el chat de WhatsApp».

### 9.3 Entrega efectiva del correo

- Se priorizan APIs transaccionales HTTPS: `RESEND_API_KEY`, `BREVO_API_KEY` y `SENDGRID_API_KEY`, en ese orden, sin dependencias nuevas.
- Sin API, SMTP SSL en puerto 465 con timeout de 15 s (Gmail con contraseña de aplicación) o STARTTLS con timeout de 10 s.
- Se registran el código exacto de respuesta (HTTP o SMTP) y los errores detallados; si no hay proveedor en producción se avisa al usuario desde el formulario.

### 9.4 Uniformidad de botones azules

- «Agregar gasto fijo», «Agregar deducción fija», «Guardar incapacidad» y todos los botones «Volver/Regresar/Volver al inicio» usan la clase azul institucional `boton--primario`.

### 9.5 Documentación

- `AGENTS.md`, `MEMORY.md` (ADR-69), `Guia.md`, `USER_GUIDE.md`, `constitution.md` y esta SRS quedan sincronizados con la versión activa v3.1.

---

## 10. SRS v3.4 — Blindaje Anti-Regresión + Cierre Documental Integral

Versión 3.4 y **línea base vigente**. Cuatro ajustes quirúrgicos sin alterar la lógica contable, las fórmulas de liquidez ni los mensajes aprobados.

### 10.1 Reglas críticas de no regresión

1. La función maestra de WhatsApp (PNG al portapapeles con el logo y chat directo) no se reescribe; el botón «Compartir por WhatsApp» del modal «Ver factura» la invoca exactamente igual que el ícono rápido y los recibos.
2. WhatsApp se abre con `window.open(url, '_blank', 'noopener,noreferrer')`: prohibido navegar en la misma pestaña o dejar pantalla en blanco; el ícono permanece siempre visible.
3. Ningún ítem de las donas comparte color: la paleta de diez HEX se lee de `core/categorias.py`.
4. El flujo de deudas es bidireccional y honesto: scroll de ida y vuelta, y SI solo si el backend confirmó la creación.

### 10.2 Paleta única de donas

Diez HEX distintos centralizados: base `#10B981`, Alimentación `#F97316`, Vivienda `#3B82F6`, Créditos `#EF4444`, Transporte `#EAB308`, Salud `#06B6D4`, Educación `#8B5CF6`, Ocio `#EC4899`, Otros `#64748B` y Dinero Libre `#84CC16`. Arcos y leyenda leen el mismo diccionario.

### 10.3 Atajos guardados en móvil

Desde 767 px, columnas `fit-content(160px)` + `max-content`, gap de 11 px, descripción `w-fit` con truncate a 160 px para textos extensos.

### 10.4 WhatsApp y registro de pagos

- Modal «Ver factura» conectado a la función maestra; sin Web Share API, sin pantalla en blanco y sin ocultar el ícono.
- Botones de abono renombrados a «Registrar Pago»; se conserva el título «Registrar Abono / Pago Total» y no hay líneas de guiones.

### 10.5 Deudas bidireccionales

- Flag `misfinanzas_scroll_to_new_debt` → scroll/resaltado/foco en `#seccion-nueva-deuda`.
- `misfinanzas_pending_debt_link` incorpora `debt_created` y `created_debt_id`; solo se marcan SI y la cuota cuando el POST se completó. Sin registro se mantiene NO con guardado bloqueado.
- El campo Valor se bloquea y desbloquea de inmediato al cambiar la categoría.

### 10.6 Cierre documental

Diccionario §15, constitución, `Guia.md`, `USER_GUIDE.md`, `AGENTS.md`, `MEMORY.md` (ADR-70) y esta SRS quedan sincronizados con la versión activa v3.4. El icono nativo de la PWA se genera desde `assets/Icono OLB BYTE Finanzas App Nativa.png` en los tamaños 180/192/512 y 512 maskable; `sw.js` quedó en `olb-finanzas-v96`.

---

## 11. SRS v3.7 — Final Consolidada con Código Completo

Versión 3.7 y **línea base vigente**. Cinco ajustes finales más el cierre documental, sin modificar los módulos ya aprobados en v3.4.

### 11.1 No regresión

Se conservan intactos: el copiado del PNG al portapapeles en los tres puntos de WhatsApp, el scroll bidireccional de deudas, el bloqueo reactivo del valor por categoría, la paleta de diez colores, el botón «Registrar Pago», la tarjeta «Estado de Cartera» y los módulos de Ayuda y soporte.

### 11.2 Atajos en móvil

El contenedor usa `w-full overflow-x-hidden`; encabezado y filas comparten la misma rejilla de tres columnas. Descripción a la izquierda con truncate, Valor y Días a la derecha sin espacio sobrante.

### 11.3 WhatsApp nativo

Sin descarga automática de PNG al compartir. En iOS/Android se abre `whatsapp://send?phone=…&text=…` con `window.location.href`, directo a la app y sin pestaña intermedia en blanco. En escritorio se mantiene `wa.me` con `_blank`, `noopener,noreferrer`. La copia con `ClipboardItem` no se modifica.

### 11.4 Validación real de deuda

Los formularios publican `data-deudas-actuales`; el payload guarda `existing_debt_ids`; al regresar se comparan con los IDs reales del servidor. Solo se marca SI si hay un ID nuevo o si el backend confirmó `debt_created` con un ID presente. Sin deuda creada: NO, aviso visible y guardado bloqueado.

### 11.5 Icono nativo oficial

El icono pasa a ser `assets/Logotipo OLB BYTE futurista en neón azul.png`, desplegado en `favicon-32.png`, `icono-180.png`, `icono-192.png`, `icono-512.png` y `icono-512-maskable.png`. `base.html` declara los `link` de 32, 192 y apple-touch-icon 180; el manifiesto usa `purpose: "any maskable"`; `sw.js` en `olb-finanzas-v98`.

### 11.6 Comparativa de cierre de deuda (Consejero)

Se sustituyen las 24 barras por un componente SVG único: píldora verde con ahorro y meses ahorrados, dos velocímetros semicirculares («Pago mínimo» azul frente a «Con excedente» verde) con fecha y total de cierre, y gráfica de área de 12 meses con línea azul punteada (Base), curva verde degradada (Optimizado), hito «¡Libre de deuda!» en el mes exacto en que el saldo llega a cero y tooltip táctil por mes. `saldoOptimizado <= saldoBase` en todos los meses. El cálculo vive en `Consejo.cierre` (Python); el SVG y `consejero.js` solo presentan. Proyección educativa sin intereses.

### 11.7 Cierre documental

Guía, Constitución, Diccionario, `MEMORY.md` (ADR-71), `AGENTS.md` y esta SRS quedan sincronizados con la versión activa v3.7.

---

## 12. SRS v3.9.1 — Blindaje UX + Cierre Documental Completo

Versión 3.9.1 y **línea base vigente**. Tres ajustes UX y el cierre documental, sin modificar los módulos aprobados en v3.7.

### 12.1 No regresión

Se conservan intactos la gráfica unificada del Consejero, el icono neón azul, WhatsApp nativo con PNG en portapapeles, la tabla móvil de Atajos, el scroll bidireccional y bloqueo reactivo en Deudas, la paleta de diez colores y Ayuda/Comentarios.

### 12.2 Validación preventiva de deudas

En el formulario se calcula en vivo `totalCuotas = cuota × cantidadCuotas`. Si los tres campos son mayores a cero y `totalCuotas < totalAdeudado`, se bloquea «Guardar deuda» con estilo apagado y se muestra justo debajo una alerta roja con este texto exacto: «El valor total calculado entre el valor de la cuota y la cantidad de cuotas no alcanza a cubrir la totalidad de la deuda. Por favor, verifica nuevamente la información y digita correctamente los datos.». En cuanto la condición se corrige, la alerta desaparece y el botón se habilita. El backend devuelve el mismo mensaje en `detail` sin prefijos HTTP.

### 12.3 Selectores de fecha

CSS global con `color-scheme: dark`, `cursor: pointer` e indicador `filter: invert(0.82) brightness(1.15)`, `opacity: 0.9`, `padding: 4px` y `border-radius: 4px`. Listener global que llama a `showPicker()` al hacer clic en cualquier zona de un `<input type="date">` en escritorio, sin perder la edición por teclado.

### 12.4 Modales propios, cero diálogos nativos

Se auditan y eliminan el 100% de `alert`, `confirm` y `prompt` del código. `base.html` aporta `#modal-confirmacion` y `#modal-aviso` con backdrop `fixed inset-0 z-9999`, tarjeta `#0F172A`, botón secundario gris «Cancelar» y primario azul «Confirmar» (rojo solo para eliminación definitiva). `app.js` gestiona `data-confirmar` en formularios y controles con `requestSubmit`, y los avisos usan el toast oscuro. Ningún flujo puede mostrar un cuadro blanco del navegador.

### 12.5 Cierre documental

Guías, Diccionario de Datos, Constitución, `MEMORY.md` (ADR-72), `AGENTS.md` y esta SRS quedan sincronizados con la versión activa v3.9.1.

---

## 13. SRS v3.9.3 — Uniformidad Visual de Gráficas + Ícono Comercial OLB_BYTE

Versión 3.9.3 y **línea base vigente**. Tres ajustes finales de identidad visual y mensajes, sin tocar los módulos aprobados en v3.9.1.

### 13.1 No regresión

No se modifican las proporciones móviles de los velocímetros ni de la curva del Consejero, los selectores de fecha con `showPicker()`, los modales propios, el ícono PWA neón azul, WhatsApp nativo, Atajos Guardados, el flujo de Deudas ni la paleta de diez colores.

### 13.2 Uniformidad de la gráfica del Consejero

La tarjeta «Comparativa de cierre de deuda» adopta exactamente la superficie de las tarjetas de gráficas de OLB_BYTE: fondo `rgba(30, 41, 59, 0.75)`, borde `var(--borde-suave)` y radio `var(--radio-lg)`, sin `#0F172A`. En escritorio (≥768 px) los dos velocímetros van en una fila de dos columnas de hasta 520 px, con SVG de 120×68 px; la curva de 12 meses se limita a 170 px y los botones de meses no tienen caja ni borde. En móvil se conservan tamaño y disposición previos, cambiando solo fondo y borde.

### 13.3 Mensaje de validación limpio

El mensaje único es: «El número de cuotas por el valor de cuota no alcanza a cubrir el valor total de la deuda. Revisa los datos y digítalos nuevamente.». Aparece bajo «Guardar deuda» con fondo rojo, bloqueando el botón mientras `cuota × cuotas < total`. `validar_formulario` elimina `Value error,` y el prefijo `tasa_implicita:`; `limpiarMensajeError()` aplica la misma limpieza en el frontend. Ningún usuario ve nombres de variables ni errores crudos.

### 13.4 Ícono comercial de OLB_BYTE

La entrada del menú exclusiva del administrador cambia la llave inglesa por un SVG de escaparate comercial (trazo 1.8, `currentColor`, 20 px), inyectado desde `icono_svg` con `| safe`. El ícono nativo de la PWA no se modifica.

### 13.5 Cierre documental

Guías, Diccionario de Datos, Constitución, `MEMORY.md` (ADR-73), `AGENTS.md` y esta SRS quedan sincronizados con la versión activa v3.9.3.

---

## 14. SRS v3.9.5 — Ajustes Quirúrgicos

Versión 3.9.5 y **línea base vigente**. Dos cambios visuales únicos, sin tocar ningún módulo aprobado en v3.9.3.

### 14.1 No regresión

No se alteran el fondo de la tarjeta del Consejero, la vista móvil, el ícono nativo PWA `Logotipo OLB BYTE futurista en neón azul.png`, la validación de cuotas, los selectores de fecha, los modales propios, WhatsApp, Atajos Guardados ni las donas.

### 14.2 Ícono oficial del módulo OLB_BYTE

La entrada del menú exclusiva del administrador renderiza `static/img/icono_OLBBYTE.png` (copiado desde `assets/`) mediante `<img src=... alt="OLB_BYTE" width="20" height="20">`, con `object-fit: contain`, `display: inline-block`, `flex-shrink: 0` y `vertical-align: middle`. Las dimensiones son idénticas a las de los íconos de los módulos vecinos, sin deformación en escritorio ni móvil. Sustituye al SVG de escaparate de v3.9.3.

### 14.3 Velocímetros en dos columnas en escritorio

El contenedor padre de los dos velocímetros fuerza en línea `display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; width: 100%; max-width: 540px; margin: 0 auto 16px auto`. Cada tarjeta lleva `min-width: 0; display: flex; flex-direction: column; align-items: center` y su SVG `width="120" height="68"` con `flex-shrink: 0`. Queda prohibido el apilamiento vertical en escritorio; no se modifica la vista móvil ni los colores de fondo.

### 14.4 Cierre documental

Guías, Diccionario de Datos, Constitución, `MEMORY.md` (ADR-74), `AGENTS.md` y esta SRS quedan sincronizados con la versión activa v3.9.5.

---

## 15. SRS v4.4 — Separación contable, deudas y preservación de scroll

Versión 4.4 y **línea base vigente**. Separa contablemente las donas de Finanzas y Trabajos Extras, consolida el libre para el Consejero y ajusta la gestión de deudas, los íconos y el desplazamiento.

### 15.1 Separación contable y libre consolidado

- La dona de **Gastos y Presupuestos** se alimenta únicamente de gastos y deducciones fijas registradas en ese módulo. No se suman ingresos ni gastos de Trabajos Extras, ni cuotas sueltas de la tabla de deudas.
- La dona de **Trabajos Extras** conserva sus ingresos, gastos fijos y créditos vinculados (`id_deuda`).
- Fórmulas obligatorias, calculadas en Python:
  - `Libre_Trabajos_Extras = Total Ingresos Trabajos Extras − Total Gastos Fijos Trabajos Extras (incluyendo créditos vinculados)`.
  - `Libre_Gastos_Presupuestos = Sueldo_Percibido − Suma_Gastos_Fijos_Gastos_y_Presupuestos`.
  - `Total_Libre_Consolidado = Libre_Gastos_Presupuestos + Libre_Trabajos_Extras`. Es la entrada del Consejero.
  - Base de la dona de Gastos y Presupuestos = `Sueldo_Percibido + Libre_Trabajos_Extras`.
- La cuota vinculada se cuenta una sola vez: dentro de la categoría del gasto o deducción registrada, nunca como tajada suelta adicional.

### 15.2 Etiqueta y saldo libre de los bloques

- La etiqueta «Saldo para el bolsillo» pasa a ser **«Sueldo-percibido»**, sin cambiar su cálculo.
- En Resumen/Liquidación, para Quincena 1, Quincena 2 y pago mensual:
  `Saldo libre restante = Ingreso proyectado del bloque − Deducciones de ley − Deducciones fijas del salario − Total Gastos Fijos del bloque (incluyendo créditos vinculados)`.
- Esta regla no altera las donas.

### 15.3 Vinculación de deudas

- `GET /api/deudas` devuelve por deuda `esta_vinculada: boolean` y `modulos_vinculados: string[]`, con valores `[]`, `['Finanzas']`, `['Trabajos Extras']` o ambos.
- La tabla incorpora la columna **«Vinculación»** con insignia verde cuando está vinculada y ámbar cuando no.
- Se retira la tarjeta «X cuota(s) — Pagos que faltan en las deudas activas» y la cuadrícula pasa a tres tarjetas.

### 15.4 Eliminación desde el modal

- El modal de edición de deudas incorpora un botón rojo **«Eliminar»**.
- Antes de `DELETE /api/deudas/{id}` se usa el modal de confirmación propio (`pedirConfirmacion`), sin diálogos nativos.
- El borrado es exclusivo de deudas propias; un identificador ajeno o inexistente responde 404.

### 15.5 Anti-duplicados

- El botón «Guardar deuda» usa un bloqueo síncrono (`envioEnCurso`, equivalente en JavaScript plano a `isSubmittingRef.current`), muestra «Guardando...» y se libera en `finally`/temporizador.
- Existe un único `onSubmit` para el alta.
- El backend es idempotente por `user_id` y mismos valores en los últimos 10 segundos: un reenvío devuelve la deuda ya creada en vez de duplicarla.

### 15.6 Íconos y scroll

- `icono_OLBBYTE.png` se renderiza a **24 px** en la navegación y **28 px** en el encabezado interno de OLB_BYTE. El ícono PWA neón azul no cambia.
- Se captura `savedScrollY`; está prohibido forzar el desplazamiento al inicio. La posición se restaura con `window.scrollTo({ top: savedScrollY, behavior: 'instant' })`.
- `history.scrollRestoration = "manual"` evita que el navegador sobrescriba la posición restaurada.
- Las anclas `bloque-quincena-1`, `bloque-quincena-2` y `bloque-pago-mensual` (además de `data-quincena`) se anclan con `scrollIntoView({ behavior: 'instant', block: 'nearest' })`.

### 15.7 Usuario QA y verificación

- Cuentas de QA locales: `prueba_qa@misfinanzas.local` / `QA_MisFinanzas_2026!` y `prueba_qa_admin@misfinanzas.local` / `QA_Admin_2026!`, creadas por `scripts/crear_usuario_qa.py`.
- El recorrido `scripts/qa_v4_4.py` verifica 38 comprobaciones en Chromium a 360/390/768/1280 px.
- No regresión: gráfica del Consejero, ícono PWA, WhatsApp nativo, Atajos Guardados, `showPicker()`, modales propios, paleta de diez colores, Ayuda/Comentarios, factura OLB_BYTE y vinculación SI/NO permanecen intactos.

### 15.8 Cierre documental

Guías, Diccionario de Datos, Constitución, `MEMORY.md` (ADR-75), `AGENTS.md` y esta SRS quedan sincronizados con la versión activa v4.4.

---

## 16. SRS v4.5 — Dona global con trazabilidad, descripción editable y velocímetros web

Versión 4.5 y **línea base vigente**. Tres ajustes ejecutables sobre v4.4. Está prohibido tocar cualquier funcionalidad no listada aquí.

### 16.1 Regla suprema de no regresión

Se conservan sin cambio la dona individual de Trabajos Extras, el «Saldo libre restante» de Quincena 1 / 2 / pago mensual, la etiqueta «Sueldo-percibido», la columna «Vinculación», el botón «Eliminar», el blindaje anti-duplicados de tres capas, `icono_OLBBYTE.png`, el ícono PWA neón azul, WhatsApp nativo, `showPicker()`, los modales propios, la paleta de diez colores y la preservación de scroll.

### 16.2 Dona global agrupada con desglose de origen (web y móvil)

- Base global: `Base_Global = Sueldo_Percibido + Total_Ingresos_Trabajos_Extras` (ingresos brutos). Las categorías de gasto de ambos módulos y el dinero libre cierran exactamente el 100,0 %.
- Las categorías homólogas se suman en **una sola tajada** con un único color del catálogo. El libre de Mis Finanzas y el de Trabajos Extras se suman en una sola tajada «Total libre».
- Cada categoría compartida muestra en la leyenda, apilada y con sangría, `↳ <categoría> - Mis Finanzas` y `↳ <categoría> - Trabajos Extras`, con valor y porcentaje global. «Total libre» muestra `↳ Libre - Mis Finanzas` y `↳ Libre - Trabajos Extras`. Las categorías de un solo origen no repiten sub-ítems.
- El Consejero sigue consumiendo el total libre consolidado y respetando el colchón de $300.000. La dona de Trabajos Extras permanece intacta.

### 16.3 Descripción editable en deudas (web y móvil)

- El modal de edición incorpora un input visible, pre-cargado y `required` para la descripción/nombre.
- Permanecen activas la validación en vivo `cuota × cuotas ≥ total`, el botón rojo «Eliminar» con el modal propio y el bloqueo síncrono de «Actualizar».
- `PUT /api/deudas/{id}` y `PATCH /api/deudas/{id}` aceptan y persisten `descripcion` en PostgreSQL y devuelven el objeto actualizado. Los campos omitidos conservan su valor.

### 16.4 Velocímetros ampliados solo en escritorio

- En `@media (min-width: 768px)`: contenedor de dos columnas con `gap: 20px`, `max-width: 640px` y SVG de `156px × 88px`.
- En móvil (`< 768px`) se mantienen `max-width: 540px` y SVG de `120px × 68px`.

### 16.5 Gate QA y cierre documental

- Usuarios QA: `prueba_qa@misfinanzas.local` / `QA_MisFinanzas_2026!` y `prueba_qa_admin@misfinanzas.local` / `QA_Admin_2026!`.
- `scripts/qa_v4_5.py`: **34/34 comprobaciones** en Chromium a 360/390/768/1280 px. Solo después del gate se ejecutaron `git add`, `commit` y `push`.
- Guías, Diccionario de Datos, Constitución, `MEMORY.md` (ADR-76), `AGENTS.md` y esta SRS quedan sincronizados con la versión activa v4.5.

---

## 17. SRS v4.8 — Liquidación oficial 2026 y quincenas reales

Versión 4.8 y **línea base vigente**. Dos ajustes ejecutables sobre la línea base anterior.

### 17.1 Regla suprema de no regresión

No se tocan la dona global con desglose apilado, la dona individual de Trabajos Extras, el Consejero, los velocímetros web 156×88, Deudas ni su edición de descripción, Atajos Guardados, selectores de fecha, modales propios, WhatsApp, OLB_BYTE ni Ayuda. Se conserva la admisión de horas enteras y decimales (por ejemplo, 10,4).

### 17.2 Tabla oficial de siete conceptos (2026)

`Hora Ordinaria = Salario Mensual Base / 220` (divisor 2026, sobreescribible con `HORAS_MENSUALES`).

| # | Concepto | Fórmula |
| --- | --- | --- |
| 1 | Hora Extra Diurna Normal | Hora Ordinaria × 1.25 |
| 2 | Hora Extra Nocturna | Hora Ordinaria × 1.75 |
| 3 | Hora Extra Diurna Dominical o Festiva | Hora Ordinaria × 2.15 |
| 4 | Hora Extra Nocturna Dominical o Festiva | Hora Ordinaria × 2.65 |
| 5 | Recargo Nocturno Ordinario | Hora Ordinaria × 0.35 |
| 6 | Recargo Ordinario Dominical o Festivo | Hora Ordinaria × 0.90 |
| 7 | Recargo Nocturno Dominical o Festivo | Hora Ordinaria × 1.25 |

Los registros históricos bajo `Recargo Dominical o Festivo Diurno/Nocturno` se mapean a la clave canónica `RECARGO_DOMINICAL_FESTIVO` con factor 0.90, sin reescribir el `valor_total` ya liquidado. La migración es idempotente y válida en SQLite y PostgreSQL.

### 17.3 Liquidación real de cortes y etiquetas

- Quincena 1: `Sueldo devengado = Salario base × %Q1`; solo se restan sus gastos fijos y créditos vinculados.
- Quincena 2 (o pago mensual): `Sueldo devengado = Salario base × %Q2 + Auxilio de Transporte vigente + Horas extras y recargos`; de ahí se descuentan las deducciones de ley del corte.
- `Saldo libre restante = Sueldo devengado − Deducciones de ley − Deducciones fijas − Gastos fijos del corte`.
- Caso base verificado: sueldo $3.484.000 (40 %/60 %), auxilio $249.095 → Q1 $1.393.600; Q2 $2.339.495 − $278.720 = **$2.060.775** netos; total consolidado **$3.454.375**.
- Etiquetas: «Ingreso proyectado» → **«Sueldo devengado»**; «Sueldo-percibido» → **«Total devengado»**, ambas sin guiones.

### 17.4 Gate QA y cierre documental

- Usuarios QA: `prueba_qa@misfinanzas.local` / `QA_MisFinanzas_2026!` y `prueba_qa_admin@misfinanzas.local` / `QA_Admin_2026!`.
- `scripts/qa_v4_8.py`: **19/19 comprobaciones** en Chromium, incluidos los siete conceptos, 10,4 h del nuevo recargo, el caso base de quincenas y la no regresión. Solo tras el gate se ejecutaron `git add`, `commit` y `push`.
- Guías, Diccionario de Datos, Constitución, `MEMORY.md` (ADR-77), `AGENTS.md` y esta SRS quedan sincronizados con la versión activa v4.8.

---

## 18. SRS v4.10 — Integridad contable del resumen y claridad del periodo

Versión 4.10 y **línea base vigente**. Dos ajustes visuales y contables sobre v4.8.

### 18.1 No regresión

No se tocan los siete factores 2026, la dona global con desglose apilado, la dona de Trabajos Extras, el Consejero, los velocímetros 156×88, Deudas, Atajos Guardados, selectores de fecha, modales propios, WhatsApp, OLB_BYTE ni Ayuda. La dona y el Consejero siguen leyendo el `Total devengado` consolidado del periodo, nunca los saldos parciales de las tarjetas.

### 18.2 Fin del doble descuento de ley en los cortes

El «Sueldo devengado» que muestra cada tarjeta de Quincena 1, Quincena 2 o Pago Único Mensual ya está neto de deducciones de ley. Se elimina la fila «Deducciones de ley» y su nota dentro de esas tarjetas. El saldo de cada corte queda:

`Saldo libre restante = Sueldo devengado (neto de ley) − Gastos fijos del corte (incluidos créditos vinculados) − Deducciones fijas del salario del corte`.

### 18.3 Resultado del periodo y desglose ordenado

- Etiqueta superior: **TOTAL DEVENGADO**, sin guion.
- Bajo el valor grande, dos líneas separadas por salto real: `Ingresos totales menos deducciones de ley e incapacidad.` y `Total de Gastos del mes: $X` (gastos fijos + deducciones fijas del mes, actualizable en vivo).
- El desglose inferior sigue exactamente este orden: Valor hora ordinaria; Horas extras y recargos; Total devengado (sueldo + recargos); Auxilio de transporte; Total ingresos; separador; Salud (4,00 %); Pensión (4,00 %); Descuento por incapacidad; Total deducciones. Los cinco primeros son positivos/verdes y los cuatro últimos negativos/rojos.

### 18.4 Gate QA y cierre documental

- Usuarios QA: `prueba_qa@misfinanzas.local` / `QA_MisFinanzas_2026!` y `prueba_qa_admin@misfinanzas.local` / `QA_Admin_2026!`.
- `scripts/qa_v4_10.py`: **14/14 comprobaciones** en Chromium, incluidos quincenal y mensual, la dona intacta y 360/390/768/1280 px. Solo tras el gate se ejecutaron `git add`, `commit` y `push`.
- Guías, Diccionario de Datos, Constitución, `MEMORY.md` (ADR-78), `AGENTS.md` y esta SRS quedan sincronizados con la versión activa v4.10.

---

## 19. SRS v4.13 — Tarjetas limpias y Consejero sin intereses ficticios

Versión 4.13 (unificación de v4.11 y v4.12) y **línea base vigente**.

### 19.1 No regresión

No se tocan los siete factores 2026, «Resultado del periodo» ni su tabla de nueve filas, la dona global con leyenda apilada, la dona de Trabajos Extras, Deudas, Atajos Guardados, selectores de fecha, modales propios, WhatsApp, OLB_BYTE ni Ayuda. Los textos y cifras del Consejero aplican en web y móvil; solo el layout del panel de gráficas es exclusivo de escritorio (`>= 768px`).

### 19.2 Tarjetas de corte simplificadas

Quincena 1, Quincena 2 y Pago Mensual muestran únicamente: encabezado con porcentaje, «SALDO LIBRE RESTANTE», «Sueldo devengado» con el **neto real del corte** (ley y deducciones fijas ya descontadas, auxilio y recargos sumados) y «Gastos fijos» del corte con créditos vinculados. Se eliminan las filas «Deducciones de ley» y «Deducciones fijas del salario».

`Saldo libre restante = Sueldo devengado neto − Gastos fijos del corte`. El detalle completo de deducciones sigue intacto en «Resultado del periodo» y en la dona global.

### 19.3 Consejero y gráficas con cifras reales

- Está prohibido mencionar ahorros de intereses ficticios o totales inflados que contradigan el saldo registrado. La reducción a 12 meses es la diferencia real entre las dos curvas.
- El titular comunica cuántos meses antes se termina, las fechas completas y la reducción de capital, junto con el excedente mensual aplicado.
- Los velocímetros muestran nombre completo del mes en español, duración exacta, saldo actual y si el escenario es «Sin abono extra» o «Abonando +$X/mes».
- Se elimina «en más de 12 meses»: los plazos `meses_minimo` y `meses_con_excedente` son exactos y aparecen en el mensaje, la cuarta viñeta y la tarjeta izquierda.
- Cada deuda se nombra siempre con su saldo pendiente y su cuota mensual; la cuota liberada se desglosa sumando cada deuda que cierra.
- Bajo la curva se muestra el detalle del mes seleccionado: saldo base, saldo optimizado y reducción extra acumulada.

### 19.4 Layout exclusivo de escritorio

En `>= 768px`: la curva de 12 meses ocupa el 100 % del ancho con etiquetas de saldo inicial y saldo al mes 12; los velocímetros van en sub-tarjetas oscuras equilibradas; el selector de meses son píldoras oscuras con el mes activo en verde esmeralda. En móvil (`< 768px`) la distribución permanece intacta.

### 19.5 Gate QA y cierre documental

- Usuarios QA: `prueba_qa@misfinanzas.local` / `QA_MisFinanzas_2026!` y `prueba_qa_admin@misfinanzas.local` / `QA_Admin_2026!`.
- `scripts/qa_v4_13.py`: **21/21 comprobaciones** en Chromium, incluidas tarjetas limpias, Consejero sin cifras ficticias, meses completos y comparación de layout escritorio/móvil. Solo tras el gate se ejecutaron `git add`, `commit` y `push`.
- Guías, Diccionario de Datos, Constitución, `MEMORY.md` (ADR-79), `AGENTS.md` y esta SRS quedan sincronizados con la versión activa v4.13.

---

## 20. SRS v4.17 — Velocímetros tipo cockpit (solo estilo visual)

Versión 4.17 y **línea base vigente**. Único cambio: la personalización visual de los dos velocímetros del Consejero.

### 20.1 Conservación estricta

Se mantienen las dimensiones vigentes —120×68 px en móvil y 156×88 px en escritorio, dentro del contenedor de dos columnas— y no se modifica ningún otro módulo de la línea base v4.13. Las cifras y textos siguen siendo los calculados por `Consejo.cierre`.

### 20.2 Diseño aprobado

- Dial radial tipo cockpit con anillo exterior de precisión, 41 micro-marcas de graduación, pista base oscura, arco activo con resplandor y aguja con pivote iluminado.
- Variante azul para «Pago mínimo» (`mfArcBlue` / `mfGlowBlue`) y esmeralda para «Con excedente» (`mfArcGreen` / `mfGlowGreen`).
- Jerarquía de texto centrada debajo del dial: título, fecha completa en español, duración «En N meses» y línea inferior con saldo real y condición (`Sin abono extra` / `Abonando +$X/mes`). La variante verde añade la píldora oscura «-N meses antes» cuando hay meses ganados.
- Las reglas CSS del componente se declaran fuera de cualquier media query para que apliquen en web y móvil; solo cambia el estilo, nunca el tamaño.

### 20.3 Gate QA y cierre documental

- Usuarios QA: `prueba_qa@misfinanzas.local` / `QA_MisFinanzas_2026!` y `prueba_qa_admin@misfinanzas.local` / `QA_Admin_2026!`.
- `scripts/qa_v4_17.py`: **14/14 comprobaciones** en Chromium, incluidos tamaños computados 156×88 y 120×68, 41 marcas, resplandor azul/esmeralda y texto centrado. Solo tras el gate se ejecutaron `git add`, `commit` y `push`.
- Guías, Diccionario de Datos, Constitución, `MEMORY.md` (ADR-80), `AGENTS.md` y esta SRS quedan sincronizados con la versión activa v4.17.

---

## 21. SRS v4.18 — Espaciado, precisión del Consejero y gráfica legible

Versión 4.18 y **línea base vigente**. Cuatro ajustes sobre v4.17.

### 21.1 No regresión

No se tocan los velocímetros web ni sus tamaños, los siete factores 2026, «Resultado del periodo» y su tabla de nueve filas, las donas, Deudas, Atajos Guardados, selectores de fecha, modales propios, WhatsApp, OLB_BYTE ni Ayuda.

### 21.2 Espaciado compacto

Las filas de Quincena 1, Quincena 2, Pago Mensual y Trabajos Extras usan 6 px arriba y abajo (`py-1.5`) y cero margen Vertical (`my-0`). La distancia entre la última fila y la divisoria inferior es de 8 px. «Resultado del periodo» conserva su espaciado original.

### 21.3 Consejero: plazos y deudas

- El plazo de la deuda recomendada es el de **esa deuda** frente a su pago mínimo; no se mezcla con el cierre global de todas las deudas.
- Todo el módulo usa el término **«pago mínimo»**. Se eliminan «pagando solo lo mínimo» y «por más tiempo».
- Las cuotas adelantadas se expresan en meses y cuotas antes que con pago mínimo, calculadas de la simulación real.
- La cuota liberada y su desglose incluyen **solo** las deudas propuestas en el plan; nunca aparece una deuda no listada. Se aclara que el cierre global cubre todas las deudas activas.
- El velocímetro verde muestra el **saldo proyectado** de su escenario, distinto del saldo inicial cuando hay abono extra.

### 21.4 Velocímetros y gráfica

En móvil (`< 768px`) los velocímetros se apilan en una columna (primero pago mínimo), sin cambios en su diseño ni tamaño en escritorio. La gráfica de 12 meses usa `min-height: 220px` en móvil, etiquetas `Inicial` y `Mes 12` en `#e2e8f0` a 14 px, curva verde sólida `#10b981` frente a curva azul discontinua `#38bdf8`, selector de meses en una sola línea con un único mes activo resaltado y una sola línea de resumen del mes seleccionado.

### 21.5 Gate QA y cierre documental

- Usuarios QA: `prueba_qa@misfinanzas.local` / `QA_MisFinanzas_2026!` y `prueba_qa_admin@misfinanzas.local` / `QA_Admin_2026!`.
- `scripts/qa_v4_18.py`: **21/21 comprobaciones** en Chromium, con estilos computados de espaciado, apilado móvil, tamaños web intactos y redacción del Consejero. Solo tras el gate se ejecutaron `git add`, `commit` y `push`.
- Guías, Diccionario de Datos, Constitución, `MEMORY.md` (ADR-81), `AGENTS.md` y esta SRS quedan sincronizados con la versión activa v4.18.

---

## 22. SRS v4.19 — Delta post-v4.18

Versión 4.19 y **línea base vigente**. Cinco ajustes nuevos; no se rehace nada de v4.17 ni v4.18.

### 22.1 No regresión

Intactos: tarjetas compactadas, terminología «pago mínimo», exclusión de deudas no propuestas, velocímetros apilados en móvil y cockpit web, siete factores 2026, «Resultado del periodo», donas, Deudas, Atajos Guardados (sin favoritos nuevos), selectores de fecha, modales propios, WhatsApp, OLB_BYTE y Ayuda.

### 22.2 Amortización en paralelo y redacción

Las deudas activas se amortizan simultáneamente: el plazo con pago mínimo es `MAX(plazo_i)`, nunca la suma (36 + 8 + 10 → 36 meses). En el escenario con excedente, la cuota de cada deuda que se cierra se suma al excedente desde el mes siguiente (cascada). El texto de liberación termina: «…de cuota mensual para tus próximas metas a pagar (Deuda A $X; Deuda B $Y).»

### 22.3 Proyección de saldo a 6 meses

La gráfica de 12 meses se sustituye por «Proyección de saldo (6 meses)»: primeros seis puntos de la simulación paralela, badges de alto contraste «Inicial: [Mes Año] $[Monto]» y «Mes 6: [Mes Año] $[Monto]», curva base discontinua `#38BDF8` (7 7) y optimizada continua `#10B981` (3,5 px), área diferencial con «+ Ahorro acumulado», seis píldoras (grid de 6 en escritorio, fila deslizable en móvil), una sola línea de detalle justificada y leyenda centrada.

### 22.4 Banner móvil, dona y tabla de atajos

En móvil, el banner verde sobre los velocímetros usa `border-radius: 14px` y texto justificado. En escritorio, la dona y sus leyendas se centran dentro de su tarjeta. «Atajos guardados» se renderiza como tabla real `table-fixed` con anchos 38 % / 34 % / 28 % y `padding: 10px 8px` compartido entre `th` y `td`. Todo el texto corrido va justificado, salvo celdas numéricas y etiquetas centradas.

### 22.5 Gate QA y cierre documental

- Usuarios QA: `prueba_qa@misfinanzas.local` / `QA_MisFinanzas_2026!` y `prueba_qa_admin@misfinanzas.local` / `QA_Admin_2026!`.
- `scripts/qa_v4_19.py`: **19/19 comprobaciones** en Chromium (web y 375 px), incluidos plazo paralelo 36 meses, gráfica de 6 meses y ancho real del 38 % en la tabla de atajos. Solo tras el gate se ejecutaron `git add`, `commit` y `push`.
- Guías, Diccionario de Datos, Constitución, `MEMORY.md` (ADR-82), `AGENTS.md` y esta SRS quedan sincronizados con la versión activa v4.19.

---

## 23. SRS v4.20 — Ajustes quirúrgicos post-v4.19

Versión 4.20 y **línea base vigente**. Cuatro ajustes puntuales; no se rehace v4.17, v4.18 ni v4.19.

### 23.1 No regresión

Intactos: alineación de columnas de atajos, gráfica a 6 meses en escritorio, compactación de tarjetas, velocímetros, radio del banner, dona centrada, justificación del resto de párrafos, siete factores 2026, «Resultado del periodo», Deudas, selectores de fecha, modales propios, WhatsApp, OLB_BYTE y Ayuda.

### 23.2 Cambios

1. **Cabeceras de atajos:** «VALOR A / PAGAR» y «DÍAS DE / PAGO» con `<br />`, sin tocar anchos ni alineación izquierda.
2. **Proyección a 6 meses:** visible en escritorio (`>= 768px`), oculta por completo en móvil (`< 768px`).
3. **Consejero:** pluralización sin `(s)` — «1 cuota» / «N cuotas»; «realizando el pago mínimo»; viñetas con «la deuda que tienes con» y la estructura exacta «Al cerrar las deudas que te acabo de recomendar (…) podrás liberar $X de cuota mensual para tus próximas metas a pagar.»; cierre «Realizando el pago mínimo, cerrarías todas tus deudas recomendadas en …; con los abonos las cerrarías en …». El plazo se calcula **exclusivamente sobre el subconjunto recomendado**, ignorando deudas largas no incluidas en el plan; banner de liquidez con tipografía 14 px en móvil y 16 px en escritorio.
4. **Banner de comparativa en móvil:** texto centrado en vez de justificado, conservando el radio de 14 px.

### 23.3 Gate QA y cierre documental

- Usuarios QA: `prueba_qa@misfinanzas.local` / `QA_MisFinanzas_2026!` y `prueba_qa_admin@misfinanzas.local` / `QA_Admin_2026!`.
- `scripts/qa_v4_20.py`: **17/17 comprobaciones** en Chromium (1280 px y 375 px), incluidos los dos `<br />`, la proyección oculta en móvil, la redacción exacta y la ausencia del plazo de la hipoteca no recomendada. Solo tras el gate se ejecutaron `git add`, `commit` y `push`.
- Guías, Diccionario de Datos, Constitución, `MEMORY.md` (ADR-83), `AGENTS.md` y esta SRS quedan sincronizados con la versión activa v4.20.

---

## 24. SRS v4.21 — Abonos extraordinarios y centrado de la dona

Versión 4.21 y **línea base vigente**. No se rehace v4.20 ni ningún módulo aprobado anteriormente.

### 24.1 No regresión

Intactos: el cierre del Consejero sobre deudas recomendadas, la redacción exacta de v4.20, la proyección a 6 meses, los velocímetros cockpit, la factura OLB_BYTE, el flujo SI/NO de vinculación y la anti-duplicación de cuotas vinculadas.

### 24.2 Cambios

1. **Puntos de entrada:** botón «Abonar» en el modal de edición de gastos fijos de Mis Finanzas y Trabajos Extras, de deducciones fijas con categoría «Créditos y Obligaciones», y de deudas registradas. No aparece en Atajos de Pago.
2. **Modal propio:** «Digita el valor que deseas abonar a tu deuda», campo COP y tres acciones: «Registrar abono», «Registrar abono + cuota» y «Cancelar». Sin diálogos nativos, con bloqueo síncrono y cierre al tocar el fondo.
3. **Contabilidad:** la tabla `abonos_deuda` guarda cada abono separado de `pagos_deuda`. El servicio `registrar_abono()` valida propiedad y `0 < valor <= saldo`, descuenta el saldo, recalcula `cuotas_pendientes = ceil(saldo / cuota)`, ajusta la cuota si el resto es menor y marca la deuda como `PAGADA` al llegar a cero. Con «abono + cuota» se registra además el `PagoDeuda` del corte, se ancla en la fecha de aplicación para no recobrar cuotas vencidas y se marca como pagado el gasto o deducción vinculado. Una deuda pagada deja de contar su cuota en totales, dona y Consejero.
4. **HTTP:** `POST /api/deudas/{id_deuda}/abono` con `valor` y `aplica_cuota` opcional, respuesta JSON con el saldo y el plan actualizados y mensajes limpios en `detail`.
5. **Alineación visual:** en «Atajos guardados» las cabeceras «VALOR A / PAGAR» y «DÍAS DE / PAGO» conservan el `<br />` y sus celdas quedan centradas, sin cambiar anchos ni padding. El panel de capacidad centra título, descripción, dona y leyendas en móvil y escritorio, en Gastos y Presupuestos y en Trabajos Extras.

### 24.3 Gate QA y cierre documental

- Usuarios QA: `prueba_qa@misfinanzas.local` / `QA_MisFinanzas_2026!` y `prueba_qa_admin@misfinanzas.local` / `QA_Admin_2026!`.
- `scripts/qa_v4_21.py`: **34/34 comprobaciones** en Chromium (1280 px y 375 px), con los cuatro puntos de entrada, el modal y sus tres botones, el descuento real de saldo y cuotas, el centrado de donas y cabeceras, sin desbordamiento horizontal ni errores de consola. Los datos sembrados se eliminan al terminar. Solo tras el gate se ejecutaron `git add`, `commit` y `push`.
- Guías, Diccionario de Datos, Constitución, `MEMORY.md` (ADR-84), `AGENTS.md` y esta SRS quedan sincronizados con la versión activa v4.21.

---

## 25. SRS v4.22 — Barras de impacto, modal, dona y logos

Versión 4.22 y **línea base vigente**. No se rehace v4.21 (abonos) ni ningún módulo aprobado anteriormente. El JSX de la Sección 4 del delta es **ilustrativo**: se implementa en Jinja2 + CSS puro + SVG, sin React ni Tailwind.

### 25.1 No regresión

Intactos: abonos a deudas y su modal, cierre del Consejero sobre deudas recomendadas, redacción exacta de v4.20, velocímetros, cabeceras de atajos en dos líneas, dona móvil, Resultado del periodo, siete factores 2026, OLB_BYTE, WhatsApp y Ayuda.

### 25.2 Cambios

1. **Comparativa de impacto:** se elimina «Proyección de saldo (6 meses)» y se sustituye por «¡Tu Excedente Aplasta tus Deudas!», visible en web y móvil. Encabezado con porcentaje global, tarjetas por deuda recomendada con badge `-N%`, barra azul de pago mínimo, barra verde con excedente, zona punteada con candado abierto y conector de recorte. Ahorro = `MAX(0, base − excedente)`; porcentaje = `round((base − excedente)/base × 100)`; pluralización sin `(s)`.
2. **Modal de abono:** 22 px de margen superior en el contenedor de botones, separándolos del campo de valor en web y móvil.
3. **Leyendas de la dona:** en escritorio (`>= 768px`) dona y leyendas se apilan en columna centrada; móvil queda intacto.
4. **Atajos:** se retira toda la opción de favorito de «Configurar atajos de pago» (alta, edición, estrella y columna). La tabla pasa a cinco columnas y se reindexan los anchos 38/34/28 y el centrado de «Valor a pagar» y «Días de pago».
5. **Logos:** icono OLB_BYTE a 26 px en el dashboard y 30 px en el encabezado del módulo; Mis Finanzas incorpora el logo oficial `icono-192.png` a 30 px.

### 25.3 Gate QA y cierre documental

- Usuarios QA: `prueba_qa@misfinanzas.local` / `QA_MisFinanzas_2026!` y `prueba_qa_admin@misfinanzas.local` / `QA_Admin_2026!`.
- `scripts/qa_v4_22.py`: **33/33 comprobaciones** en Chromium (1280 px y 375 px), con título y subtítulo, tres tarjetas, badges, barras, zonas punteadas, espaciado 24/20 px, modal separado, leyendas en columna solo en web, sin favoritos, logos y sin desbordamiento ni errores de consola. Los datos sembrados se eliminan al terminar. Solo tras el gate se ejecutaron `git add`, `commit` y `push`.
- Guías, Diccionario de Datos, Constitución, `MEMORY.md` (ADR-85), `AGENTS.md` y esta SRS quedan sincronizados con la versión activa v4.22.

---

## 26. SRS v4.24 — Ajustes móviles de las barras

Versión 4.24 y **línea base vigente**. No se rehace v4.22 ni ningún módulo aprobado anteriormente.

### 26.1 No regresión

Intactos: contenido y cálculo del Consejero, velocímetros, banner verde, abonos, donas, atajos, modales, OLB_BYTE y WhatsApp.

### 26.2 Cambios

1. **Fecha compacta:** `fecha_cierre_base_corta` en `MM/AAAA` para la barra azul, en vez del nombre completo del mes.
2. **Sin recorte:** la barra usa `min-width: max-content` y `overflow: visible`; ningún texto se corta ni se sale del recuadro.
3. **Fondo:** el componente y sus sub-tarjetas usan el mismo fondo de los velocímetros (`rgba(15, 23, 42, 0.55)` / `0.45`).
4. **Móvil:** el badge `-N%` se muestra junto a «Pago mínimo»; la cuota no incluye `/mes`; el panel usa 14 px de padding; gráfica y velocímetros comparten exactamente el mismo ancho; el subtítulo replica el recuadro verde del banner (fondo, borde, color, 0.8 rem, centrado y radio 14 px). Las reglas móviles se declaran al final del CSS para no ser sobrescritas.

### 26.3 Gate QA y cierre documental

- Usuarios QA: `prueba_qa@misfinanzas.local` / `QA_MisFinanzas_2026!` y `prueba_qa_admin@misfinanzas.local` / `QA_Admin_2026!`.
- `scripts/qa_v4_23.py`: **13/13 comprobaciones** y `scripts/qa_v4_24.py`: **14/14 comprobaciones** en Chromium (1280 px y 375 px). Validación adicional de desbordes, recortes y solapes en 360/375/390 px sobre las tres tarjetas, sin hallazgos.
- Guías, Diccionario de Datos, Constitución, `MEMORY.md` (ADR-86), `AGENTS.md` y esta SRS quedan sincronizados con la versión activa v4.24.

---

## 27. SRS v4.25 — Icono correcto y texto sin paréntesis

Versión 4.25 y **línea base vigente**. No se rehace v4.24 ni ningún módulo aprobado anteriormente.

### 27.1 No regresión

Intactos: cálculo y contenido del Consejero, velocímetros, banner verde, abonos, donas, atajos, modales, OLB_BYTE y WhatsApp.

### 27.2 Cambios

1. El encabezado de Mis Finanzas muestra la bolsa de dinero (💰) del inicio en vez del PNG de la PWA.
2. Ningún rótulo visible de la gráfica comparativa usa paréntesis: porcentaje global, descripción de la deuda, fecha de cierre y tiempo con cuotas.
3. En móvil el badge `-N%` se alinea al extremo derecho de la fila de «Pago mínimo» mediante `justify-content: space-between`.

### 27.3 Gate QA y cierre documental

- Usuarios QA: `prueba_qa@misfinanzas.local` / `QA_MisFinanzas_2026!` y `prueba_qa_admin@misfinanzas.local` / `QA_Admin_2026!`.
- Gates: `scripts/qa_v4_22.py` **33/33**, `scripts/qa_v4_23.py` **13/13** y `scripts/qa_v4_24.py` **16/16** en Chromium (1280 px y 375 px). Suite completa: **880 pruebas** en verde.
- Guías, Diccionario de Datos, Constitución, `MEMORY.md` (ADR-87), `AGENTS.md` y esta SRS quedan sincronizados con la versión activa v4.25.

---

## 28. SRS v4.26 — Grilla de modales y checks optimistas

Versión 4.26 y **línea base vigente**. El documento recibido se autodenomina v4.19, pero la línea base pusheada es v4.25: se registra como v4.26 para no reescribir historial. No se rehace ningún módulo aprobado.

### 28.1 No regresión

Intactos: modal de Editar Gasto Fijo y Registrar Abono, tarjetas de corte, 7 factores 2026, Resultado del periodo, Consejero, velocímetros, donas, Atajos Guardados, selectores de fecha, WhatsApp, OLB_BYTE y Ayuda.

### 28.2 Cambios

1. **Grilla de botones:** en «Editar deuda» y «Editar deducción fija» el contenedor de acciones usa `display: grid; grid-template-columns: 1fr 1fr; gap: 12px`. Fila 1: `Actualizar` + `Abonar` (deuda) o `Eliminar` (deducción); fila 2: `Cancelar` con `grid-column: 1 / -1`. La acción secundaria restante va en la cabecera. Igual en web y móvil.
2. **Checks optimistas:** al pulsar el ✔ de un gasto fijo, el estado visual cambia en 0 ms (clase pagada y nombre tachado). El guardado va en un `fetch` silencioso a `POST /api/gastos/{id}/pagado` o `/no-pagado`, que reutiliza `pagos_metas` sin alterar la lógica de créditos vinculados ni de abonos de metas. Si falla, se revierte y se muestra un aviso discreto. Solo se bloquea el botón pulsado. Sin recarga global ni alertas que muevan el layout.

### 28.3 Gate QA y cierre documental

- Usuarios QA: `prueba_qa@misfinanzas.local` / `QA_MisFinanzas_2026!` y `prueba_qa_admin@misfinanzas.local` / `QA_Admin_2026!`.
- `scripts/qa_v4_26.py`: **25/25 comprobaciones** en Chromium (1280 px y 375 px), con la grilla medida en ambos modales, check a 0,7 ms (web) y 0,5 ms (móvil), sin recarga, estado invertido y persistente tras recargar.
- Guías, Diccionario de Datos, Constitución, `MEMORY.md` (ADR-88), `AGENTS.md` y esta SRS quedan sincronizados con la versión activa v4.26.

---

## 29. SRS v4.27 — Abono en la fila inferior

Versión 4.27 y **línea base vigente**. No se rehace v4.26 ni ningún módulo aprobado.

### 29.1 No regresión

Intactos: donas, Consejero, velocímetros, checks optimistas, subnavegación, gráfica comparativa, Atajos, OLB_BYTE y WhatsApp. No se introduce HTMX ni librería de navegación parcial.

### 29.2 Cambios

1. En «Editar deuda» y «Editar deducción fija» se elimina el botón «Cancelar»: la X de la cabecera cumple esa función.
2. «Abonar» se mueve a la fila inferior con `grid-column: 1 / -1` (ancho completo). La fila superior conserva «Actualizar» y «Eliminar». Igual en web y móvil.

### 29.3 Gate QA y cierre documental

- Usuarios QA: `prueba_qa@misfinanzas.local` / `QA_MisFinanzas_2026!` y `prueba_qa_admin@misfinanzas.local` / `QA_Admin_2026!`.
- `scripts/qa_v4_26.py`: **25/25 comprobaciones** en Chromium (1280 px y 375 px), con la grilla y los checks sin cambios. Suite completa: **884 pruebas** en verde.
- Guías, Diccionario de Datos, Constitución, `MEMORY.md` (ADR-89), `AGENTS.md` y esta SRS quedan sincronizados con la versión activa v4.27.

---

## 30. SRS v4.28 — Ocho bloques de pulido

Versión 4.28 y **línea base vigente**. El documento se autodenomina v4.19, pero la línea base pusheada es v4.27; se registra como v4.28 para no reescribir historial. No se introduce HTMX: la navegación entre pestañas permanece intacta.

### 30.1 No regresión

Intactos: botones de modales de deuda/deducción, checks optimistas, velocímetros, Consejero, 7 factores 2026, donas y WhatsApp.

### 30.2 Cambios

1. Modales, alertas y confirmaciones centrados en el viewport, con capas 9000/9999 y preservación de `window.scrollY`.
2. Anulación/eliminación en OLB_BYTE confirma al pulsar, sin esperar a salir y volver.
3. Abonos múltiples a metas: botón en el gasto vinculado, modal libre en COP y acumulación sobre el abono del mes.
4. Paridad total: ambos roles ven la misma comparativa de cierre; sin deudas se muestra el componente con mensaje, no la gráfica heredada.
5. Seguridad sin nombres de algoritmos y sin etiqueta de rol junto al nombre.
6. Web: «Nueva deuda» centrada arriba y «Deudas registradas» a todo el ancho; móvil sin cambios.
7. Atajos de pago: sin «Ver todos los gastos fijos →» y con la distribución de dos filas en web.
8. «Mis Finanzas» (separado) en Ayuda y comentarios.

### 30.3 Gate QA y cierre documental

- Usuarios QA: `prueba_qa@misfinanzas.local` / `QA_MisFinanzas_2026!` y `prueba_qa_admin@misfinanzas.local` / `QA_Admin_2026!`.
- Gates: `qa_v4_28.py` **32/32** (ambos roles en 1280 y 375 px) y `qa_v4_28b.py` **10/10** (layout, scroll, abono y móvil). Suite: **890 pruebas** en verde.
- Guías, Diccionario de Datos, Constitución, `MEMORY.md` (ADR-90), `AGENTS.md` y esta SRS quedan sincronizados con la versión activa v4.28.

---

## 31. SRS v4.29 — Modales centrados en web

Versión 4.29 y **línea base vigente**. No se rehace v4.28.

### 31.1 No regresión

Intactos: modales de edición de deuda/deducción, checks optimistas, paridad de gráficas, abonos a metas, textos y branding, layout de deudas y atajos.

### 31.2 Cambio

Un `@media (max-width: 767px)` abierto desde el ícono de OLB_BYTE engullía la sección de modales propios, de modo que en escritorio `.app-modal` computaba `position: static` y los modales de abono aparecían como bloques al final de la página. Se cierra ese media query después del ícono y se reabre solo para las reglas móviles de Atajos Guardados. Los modales de crédito, meta, confirmación y aviso vuelven a centrarse en el viewport con `z-index: 9999` en web y móvil.

### 31.3 Gate QA y cierre documental

- Usuarios QA: `prueba_qa@misfinanzas.local` / `QA_MisFinanzas_2026!` y `prueba_qa_admin@misfinanzas.local` / `QA_Admin_2026!`.
- `scripts/qa_v4_29.py`: **18/18 comprobaciones**; en 1280 px los modales de crédito, meta y confirmación miden tarjeta centrada en (640, 450) con `position: fixed` y `z-index: 9999`. Suite: **892 pruebas** en verde.
- Guías, Diccionario de Datos, Constitución, `MEMORY.md` (ADR-91), `AGENTS.md` y esta SRS quedan sincronizados con la versión activa v4.29.

---

## 32. SRS v4.30 — Atajos en dos filas y anulación móvil

Versión 4.30 y **línea base vigente**. No se rehace v4.29.

### 32.1 No regresión

Intactos: donas, Consejero, velocímetros, checks optimistas, abonos a metas, modales de edición y paridad de roles.

### 32.2 Cambios

1. En web (`>= 768px`) cada atajo de pago se reparte en dos filas: descripción completa | «Valor a<br>Pagar:» con el valor en COP | día; abajo referencia con Copiar y botón Pagar. La descripción deja de acortarse con puntos suspensivos. Móvil sin cambios.
2. En móvil, las órdenes de OLB_BYTE se abren en un `<dialog>` nativo. La confirmación de anulación (y el aviso) se trasladan dentro del dialog mientras están visibles, para heredar su capa superior; al cerrarse vuelven al `body`.

### 32.3 Gate QA y cierre documental

- Usuarios QA: `prueba_qa@misfinanzas.local` / `QA_MisFinanzas_2026!` y `prueba_qa_admin@misfinanzas.local` / `QA_Admin_2026!`.
- `scripts/qa_v4_30.py`: **11/11 comprobaciones** (dos filas y texto completo en 1280 px; confirmación visible y al frente del dialog en 375 px). Suite: **894 pruebas** en verde. Gates v4.26/28/29 sin regresiones.
- Guías, Diccionario de Datos, Constitución, `MEMORY.md` (ADR-92), `AGENTS.md` y esta SRS quedan sincronizados con la versión activa v4.30.

---

## 33. SRS v4.31 — Nueva deuda a ancho KPI y grilla 3 × 3

Versión 4.31 y **línea base vigente**. El documento se autodenomina v4.21, pero la línea base pusheada es v4.30; se registra v4.31. Solo se rediseña «Nueva deuda» en escritorio.

### 33.1 No regresión

Intactos: «Deudas registradas», la vista móvil, el alta de deudas, las KPI y el resto de módulos.

### 33.2 Cambios

1. En `>= 768px` la tarjeta «Nueva deuda» ocupa el ancho total de las tres KPI superiores, sin margen lateral.
2. Los seis campos se organizan en `repeat(3, minmax(0, 1fr))`, `gap: 18px` y `align-items: end`: arriba Acreedor | Descripción | Periodicidad; abajo Total Adeudado (COP) | Cuota (COP) | No. Cuotas Pendientes. `margin-inline: -23px` compensa el padding del panel para alinear columnas con las KPI.
3. Pie con `border-top` y botón «Guardar deuda» centrado.

### 33.3 Gate QA y cierre documental

- Usuario QA: `prueba_qa@misfinanzas.local` / `QA_MisFinanzas_2026!`.
- `scripts/qa_v4_31.py`: **10/10 comprobaciones** en 1280 y 375 px, con ancho 1080 px, columnas 348 px centradas en 274/640/1006, alta de deuda correcta y móvil sin desbordamiento. Suite: **896 pruebas** en verde.
- Guías, Diccionario de Datos, Constitución, `MEMORY.md` (ADR-93), `AGENTS.md` y esta SRS quedan sincronizados con la versión activa v4.31.

---

## 34. SRS v4.32 — Campos más compactos en Nueva deuda

Versión 4.32 y **línea base vigente**. Ajuste puntual sobre v4.31, sin tocar móvil ni «Deudas registradas».

### 34.1 Cambios

1. La grilla conserva el ancho de las KPI, pero con `padding-inline: 12px`: los campos quedan separados 12 px de los bordes del panel.
2. Las cajas de texto bajan de 50 a 42 px de alto, con padding 8/12 y tipografía 0.9 rem.

### 34.2 Gate QA y cierre documental

- `scripts/qa_v4_31.py`: **12/12 comprobaciones** (márgenes 12/12, cajas de 42 px, grilla y alta correctas). Suite: **896 pruebas** en verde.
- Guías, Diccionario de Datos, Constitución, `MEMORY.md` (ADR-94), `AGENTS.md` y esta SRS quedan sincronizados con la versión activa v4.32.

---

## 35. SRS v4.33 — Atajos con distribución exacta

Versión 4.33 y **línea base vigente**. Sustituye la distribución de v4.30 en el componente de Atajos de pago.

### 35.1 No regresión

Intactos: vista primaria móvil, cálculos, Optimistic UI, donas, velocímetros y demás modales.

### 35.2 Cambios

1. Web (`>= 768px`): fila 1 descripción + «Fecha pago: Día X» con línea inferior azul; fila 2 «REF: …» a la izquierda y «Valor a Pagar: …» a la derecha; fila 3 Copiar bajo REF y Pagar azul bajo el valor.
2. Móvil (`< 768px`): la lista no cambia; al tocar el atajo, el modal muestra la misma distribución.
3. Los botones Copiar y Pagar se igualan a 34 px de alto para quedar al mismo nivel.

### 35.3 Gate QA y cierre documental

- Usuario QA: `prueba_qa@misfinanzas.local` / `QA_MisFinanzas_2026!`.
- `scripts/qa_v4_33.py`: **30/30 comprobaciones** en 1280 y 375 px. Suite: **899 pruebas** en verde.
- Guías, Diccionario de Datos, Constitución, `MEMORY.md` (ADR-95), `AGENTS.md` y esta SRS quedan sincronizados con la versión activa v4.33.