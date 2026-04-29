# Test plan — admin support chat (PR #36)

## What changed (user-visible)
- New column **Chat** in `Soporte > Tickets` con botón `💬 Responder`.
- Nueva URL `/jheliz-admin/support/ticket/<id>/chat/` con UI de chat (burbujas) idéntica a la del cliente.
- Selector de plantillas (`ReplyTemplate`) que rellena el textarea con el cuerpo renderizado y dispara `use_count += 1` al enviar.
- Enviar respuesta no recarga la página (HTMX) y el ticket pasa a `Esperando al cliente`.

## Primary flow (adversarial)
**Setup state**: ticket #1 = "No me llega Netflix" abierto por `cliente_demo`, status `Esperando soporte (pending_admin)`, 1 mensaje del cliente.

1. **(admin)** Abrir `https://jhelizservicestv.xyz/jheliz-admin/support/ticket/` → debe verse columna **Chat** con un botón `💬 Responder` en la fila del ticket #1.
   - **Pass**: aparece el botón con texto exacto `💬 Responder` y atributo `href` que termina en `/support/ticket/1/chat/`.
   - **Fail si**: no aparece la columna o el href apunta al admin clásico (`/change/`).
2. **(admin)** Click en `💬 Responder`. Debe cargar la pantalla de chat con header `Chat — Ticket #1`, status badge `Esperando soporte`, y la burbuja del cliente con texto `Hola, no me llegan las credenciales del pedido.` a la izquierda.
   - **Pass**: la URL termina en `/jheliz-admin/support/ticket/1/chat/`, aparece exactamente 1 burbuja con ese texto.
   - **Fail si**: aparece 404, 302 al admin clásico, o burbujas duplicadas.
3. **(cliente, otra pestaña)** Abrir `http://localhost:8000/soporte/1/` como `cliente_demo`. Anotar que solo hay 1 mensaje (el del cliente).
4. **(admin)** En el dropdown `Plantillas`, seleccionar `Saludo demo (general)`. El textarea debe quedar pre-llenado con el texto literal `Hola cliente_demo, gracias por escribir. Te ayudo enseguida.` (variable `{nombre}` reemplazada).
   - **Pass**: el textarea contiene exactamente ese texto, no `{nombre}`.
   - **Fail si**: queda vacío o se ven llaves `{}`.
5. **(admin)** Click `Enviar`. Sin recargar la página debe aparecer una nueva burbuja a la **derecha** con el mismo texto y avatar/etiqueta `Soporte`.
   - **Pass**: ahora hay 2 burbujas en la pantalla, la URL no cambió, el textarea quedó vacío.
   - **Fail si**: la URL cambió, hubo recarga full, o la burbuja salió a la izquierda (=is_from_staff=False).
6. **(cliente, sin recargar)** En menos de ~10s la pestaña del cliente debe mostrar automáticamente una nueva burbuja a la **izquierda** con avatar `Soporte Jheliz` y texto literal `Hola cliente_demo, gracias por escribir. Te ayudo enseguida.`.
   - **Pass**: aparece sola sin F5, exactamente con ese texto.
   - **Fail si**: requiere recarga manual, o el texto no coincide.
7. **(verificación DB en shell)** Confirmar en `manage.py shell`:
   - El último `TicketMessage` del ticket #1 tiene `is_from_staff=True` y `author=devin-admin@example.com`.
   - El ticket #1 está en `status='pending_user'`.
   - El template `Saludo demo` tiene `use_count=1` y `last_used_at` no nulo.
   - **Fail si** cualquiera de las tres no se cumple — sería un bug silencioso aunque la UI parezca OK.

## Why this distinguishes broken from working
- Si `is_from_staff` no se setea, las burbujas saldrían del lado equivocado en ambas pestañas.
- Si el HTMX no funciona, la página se recargaría (URL podría parpadear) y la pestaña del cliente no actualizaría sola.
- Si `ReplyTemplate.render(ticket=ticket)` no se llama, las llaves `{nombre}` quedarían visibles.
- Si `use_count` no se incrementa, el seguimiento de uso de plantillas estaría roto aunque la UI parezca correcta.
- Si la URL no se monta antes de `admin.site.urls`, el botón de chat caería en el changeview clásico.
