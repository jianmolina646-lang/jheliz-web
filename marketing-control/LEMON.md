# Validación de Lemon Cash

## Flujo

Solo pedidos nuevos posteriores a la activación. El cliente envía el comprobante
y el bot solicita nombre completo y apellidos. La respuesta se vincula al pedido
pendiente del mismo chat e instancia, nunca a un pedido indicado por el usuario.
`Binance` deriva a revisión manual. Los precios y monedas del catálogo no cambian.

`/corregirnombre` permite volver a solicitar el nombre para el pedido pendiente
del mismo chat e instancia, con comprobante recibido y pago Lemon. Conserva captura,
monto y pedido; elimina el nombre anterior mientras espera la nueva respuesta.
No modifica pedidos aprobados/entregados ni Binance. Hasta cinco solicitudes nuevas
por 15 minutos; las repeticiones mientras espera el nombre no reinician el proceso.
Si existe un pago compatible en importe/ventana pero no en nombre, se registra
NAME_MISMATCH y se intenta un aviso por ciclo de corrección, sin revelar titulares.
Los envíos de resultado incierto no se repiten automáticamente para evitar duplicados.

La imagen no prueba el ingreso. OCR local (Tesseract) exige un único monto explícito
en soles, coincidente en dos modos de lectura y con el precio del pedido. También
exige una fecha completa seguida de la hora de operación, coincidente en ambas
lecturas. Acepta fechas día/mes/año o meses en español, con hora de 24 horas o AM/PM;
interpreta la fecha en Perú (UTC-5). No toma relojes sin fecha ni completa el año.
El minuto debe coincidir exactamente con INTERNALDATE de Gmail (recepción del
mensaje), no con la hora de envío de la captura por WhatsApp. No flexibiliza el nombre.
Una captura ilegible, ambigua o con otro importe
bloquea la aprobación automática; puede reemplazarse mientras siga pendiente.
Las capturas anteriores sin lectura deben reenviarse. Binance sigue siendo manual.
El OCR no sustituye la verificación del ingreso auténtico. Gmail se abre
en modo de solo lectura. El lector acepta únicamente notificaciones dirigidas a
`natalivillalima@gmail.com`, de `notificaciones@lemoncash.com.ar`, con DKIM de Lemon
y DMARC aprobados en la cabecera superior de autenticación de Gmail. El formato
debe identificar al beneficiario configurado, importe PEN, titular, ID de operación
y referencia externa. Formatos distintos se rechazan.

Nombre completo normalizado (sin búsqueda aproximada), importe exacto en centavos,
pago posterior al pedido dentro de dos horas, recibido hace menos de un día y sin
retraso superior a diez minutos respecto a la fecha del correo. No aprueba pagos
anteriores al pedido. Más de un pago o pedido coincidente requiere revisión.

Los dos identificadores de cada pago se contrastan con pagos automáticos y
referencias manuales. Transacción con bloqueo compartido entre aprobaciones
manuales/automáticas, ledger persistente, asignación de stock con bloqueo de fila.
Las renovaciones también se aprueban automáticamente: el propietario confirmó que
el servicio ya está renovado en la plataforma y el bot solo actualiza la vigencia.
No se asigna ni consume otra cuenta. Se actualiza el vencimiento del pedido original
y se reinicia su recordatorio. Los planes de 30 días se renuevan por un mes calendario
en hora de Perú, conservando el día cuando existe y ajustando al último día si no.
Se cuenta desde el vencimiento vigente o desde la aprobación si ya venció.
Otros planes conservan su duración en días. Stock insuficiente en compras nuevas
o una cuenta original inválida en renovaciones deja el pedido pendiente.

La entrega usa el flujo existente: estados APPROVED/SENDING/DELIVERED y REVIEW si
el resultado de WhatsApp es ambiguo. No se reenvían cuentas automáticamente tras
un envío incierto. No se promete disponibilidad permanente de Gmail o WhatsApp.

## Operación

Alerta al administrador (51978640413): pedidos PENDING con comprobante desde hace
5 minutos generan PAYMENT_DELAYED, único por pedido. Se toma la fecha de creación
del aviso RECEIPT, correspondiente al primer comprobante; reenviarlo no reinicia
el plazo. Se omiten los pedidos resueltos antes del envío. El aviso incluye cliente,
plataforma, monto, referencia y motivo disponible, sin enlace web ni datos del correo.
La entrega usa SENDING/SENT/REVIEW: un envío incierto no se reintenta automáticamente.
Si WhatsApp está desconectado, la alerta espera a que vuelva la conexión.

- Activación: fila `lemon_verifier`, `enabled=true` y `activated_at` estable.
- Desactivar: `UPDATE lemon_verifier SET enabled=false WHERE id=1;`.
- Estado: `enabled`, `activated_at`, `last_success`, `last_error` en esa fila.
- `last_success` refleja lectura/procesamiento exitoso, no necesariamente un pago.
- `orders.lemon_check`: WAITING, AMBIGUOUS, AMBIGUOUS_OR_USED, NO_STOCK,
  RENEWAL_REVIEW, MANUAL_BINANCE, RECEIPT_UNREADABLE, RECEIPT_AMOUNT_MISMATCH,
  RECEIPT_TIME_UNREADABLE, RECEIPT_TIME_MISMATCH o VERIFIED.
- Auditoría: `payment.lemon_verified`; no contiene contraseñas ni cuerpos de correos.
- El nombre del pagador se guarda en el pedido; el ledger guarda la normalización
  necesaria para conciliación y evitar reutilización. Limitar el acceso a la base.
- Credencial: `/opt/jheliz-marketing-secrets/lemon-gmail-app-password`, propietario
  1000:1000 y modo 0400, montada como `/run/secrets/lemon-gmail-app-password`.
  No guardar en Git, variables de entorno, logs ni mensajes.
- Sondeo con exclusión mutua cada 60 segundos cuando hay pedidos con nombre pendiente.
  Ante errores, cero aprobaciones y estado para revisión. No salta errores de fetch
  ni procesa lotes truncados mayores de 200 mensajes.
- Cambiar la contraseña de Google puede revocar la contraseña de aplicación.

## Pruebas

`node --test tests/*.test.js` y
`python3 -B -m unittest discover -s tests -p test_lemon_mail.py -v`.
`RUN_LEMON_TEST=1` requiere exclusivamente una base desechable llamada
`marketing_lemon_test`: la prueba elimina sus datos sintéticos, nunca usar producción.

La validación por correo no equivale a una confirmación bancaria independiente.
Si varias personas comparten el mismo nombre e importe, se deriva a revisión;
la revisión manual de casos dudosos sigue siendo necesaria.
