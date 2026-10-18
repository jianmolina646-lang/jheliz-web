# Soporte de compras entregadas

Administración: **Soporte → Registrar reclamo** o casos enviados desde el WhatsApp comprador. La cuenta con rol ADMIN puede abrir/atender un caso, ver el correo vinculado (consulta auditada), corregir accesos, elegir un reemplazo o responder con un mensaje. Las contraseñas nunca se muestran en listas ni reportes.

Cliente: `/soporte` muestra sus compras entregadas y casos; `/soporte UUID_DEL_PEDIDO clave`, `caida` u `otro` registra un reclamo. La pertenencia se valida por instancia y JID, no por un teléfono escrito en el mensaje. Solo existe un caso activo por compra.

**Corregir accesos** guarda y envía datos que el administrador ya corrigió en la plataforma; no cambia contraseñas en Netflix/Prime/etc. **Reemplazar cuenta** bloquea la compra y el inventario en una transacción, retira la cuenta anterior y asigna una del mismo producto que cubra el vencimiento original. Inicio, precio y vencimiento de la compra no cambian. La cuenta retirada no vuelve a estar disponible. Una compra vencida no admite reemplazos ni correcciones, pero sí una respuesta del administrador.

Cada solución se guarda cifrada para envío al WhatsApp original, con una acción única por caso. Sin conexión permanece en cola. El caso se resuelve cuando el envío es aceptado; no prueba lectura del cliente. Un resultado incierto se marca **Revisar envío** y no se reenvía automáticamente. El administrador puede confirmar recepción o reintentar la misma solución tras revisar el chat, sin asignar otra cuenta. No se envían credenciales si el vencimiento transcurrió mientras estaba en cola.

Google Sheets agrega **Soporte** e **Historial soporte**, con referencias, categorías, estados, responsable, fechas y cuenta anterior/nueva. No exporta texto de respuestas ni contraseñas. El historial mantiene vinculadas también las cuentas retiradas. No se agregan ventas ni cobros por un reemplazo.

Pruebas de soporte: únicamente `RUN_SUPPORT_TEST=1` con base `marketing_commerce_test`; ejecutar después de migrar, en serie respecto a las pruebas de comercio. Cubren pertenencia, apertura duplicada, reemplazo concurrente, conservación de vencimiento, corrección, bloqueo de compras vencidas y envío ambiguo sin duplicación. No usar credenciales reales ni enviar mensajes a clientes en estas pruebas.
