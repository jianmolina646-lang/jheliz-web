# Binance: conexión de consulta (pendiente de activar)

Este cambio solamente prepara el cliente de consulta y una prueba de conexión.
No modifica los comandos del bot, no aprueba pedidos y no activa entregas.

1. El titular debe crear una clave API con acceso de lectura únicamente.
   No habilitar trading, retiros ni transferencias. Restringirla a la IP de
   salida verificada del servidor. No enviar secretos por chats ni capturas.
2. Instalar la clave y el secreto en archivos privados fuera del repositorio,
   montados como secretos de solo lectura en el contenedor. Configurar
   `BINANCE_API_KEY_FILE` y `BINANCE_API_SECRET_FILE` con esas rutas.
   También se admiten variables `BINANCE_API_KEY` y `BINANCE_API_SECRET`,
   pero nunca guardarlas en archivos versionados, argumentos o logs.
3. Ejecutar `node scripts/check-binance.mjs` en ese entorno. Consulta solamente
   la última hora; imprime éxito o un error sanitizado, no movimientos.
4. Una consulta correcta prueba acceso, no que todos los tipos de transferencia
   del titular aparezcan. Confirmar una operación real recibida antes de integrar.

Antes de activar pagos: definir moneda y cotización PEN/USDT por pedido;
   guardar la cotización y su vigencia; buscar el transactionId exacto sin cambiar
   mayúsculas; exigir ingreso positivo, tipo admitido, destinatario, importe,
   moneda y fecha correctos; vincular de forma segura al comprador; impedir
   reutilización con una restricción única y transacción de base de datos.
   Un ID por sí solo no prueba quién pagó. Los reembolsos y las salidas no son pagos.
   Una página de 100 resultados puede estar incompleta: no tratarla como exhaustiva.
   Respetar límites de API y no consultar por cada mensaje indiscriminadamente.
   Mantener revisión manual ante ambigüedad, fallo de API o falta de stock.
   Las renovaciones conservan la confirmación administrativa del servicio.

Referencia: https://developers.binance.com/docs/pay/rest-api/Get-Pay-Trade-History

Pruebas unitarias: `node --test tests/binance-pay.test.js`.
