# Fase 4: reposiciones trazables

## Alcance implementado

- Sustitución de una cuenta vendida por otra disponible del mismo servicio.
- Motivo, fecha, notas internas y usuario responsable.
- Cambio atómico de la cuenta anterior a `Retirada` y la nueva a `Vendida`.
- Una única reposición saliente por cuenta y una única asignación entrante.
- Cadenas trazables cuando una cuenta de reposición falla posteriormente.
- Historial sin edición ni eliminación desde la interfaz.
- Lectura autenticada y escritura solo para administradores o vendedores.

## Protección

La operación no modifica ni elimina la venta original. No almacena nombre, teléfono,
correo, documento ni ningún otro dato del comprador. Si una validación falla, ninguno
de los dos estados se modifica.

## Fuera de alcance

Perfiles, cupos, identidad de clientes, revelado de credenciales, despliegue, DNS,
VPS y modificaciones a JhelizTV, Mail Control o sus bots.
