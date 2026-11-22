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

    * Si $\text{Total Devengado} \le 2\text{ SMMLV}$, el sistema asigna el valor legal del auxilio de transporte y muestra la diferencia restante para alcanzar el tope.

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