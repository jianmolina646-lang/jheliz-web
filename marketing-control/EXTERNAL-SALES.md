# Registrar ventas anteriores

Panel → Pedidos y pagos → Registrar venta anterior (solo administrador).
Seleccionar conexión activa, cliente, teléfono internacional sin +, producto,
cuenta disponible o correo/contraseña de la cuenta ya vendida. Introducir inicio
y vencimiento originales en hora de Perú, importe ya cobrado (0 cortesía) y
referencia opcional. Confirmar destinatario y guardar para programar el envío.

El inicio debe ser pasado y el vencimiento futuro. No se envían cuentas vencidas.
Se conserva la vigencia; no se inicia un nuevo período. No cobra dinero.
Se registra el ingreso en la fecha de inicio original, indicado en el formulario.
No usar para ventas ya registradas. Stock, correo por plataforma, referencia
de pago e idempotencia evitan duplicados; asignación y registro son atómicos.
El mismo correo en otra plataforma se admite como stock independiente.

Sheets registra los accesos sin contraseña y las fechas en Vendidas/Ventas Bot;
Ventas Bot y Pagos añaden Origen de venta=Venta externa, al final, sin mover
columnas previas. Entrega ambigua o vencimiento antes del envío: REVIEW, sin
reintento automático para evitar duplicar mensajes. Verificar el chat.

Migración 5: source y external_key en orders, sin borrar datos.
Pruebas aisladas: RUN_EXTERNAL_TEST=1, exclusivamente marketing_commerce_test.
Mensajes simulados, no se envían accesos a clientes reales durante las pruebas.
