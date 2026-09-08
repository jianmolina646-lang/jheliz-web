# Recuperación de reenvíos Outlook — 8 de septiembre de 2026

El filtro de destinatarios exactos descartaba reenvíos automáticos Outlook:
los encabezados exteriores apuntan a la casilla central y el destinatario
original aparece en el bloque `De / Enviados / Para / Asunto` del HTML.
En producción se comprobaron 21 solicitudes sin resultado durante 24 horas
para una cuenta; había mensajes de Hogar y acceso temporal dentro de la ventana
de varias solicitudes. Telegram e IMAP respondían y no había errores registrados.

La compatibilidad se activa por casilla mediante
`CODES_IMAP_TRUSTED_AUTHSERV_ID` (o `CODES_IMAP2_TRUSTED_AUTHSERV_ID`).
El valor predeterminado está vacío: no se confía en autenticación de ningún
receptor hasta configurarlo. Para la casilla Proton verificada se utiliza
`mail.protonmail.ch`.

Cuando los destinatarios exteriores no coinciden, Netflix admite únicamente
el formato automático Outlook observado, con remitente exterior exactamente
igual a la cuenta solicitada, marcas de regla automática, autenticación
DKIM/DMARC alineada del receptor configurado y un bloque original inmediato
con remitente Netflix y destinatario exacto. No basta mencionar un correo en
el texto ni escribirlo como nombre visible de otra dirección.

La confianza en Authentication-Results requiere que el receptor configurado
genere sus resultados y proteja su identidad frente a encabezados inyectados.
Esta opción no debe trasladarse a otra casilla/proveedor sin comprobar esa
frontera. La autenticación de Outlook verifica su dominio; la asociación con
la dirección completa depende de que el proveedor controle sus remitentes.

Los avisos explícitos de Hogar ya confirmado y nuevo dispositivo se clasifican
como notificaciones, para evitar que sus enlaces de navegación o recuperación
se presenten como códigos/solicitudes. Los mensajes de actualización de Hogar,
viaje y restablecimiento intencional mantienen su clasificación.

Se conservan asignaciones, comprobación de acceso, límite de antigüedad de
15 minutos, acciones permitidas y compatibilidad de Disney. No hay migraciones
ni cambios de clientes, asignaciones o credenciales.

Las pruebas usan direcciones, códigos y enlaces ficticios. La comprobación
histórica se realiza en un proceso separado y de solo lectura: muestra
conteos y tipos, sin enviar mensajes por Telegram ni registrar entregas.

## Verificación previa al despliegue

- 207 pruebas del módulo `codes` aprobadas en Docker sin red, SQLite en memoria
  y archivos de prueba en volúmenes temporales. Incluyen Netflix y el lector de Disney.
- Reproducción histórica de 21 consultas: se recuperan las ocho solicitudes de
  acceso temporal y cinco de Hogar que tenían un correo del tipo correcto vigente.
  Las otras ocho continúan sin resultado porque solicitaban otro tipo de mensaje.
- Los siete mensajes accionables recuperados (cuatro de viaje, tres de Hogar)
  pasan la identidad exacta y autenticación; los avisos de confirmación y dispositivo
  quedan como `other`. Los cuerpos reales no se almacenan ni se incluyen como fixtures.
