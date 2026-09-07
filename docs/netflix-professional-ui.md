# Presentación profesional del bot Netflix

## Qué cambia

- Encabezados consistentes con la marca NETFLIX · TEAM JHELIZ y títulos claros.
- Bienvenida breve, nombre escapado, número de cuentas asignadas y acceso directo
  a los comandos, sin enviar automáticamente una lista de correos.
- Teclado de ocho accesos en cuatro filas: Código / Enlace TV, Viaje / Hogar,
  Clave / Activar TV, Mis correos / Ayuda. Se conservan los aliases anteriores.
- Iconos Premium existentes, estilos de botones y alternativas sin estilos.
- Código destacado en una línea independiente, correo enmascarado y enlace
  claramente identificado. Se conserva el URL original escapado para HTML.
- Mensajes de búsqueda, ausencia de resultado, duplicados y errores con la misma
  composición. No se promete una duración total exacta ni se muestra el proveedor
  de correo al cliente.
- Instrucciones distintas para la página de activación TV y el enlace recibido
  por email; confirmación de la cuenta antes de buscar el enlace.
- Ayuda agrupada por tareas, incluidos los comandos administrativos existentes.
  El diagnóstico describe el token como configurado sin afirmar por eso una
  comprobación de conexión Telegram.

## Qué permanece igual

Los comandos, las autorizaciones, los filtros de destinatarios exactos y tipos
permitidos, el acceso a `/clave`, la caché y la búsqueda con `wait_seconds=10`
conservan su lógica. El resultado sigue siendo HTML en texto, con el contrato
de retorno que usa la entrega existente. No se cambian los datos de clientes,
asignaciones, credenciales, límites o el funcionamiento de Disney.

La búsqueda edita su propio mensaje de progreso y no borra el historial.
Los mensajes anteriores no se reescriben ni se envían anuncios a los clientes.
Después del despliegue, `/start` muestra la bienvenida y actualiza el teclado;
`/cmds` muestra la guía de comandos.

## Límites visuales y verificación

Se utiliza presentación nativa de Telegram, no una página web ni CSS. El tema
del chat y el aspecto final de los botones dependen de Telegram. Los iconos
Premium existentes se conservan con sus alternativas Unicode.

Los formatos se limitan a las etiquetas HTML admitidas. En particular, no se
anidan códigos dentro de negrita o cursiva, conforme a las
[restricciones de formato de Telegram](https://core.telegram.org/bots/api#formatting-options).

Las pruebas nuevas cubren marcado equilibrado, escapes de títulos/códigos/URLs,
UTF-8 de los iconos TV, privacidad de correos, mapeo de botones y navegación.
Las pruebas existentes continúan verificando permisos, `/clave`, filtros,
compatibilidad de Disney y conservación del historial.
