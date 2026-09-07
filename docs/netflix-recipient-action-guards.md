# Netflix: destinatarios exactos y acciones permitidas

Corrección de N01 y N03 de la auditoría del 7 de septiembre de 2026.

## Política autorizada

El propietario autoriza que sus clientes activos reciban enlaces para restablecer
la contraseña de las cuentas asignadas. `/clave` y `password_reset` se conservan
en el menú, los botones y la validación del servidor. No se agregan permisos
administrativos nuevos ni se implementa cierre de sesiones.

## Cambios

- Netflix identifica la cuenta por igualdad exacta con una dirección de los
  encabezados de destinatario/entrega admitidos. Una subcadena, una mención en
  el asunto/cuerpo o un destinatario escrito dentro de un reenvío manual no
  autorizan la entrega. Los reenvíos automáticos que conservan `To` o un
  encabezado de destinatario original siguen siendo compatibles.
- Disney conserva su política previa de búsqueda; el lector recibe explícitamente
  el servicio para evitar cambiar su comportamiento con este parche.
- Los callbacks y la función de entrega rechazan acciones desconocidas o vacías.
  La función interna aún admite `kind=None`, pero solo entrega tipos conocidos.
- El tipo del resultado debe coincidir con lo solicitado. `/enlacetv` mantiene
  su compatibilidad con `passwordless_signin` y `tv_signin`.
- La caché incluye tipo y texto; entradas antiguas sin tipo o con tipo incorrecto
  se ignoran. Se conserva el TTL máximo de cinco segundos.
- El lector Netflix descarta `other` incluso si se pide explícitamente.

## Verificación

160 pruebas del módulo `codes` pasaron en Docker sin red, usando una base
SQLite efímera: 133 existentes y 27 nuevas. Incluyen aislamiento de destinatarios,
continuar buscando después de un mensaje ajeno, reenvíos automáticos, mensajes
HTML, datos de callback manipulados, caché, `/clave`, `/tv` y `/enlacetv`.

La consulta previa al despliegue examinó solo encabezados de 100 mensajes:
74 tenían un destinatario asignado exacto en `To`; 26 no tenían coincidencia
exacta con las asignaciones actuales. No se mostraron direcciones ni códigos.
Ese muestreo no demuestra que todo formato de reenvío existente sea compatible.

## Límites de este parche

No autentica al remitente Netflix ni la cadena de reenvío. Los encabezados exactos
resuelven la confusión de direcciones, pero no sustituyen autenticación del origen.
Un reenvío que solo lleva el destinatario en el cuerpo necesita conservarlo en
los encabezados de entrega; no se vuelve a habilitar la búsqueda insegura como
alternativa.

No cambia el registro previo a confirmación Telegram, la deduplicación compartida,
los índices de botones antiguos, la duración real de la espera o la política de
grupos. Esos hallazgos no forman parte de las dos correcciones autorizadas.

No hay migraciones ni modificaciones de clientes, asignaciones, credenciales,
tokens o límites diarios. Se publica mediante el CI/despliegue existente y se
verifican los archivos del contenedor y la conectividad después del despliegue.
