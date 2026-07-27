# WhatsApp Business para Jheliz Control

La aplicacion ya soporta una conexion independiente por revendedor mediante
Meta Embedded Signup. Los tokens quedan cifrados en la base de datos y los
webhooks se validan con HMAC-SHA256.

## Variables de produccion

```env
META_APP_ID=
META_APP_SECRET=
META_CONFIG_ID=
META_WEBHOOK_VERIFY_TOKEN=
META_GRAPH_API_VERSION=v23.0
```

No guardar estos valores en Git. En produccion deben cargarse como secretos.

## Configuracion en Meta

1. Verificar legalmente el negocio Jheliz en Meta Business Manager y activar
   autenticacion en dos pasos.
2. Crear una app de tipo Business, agregar WhatsApp y crear una configuracion
   de Embedded Signup.
3. Solicitar App Review y acceso avanzado a `business_management`,
   `whatsapp_business_management` y `whatsapp_business_messaging`.
4. Configurar el dominio `jheliztv.xyz`, HTTPS y la URL permitida para el SDK.
5. Configurar el webhook:
   `https://jheliztv.xyz/meta/whatsapp/webhook/`, usando el mismo valor de
   `META_WEBHOOK_VERIFY_TOKEN`, y suscribir el campo `messages`.
6. Crear y aprobar una plantilla de utilidad llamada
   `recordatorio_vencimiento`, idioma `es`, con cinco variables en este orden:
   cliente, servicio, cuenta enmascarada, fecha de vencimiento y negocio.

Texto sugerido:

> Hola {{1}}. Tu servicio {{2}} (cuenta {{3}}) vence el {{4}}.
> ¿Deseas renovarlo? Mensaje enviado por {{5}}.

## Reglas de envio

- Solo se envia si el cliente tiene WhatsApp y consentimiento marcado.
- Nunca se incluyen contrasenas ni PIN.
- Cada aviso se registra una sola vez por suscripcion, fecha y ventana.
- Los fallos se reintentan hasta tres veces.
- Meta informa los estados enviado, entregado, leido o fallido por webhook.

## Facturacion centralizada

Ser Tech Provider permite integrar cuentas de terceros, pero para que Jheliz
reciba una factura consolidada y asigne su linea de credito a cada WABA se
requiere ademas acceso a una linea de credito como Solution Partner (o trabajar
con uno). El codigo puede operar mientras cada negocio tenga su propio metodo
de pago; la linea de credito se incorpora despues de la aprobacion comercial.
