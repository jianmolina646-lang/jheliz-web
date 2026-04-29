# Test plan — Support chat asíncrono (PR #35)

## Qué cambió (en términos visibles para el usuario)
- Antes: `/soporte/<id>/` era una página que recargaba completa al enviar un mensaje, y los mensajes nuevos del staff solo aparecían si el cliente recargaba manualmente.
- Ahora: la página se ve como un chat (burbujas izquierda = soporte, derecha = cliente), enviar un mensaje **no** recarga la página, y los mensajes nuevos aparecen automáticamente cada ~6s vía HTMX polling al endpoint `/<id>/mensajes/`.

Código relevante:
- `templates/support/ticket_detail.html` — UI con `hx-post` y polling (líneas 18–46).
- `templates/support/_messages.html` — partial con `hx-trigger="every 6s"`.
- `support/views.py:ticket_messages` (poll) y `support/views.py:ticket_reply` (HTMX-aware).
- `support/urls.py` — nueva ruta `support:messages`.

## Setup ya hecho
- App local corriendo en `http://localhost:8000`.
- Usuario cliente `cliente_demo` con password `DevinTest123!`.
- Ticket #1 con un mensaje inicial del cliente.

## Flujo principal (adversarial)
Una sesión de navegador como `cliente_demo` con la página `/soporte/1/` abierta. En paralelo, otro terminal inserta un mensaje de staff vía `manage.py shell` para simular la respuesta de soporte.

### Test 1 — Cliente envía mensaje sin recargar la página
1. Estar en `/soporte/1/`. Anotar el contenido del campo de URL **exacto** y el contador de mensajes en pantalla (debe ser 1).
2. Escribir `Probando 123` en el textarea y click en `Enviar`.
3. **Pass criteria**:
   - La URL **no cambia** (sigue siendo `/soporte/1/`, no se ve `/responder/` ni un flash de redirect).
   - Aparece una nueva burbuja a la **derecha** con texto exacto `Probando 123` y etiqueta `Tú` o `Staff · …`.
   - El textarea queda **vacío** después del envío.
   - El número total de burbujas en la pantalla pasa de 1 a 2.
4. **Fail si**: la página se recarga (parpadeo completo), la URL cambia, el textarea conserva el texto enviado, o la nueva burbuja no aparece sin recargar.

> Por qué es adversarial: si `support:reply` no fuera HTMX-aware, devolvería un redirect 302 → la URL `/responder/` aparecería brevemente y la página se recargaría completa. El reload completo es visualmente distinto del swap parcial de HTMX.

### Test 2 — Mensaje de soporte aparece sin que el cliente toque nada (polling)
1. Con la misma página `/soporte/1/` abierta, **sin tocar el navegador**, en otro terminal correr:
   ```
   python manage.py shell -c "from support.models import Ticket, TicketMessage; t=Ticket.objects.get(pk=1); TicketMessage.objects.create(ticket=t, body='Hola, te ayudo enseguida.', is_from_staff=True)"
   ```
2. Esperar hasta 10s (el polling es cada 6s).
3. **Pass criteria**:
   - Aparece una burbuja a la **izquierda** con etiqueta `Soporte Jheliz` y texto exacto `Hola, te ayudo enseguida.`.
   - La aparición ocurre **sin recargar manualmente** la página y sin que el cursor del cliente esté en la pestaña.
4. **Fail si**: el mensaje no aparece tras 12s sin recargar, o aparece solo después de un F5 manual.

> Por qué es adversarial: si el polling no funcionara (p. ej. `_messages.html` sin `hx-trigger`, o `ticket_messages` no devolviera el partial), el mensaje insertado en BD nunca aparecería en la web hasta una recarga manual. La inserción vía shell es invisible al navegador hasta que el polling la trae.

## Lo que no se prueba aquí
- Notificaciones por email — ya existían y no fueron tocadas en este PR.
- Vista del lado admin (`Unfold`) — no cambió.
- Edge case con ticket cerrado — cubierto por test unitario, no necesita ejecución manual.
