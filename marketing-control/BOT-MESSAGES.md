# Mensajes WhatsApp — actualización 6

- Bienvenida con accesos a catálogo, compras y soporte. Se responde mediante
  comandos, no botones interactivos ni reconocimiento de opciones numéricas.
- Catálogo con nombre, precio en soles, duración y disponibilidad.
- QR con pasos de pago; comprobante recibido no equivale a pago aprobado.
- /pedidos muestra pendiente, aprobado, entregando, entregado o revisión.
- Entrega con plataforma, correo, contraseña, fechas en Perú y ayuda.
  Ventas externas se identifican sin anunciar un cobro nuevo.
- Soporte presenta comandos completos por compra y tres categorías.
  Confirmación de caso y respuestas/correcciones/reemplazos uniformes.

No se modifican aprobación, propiedad de pedidos, stock, fechas ni reintentos.
No se notifican retroactivamente entregas o casos ya resueltos.
El menú anterior queda guardado en auditoría menu.before_copy_v6, además del
respaldo de sistema 20261013T232318Z. Migración una sola vez: cambios posteriores
del menú desde el panel se conservan.

Pruebas: tests/bot-copy.test.js; flujos aislados de comercio, soporte y ventas
externas en marketing_commerce_test. Los envíos de prueba son simulados.
