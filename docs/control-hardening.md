# Refuerzos de Jheliz Control — septiembre de 2026

- El workflow de despliegue recrea explícitamente `control_alerts_bot`, que usa
  un perfil opcional. Conserva el override local de secretos y comprueba tanto
  las huellas del código compartido como la identidad de la base de datos frente
  a `web`, sin imprimir credenciales. Una divergencia hace fallar el despliegue.
- El panel global requiere `gestion.manage_tenants` y segundo factor confirmado.
  Un administrador sin TOTP solo puede completar la configuración antes de
  acceder a funciones globales. Se aceptan los dispositivos TOTP existentes,
  independientemente de su nombre; no se regeneran. La sesión verificada queda
  ligada al usuario y al dispositivo, y deja de servir si se elimina el dispositivo.
- Los ModelAdmin de gestión requieren también el permiso global, además de sus
  permisos Django. Dar a un revendedor un permiso aislado de modelo no le abre
  el listado global del admin. Los revendedores trabajan mediante `/app/` y el
  bot vinculado; no se cambian sus contraseñas ni fechas.
- La numeración de soporte se serializa bloqueando al propietario, no solo al
  contacto. Se valida que contacto, cliente y suscripción correspondan.
- `TenantOwnedModel` valida coherencia de propietarios en `clean()` y `save()`
  de servicios, clientes, suscripciones, stock, movimientos, soporte, métodos
  de pago y renovaciones. Un dueño existente no puede reasignarse por `save()`.
  No cambia el esquema ni transforma datos anteriores.

## Límites de las validaciones ORM

`QuerySet.update()`, `bulk_create()` y SQL directo no ejecutan `save()`. No deben
utilizarse para reasignar dueños o relaciones desde datos recibidos de usuarios.
Las operaciones masivas administrativas requieren revisión y validación previa;
esto no constituye aislamiento PostgreSQL RLS. Los filtros por dueño siguen
siendo obligatorios en todos los endpoints y en las operaciones del bot.

## Regresiones

- `gestion.test_control_hardening`: obligatoriedad de OTP, conservación de los
  dispositivos, invalidez de sesiones antiguas/revocadas, permisos globales y
  relaciones de otros revendedores.
- `gestion.test_postgres_concurrency`: seis tickets simultáneos de dos contactos,
  doble aprobación concurrente y reemplazos concurrentes sin tocar otro tenant.
  Se ejecuta en PostgreSQL 16 efímero como job obligatorio de CI; en SQLite se
  omite explícitamente por falta de bloqueos de fila.
- Las pruebas de negocio usan `gestion.testing.force_owner_login` para preparar
  una sesión con OTP; las pruebas de autenticación recorren el flujo real.

## Comprobación de producción previa

Se verificó un único usuario activo con privilegios globales (`admin`, ID 3) y
dos dispositivos TOTP confirmados, sin leer sus claves en la salida. Los conteos
de relaciones con dueño distinto fueron cero para suscripciones, stock,
movimientos, contactos/tickets de soporte y renovaciones. La configuración OTP
se compara mediante huella antes y después del despliegue; no se desactiva 2FA
ni se crean usuarios de prueba en producción.
