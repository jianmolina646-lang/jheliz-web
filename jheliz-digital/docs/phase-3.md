# Fase 3: ventas sin datos del cliente

## Alcance implementado

- Registro de una venta por cuenta completa.
- Importe, fecha, método de cobro, referencia segura y notas internas.
- Cambio atómico de la cuenta desde `Disponible` hasta `Vendida`.
- Bloqueo de ventas repetidas mediante relación única y verificación transaccional.
- Historial y detalle accesibles para usuarios autenticados.
- Registro permitido solo a administradores y vendedores.
- Ventas sin nombre, teléfono, correo, documento ni otro dato del comprador.

## Protección

No se guardan números completos de tarjeta ni CVV. Las referencias de tarjetas se
limitan a los últimos cuatro dígitos. Los registros no tienen edición ni eliminación
desde la interfaz para preservar el historial.

## Fuera de alcance

Clientes, perfiles, cupos, reposiciones, despliegue, DNS, VPS y modificaciones a
JhelizTV, Mail Control o sus bots.
