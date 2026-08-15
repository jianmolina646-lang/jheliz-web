# Fase 2: catálogo e inventario

## Alcance implementado

- Catálogo configurable de servicios digitales.
- Inventario de cuentas completas, sin perfiles ni cupos.
- Estados operativos, fechas de compra y renovación, costo y país.
- Contraseñas cifradas con una clave Fernet proporcionada por entorno.
- Referencias de pago limitadas a etiquetas o cuatro dígitos.
- Búsqueda y filtros por servicio y estado.
- Dashboard con métricas reales y renovaciones de los próximos 30 días.
- Lectura para todos los usuarios autenticados; escritura solo para los roles
  administrador y vendedor.

## Fuera de alcance

Clientes, ventas, cobros, reposiciones, revelado de credenciales, despliegue, DNS,
VPS y cualquier modificación a JhelizTV o Mail Control.

## Operación segura

`ACCOUNT_CREDENTIAL_KEY` debe generarse una sola vez para cada entorno, almacenarse
fuera del repositorio y respaldarse de forma segura. Perderla impide descifrar las
credenciales existentes. Cambiarla requiere una rotación controlada, que no forma
parte de esta fase.
