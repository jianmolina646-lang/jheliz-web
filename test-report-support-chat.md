# Test report — Support chat asíncrono (PR #35)

Probado contra `main` local + rama `devin/1777425297-support-chat-ui` con la app corriendo en `http://localhost:8000`. Una pestaña como `cliente_demo` sobre `/soporte/1/`.

## Resultado

- **Test 1 — Cliente envía mensaje sin recargar la página**: PASS
  - Texto exacto `Probando 123` apareció como nueva burbuja a la derecha con etiqueta `Tú` y timestamp `28/04 20:20`.
  - URL se mantuvo en `/soporte/1/` (no hubo flash a `/responder/` ni recarga completa).
  - Textarea se vació tras el envío.
  - El total de burbujas pasó de 1 a 2 sin reload.
- **Test 2 — Mensaje del staff aparece solo vía polling**: PASS
  - Se insertó vía `manage.py shell` un `TicketMessage(body='Hola, te ayudo enseguida.', is_from_staff=True)` sin tocar el navegador.
  - Tras ~6–10s la burbuja apareció en la página abierta del cliente, a la **izquierda**, con etiqueta `SOPORTE JHELIZ` y el texto exacto `Hola, te ayudo enseguida.`.
  - No se recargó la página manualmente.
- **Bonus — Notificaciones por email**: PASS (no era objetivo del PR pero se observó)
  - Al insertar el mensaje del staff, el signal `post_save` envió un email a `cliente_demo@example.com` con el asunto `Nueva respuesta en tu ticket #1 — No me llega Netflix`. Esto confirma que el cambio a HTMX no rompió las notificaciones existentes.

## Evidencia visual

| Estado inicial: ticket abierto, 1 burbuja | Test 1: enviar `Probando 123` |
|---|---|
| ![Estado inicial](https://app.devin.ai/attachments/d07e2c21-0112-4cd6-a38c-92b1a556a6ab/screenshot_582109583e7b448a8522e0e95a4101ee.png) | ![Test 1 PASS](https://app.devin.ai/attachments/6d85568d-c9f8-47f9-9932-c0188ba48d22/screenshot_691af7f7559e43f9be859d93e0a50d95.png) |
| URL `/soporte/1/`, mensaje del cliente a la derecha. | Burbuja `Probando 123` 28/04 20:20 a la derecha, textarea vacío, URL no cambió. |

| Test 2: staff inserta mensaje vía shell | Resultado tras polling (~10s) |
|---|---|
| _(comando ejecutado fuera del navegador)_ | ![Test 2 PASS](https://app.devin.ai/attachments/e9f06727-143d-459d-a96b-3fed529b48ba/screenshot_ca8eaf4d2bf84abaae4be1847ae47e83.png) |
| `TicketMessage.objects.create(ticket=t, body='Hola, te ayudo enseguida.', is_from_staff=True)` | Burbuja `SOPORTE JHELIZ — Hola, te ayudo enseguida.` apareció sola a la izquierda. |

## Lo que no se probó

- Vista del lado admin (`Unfold`) — fuera de scope del PR.
- Edge case con ticket cerrado — cubierto en test unitario `support.tests.SupportChatViewsTests`, pasa.
- Comportamiento exacto del fallback no-HTMX (con JS desactivado) — cubierto en `test_non_htmx_reply_redirects_to_detail`, pasa.

## Comandos útiles para reproducir

```
cd /home/ubuntu/repos/jheliz-web
. .venv/bin/activate
python manage.py runserver
# en otro terminal:
python manage.py shell -c "from support.models import Ticket, TicketMessage; t=Ticket.objects.get(pk=1); TicketMessage.objects.create(ticket=t, body='Hola, te ayudo enseguida.', is_from_staff=True)"
```

Tests automáticos: `python manage.py test support.tests` → 5 OK.
