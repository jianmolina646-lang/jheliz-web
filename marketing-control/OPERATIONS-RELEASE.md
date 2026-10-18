# Panel de operaciones · 14 octubre 2026

## Cambios

- Resumen operativo calculado desde la base de datos: pagos pendientes, cola, revisión, próximos vencimientos, stock válido y clientes por bot.
- Separación SALES/CODES persistida para las conexiones existentes. Registro, aprobación, renovaciones y entregas comerciales bloquean el bot de códigos; soporte y recordatorios tampoco salen por él. No se reasignan pedidos antiguos automáticamente.
- Clientes: búsqueda por nombre/teléfono, ficha con cuentas, correos, fechas, pagos, renovaciones y soporte. No se devuelven contraseñas. Los alias de WhatsApp no se fusionan sin identidad verificada.
- Renovaciones: vista independiente, correo, importe, comprobante, vencimiento actual y propuesto. Reutiliza la aprobación con confirmación del servicio.
- Entregas: cola, envío, enviado y revisión. Reintento administrativo con confirmación de no recepción, motivo, bloqueo de concurrencia y máximo tres reintentos; conserva cuenta y fechas. No se reenvían entregas marcadas como completadas.
- Duplicados: errores específicos para correo/plataforma, referencia de pago, cuenta asignada, producto y solicitud pendiente.
- Historial comercial: responsable, fecha y detalles permitidos de aprobaciones, renovaciones, soporte, inventario y entregas. Rechazar un pedido exige motivo.

## Archivos principales

Nuevos: `src/operations.js`, `src/instance-purpose.js`, `public/operations-ui.js`, `public/operations.css`.

Integración: `src/server.js`, `src/migrate.js`, `src/commerce.js`, `src/external-sales.js`, `src/renewals.js`, `src/commerce-worker.js`, `src/support.js`, `src/codes-bridge.js`, `public/app.js`, `public/index.html`, `public/commerce-ui.js`, `public/external-sale-ui.js`.

Pruebas: `tests/operations.test.js`, `tests/operations-integration.mjs`, `tests/renewal-integration.mjs`, `tests/operations-preview.html` y capturas de vista previa locales.

## Verificación ejecutada

- `npm test`: 35 aprobadas, 0 fallidas, 5 opcionales omitidas.
- Integración aislada de operaciones: guardas de bot, autorización por rol, confirmación del reintento, dos solicitudes concurrentes, fechas preservadas, un envío simulado, bloqueo de un pedido antiguo ligado a códigos, seis endpoints y privacidad.
- Integración aislada de renovaciones: titularidad, concurrencia, confirmación, aprobación repetida, fechas y mismo inventario, una entrega simulada.
- Chrome local con datos ficticios: cinco vistas, apertura de ficha y diálogo de reintento. Capturas de escritorio y tamaño móvil. No es una sesión real de producción.
- Migración aditiva ejecutada y API/worker recreados. `/health` devolvió `ok`; conexiones `Codigos Jheliz` (CODES) y `jheliz` (SALES) CONNECTED.

## Respaldo y límites

Respaldo previo del código y PostgreSQL: `/opt/jheliz-operations-backup-20261014-0800/`, acceso solo de administración.

No se enviaron mensajes de prueba a clientes reales. “Enviado” significa que el envío fue aceptado por la conexión, no que el cliente lo leyó. WhatsApp no permite garantizar ausencia absoluta de duplicados ante un resultado de red ambiguo; por eso la recuperación requiere revisión humana y no es automática.

Se conservan todos los registros de negocio. Las pruebas SQL crearon y eliminaron únicamente sus esquemas aleatorios de prueba. Las vistas muestran límites explícitos (200 clientes por búsqueda, 300 movimientos; ficha hasta 500 operaciones y 100 casos). No se modificó la estructura de Google Sheets ni la lógica de obtención de códigos.
