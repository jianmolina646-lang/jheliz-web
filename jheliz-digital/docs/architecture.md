# Arquitectura inicial

Jheliz Digital es un monolito modular Django independiente. Esta decisión conserva
una operación sencilla y deja límites claros entre áreas sin introducir servicios
distribuidos antes de necesitarlos.

## Módulos actuales

- `config`: configuración, rutas y arranque ASGI/WSGI.
- `accounts`: usuario personalizado y roles administrador, vendedor y solo lectura.
- `dashboard`: entrada autenticada, resumen visual y estado de salud.
- `services`: catálogo de plataformas digitales activas e inactivas.
- `inventory`: cuentas completas, disponibilidad, renovaciones y credenciales
  cifradas mediante Fernet.
- `templates` y `static`: interfaz responsive sin dependencia de un frontend separado.

## Módulos previstos
- `customers`: clientes.
- `sales`: ventas internas de cuentas completas, sin identidad del comprador.
- `billing`: renovaciones y métodos de pago.
- `replacements`: sustituciones trazables y atómicas entre cuentas del mismo servicio.
- `audit`: registro inmutable de acciones sensibles.
- `notifications`: alertas internas y futuras integraciones.

## Protección

La aplicación tendrá base, contenedores, secretos, backups y dominio propios. No
importará modelos ni accederá directamente a las bases de JhelizTV o Mail Control.
